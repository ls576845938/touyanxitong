from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, Stock
from app.engines.universe_engine import TRUSTED_DATA_SOURCES, UniverseProfile, build_research_universe, eligible_codes


def research_universe_payload(session: Session, stocks: list[Stock] | None = None, target_date: date | None = None) -> dict[str, Any]:
    universe_stocks = stocks
    if universe_stocks is None:
        universe_stocks = session.scalars(select(Stock).order_by(Stock.market, Stock.board, Stock.code)).all()
    summaries = bar_summaries_by_stock(session, [stock.code for stock in universe_stocks], target_date)
    profiles = [
        UniverseProfile(
            code=stock.code,
            name=stock.name,
            market=stock.market,
            board=stock.board,
            is_active=stock.is_active,
            is_st=stock.is_st,
            market_cap=stock.market_cap,
            float_market_cap=stock.float_market_cap,
            bars=[],
            asset_type=stock.asset_type,
            listing_status=stock.listing_status,
            is_etf=stock.is_etf,
            source=stock.source,
            data_vendor=stock.data_vendor,
            bars_count_override=int(summaries.get(stock.code, {}).get("bars_count", 0) or 0),
            latest_trade_date_override=summaries.get(stock.code, {}).get("latest_trade_date"),
            latest_close_override=float(summaries.get(stock.code, {}).get("latest_close", 0.0) or 0.0),
            avg_amount_20d_override=float(summaries.get(stock.code, {}).get("avg_amount_20d", 0.0) or 0.0),
            avg_volume_20d_override=float(summaries.get(stock.code, {}).get("avg_volume_20d", 0.0) or 0.0),
            selected_bar_source_override=str(summaries.get(stock.code, {}).get("selected_bar_source", "unknown") or "unknown"),
            source_profile_override=summaries.get(stock.code, {}).get("source_profile", {"sources": [], "mixed_sources": False}),
        )
        for stock in universe_stocks
    ]
    return build_research_universe(profiles)


def eligible_stock_codes(session: Session, stocks: list[Stock] | None = None, target_date: date | None = None) -> set[str]:
    return eligible_codes(research_universe_payload(session, stocks=stocks, target_date=target_date))


def bar_summaries_by_stock(session: Session, stock_codes: list[str], target_date: date | None = None) -> dict[str, dict[str, Any]]:
    if not stock_codes:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(stock_codes, 800):
        source_stats = _source_stats(session, chunk, target_date)
        selected_sources: dict[str, str] = {}
        for stock_code, rows in source_stats.items():
            selected = max(rows, key=lambda item: (float(item["trust"]), int(item["bars_count"]), str(item["latest_trade_date"] or "")))
            selected_source = str(selected["source"])
            selected_sources[stock_code] = selected_source
            result[stock_code] = {
                "bars_count": int(selected["bars_count"]),
                "latest_trade_date": selected["latest_trade_date"],
                "latest_close": 0.0,
                "avg_amount_20d": 0.0,
                "avg_volume_20d": 0.0,
                "selected_bar_source": selected_source,
                "source_profile": {
                    "sources": [
                        {
                            "source": str(row["source"]),
                            "bars_count": int(row["bars_count"]),
                            "latest_trade_date": row["latest_trade_date"].isoformat() if isinstance(row["latest_trade_date"], date) else None,
                            "trust": round(float(row["trust"]), 2),
                        }
                        for row in sorted(rows, key=lambda item: str(item["source"]))
                    ],
                    "mixed_sources": len(rows) > 1,
                },
            }
        _fill_recent_bar_stats(session, chunk, selected_sources, result, target_date)
    return result


