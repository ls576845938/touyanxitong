"""Unit tests for the VisionPortfolioExtractor adapter internals."""
from __future__ import annotations

import json

from app.agent.vision.adapter import VisionPortfolioExtractor, _safe_float


class TestSafeFloat:
    def test_numeric_string(self):
        assert _safe_float("3.14") == 3.14

    def test_none(self):
        assert _safe_float(None) is None

    def test_invalid(self):
        assert _safe_float("abc") is None

    def test_default(self):
        assert _safe_float(None, default=0.0) == 0.0


class TestStripMarkdownFence:
    def setup_method(self):
        self.ext = VisionPortfolioExtractor()

    def test_triple_backtick_json(self):
        fenced = "```json\n{\"key\": \"value\"}\n```"
        cleaned = self.ext._strip_markdown_fence(fenced)
        assert json.loads(cleaned) == {"key": "value"}

    def test_triple_backtick_plain(self):
        fenced = "```\n{\"a\": 1}\n```"
        cleaned = self.ext._strip_markdown_fence(fenced)
        assert json.loads(cleaned) == {"a": 1}

    def test_no_fence(self):
        clean = "{\"b\": 2}"
        assert self.ext._strip_markdown_fence(clean) == clean

    def test_surrounding_text(self):
        fenced = "Some text before\n```\n{\"c\": 3}\n```\nSome text after"
        cleaned = self.ext._strip_markdown_fence(fenced)
        assert json.loads(cleaned) == {"c": 3}


class TestBuildUserPrompt:
    def setup_method(self):
        self.ext = VisionPortfolioExtractor()

    def test_all_hints(self):
        prompt = self.ext._build_user_prompt("同花顺", "A", "这是我的持仓")
        assert "同花顺" in prompt
        assert "A股" in prompt
        assert "我的持仓" in prompt

    def test_no_hints(self):
        prompt = self.ext._build_user_prompt(None, None, None)
        assert "持仓" in prompt

    def test_market_hint_only(self):
        prompt = self.ext._build_user_prompt(None, "HK", None)
        assert "港股" in prompt


class TestNormalizeResponse:
    def setup_method(self):
        self.ext = VisionPortfolioExtractor()

    def test_success_case(self):
        mock = {
            "status": "success",
            "broker_name": "同花顺",
            "account_equity": 1_000_000.0,
            "cash": 50_000.0,
            "positions": [
                {
                    "symbol": "000858",
                    "name": "五粮液",
                    "quantity": 1000,
                    "market_value": 150000.0,
                    "cost": 140.0,
                    "weight_pct": 15.0,
                    "unrealized_pnl": 10000.0,
                    "confidence": 0.95,
                    "raw_text": "五粮液 1000股 市值15万",
                }
            ],
            "warnings": [],
            "unmapped_rows": [],
        }
        result = self.ext._normalize_response(mock)
        assert result.status == "success"
        assert result.broker_name == "同花顺"
        assert result.account_equity == 1_000_000.0
        assert len(result.positions) == 1
        assert result.positions[0].symbol == "000858"
        assert result.positions[0].name == "五粮液"
        assert result.positions[0].confidence == 0.95
        assert result.needs_user_confirmation is True

    def test_non_list_positions(self):
        result = self.ext._normalize_response({"status": "success", "positions": "invalid"})
        assert result.positions == []

    def test_normalizes_bad_status(self):
        result = self.ext._normalize_response({"status": "unknown", "positions": []})
        assert result.status == "parse_failed"

    def test_handles_missing_fields(self):
        mock = {
            "status": "success",
            "positions": [
                {"symbol": None, "name": "未知", "quantity": None, "confidence": None}
            ],
        }
        result = self.ext._normalize_response(mock)
        assert result.positions[0].symbol is None
        assert result.positions[0].quantity is None
        assert result.positions[0].confidence == 0.0

    def test_unmapped_rows_preserved(self):
        mock = {
            "status": "success",
            "positions": [],
            "unmapped_rows": ["某证券 1000股", "合计行"],
        }
        result = self.ext._normalize_response(mock)
        assert result.unmapped_rows == ["某证券 1000股", "合计行"]

    def test_empty_image_vision_unavailable(self):
        """Without API key, extract returns vision_unavailable."""
        from app.config import settings

        if settings.openai_api_key:
            return  # skip when configured

        result = self.ext.extract(image_bytes=b"")
        assert result.status == "vision_unavailable"
        assert result.needs_user_confirmation is True
        assert len(result.positions) == 0
