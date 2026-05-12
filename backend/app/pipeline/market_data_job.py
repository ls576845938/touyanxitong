from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.data_sources.market_classifier import normalize_markets
from app.data_sources.provider import get_market_data_client
from app.data_sources.source_quality import source_confidence, source_kind
from app.db.models import DailyBar, DataIngestionBatch, Stock, utcnow
from app.pipeline.data_run import record_data_run


def run_market_data_job(
    session: Session,
    end_date: date | None = None,
    markets: tuple[str, ...] | None = None,
    max_stocks_per_market: int | None = None,
    stock_codes: tuple[str, ...] | None = None,
    periods: int | None = None,
    batch_offset: int = 0,
    client=None,
) -> dict[str, object]:
    requested_markets = normalize_markets(markets, settings.enabled_markets)
    requested_codes = {code.strip().upper() for code in stock_codes or () if code.strip()}
    batch_limit = settings.max_stocks_per_market if max_stocks_per_market is None else max_stocks_per_market
    bar_periods = periods or settings.market_data_periods
    client = client or get_market_data_client()
    started_at = datetime.now(timezone.utc)
    query = select(Stock).where(
        Stock.is_active.is_(True),
        Stock.listing_status == "listed",
        Stock.asset_type == "equity",
        Stock.is_etf.is_(False),
        Stock.market.in_(requested_markets),
    )
    if requested_codes:
        query = query.where(Stock.code.in_(requested_codes))
    if "US" in requested_markets:
        query = query.where(or_(Stock.market != "US", and_(*_supported_us_code_filters())))
    stocks = session.scalars(query.order_by(Stock.market, desc(Stock.float_market_cap), Stock.code)).all()
    selected_stocks = _limit_stocks_by_market(list(stocks), batch_limit, batch_offset)
    batch_row = _start_batch(
        session,
        source=str(getattr(client, "source", settings.market_data_source)),
        markets=requested_markets,
        offset=batch_offset,
        requested=len(selected_stocks),
        periods=bar_periods,
    )
    inserted = 0
    updated = 0
    missing = 0
    failed_symbols: list[dict[str, str]] = []
    processed_symbols: list[str] = []
    observed_sources: set[str] = set()
    try:
        for stock in selected_stocks:
            processed_symbols.append(stock.code)
            try:
                rows = client.fetch_daily_bars(stock.code, market=stock.market, end_date=end_date, periods=bar_periods)
            except Exception as exc:
                missing += 1
                failed_symbols.append({"code": stock.code, "market": stock.market, "error": str(exc)})
                logger.warning("market data fetch failed for {}: {}", stock.code, exc)
                continue
            if not rows:
                missing += 1
                failed_symbols.append({"code": stock.code, "market": stock.market, "error": "no_usable_bars"})
                continue
            for item in _dedupe_bar_rows(rows):
                observed_sources.add(str(item["source"]))
                existed = _daily_bar_exists(session, item)
                _upsert_daily_bar(session, item)
                if existed:
                    updated += 1
                else:
                    inserted += 1
        session.commit()
        batch_status = _batch_status(len(selected_stocks), inserted, updated, missing)
        batch_error = _batch_error(batch_status, len(selected_stocks), missing, failed_symbols)
        record_data_run(
            session,
            job_name="market_data",
            effective_source=",".join(sorted(observed_sources)) if observed_sources else str(getattr(client, "last_effective_source", client.source)),
            markets=requested_markets,
            status=batch_status,
            rows_inserted=inserted,
            rows_updated=updated,
            rows_total=inserted + updated,
            error=batch_error,
            started_at=started_at,
        )
        _finish_batch(session, batch_row, batch_status, len(selected_stocks), inserted, updated, missing, batch_error)
    except Exception as exc:
        session.rollback()
        record_data_run(
            session,
            job_name="market_data",
            effective_source=client.source,
            markets=requested_markets,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        _finish_batch(session, batch_row, "failed", 0, inserted, updated, missing, str(exc))
        raise
    skipped_by_limit = max(len(stocks) - batch_offset - len(selected_stocks), 0)
    logger.info(
        "market data updated: inserted={}, updated={}, stocks_without_bars={}, stocks_processed={}, skipped_by_limit={}",
        inserted,
        updated,
        missing,
        len(selected_stocks),
        skipped_by_limit,
    )
    return {
        "inserted": inserted,
        "updated": updated,
        "missing_stocks": missing,
        "stocks_requested": len(stocks),
        "stocks_processed": len(selected_stocks),
        "skipped_by_limit": skipped_by_limit,
        "batch_offset": batch_offset,
        "batch_id": batch_row.id,
        "periods": bar_periods,
        "status": batch_row.status,
        "processed_symbols": processed_symbols,
        "failed_symbols": failed_symbols,
    }


def _limit_stocks_by_market(stocks: list[Stock], max_stocks_per_market: int, batch_offset: int = 0) -> list[Stock]:
    if max_stocks_per_market <= 0:
        return stocks[batch_offset:]
    counts: dict[str, int] = {}
    skipped: dict[str, int] = {}
    selected: list[Stock] = []
    for stock in stocks:
        skipped_count = skipped.get(stock.market, 0)
        if skipped_count < batch_offset:
            skipped[stock.market] = skipped_count + 1
            continue
        count = counts.get(stock.market, 0)
        if count >= max_stocks_per_market:
            continue
        selected.append(stock)
        counts[stock.market] = count + 1
    return selected


def _supported_us_code_filters() -> list[object]:
    filters: list[object] = [
        ~Stock.code.like("%.%"),
        ~Stock.code.like("%\\_%", escape="\\"),
    ]
    filters.extend(~Stock.code.like(f"%{digit}%") for digit in "0123456789")
    filters.extend(
        [
            or_(Stock.market_cap > 0, ~Stock.code.like("%R")),
            or_(Stock.market_cap > 0, ~Stock.code.like("%W")),
            or_(Stock.market_cap > 0, ~Stock.code.like("%U")),
            ~Stock.code.like("%WI"),
            ~Stock.code.like("%WS"),
            ~Stock.code.like("%WT"),
        ]
    )
    for token in (
        "ETF",
        "ETN",
        "Fund",
        "Warrant",
        "Wts",
        "Wt",
        "Right",
        "Rt",
        "Unit",
        "Uni",
        "Preferred",
        "Note",
        "Bond",
        "Leverage",
        "Leveraged",
        "Daily",
        "YieldMax",
        "GraniteShares",
        "Direxion",
        "T-Rex",
        "Roundhill",
        "二倍",
        "三倍",
        "做多",
        "做空",
        "期权收益",
        "收益策略",
        "基金",
    ):
        filters.append(~Stock.name.ilike(f"%{token}%"))
    return filters


def _dedupe_bar_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed: dict[tuple[str, date, str], dict[str, Any]] = {}
    for item in rows:
        key = (str(item["stock_code"]), item["trade_date"], str(item["source"]))
        keyed[key] = item
    return list(keyed.values())


def _daily_bar_exists(session: Session, item: dict[str, Any]) -> bool:
    return (
        session.scalar(
            select(DailyBar.id).where(
                DailyBar.stock_code == item["stock_code"],
                DailyBar.trade_date == item["trade_date"],
                DailyBar.source == item["source"],
            )
        )
        is not None
    )


def _upsert_daily_bar(session: Session, item: dict[str, Any]) -> None:
    values = {
        "stock_code": item["stock_code"],
        "trade_date": item["trade_date"],
        "open": item["open"],
        "high": item["high"],
        "low": item["low"],
        "close": item["close"],
        "pre_close": item["pre_close"],
        "volume": item["volume"],
        "amount": item["amount"],
        "pct_chg": item["pct_chg"],
        "adj_factor": item["adj_factor"],
        "source": item["source"],
        "source_kind": item.get("source_kind") or source_kind(str(item.get("source"))),
        "source_confidence": float(item.get("source_confidence") or source_confidence(str(item.get("source")))),
    }
    if session.get_bind().dialect.name == "sqlite":
        update_values = {
            key: values[key]
            for key in ("open", "high", "low", "close", "pre_close", "volume", "amount", "pct_chg", "adj_factor", "source_kind", "source_confidence")
        }
        statement = (
            sqlite_insert(DailyBar)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["stock_code", "trade_date", "source"],
                set_=update_values,
            )
        )
        session.execute(statement)
        return

    existing = session.scalar(
        select(DailyBar).where(
            DailyBar.stock_code == item["stock_code"],
            DailyBar.trade_date == item["trade_date"],
            DailyBar.source == item["source"],
        )
    )
    if existing is None:
        session.add(DailyBar(**values))
        session.flush()
    else:
        for key, value in values.items():
            if key not in {"stock_code", "trade_date", "source"}:
                setattr(existing, key, value)


