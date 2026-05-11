from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any


@dataclass(frozen=True)
class BacktestObservation:
    stock_code: str
    signal_date: date
    entry_date: date
    exit_date: date
    rating: str
    confidence_level: str
    final_score: float
    forward_return: float
    max_forward_return: float


@dataclass(frozen=True)
class SignalBacktestResult:
    as_of_date: date
    horizon_days: int
    min_score: float
    market: str
    board: str
    status: str
    sample_count: int
    average_forward_return: float
    median_forward_return: float
    average_max_return: float
    hit_rate_2x: float
    hit_rate_5x: float
    hit_rate_10x: float
    bucket_summary: list[dict[str, Any]]
    rating_summary: list[dict[str, Any]]
    confidence_summary: list[dict[str, Any]]
    failures: list[str]
    explanation: str


def run_signal_backtest(
    *,
    score_rows: list[Any],
    bars_by_stock: dict[str, list[Any]],
    as_of_date: date,
    horizon_days: int = 120,
    min_score: float = 0.0,
    market: str = "ALL",
    board: str = "all",
) -> SignalBacktestResult:
    observations: list[BacktestObservation] = []
    failures: list[str] = []
    for score in score_rows:
        final_score = _number(_field(score, "final_score", 0.0))
        if final_score < min_score:
            continue
        signal_date = _field(score, "trade_date")
        if signal_date is None or signal_date >= as_of_date:
            continue
        bars = sorted(bars_by_stock.get(str(_field(score, "stock_code")), []), key=lambda row: _field(row, "trade_date"))
        observation = _observation(score, bars, horizon_days)
        if observation is None:
            failures.append(f"{_field(score, 'stock_code')}: forward bars insufficient")
            continue
        observations.append(observation)

    forward_returns = [row.forward_return for row in observations]
    max_returns = [row.max_forward_return for row in observations]
    sample_count = len(observations)
    status = "success" if sample_count else "empty"
    explanation = (
        f"使用信号日后下一根K线作为入场，向后观察{horizon_days}个交易日；"
        f"样本{sample_count}个。该回测只用于信号校准，不代表可交易收益。"
    )
    if failures:
        explanation += f" 有{len(failures)}个样本因未来K线不足被跳过。"
    return SignalBacktestResult(
        as_of_date=as_of_date,
        horizon_days=horizon_days,
        min_score=min_score,
        market=market,
        board=board,
        status=status,
        sample_count=sample_count,
        average_forward_return=round(sum(forward_returns) / sample_count, 6) if sample_count else 0.0,
        median_forward_return=round(float(median(forward_returns)), 6) if sample_count else 0.0,
        average_max_return=round(sum(max_returns) / sample_count, 6) if sample_count else 0.0,
        hit_rate_2x=_hit_rate(max_returns, 1.0),
        hit_rate_5x=_hit_rate(max_returns, 4.0),
        hit_rate_10x=_hit_rate(max_returns, 9.0),
        bucket_summary=_group_summary(observations, key_fn=lambda row: _score_bucket(row.final_score)),
        rating_summary=_group_summary(observations, key_fn=lambda row: row.rating or "unknown"),
        confidence_summary=_group_summary(observations, key_fn=lambda row: row.confidence_level or "unknown"),
        failures=failures[:100],
        explanation=explanation,
    )


def backtest_to_payload(result: Any) -> dict[str, Any]:
    return {
        "as_of_date": _date_text(_field(result, "as_of_date")),
        "horizon_days": int(_number(_field(result, "horizon_days", 0))),
        "min_score": _number(_field(result, "min_score", 0.0)),
        "market": _field(result, "market", "ALL"),
        "board": _field(result, "board", "all"),
        "status": _field(result, "status", "unknown"),
        "sample_count": int(_number(_field(result, "sample_count", 0))),
        "average_forward_return": _number(_field(result, "average_forward_return", 0.0)),
        "median_forward_return": _number(_field(result, "median_forward_return", 0.0)),
        "average_max_return": _number(_field(result, "average_max_return", 0.0)),
        "hit_rate_2x": _number(_field(result, "hit_rate_2x", 0.0)),
        "hit_rate_5x": _number(_field(result, "hit_rate_5x", 0.0)),
        "hit_rate_10x": _number(_field(result, "hit_rate_10x", 0.0)),
        "bucket_summary": _json_list(_field(result, "bucket_summary", [])),
        "rating_summary": _json_list(_field(result, "rating_summary", [])),
        "confidence_summary": _json_list(_field(result, "confidence_summary", [])),
        "failures": _json_list(_field(result, "failures", [])),
        "explanation": _field(result, "explanation", ""),
    }


def _observation(score: Any, bars: list[Any], horizon_days: int) -> BacktestObservation | None:
    signal_date = _field(score, "trade_date")
    entry_index = None
    for index, bar in enumerate(bars):
        if _field(bar, "trade_date") > signal_date:
            entry_index = index
            break
    if entry_index is None:
        return None
    exit_index = entry_index + horizon_days
    if exit_index >= len(bars):
        return None
    entry_bar = bars[entry_index]
    future_bars = bars[entry_index : exit_index + 1]
    exit_bar = future_bars[-1]
    entry_close = _number(_field(entry_bar, "close", 0.0))
    exit_close = _number(_field(exit_bar, "close", 0.0))
    if entry_close <= 0 or exit_close <= 0:
        return None
    max_close = max(_number(_field(row, "close", 0.0)) for row in future_bars)
    return BacktestObservation(
        stock_code=str(_field(score, "stock_code")),
        signal_date=signal_date,
        entry_date=_field(entry_bar, "trade_date"),
        exit_date=_field(exit_bar, "trade_date"),
        rating=str(_field(score, "rating", "unknown")),
        confidence_level=str(_field(score, "confidence_level", "unknown")),
        final_score=_number(_field(score, "final_score", 0.0)),
        forward_return=round(exit_close / entry_close - 1, 6),
        max_forward_return=round(max_close / entry_close - 1, 6),
    )


def _group_summary(observations: list[BacktestObservation], *, key_fn) -> list[dict[str, Any]]:
    grouped: dict[str, list[BacktestObservation]] = {}
    for row in observations:
        grouped.setdefault(str(key_fn(row)), []).append(row)
    result: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        forward_returns = [row.forward_return for row in rows]
        max_returns = [row.max_forward_return for row in rows]
        count = len(rows)
        result.append(
            {
                "bucket": key,
                "sample_count": count,
                "average_forward_return": round(sum(forward_returns) / count, 6) if count else 0.0,
                "median_forward_return": round(float(median(forward_returns)), 6) if count else 0.0,
                "average_max_return": round(sum(max_returns) / count, 6) if count else 0.0,
                "hit_rate_2x": _hit_rate(max_returns, 1.0),
                "hit_rate_5x": _hit_rate(max_returns, 4.0),
                "hit_rate_10x": _hit_rate(max_returns, 9.0),
            }
        )
    return sorted(result, key=lambda item: str(item["bucket"]))


def _score_bucket(score: float) -> str:
    if score >= 85:
        return "85-100"
    if score >= 70:
        return "70-84"
    if score >= 55:
        return "55-69"
    if score >= 40:
        return "40-54"
    return "0-39"


def _hit_rate(values: list[float], threshold: float) -> float:
    if not values:
        return 0.0
    return round(sum(1 for value in values if value >= threshold) / len(values), 6)


def _field(row: Any, field: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _number(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _date_text(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        import json

        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []
    return []
