from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, desc, func, select, text
from sqlalchemy.orm import Session

from app.db.models import DailyBar, DataIngestionBatch, DataIngestionTask, DataSourceRun, Stock
from app.db.session import canonical_database_url, sqlite_database_path
from app.pipeline.ingestion_task_service import ensure_ingestion_task_runtime_columns


DEFAULT_BACKFILL_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "backfill" / "market_data_backfill_manifest.json"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_backfill_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_backfill_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def market_data_coverage(session: Session, *, markets: tuple[str, ...], complete_bars: int) -> list[dict[str, Any]]:
    normalized_markets = tuple(market.upper() for market in markets)
    bars_summary = (
        select(
            DailyBar.stock_code.label("stock_code"),
            func.count(DailyBar.id).label("bars_count"),
            func.min(DailyBar.trade_date).label("first_trade_date"),
            func.max(DailyBar.trade_date).label("latest_trade_date"),
        )
        .group_by(DailyBar.stock_code)
        .subquery()
    )
    bars_count = func.coalesce(bars_summary.c.bars_count, 0)
    rows = session.execute(
        select(
            Stock.market,
            func.count(Stock.id),
            func.sum(case((bars_count >= complete_bars, 1), else_=0)),
            func.sum(case((and_(bars_count > 0, bars_count < complete_bars), 1), else_=0)),
            func.sum(case((bars_count == 0, 1), else_=0)),
            func.avg(bars_count),
            func.min(bars_summary.c.first_trade_date),
            func.max(bars_summary.c.latest_trade_date),
        )
        .outerjoin(bars_summary, bars_summary.c.stock_code == Stock.code)
        .where(
            Stock.market.in_(normalized_markets),
            Stock.is_active.is_(True),
            Stock.listing_status == "listed",
            Stock.asset_type == "equity",
            Stock.is_etf.is_(False),
        )
        .group_by(Stock.market)
    ).all()
    by_market = {
        market: {
            "market": market,
            "eligible_symbols": int(total or 0),
            "covered_symbols": int(covered or 0),
            "partial_symbols": int(partial or 0),
            "empty_symbols": int(empty or 0),
            "coverage_ratio": round((int(covered or 0) / int(total or 1)), 4) if total else 0.0,
            "average_bars": round(float(avg_bars or 0), 2),
            "first_trade_date": first_date.isoformat() if first_date else None,
            "latest_trade_date": latest_date.isoformat() if latest_date else None,
            "complete_bars_threshold": complete_bars,
        }
        for market, total, covered, partial, empty, avg_bars, first_date, latest_date in rows
    }
    return [
        by_market.get(
            market,
            {
                "market": market,
                "eligible_symbols": 0,
                "covered_symbols": 0,
                "partial_symbols": 0,
                "empty_symbols": 0,
                "coverage_ratio": 0.0,
                "average_bars": 0.0,
                "first_trade_date": None,
                "latest_trade_date": None,
                "complete_bars_threshold": complete_bars,
            },
        )
        for market in normalized_markets
    ]


def batch_summary(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(
            DataIngestionBatch.status,
            func.count(DataIngestionBatch.id),
            func.coalesce(func.sum(DataIngestionBatch.requested), 0),
            func.coalesce(func.sum(DataIngestionBatch.processed), 0),
            func.coalesce(func.sum(DataIngestionBatch.inserted), 0),
            func.coalesce(func.sum(DataIngestionBatch.updated), 0),
            func.coalesce(func.sum(DataIngestionBatch.failed), 0),
        )
        .where(DataIngestionBatch.job_name == "market_data")
        .group_by(DataIngestionBatch.status)
    ).all()
    latest = session.scalars(
        select(DataIngestionBatch)
        .where(DataIngestionBatch.job_name == "market_data")
        .order_by(desc(DataIngestionBatch.started_at), desc(DataIngestionBatch.id))
        .limit(5)
    ).all()
    return {
        "by_status": [
            {
                "status": status,
                "batches": int(count or 0),
                "requested": int(requested or 0),
                "processed": int(processed or 0),
                "inserted": int(inserted or 0),
                "updated": int(updated or 0),
                "failed": int(failed or 0),
            }
            for status, count, requested, processed, inserted, updated, failed in rows
        ],
        "latest": [_batch_payload(row) for row in latest],
    }


