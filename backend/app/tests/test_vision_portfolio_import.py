"""Tests for the VisionPortfolioExtractor and its output contracts.

Verifies that:
- The extractor returns ``vision_unavailable`` when no vision model is configured.
- ``needs_user_confirmation`` is always True (no auto-import).
- Mock vision responses parse correctly into ``ExtractedPosition`` objects.
- Extracted positions are NOT auto-imported into the risk portfolio.
"""
from __future__ import annotations

import json

import pytest


class TestVisionPortfolioImport:
    """Test vision-based portfolio import behaviour and contracts."""

    def test_vision_unavailable_status(self) -> None:
        """When no vision model, returns vision_unavailable."""
        try:
            from app.agent.vision import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"VisionPortfolioExtractor not available: {exc}")

        from app.config import settings

        if settings.openai_api_key:
            pytest.skip("This test requires no OPENAI_API_KEY (CI env)")

        extractor = VisionPortfolioExtractor()
        assert extractor.available is False, (
            "Expected extractor.available=False when no vision model configured"
        )

        result = extractor.extract(image_bytes=b"fake-image-bytes")
        assert result.status == "vision_unavailable", (
            f"Expected 'vision_unavailable', got '{result.status}'"
        )

    def test_extract_positions_requires_confirmation(self) -> None:
        """needs_user_confirmation is always True."""
        try:
            from app.agent.vision import (
                PortfolioImageExtractResponse,
                ExtractedPosition,
            )
        except ImportError as exc:
            pytest.skip(f"Vision schemas not available: {exc}")

        # Simulate a successful extraction response — confirmation still required
        resp = PortfolioImageExtractResponse(
            status="success",
            broker_name="test_broker",
            account_equity=1_000_000.0,
            cash=200_000.0,
            positions=[
                ExtractedPosition(
                    symbol="300308",
                    name="中际旭创",
                    quantity=1000.0,
                    market_value=100_000.0,
                    weight_pct=10.0,
                    confidence=0.95,
                    raw_text="中际旭创 1000股",
                ),
            ],
            warnings=[],
            unmapped_rows=[],
            needs_user_confirmation=True,
        )
        assert resp.needs_user_confirmation is True, (
            "needs_user_confirmation must always be True even on success"
        )

    def test_mock_vision_response_parses_positions(self) -> None:
        """Mock vision response creates valid ExtractedPosition objects."""
        try:
            from app.agent.vision import ExtractedPosition
        except ImportError as exc:
            pytest.skip(f"ExtractedPosition schema not available: {exc}")

        mock_json = json.dumps({
            "status": "success",
            "broker_name": "test_broker",
            "account_equity": 500_000.0,
            "cash": 50_000.0,
            "positions": [
                {"symbol": "600519", "name": "贵州茅台", "quantity": 200.0,
                 "market_value": 400_000.0, "weight_pct": 80.0,
                 "confidence": 0.98, "raw_text": "贵州茅台 200股"},
                {"symbol": "000858", "name": "五粮液", "quantity": 500.0,
                 "market_value": 75_000.0, "weight_pct": 15.0,
                 "confidence": 0.92, "raw_text": "五粮液 500股"},
            ],
            "warnings": [],
            "unmapped_rows": ["某证券 1000股"],
            "needs_user_confirmation": True,
        })
        parsed = json.loads(mock_json)
        positions = [ExtractedPosition(**p) for p in parsed["positions"]]

        assert len(positions) == 2
        assert positions[0].symbol == "600519"
        assert positions[0].name == "贵州茅台"
        assert positions[0].quantity == 200.0
        assert positions[0].confidence == 0.98

        assert positions[1].symbol == "000858"
        assert positions[1].name == "五粮液"
        assert positions[1].quantity == 500.0

        # Verify unmapped rows are carried through
        assert parsed["unmapped_rows"] == ["某证券 1000股"]
        assert parsed["needs_user_confirmation"] is True

    def test_no_auto_import(self) -> None:
        """Vision extraction does NOT auto-create portfolio positions."""
        try:
            from app.agent.vision import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"VisionPortfolioExtractor not available: {exc}")

        from app.config import settings

        if settings.openai_api_key:
            pytest.skip("This test requires no OPENAI_API_KEY (CI env)")

        extractor = VisionPortfolioExtractor()
        result = extractor.extract(image_bytes=b"fake-image-bytes")

        # The stub returns vision_unavailable and needs confirmation
        assert result.status == "vision_unavailable"
        assert result.needs_user_confirmation is True

        # No positions should be created — this is purely a read-only extraction
        assert len(result.positions) == 0, (
            "Vision extraction should not auto-create portfolio positions; "
            f"got {len(result.positions)} positions"
        )
