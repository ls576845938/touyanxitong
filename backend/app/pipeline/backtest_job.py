from __future__ import annotations

import json
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, SignalBacktestRun, Stock, StockScore
from app.engines.backtest_engine import run_signal_backtest
from app.pipeline.utils import latest_trade_date


def run_signal_backtest_job(
    session: Session,
    *,
    as_of_date: date | None = None,
    horizon_days: int = 120,
    min_score: float = 0.0,
    market: str | None = None,
    board: str | None = None,
) -> dict[str, int | str]:
    target_date = as_of_date or latest_trade_date(session)
    market_key = (market or "ALL").upper()
    board_key = (board or "all").lower()

    query = select(StockScore, Stock).join(Stock, Stock.code == StockScore.stock_code).where(StockScore.trade_date <= target_date)
    if market_key != "ALL":
        query = query.where(Stock.market == market_key)
    if board_key != "all":
        query = query.where(Stock.board == board_key)
    rows = session.execute(query).all()
    score_rows = [score for score, _stock in rows]
    codes = sorted({score.stock_code for score in score_rows})
    bars_by_stock = _bars_by_stock(session, codes, target_date)
    result = run_signal_backtest(
        score_rows=score_rows,
        bars_by_stock=bars_by_stock,
        as_of_date=target_date,
        horizon_days=horizon_days,
        min_score=min_score,
        market=market_key,
        board=board_key,
    )
    run_key = f"{target_date.isoformat()}:{market_key}:{board_key}:h{horizon_days}:s{min_score:.2f}"
    payload = {
        "as_of_date": result.as_of_date,
        "horizon_days": result.horizon_days,
        "min_score": result.min_score,
        "market": result.market,
        "board": result.board,
        "status": result.status,
        "sample_count": result.sample_count,
        "average_forward_return": result.average_forward_return,
        "median_forward_return": result.median_forward_return,
        "average_max_return": result.average_max_return,
        "hit_rate_2x": result.hit_rate_2x,
        "hit_rate_5x": result.hit_rate_5x,
        "hit_rate_10x": result.hit_rate_10x,
        "bucket_summary": json.dumps(result.bucket_summary, ensure_ascii=False),
        "rating_summary": json.dumps(result.rating_summary, ensure_ascii=False),
        "confidence_summary": json.dumps(result.confidence_summary, ensure_ascii=False),
        "failures": json.dumps(result.failures, ensure_ascii=False),
        "explanation": result.explanation,
    }
    existing = session.scalar(select(SignalBacktestRun).where(SignalBacktestRun.run_key == run_key))
    if existing is None:
        session.add(SignalBacktestRun(run_key=run_key, **payload))
        inserted = 1
    else:
        for key, value in payload.items():
            setattr(existing, key, value)
        inserted = 0
    session.commit()
    logger.info("signal backtest generated: {} sample_count={}", run_key, result.sample_count)
    return {"backtest_runs": inserted, "run_key": run_key, "sample_count": result.sample_count}


def _bars_by_stock(session: Session, stock_codes: list[str], as_of_date: date) -> dict[str, list[DailyBar]]:
    if not stock_codes:
        return {}
    rows = session.scalars(
        select(DailyBar)
        .where(DailyBar.stock_code.in_(stock_codes), DailyBar.trade_date <= as_of_date)
        .order_by(DailyBar.stock_code, DailyBar.source_confidence.desc(), DailyBar.trade_date)
    ).all()
    grouped_by_source: dict[tuple[str, str], list[DailyBar]] = {}
    for row in rows:
        grouped_by_source.setdefault((row.stock_code, row.source), []).append(row)
    selected: dict[str, list[DailyBar]] = {}
    for (code, source), items in grouped_by_source.items():
        current = selected.get(code)
        if current is None or _source_rank(items) > _source_rank(current):
            selected[code] = items
    return selected


def _source_rank(rows: list[DailyBar]) -> tuple[float, int, object]:
    if not rows:
        return (0.0, 0, "")
    return (
        max(float(row.source_confidence or 0.0) for row in rows),
        len(rows),
        max(row.trade_date for row in rows),
    )
