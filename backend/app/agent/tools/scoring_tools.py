from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Stock, StockScore, TrendSignal
from app.engines.risk_engine import assess_stock_risk
from app.services.stock_resolver import resolve_stock


def get_stock_score(session: Session, symbol: str | None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol or "")
    if stock is None:
        return {"status": "unavailable", "message": f"未识别股票：{symbol or ''}"}
    score = _latest_score(session, stock.code)
    if score is None:
        return {"status": "unavailable", "message": f"{stock.name} 缺少评分数据"}
    return _score_payload(score, stock)


def get_score_breakdown(session: Session, symbol: str | None) -> dict[str, Any]:
    payload = get_stock_score(session, symbol)
    if payload.get("status") != "ok":
        return payload
    payload["breakdown"] = {
        "industry_score": payload["industry_score"],
        "company_score": payload["company_score"],
        "trend_score": payload["trend_score"],
        "catalyst_score": payload["catalyst_score"],
        "risk_penalty": payload["risk_penalty"],
    }
    payload["scoring_basis"] = "final_score = industry + company + trend + catalyst - risk_penalty"
    return payload


def get_top_scored_stocks(session: Session, scope: str | None = None, limit: int = 20) -> dict[str, Any]:
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"status": "unavailable", "message": "评分数据不足", "stocks": []}
    query = (
        select(StockScore, Stock)
        .join(Stock, Stock.code == StockScore.stock_code)
        .where(StockScore.trade_date == latest_date, Stock.is_active.is_(True), Stock.asset_type == "equity")
        .order_by(StockScore.final_score.desc())
        .limit(max(1, min(limit, 100)))
    )
    market = _market_scope(scope)
    if market:
        query = query.where(Stock.market == market)
    rows = [_score_payload(score, stock) for score, stock in session.execute(query).all()]
    return {"status": "ok", "scope": scope or "ALL", "trade_date": latest_date.isoformat(), "stocks": rows, "data_source": "stock_score"}


def get_risk_flags(session: Session, symbol: str | None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol or "")
    if stock is None:
        return {"status": "unavailable", "message": f"未识别股票：{symbol or ''}", "flags": []}
    trend = session.scalars(
        select(TrendSignal).where(TrendSignal.stock_code == stock.code).order_by(TrendSignal.trade_date.desc()).limit(1)
    ).first()
    risk = assess_stock_risk(stock, trend)
    score = _latest_score(session, stock.code)
    flags = list(risk.flags)
    if score and float(score.risk_penalty or 0.0) >= 5:
        flags.append("评分系统风险扣分较高")
    if not flags:
        flags.append("未触发核心风险标签，仍需人工复核公告、财务和估值风险")
    return {
        "status": "ok",
        "code": stock.code,
        "name": stock.name,
        "penalty": risk.penalty,
        "flags": _dedupe(flags),
        "explanation": risk.explanation,
        "data_source": "stock/trend_signal/risk_engine",
    }


def _latest_score(session: Session, code: str) -> StockScore | None:
    return session.scalars(
        select(StockScore).where(StockScore.stock_code == code).order_by(StockScore.trade_date.desc()).limit(1)
    ).first()


def _score_payload(score: StockScore, stock: Stock) -> dict[str, Any]:
    return {
        "status": "ok",
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "industry": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "trade_date": score.trade_date.isoformat(),
        "final_score": score.final_score,
        "raw_score": score.raw_score,
        "rating": score.rating,
        "industry_score": score.industry_score,
        "company_score": score.company_score,
        "trend_score": score.trend_score,
        "catalyst_score": score.catalyst_score,
        "risk_penalty": score.risk_penalty,
        "confidence_level": score.confidence_level,
        "confidence_reasons": _loads_list(score.confidence_reasons),
        "explanation": score.explanation,
        "data_source": "stock_score",
    }


def _market_scope(scope: str | None) -> str | None:
    raw = (scope or "").upper()
    return raw if raw in {"A", "US", "HK"} else None


def _loads_list(raw: str | None) -> list[Any]:
    import json

    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _dedupe(items: list[str]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows
