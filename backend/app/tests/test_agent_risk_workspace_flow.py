"""Tests for the agent risk workspace workflow — integrated import, exposure,
risk-card generation, and guardrail enforcement.

Verifies that:
- After importing positions via DB, exposure check returns correct data.
- Risk cards can carry imported portfolio context.
- Guardrails remain active after import (no buy/sell language).
"""
from __future__ import annotations

import pytest


class TestAgentRiskWorkflow:
    """Test the post-import risk workspace flow."""

    def test_exposure_check_after_import(self, db_session) -> None:
        """After importing positions, exposure check returns correct data."""
        try:
            from app.db.models import RiskPortfolio, RiskPosition
            from app.risk.exposure import compute_exposure
        except ImportError as exc:
            pytest.skip(f"Risk exposure module not available: {exc}")

        portfolio = RiskPortfolio(
            user_id="test_user",
            name="工作流测试组合",
            total_equity=1_000_000.0,
            cash=200_000.0,
        )
        db_session.add(portfolio)
        db_session.flush()

        positions_data = [
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="300308",
                name="中际旭创",
                market_value=500_000.0,
                industry="通信",
                theme_tags_json='["AI算力", "光模块"]',
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="000858",
                name="五粮液",
                market_value=300_000.0,
                industry="食品饮料",
                theme_tags_json='["消费"]',
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="600519",
                name="贵州茅台",
                market_value=200_000.0,
                industry="食品饮料",
                theme_tags_json='["消费", "白酒"]',
            ),
        ]
        for p in positions_data:
            db_session.add(p)
        db_session.commit()

        exposure = compute_exposure(portfolio.id, db_session)

        # Total market value should sum correctly
        assert exposure["total_market_value"] == 1_000_000.0

        # Industry exposure
        assert "通信" in exposure["industry_exposure"]
        assert "食品饮料" in exposure["industry_exposure"]
        # 通信: 500k/1M = 50%, 食品饮料: (300k+200k)/1M = 50%
        assert exposure["industry_exposure"]["通信"] == 50.0
        assert exposure["industry_exposure"]["食品饮料"] == 50.0

        # Theme exposure
        assert "AI算力" in exposure["theme_exposure"]
        assert "光模块" in exposure["theme_exposure"]
        # AI算力: 500k/1M = 50%
        assert exposure["theme_exposure"]["AI算力"] == 50.0

        # Position-level data
        positions_lookup = {p["symbol"]: p for p in exposure["positions"]}
        assert "300308" in positions_lookup
        assert positions_lookup["300308"]["position_pct"] == 50.0
        assert positions_lookup["300308"]["industry"] == "通信"

        # Warnings: 300308 is 50% (>20%), 通信 is 50% (>40%)
        warnings_text = " ".join(exposure["warnings"])
        assert "300308" in warnings_text, (
            "Expected concentration warning for 300308 at 50%"
        )
        assert "通信" in warnings_text, (
            "Expected industry exposure warning for 通信 at 50%"
        )

    def test_risk_card_generated_after_import(self) -> None:
        """Risk card includes imported portfolio context."""
        try:
            from app.agent.schemas import RiskCardData
        except ImportError as exc:
            pytest.skip(f"RiskCardData schema not available: {exc}")

        # A risk card carrying a portfolio_id links back to the imported context
        card = RiskCardData(
            card_type="exposure_check",
            title="主题暴露检查 — 导入后",
            symbol="300308",
            portfolio_id=1,
            theme_exposure_after_pct=45.0,
            warnings=["AI算力 暴露 45.0% 超过主题集中度限制30%"],
            disclaimer="本模块仅用于风险预算测算，不构成投资建议。",
            calculation_explain=(
                "导入后AI算力主题暴露为45%，超过30%限制"
            ),
        )
        assert card.portfolio_id is not None, (
            "Risk card must carry portfolio_id after import"
        )
        assert card.portfolio_id == 1
        assert card.symbol == "300308"
        assert len(card.warnings) == 1
        assert card.disclaimer, "Risk card must include disclaimer"
        assert "不构成" in card.disclaimer

    def test_guardrails_still_active(self) -> None:
        """After import, guardrails must not output buy/sell language."""
        try:
            from app.risk.guardrails import (
                FORBIDDEN_TERMS,
                sanitize_risk_output,
            )
        except ImportError as exc:
            pytest.skip(f"Risk guardrails not available: {exc}")

        # Simulated output from a risk workflow after import
        sample = (
            "导入组合后AI算力暴露过高，建议卖出部分光模块仓位, "
            "建议买入消费板块补充分散度"
        )
        result = sanitize_risk_output(sample)
        for term in FORBIDDEN_TERMS:
            assert term not in result, (
                f"Forbidden term '{term}' survived sanitization in "
                f"post-import risk output"
            )

        # Also verify the agent-level guardrails
        try:
            from app.agent.guardrails import (
                FORBIDDEN_REPLACEMENTS,
                sanitize_financial_text,
            )
        except ImportError:
            pytest.skip("Agent guardrails not available")

        agent_sample = (
            "根据风险分析，建议买入2000股，可以重仓这个标的"
        )
        sanitized, _warnings = sanitize_financial_text(agent_sample)
        for term in FORBIDDEN_REPLACEMENTS:
            assert term not in sanitized, (
                f"Agent forbidden term '{term}' survived sanitization"
            )
