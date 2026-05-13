"""Tests for ResearchThesis model and thesis generation engine."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import ResearchThesis
from app.engines.thesis_engine import (
    extract_theses_from_agent_claims,
    generate_theses_from_report,
    thesis_to_markdown,
)


# =============================================================================
# ResearchThesis model
# =============================================================================


class TestResearchThesisModel:
    """Test ResearchThesis model creation and validation."""

    def test_create_thesis_minimal(self, db_session) -> None:
        """Can create a thesis with minimum required fields."""
        thesis = ResearchThesis(
            source_type="daily_report",
            subject_type="stock",
            subject_id="300308",
            subject_name="中际旭创",
            thesis_title="趋势确认测试",
            thesis_body="该标的趋势偏强，需关注持续性。",
        )
        db_session.add(thesis)
        db_session.commit()
        db_session.refresh(thesis)

        assert thesis.id is not None
        assert thesis.source_type == "daily_report"
        assert thesis.subject_type == "stock"
        assert thesis.subject_id == "300308"
        assert thesis.subject_name == "中际旭创"
        assert thesis.thesis_title == "趋势确认测试"
        assert thesis.thesis_body == "该标的趋势偏强，需关注持续性。"
        # Model defaults
        assert thesis.status == "active"
        assert thesis.horizon_days == 20
        assert thesis.created_at is not None

    def test_create_thesis_full(self, db_session) -> None:
        """Can create a thesis with all fields populated."""
        thesis = ResearchThesis(
            source_type="daily_report",
            source_id="42",
            subject_type="industry",
            subject_id="101",
            subject_name="AI算力",
            thesis_title="AI算力热度持续扩散",
            thesis_body="AI算力产业热度维持较强扩散态势，持续关注。",
            direction="positive",
            horizon_days=60,
            confidence=75.0,
            evidence_refs_json=json.dumps(
                [{"source": "industry_heat", "heat_score": 82.0}]
            ),
            key_metrics_json=json.dumps(
                [{"name": "热度分", "value": 82.0}]
            ),
            invalidation_conditions_json=json.dumps(
                ["热度连续3个交易日回落超过15%"]
            ),
            risk_flags_json=json.dumps(
                ["产业热度不代表个股表现"]
            ),
            status="active",
        )
        db_session.add(thesis)
        db_session.commit()
        db_session.refresh(thesis)

        assert thesis.id is not None
        assert thesis.source_type == "daily_report"
        assert thesis.source_id == "42"
        assert thesis.subject_type == "industry"
        assert thesis.direction == "positive"
        assert thesis.horizon_days == 60
        assert thesis.confidence == 75.0

        # JSON fields should be stored and retrievable
        evidence_refs = json.loads(thesis.evidence_refs_json)
        assert len(evidence_refs) == 1
        assert evidence_refs[0]["source"] == "industry_heat"
        assert evidence_refs[0]["heat_score"] == 82.0

        key_metrics = json.loads(thesis.key_metrics_json)
        assert key_metrics[0]["name"] == "热度分"
        assert key_metrics[0]["value"] == 82.0

        invalidation = json.loads(thesis.invalidation_conditions_json)
        assert "回落" in invalidation[0]

        risk_flags = json.loads(thesis.risk_flags_json)
        assert risk_flags[0] == "产业热度不代表个股表现"

    def test_thesis_evidence_refs_stored(self, db_session) -> None:
        """Thesis with empty evidence_refs can be saved (not enforced at DB level)."""
        thesis = ResearchThesis(
            source_type="daily_report",
            subject_type="stock",
            subject_id="688235",
            subject_name="样本",
            thesis_title="空证据测试",
            thesis_body="暂无证据引用。",
            evidence_refs_json="[]",
        )
        db_session.add(thesis)
        db_session.commit()
        db_session.refresh(thesis)

        assert json.loads(thesis.evidence_refs_json) == []

    def test_thesis_direction_values(self, db_session) -> None:
        """Thesis direction accepts various valid values."""
        for direction in ("positive", "negative", "neutral", "mixed"):
            thesis = ResearchThesis(
                source_type="daily_report",
                subject_type="stock",
                subject_id="T001",
                subject_name=f"测试_{direction}",
                thesis_title=f"方向测试_{direction}",
                thesis_body=f"方向{direction}测试正文。",
                direction=direction,
            )
            db_session.add(thesis)
            db_session.commit()
            db_session.refresh(thesis)
            assert thesis.direction == direction
            db_session.delete(thesis)
            db_session.commit()

    def test_thesis_confidence_range(self, db_session) -> None:
        """Confidence should be 0-100; boundary values are accepted."""
        for confidence in (0.0, 50.0, 100.0):
            thesis = ResearchThesis(
                source_type="daily_report",
                subject_type="stock",
                subject_id="T001",
                subject_name="测试",
                thesis_title=f"置信度测试_{confidence}",
                thesis_body="测试正文。",
                confidence=confidence,
            )
            db_session.add(thesis)
            db_session.commit()
            db_session.refresh(thesis)
            assert thesis.confidence == confidence
            db_session.delete(thesis)
            db_session.commit()

    def test_thesis_status_transitions(self, db_session) -> None:
        """Model allows setting different thesis statuses."""
        thesis = ResearchThesis(
            source_type="daily_report",
            subject_type="stock",
            subject_id="T001",
            subject_name="测试",
            thesis_title="状态测试",
            thesis_body="测试正文。",
            status="active",
        )
        db_session.add(thesis)
        db_session.commit()

        thesis.status = "validated"
        db_session.commit()
        db_session.refresh(thesis)
        assert thesis.status == "validated"

        thesis.status = "invalidated"
        db_session.commit()
        db_session.refresh(thesis)
        assert thesis.status == "invalidated"

    def test_thesis_created_at_auto_set(self, db_session) -> None:
        """created_at should be set on insert."""
        thesis = ResearchThesis(
            source_type="daily_report",
            subject_type="stock",
            subject_id="T001",
            subject_name="测试",
            thesis_title="时间测试",
            thesis_body="测试正文。",
        )
        db_session.add(thesis)
        db_session.commit()
        db_session.refresh(thesis)
        assert thesis.created_at is not None
        assert isinstance(thesis.created_at, datetime)
        assert thesis.updated_at is not None


# =============================================================================
# generate_theses_from_report  (no DB needed -- pure dict-based)
# =============================================================================


class TestThesisEngine:
    """Test thesis generation engine (generate_theses_from_report)."""

    def test_generate_theses_from_report_context(self) -> None:
        """Engine should generate 3-5 theses from valid report context."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 85.0, "explanation": "AI算力热度高", "top_keywords": ["算力", "光模块"]},
                {"industry_id": 2, "heat_score": 72.0, "explanation": "机器人热度中等", "top_keywords": ["减速器"]},
                {"industry_id": 3, "heat_score": 45.0, "explanation": "消费电子中性", "top_keywords": []},
            ],
            top_trend_stocks=[
                {"code": "300308", "name": "中际旭创", "final_score": 82.0, "trend_score": 68.0, "risk_penalty": 0.5, "rating": "强观察"},
                {"code": "688235", "name": "样本", "final_score": 62.0, "trend_score": 55.0, "risk_penalty": 1.0, "rating": "观察"},
            ],
            risk_alerts=["市场波动率上升", "北向资金连续流出"],
            market_summary="市场整体偏强，结构性机会集中",
        )

        assert 3 <= len(theses) <= 5
        # Should include different subject types
        subject_types = {t["subject_type"] for t in theses}
        assert "market" in subject_types or "stock" in subject_types

    def test_thesis_has_required_fields(self) -> None:
        """Each generated thesis should have all required fields."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 82.0, "explanation": "热度高", "top_keywords": ["算力"]},
            ],
            top_trend_stocks=[
                {"code": "300308", "name": "中际旭创", "final_score": 82.0, "trend_score": 68.0, "risk_penalty": 0.5, "rating": "强观察"},
            ],
            risk_alerts=["风险预警1"],
            market_summary="市场偏强",
        )

        assert len(theses) >= 3
        for thesis in theses:
            assert "thesis_title" in thesis
            assert "thesis_body" in thesis
            assert "direction" in thesis
            assert thesis["direction"] in ("positive", "negative", "neutral", "mixed")
            assert "horizon_days" in thesis
            assert isinstance(thesis["horizon_days"], int)
            assert "confidence" in thesis
            assert isinstance(thesis["confidence"], (int, float))
            assert 0 <= thesis["confidence"] <= 100
            assert "evidence_refs" in thesis
            assert "invalidation_conditions" in thesis
            assert isinstance(thesis["invalidation_conditions"], list)
            assert "subject_type" in thesis
            assert "subject_id" in thesis or thesis.get("subject_id") is None
            assert "subject_name" in thesis

    def test_thesis_not_just_guanzhu(self) -> None:
        """Thesis titles should be judgment sentences, not just '关注XXX'."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 90.0, "explanation": "AI算力热度很高", "top_keywords": ["算力", "CPO"]},
                {"industry_id": 2, "heat_score": 60.0, "explanation": "新能源中性", "top_keywords": []},
            ],
            top_trend_stocks=[
                {"code": "300308", "name": "中际旭创", "final_score": 82.0, "trend_score": 68.0, "risk_penalty": 0.5, "rating": "强观察"},
            ],
            risk_alerts=[],
            market_summary="市场整体偏强",
        )

        for thesis in theses:
            assert not thesis["thesis_title"].startswith("关注"), (
                f"Thesis title should not be a simple '关注' statement: '{thesis['thesis_title']}'"
            )

    def test_generate_theses_empty_context(self) -> None:
        """Should handle empty/missing context gracefully without crashing."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[],
            top_trend_stocks=[],
            risk_alerts=[],
            market_summary="",
        )

        # Should return a non-crash result (may be empty or contain theses)
        assert isinstance(theses, list)

    def test_generate_theses_partial_data(self) -> None:
        """Should handle partial data without crashing."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 75.0, "explanation": "热度中等", "top_keywords": []},
            ],
            top_trend_stocks=[],  # No stocks
            risk_alerts=["预警1"],
            market_summary="市场中性",
        )

        assert isinstance(theses, list)
        # Should at least generate industry and market theses
        assert len(theses) >= 1

    def test_thesis_guardrails_applied(self) -> None:
        """Generated thesis text should not contain forbidden terms."""
        forbidden = ["买入", "卖出", "稳赚", "必涨", "无风险", "保本"]
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 88.0, "explanation": "热度高", "top_keywords": ["算力"]},
            ],
            top_trend_stocks=[
                {"code": "300308", "name": "中际旭创", "final_score": 82.0, "trend_score": 68.0, "risk_penalty": 0.5, "rating": "强观察"},
            ],
            risk_alerts=["风险"],
            market_summary="市场偏强",
        )

        for thesis in theses:
            text = f"{thesis.get('thesis_title', '')} {thesis.get('thesis_body', '')}"
            for term in forbidden:
                assert term not in text, (
                    f"Forbidden term '{term}' found in thesis text: '{text[:100]}'"
                )


