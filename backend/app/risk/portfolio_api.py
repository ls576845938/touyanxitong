from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RiskEvent, RiskPortfolio, RiskPosition, RiskRule, Stock
from app.db.session import get_session
from app.risk.drawdown import get_drawdown_multiplier, should_block_new_active_plan
from app.risk.exposure import check_portfolio_rules, compute_exposure

router = APIRouter(prefix="/api/risk", tags=["risk-portfolio"])

RISK_BOUNDARY = "风险监控与组合管理，不构成投资建议。"


def _portfolio_payload(portfolio: RiskPortfolio) -> dict[str, Any]:
    return {
        "id": portfolio.id,
        "user_id": portfolio.user_id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "total_equity": portfolio.total_equity,
        "cash": portfolio.cash,
        "current_drawdown_pct": portfolio.current_drawdown_pct,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
        "updated_at": portfolio.updated_at.isoformat() if portfolio.updated_at else None,
    }


def _position_payload(position: RiskPosition) -> dict[str, Any]:
    return {
        "id": position.id,
        "portfolio_id": position.portfolio_id,
        "symbol": position.symbol,
        "name": position.name,
        "market": position.market,
        "quantity": position.quantity,
        "avg_cost": position.avg_cost,
        "last_price": position.last_price,
        "market_value": position.market_value,
        "position_pct": position.position_pct,
        "industry": position.industry,
        "theme_tags": _safe_json_loads(position.theme_tags_json),
        "updated_at": position.updated_at.isoformat() if position.updated_at else None,
    }