def _start_batch(
    session: Session,
    *,
    source: str,
    markets: tuple[str, ...],
    offset: int,
    requested: int,
    periods: int,
) -> DataIngestionBatch:
    market_key = ",".join(markets)
    key = f"market_data:{market_key}:offset={offset}:limit={requested}:periods={periods}:{utcnow().strftime('%Y%m%d%H%M%S%f')}"
    row = DataIngestionBatch(
        batch_key=key,
        job_name="market_data",
        market=market_key or "ALL",
        board="all",
        source=source,
        status="running",
        offset=offset,
        requested=requested,
        started_at=utcnow(),
    )
    session.add(row)
    session.commit()
    return row


def _finish_batch(
    session: Session,
    row: DataIngestionBatch,
    status: str,
    processed: int,
    inserted: int,
    updated: int,
    failed: int,
    error: str = "",
) -> None:
    row.status = status
    row.processed = processed
    row.inserted = inserted
    row.updated = updated
    row.failed = failed
    row.error = error
    row.finished_at = utcnow()
    session.add(row)
    session.commit()


def _batch_status(processed: int, inserted: int, updated: int, failed: int) -> str:
    usable_rows = inserted + updated
    if processed <= 0:
        return "success"
    if failed >= processed and usable_rows == 0:
        return "failed"
    if failed > 0:
        return "partial"
    return "success"


def _batch_error(status: str, processed: int, failed: int, failed_symbols: list[dict[str, str]] | None = None) -> str:
    detail = _failed_symbol_summary(failed_symbols or [])
    if status == "failed":
        message = "provider returned no usable bars for selected stocks"
        return f"{message}; {detail}" if detail else message
    if status == "partial":
        message = f"provider returned no usable bars for {failed} of {processed} selected stocks"
        return f"{message}; {detail}" if detail else message
    return ""


def _failed_symbol_summary(failed_symbols: list[dict[str, str]]) -> str:
    if not failed_symbols:
        return ""
    preview_limit = 50
    preview = ", ".join(f"{item.get('code', '')}:{item.get('error', '')}" for item in failed_symbols[:preview_limit])
    suffix = f"; +{len(failed_symbols) - preview_limit} more" if len(failed_symbols) > preview_limit else ""
    return f"failed_symbols=[{preview}{suffix}]"
