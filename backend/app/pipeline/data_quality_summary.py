from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, Stock
from app.market_meta import board_label, market_label


def data_quality_payload(
    session: Session,
    stocks: list[Stock] | None = None,
    target_date: date | None = None,
    *,
    min_required_bars: int = 60,
    preferred_bars: int = 250,
) -> dict[str, Any]:
    """Fast aggregate data-quality payload for full-market API/report views."""

    active_stocks = stocks
    if active_stocks is None:
        active_stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.market, Stock.board, Stock.code)).all()
    stock_by_code = {stock.code: stock for stock in active_stocks}
    if not stock_by_code:
        return _empty_payload(min_required_bars, preferred_bars)

    codes = list(stock_by_code)
    bar_summary = _bar_summary(session, codes, target_date)
    source_kinds = _source_kind_summary(session, codes, target_date)
    segment_latest: dict[tuple[str, str], date | None] = {}
    for stock in active_stocks:
        key = (stock.market, stock.board)
        latest = bar_summary.get(stock.code, {}).get("latest_trade_date")
        current = segment_latest.get(key)
        if latest and (current is None or latest > current):
            segment_latest[key] = latest

    issues: list[dict[str, Any]] = []
    segment_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(_empty_segment)
    for stock in active_stocks:
        summary = bar_summary.get(stock.code, {})
        kinds = source_kinds.get(stock.code, {})
        bars_count = int(summary.get("bars_count", 0) or 0)
        real_bars_count = int(summary.get("real_bars_count", 0) or 0)
        latest = summary.get("latest_trade_date")
        source_count = int(summary.get("source_count", 0) or 0)
        bad_ohlc_count = int(summary.get("bad_ohlc_count", 0) or 0)
        zero_liquidity_count = int(summary.get("zero_liquidity_count", 0) or 0)

        key = (stock.market, stock.board)
        stats = segment_stats[key]
        stats["market"] = stock.market
        stats["board"] = stock.board
        stats["stock_count"] += 1
        if bars_count > 0:
            stats["stocks_with_bars"] += 1
        if real_bars_count > 0:
            stats["stocks_with_real_bars"] += 1
        if bars_count >= min_required_bars:
            stats["stocks_with_required_history"] += 1
        if bars_count >= preferred_bars:
            stats["stocks_with_preferred_history"] += 1
        stats["bar_count_total"] += bars_count
        stats["latest_trade_date"] = _max_date(stats["latest_trade_date"], latest)
        for kind, count in kinds.items():
            stats["stocks_by_source_kind"][kind] += 1
            stats["bars_by_source_kind"][kind] += count

        stock_ref = {
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "market_label": market_label(stock.market),
            "board": stock.board,
            "board_label": board_label(stock.board),
            "bars_count": bars_count,
            "latest_trade_date": latest.isoformat() if latest else None,
            "source_kinds": sorted(kinds),
            "real_bars_count": real_bars_count,
        }
        if bars_count == 0:
            issues.append(_issue_payload(stock_ref, "FAIL", "no_bars", "没有可用日线，不能进入趋势和评分计算。"))
        elif bars_count < min_required_bars:
            issues.append(
                _issue_payload(stock_ref, "FAIL", "insufficient_history", f"历史K线少于 {min_required_bars} 根，趋势指标不可信。")
            )
        elif bars_count < preferred_bars:
            issues.append(
                _issue_payload(stock_ref, "WARN", "short_history", f"历史K线少于 {preferred_bars} 根，250日新高和长期相对强度需要谨慎。")
            )
        if bars_count > 0 and real_bars_count == 0:
            issues.append(
                _issue_payload(stock_ref, "FAIL", "non_real_bars", "当前日线全部来自 mock/fallback/unknown，不能作为正式研究数据。")
            )
        segment_max_date = segment_latest.get(key)
        if latest and segment_max_date and latest < segment_max_date:
            issues.append(
                _issue_payload(stock_ref, "WARN", "stale_bars", f"最新K线早于同板块最新日期 {segment_max_date.isoformat()}，可能存在停牌、缺失或数据延迟。")
            )
        if source_count > 1:
            issues.append(_issue_payload(stock_ref, "WARN", "mixed_sources", "同一股票存在多个行情 source，计算前必须确认使用同一数据源口径。"))
        if bad_ohlc_count:
            issues.append(_issue_payload(stock_ref, "FAIL", "bad_ohlc", f"发现 {bad_ohlc_count} 根 OHLC 异常K线。"))
        if zero_liquidity_count:
            issues.append(_issue_payload(stock_ref, "WARN", "zero_liquidity", f"发现 {zero_liquidity_count} 根成交量或成交额为零的K线。"))

    segments = [_segment_payload(stats, min_required_bars, preferred_bars) for _, stats in sorted(segment_stats.items())]
    fail_count = sum(1 for item in issues if item["severity"] == "FAIL")
    warn_count = sum(1 for item in issues if item["severity"] == "WARN")
    return {
        "status": "FAIL" if fail_count else "WARN" if warn_count else "PASS",
        "summary": {
            "stock_count": len(active_stocks),
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


def _bar_summary(session: Session, stock_codes: list[str], target_date: date | None) -> dict[str, dict[str, Any]]:
    bad_ohlc = case(
        (
            or_(
                DailyBar.open <= 0,
                DailyBar.high <= 0,
                DailyBar.low <= 0,
                DailyBar.close <= 0,
                DailyBar.high < DailyBar.open,
                DailyBar.high < DailyBar.close,
                DailyBar.low > DailyBar.open,
                DailyBar.low > DailyBar.close,
            ),
            1,
        ),
        else_=0,
    )
    zero_liquidity = case((or_(DailyBar.volume <= 0, DailyBar.amount <= 0), 1), else_=0)
    real_bar = case((DailyBar.source_kind == "real", 1), else_=0)
    query = select(
        DailyBar.stock_code,
        func.count(DailyBar.id),
        func.max(DailyBar.trade_date),
        func.count(func.distinct(DailyBar.source)),
        func.sum(bad_ohlc),
        func.sum(zero_liquidity),
        func.sum(real_bar),
    ).where(DailyBar.stock_code.in_(stock_codes))
    if target_date is not None:
        query = query.where(DailyBar.trade_date <= target_date)
    rows = session.execute(query.group_by(DailyBar.stock_code)).all()
    return {
        str(code): {
            "bars_count": int(count or 0),
            "latest_trade_date": latest_trade_date,
            "source_count": int(source_count or 0),
            "bad_ohlc_count": int(bad_count or 0),
            "zero_liquidity_count": int(zero_count or 0),
            "real_bars_count": int(real_count or 0),
        }
        for code, count, latest_trade_date, source_count, bad_count, zero_count, real_count in rows
    }


def _source_kind_summary(session: Session, stock_codes: list[str], target_date: date | None) -> dict[str, dict[str, int]]:
    query = select(DailyBar.stock_code, DailyBar.source_kind, func.count(DailyBar.id)).where(DailyBar.stock_code.in_(stock_codes))
    if target_date is not None:
        query = query.where(DailyBar.trade_date <= target_date)
    rows = session.execute(query.group_by(DailyBar.stock_code, DailyBar.source_kind)).all()
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for stock_code, source_kind, count in rows:
        result[str(stock_code)][str(source_kind or "unknown")] = int(count or 0)
    return result


def _segment_payload(stats: dict[str, Any], min_required_bars: int, preferred_bars: int) -> dict[str, Any]:
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
    blocking_reasons = _segment_blocking_reasons(
        coverage_ratio=coverage_ratio,
        real_coverage_ratio=real_coverage_ratio,
        required_ratio=required_ratio,
        preferred_ratio=preferred_ratio,
    )
    return {
        "market": stats["market"],
        "market_label": market_label(stats["market"]),
        "board": stats["board"],
        "board_label": board_label(stats["board"]),
        "status": status,
        "formal_research_allowed": status != "FAIL",
        "backfill_priority": _segment_backfill_priority(status, stats["market"], stats["board"]),
        "recommended_action": _segment_recommended_action(status, stats["market"], stats["board"], blocking_reasons),
        "blocking_reasons": blocking_reasons,
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


def _empty_payload(min_required_bars: int, preferred_bars: int) -> dict[str, Any]:
    return {
        "status": "PASS",
        "summary": {
            "stock_count": 0,
            "issue_count": 0,
            "fail_count": 0,
            "warn_count": 0,
            "min_required_bars": min_required_bars,
            "preferred_bars": preferred_bars,
            "stocks_with_real_bars": 0,
        },
        "segments": [],
        "issues": [],
    }


def _issue_payload(stock_ref: dict[str, Any], severity: str, issue_type: str, message: str) -> dict[str, Any]:
    return {
        **stock_ref,
        "severity": severity,
        "issue_type": issue_type,
        "message": message,
        "remediation": _issue_remediation(stock_ref, issue_type),
    }


def _issue_remediation(stock_ref: dict[str, Any], issue_type: str) -> dict[str, Any]:
    market = str(stock_ref.get("market") or "").upper()
    board = str(stock_ref.get("board") or "all").lower()
    code = str(stock_ref.get("code") or "")
    if issue_type in {"no_bars", "insufficient_history", "short_history", "non_real_bars", "stale_bars"}:
        return {
            "action": "queue_backfill",
            "api": "/api/market/ingestion-tasks",
            "payload": {
                "task_type": "single",
                "market": market,
                "board": board,
                "stock_code": code,
                "periods": 320,
            },
        }
    if issue_type in {"bad_ohlc", "zero_liquidity", "mixed_sources"}:
        return {
            "action": "inspect_and_reingest",
            "api": "/api/market/ingestion-tasks",
            "payload": {
                "task_type": "single",
                "market": market,
                "board": board,
                "stock_code": code,
                "periods": 320,
            },
        }
    return {"action": "manual_review"}


def _segment_blocking_reasons(
    *,
    coverage_ratio: float,
    real_coverage_ratio: float,
    required_ratio: float,
    preferred_ratio: float,
) -> list[str]:
    reasons: list[str] = []
    if coverage_ratio < 0.95:
        reasons.append("日线覆盖率低于 95%")
    if real_coverage_ratio < 0.95:
        reasons.append("真实数据覆盖率低于 95%")
    if required_ratio < 0.95:
        reasons.append("满足最小历史长度的股票低于 95%")
    if preferred_ratio < 0.8:
        reasons.append("满足长期观察窗口的股票低于 80%")
    return reasons


def _segment_backfill_priority(status: str, market: str, board: str) -> str:
    if status == "PASS":
        return "low"
    if market == "US" or market == "HK" or (market == "A" and board == "bse"):
        return "high"
    return "medium" if status == "FAIL" else "low"


def _segment_recommended_action(status: str, market: str, board: str, blocking_reasons: list[str]) -> str:
    if status == "PASS":
        return "可进入正式研究，继续监控数据新鲜度。"
    target = f"{market_label(market)} / {board_label(board)}"
    reason = "；".join(blocking_reasons) if blocking_reasons else "存在数据质量缺口"
    return f"优先回填 {target}：{reason}。质量门为 FAIL 时，Agent 报告只能输出观察线索。"


def _max_date(left: date | None, right: date | None) -> date | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
