"""Tests for risk position-sizing calculators."""
from __future__ import annotations

import pytest

from app.risk.calculators import calculate_position_size
from app.risk.guardrails import FORBIDDEN_TERMS, RISK_DISCLAIMER
from app.risk.schemas import PositionSizeRequest


class TestPositionSize:
    """Test position-size calculation engine."""

    def test_basic_calculation(self, db_session) -> None:
        """100万账户, 1%风险, 50入场, 45止损 -> 2000股 max."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="300308",
            entry_price=50,
            invalidation_price=45,
            risk_per_trade_pct=1.0,
            market="A",
        )
        result = calculate_position_size(req)

        assert result.rounded_quantity == 2000
        assert result.max_loss_amount == 10000
        assert result.error is None
        # Verify intermediate values
        assert result.risk_per_share == 5.0
        # Position should be ~10% of equity with 1% max loss risk
        assert result.estimated_position_value == 100000.0
        assert result.estimated_position_pct == 10.0

    def test_a_share_lot_size_100(self, db_session) -> None:
        """A股应该按100取整."""
        req = PositionSizeRequest(
            account_equity=500000,
            symbol="000001",
            entry_price=10,
            invalidation_price=9.5,
            risk_per_trade_pct=1.0,
            market="A",
        )
        result = calculate_position_size(req)
        # risk_amount = 5000; risk_per_share = 0.5; raw = 10000
        # lot_size=100 -> floor(10000/100)*100 = 10000
        assert result.rounded_quantity is not None
        assert result.rounded_quantity % 100 == 0

    def test_invalidation_above_entry_returns_error(self, db_session) -> None:
        """无效点高于入场价 -> error."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="300308",
            entry_price=50,
            invalidation_price=55,
            risk_per_trade_pct=1.0,
        )
        result = calculate_position_size(req)

        assert result.error is not None
        assert "高于" in result.error or "低于" in result.error
        # Core calculation fields should be None when there is an error
        assert result.rounded_quantity is None
        assert result.max_loss_amount is None

    def test_missing_invalidation_returns_error(self, db_session) -> None:
        """无效点为None -> error."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="300308",
            entry_price=50,
            invalidation_price=None,
            risk_per_trade_pct=1.0,
        )
        result = calculate_position_size(req)

        assert result.error is not None
        assert "无效条件" in result.error or "止损" in result.error or "无效点" in result.error
        assert result.rounded_quantity is None

    def test_risk_over_2_pct_warns(self, db_session) -> None:
        """单笔风险超2% -> warning."""
        req = PositionSizeRequest(
            account_equity=100000,
            symbol="300308",
            entry_price=50,
            invalidation_price=45,
            risk_per_trade_pct=2.5,
            market="A",
        )
        result = calculate_position_size(req)

        # Should not be an error (risk_pct up to 5.0 is valid in Request schema)
        assert result.error is None
        assert any("单笔风险" in w for w in result.warnings)

    def test_disclaimer_present(self, db_session) -> None:
        """响应必须包含免责声明."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="300308",
            entry_price=50,
            invalidation_price=45,
            risk_per_trade_pct=1.0,
        )
        result = calculate_position_size(req)

        assert RISK_DISCLAIMER in result.disclaimer

    def test_no_buy_sell_language(self, db_session) -> None:
        """响应不能有买入卖出."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="300308",
            entry_price=50,
            invalidation_price=45,
            risk_per_trade_pct=1.0,
        )
        result = calculate_position_size(req)

        # Check the full output for forbidden terms
        output = (
            (result.calculation_explain or "")
            + " "
            + " ".join(result.warnings or [])
            + " "
            + (result.disclaimer or "")
        )
        for term in FORBIDDEN_TERMS:
            assert term not in output, (
                f"Forbidden term '{term}' found in position-size output"
            )

    def test_hk_lot_size_defaults_1(self, db_session) -> None:
        """港股默认lot=1."""
        req = PositionSizeRequest(
            account_equity=1000000,
            symbol="00700",
            entry_price=500,
            invalidation_price=480,
            risk_per_trade_pct=1.0,
            market="HK",
        )
        result = calculate_position_size(req)
        # risk_amount=10000; risk_per_share=20; raw=500
        # lot_size=1 -> floor(500/1)*1 = 500
        assert result.rounded_quantity == 500
        assert result.error is None

    def test_large_position_warns(self, db_session) -> None:
        """超大仓位 -> warning."""
        # Use a tight stop (small risk_per_share) so raw_quantity is huge
        # and the position exceeds max_single_position_pct
        req = PositionSizeRequest(
            account_equity=100000,
            symbol="300308",
            entry_price=50,
            invalidation_price=49.5,
            risk_per_trade_pct=2.0,
            market="A",
            max_single_position_pct=30.0,
        )
        result = calculate_position_size(req)
        # risk_amount=2000; risk_per_share=0.5; raw=4000
        # Without constraint: 4000*50=200000 > 100000, capped at 100%
        # max_by_equity = int(100000/50) = 2000
        # max_by_equity_rounded = (2000//100)*100 = 2000
        # So rounded=2000, position_value=100000, pct=100% (>30%)
        # Then max_single_position_pct restricts further:
        # max_by_position_val=100000*0.3=30000
        # max_by_position_qty=int(30000/50)=600
        # max_by_position_rounded=(600//100)*100=600
        # Final rounded=600

        assert result.error is None
        # Should have at least one warning about size/limit
        assert len(result.warnings) >= 1
        # Verify the constraint was applied
        assert result.rounded_quantity is not None
        assert result.rounded_quantity <= 600
