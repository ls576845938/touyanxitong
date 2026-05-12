from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, Stock, TrendSignal
from app.services.stock_resolver import resolve_stock


def get_stock_basic(session: Session, symbol_or_name: str | None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol_or_name or "")
    if stock is None:
        return {"status": "unavailable", "message": f"未识别股票：{symbol_or_name or ''}"}
    return {
        "status": "ok",
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "board": stock.board,
        "exchange": stock.exchange,
        "industry_level1": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "concepts": _loads_list(stock.concepts),
        "market_cap": stock.market_cap,
        "float_market_cap": stock.float_market_cap,
        "is_st": stock.is_st,
        "is_active": stock.is_active,
        "data_source": "stock",
    }


def get_price_trend(session: Session, symbol: str | None, window: str | None = None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol or "")
    if stock is None:
        return {"status": "unavailable", "message": f"未识别股票：{symbol or ''}"}
    limit = _window_to_limit(window)
    bars = list(
        session.scalars(
            select(DailyBar)
            .where(DailyBar.stock_code == stock.code)
            .order_by(DailyBar.trade_date.desc())
            .limit(limit)
        ).all()
    )
    if not bars:
        return {"status": "unavailable", "message": f"{stock.name} 缺少行情数据"}
    rows = list(reversed(bars))
    latest_bar = rows[-1]
    first_close = float(rows[0].close or 0.0)
    latest_close = float(latest_bar.close or 0.0)
    window_return = (latest_close / first_close - 1) * 100 if first_close else None
    trend = session.scalars(
        select(TrendSignal).where(TrendSignal.stock_code == stock.code).order_by(TrendSignal.trade_date.desc()).limit(1)
    ).first()
    return {
        "status": "ok",
        "code": stock.code,
        "name": stock.name,
        "trade_date": latest_bar.trade_date.isoformat(),
        "close": latest_close,
        "window": window or f"{limit}d",
        "window_return_pct": round(window_return, 2) if window_return is not None else None,
        "ma20": trend.ma20 if trend else None,
        "ma60": trend.ma60 if trend else None,
        "ma120": trend.ma120 if trend else None,
        "ma250": trend.ma250 if trend else None,
        "trend_score": trend.trend_score if trend else None,
        "relative_strength_rank": trend.relative_strength_rank if trend else None,
        "is_ma_bullish": trend.is_ma_bullish if trend else None,
        "is_breakout_120d": trend.is_breakout_120d if trend else None,
        "is_breakout_250d": trend.is_breakout_250d if trend else None,
        "volume_expansion_ratio": trend.volume_expansion_ratio if trend else None,
        "max_drawdown_60d": trend.max_drawdown_60d if trend else None,
        "explanation": trend.explanation if trend else "趋势信号尚未生成。",
        "data_source": "daily_bar/trend_signal",
    }


def get_momentum_rank(session: Session, scope: str | None = None, window: str | None = None, limit: int = 20) -> dict[str, Any]:
    latest_date = session.scalars(select(TrendSignal.trade_date).order_by(TrendSignal.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"status": "unavailable", "message": "趋势信号数据不足", "stocks": []}
    query = (
        select(TrendSignal, Stock)
        .join(Stock, Stock.code == TrendSignal.stock_code)
        .where(TrendSignal.trade_date == latest_date, Stock.is_active.is_(True), Stock.asset_type == "equity")
        .order_by(TrendSignal.trend_score.desc(), TrendSignal.relative_strength_rank.asc())
        .limit(max(1, min(limit, 100)))
    )
    market = _market_scope(scope)
    if market:
        query = query.where(Stock.market == market)
    rows = []
    for trend, stock in session.execute(query).all():
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "industry": stock.industry_level1,
                "trade_date": latest_date.isoformat(),
                "trend_score": trend.trend_score,
                "relative_strength_rank": trend.relative_strength_rank,
                "is_ma_bullish": trend.is_ma_bullish,
                "is_breakout_120d": trend.is_breakout_120d,
                "is_breakout_250d": trend.is_breakout_250d,
                "volume_expansion_ratio": trend.volume_expansion_ratio,
            }
        )
    return {"status": "ok", "window": window or "latest", "scope": scope or "ALL", "stocks": rows, "data_source": "trend_signal"}


def get_market_coverage_status(session: Session) -> dict[str, Any]:
    stock_count = int(session.scalar(select(func.count(Stock.id))) or 0)
    bars_stock_count = int(session.scalar(select(func.count(func.distinct(DailyBar.stock_code)))) or 0)
    latest_trade_date = session.scalars(select(DailyBar.trade_date).order_by(DailyBar.trade_date.desc()).limit(1)).first()
    latest_trend_date = session.scalars(select(TrendSignal.trade_date).order_by(TrendSignal.trade_date.desc()).limit(1)).first()
    return {
        "status": "ok",
        "stock_count": stock_count,
        "stocks_with_bars": bars_stock_count,
        "bar_coverage_ratio": round(bars_stock_count / stock_count, 4) if stock_count else 0.0,
        "latest_trade_date": latest_trade_date.isoformat() if isinstance(latest_trade_date, date) else None,
        "latest_trend_date": latest_trend_date.isoformat() if isinstance(latest_trend_date, date) else None,
        "data_source": "stock/daily_bar/trend_signal",
    }


def _window_to_limit(window: str | None) -> int:
    raw = (window or "120d").lower().strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return 120
    return max(20, min(int(digits), 520))


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
