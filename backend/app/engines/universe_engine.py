from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class UniverseProfile:
    code: str
    name: str
    market: str
    board: str
    is_active: bool
    is_st: bool
    market_cap: float
    float_market_cap: float
    bars: list[Any]
    asset_type: str = "equity"
    listing_status: str = "listed"
    is_etf: bool = False
    source: str = "mock"
    data_vendor: str = "mock"
    bars_count_override: int | None = None
    latest_trade_date_override: date | None = None
    latest_close_override: float | None = None
    avg_amount_20d_override: float | None = None
    avg_volume_20d_override: float | None = None
    selected_bar_source_override: str | None = None
    source_profile_override: dict[str, Any] | None = None


DEFAULT_RULES: dict[str, dict[str, float | int]] = {
    "A": {"min_market_cap": 80, "min_float_market_cap": 50, "min_avg_amount_20d": 20_000_000, "min_history_bars": 120, "min_price": 3},
    "US": {"min_market_cap": 500, "min_float_market_cap": 0, "min_avg_amount_20d": 20_000_000, "min_history_bars": 120, "min_price": 5},
    "HK": {"min_market_cap": 100, "min_float_market_cap": 0, "min_avg_amount_20d": 10_000_000, "min_history_bars": 120, "min_price": 1},
}

TRUSTED_DATA_SOURCES: dict[str, float] = {
    "mock": 0.0,
    "polygon": 0.98,
    "tiingo": 0.97,
    "eodhd": 0.96,
    "tencent": 0.95,
    "baostock": 0.92,
    "akshare": 0.9,
    "tushare": 0.9,
    "yahoo": 0.82,
}


