"""Tests for risk output guardrails — sanitization, disclaimer, forbidden terms."""
from __future__ import annotations

import pytest

from app.risk.guardrails import FORBIDDEN_TERMS, RISK_DISCLAIMER, sanitize_risk_output


class TestRiskGuardrails:
    """Test that risk module outputs are sanitized and compliant."""

    def test_forbidden_terms_replaced(self) -> None:
        """All forbidden terms should be replaced by safe alternatives."""
        for forbidden, replacement in FORBIDDEN_TERMS.items():
            text = f"这是一个{forbidden}的测试输出"
            result = sanitize_risk_output(text)

            assert forbidden not in result, (
                f"Forbidden term '{forbidden}' was not replaced"
            )
            assert replacement in result, (
                f"Replacement '{replacement}' not found in sanitized output for '{forbidden}'"
            )

    def test_disclaimer_always_present(self) -> None:
        """RISK_DISCLAIMER must contain key compliance phrases."""
        assert "不构成任何投资建议" in RISK_DISCLAIMER
        assert "风险" in RISK_DISCLAIMER
        assert "买卖" in RISK_DISCLAIMER or "投资" in RISK_DISCLAIMER
        assert "市场有风险" in RISK_DISCLAIMER
        assert "独立判断" in RISK_DISCLAIMER

    def test_no_buy_recommendation_in_outputs(self) -> None:
        """Sanitized output should never contain buy/sell recommendations."""
        test_cases = [
            "建议买入该标的",
            "建议卖出该标的",
            "应该买这个股票",
            "应该卖这个股票",
            "可以重仓配置",
            "满仓操作",
            "梭哈入场",
            "加杠杆操作",
            "稳赚不赔",
            "必涨形态",
            "无风险套利",
            "保证收益产品",
            "仓位推荐方案",
        ]
        for case in test_cases:
            result = sanitize_risk_output(case)
            # All forbidden keys should be absent from sanitized output
            for forbidden in FORBIDDEN_TERMS:
                assert forbidden not in result, (
                    f"Forbidden term '{forbidden}' survived sanitization in: '{case}'"
                )
