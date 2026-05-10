from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Stock, StockScore, WatchlistItem
from app.db.session import get_session
from app.engines.watchlist_change_engine import WATCH_RATINGS, build_watchlist_changes

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistCreate(BaseModel):
    stock_code: str
    note: str = ""
    status: str = "观察"


@router.get("")
def list_watchlist(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.execute(select(WatchlistItem, Stock).join(Stock, Stock.code == WatchlistItem.stock_code)).all()
    return [
        {
            "stock_code": item.stock_code,
            "name": stock.name,
            "industry": stock.industry_level1,
            "note": item.note,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item, stock in rows
    ]


@router.get("/changes")
def watchlist_changes(session: Session = Depends(get_session)) -> dict[str, object]:
    score_dates = session.scalars(select(StockScore.trade_date).distinct().order_by(StockScore.trade_date.desc()).limit(2)).all()
    latest_date = score_dates[0] if score_dates else None
    previous_date = score_dates[1] if len(score_dates) > 1 else None
    latest_scores = session.scalars(select(StockScore).where(StockScore.trade_date == latest_date)).all() if latest_date else []
    previous_scores = session.scalars(select(StockScore).where(StockScore.trade_date == previous_date)).all() if previous_date else []
    score_codes = {score.stock_code for score in latest_scores} | {score.stock_code for score in previous_scores}
    stocks = session.scalars(select(Stock).where(Stock.code.in_(score_codes))).all() if score_codes else []
    stocks_by_code = {stock.code: stock for stock in stocks}
    return build_watchlist_changes(
        latest_date=latest_date,
        previous_date=previous_date,
        latest_scores=list(latest_scores),
        previous_scores=list(previous_scores),
        stocks_by_code=stocks_by_code,
    )


@router.get("/timeline")
def watchlist_timeline(
    limit: int = Query(default=20, ge=1, le=120),
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    stocks_query = select(Stock)
    if market and market.upper() != "ALL":
        stocks_query = stocks_query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        stocks_query = stocks_query.where(Stock.board == board.lower())

    stocks = session.scalars(stocks_query).all()
    stocks_by_code = {stock.code: stock for stock in stocks}
    scoped_codes = set(stocks_by_code)
    if not scoped_codes:
        return {
            "market": market.upper() if market else "ALL",
            "board": board.lower() if board else "all",
            "latest": None,
            "timeline": [],
        }

    score_dates = session.scalars(
        select(StockScore.trade_date)
        .where(StockScore.stock_code.in_(scoped_codes))
        .distinct()
        .order_by(StockScore.trade_date.desc())
        .limit(limit + 1)
    ).all()
    if not score_dates:
        return {
            "market": market.upper() if market else "ALL",
            "board": board.lower() if board else "all",
            "latest": None,
            "timeline": [],
        }

    scores_by_date: dict[object, list[StockScore]] = {}
    for trade_date in score_dates:
        scores_by_date[trade_date] = list(
            session.scalars(
                select(StockScore)
                .where(StockScore.trade_date == trade_date, StockScore.stock_code.in_(scoped_codes))
                .order_by(StockScore.final_score.desc())
            ).all()
        )

    timeline: list[dict[str, object]] = []
    for index, trade_date in enumerate(score_dates[:limit]):
        previous_date = score_dates[index + 1] if index + 1 < len(score_dates) else None
        latest_scores = scores_by_date.get(trade_date, [])
        previous_scores = scores_by_date.get(previous_date, []) if previous_date else []
        changes = build_watchlist_changes(
            latest_date=trade_date,
            previous_date=previous_date,
            latest_scores=latest_scores,
            previous_scores=previous_scores,
            stocks_by_code=stocks_by_code,
        )
        timeline.append(
            {
                "trade_date": trade_date.isoformat(),
                "previous_date": previous_date.isoformat() if previous_date else None,
                "summary": changes["summary"],
                "new_entries": changes["new_entries"],
                "removed_entries": changes["removed_entries"],
                "upgraded": changes["upgraded"],
                "downgraded": changes["downgraded"],
                "score_gainers": changes["score_gainers"],
                "score_losers": changes["score_losers"],
                "watchlist_top": _watchlist_top(latest_scores, stocks_by_code),
            }
        )

    return {
        "market": market.upper() if market else "ALL",
        "board": board.lower() if board else "all",
        "latest": timeline[0] if timeline else None,
        "timeline": timeline,
    }


@router.post("")
def add_watchlist(payload: WatchlistCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = session.scalar(select(Stock).where(Stock.code == payload.stock_code))
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    item = session.scalar(select(WatchlistItem).where(WatchlistItem.stock_code == payload.stock_code))
    if item is None:
        item = WatchlistItem(stock_code=payload.stock_code, note=payload.note, status=payload.status)
        session.add(item)
    else:
        item.note = payload.note
        item.status = payload.status
    session.commit()
    return {"stock_code": payload.stock_code, "status": payload.status}


def _watchlist_top(scores: list[StockScore], stocks_by_code: dict[str, Stock], limit: int = 20) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for score in scores:
        if score.rating not in WATCH_RATINGS:
            continue
        stock = stocks_by_code.get(score.stock_code)
        rows.append(
            {
                "code": score.stock_code,
                "name": stock.name if stock else score.stock_code,
                "market": stock.market if stock else "",
                "board": stock.board if stock else "",
                "industry": stock.industry_level1 if stock else "",
                "rating": score.rating,
                "final_score": round(score.final_score, 2),
                "industry_score": round(score.industry_score, 2),
                "company_score": round(score.company_score, 2),
                "trend_score": round(score.trend_score, 2),
                "catalyst_score": round(score.catalyst_score, 2),
                "risk_penalty": round(score.risk_penalty, 2),
            }
        )
    return rows[:limit]
