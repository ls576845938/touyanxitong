from __future__ import annotations

from collections import defaultdict
from datetime import date

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, Stock, TrendSignal
from app.engines.trend_engine import calculate_trend_metrics
from app.pipeline.research_universe import research_universe_payload
from app.pipeline.utils import latest_trade_date


def run_trend_signal_job(session: Session, trade_date: date | None = None) -> dict[str, int]:
    target_date = trade_date or latest_trade_date(session)
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
    universe = research_universe_payload(session, stocks=stocks, target_date=target_date)
    eligible_rows = {str(row["code"]): row for row in universe["rows"] if row["eligible"]}
    bars_by_stock: dict[str, list[DailyBar]] = defaultdict(list)
    for stock in stocks:
        universe_row = eligible_rows.get(stock.code)
        if universe_row is None:
            continue
        source = str(universe_row.get("selected_bar_source") or "")
        if source is None:
            continue
        rows = session.scalars(
            select(DailyBar)
            .where(DailyBar.stock_code == stock.code, DailyBar.trade_date <= target_date, DailyBar.source == source)
            .order_by(DailyBar.trade_date)
        ).all()
        bars_by_stock[stock.code] = list(rows)
    metrics = calculate_trend_metrics(bars_by_stock)
    metric_codes = {item.stock_code for item in metrics}
    if metric_codes:
        session.execute(delete(TrendSignal).where(TrendSignal.trade_date == target_date, TrendSignal.stock_code.not_in(metric_codes)))
    else:
        session.execute(delete(TrendSignal).where(TrendSignal.trade_date == target_date))
    for item in metrics:
        existing = session.scalar(
            select(TrendSignal).where(TrendSignal.stock_code == item.stock_code, TrendSignal.trade_date == item.trade_date)
        )
        payload = item.__dict__.copy()
        payload.pop("stock_code")
        payload.pop("trade_date")
        if existing is None:
            session.add(TrendSignal(stock_code=item.stock_code, trade_date=item.trade_date, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    session.commit()
    logger.info("trend signals calculated: {}", len(metrics))
    return {"trend_signals": len(metrics)}
