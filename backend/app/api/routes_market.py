from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.db.models import DailyBar, DailyReport, DataIngestionBatch, DataIngestionTask, DataSourceRun, IndustryHeat, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.engines.universe_engine import DEFAULT_RULES, TRUSTED_DATA_SOURCES
from app.market_meta import A_BOARD_ORDER, MARKET_ORDER, board_label, market_label
from app.pipeline.backfill_manifest import DEFAULT_BACKFILL_MANIFEST_PATH, build_backfill_manifest, load_backfill_manifest
from app.pipeline.data_quality_summary import data_quality_payload
from app.pipeline.ingestion_task_service import (
    create_ingestion_task,
    enqueue_ingestion_backfill,
    list_ingestion_tasks,
    priority_candidates,
    run_ingestion_queue,
    run_ingestion_task,
    run_next_ingestion_task,
    task_payload,
)
from app.pipeline.research_universe import research_universe_payload
from app.services.stock_resolver import alias_code_for_identifier, resolve_stock

router = APIRouter(prefix="/api/market", tags=["market"])

_CACHE_TTL_SECONDS = 120.0
_payload_cache: dict[str, tuple[float, Any]] = {}
QUALITY_BACKFILL_FOCUS: tuple[tuple[str, str], ...] = (("US", "all"), ("HK", "all"), ("A", "bse"))


def _cached_payload(key: str, builder: Callable[[], Any], *, ttl: float = _CACHE_TTL_SECONDS) -> Any:
    now = time.monotonic()
    cached = _payload_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    value = builder()
    _payload_cache[key] = (now + ttl, value)
    return value


class IngestionTaskCreate(BaseModel):
    task_type: str = "batch"
    market: str = "A"
    board: str = "all"
    stock_code: str | None = None
    source: str | None = None
    batch_limit: int = 20
    periods: int = 320
    priority: float | None = None


class IngestionBackfillCreate(BaseModel):
    markets: list[str] = Field(default_factory=lambda: ["A", "US", "HK"])
    board: str = "all"
    source: str | None = None
    batches_per_market: int = 3
    batch_limit: int = 20
    periods: int = 320


@router.get("/summary")
def market_summary(session: Session = Depends(get_session)) -> dict[str, object]:
    stock_count = session.scalar(select(func.count()).select_from(Stock)) or 0
    latest_date = session.scalars(select(DailyBar.trade_date).order_by(DailyBar.trade_date.desc()).limit(1)).first()
    latest_score_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    watch_count = 0
    if latest_score_date is not None:
        watch_count = session.scalar(
            select(func.count())
            .select_from(StockScore)
            .join(TrendSignal, (TrendSignal.stock_code == StockScore.stock_code) & (TrendSignal.trade_date == StockScore.trade_date))
            .where(StockScore.trade_date == latest_score_date, StockScore.rating.in_(["强观察", "观察"]))
        ) or 0
    heat_count = session.scalar(select(func.count()).select_from(IndustryHeat)) or 0
    report = session.scalars(select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)).first()
    by_market = _market_segments(session)
    return {
        "stock_count": stock_count,
        "latest_trade_date": latest_date.isoformat() if latest_date else None,
        "watch_count": watch_count,
        "industry_heat_records": heat_count,
        "latest_report_title": report.title if report else None,
        "markets": by_market,
        "boundary": "研究辅助，不输出买入、卖出、目标价或收益承诺。",
    }


