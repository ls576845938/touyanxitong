from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Stock, StockScore
from app.engines.watchlist_change_engine import build_watchlist_changes
from app.market_meta import board_label, market_label
from app.pipeline.data_quality_summary import data_quality_payload
from app.pipeline.research_universe import research_universe_payload


def build_report_context(session: Session, target_date: date | None = None, *, include_universe_rows: bool = False) -> dict[str, Any]:
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.market, Stock.board, Stock.code)).all()
    stocks_by_code = {stock.code: stock for stock in stocks}
    data_quality = _data_quality_context(session, stocks, target_date)
    research_universe = _research_universe_context(session, stocks, target_date, include_rows=include_universe_rows)
    watchlist_changes = _watchlist_changes_context(session, stocks_by_code, target_date)
    return {
        "data_quality": data_quality,
        "research_universe": research_universe,
        "watchlist_changes": watchlist_changes,
    }


def _data_quality_context(session: Session, stocks: list[Stock], target_date: date | None) -> dict[str, Any]:
    return data_quality_payload(session, stocks=stocks, target_date=target_date)


def _research_universe_context(session: Session, stocks: list[Stock], target_date: date | None, *, include_rows: bool) -> dict[str, Any]:
    payload = research_universe_payload(session, stocks=stocks, target_date=target_date)
    for segment in payload["segments"]:
        segment["market_label"] = market_label(segment["market"])
        segment["board_label"] = board_label(segment["board"])
    for row in payload["rows"]:
        row["market_label"] = market_label(row["market"])
        row["board_label"] = board_label(row["board"])
    if not include_rows:
        payload["rows"] = []
    return payload


def _watchlist_changes_context(session: Session, stocks_by_code: dict[str, Stock], target_date: date | None) -> dict[str, Any]:
    if target_date is None:
        score_dates = session.scalars(select(StockScore.trade_date).distinct().order_by(StockScore.trade_date.desc()).limit(2)).all()
        latest_date = score_dates[0] if score_dates else None
        previous_date = score_dates[1] if len(score_dates) > 1 else None
    else:
        latest_date = target_date
        previous_date = session.scalars(
            select(StockScore.trade_date)
            .distinct()
            .where(StockScore.trade_date < target_date)
            .order_by(StockScore.trade_date.desc())
            .limit(1)
        ).first()
    latest_scores = session.scalars(select(StockScore).where(StockScore.trade_date == latest_date)).all() if latest_date else []
    previous_scores = session.scalars(select(StockScore).where(StockScore.trade_date == previous_date)).all() if previous_date else []
    return build_watchlist_changes(
        latest_date=latest_date,
        previous_date=previous_date,
        latest_scores=list(latest_scores),
        previous_scores=list(previous_scores),
        stocks_by_code=stocks_by_code,
    )
