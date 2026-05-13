"""Tests for risk intent detection, parameter extraction, and output guardrails.

Verifies that the agent orchestrator correctly:
- Routes risk-related user prompts to the risk budget task type.
- Extracts position-sizing parameters from natural-language prompts.
- Identifies missing required parameters (entry_price, invalidation_price).
- Never emits buy/sell language in risk tool outputs.
"""
from __future__ import annotations

import pytest


class TestAgentRiskRouting:
    """Test that the orchestrator correctly detects risk-related user intents."""

    def test_risk_position_size_intent_detected(self) -> None:
        """'100万账户，50入场，45止损，1%风险，能配多少？' should trigger risk intent."""
        try:
            from app.agent.orchestrator import _is_risk_intent
            from app.agent.orchestrator import _extract_risk_params
        except ImportError as exc:
            pytest.skip(f"Risk orchestrator functions not available: {exc}")

        prompt = "100万账户，50入场，45止损，1%风险，能配多少？"
        assert _is_risk_intent(prompt), (
            "Expected '能配多少' to trigger risk intent detection"
        )
        params = _extract_risk_params(prompt, [])
        assert params.get("account_equity") == 1_000_000
        assert params.get("intent_type") == "position_size"

    def test_exposure_intent_detected(self) -> None:
        """'AI算力链是不是太集中？' should trigger exposure check."""
        try:
            from app.agent.orchestrator import _is_risk_intent
            from app.agent.orchestrator import _extract_risk_params
        except ImportError as exc:
            pytest.skip(f"Risk orchestrator functions not available: {exc}")

        prompt = "AI算力链是不是太集中？"
        assert _is_risk_intent(prompt), (
            "Expected '是不是太集中' to trigger exposure risk intent"
        )
        params = _extract_risk_params(prompt, [])
        assert params.get("intent_type") == "exposure"

    def test_missing_entry_price_triggers_followup(self) -> None:
        """Missing entry_price should ask user, not fabricate."""
        try:
            from app.agent.orchestrator import _extract_risk_params
        except ImportError as exc:
            pytest.skip(f"Risk orchestrator functions not available: {exc}")

        prompt = "100万账户，45止损，1%风险，能配多少？"
        params = _extract_risk_params(prompt, [])
        assert "account_equity" in params
        assert params.get("has_all_position_params") is False
        missing = params.get("missing_params", [])
        missing_str = " ".join(str(m) for m in missing)
        assert any("entry" in m.lower() or "入场" in m for m in missing), (
            f"Expected entry_price in missing_params, got {missing_str}"
        )

    def test_missing_invalidation_price_triggers_followup(self) -> None:
        """Missing invalidation_price should ask user."""
        try:
            from app.agent.orchestrator import _extract_risk_params
        except ImportError as exc:
            pytest.skip(f"Risk orchestrator functions not available: {exc}")

        prompt = "100万账户，入场价50，1%风险，能配多少？"
        params = _extract_risk_params(prompt, [])
        assert "account_equity" in params
        assert "entry_price" in params
        assert params.get("has_all_position_params") is False
        missing = params.get("missing_params", [])
        missing_str = " ".join(str(m) for m in missing)
        assert any(
            "invalid" in m.lower() or "止损" in m or "无效" in m
            for m in missing
        ), f"Expected invalidation_price in missing_params, got {missing_str}"

    def test_risk_output_no_buy_sell(self) -> None:
        """Risk tool output must not contain buy/sell recommendations."""
        try:
            from app.risk.guardrails import FORBIDDEN_TERMS, sanitize_risk_output
        except ImportError as exc:
            pytest.skip(f"Risk guardrails not available: {exc}")

        sample = "根据风险预算结果，建议买入1000股，建议卖出200股，可以重仓配置"
        result = sanitize_risk_output(sample)
        for term in FORBIDDEN_TERMS:
            assert term not in result, (
                f"Forbidden term '{term}' found in sanitized output"
            )