@router.get("/segments")
def market_segments(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return _market_segments(session)


@router.get("/data-status")
def data_status(
    include_source_coverage: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return _cached_payload(
        f"data-status:{int(include_source_coverage)}",
        lambda: _data_status_payload(session, include_source_coverage=include_source_coverage),
    )


def _data_status_payload(session: Session, *, include_source_coverage: bool = False) -> dict[str, object]:
    bar_latest_by_stock = (
        select(
            DailyBar.stock_code.label("stock_code"),
            func.max(DailyBar.trade_date).label("latest_trade_date"),
        )
        .group_by(DailyBar.stock_code)
        .subquery()
    )
    coverage_rows = session.execute(
        select(
            Stock.market,
            Stock.board,
            func.count(Stock.id),
            func.count(bar_latest_by_stock.c.stock_code),
            func.max(bar_latest_by_stock.c.latest_trade_date),
        )
        .outerjoin(bar_latest_by_stock, bar_latest_by_stock.c.stock_code == Stock.code)
        .where(Stock.is_active.is_(True))
        .group_by(Stock.market, Stock.board)
    ).all()
    coverage = []
    for market, board, stock_count, stocks_with_bars, latest_trade_date in coverage_rows:
        stock_total = int(stock_count or 0)
        with_bars = int(stocks_with_bars or 0)
        coverage.append(
            {
                "market": market,
                "market_label": market_label(market),
                "board": board,
                "board_label": board_label(board),
                "stock_count": stock_total,
                "stocks_with_bars": with_bars,
                "coverage_ratio": round(with_bars / stock_total, 4) if stock_total else 0,
                "latest_trade_date": latest_trade_date.isoformat() if latest_trade_date else None,
            }
        )
    source_rows = []
    if include_source_coverage:
        source_rows = session.execute(
            select(
                DailyBar.source_kind,
                DailyBar.source,
                func.count(DailyBar.id),
                func.count(func.distinct(DailyBar.stock_code)),
                func.min(DailyBar.trade_date),
                func.max(DailyBar.trade_date),
            )
            .group_by(DailyBar.source_kind, DailyBar.source)
            .order_by(DailyBar.source_kind, DailyBar.source)
        ).all()
    runs = session.scalars(select(DataSourceRun).order_by(DataSourceRun.finished_at.desc(), DataSourceRun.id.desc()).limit(20)).all()
    return {
        "coverage": sorted(coverage, key=lambda item: (_market_sort_key(str(item["market"])), _board_sort_key(str(item["board"])))),
        "source_coverage": [
            {
                "source_kind": source_kind,
                "source": source,
                "bars_count": int(bars_count or 0),
                "stocks_with_bars": int(stocks_with_bars or 0),
                "first_trade_date": first_trade_date.isoformat() if first_trade_date else None,
                "latest_trade_date": latest_trade_date.isoformat() if latest_trade_date else None,
            }
            for source_kind, source, bars_count, stocks_with_bars, first_trade_date, latest_trade_date in source_rows
        ],
        "runs": [
            {
                "job_name": row.job_name,
                "requested_source": row.requested_source,
                "effective_source": row.effective_source,
                "source_kind": row.source_kind,
                "source_confidence": row.source_confidence,
                "markets": json.loads(row.markets),
                "status": row.status,
                "rows_inserted": row.rows_inserted,
                "rows_updated": row.rows_updated,
                "rows_total": row.rows_total,
                "error": row.error,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in runs
        ],
    }


@router.get("/backfill-manifest")
def backfill_manifest(session: Session = Depends(get_session)) -> dict[str, object]:
    payload = load_backfill_manifest(DEFAULT_BACKFILL_MANIFEST_PATH)
    resume = payload.get("resume") if isinstance(payload.get("resume"), dict) else {}
    attempts = resume.get("attempts") if isinstance(resume, dict) else {}
    markets = tuple(payload.get("markets") or settings.enabled_markets) if payload else tuple(settings.enabled_markets)
    source = str(payload.get("source") or settings.market_data_source) if payload else settings.market_data_source
    periods = int(payload.get("periods") or settings.market_data_periods) if payload else settings.market_data_periods
    complete_bars = int(payload.get("complete_bars") or int(periods * 0.95)) if payload else int(settings.market_data_periods * 0.95)
    return build_backfill_manifest(
        session,
        status=str(payload.get("status") or "not_started") if payload else "not_started",
        markets=markets,
        source=source,
        periods=periods,
        complete_bars=complete_bars,
        totals=payload.get("totals") if payload else None,
        attempts=attempts if isinstance(attempts, dict) else None,
        started_at=payload.get("started_at") if payload else None,
        finished_at=payload.get("finished_at") if payload else None,
        last_batch=payload.get("last_batch") if payload else None,
    ) | {"manifest_path": str(DEFAULT_BACKFILL_MANIFEST_PATH)}


@router.get("/instruments")
def instruments(
    market: str | None = None,
    board: str | None = None,
    asset_type: str | None = None,
    q: str | None = None,
    active_only: bool = True,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    bars_summary = (
        select(
            DailyBar.stock_code.label("stock_code"),
            func.count(DailyBar.id).label("bars_count"),
            func.max(DailyBar.trade_date).label("latest_trade_date"),
        )
        .group_by(DailyBar.stock_code)
        .subquery()
    )
    query = select(Stock, bars_summary.c.bars_count, bars_summary.c.latest_trade_date).outerjoin(
        bars_summary, bars_summary.c.stock_code == Stock.code
    )
    count_query = select(func.count()).select_from(Stock)
    filters = []
    if active_only:
        filters.append(Stock.is_active.is_(True))
    if market and market.upper() != "ALL":
        filters.append(Stock.market == market.upper())
    if board and board.lower() != "all":
        filters.append(Stock.board == board.lower())
    if asset_type and asset_type.lower() != "all":
        filters.append(Stock.asset_type == asset_type.lower())
    if q:
        pattern = f"%{q.strip()}%"
        alias_code = alias_code_for_identifier(q)
        if alias_code:
            filters.append((Stock.code.like(pattern)) | (Stock.name.like(pattern)) | (Stock.code == alias_code))
        else:
            filters.append((Stock.code.like(pattern)) | (Stock.name.like(pattern)))
    for item in filters:
        query = query.where(item)
        count_query = count_query.where(item)
    total = int(session.scalar(count_query) or 0)
    rows = session.execute(query.order_by(Stock.market, Stock.board, Stock.code).offset(offset).limit(limit)).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [_instrument_payload(stock, bars_count=bars_count, latest_trade_date=latest_trade_date) for stock, bars_count, latest_trade_date in rows],
    }


@router.get("/instruments/{code}/navigation")
def instrument_navigation(code: str, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = resolve_stock(session, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    previous_stock = session.scalars(
        select(Stock)
        .where(
            Stock.is_active.is_(True),
            Stock.market == stock.market,
            Stock.board == stock.board,
            Stock.code < stock.code,
        )
        .order_by(Stock.code.desc())
        .limit(1)
    ).first()
    next_stock = session.scalars(
        select(Stock)
        .where(
            Stock.is_active.is_(True),
            Stock.market == stock.market,
            Stock.board == stock.board,
            Stock.code > stock.code,
        )
        .order_by(Stock.code)
        .limit(1)
    ).first()
    return {
        "current": _instrument_payload_with_bars(session, stock),
        "previous": _instrument_payload_with_bars(session, previous_stock) if previous_stock else None,
        "next": _instrument_payload_with_bars(session, next_stock) if next_stock else None,
        "scope": {
            "market": stock.market,
            "market_label": market_label(stock.market),
            "board": stock.board,
            "board_label": board_label(stock.board),
        },
    }


@router.get("/ingestion-batches")
def ingestion_batches(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(DataIngestionBatch).order_by(DataIngestionBatch.started_at.desc()).limit(30)).all()
    return [
        {
            "batch_key": row.batch_key,
            "job_name": row.job_name,
            "market": row.market,
            "board": row.board,
            "source": row.source,
            "status": row.status,
            "offset": row.offset,
            "requested": row.requested,
            "processed": row.processed,
            "inserted": row.inserted,
            "updated": row.updated,
            "failed": row.failed,
            "error": row.error,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
        for row in rows
    ]


@router.get("/ingestion-tasks")
def ingestion_tasks(limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return [task_payload(task) for task in list_ingestion_tasks(session, limit=limit)]


@router.post("/ingestion-tasks")
def create_task(payload: IngestionTaskCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    try:
        task = create_ingestion_task(
            session,
            task_type=payload.task_type,
            market=payload.market,
            board=payload.board,
            stock_code=payload.stock_code,
            source=payload.source,
            batch_limit=payload.batch_limit,
            periods=payload.periods,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_payload(task)


@router.post("/ingestion-tasks/backfill")
def create_backfill_tasks(payload: IngestionBackfillCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    return enqueue_ingestion_backfill(
        session,
        markets=tuple(payload.markets),
        board=payload.board,
        source=payload.source,
        batches_per_market=payload.batches_per_market,
        batch_limit=payload.batch_limit,
        periods=payload.periods,
    )


@router.post("/ingestion-tasks/{task_id}/run")
def run_task(task_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    task = session.get(DataIngestionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="ingestion task not found")
    return task_payload(run_ingestion_task(session, task))


@router.post("/ingestion-tasks/run-next")
def run_next_task(session: Session = Depends(get_session)) -> dict[str, object]:
    task = run_next_ingestion_task(session)
    if task is None:
        raise HTTPException(status_code=404, detail="no pending ingestion task")
    return task_payload(task)


@router.post("/ingestion-tasks/run-queue")
def run_task_queue(max_tasks: int = Query(default=3, ge=1, le=20), session: Session = Depends(get_session)) -> dict[str, object]:
    return run_ingestion_queue(session, max_tasks=max_tasks)


@router.get("/ingestion-priority")
def ingestion_priority(
    market: str = Query(default="A"),
    board: str = Query(default="all"),
    limit: int = Query(default=20, ge=1, le=200),
    periods: int = Query(default=320, ge=60, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return {
        "market": market.upper(),
        "board": board.lower(),
        "limit": limit,
        "periods": periods,
        "candidates": priority_candidates(session, market=market, board=board, limit=limit, periods=periods),
    }


@router.get("/data-quality/backfill-plan")
def data_quality_backfill_plan(
    limit_per_segment: int = Query(default=20, ge=1, le=80),
    periods: int = Query(default=320, ge=60, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return _quality_backfill_plan(session, limit_per_segment=limit_per_segment, periods=periods)


@router.get("/data-quality")
def data_quality(session: Session = Depends(get_session)) -> dict[str, object]:
    return _cached_payload("data-quality", lambda: _data_quality_payload(session), ttl=120.0)


def _data_quality_payload(session: Session) -> dict[str, object]:
    stocks = session.scalars(
        select(Stock)
        .where(
            Stock.is_active.is_(True),
            Stock.listing_status == "listed",
            Stock.asset_type == "equity",
            Stock.is_etf.is_(False),
        )
        .order_by(Stock.market, Stock.board, Stock.code)
    ).all()
    result = data_quality_payload(session, stocks=list(stocks))
    result["summary"]["explainable_unusable_count"] = len(_recent_unusable_symbols(session))
    return result


@router.get("/ingestion-plan")
def ingestion_plan(session: Session = Depends(get_session)) -> dict[str, object]:
    rows = session.execute(
        select(
            Stock.market,
            func.count(func.distinct(Stock.id)),
            func.count(func.distinct(DailyBar.stock_code)),
            func.max(DailyBar.trade_date),
        )
        .outerjoin(DailyBar, DailyBar.stock_code == Stock.code)
        .where(Stock.is_active.is_(True), Stock.market.in_(settings.enabled_markets))
        .group_by(Stock.market)
    ).all()
    markets = []
    for market, stock_count, stocks_with_bars, latest_trade_date in rows:
        total = int(stock_count or 0)
        with_bars = int(stocks_with_bars or 0)
        markets.append(
            {
                "market": market,
                "label": market_label(market),
                "stock_count": total,
                "stocks_with_bars": with_bars,
                "coverage_ratio": round(with_bars / total, 4) if total else 0,
                "latest_trade_date": latest_trade_date.isoformat() if latest_trade_date else None,
                "next_batch_size": min(settings.max_stocks_per_market, total) if settings.max_stocks_per_market > 0 else total,
                "remaining_without_bars": max(total - with_bars, 0),
                "next_batch_offset": with_bars,
            }
        )
    markets = sorted(markets, key=lambda item: _market_sort_key(str(item["market"])))
    commands = [
        (
            "MOCK_DATA=false MARKET_DATA_SOURCE=akshare "
            f"ENABLED_MARKETS={item['market']} python scripts/run_daily_pipeline.py "
            f"--markets {item['market']} --max-stocks-per-market {item['next_batch_size']} "
            f"--batch-offset {item['next_batch_offset']} --periods {settings.market_data_periods}"
        )
        for item in markets
    ]
    discovery_commands = [
        f"MOCK_DATA=false MARKET_DATA_SOURCE=akshare ENABLED_MARKETS={item['market']} python scripts/discover_universe.py --markets {item['market']}"
        for item in markets
    ]
    return {
        "mode": "mock" if settings.mock_data else settings.market_data_source,
        "settings": {
            "mock_data": settings.mock_data,
            "market_data_source": settings.market_data_source,
            "enabled_markets": list(settings.enabled_markets),
            "max_stocks_per_market": settings.max_stocks_per_market,
            "market_data_periods": settings.market_data_periods,
        },
        "markets": markets,
        "quality_backfill_focus": _quality_backfill_plan(session, limit_per_segment=10, periods=settings.market_data_periods),
        "discovery_commands": discovery_commands,
        "recommended_commands": commands,
        "safety_rules": [
            "先单市场小批次运行，不直接全市场真实抓取。",
            "每批运行后检查 /api/market/data-quality。",
            "数据质量 FAIL 时不扩大市场范围，不使用趋势评分做研究判断。",
            "真实源不可用时允许 fallback mock，但 Dashboard 必须显示 actual source。",
        ],
    }


def _quality_backfill_plan(session: Session, *, limit_per_segment: int, periods: int) -> dict[str, object]:
    normalized_periods = max(60, min(int(periods), 1000))
    normalized_limit = max(1, min(int(limit_per_segment), 80))
    segments: list[dict[str, object]] = []
    for market, board in QUALITY_BACKFILL_FOCUS:
        candidates = priority_candidates(session, market=market, board=board, limit=normalized_limit, periods=normalized_periods)
        stats = _quality_focus_stats(session, market=market, board=board, periods=normalized_periods)
        queue_payload = {
            "markets": [market],
            "board": board,
            "batches_per_market": 3,
            "batch_limit": min(20, normalized_limit),
            "periods": normalized_periods,
        }
        status = _quality_focus_status(stats)
        segments.append(
            {
                "market": market,
                "market_label": market_label(market),
                "board": board,
                "board_label": board_label(board),
                "status": status,
                "priority": "high" if status == "FAIL" else "medium" if status == "WARN" else "low",
                "reason": _quality_focus_reason(stats),
                "stats": stats,
                "candidate_count": len(candidates),
                "candidates": candidates,
                "cooldown_blocked_codes": _segment_cooldown_blocked_codes(session, market=market, board=board),
                "provider_failed_codes": _segment_provider_failed_codes(session, market=market, board=board),
                "queue_payload": queue_payload,
                "queue_api": "/api/market/ingestion-tasks/backfill",
                "queue_command": _queue_backfill_command(queue_payload),
                "next_action": _quality_focus_next_action(
                    session,
                    market=market,
                    board=board,
                    status=status,
                    candidates=candidates,
                    queue_payload=queue_payload,
                ),
            }
        )
    return {
        "focus": "US/HK/北交所优先回填",
        "periods": normalized_periods,
        "limit_per_segment": normalized_limit,
        "segments": segments,
        "next_actions": [
            "先按 focus 顺序入队 US、HK、北交所回填任务。",
            "每批执行后复查 /api/market/data-quality，FAIL 不消除前不扩大到低优先级市场。",
            "Agent 报告遇到 FAIL 分段时只输出观察和数据不足说明，不输出确定性结论。",
        ],
    }


def _quality_focus_stats(session: Session, *, market: str, board: str, periods: int) -> dict[str, object]:
    bars_summary = (
        select(
            DailyBar.stock_code.label("stock_code"),
            func.count(DailyBar.id).label("bars_count"),
            func.max(DailyBar.trade_date).label("latest_trade_date"),
            func.sum(case((DailyBar.source_kind == "real", 1), else_=0)).label("real_bars_count"),
        )
        .group_by(DailyBar.stock_code)
        .subquery()
    )
    bars_count = func.coalesce(bars_summary.c.bars_count, 0)
    real_bars_count = func.coalesce(bars_summary.c.real_bars_count, 0)
    filters = [
        Stock.is_active.is_(True),
        Stock.listing_status == "listed",
        Stock.asset_type == "equity",
        Stock.is_etf.is_(False),
        Stock.market == market,
    ]
    if board != "all":
        filters.append(Stock.board == board)
    row = session.execute(
        select(
            func.count(Stock.id),
            func.count(bars_summary.c.stock_code),
            func.sum(case((bars_count == 0, 1), else_=0)),
            func.sum(case((bars_count < 60, 1), else_=0)),
            func.sum(case((bars_count < periods, 1), else_=0)),
            func.sum(case((real_bars_count == 0, 1), else_=0)),
            func.max(bars_summary.c.latest_trade_date),
        )
        .outerjoin(bars_summary, bars_summary.c.stock_code == Stock.code)
        .where(*filters)
    ).one()
    stock_count = int(row[0] or 0)
    stocks_with_bars = int(row[1] or 0)
    without_bars = int(row[2] or 0)
    below_required = int(row[3] or 0)
    below_preferred = int(row[4] or 0)
    without_real = int(row[5] or 0)
    required_ready = max(stock_count - below_required, 0)
    preferred_ready = max(stock_count - below_preferred, 0)
    real_ready = max(stock_count - without_real, 0)
    return {
        "stock_count": stock_count,
        "stocks_with_bars": stocks_with_bars,
        "without_bars": without_bars,
        "stocks_with_required_history": required_ready,
        "stocks_with_preferred_history": preferred_ready,
        "stocks_with_real_bars": real_ready,
        "coverage_ratio": round(stocks_with_bars / stock_count, 4) if stock_count else 0.0,
        "required_history_ratio": round(required_ready / stock_count, 4) if stock_count else 0.0,
        "preferred_history_ratio": round(preferred_ready / stock_count, 4) if stock_count else 0.0,
        "real_coverage_ratio": round(real_ready / stock_count, 4) if stock_count else 0.0,
        "latest_trade_date": row[6].isoformat() if row[6] else None,
    }


def _quality_focus_status(stats: dict[str, object]) -> str:
    coverage = float(stats.get("coverage_ratio") or 0.0)
    required = float(stats.get("required_history_ratio") or 0.0)
    real = float(stats.get("real_coverage_ratio") or 0.0)
    preferred = float(stats.get("preferred_history_ratio") or 0.0)
    if coverage < 0.95 or required < 0.95 or real < 0.95:
        return "FAIL"
    if coverage < 1.0 or preferred < 0.8:
        return "WARN"
    return "PASS"


def _quality_focus_reason(stats: dict[str, object]) -> str:
    missing = int(stats.get("without_bars") or 0)
    below_required = int(stats.get("stock_count") or 0) - int(stats.get("stocks_with_required_history") or 0)
    without_real = int(stats.get("stock_count") or 0) - int(stats.get("stocks_with_real_bars") or 0)
    reasons = []
    if missing:
        reasons.append(f"{missing} 只无日线")
    if below_required:
        reasons.append(f"{below_required} 只未达到 60 根K线")
    if without_real:
        reasons.append(f"{without_real} 只缺少真实来源K线")
    return "；".join(reasons) if reasons else "当前无关键质量缺口，继续监控新鲜度。"


def _queue_backfill_command(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False)
    return f"curl -X POST http://localhost:8000/api/market/ingestion-tasks/backfill -H 'Content-Type: application/json' -d '{encoded}'"


def _quality_focus_next_action(
    session: Session,
    *,
    market: str,
    board: str,
    status: str,
    candidates: list[dict[str, object]],
    queue_payload: dict[str, object],
) -> dict[str, object]:
    blocked_codes = _segment_cooldown_blocked_codes(session, market=market, board=board)
    provider_failed_codes = _segment_provider_failed_codes(session, market=market, board=board)
    board_name = board_label(board)
    market_name = market_label(market)
    if provider_failed_codes:
        scope_name = board_name if board != "all" else market_name
        return {
            "kind": "provider_check",
            "message": f"{scope_name} 最近存在 provider 失败；先验证数据源可用性，再对失败标的做单票重试，确认恢复后再执行批量回填。",
            "failed_codes": provider_failed_codes,
            "retry_api": "/api/market/ingestion-tasks",
            "queue_api": "/api/market/ingestion-tasks/backfill",
            "queue_payload": queue_payload,
        }
    if blocked_codes and not candidates:
        return {
            "kind": "wait_for_cooldown",
            "message": f"{board_name if board != 'all' else market_name} 当前候选都被最近失败 cooldown 过滤；先检查失败标的，再等待或单票重试。",
            "blocked_codes": blocked_codes,
            "retry_api": "/api/market/ingestion-tasks",
        }
    if status == "FAIL":
        return {
            "kind": "queue_backfill",
            "message": f"先按 {market_name}/{board_name} 小批次入队回填，执行后立即复查数据质量。",
            "queue_api": "/api/market/ingestion-tasks/backfill",
            "queue_payload": queue_payload,
        }
    if status == "WARN":
        return {
            "kind": "monitor",
            "message": f"{market_name}/{board_name} 当前可继续补齐剩余候选，并持续复查覆盖率与真实源占比。",
            "queue_api": "/api/market/ingestion-tasks/backfill",
            "queue_payload": queue_payload,
        }
    return {
        "kind": "monitor",
        "message": f"{market_name}/{board_name} 当前无紧急缺口，保持日常巡检即可。",
    }


@router.get("/research-universe")
def research_universe(
    include_rows: bool = Query(default=False),
    row_limit: int = Query(default=200, ge=0, le=5000),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if include_rows:
        payload = _research_universe_payload(session)
    else:
        payload = _cached_payload("research-universe:summary", lambda: _research_universe_fast_summary(session), ttl=120.0)
    for segment in payload["segments"]:
        segment["market_label"] = market_label(segment["market"])
        segment["board_label"] = board_label(segment["board"])
    for row in payload["rows"]:
        row["market_label"] = market_label(row["market"])
        row["board_label"] = board_label(row["board"])
    if include_rows:
        payload["rows"] = payload["rows"][:row_limit]
    else:
        payload["rows"] = []
    return payload


def _market_segments(session: Session) -> list[dict[str, object]]:
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    rows = session.execute(
        select(Stock.market, Stock.board, func.count(Stock.id))
        .where(Stock.is_active.is_(True))
        .group_by(Stock.market, Stock.board)
    ).all()
    watch_rows = []
    if latest_date is not None:
        watch_rows = session.execute(
            select(Stock.market, Stock.board, func.count(Stock.id))
            .join(StockScore, StockScore.stock_code == Stock.code)
            .where(StockScore.trade_date == latest_date, StockScore.rating.in_(["强观察", "观察"]))
            .group_by(Stock.market, Stock.board)
        ).all()
    watch_counts = {(market, board): count for market, board, count in watch_rows}
    grouped: dict[str, dict[str, object]] = {}
    for market, board, count in rows:
        market_key = market or "A"
        board_key = board or "main"
        item = grouped.setdefault(
            market_key,
            {
                "market": market_key,
                "label": market_label(market_key),
                "stock_count": 0,
                "watch_count": 0,
                "boards": [],
            },
        )
        item["stock_count"] = int(item["stock_count"]) + int(count)
        item["watch_count"] = int(item["watch_count"]) + int(watch_counts.get((market_key, board_key), 0))
        item["boards"].append(
            {
                "board": board_key,
                "label": board_label(board_key),
                "stock_count": int(count),
                "watch_count": int(watch_counts.get((market_key, board_key), 0)),
            }
        )

    result = sorted(grouped.values(), key=lambda item: _market_sort_key(str(item["market"])))
    for item in result:
        item["boards"] = sorted(item["boards"], key=lambda row: _board_sort_key(str(row["board"])))
    return result


def _market_sort_key(market: str) -> int:
    return MARKET_ORDER.index(market) if market in MARKET_ORDER else 99


def _board_sort_key(board: str) -> int:
    return A_BOARD_ORDER.index(board) if board in A_BOARD_ORDER else 99


def _research_universe_payload(session: Session) -> dict[str, object]:
    return research_universe_payload(session)


def _research_universe_fast_summary(session: Session) -> dict[str, object]:
    stocks = session.scalars(
        select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.market, Stock.board, Stock.code)
    ).all()
    rows: list[dict[str, object]] = []
    for stock in stocks:
        reasons = _fast_universe_exclusion_reasons(stock)
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "board": stock.board,
                "eligible": not reasons,
                "exclusion_reasons": reasons,
                "market_cap": stock.market_cap,
                "float_market_cap": stock.float_market_cap,
                "bars_count": 0,
                "latest_trade_date": None,
                "latest_close": 0.0,
                "avg_amount_20d": 0.0,
                "avg_volume_20d": 0.0,
                "selected_bar_source": "summary_not_loaded",
                "source": stock.source,
                "data_vendor": stock.data_vendor,
                "data_source_trust": 0.0,
                "source_profile": {"sources": [], "mixed_sources": False},
            }
        )
    return {
        "summary": _fast_universe_summary(rows),
        "segments": _fast_universe_segments(rows),
        "exclusion_summary": _fast_universe_exclusion_summary(rows),
        "rules": DEFAULT_RULES,
        "trusted_data_sources": TRUSTED_DATA_SOURCES,
        "rows": [],
        "summary_mode": "fast",
    }


def _fast_universe_exclusion_reasons(stock: Stock) -> list[str]:
    rules = DEFAULT_RULES.get(stock.market, DEFAULT_RULES["A"])
    reasons: list[str] = []
    if not stock.is_active:
        reasons.append("inactive")
    if stock.listing_status != "listed":
        reasons.append("not_listed")
    if stock.asset_type != "equity":
        reasons.append("not_equity")
    if stock.is_etf:
        reasons.append("etf_excluded")
    if stock.is_st:
        reasons.append("st_or_special_treatment")
    if float(stock.market_cap or 0.0) < float(rules["min_market_cap"]):
        reasons.append("market_cap_too_small")
    if float(stock.float_market_cap or 0.0) < float(rules["min_float_market_cap"]):
        reasons.append("float_market_cap_too_small")
    return reasons


def _fast_universe_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    eligible = sum(1 for row in rows if row["eligible"])
    return {
        "stock_count": total,
        "eligible_count": eligible,
        "excluded_count": total - eligible,
        "eligible_ratio": round(eligible / total, 4) if total else 0,
    }


def _fast_universe_segments(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["market"]), str(row["board"]))
        segment = grouped.setdefault(
            key,
            {"market": key[0], "board": key[1], "stock_count": 0, "eligible_count": 0, "excluded_count": 0, "exclusion_reasons": {}},
        )
        segment["stock_count"] += 1
        if row["eligible"]:
            segment["eligible_count"] += 1
        else:
            segment["excluded_count"] += 1
            for reason in row["exclusion_reasons"]:
                segment["exclusion_reasons"][reason] = int(segment["exclusion_reasons"].get(reason, 0)) + 1
    result = []
    for segment in grouped.values():
        total = int(segment["stock_count"])
        segment["eligible_ratio"] = round(int(segment["eligible_count"]) / total, 4) if total else 0
        result.append(segment)
    return sorted(result, key=lambda item: (_market_sort_key(str(item["market"])), _board_sort_key(str(item["board"]))))


def _fast_universe_exclusion_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for reason in row["exclusion_reasons"]:
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _bars_by_stock(session: Session, stock_codes: list[str]) -> dict[str, list[DailyBar]]:
    if not stock_codes:
        return {}
    rows = session.scalars(select(DailyBar).where(DailyBar.stock_code.in_(stock_codes)).order_by(DailyBar.stock_code, DailyBar.trade_date)).all()
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.stock_code, []).append(row)
    return grouped


def _recent_unusable_symbols(session: Session, *, limit: int = 200) -> dict[str, str]:
    rows = session.execute(
        select(DataIngestionTask.error, DataIngestionTask.last_error)
        .where(DataIngestionTask.status.in_(["success", "failed"]))
        .order_by(DataIngestionTask.finished_at.desc(), DataIngestionTask.id.desc())
        .limit(limit)
    ).all()
    reasons: dict[str, str] = {}
    for error, last_error in rows:
        for value in (error or "", last_error or ""):
            for code, reason in re.findall(r"([A-Za-z0-9_.-]+):(no_usable_bars|unsupported_daily_bars)", value):
                reasons.setdefault(code.upper(), reason)
    return reasons


def _recent_provider_failed_symbols(session: Session, *, limit: int = 200) -> dict[str, str]:
    rows = session.execute(
        select(DataIngestionTask.error, DataIngestionTask.last_error)
        .where(DataIngestionTask.status.in_(["success", "failed"]))
        .order_by(DataIngestionTask.finished_at.desc(), DataIngestionTask.id.desc())
        .limit(limit)
    ).all()
    reasons: dict[str, str] = {}
    for error, last_error in rows:
        for value in (error or "", last_error or ""):
            for code, reason in re.findall(r"([A-Za-z0-9_.-]+):(hk_provider_failed|bse_provider_failed)", value):
                reasons.setdefault(code.upper(), reason)
    return reasons


def _segment_cooldown_blocked_codes(session: Session, *, market: str, board: str) -> list[str]:
    return _segment_codes_from_reason_map(session, market=market, board=board, reason_map=_recent_unusable_symbols(session))


def _segment_provider_failed_codes(session: Session, *, market: str, board: str) -> list[str]:
    return _segment_codes_from_reason_map(session, market=market, board=board, reason_map=_recent_provider_failed_symbols(session))


def _segment_codes_from_reason_map(session: Session, *, market: str, board: str, reason_map: dict[str, str]) -> list[str]:
    if not reason_map:
        return []
    query = select(Stock.code).where(Stock.market == market.upper())
    if board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    segment_codes = {code.upper() for code in session.scalars(query).all()}
    return sorted(code for code in reason_map if code in segment_codes)


def _instrument_payload(stock: Stock, bars_count: int | None = None, latest_trade_date: object | None = None) -> dict[str, object]:
    return {
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "market_label": market_label(stock.market),
        "board": stock.board,
        "board_label": board_label(stock.board),
        "exchange": stock.exchange,
        "asset_type": stock.asset_type,
        "currency": stock.currency,
        "listing_status": stock.listing_status,
        "industry_level1": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "market_cap": stock.market_cap,
        "float_market_cap": stock.float_market_cap,
        "listing_date": stock.listing_date.isoformat() if stock.listing_date else None,
        "delisting_date": stock.delisting_date.isoformat() if stock.delisting_date else None,
        "is_st": stock.is_st,
        "is_etf": stock.is_etf,
        "is_adr": stock.is_adr,
        "is_active": stock.is_active,
        "source": stock.source,
        "data_vendor": stock.data_vendor,
        "bars_count": int(bars_count or 0),
        "latest_trade_date": latest_trade_date.isoformat() if latest_trade_date else None,
        "updated_at": stock.updated_at.isoformat(),
    }


def _instrument_payload_with_bars(session: Session, stock: Stock) -> dict[str, object]:
    bars_count, latest_trade_date = session.execute(
        select(func.count(DailyBar.id), func.max(DailyBar.trade_date)).where(DailyBar.stock_code == stock.code)
    ).one()
    return _instrument_payload(stock, bars_count=bars_count, latest_trade_date=latest_trade_date)