def _source_stats(session: Session, stock_codes: list[str], target_date: date | None) -> dict[str, list[dict[str, Any]]]:
    query = select(DailyBar.stock_code, DailyBar.source, func.count(DailyBar.id), func.max(DailyBar.trade_date)).where(DailyBar.stock_code.in_(stock_codes))
    if target_date is not None:
        query = query.where(DailyBar.trade_date <= target_date)
    rows = session.execute(query.group_by(DailyBar.stock_code, DailyBar.source)).all()
    result: dict[str, list[dict[str, Any]]] = {}
    for stock_code, source, count, latest_trade_date in rows:
        normalized_source = str(source or "unknown").lower()
        result.setdefault(str(stock_code), []).append(
            {
                "source": normalized_source,
                "bars_count": int(count or 0),
                "latest_trade_date": latest_trade_date,
                "trust": _source_trust(normalized_source),
            }
        )
    return result


def _fill_recent_bar_stats(
    session: Session,
    stock_codes: list[str],
    selected_sources: dict[str, str],
    result: dict[str, dict[str, Any]],
    target_date: date | None,
) -> None:
    if not selected_sources:
        return
    selected_source_values = sorted(set(selected_sources.values()))
    ranked = (
        select(
            DailyBar.stock_code.label("stock_code"),
            DailyBar.source.label("source"),
            DailyBar.trade_date.label("trade_date"),
            DailyBar.close.label("close"),
            DailyBar.amount.label("amount"),
            DailyBar.volume.label("volume"),
            func.row_number()
            .over(partition_by=(DailyBar.stock_code, DailyBar.source), order_by=DailyBar.trade_date.desc())
            .label("rn"),
        )
        .where(DailyBar.stock_code.in_(stock_codes), func.lower(DailyBar.source).in_(selected_source_values))
    )
    if target_date is not None:
        ranked = ranked.where(DailyBar.trade_date <= target_date)
    ranked_subquery = ranked.subquery()
    rows = session.execute(
        select(
            ranked_subquery.c.stock_code,
            ranked_subquery.c.source,
            ranked_subquery.c.trade_date,
            ranked_subquery.c.close,
            ranked_subquery.c.amount,
            ranked_subquery.c.volume,
        )
        .where(ranked_subquery.c.rn <= 20)
        .order_by(ranked_subquery.c.stock_code, ranked_subquery.c.trade_date.desc())
    ).all()

    recent_by_code: dict[str, list[Any]] = {}
    for stock_code, source, trade_date, close, amount, volume in rows:
        code = str(stock_code)
        if selected_sources.get(code) != str(source or "unknown").lower():
            continue
        recent_by_code.setdefault(code, []).append((trade_date, close, amount, volume))

    for stock_code, recent_rows in recent_by_code.items():
        ordered_desc = sorted(recent_rows, key=lambda item: item[0], reverse=True)
        latest = ordered_desc[0] if ordered_desc else None
        amounts = [_number(item[2]) for item in ordered_desc]
        volumes = [_number(item[3]) for item in ordered_desc]
        summary = result.setdefault(stock_code, {})
        if latest is not None:
            summary["latest_close"] = _number(latest[1])
        summary["avg_amount_20d"] = sum(amounts) / len(amounts) if amounts else 0.0
        summary["avg_volume_20d"] = sum(volumes) / len(volumes) if volumes else 0.0


def _source_trust(source: str | None) -> float:
    normalized = str(source or "").lower()
    if normalized in TRUSTED_DATA_SOURCES:
        return float(TRUSTED_DATA_SOURCES[normalized])
    tokens = [item.strip() for chunk in normalized.split(",") for item in chunk.split("+")]
    scores = []
    for token in tokens:
        token = token.removesuffix("_fallback")
        if token in TRUSTED_DATA_SOURCES:
            scores.append(float(TRUSTED_DATA_SOURCES[token]))
    return max(scores) if scores else 0.0


def _number(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def bars_by_stock(session: Session, stock_codes: list[str], target_date: date | None = None) -> dict[str, list[DailyBar]]:
    if not stock_codes:
        return {}
    query = select(DailyBar).where(DailyBar.stock_code.in_(stock_codes))
    if target_date is not None:
        query = query.where(DailyBar.trade_date <= target_date)
    rows = session.scalars(query.order_by(DailyBar.stock_code, DailyBar.trade_date)).all()
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.stock_code, []).append(row)
    return grouped
