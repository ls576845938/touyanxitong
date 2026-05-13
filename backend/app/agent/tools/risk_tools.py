from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PositionPlan, RiskRule
from app.risk.guardrails import RISK_DISCLAIMER, sanitize_risk_output


def calculate_position_size(
    account_equity: float,
    symbol: str,
    entry_price: float,
    invalidation_price: float,
    risk_per_trade_pct: float = 1.0,
    market: str | None = None,
) -> dict[str, Any]:
    """Calculate risk-budget position size upper limit. NOT a trade recommendation."""
    try:
        from app.risk.calculators import calculate_position_size as _calc
        from app.risk.schemas import PositionSizeRequest

        req = PositionSizeRequest(
            account_equity=account_equity,
            symbol=symbol,
            entry_price=entry_price,
            invalidation_price=invalidation_price,
            risk_per_trade_pct=risk_per_trade_pct,
            market=market,
        )
        resp = _calc(req)
        return {
            "symbol": resp.symbol or symbol,
            "entry_price": resp.entry_price or entry_price,
            "invalidation_price": resp.invalidation_price or invalidation_price,
            "max_loss_amount": resp.max_loss_amount,
            "rounded_quantity": resp.rounded_quantity,
            "estimated_position_pct": resp.estimated_position_pct,
            "warnings": resp.warnings,
            "calculation_explain": resp.calculation_explain,
            "disclaimer": resp.disclaimer,
            "error": resp.error,
        }
    except ImportError:
        return _stub_position_result(symbol, entry_price, invalidation_price)


def check_portfolio_exposure(session: Session, portfolio_id: int | None = None) -> dict[str, Any]:
    """Check industry and theme exposure for a portfolio."""
    if portfolio_id is None:
        return {
            "status": "unavailable",
            "message": "缺少 portfolio_id，请先创建或选择投资组合",
        }
    try:
        from app.risk.exposure import compute_exposure

        exposure = compute_exposure(portfolio_id, session)
        return {
            "status": "ok",
            "portfolio_id": portfolio_id,
            "total_market_value": exposure.get("total_market_value"),
            "positions": exposure.get("positions", []),
            "industry_exposure": exposure.get("industry_exposure", {}),
            "theme_exposure": exposure.get("theme_exposure", {}),
            "warnings": exposure.get("warnings", []),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"无法获取组合暴露数据: {exc}",
        }


def get_risk_rules(session: Session, user_id: str | None = None) -> dict[str, Any]:
    """Get active risk rules."""
    default_rules = {
        "status": "ok",
        "rules": [
            {
                "id": None,
                "user_id": None,
                "portfolio_id": None,
                "max_risk_per_trade_pct": 1.0,
                "max_single_position_pct": 20.0,
                "max_industry_exposure_pct": 40.0,
                "max_theme_exposure_pct": 30.0,
                "drawdown_rules": [
                    {"tier": "警戒线", "threshold": 5, "action": "减仓"},
                    {"tier": "止损线", "threshold": 10, "action": "止损"},
                    {"tier": "硬性止损线", "threshold": 15, "action": "强制平仓"},
                ],
            }
        ],
        "source": "default",
    }

    try:
        query = select(RiskRule).order_by(RiskRule.created_at.desc())
        if user_id:
            query = query.where(RiskRule.user_id == user_id)
        rules = session.scalars(query).all()
        if not rules:
            return default_rules

        return {
            "status": "ok",
            "rules": [_rule_to_dict(r) for r in rules],
            "source": "database",
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"无法获取风险规则: {exc}",
        }


def get_position_plans(session: Session, status: str = "active") -> dict[str, Any]:
    """List position plans."""
    try:
        query = select(PositionPlan).order_by(PositionPlan.created_at.desc())
        if status:
            query = query.where(PositionPlan.status == status)
        plans = session.scalars(query).all()

        return {
            "status": "ok",
            "plans": [_plan_to_dict(p) for p in plans],
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"无法获取仓位计划: {exc}",
            "plans": [],
        }


def explain_risk_budget(
    account_equity: float,
    risk_per_trade_pct: float = 1.0,
    max_loss_example: float | None = None,
) -> dict[str, Any]:
    """Explain risk budget concept in plain language. NO trading advice."""
    risk_amount = account_equity * risk_per_trade_pct / 100.0

    explanation = (
        f"风险预算的概念：\n\n"
        f"风险预算是指您为单笔交易愿意承担的最大亏损金额，"
        f"它由账户权益和单笔风险比例共同决定。\n\n"
        f"计算方法：\n"
        f"• 账户权益：{account_equity:.2f}\n"
        f"• 单笔风险比例：{risk_per_trade_pct}%\n"
        f"• 计算过程：{account_equity:.2f} × {risk_per_trade_pct}% = {risk_amount:.2f}\n"
        f"• 最大亏损预算：{risk_amount:.2f}\n\n"
        f"这意味着在这笔交易中，您计划承担的最大亏损不超过 {risk_amount:.2f}，"
        f"占账户权益的 {risk_per_trade_pct}%。\n\n"
        f"实际使用中，将根据入场价和无效点（止损价）之间的差价，"
        f"以及最小交易单位（如A股100股一手），计算实际可开仓数量。"
        f"最终仓位大小会以不超过风险预算为原则，并向下取整到最小交易单位。\n\n"
        f"注意：风险预算是控制单笔亏损的工具，不代表预期收益。"
        f"不构成任何交易建议。市场有风险，决策需独立判断。"
    )

    return {
        "status": "ok",
        "explanation": sanitize_risk_output(explanation),
        "disclaimer": RISK_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stub_position_result(
    symbol: str, entry_price: float, invalidation_price: float
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "invalidation_price": invalidation_price,
        "max_loss_amount": None,
        "rounded_quantity": None,
        "estimated_position_pct": None,
        "warnings": ["风险模块尚未加载，无法计算仓位"],
        "calculation_explain": "",
        "disclaimer": RISK_DISCLAIMER,
        "error": "风险模块不可用",
    }


def _rule_to_dict(rule: RiskRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "user_id": rule.user_id,
        "portfolio_id": rule.portfolio_id,
        "max_risk_per_trade_pct": rule.max_risk_per_trade_pct,
        "max_single_position_pct": rule.max_single_position_pct,
        "max_industry_exposure_pct": rule.max_industry_exposure_pct,
        "max_theme_exposure_pct": rule.max_theme_exposure_pct,
        "drawdown_rules": _safe_json_loads(rule.drawdown_rules_json),
    }


def _plan_to_dict(plan: PositionPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "portfolio_id": plan.portfolio_id,
        "thesis_id": plan.thesis_id,
        "symbol": plan.symbol,
        "subject_name": plan.subject_name,
        "subject_type": plan.subject_type,
        "entry_price": plan.entry_price,
        "invalidation_price": plan.invalidation_price,
        "risk_per_share": plan.risk_per_share,
        "risk_per_trade_pct": plan.risk_per_trade_pct,
        "max_loss_amount": plan.max_loss_amount,
        "calculated_quantity": plan.calculated_quantity,
        "calculated_position_value": plan.calculated_position_value,
        "calculated_position_pct": plan.calculated_position_pct,
        "status": plan.status,
        "warnings": _safe_json_loads(plan.warnings_json),
        "constraints": _safe_json_loads(plan.constraints_json),
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _safe_json_loads(raw: str | None) -> list[Any]:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
