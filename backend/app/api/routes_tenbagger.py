from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundamentalMetric, SignalBacktestRun, Stock, StockScore, TenbaggerThesis
from app.db.session import get_session
from app.engines.backtest_engine import backtest_to_payload
from app.engines.data_gate_engine import assess_research_data_gate
from app.engines.tenbagger_thesis_engine import thesis_to_payload
from app.pipeline.backtest_job import run_signal_backtest_job

router = APIRouter(prefix="/api/research", tags=["tenbagger-research"])


class BacktestRunCreate(BaseModel):
    as_of_date: date | None = None
    horizon_days: int = 120
    min_score: float = 0.0
    market: str | None = None
    board: str | None = None


@router.get("/thesis")
def thesis_list(
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    data_gate_status: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    latest_date = session.scalars(select(TenbaggerThesis.trade_date).order_by(TenbaggerThesis.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"latest_date": None, "summary": _thesis_summary([]), "rows": []}
    query = (
        select(TenbaggerThesis, Stock, StockScore)
        .join(Stock, Stock.code == TenbaggerThesis.stock_code)
        .join(StockScore, (StockScore.stock_code == TenbaggerThesis.stock_code) & (StockScore.trade_date == TenbaggerThesis.trade_date))
        .where(TenbaggerThesis.trade_date == latest_date)
        .order_by(TenbaggerThesis.thesis_score.desc(), StockScore.final_score.desc())
    )
    if market and market.upper() != "ALL":
        query = query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    if stage and stage.lower() != "all":
        query = query.where(TenbaggerThesis.stage == stage)
    if data_gate_status and data_gate_status.upper() != "ALL":
        query = query.where(TenbaggerThesis.data_gate_status == data_gate_status.upper())
    all_rows = session.execute(query).all()
    rows = [_thesis_row(thesis, stock, score) for thesis, stock, score in all_rows]
    return {"latest_date": latest_date.isoformat(), "summary": _thesis_summary(rows), "rows": rows[offset : offset + limit]}


@router.get("/thesis/{code}")
def thesis_detail(code: str, session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.execute(
        select(TenbaggerThesis, Stock, StockScore)
        .join(Stock, Stock.code == TenbaggerThesis.stock_code)
        .join(StockScore, (StockScore.stock_code == TenbaggerThesis.stock_code) & (StockScore.trade_date == TenbaggerThesis.trade_date))
        .where(TenbaggerThesis.stock_code == code)
        .order_by(TenbaggerThesis.trade_date.desc())
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="thesis not found; run daily pipeline first")
    thesis, stock, score = row
    history = session.execute(
        select(TenbaggerThesis, StockScore)
        .join(StockScore, (StockScore.stock_code == TenbaggerThesis.stock_code) & (StockScore.trade_date == TenbaggerThesis.trade_date))
        .where(TenbaggerThesis.stock_code == code)
        .order_by(TenbaggerThesis.trade_date.desc())
        .limit(60)
    ).all()
    return {
        "latest": _thesis_row(thesis, stock, score),
        "history": [
            {
                **thesis_to_payload(history_thesis),
                "final_score": history_score.final_score,
                "rating": history_score.rating,
            }
            for history_thesis, history_score in history
        ],
    }


@router.get("/data-gate")
def data_gate(
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=300),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"latest_date": None, "summary": _gate_summary([]), "rows": []}
    query = select(StockScore, Stock).join(Stock, Stock.code == StockScore.stock_code).where(StockScore.trade_date == latest_date)
    if market and market.upper() != "ALL":
        query = query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    pairs = session.execute(query.order_by(StockScore.final_score.desc())).all()
    codes = [score.stock_code for score, _stock in pairs]
    fundamentals = session.scalars(
        select(FundamentalMetric)
        .where(FundamentalMetric.stock_code.in_(codes), FundamentalMetric.report_date <= latest_date)
        .order_by(FundamentalMetric.stock_code, FundamentalMetric.report_date)
    ).all()
    fundamental_by_code: dict[str, FundamentalMetric] = {}
    for item in fundamentals:
        fundamental_by_code[item.stock_code] = item
    rows = []
    for score, stock in pairs:
        gate = assess_research_data_gate(stock=stock, score=score, fundamental=fundamental_by_code.get(stock.code))
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "board": stock.board,
                "industry": stock.industry_level1,
                "final_score": score.final_score,
                "rating": score.rating,
                "status": gate.status,
                "gate_score": gate.score,
                "reasons": gate.reasons,
                "required_actions": gate.required_actions,
            }
        )
    rows = sorted(rows, key=lambda item: (str(item["status"]) != "FAIL", -float(item["final_score"])))
    return {"latest_date": latest_date.isoformat(), "summary": _gate_summary(rows), "rows": rows[:limit]}


