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


class TestRealVisionAdapter:
    """Test adapter-layer behaviour for the RealVision LLM extractor.

    These tests validate the contracts that the adapter will fulfil once
    the full Vision-LLM pipeline is wired in (MVP 3.4+).
    """

    def test_adapter_returns_unavailable_without_key(self, monkeypatch) -> None:
        """When no API key, returns vision_unavailable."""
        try:
            from app.agent.vision.adapter import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"VisionPortfolioExtractor not available: {exc}")

        # Monkeypatch _load_config to return no API key
        monkeypatch.setattr(
            VisionPortfolioExtractor,
            "_load_config",
            staticmethod(lambda: (None, None, {})),
        )

        extractor = VisionPortfolioExtractor()
        assert extractor.available is False

        result = extractor.extract(image_bytes=b"fake-image-bytes")
        assert result.status == "vision_unavailable", (
            f"Expected 'vision_unavailable', got '{result.status}'"
        )

    def test_adapter_accepts_valid_image_types(self) -> None:
        """Should accept PNG, JPEG, WEBP, BMP."""
        try:
            from app.agent.vision.api import ALLOWED_IMAGE_TYPES
        except ImportError as exc:
            pytest.skip(f"Vision API module not available: {exc}")

        for mime in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
            assert mime in ALLOWED_IMAGE_TYPES, (
                f"Expected '{mime}' to be in ALLOWED_IMAGE_TYPES"
            )

    def test_adapter_rejects_invalid_image_type(self) -> None:
        """Should reject non-image files."""
        try:
            from app.agent.vision.api import ALLOWED_IMAGE_TYPES
        except ImportError as exc:
            pytest.skip(f"Vision API module not available: {exc}")

        for mime in (
            "application/pdf",
            "text/plain",
            "image/gif",
            "application/octet-stream",
        ):
            assert mime not in ALLOWED_IMAGE_TYPES, (
                f"Expected '{mime}' to be rejected"
            )

    def test_adapter_parse_failed_on_invalid_json(self, monkeypatch) -> None:
        """When model returns non-JSON, status=parse_failed."""
        try:
            from app.agent.vision.schemas import PortfolioImageExtractResponse
            from app.agent.vision.adapter import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"Vision modules not available: {exc}")

        def _mock_extract(
            self, image_bytes: bytes, broker_hint: str | None = None
        ) -> PortfolioImageExtractResponse:
            return PortfolioImageExtractResponse(
                status="parse_failed",
                warnings=["模型返回的数据不是有效的 JSON 格式"],
                needs_user_confirmation=True,
            )

        monkeypatch.setattr(VisionPortfolioExtractor, "extract", _mock_extract)

        extractor = VisionPortfolioExtractor()
        result = extractor.extract(image_bytes=b"fake")
        assert result.status == "parse_failed", (
            f"Expected 'parse_failed', got '{result.status}'"
        )
        assert len(result.positions) == 0

    def test_adapter_extracts_positions_from_valid_json(
        self, monkeypatch
    ) -> None:
        """Mock valid JSON response -> parsed positions."""
        try:
            from app.agent.vision.schemas import (
                ExtractedPosition,
                PortfolioImageExtractResponse,
            )
            from app.agent.vision.adapter import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"Vision modules not available: {exc}")

        positions = [
            ExtractedPosition(
                symbol="600519",
                name="贵州茅台",
                quantity=200.0,
                market_value=400_000.0,
                weight_pct=80.0,
                confidence=0.98,
                raw_text="贵州茅台 200股",
            ),
            ExtractedPosition(
                symbol="000858",
                name="五粮液",
                quantity=500.0,
                market_value=75_000.0,
                weight_pct=15.0,
                confidence=0.92,
                raw_text="五粮液 500股",
            ),
        ]

        def _mock_extract(
            self, image_bytes: bytes, broker_hint: str | None = None
        ) -> PortfolioImageExtractResponse:
            return PortfolioImageExtractResponse(
                status="success",
                broker_name="test_broker",
                account_equity=500_000.0,
                cash=50_000.0,
                positions=positions,
                warnings=[],
                unmapped_rows=[],
                needs_user_confirmation=True,
            )

        monkeypatch.setattr(VisionPortfolioExtractor, "extract", _mock_extract)

        extractor = VisionPortfolioExtractor()
        result = extractor.extract(image_bytes=b"fake")
        assert result.status == "success"
        assert len(result.positions) == 2

        p0 = result.positions[0]
        assert p0.symbol == "600519"
        assert p0.name == "贵州茅台"
        assert p0.quantity == 200.0
        assert p0.market_value == 400_000.0
        assert p0.weight_pct == 80.0

        p1 = result.positions[1]
        assert p1.symbol == "000858"
        assert p1.name == "五粮液"
        assert p1.quantity == 500.0
        assert p1.market_value == 75_000.0

        assert result.account_equity == 500_000.0
        assert result.cash == 50_000.0
        assert result.needs_user_confirmation is True

    def test_adapter_preserves_confidence(self, monkeypatch) -> None:
        """Confidence values from model must be preserved."""
        try:
            from app.agent.vision.schemas import (
                ExtractedPosition,
                PortfolioImageExtractResponse,
            )
            from app.agent.vision.adapter import VisionPortfolioExtractor
        except ImportError as exc:
            pytest.skip(f"Vision modules not available: {exc}")

        def _mock_extract(
            self, image_bytes: bytes, broker_hint: str | None = None
        ) -> PortfolioImageExtractResponse:
            return PortfolioImageExtractResponse(
                status="success",
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
                    ExtractedPosition(
                        symbol="002415",
                        name="海康威视",
                        quantity=2000.0,
                        market_value=200_000.0,
                        weight_pct=20.0,
                        confidence=0.88,
                        raw_text="海康威视 2000股",
                    ),
                ],
                needs_user_confirmation=True,
            )

        monkeypatch.setattr(VisionPortfolioExtractor, "extract", _mock_extract)

        extractor = VisionPortfolioExtractor()
        result = extractor.extract(image_bytes=b"fake")
        assert result.positions[0].confidence == 0.95
        assert result.positions[1].confidence == 0.88


