from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from loguru import logger
from sqlalchemy import asc, case, desc, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.data_sources.provider import get_market_data_client
from app.db.models import DailyBar, DataIngestionTask, Stock, utcnow
from app.db.session import ingestion_task_runtime_column_definitions
from app.pipeline.market_data_job import run_market_data_job


DEFAULT_TASK_LEASE_SECONDS = 15 * 60
DEFAULT_STALE_HEARTBEAT_SECONDS = 30 * 60
_TASK_RUNTIME_SCHEMA_READY: set[int] = set()


def create_ingestion_task(
    session: Session,
    *,
    task_type: str,
    market: str = "A",
    board: str = "all",
    stock_code: str | None = None,
    source: str | None = None,
    batch_limit: int = 20,
    periods: int = 320,
    priority: float | None = None,
) -> DataIngestionTask:
    ensure_ingestion_task_runtime_columns(session)
    normalized_type = task_type.lower()
    if normalized_type not in {"batch", "single"}:
        raise ValueError("task_type must be batch or single")
    normalized_market = market.upper()
    normalized_board = board.lower()
    normalized_source = (source or ("akshare" if settings.market_data_source != "mock" else "mock")).lower()
    normalized_code = stock_code.strip().upper() if stock_code else None
    if normalized_type == "single" and not normalized_code:
        raise ValueError("single task requires stock_code")
    task = DataIngestionTask(
        task_key=f"{normalized_type}:{normalized_market}:{normalized_board}:{normalized_code or 'batch'}:{utcnow().strftime('%Y%m%d%H%M%S%f')}:{uuid4().hex[:8]}",
        task_type=normalized_type,
        market=normalized_market,
        board=normalized_board,
        stock_code=normalized_code,
        source=normalized_source,
        status="pending",
        priority=float(priority if priority is not None else _default_priority(normalized_type, normalized_market, normalized_code)),
        batch_limit=max(1, min(int(batch_limit), 200)),
        periods=max(60, min(int(periods), 1000)),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    _update_task_runtime(session, task.id, progress=0.0, clear_lease=True)
    _attach_task_runtime(session, task)
    return task


def claim_next_ingestion_task(
    session: Session,
    *,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    stale_after_seconds: int = DEFAULT_STALE_HEARTBEAT_SECONDS,
) -> DataIngestionTask | None:
    ensure_ingestion_task_runtime_columns(session)
    worker = worker_id or _default_worker_id()
    _recover_stale_running_tasks(session, stale_after_seconds=stale_after_seconds)
    candidates = session.scalars(
        select(DataIngestionTask)
        .where(DataIngestionTask.status.in_(["pending", "failed"]))
        .where(DataIngestionTask.retry_count <= DataIngestionTask.max_retries)
        .order_by(case((DataIngestionTask.status == "pending", 0), else_=1), desc(DataIngestionTask.priority), asc(DataIngestionTask.created_at))
        .limit(10)
    ).all()
    for task in candidates:
        if _claim_task(session, task.id, worker_id=worker, lease_seconds=lease_seconds):
            claimed = session.get(DataIngestionTask, task.id)
            if claimed is None:
                continue
            _attach_task_runtime(session, claimed)
            return claimed
    return None


def run_next_ingestion_task(
    session: Session,
    *,
    end_date: date | None = None,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
) -> DataIngestionTask | None:
    task = claim_next_ingestion_task(session, worker_id=worker_id, lease_seconds=lease_seconds)
    if task is None:
        return None
    return run_ingestion_task(
        session,
        task,
        end_date=end_date,
        worker_id=getattr(task, "worker_id", worker_id),
        lease_seconds=lease_seconds,
        claimed=True,
    )


def enqueue_ingestion_backfill(
    session: Session,
    *,
    markets: tuple[str, ...] = ("A", "US", "HK"),
    board: str = "all",
    source: str | None = None,
    batches_per_market: int = 3,
    batch_limit: int = 20,
    periods: int = 320,
) -> dict[str, object]:
    normalized_markets = tuple(_normalize_backfill_markets(markets))
    normalized_board = board.lower()
    batches = max(1, min(int(batches_per_market), 20))
    limit = max(1, min(int(batch_limit), 200))
    queued: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for market in normalized_markets:
        target_board = normalized_board if market == "A" else "all"
        pending_count = _pending_task_count(session, market, target_board)
        if pending_count >= batches:
            skipped.append({"market": market, "board": target_board, "reason": "pending_queue_already_sufficient", "pending": pending_count})
            continue
        for index in range(batches - pending_count):
            task = create_ingestion_task(
                session,
                task_type="batch",
                market=market,
                board=target_board,
                source=source,
                batch_limit=limit,
                periods=periods,
                priority=_default_priority("batch", market, None) + (batches - index) / 100,
            )
            queued.append(task_payload(task))
    return {
        "markets": list(normalized_markets),
        "board": normalized_board,
        "batches_per_market": batches,
        "batch_limit": limit,
        "periods": periods,
        "queued_count": len(queued),
        "skipped_count": len(skipped),
        "queued_tasks": queued,
        "skipped": skipped,
    }


def run_ingestion_queue(
    session: Session,
    *,
    max_tasks: int = 3,
    end_date: date | None = None,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
) -> dict[str, object]:
    task_limit = max(1, min(int(max_tasks), 20))
    rows: list[dict[str, object]] = []
    seen_task_ids: set[int] = set()
    stopped_reason = "empty_queue"
    for _ in range(task_limit):
        task = run_next_ingestion_task(session, end_date=end_date, worker_id=worker_id, lease_seconds=lease_seconds)
        if task is None:
            stopped_reason = "empty_queue"
            break
        if task.id in seen_task_ids:
            stopped_reason = "same_task_selected_again"
            break
        seen_task_ids.add(task.id)
        rows.append(task_payload(task))
        if task.status == "failed":
            stopped_reason = "task_failed"
            break
    else:
        stopped_reason = "max_tasks_reached"
    return {"tasks_run": len(rows), "max_tasks": task_limit, "stopped_reason": stopped_reason, "tasks": rows}


def run_ingestion_task(
    session: Session,
    task: DataIngestionTask,
    *,
    end_date: date | None = None,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    claimed: bool = False,
) -> DataIngestionTask:
    ensure_ingestion_task_runtime_columns(session)
    worker = worker_id or getattr(task, "worker_id", None) or _default_worker_id()
    if task.status == "running" and not claimed and not _task_lease_is_stale(session, task.id):
        _attach_task_runtime(session, task)
        return task
    if task.status == "running" and not claimed:
        _recover_stale_running_tasks(session, stale_after_seconds=0)
        session.refresh(task)
    if task.status != "running" and not _claim_task(session, task.id, worker_id=worker, lease_seconds=lease_seconds):
        current = session.get(DataIngestionTask, task.id)
        if current is None:
            raise RuntimeError("ingestion task disappeared before claim")
        _attach_task_runtime(session, current)
        return current
    task = session.get(DataIngestionTask, task.id)
    if task is None:
        raise RuntimeError("ingestion task disappeared after claim")
    task.started_at = task.started_at or utcnow()
    task.finished_at = None
    task.error = ""
    _save_task_checkpoint(session, task, progress=0.0, last_error="", last_stock=None, lease_seconds=lease_seconds)
    try:
        stocks = _stocks_for_task(session, task)
        codes = tuple(stock.code for stock in stocks)
        task.requested = len(codes)
        _save_task_checkpoint(session, task, progress=0.0, lease_seconds=lease_seconds)
        if not codes:
            raise RuntimeError("no eligible stock codes selected for ingestion task")
        unsupported = [stock for stock in stocks if not _supports_daily_bars(stock)]
        if unsupported:
            names = "、".join(f"{stock.name}({stock.code})" for stock in unsupported[:5])
            failed_detail = _failed_symbol_error([{"code": stock.code, "market": stock.market, "error": "unsupported_daily_bars"} for stock in unsupported])
            task.status = "failed"
            task.processed = 0
            task.failed = len(unsupported)
            task.error = f"该标的不是普通股票或当前行情源暂不支持日K补齐：{names}; {failed_detail}"
            task.retry_count = task.max_retries + 1
            task.finished_at = utcnow()
            _save_task_checkpoint(session, task, progress=1.0, last_error=task.error, last_stock=unsupported[-1].code, clear_lease=True)
            return task
        result = run_market_data_job(
            session,
            end_date=end_date,
            markets=(task.market,),
            max_stocks_per_market=len(codes),
            stock_codes=codes,
            periods=task.periods,
            batch_offset=0,
            client=_client_for_source(task.source),
        )
        task.processed = int(result["stocks_processed"])
        task.inserted = int(result["inserted"])
        task.updated = int(result["updated"])
        task.failed = int(result["missing_stocks"])
        processed_symbols = [str(code) for code in result.get("processed_symbols", [])]
        failed_symbols = [dict(item) for item in result.get("failed_symbols", [])]
        failed_detail = _failed_symbol_error(failed_symbols)
        if task.processed == 0 or task.failed >= task.processed:
            task.status = "failed"
            task.error = f"provider returned no usable bars for selected stocks; {failed_detail}" if failed_detail else "provider returned no usable bars for selected stocks"
            task.retry_count = task.max_retries + 1 if failed_symbols else task.retry_count + 1
        else:
            task.status = "success"
            task.error = failed_detail
        task.finished_at = utcnow()
        _save_task_checkpoint(
            session,
            task,
            progress=1.0,
            last_error=task.error,
            last_stock=processed_symbols[-1] if processed_symbols else None,
            clear_lease=True,
        )
        return task
    except Exception as exc:
        logger.warning("ingestion task {} failed: {}", task.id, exc)
        session.rollback()
        task = session.get(DataIngestionTask, task.id)
        if task is None:
            raise
        task.status = "failed"
        task.retry_count += 1
        task.error = str(exc)
        task.finished_at = utcnow()
        _save_task_checkpoint(session, task, progress=1.0, last_error=task.error, clear_lease=True)
        return task


def list_ingestion_tasks(session: Session, *, limit: int = 50) -> list[DataIngestionTask]:
    ensure_ingestion_task_runtime_columns(session)
    rows = list(session.scalars(select(DataIngestionTask).order_by(desc(DataIngestionTask.created_at)).limit(limit)).all())
    for task in rows:
        _attach_task_runtime(session, task)
    return rows


def priority_candidates(
    session: Session,
    *,
    market: str = "A",
    board: str = "all",
    limit: int = 20,
    periods: int = 320,
) -> list[dict[str, object]]:
    return [_candidate_payload(row, bars_count, latest_trade_date, periods) for row, bars_count, latest_trade_date in _priority_query(session, market, board, limit, periods)]


def task_payload(task: DataIngestionTask) -> dict[str, object]:
    worker_id = getattr(task, "worker_id", None)
    heartbeat_at = getattr(task, "heartbeat_at", None)
    lease_expires_at = getattr(task, "lease_expires_at", None)
    progress = float(getattr(task, "progress", 0.0) or 0.0)
    return {
        "id": task.id,
        "task_key": task.task_key,
        "task_type": task.task_type,
        "market": task.market,
        "board": task.board,
        "stock_code": task.stock_code,
        "source": task.source,
        "status": task.status,
        "priority": task.priority,
        "batch_limit": task.batch_limit,
        "periods": task.periods,
        "requested": task.requested,
        "processed": task.processed,
        "inserted": task.inserted,
        "updated": task.updated,
        "failed": task.failed,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "error": task.error,
        "worker_id": worker_id,
        "heartbeat_at": heartbeat_at,
        "heartbeat": heartbeat_at,
        "lease_expires_at": lease_expires_at,
        "lease": {
            "worker_id": worker_id,
            "expires_at": lease_expires_at,
        },
        "progress": progress,
        "last_error": getattr(task, "last_error", "") or "",
        "last_stock": getattr(task, "last_stock", None),
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def ensure_ingestion_task_runtime_columns(session: Session) -> None:
    bind = session.get_bind()
    bind_key = id(bind)
    if bind_key in _TASK_RUNTIME_SCHEMA_READY:
        return
    inspector = inspect(bind)
    if not inspector.has_table(DataIngestionTask.__tablename__):
        return
    existing = {column["name"] for column in inspector.get_columns(DataIngestionTask.__tablename__)}
    missing = [(name, column_type) for name, column_type in ingestion_task_runtime_column_definitions(bind).items() if name not in existing]
    if missing:
        with bind.begin() as connection:
            for name, column_type in missing:
                connection.execute(text(f"ALTER TABLE {DataIngestionTask.__tablename__} ADD COLUMN {name} {column_type}"))
    _TASK_RUNTIME_SCHEMA_READY.add(bind_key)


def _claim_task(session: Session, task_id: int, *, worker_id: str, lease_seconds: int) -> bool:
    now = _runtime_timestamp()
    lease_expires_at = _runtime_timestamp(utcnow() + timedelta(seconds=max(30, int(lease_seconds))))
    result = session.execute(
        text(
            """
            UPDATE data_ingestion_task
            SET status = 'running',
                worker_id = :worker_id,
                heartbeat_at = :heartbeat_at,
                lease_expires_at = :lease_expires_at,
                progress = CASE WHEN requested > 0 THEN CAST(processed AS FLOAT) / requested ELSE 0 END,
                started_at = COALESCE(started_at, :started_at),
                finished_at = NULL,
                error = CASE WHEN status = 'pending' THEN '' ELSE error END
            WHERE id = :task_id
              AND status IN ('pending', 'failed')
              AND retry_count <= max_retries
            """
        ),
        {
            "task_id": task_id,
            "worker_id": worker_id,
            "heartbeat_at": now,
            "lease_expires_at": lease_expires_at,
            "started_at": utcnow(),
        },
    )
    session.commit()
    return int(result.rowcount or 0) == 1


def _recover_stale_running_tasks(session: Session, *, stale_after_seconds: int) -> None:
    now = _runtime_timestamp()
    stale_before = _runtime_timestamp(utcnow() - timedelta(seconds=max(0, int(stale_after_seconds))))
    message = f"stale running task recovered at {now}"
    stale_condition = _stale_runtime_condition_sql(session)
    result = session.execute(
        text(
            f"""
            UPDATE data_ingestion_task
            SET status = 'pending',
                worker_id = NULL,
                lease_expires_at = NULL,
                last_error = :message,
                error = CASE WHEN error IS NULL OR error = '' THEN :message ELSE error END
            WHERE status = 'running'
              AND ({stale_condition})
            """
        ),
        {"message": message, "now": now, "stale_before": stale_before},
    )
    if int(result.rowcount or 0) > 0:
        session.commit()
    else:
        session.rollback()


def _task_lease_is_stale(session: Session, task_id: int) -> bool:
    ensure_ingestion_task_runtime_columns(session)
    now = _runtime_timestamp()
    stale_before = _runtime_timestamp(utcnow() - timedelta(seconds=DEFAULT_STALE_HEARTBEAT_SECONDS))
    stale_condition = _stale_runtime_condition_sql(session)
    stale = session.scalar(
        text(
            f"""
            SELECT 1
            FROM data_ingestion_task
            WHERE id = :task_id
              AND status = 'running'
              AND ({stale_condition})
            LIMIT 1
            """
        ),
        {"task_id": task_id, "now": now, "stale_before": stale_before},
    )
    return stale is not None


def _stale_runtime_condition_sql(session: Session) -> str:
    if session.get_bind().dialect.name == "sqlite":
        return """
            lease_expires_at IS NULL
            OR datetime(lease_expires_at) <= datetime(:now)
            OR heartbeat_at IS NULL
            OR datetime(heartbeat_at) <= datetime(:stale_before)
        """
    return """
        lease_expires_at IS NULL
        OR lease_expires_at <= :now
        OR heartbeat_at IS NULL
        OR heartbeat_at <= :stale_before
    """


def _save_task_checkpoint(
    session: Session,
    task: DataIngestionTask,
    *,
    progress: float | None = None,
    last_error: str | None = None,
    last_stock: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    clear_lease: bool = False,
) -> None:
    session.add(task)
    session.flush()
    _update_task_runtime(
        session,
        task.id,
        worker_id=getattr(task, "worker_id", None),
        progress=progress,
        last_error=last_error,
        last_stock=last_stock,
        lease_seconds=lease_seconds,
        clear_lease=clear_lease,
        commit=False,
    )
    session.commit()
    session.refresh(task)
    _attach_task_runtime(session, task)


def _update_task_runtime(
    session: Session,
    task_id: int,
    *,
    worker_id: str | None = None,
    progress: float | None = None,
    last_error: str | None = None,
    last_stock: str | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    clear_lease: bool = False,
    commit: bool = True,
) -> None:
    ensure_ingestion_task_runtime_columns(session)
    now = _runtime_timestamp()
    lease_expires_at = None if clear_lease else _runtime_timestamp(utcnow() + timedelta(seconds=max(30, int(lease_seconds))))
    session.execute(
        text(
            """
            UPDATE data_ingestion_task
            SET worker_id = CASE WHEN :clear_lease THEN NULL ELSE COALESCE(:worker_id, worker_id) END,
                heartbeat_at = :heartbeat_at,
                lease_expires_at = :lease_expires_at,
                progress = COALESCE(:progress, progress, 0),
                last_error = COALESCE(:last_error, last_error, ''),
                last_stock = COALESCE(:last_stock, last_stock)
            WHERE id = :task_id
            """
        ),
        {
            "task_id": task_id,
            "worker_id": worker_id,
            "heartbeat_at": now,
            "lease_expires_at": lease_expires_at,
            "progress": progress,
            "last_error": last_error,
            "last_stock": last_stock,
            "clear_lease": clear_lease,
        },
    )
    if commit:
        session.commit()


def _task_runtime(session: Session, task_id: int) -> dict[str, Any]:
    ensure_ingestion_task_runtime_columns(session)
    row = session.execute(
        text(
            """
            SELECT worker_id, heartbeat_at, lease_expires_at, progress, last_error, last_stock
            FROM data_ingestion_task
            WHERE id = :task_id
            """
        ),
        {"task_id": task_id},
    ).mappings().first()
    if row is None:
        return {}
    return dict(row)


def _attach_task_runtime(session: Session, task: DataIngestionTask) -> None:
    for key, value in _task_runtime(session, task.id).items():
        if key in {"heartbeat_at", "lease_expires_at"}:
            value = _coerce_runtime_datetime(value)
        setattr(task, key, value)


def _runtime_timestamp(value=None) -> datetime:
    return value or utcnow()


def _coerce_runtime_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _default_worker_id() -> str:
    host = os.environ.get("HOSTNAME") or "local"
    return f"{host}:{os.getpid()}:{uuid4().hex[:8]}"


def _failed_symbol_error(failed_symbols: list[dict[str, Any]]) -> str:
    if not failed_symbols:
        return ""
    preview_limit = 50
    preview = ", ".join(f"{item.get('code', '')}:{item.get('error', '')}" for item in failed_symbols[:preview_limit])
    suffix = f"; +{len(failed_symbols) - preview_limit} more" if len(failed_symbols) > preview_limit else ""
    return f"failed_symbols=[{preview}{suffix}]"


def source_comparison(session: Session, stock_code: str) -> dict[str, object]:
    rows = session.execute(
        select(
            DailyBar.source,
            func.count(DailyBar.id),
            func.min(DailyBar.trade_date),
            func.max(DailyBar.trade_date),
        )
        .where(DailyBar.stock_code == stock_code)
        .group_by(DailyBar.source)
        .order_by(DailyBar.source)
    ).all()
    return {
        "stock_code": stock_code,
        "sources": [
            {
                "source": source,
                "bars_count": int(count or 0),
                "first_trade_date": first_date.isoformat() if first_date else None,
                "latest_trade_date": latest_date.isoformat() if latest_date else None,
            }
            for source, count, first_date, latest_date in rows
        ],
    }


def _stocks_for_task(session: Session, task: DataIngestionTask) -> list[Stock]:
    if task.task_type == "single" and task.stock_code:
        stock = session.scalar(select(Stock).where(Stock.code == task.stock_code))
        return [stock] if stock else []
    return [stock for stock, _, _ in _priority_query(session, task.market, task.board, task.batch_limit, task.periods)]


def _priority_query(session: Session, market: str, board: str, limit: int, periods: int):
    failed_cooldown_codes = _recent_unusable_symbol_codes(session, market)
    bars_summary = (
        select(
            DailyBar.stock_code.label("stock_code"),
            func.count(DailyBar.id).label("bars_count"),
            func.max(DailyBar.trade_date).label("latest_trade_date"),
        )
        .group_by(DailyBar.stock_code)
        .subquery()
    )
    bars_count = func.coalesce(bars_summary.c.bars_count, 0)
    query = (
        select(Stock, bars_count, bars_summary.c.latest_trade_date)
        .outerjoin(bars_summary, bars_summary.c.stock_code == Stock.code)
        .where(
            Stock.is_active.is_(True),
            Stock.listing_status == "listed",
            Stock.asset_type == "equity",
            Stock.is_etf.is_(False),
            Stock.market == market.upper(),
            bars_count < periods,
            ~Stock.name.like("%定转%"),
            ~Stock.name.like("%转债%"),
            ~Stock.name.like("%债%"),
            ~Stock.name.like("%优先%"),
            ~Stock.name.like("%权证%"),
            ~Stock.name.like("%退市%"),
            ~Stock.name.like("%退%"),
        )
    )
    if board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    if market.upper() == "US":
        query = query.where(*_supported_us_code_filters())
    if market.upper() == "HK":
        query = query.where(*_supported_hk_code_filters())
    if failed_cooldown_codes:
        query = query.where(~Stock.code.in_(failed_cooldown_codes))
    return session.execute(query.order_by(bars_count, desc(Stock.float_market_cap), desc(Stock.market_cap), Stock.code).limit(max(1, limit))).all()


def _recent_unusable_symbol_codes(session: Session, market: str, *, limit: int = 200) -> set[str]:
    rows = session.execute(
        select(DataIngestionTask.error, DataIngestionTask.last_error)
        .where(
            DataIngestionTask.market == market.upper(),
            DataIngestionTask.status.in_(["success", "failed"]),
        )
        .order_by(desc(DataIngestionTask.finished_at), desc(DataIngestionTask.id))
        .limit(limit)
    ).all()
    codes: set[str] = set()
    for error, last_error in rows:
        for value in (error or "", last_error or ""):
            for code, reason in re.findall(r"([A-Za-z0-9_.-]+):(no_usable_bars|unsupported_daily_bars)", value):
                codes.add(code.upper())
    return codes


def _candidate_payload(stock: Stock, bars_count: int, latest_trade_date, periods: int) -> dict[str, object]:
    missing = max(periods - int(bars_count or 0), 0)
    return {
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "board": stock.board,
        "market_cap": stock.market_cap,
        "float_market_cap": stock.float_market_cap,
        "bars_count": int(bars_count or 0),
        "missing_bars": missing,
        "latest_trade_date": latest_trade_date.isoformat() if latest_trade_date else None,
        "priority_score": round(missing + min(stock.float_market_cap or stock.market_cap or 0, 10_000) / 100, 2),
    }


def _client_for_source(source: str):
    return get_market_data_client(source=source)


def _normalize_backfill_markets(markets: tuple[str, ...]) -> list[str]:
    requested = [item.upper() for item in markets if item.upper() in {"A", "US", "HK"}]
    if not requested:
        requested = ["A", "US", "HK"]
    return requested


def _pending_task_count(session: Session, market: str, board: str) -> int:
    return int(
        session.scalar(
            select(func.count(DataIngestionTask.id)).where(
                DataIngestionTask.task_type == "batch",
                DataIngestionTask.market == market,
                DataIngestionTask.board == board,
                DataIngestionTask.status.in_(["pending", "running"]),
            )
        )
        or 0
    )


def _supports_daily_bars(stock: Stock) -> bool:
    if stock.asset_type != "equity" or stock.is_etf:
        return False
    if stock.market == "A":
        unsupported_tokens = ("定转", "转债", "债", "优先", "权证")
        if any(token in stock.name for token in unsupported_tokens):
            return False
        if stock.code.startswith("81"):
            return False
    if stock.market == "US" and not _is_supported_us_stock(stock):
        return False
    if stock.market == "HK" and not _is_supported_hk_stock(stock):
        return False
    return True


def _supported_us_code_filters() -> list[object]:
    filters: list[object] = [
        ~Stock.code.like("%.%"),
        ~Stock.code.like("%\\_%", escape="\\"),
        Stock.market_cap > 0,
    ]
    filters.extend(~Stock.code.like(f"%{digit}%") for digit in "0123456789")
    filters.extend(
        [
            or_(Stock.market_cap > 0, ~Stock.code.like("%R")),
            or_(Stock.market_cap > 0, ~Stock.code.like("%W")),
            or_(Stock.market_cap > 50, ~Stock.code.like("%U")),
            ~Stock.code.like("%WI"),
            ~Stock.code.like("%WS"),
            ~Stock.code.like("%WT"),
            ~Stock.name.ilike("% WI"),
            ~Stock.name.ilike("% When Issued%"),
        ]
    )
    filters.extend(_supported_us_name_filters())
    return filters


def _is_supported_us_code(code: str) -> bool:
    normalized = code.upper()
    return "." not in normalized and "_" not in normalized and not any(char.isdigit() for char in normalized)


def _is_supported_us_stock(stock: Stock) -> bool:
    if not stock.market_cap or stock.market_cap <= 0:
        return False
    if not _is_supported_us_code(stock.code):
        return False
    if stock.code.endswith("U") and stock.market_cap <= 50:
        return False
    upper_name = stock.name.upper()
    upper = f"{upper_name} {stock.code}".upper()
    if upper_name.endswith(" WI") or " WHEN ISSUED" in upper:
        return False
    return not any(token in upper for token in _UNSUPPORTED_US_SECURITY_TOKENS)


_UNSUPPORTED_US_SECURITY_TOKENS = (
    " ETF",
    " ETN",
    " FUND",
    " WARRANT",
    " WTS",
    " WT",
    " RIGHT",
    " RT",
    " UNIT",
    " UNI",
    " PREFERRED",
    " NOTE",
    " BOND",
    " LEVERAGE",
    " LEVERAGED",
    " DAILY",
    " YIELDMAX",
    " GRANITESHARES",
    " DIREXION",
    " T-REX",
    " ROUNDHILL",
    "二倍",
    "三倍",
    "做多",
    "做空",
    "期权收益",
    "收益策略",
    "基金",
    " ISHARES",
    " PACER",
    " INNOVATOR",
    " ABRDN",
    " QRAFT",
    " HEDGED",
    " MULTI-ASSET",
    " INCOME ET",
    " ADOPTERS ET",
    " ACTIVEPASSIVE",
    " ALLIANZIM",
    " TRUESHARES",
    " FT VEST",
    " BUFFER",
    " STRUCTURED OUTCOME",
    " EQUITY MAX",
    " ACQUISITION",
    " ACQUISI",
    " SPAC",
)


def _supported_us_name_filters() -> list[object]:
    return [~Stock.name.ilike(f"%{token.strip()}%") for token in _UNSUPPORTED_US_SECURITY_TOKENS]


def _supported_hk_code_filters() -> list[object]:
    filters: list[object] = [
        ~Stock.code.like("04%"),
        ~Stock.code.like("05%"),
    ]
    filters.extend(~Stock.name.ilike(f"%{token}%") for token in _UNSUPPORTED_HK_SECURITY_TOKENS)
    return filters


def _is_supported_hk_stock(stock: Stock) -> bool:
    if stock.code.startswith(("04", "05")):
        return False
    upper = f"{stock.name} {stock.code}".upper()
    return not any(token in upper for token in _UNSUPPORTED_HK_SECURITY_TOKENS)


_UNSUPPORTED_HK_SECURITY_TOKENS = (
    "EFN",
    "HKGB",
    "SUKUK",
    "BOND",
    "NOTE",
    "NOTES",
    " N",
    "FRN",
    "PRC",
    "PTT",
    "CNOOC F",
    " B27",
    " B28",
    " B32",
    "SPCSC",
    "STOCK ",
    "INV B",
    "CB B",
    "SFIC B",
    "SOAI B",
    "SDS",
    "SDCS",
    "SPCS",
    "PREF",
    "UGPS",
    "SGPS",
    " B29",
    " B2",
    " B3",
    " B4",
    " B5",
    " B48",
    "PSGCS",
    "金兑",
    "债",
)


def _default_priority(task_type: str, market: str, stock_code: str | None) -> float:
    if task_type == "single":
        return 10_000.0
    return {"A": 300.0, "US": 200.0, "HK": 100.0}.get(market, 50.0) + (100.0 if stock_code else 0.0)
