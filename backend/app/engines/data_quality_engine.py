from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class StockDataProfile:
    code: str
    name: str
    market: str
    board: str
    bars: list[Any]
    unusable_reason: str | None = None


def assess_market_data_quality(
    profiles: list[StockDataProfile],
    *,
    min_required_bars: int = 60,
    preferred_bars: int = 250,
) -> dict[str, Any]:
    """Assess whether current OHLCV data is usable for full-market research."""

    segment_latest: dict[tuple[str, str], date | None] = {}
    for profile in profiles:
        key = (profile.market, profile.board)
        latest = _latest_date(profile.bars)
        current = segment_latest.get(key)
        if latest and (current is None or latest > current):
            segment_latest[key] = latest

    issues: list[dict[str, Any]] = []
    segment_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(_empty_segment)

    for profile in profiles:
        key = (profile.market, profile.board)
        stats = segment_stats[key]
        stats["market"] = profile.market
        stats["board"] = profile.board
        stats["stock_count"] += 1

        ordered = sorted(profile.bars, key=lambda row: _value(row, "trade_date"))
        bars_count = len(ordered)
        latest = _latest_date(ordered)
        source_count = len({str(_value(row, "source", "unknown")) for row in ordered}) if ordered else 0
        source_kinds = [_row_source_kind(row) for row in ordered]
        real_bars_count = sum(1 for kind in source_kinds if kind == "real")
        bad_ohlc_count = sum(1 for row in ordered if _bad_ohlc(row))
        zero_liquidity_count = sum(1 for row in ordered if _number(_value(row, "volume", 0)) <= 0 or _number(_value(row, "amount", 0)) <= 0)

        if bars_count > 0:
            stats["stocks_with_bars"] += 1
        if real_bars_count > 0:
            stats["stocks_with_real_bars"] += 1
        for kind in set(source_kinds):
            stats["stocks_by_source_kind"][kind] += 1
        for kind in source_kinds:
            stats["bars_by_source_kind"][kind] += 1
        if bars_count >= min_required_bars:
            stats["stocks_with_required_history"] += 1
        if bars_count >= preferred_bars:
            stats["stocks_with_preferred_history"] += 1
        stats["bar_count_total"] += bars_count
        stats["latest_trade_date"] = _max_date(stats["latest_trade_date"], latest)

        stock_ref = {
            "code": profile.code,
            "name": profile.name,
            "market": profile.market,
            "board": profile.board,
            "bars_count": bars_count,
            "latest_trade_date": latest.isoformat() if latest else None,
            "source_kinds": sorted(set(source_kinds)),
            "real_bars_count": real_bars_count,
        }
        if bars_count == 0:
            if profile.unusable_reason:
                issues.append(
                    {
                        **stock_ref,
                        "severity": "WARN",
                        "issue_type": "provider_unusable",
                        "message": f"Provider 已返回不可用结果：{profile.unusable_reason}。该标的暂不重复污染抓取队列。",
                    }
                )
            else:
                issues.append({**stock_ref, "severity": "FAIL", "issue_type": "no_bars", "message": "没有可用日线，不能进入趋势和评分计算。"})
        elif bars_count < min_required_bars:
            issues.append(
                {
                    **stock_ref,
                    "severity": "FAIL",
                    "issue_type": "insufficient_history",
                    "message": f"历史K线少于 {min_required_bars} 根，趋势指标不可信。",
                }
            )
        elif bars_count < preferred_bars:
            issues.append(
                {
                    **stock_ref,
                    "severity": "WARN",
                    "issue_type": "short_history",
                    "message": f"历史K线少于 {preferred_bars} 根，250日新高和长期相对强度需要谨慎。",
                }
            )
        if bars_count > 0 and real_bars_count == 0:
            issues.append(
                {
                    **stock_ref,
                    "severity": "FAIL",
                    "issue_type": "non_real_bars",
                    "message": "当前日线全部来自 mock/fallback/unknown，不能作为正式研究数据。",
                }
            )

        segment_max_date = segment_latest.get(key)
        if latest and segment_max_date and latest < segment_max_date:
            issues.append(
                {
                    **stock_ref,
                    "severity": "WARN",
                    "issue_type": "stale_bars",
                    "message": f"最新K线早于同板块最新日期 {segment_max_date.isoformat()}，可能存在停牌、缺失或数据延迟。",
                }
            )
        if source_count > 1:
            issues.append(
                {
                    **stock_ref,
                    "severity": "WARN",
                    "issue_type": "mixed_sources",
                    "message": "同一股票存在多个行情 source，计算前必须确认使用同一数据源口径。",
                }
            )
        if bad_ohlc_count:
            issues.append(
                {
                    **stock_ref,
                    "severity": "FAIL",
                    "issue_type": "bad_ohlc",
                    "message": f"发现 {bad_ohlc_count} 根 OHLC 异常K线。",
                }
            )
        if zero_liquidity_count:
            issues.append(
                {
                    **stock_ref,
                    "severity": "WARN",
                    "issue_type": "zero_liquidity",
                    "message": f"发现 {zero_liquidity_count} 根成交量或成交额为零的K线。",
                }
            )

    segments = []
    for (market, board), stats in sorted(segment_stats.items()):
        stock_count = int(stats["stock_count"])
        coverage_ratio = stats["stocks_with_bars"] / stock_count if stock_count else 0.0
        real_coverage_ratio = stats["stocks_with_real_bars"] / stock_count if stock_count else 0.0
        required_ratio = stats["stocks_with_required_history"] / stock_count if stock_count else 0.0
        preferred_ratio = stats["stocks_with_preferred_history"] / stock_count if stock_count else 0.0
        status = "PASS"
        if coverage_ratio < 0.95 or required_ratio < 0.95 or real_coverage_ratio < 0.95:
            status = "FAIL"
        elif coverage_ratio < 1.0 or preferred_ratio < 0.8:
            status = "WARN"
        segments.append(
            {
                "market": market,
                "board": board,
                "status": status,
                "stock_count": stock_count,
                "stocks_with_bars": int(stats["stocks_with_bars"]),
                "stocks_with_real_bars": int(stats["stocks_with_real_bars"]),
                "stocks_with_required_history": int(stats["stocks_with_required_history"]),
                "stocks_with_preferred_history": int(stats["stocks_with_preferred_history"]),
                "coverage_ratio": round(coverage_ratio, 4),
                "real_coverage_ratio": round(real_coverage_ratio, 4),
                "required_history_ratio": round(required_ratio, 4),
                "preferred_history_ratio": round(preferred_ratio, 4),
                "avg_bars": round(stats["bar_count_total"] / stock_count, 1) if stock_count else 0,
                "latest_trade_date": stats["latest_trade_date"].isoformat() if stats["latest_trade_date"] else None,
                "source_kind_coverage": {
                    kind: {
                        "stocks_with_bars": int(count),
                        "coverage_ratio": round(int(count) / stock_count, 4) if stock_count else 0.0,
                        "bars_count": int(stats["bars_by_source_kind"].get(kind, 0)),
                    }
                    for kind, count in sorted(stats["stocks_by_source_kind"].items())
                },
            }
        )

    fail_count = sum(1 for item in issues if item["severity"] == "FAIL")
    warn_count = sum(1 for item in issues if item["severity"] == "WARN")
    status = "FAIL" if fail_count else "WARN" if warn_count else "PASS"
    return {
        "status": status,
        "summary": {
            "stock_count": len(profiles),
            "issue_count": len(issues),
            "fail_count": fail_count,
            "warn_count": warn_count,
            "min_required_bars": min_required_bars,
            "preferred_bars": preferred_bars,
            "stocks_with_real_bars": sum(int(item["stocks_with_real_bars"]) for item in segments),
        },
        "segments": segments,
        "issues": issues[:100],
    }