def build_research_universe(profiles: list[UniverseProfile]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        if profile.bars_count_override is not None:
            selected_source = profile.selected_bar_source_override or "unknown"
            source_profile = profile.source_profile_override or {"sources": [], "mixed_sources": False}
            bars_count = int(profile.bars_count_override or 0)
            latest = profile.latest_trade_date_override
            close = float(profile.latest_close_override or 0.0)
            avg_amount_20d = float(profile.avg_amount_20d_override or 0.0)
            avg_volume_20d = float(profile.avg_volume_20d_override or 0.0)
        else:
            selected_source, ordered, source_profile = _select_bars_for_universe(profile.bars)
            bars_count = len(ordered)
            latest = _value(ordered[-1], "trade_date") if ordered else None
            close = _number(_value(ordered[-1], "close", 0)) if ordered else 0.0
            recent_amounts = [_number(_value(row, "amount", 0)) for row in ordered[-20:]]
            recent_volumes = [_number(_value(row, "volume", 0)) for row in ordered[-20:]]
            avg_amount_20d = mean(recent_amounts) if recent_amounts else 0.0
            avg_volume_20d = mean(recent_volumes) if recent_volumes else 0.0
        rules = DEFAULT_RULES.get(profile.market, DEFAULT_RULES["A"])
        source_trust = _combined_source_trust(profile, selected_source)
        reasons = _exclusion_reasons(profile, bars_count, close, avg_amount_20d, rules, source_trust)
        rows.append(
            {
                "code": profile.code,
                "name": profile.name,
                "market": profile.market,
                "board": profile.board,
                "eligible": not reasons,
                "exclusion_reasons": reasons,
                "market_cap": profile.market_cap,
                "float_market_cap": profile.float_market_cap,
                "bars_count": bars_count,
                "latest_trade_date": latest.isoformat() if isinstance(latest, date) else None,
                "latest_close": round(close, 4),
                "avg_amount_20d": round(avg_amount_20d, 2),
                "avg_volume_20d": round(avg_volume_20d, 2),
                "selected_bar_source": selected_source,
                "source": profile.source,
                "data_vendor": profile.data_vendor,
                "data_source_trust": round(source_trust, 2),
                "source_profile": source_profile,
            }
        )
    return {
        "summary": _summary(rows),
        "segments": _segments(rows),
        "exclusion_summary": _exclusion_summary(rows),
        "rules": DEFAULT_RULES,
        "trusted_data_sources": TRUSTED_DATA_SOURCES,
        "rows": sorted(rows, key=lambda row: (not row["eligible"], row["market"], row["board"], -float(row["avg_amount_20d"]))),
    }


def eligible_codes(payload: dict[str, Any]) -> set[str]:
    return {str(row["code"]) for row in payload["rows"] if row["eligible"]}


def _exclusion_reasons(
    profile: UniverseProfile,
    bars_count: int,
    latest_close: float,
    avg_amount_20d: float,
    rules: dict[str, float | int],
    source_trust: float,
) -> list[str]:
    reasons: list[str] = []
    if source_trust <= 0:
        reasons.append("untrusted_data_source")
    if not profile.is_active:
        reasons.append("inactive")
    if profile.listing_status != "listed":
        reasons.append("not_listed")
    if profile.asset_type != "equity":
        reasons.append("not_equity")
    if profile.is_etf:
        reasons.append("etf_excluded")
    if profile.is_st:
        reasons.append("st_or_special_treatment")
    if bars_count < int(rules["min_history_bars"]):
        reasons.append("insufficient_history")
    if profile.market_cap < float(rules["min_market_cap"]):
        reasons.append("market_cap_too_small")
    if profile.float_market_cap < float(rules["min_float_market_cap"]):
        reasons.append("float_market_cap_too_small")
    if avg_amount_20d < float(rules["min_avg_amount_20d"]):
        reasons.append("liquidity_too_low")
    if latest_close < float(rules["min_price"]):
        reasons.append("price_too_low")
    return reasons


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    eligible = sum(1 for row in rows if row["eligible"])
    return {
        "stock_count": total,
        "eligible_count": eligible,
        "excluded_count": total - eligible,
        "eligible_ratio": round(eligible / total, 4) if total else 0,
    }


def _segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    return sorted(result, key=lambda item: (item["market"], item["board"]))


def _exclusion_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for reason in row["exclusion_reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _select_bars_for_universe(bars: list[Any]) -> tuple[str, list[Any], dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for row in bars:
        source = str(_value(row, "source", "unknown") or "unknown").lower()
        grouped.setdefault(source, []).append(row)
    source_rows: list[dict[str, Any]] = []
    for source, items in grouped.items():
        ordered = sorted(items, key=lambda row: _value(row, "trade_date"))
        latest = _value(ordered[-1], "trade_date") if ordered else None
        source_rows.append(
            {
                "source": source,
                "bars_count": len(ordered),
                "latest_trade_date": latest.isoformat() if isinstance(latest, date) else None,
                "trust": round(_source_trust(source), 2),
            }
        )
    if not source_rows:
        return "unknown", [], {"sources": [], "mixed_sources": False}
    selected = max(source_rows, key=lambda item: (float(item["trust"]), int(item["bars_count"]), str(item["latest_trade_date"] or "")))
    selected_source = str(selected["source"])
    ordered = sorted(grouped[selected_source], key=lambda row: _value(row, "trade_date"))
    return selected_source, ordered, {"sources": sorted(source_rows, key=lambda item: item["source"]), "mixed_sources": len(source_rows) > 1}


def _combined_source_trust(profile: UniverseProfile, selected_bar_source: str) -> float:
    return _source_trust(selected_bar_source)


def _source_trust(source: str | None) -> float:
    normalized = str(source or "").lower()
    if normalized in TRUSTED_DATA_SOURCES:
        return TRUSTED_DATA_SOURCES[normalized]
    tokens = [item.strip() for chunk in normalized.split(",") for item in chunk.split("+")]
    scores = []
    for token in tokens:
        token = token.removesuffix("_fallback")
        if token in TRUSTED_DATA_SOURCES:
            scores.append(TRUSTED_DATA_SOURCES[token])
    return max(scores) if scores else 0.0


def _value(row: Any, field: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _number(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
