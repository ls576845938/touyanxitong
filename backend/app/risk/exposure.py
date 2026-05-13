from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RiskPosition, RiskRule, Stock


def compute_exposure(portfolio_id: int, db_session: Session) -> dict[str, Any]:
    """Compute single-stock, industry, and theme exposure for a portfolio."""
    positions = db_session.scalars(
        select(RiskPosition).where(RiskPosition.portfolio_id == portfolio_id)
    ).all()

    total_equity = 0.0
    total_market_value = 0.0
    position_list: list[dict[str, Any]] = []

    for pos in positions:
        mv = pos.market_value or 0.0
        total_market_value += mv

    if total_market_value > 0:
        for pos in positions:
            mv = pos.market_value or 0.0
            pct = (mv / total_market_value) * 100.0 if total_market_value else 0.0
            position_list.append({
                "symbol": pos.symbol,
                "name": pos.name,
                "market_value": mv,
                "position_pct": round(pct, 2),
                "industry": pos.industry,
                "theme_tags": _safe_json_loads(pos.theme_tags_json),
            })
    else:
        total_market_value = sum(pos.market_value or 0.0 for pos in positions)
        for pos in positions:
            position_list.append({
                "symbol": pos.symbol,
                "name": pos.name,
                "market_value": pos.market_value or 0.0,
                "position_pct": pos.position_pct or 0.0,
                "industry": pos.industry,
                "theme_tags": _safe_json_loads(pos.theme_tags_json),
            })

    # Industry exposure
    industry_totals: dict[str, float] = defaultdict(float)
    for pos in positions:
        ind = pos.industry or "未分类"
        industry_totals[ind] += pos.market_value or 0.0

    total = total_market_value if total_market_value > 0 else 1.0
    industry_exposure = {
        ind: round((val / total) * 100.0, 2)
        for ind, val in sorted(industry_totals.items(), key=lambda x: x[1], reverse=True)
    }

    # Theme exposure
    theme_totals: dict[str, float] = defaultdict(float)
    for pos in positions:
        themes = _safe_json_loads(pos.theme_tags_json)
        mv = pos.market_value or 0.0
        for theme in themes:
            theme_totals[theme] += mv

    theme_exposure = {
        theme: round((val / total) * 100.0, 2)
        for theme, val in sorted(theme_totals.items(), key=lambda x: x[1], reverse=True)
    }

    # Warnings for concentrated positions
    warnings: list[str] = []
    if total_market_value > 0:
        for pos in position_list:
            if pos["position_pct"] is not None and pos["position_pct"] > 20.0:
                warnings.append(
                    f"{pos['symbol']} 仓位 {pos['position_pct']:.1f}% 超过单股集中度限制20%"
                )
        for ind, pct in industry_exposure.items():
            if pct > 40.0:
                warnings.append(
                    f"行业 {ind} 暴露 {pct:.1f}% 超过行业集中度限制40%"
                )
        for theme, pct in theme_exposure.items():
            if pct > 30.0:
                warnings.append(
                    f"主题 {theme} 暴露 {pct:.1f}% 超过主题集中度限制30%"
                )

    return {
        "total_equity": total_equity,
        "total_market_value": round(total_market_value, 2),
        "positions": position_list,
        "industry_exposure": industry_exposure,
        "theme_exposure": theme_exposure,
        "warnings": warnings,
    }


def check_portfolio_rules(
    portfolio_id: int,
    db_session: Session,
    hypothetical_symbol: str | None = None,
    hypothetical_position_pct: float = 0.0,
) -> dict[str, Any]:
    """Check if current or hypothetical portfolio violates risk rules."""
    rule = db_session.scalar(
        select(RiskRule).where(RiskRule.portfolio_id == portfolio_id)
    )

    max_single = rule.max_single_position_pct if rule else 20.0
    max_industry = rule.max_industry_exposure_pct if rule else 40.0
    max_theme = rule.max_theme_exposure_pct if rule else 30.0

    exposure = compute_exposure(portfolio_id, db_session)
    violations: list[dict[str, Any]] = []

    # Single position checks with optional hypothetical
    if hypothetical_symbol and hypothetical_position_pct > 0:
        # Check if hypothetical would exceed max single position
        if hypothetical_position_pct > max_single:
            violations.append({
                "type": "single_position",
                "symbol": hypothetical_symbol,
                "current_pct": hypothetical_position_pct,
                "limit_pct": max_single,
                "message": f"假设仓位 {hypothetical_symbol} {hypothetical_position_pct:.1f}% 超过单股限制 {max_single:.1f}%",
            })

    for pos in exposure["positions"]:
        pct = pos["position_pct"] or 0.0
        if pct > max_single:
            violations.append({
                "type": "single_position",
                "symbol": pos["symbol"],
                "current_pct": pct,
                "limit_pct": max_single,
                "message": f"{pos['symbol']} 仓位 {pct:.1f}% 超过单股限制 {max_single:.1f}%",
            })

    # Industry exposure checks
    for ind, pct in exposure["industry_exposure"].items():
        if pct > max_industry:
            violations.append({
                "type": "industry_exposure",
                "industry": ind,
                "current_pct": pct,
                "limit_pct": max_industry,
                "message": f"行业 {ind} 暴露 {pct:.1f}% 超过限制 {max_industry:.1f}%",
            })

    # Theme exposure checks
    for theme, pct in exposure["theme_exposure"].items():
        if pct > max_theme:
            violations.append({
                "type": "theme_exposure",
                "theme": theme,
                "current_pct": pct,
                "limit_pct": max_theme,
                "message": f"主题 {theme} 暴露 {pct:.1f}% 超过限制 {max_theme:.1f}%",
            })

    return {
        "portfolio_id": portfolio_id,
        "rule_id": rule.id if rule else None,
        "limits": {
            "max_single_position_pct": max_single,
            "max_industry_exposure_pct": max_industry,
            "max_theme_exposure_pct": max_theme,
        },
        "violations": violations,
        "breach_count": len(violations),
        "exposure": exposure,
    }


def _safe_json_loads(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        if value and value.startswith("["):
            return []
        if value:
            return [value]
        return []
