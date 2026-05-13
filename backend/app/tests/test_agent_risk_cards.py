"""Tests for risk card data structures and content guardrails.

Verifies that ``RiskCardData`` (position_size, exposure_check, etc.) can be
carried in ``AgentArtifact.content_json`` and that every card instance
includes the required disclaimer and never contains forbidden buy/sell terms.
"""
from __future__ import annotations

import json

import pytest


class TestRiskCards:
    """Test risk card schema, disclaimers, and forbidden-term filtering."""

    def test_artifact_content_json_accepts_risk_cards(self) -> None:
        """AgentArtifact.content_json can hold risk_cards key."""
        try:
            from app.agent.schemas import RiskCardData
        except ImportError as exc:
            pytest.skip(f"RiskCardData schema not available: {exc}")

        card = RiskCardData(
            card_type="position_size",
            title="仓位测算: 300308",
            symbol="300308",
            max_loss_amount=10000.0,
            estimated_position_pct=10.0,
            rounded_quantity=2000,
            calculation_explain="基于1%风险预算",
            disclaimer="本模块仅用于风险预算测算，不构成投资建议。",
        )
        # Simulate how content_json is stored in the DB (serialised as a JSON string)
        content_json = {
            "risk_cards": [card.model_dump()],
            "summary": "仓位测算结果",
        }
        serialised = json.dumps(content_json, ensure_ascii=False)
        deserialised = json.loads(serialised)

        assert "risk_cards" in deserialised
        assert len(deserialised["risk_cards"]) == 1
        rc = deserialised["risk_cards"][0]
        assert rc["card_type"] == "position_size"
        assert rc["symbol"] == "300308"
        assert rc["rounded_quantity"] == 2000

    def test_risk_card_has_disclaimer(self) -> None:
        """Every risk card must include disclaimer."""
        try:
            from app.agent.schemas import RiskCardData
        except ImportError as exc:
            pytest.skip(f"RiskCardData schema not available: {exc}")

        card = RiskCardData(
            card_type="exposure_check",
            title="主题暴露检查",
            symbol="300308",
            theme_exposure_after_pct=45.0,
            disclaimer="本模块仅用于风险预算测算，不构成投资建议。",
        )
        assert card.disclaimer, "Expected non-empty disclaimer on risk card"
        assert "不构成" in card.disclaimer

    def test_risk_card_no_forbidden_terms(self) -> None:
        """Risk card text must not contain forbidden buy/sell terms."""
        try:
            from app.agent.schemas import RiskCardData
            from app.risk.guardrails import FORBIDDEN_TERMS
        except ImportError as exc:
            pytest.skip(f"RiskCardData or FORBIDDEN_TERMS not available: {exc}")

        card = RiskCardData(
            card_type="position_size",
            title="仓位测算",
            symbol="300308",
            calculation_explain="建议买入2000股，建议卖出部分仓位",
            disclaimer="本模块仅用于风险预算测算，不构成投资建议。",
        )
        from app.risk.guardrails import sanitize_risk_output

        sanitised_explain = sanitize_risk_output(card.calculation_explain)
        for term in FORBIDDEN_TERMS:
            assert term not in sanitised_explain, (
                f"Forbidden term '{term}' found in risk card calculation_explain"
            )

        # Also check the title via sanitise
        sanitised_title = sanitize_risk_output(card.title)
        for term in FORBIDDEN_TERMS:
            assert term not in sanitised_title, (
                f"Forbidden term '{term}' found in risk card title"
            )