def _rule_payload(rule: RiskRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "user_id": rule.user_id,
        "portfolio_id": rule.portfolio_id,
        "max_risk_per_trade_pct": rule.max_risk_per_trade_pct,
        "max_single_position_pct": rule.max_single_position_pct,
        "max_industry_exposure_pct": rule.max_industry_exposure_pct,
        "max_theme_exposure_pct": rule.max_theme_exposure_pct,
        "drawdown_rules": _safe_json_loads(rule.drawdown_rules_json),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _create_risk_event(
    db_session: Session,
    user_id: str | None,
    portfolio_id: int | None,
    event_type: str,
    severity: str,
    message: str,
    related_symbol: str | None = None,
    related_theme: str | None = None,
    payload_json: str | None = None,
) -> RiskEvent:
    event = RiskEvent(
        user_id=user_id,
        portfolio_id=portfolio_id,
        event_type=event_type,
        severity=severity,
        message=message,
        related_symbol=related_symbol,
        related_theme=related_theme,
        payload_json=payload_json,
    )
    db_session.add(event)
    return event


def _lookup_stock(session: Session, symbol: str) -> Stock | None:
    """Look up stock by symbol (code) or name."""
    stock = session.scalar(select(Stock).where(Stock.code == symbol).limit(1))
    if stock is None:
        stock = session.scalar(select(Stock).where(Stock.name == symbol).limit(1))
    return stock


def _safe_json_loads(value: str | None) -> list | dict | str:
    if not value:
        return value if value == "" else []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


# ── Portfolio CRUD ──────────────────────────────────────────────────


@router.post("/portfolios")
def create_portfolio(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    portfolio = RiskPortfolio(
        user_id=str(payload.get("user_id")) if payload.get("user_id") else None,
        name=str(payload.get("name", "默认组合")),
        base_currency=str(payload.get("base_currency", "CNY")),
        total_equity=float(payload.get("total_equity", 0.0)),
        cash=float(payload.get("cash", 0.0)),
        current_drawdown_pct=float(payload["current_drawdown_pct"]) if payload.get("current_drawdown_pct") is not None else None,
    )
    session.add(portfolio)
    session.flush()

    # Create default risk rule for the portfolio
    rule = RiskRule(
        user_id=portfolio.user_id,
        portfolio_id=portfolio.id,
    )
    session.add(rule)

    _create_risk_event(
        session,
        portfolio.user_id,
        portfolio.id,
        event_type="plan_created",
        severity="info",
        message=f"组合 '{portfolio.name}' 已创建",
    )
    session.commit()

    return {
        "boundary": RISK_BOUNDARY,
        "portfolio": _portfolio_payload(portfolio),
    }


@router.get("/portfolios")
def list_portfolios(
    user_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(RiskPortfolio).order_by(RiskPortfolio.created_at.desc())
    if user_id:
        query = query.where(RiskPortfolio.user_id == user_id)
    portfolios = session.scalars(query).all()
    return {
        "boundary": RISK_BOUNDARY,
        "portfolios": [_portfolio_payload(p) for p in portfolios],
    }


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    positions = session.scalars(
        select(RiskPosition).where(RiskPosition.portfolio_id == portfolio_id)
    ).all()
    return {
        "boundary": RISK_BOUNDARY,
        "portfolio": _portfolio_payload(portfolio),
        "positions": [_position_payload(p) for p in positions],
    }


# ── Positions ───────────────────────────────────────────────────────


@router.post("/portfolios/{portfolio_id}/positions")
def add_or_update_position(
    portfolio_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    position = session.scalar(
        select(RiskPosition).where(
            RiskPosition.portfolio_id == portfolio_id,
            RiskPosition.symbol == symbol,
        )
    )

    is_new = position is None
    if is_new:
        position = RiskPosition(portfolio_id=portfolio_id, symbol=symbol)
        session.add(position)

    # Auto-populate from Stock data
    stock = _lookup_stock(session, symbol)

    position.name = str(payload.get("name") or position.name or (stock.name if stock else symbol))
    position.market = str(payload.get("market") or position.market or (stock.market if stock else "A"))
    position.quantity = float(payload.get("quantity", position.quantity or 0.0))
    position.avg_cost = float(payload["avg_cost"]) if payload.get("avg_cost") is not None else position.avg_cost
    position.last_price = float(payload["last_price"]) if payload.get("last_price") is not None else position.last_price
    position.market_value = float(payload["market_value"]) if payload.get("market_value") is not None else position.market_value
    position.position_pct = float(payload["position_pct"]) if payload.get("position_pct") is not None else position.position_pct
    position.updated_at = datetime.now(timezone.utc)

    # Auto-populate industry from Stock.industry_level1
    if stock and stock.industry_level1:
        position.industry = str(payload.get("industry") or stock.industry_level1)

    # Auto-populate theme tags from Stock.concepts
    if stock and stock.concepts:
        stock_themes = _safe_json_loads(stock.concepts)
        if isinstance(stock_themes, list) and stock_themes:
            # Merge existing themes with stock concepts
            existing_themes = _safe_json_loads(position.theme_tags_json)
            if isinstance(existing_themes, list):
                merged = list(set(existing_themes + stock_themes))
            else:
                merged = stock_themes
            position.theme_tags_json = json.dumps(merged, ensure_ascii=False)

    # Override industry/theme if explicitly provided
    if payload.get("industry"):
        position.industry = str(payload["industry"])
    if payload.get("theme_tags") is not None:
        theme_tags = payload["theme_tags"]
        if isinstance(theme_tags, list):
            position.theme_tags_json = json.dumps(theme_tags, ensure_ascii=False)
        elif isinstance(theme_tags, str):
            position.theme_tags_json = theme_tags

    session.flush()

    event_message = f"已{'新增' if is_new else '更新'}仓位 {symbol}"
    if position.name:
        event_message += f" ({position.name})"
    _create_risk_event(
        session,
        portfolio.user_id,
        portfolio_id,
        event_type="plan_created" if is_new else "plan_reviewed",
        severity="info",
        message=event_message,
        related_symbol=symbol,
    )
    session.commit()

    return {
        "boundary": RISK_BOUNDARY,
        "position": _position_payload(position),
    }


@router.delete("/portfolios/{portfolio_id}/positions/{symbol}")
def remove_position(
    portfolio_id: int,
    symbol: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    position = session.scalar(
        select(RiskPosition).where(
            RiskPosition.portfolio_id == portfolio_id,
            RiskPosition.symbol == symbol,
        )
    )
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")

    session.delete(position)
    _create_risk_event(
        session,
        portfolio.user_id,
        portfolio_id,
        event_type="plan_created",
        severity="info",
        message=f"已移除仓位 {symbol}",
        related_symbol=symbol,
    )
    session.commit()

    return {
        "boundary": RISK_BOUNDARY,
        "removed": True,
        "symbol": symbol,
    }


# ── Rule Checking ──────────────────────────────────────────────────


@router.post("/portfolio-check")
def portfolio_rule_check(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio_id = int(payload.get("portfolio_id", 0))
    if portfolio_id <= 0:
        raise HTTPException(status_code=400, detail="portfolio_id is required")

    portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    hypothetical_symbol = str(payload["symbol"]).strip() if payload.get("symbol") else None
    hypothetical_pct = float(payload.get("position_pct", 0.0))

    result = check_portfolio_rules(
        portfolio_id=portfolio_id,
        db_session=session,
        hypothetical_symbol=hypothetical_symbol,
        hypothetical_position_pct=hypothetical_pct,
    )

    return {
        "boundary": RISK_BOUNDARY,
        **result,
    }


# ── Exposure ────────────────────────────────────────────────────────


@router.get("/exposure")
def exposure_report(
    portfolio_id: int = Query(..., description="Portfolio ID"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    exposure = compute_exposure(portfolio_id, session)
    return {
        "boundary": RISK_BOUNDARY,
        "portfolio_id": portfolio_id,
        **exposure,
    }


# ── Risk Rules ─────────────────────────────────────────────────────


@router.get("/rules")
def get_risk_rules(
    portfolio_id: int | None = Query(default=None),
    user_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(RiskRule).order_by(RiskRule.created_at.desc())
    if portfolio_id:
        query = query.where(RiskRule.portfolio_id == portfolio_id)
    elif user_id:
        query = query.where(RiskRule.user_id == user_id)
    rules = session.scalars(query).all()
    return {
        "boundary": RISK_BOUNDARY,
        "rules": [_rule_payload(r) for r in rules],
    }


@router.post("/rules")
def upsert_risk_rules(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio_id = payload.get("portfolio_id")
    user_id = str(payload.get("user_id")) if payload.get("user_id") else None

    rule = None
    if portfolio_id:
        rule = session.scalar(select(RiskRule).where(RiskRule.portfolio_id == int(portfolio_id)))
    if rule is None and user_id:
        rule = session.scalar(select(RiskRule).where(RiskRule.user_id == user_id, RiskRule.portfolio_id.is_(None)))

    is_new = rule is None
    if is_new:
        rule = RiskRule(
            user_id=user_id,
            portfolio_id=int(portfolio_id) if portfolio_id else None,
        )
        session.add(rule)

    if payload.get("max_risk_per_trade_pct") is not None:
        rule.max_risk_per_trade_pct = float(payload["max_risk_per_trade_pct"])
    if payload.get("max_single_position_pct") is not None:
        rule.max_single_position_pct = float(payload["max_single_position_pct"])
    if payload.get("max_industry_exposure_pct") is not None:
        rule.max_industry_exposure_pct = float(payload["max_industry_exposure_pct"])
    if payload.get("max_theme_exposure_pct") is not None:
        rule.max_theme_exposure_pct = float(payload["max_theme_exposure_pct"])
    if payload.get("drawdown_rules") is not None:
        dr = payload["drawdown_rules"]
        if isinstance(dr, list):
            rule.drawdown_rules_json = json.dumps(dr, ensure_ascii=False)
        elif isinstance(dr, str):
            rule.drawdown_rules_json = dr

    session.commit()

    return {
        "boundary": RISK_BOUNDARY,
        "rule": _rule_payload(rule),
    }


@router.get("/events")
def list_risk_events(
    portfolio_id: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(RiskEvent).order_by(RiskEvent.created_at.desc())
    if portfolio_id:
        query = query.where(RiskEvent.portfolio_id == portfolio_id)
    if event_type:
        query = query.where(RiskEvent.event_type == event_type)
    if severity:
        query = query.where(RiskEvent.severity == severity)
    events = session.scalars(query.limit(limit)).all()

    def _event_payload(e: RiskEvent) -> dict[str, Any]:
        return {
            "id": e.id,
            "user_id": e.user_id,
            "portfolio_id": e.portfolio_id,
            "event_type": e.event_type,
            "severity": e.severity,
            "message": e.message,
            "related_symbol": e.related_symbol,
            "related_theme": e.related_theme,
            "payload": _safe_json_loads(e.payload_json) if e.payload_json else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }

    return {
        "boundary": RISK_BOUNDARY,
        "events": [_event_payload(e) for e in events],
    }


# ── Drawdown Status ────────────────────────────────────────────────────


@router.get("/drawdown-status")
def drawdown_status(
    current_drawdown_pct: float = Query(
        ..., description="当前组合回撤百分比，例如 5.0 表示回撤 5%"
    ),
) -> dict[str, Any]:
    """返回当前回撤水平对应的风险预算乘数、状态等级及计划创建限制。"""
    dd = get_drawdown_multiplier(current_drawdown_pct)
    blocked, reason = should_block_new_active_plan(current_drawdown_pct)
    return {
        "boundary": RISK_BOUNDARY,
        "current_drawdown_pct": current_drawdown_pct,
        "multiplier": dd["multiplier"],
        "label": dd["label"],
        "description": dd["description"],
        "warnings": dd["warnings"],
        "block_new_active_plan": blocked,
        "block_reason": reason,
    }