def _empty_segment() -> dict[str, Any]:
    return {
        "market": "",
        "board": "",
        "stock_count": 0,
        "stocks_with_bars": 0,
        "stocks_with_real_bars": 0,
        "stocks_with_required_history": 0,
        "stocks_with_preferred_history": 0,
        "bar_count_total": 0,
        "stocks_by_source_kind": defaultdict(int),
        "bars_by_source_kind": defaultdict(int),
        "latest_trade_date": None,
    }


def _latest_date(rows: list[Any]) -> date | None:
    dates = [_value(row, "trade_date", None) for row in rows]
    dates = [item for item in dates if item is not None]
    return max(dates) if dates else None


def _max_date(left: date | None, right: date | None) -> date | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _value(row: Any, field: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _number(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _bad_ohlc(row: Any) -> bool:
    open_price = _number(_value(row, "open", 0))
    high = _number(_value(row, "high", 0))
    low = _number(_value(row, "low", 0))
    close = _number(_value(row, "close", 0))
    return min(open_price, high, low, close) <= 0 or high < max(open_price, close) or low > min(open_price, close)


def _row_source_kind(row: Any) -> str:
    explicit = _value(row, "source_kind", None)
    if explicit:
        return str(explicit)
    source = str(_value(row, "source", "unknown")).lower()
    if source in {"akshare", "baostock", "databento", "eodhd", "fmp", "polygon", "tencent", "tiingo", "tushare", "twelvedata", "yahoo"}:
        return "real"
    if source == "mock":
        return "mock"
    if "fallback" in source:
        return "fallback"
    return "unknown"