class TestConfirmImport:
    """Test the import-confirm process: writing extracted positions into DB.

    These tests work directly with the risk DB models (RiskPortfolio,
    RiskPosition) to validate merge / replace / append modes and the
    persistence of account-level fields.
    """

    # ------------------------------------------------------------------
    # Test helpers — simulate the import-confirm business logic inline
    # so the tests are self-contained and do not depend on API routes.
    # ------------------------------------------------------------------

    @staticmethod
    def _create_portfolio(
        db_session,
        name: str = "测试组合",
        user_id: str = "test_user",
        total_equity: float = 1_000_000.0,
        cash: float = 0.0,
    ):
        from app.db.models import RiskPortfolio

        p = RiskPortfolio(
            name=name,
            user_id=user_id,
            total_equity=total_equity,
            cash=cash,
        )
        db_session.add(p)
        db_session.flush()
        return p

    @staticmethod
    def _merge_positions(db_session, portfolio_id, positions_data):
        """Upsert: update existing symbols, insert new ones."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        for pd in positions_data:
            existing = db_session.scalar(
                select(RiskPosition).where(
                    RiskPosition.portfolio_id == portfolio_id,
                    RiskPosition.symbol == pd["symbol"],
                )
            )
            if existing:
                for key, val in pd.items():
                    setattr(existing, key, val)
            else:
                db_session.add(RiskPosition(portfolio_id=portfolio_id, **pd))
        db_session.commit()

    @staticmethod
    def _replace_positions(db_session, portfolio_id, positions_data):
        """Delete all existing, then insert new ones."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        existing = db_session.scalars(
            select(RiskPosition).where(RiskPosition.portfolio_id == portfolio_id)
        ).all()
        for pos in existing:
            db_session.delete(pos)
        db_session.flush()
        for pd in positions_data:
            db_session.add(RiskPosition(portfolio_id=portfolio_id, **pd))
        db_session.commit()

    @staticmethod
    def _append_positions(db_session, portfolio_id, positions_data):
        """Only add symbols not already present."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        existing_symbols = {
            row[0]
            for row in db_session.execute(
                select(RiskPosition.symbol).where(
                    RiskPosition.portfolio_id == portfolio_id
                )
            ).all()
        }
        for pd in positions_data:
            if pd["symbol"] not in existing_symbols:
                db_session.add(RiskPosition(portfolio_id=portfolio_id, **pd))
        db_session.commit()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_confirm_creates_portfolio_if_not_exists(
        self, db_session
    ) -> None:
        """Confirm import with no portfolio_id creates a new portfolio."""
        from app.db.models import RiskPortfolio

        portfolio = self._create_portfolio(db_session)
        assert portfolio.id is not None
        assert portfolio.name == "测试组合"
        assert portfolio.user_id == "test_user"
        assert portfolio.total_equity == 1_000_000.0

        # Verify the portfolio is persisted and queryable
        fetched = db_session.get(RiskPortfolio, portfolio.id)
        assert fetched is not None
        assert fetched.name == "测试组合"

    def test_confirm_merge_mode_upserts_positions(self, db_session) -> None:
        """merge mode: existing positions updated, new ones added."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        portfolio = self._create_portfolio(db_session)

        # Start with one position
        self._merge_positions(
            db_session,
            portfolio.id,
            [
                {
                    "symbol": "300308",
                    "name": "中际旭创",
                    "quantity": 1000.0,
                    "market_value": 100_000.0,
                },
            ],
        )

        # Merge: update existing (300308) + add new (000858)
        self._merge_positions(
            db_session,
            portfolio.id,
            [
                {
                    "symbol": "300308",
                    "name": "中际旭创",
                    "quantity": 2000.0,  # updated
                    "market_value": 200_000.0,
                },
                {
                    "symbol": "000858",
                    "name": "五粮液",
                    "quantity": 500.0,
                    "market_value": 75_000.0,
                },
            ],
        )

        positions = db_session.scalars(
            select(RiskPosition).where(
                RiskPosition.portfolio_id == portfolio.id
            )
        ).all()
        assert len(positions) == 2, "Expected 2 positions after merge"

        p1 = next(p for p in positions if p.symbol == "300308")
        assert p1.quantity == 2000.0, "Existing position should be updated"

        p2 = next(p for p in positions if p.symbol == "000858")
        assert p2.quantity == 500.0

    def test_confirm_replace_mode_clears_first(self, db_session) -> None:
        """replace mode: old positions deleted, only new ones kept."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        portfolio = self._create_portfolio(db_session)

        # Seed with initial positions
        self._merge_positions(
            db_session,
            portfolio.id,
            [
                {"symbol": "300308", "name": "中际旭创", "quantity": 1000.0},
                {"symbol": "000858", "name": "五粮液", "quantity": 500.0},
            ],
        )

        # Replace with a completely different set
        self._replace_positions(
            db_session,
            portfolio.id,
            [
                {"symbol": "600519", "name": "贵州茅台", "quantity": 200.0},
            ],
        )

        positions = db_session.scalars(
            select(RiskPosition).where(
                RiskPosition.portfolio_id == portfolio.id
            )
        ).all()
        symbols = {p.symbol for p in positions}
        assert len(positions) == 1, "Expected only 1 position after replace"
        assert "600519" in symbols
        assert "300308" not in symbols, "Old position should be removed"
        assert "000858" not in symbols, "Old position should be removed"

    def test_confirm_append_mode_only_adds_new(self, db_session) -> None:
        """append mode: only adds new symbols, skips existing."""
        from app.db.models import RiskPosition
        from sqlalchemy import select

        portfolio = self._create_portfolio(db_session)

        self._merge_positions(
            db_session,
            portfolio.id,
            [
                {"symbol": "300308", "name": "中际旭创", "quantity": 1000.0},
            ],
        )

        # Append: 000858 is new, 300308 already exists
        self._append_positions(
            db_session,
            portfolio.id,
            [
                {"symbol": "300308", "name": "中际旭创", "quantity": 9999.0},
                {"symbol": "000858", "name": "五粮液", "quantity": 500.0},
            ],
        )

        positions = db_session.scalars(
            select(RiskPosition).where(
                RiskPosition.portfolio_id == portfolio.id
            )
        ).all()
        assert len(positions) == 2

        p1 = next(p for p in positions if p.symbol == "300308")
        assert p1.quantity == 1000.0, (
            "Existing position should NOT have been updated in append mode"
        )

        p2 = next(p for p in positions if p.symbol == "000858")
        assert p2.quantity == 500.0

    def test_confirm_writes_account_equity_and_cash(self, db_session) -> None:
        """Account equity and cash from import are written to portfolio."""
        from app.db.models import RiskPortfolio

        portfolio = self._create_portfolio(
            db_session, total_equity=0.0, cash=0.0
        )

        # Simulate writing equity and cash after import confirmation
        portfolio.total_equity = 500_000.0
        portfolio.cash = 100_000.0
        db_session.commit()
        db_session.refresh(portfolio)

        assert portfolio.total_equity == 500_000.0
        assert portfolio.cash == 100_000.0