class TestThesisEngineEdgeCases:
    """Edge cases and special scenarios for thesis generation."""

    def test_market_thesis_strong_market(self) -> None:
        """Strong market data should generate a positive market thesis."""
        stocks = [
            {"code": f"T{i:04d}", "name": f"股票{i}", "final_score": 85.0, "trend_score": 70.0, "risk_penalty": 0.0, "rating": "强观察"}
            for i in range(10)
        ]
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 80.0, "explanation": "热度高", "top_keywords": ["算力"]},
            ],
            top_trend_stocks=stocks,
            risk_alerts=[],
            market_summary="市场整体偏强",
        )

        market_theses = [t for t in theses if t.get("subject_type") == "market"]
        assert len(market_theses) >= 1
        market = market_theses[0]
        assert market["direction"] in ("positive", "neutral")
        assert market["confidence"] >= 30

    def test_stock_thesis_high_risk(self) -> None:
        """Stock with high risk_penalty should generate a cautionary thesis."""
        theses = generate_theses_from_report(
            report_date=date(2026, 5, 13),
            top_industries=[
                {"industry_id": 1, "heat_score": 60.0, "explanation": "中性", "top_keywords": []},
            ],
            top_trend_stocks=[
                {"code": "300999", "name": "高风险股", "final_score": 45.0, "trend_score": 30.0, "risk_penalty": 5.0, "rating": "仅记录"},
            ],
            risk_alerts=[],
            market_summary="市场中性",
        )

        stock_theses = [t for t in theses if t.get("subject_type") == "stock"]
        if stock_theses:
            stock = stock_theses[0]
            assert stock["direction"] == "negative"
            assert "风险" in stock["thesis_title"]

    def test_thesis_to_markdown_output(self) -> None:
        """thesis_to_markdown should produce valid markdown."""
        theses = [
            {
                "subject_type": "market",
                "subject_id": None,
                "subject_name": "大盘综合分析",
                "thesis_title": "市场整体偏强",
                "thesis_body": "当前趋势偏强。",
                "direction": "positive",
                "horizon_days": 20,
                "confidence": 70,
                "evidence_refs": [],
                "key_metrics": [{"name": "前10平均评分", "value": 75.0}],
                "invalidation_conditions": ["市场评分连续下降"],
                "risk_flags": ["整体评分不代表个股表现"],
            }
        ]

        md = thesis_to_markdown(theses)
        assert "今日核心观点" in md
        assert "市场整体偏强" in md
        assert "方向" in md
        assert "置信度" in md
        assert "不构成任何投资建议" in md or "不构成投资建议" in md

    def test_thesis_to_markdown_empty(self) -> None:
        """Empty thesis list should return empty string."""
        assert thesis_to_markdown([]) == ""


class TestExtractThesesFromAgentClaims:
    """Test extract_theses_from_agent_claims function."""

    def test_extract_empty_claims(self, db_session) -> None:
        """Empty claims list should return empty list."""
        ids = extract_theses_from_agent_claims(db_session, run_id=1, claims=[], artifact_id=1)
        assert ids == []

    def test_extract_single_claim(self, db_session) -> None:
        """Single valid claim should create a thesis."""
        claims = [
            {"text": "中际旭创趋势偏强，持续关注进一步确认。", "confidence": "high", "section": "个股分析", "evidence_ref_ids": ["1", "2"]},
        ]
        ids = extract_theses_from_agent_claims(db_session, run_id=42, claims=claims, artifact_id=1)
        assert len(ids) == 1

        thesis = db_session.get(ResearchThesis, ids[0])
        assert thesis is not None
        assert thesis.source_type == "agent_run"
        assert thesis.source_id == "42"

    def test_extract_claim_too_short(self, db_session) -> None:
        """Very short claim text should be skipped."""
        claims = [{"text": "短", "confidence": "low", "section": ""}]
        ids = extract_theses_from_agent_claims(db_session, run_id=1, claims=claims, artifact_id=1)
        assert ids == []