def source_summary(session: Session) -> dict[str, Any]:
    bar_sources = session.execute(
        select(DailyBar.source, func.count(DailyBar.id), func.min(DailyBar.trade_date), func.max(DailyBar.trade_date))
        .group_by(DailyBar.source)
        .order_by(DailyBar.source)
    ).all()
    latest_runs = session.scalars(
        select(DataSourceRun).where(DataSourceRun.job_name == "market_data").order_by(desc(DataSourceRun.started_at), desc(DataSourceRun.id)).limit(5)
    ).all()
    return {
        "daily_bar_sources": [
            {
                "source": source,
                "rows": int(rows or 0),
                "first_trade_date": first_date.isoformat() if first_date else None,
                "latest_trade_date": latest_date.isoformat() if latest_date else None,
            }
            for source, rows, first_date, latest_date in bar_sources
        ],
        "latest_runs": [
            {
                "requested_source": row.requested_source,
                "effective_source": row.effective_source,
                "markets": row.markets,
                "status": row.status,
                "rows_inserted": row.rows_inserted,
                "rows_updated": row.rows_updated,
                "rows_total": row.rows_total,
                "error": row.error,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in latest_runs
        ],
    }


def build_backfill_manifest(
    session: Session,
    *,
    status: str,
    markets: tuple[str, ...],
    source: str,
    periods: int,
    complete_bars: int,
    totals: dict[str, Any] | None = None,
    attempts: dict[str, int] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    last_batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_database_url = canonical_database_url()
    database_path = sqlite_database_path(resolved_database_url)
    attempts = attempts or {}
    return {
        "status": status,
        "started_at": started_at,
        "updated_at": utc_iso(),
        "finished_at": finished_at,
        "database": {
            "url": resolved_database_url,
            "path": str(database_path) if database_path else None,
        },
        "markets": list(markets),
        "source": source,
        "periods": periods,
        "complete_bars": complete_bars,
        "coverage": market_data_coverage(session, markets=markets, complete_bars=complete_bars),
        "batches": batch_summary(session),
        "tasks": task_summary(session),
        "data_sources": source_summary(session),
        "totals": totals or {},
        "last_batch": last_batch,
        "resume": {
            "attempted_symbols": len(attempts),
            "attempts": dict(sorted(attempts.items())),
        },
    }


def task_summary(session: Session) -> dict[str, Any]:
    ensure_ingestion_task_runtime_columns(session)
    status_rows = session.execute(
        select(
            DataIngestionTask.status,
            func.count(DataIngestionTask.id),
            func.coalesce(func.sum(DataIngestionTask.requested), 0),
            func.coalesce(func.sum(DataIngestionTask.processed), 0),
            func.coalesce(func.sum(DataIngestionTask.failed), 0),
        ).group_by(DataIngestionTask.status)
    ).all()
    latest = session.execute(
        select(
            DataIngestionTask.id,
            DataIngestionTask.task_key,
            DataIngestionTask.task_type,
            DataIngestionTask.market,
            DataIngestionTask.board,
            DataIngestionTask.stock_code,
            DataIngestionTask.source,
            DataIngestionTask.status,
            DataIngestionTask.requested,
            DataIngestionTask.processed,
            DataIngestionTask.failed,
            DataIngestionTask.error,
            DataIngestionTask.created_at,
            DataIngestionTask.started_at,
            DataIngestionTask.finished_at,
        )
        .order_by(desc(DataIngestionTask.created_at), desc(DataIngestionTask.id))
        .limit(20)
    ).all()
    runtime_by_id = _task_runtime_rows(session, [int(row.id) for row in latest])
    return {
        "by_status": [
            {
                "status": status,
                "tasks": int(count or 0),
                "requested": int(requested or 0),
                "processed": int(processed or 0),
                "failed": int(failed or 0),
            }
            for status, count, requested, processed, failed in status_rows
        ],
        "latest": [_task_payload(row, runtime_by_id.get(int(row.id), {})) for row in latest],
    }


def _batch_payload(row: DataIngestionBatch) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_key": row.batch_key,
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


def _task_runtime_rows(session: Session, task_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not task_ids:
        return {}
    placeholders = ", ".join(f":task_id_{index}" for index, _ in enumerate(task_ids))
    params = {f"task_id_{index}": task_id for index, task_id in enumerate(task_ids)}
    rows = session.execute(
        text(
            f"""
            SELECT id, worker_id, heartbeat_at, lease_expires_at, progress, last_error, last_stock
            FROM data_ingestion_task
            WHERE id IN ({placeholders})
            """
        ),
        params,
    ).mappings()
    return {int(row["id"]): dict(row) for row in rows}


def _task_payload(row, runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_key": row.task_key,
        "task_type": row.task_type,
        "market": row.market,
        "board": row.board,
        "stock_code": row.stock_code,
        "source": row.source,
        "status": row.status,
        "requested": row.requested,
        "processed": row.processed,
        "failed": row.failed,
        "error": row.error,
        "worker_id": runtime.get("worker_id"),
        "heartbeat_at": _manifest_datetime(runtime.get("heartbeat_at")),
        "lease_expires_at": _manifest_datetime(runtime.get("lease_expires_at")),
        "progress": float(runtime.get("progress") or 0.0),
        "last_error": runtime.get("last_error") or "",
        "last_stock": runtime.get("last_stock"),
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _manifest_datetime(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