@router.get("/backtest/latest")
def latest_backtest(session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalars(select(SignalBacktestRun).order_by(SignalBacktestRun.created_at.desc(), SignalBacktestRun.id.desc()).limit(1)).first()
    if row is None:
        return {"latest": None, "runs": []}
    runs = session.scalars(select(SignalBacktestRun).order_by(SignalBacktestRun.created_at.desc(), SignalBacktestRun.id.desc()).limit(20)).all()
    return {"latest": _backtest_run_payload(row), "runs": [_backtest_run_payload(item) for item in runs]}


@router.post("/backtest/run")
def run_backtest(payload: BacktestRunCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    result = run_signal_backtest_job(
        session,
        as_of_date=payload.as_of_date,
        horizon_days=payload.horizon_days,
        min_score=payload.min_score,
        market=payload.market,
        board=payload.board,
    )
    row = session.scalar(select(SignalBacktestRun).where(SignalBacktestRun.run_key == result["run_key"]))
    return {"result": result, "run": _backtest_run_payload(row) if row else None}


def _thesis_row(thesis: TenbaggerThesis, stock: Stock, score: StockScore) -> dict[str, object]:
    return {
        **thesis_to_payload(thesis),
        "stock": {
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "board": stock.board,
            "industry": stock.industry_level1,
            "industry_level2": stock.industry_level2,
            "market_cap": stock.market_cap,
            "float_market_cap": stock.float_market_cap,
        },
        "score": {
            "final_score": score.final_score,
            "raw_score": score.raw_score,
            "rating": score.rating,
            "industry_score": score.industry_score,
            "company_score": score.company_score,
            "trend_score": score.trend_score,
            "catalyst_score": score.catalyst_score,
            "risk_penalty": score.risk_penalty,
            "confidence_level": score.confidence_level,
            "source_confidence": score.source_confidence,
            "data_confidence": score.data_confidence,
            "fundamental_confidence": score.fundamental_confidence,
            "news_confidence": score.news_confidence,
            "evidence_confidence": score.evidence_confidence,
        },
    }


def _thesis_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    stage_counts: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    for row in rows:
        stage_counts[str(row.get("stage", "unknown"))] = stage_counts.get(str(row.get("stage", "unknown")), 0) + 1
        gate_counts[str(row.get("data_gate_status", "unknown"))] = gate_counts.get(str(row.get("data_gate_status", "unknown")), 0) + 1
    scores = [float(row.get("thesis_score", 0.0) or 0.0) for row in rows]
    return {
        "count": len(rows),
        "average_thesis_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "candidate_count": stage_counts.get("candidate", 0),
        "verification_count": stage_counts.get("verification", 0),
        "blocked_count": stage_counts.get("blocked", 0),
        "stage_counts": stage_counts,
        "gate_counts": gate_counts,
    }


def _gate_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for row in rows:
        status = str(row.get("status", "FAIL"))
        counts[status] = counts.get(status, 0) + 1
    return {
        "count": len(rows),
        "pass_count": counts.get("PASS", 0),
        "warn_count": counts.get("WARN", 0),
        "fail_count": counts.get("FAIL", 0),
        "formal_ready_ratio": round(counts.get("PASS", 0) / len(rows), 4) if rows else 0.0,
    }


def _backtest_run_payload(row: SignalBacktestRun) -> dict[str, object]:
    payload = backtest_to_payload(row)
    payload["run_key"] = row.run_key
    payload["created_at"] = row.created_at.isoformat()
    return payload


def _loads_json_list(value: str) -> list[object]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []
