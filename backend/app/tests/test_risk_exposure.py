"""Tests for portfolio exposure computation."""
from __future__ import annotations

import pytest

from app.db.models import RiskPortfolio, RiskPosition, RiskRule
from app.risk.exposure import check_portfolio_rules, compute_exposure


class TestExposure:
    """Test portfolio exposure and risk-rule checking."""

    def test_create_portfolio(self, db_session) -> None:
        """Can create a RiskPortfolio with a default RiskRule."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="测试组合",
            base_currency="CNY",
            total_equity=1_000_000.0,
            cash=500_000.0,
        )
        db_session.add(portfolio)
        db_session.flush()

        # Default risk rule should be creatable for the portfolio
        rule = RiskRule(
            user_id="test_user",
            portfolio_id=portfolio.id,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(portfolio)

        assert portfolio.id is not None
        assert portfolio.name == "测试组合"
        assert portfolio.total_equity == 1_000_000.0
        assert portfolio.cash == 500_000.0
        assert portfolio.base_currency == "CNY"

    def test_add_position(self, db_session) -> None:
        """Can add a RiskPosition to a portfolio."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="测试组合",
            total_equity=1_000_000.0,
        )
        db_session.add(portfolio)
        db_session.flush()

        position = RiskPosition(
            portfolio_id=portfolio.id,
            symbol="300308",
            name="中际旭创",
            market="A",
            quantity=1000,
            avg_cost=50.0,
            last_price=52.0,
            market_value=52_000.0,
            position_pct=5.2,
            industry="通信",
        )
        db_session.add(position)
        db_session.commit()
        db_session.refresh(position)

        assert position.id is not None
        assert position.symbol == "300308"
        assert position.name == "中际旭创"
        assert position.portfolio_id == portfolio.id
        assert position.market_value == 52_000.0

    def test_industry_exposure_computation(self, db_session) -> None:
        """Industry exposure percentages should sum to 100%."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="行业暴露测试",
        )
        db_session.add(portfolio)
        db_session.flush()

        positions = [
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="A",
                name="科技A",
                market_value=300_000.0,
                industry="科技",
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="B",
                name="科技B",
                market_value=200_000.0,
                industry="科技",
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="C",
                name="消费C",
                market_value=500_000.0,
                industry="消费",
            ),
        ]
        for p in positions:
            db_session.add(p)
        db_session.commit()

        exposure = compute_exposure(portfolio.id, db_session)

        assert exposure["industry_exposure"]["科技"] == 50.0  # 500k/1M
        assert exposure["industry_exposure"]["消费"] == 50.0  # 500k/1M
        assert len(exposure["positions"]) == 3

    def test_theme_exposure_computation(self, db_session) -> None:
        """Theme exposure should aggregate across positions with shared tags."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="主题暴露测试",
        )
        db_session.add(portfolio)
        db_session.flush()

        positions = [
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="A",
                name="AI股",
                market_value=300_000.0,
                industry="科技",
                theme_tags_json='["AI", "机器人"]',
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="B",
                name="机器人股",
                market_value=200_000.0,
                industry="科技",
                theme_tags_json='["机器人"]',
            ),
        ]
        for p in positions:
            db_session.add(p)
        db_session.commit()

        exposure = compute_exposure(portfolio.id, db_session)

        # AI: 300k/500k = 60%
        assert exposure["theme_exposure"]["AI"] == 60.0
        # 机器人: (300k+200k)/500k = 100%
        assert exposure["theme_exposure"]["机器人"] == 100.0

    def test_exposure_warning_on_over_limit(self, db_session) -> None:
        """Position >20%, industry >40%, theme >30% should all trigger warnings."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="超限测试",
        )
        db_session.add(portfolio)
        db_session.flush()

        # One dominant position, one small position, same industry & theme
        positions = [
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="HEAVY",
                name="重仓股",
                market_value=800_000.0,
                industry="单一行业",
                theme_tags_json='["单一主题"]',
            ),
            RiskPosition(
                portfolio_id=portfolio.id,
                symbol="LIGHT",
                name="轻仓股",
                market_value=200_000.0,
                industry="单一行业",
                theme_tags_json='["单一主题"]',
            ),
        ]
        for p in positions:
            db_session.add(p)
        db_session.commit()

        exposure = compute_exposure(portfolio.id, db_session)

        # HEAVY is 80% (>20%) -> warning
        # 单一行业 is 100% (>40%) -> warning
        # 单一主题 is 100% (>30%) -> warning
        # LIGHT is 20% (not over 20%) -> no warning for LIGHT alone
        assert len(exposure["warnings"]) >= 2

        # Verify specific warning messages
        warning_texts = " ".join(exposure["warnings"])
        assert "HEAVY" in warning_texts
        assert "单一行业" in warning_texts
        assert "单一主题" in warning_texts

    def test_no_positions_empty_exposure(self, db_session) -> None:
        """Portfolio with no positions should return empty exposure."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="空组合",
        )
        db_session.add(portfolio)
        db_session.commit()

        exposure = compute_exposure(portfolio.id, db_session)

        assert exposure["positions"] == []
        assert exposure["industry_exposure"] == {}
        assert exposure["theme_exposure"] == {}
        assert exposure["warnings"] == []

    def test_check_portfolio_rules_with_defaults(self, db_session) -> None:
        """Portfolio rule checker should apply default limits."""
        portfolio = RiskPortfolio(
            user_id="test_user",
            name="规则检查测试",
        )
        db_session.add(portfolio)
        db_session.flush()

        position = RiskPosition(
            portfolio_id=portfolio.id,
            symbol="BIG",
            name="大仓位",
            market_value=900_000.0,
            industry="科技",
        )
        db_session.add(position)
        db_session.commit()

        # No RiskRule explicitly created -> defaults applied
        result = check_portfolio_rules(portfolio.id, db_session)

        assert result["portfolio_id"] == portfolio.id
        assert result["limits"]["max_single_position_pct"] == 20.0
        assert result["limits"]["max_industry_exposure_pct"] == 40.0
        assert result["limits"]["max_theme_exposure_pct"] == 30.0
        # BIG is 100% -> should violate single position limit
        assert result["breach_count"] >= 1
