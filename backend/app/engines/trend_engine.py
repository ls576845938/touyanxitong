from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class TrendMetrics:
    stock_code: str
    trade_date: date
    ma20: float
    ma60: float
    ma120: float
    ma250: float
    return_20d: float
    return_60d: float
    return_120d: float
    relative_strength_score: float
    relative_strength_rank: int
    is_ma_bullish: bool
    is_breakout_120d: bool
    is_breakout_250d: bool
    volume_expansion_ratio: float
    max_drawdown_60d: float
    trend_score: float
    explanation: str


def _value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row[field]
    return getattr(row, field)


def _ma(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    sample = values[-window:]
    return mean(sample)


def _return(values: list[float], window: int) -> float:
    if len(values) <= window:
        return 0.0
    base = values[-window - 1]
    if base <= 0:
        return 0.0
    return values[-1] / base - 1


def _max_drawdown(values: list[float]) -> float:
    peak = values[0] if values else 0.0
    max_dd = 0.0
    for price in values:
        peak = max(peak, price)
        if peak > 0:
            max_dd = min(max_dd, price / peak - 1)
    return max_dd


def _trend_score(
    relative_strength_score: float,
    is_ma_bullish: bool,
    is_breakout_120d: bool,
    is_breakout_250d: bool,
    volume_expansion_ratio: float,
    max_drawdown_60d: float,
) -> float:
    rs_score = 25.0 * 0.30 * (relative_strength_score / 100)
    ma_score = 25.0 * 0.20 if is_ma_bullish else 0.0
    breakout_score = 25.0 * 0.20 * (1.0 if is_breakout_250d else 0.6 if is_breakout_120d else 0.0)
    volume_score = 25.0 * 0.15 * min(max(volume_expansion_ratio - 1.0, 0.0) / 1.5, 1.0)
    drawdown_score = 25.0 * 0.15 * min(max((0.35 + max_drawdown_60d) / 0.35, 0.0), 1.0)
    return round(rs_score + ma_score + breakout_score + volume_score + drawdown_score, 2)


def calculate_trend_metrics(bars_by_stock: dict[str, list[Any]]) -> list[TrendMetrics]:
    raw: list[dict[str, Any]] = []
    for stock_code, bars in bars_by_stock.items():
        ordered = sorted(bars, key=lambda row: _value(row, "trade_date"))
        if len(ordered) < 60:
            continue
        closes = [float(_value(row, "close")) for row in ordered]
        amounts = [float(_value(row, "amount")) for row in ordered]
        trade_date = _value(ordered[-1], "trade_date")
        ma20 = _ma(closes, 20)
        ma60 = _ma(closes, 60)
        ma120 = _ma(closes, 120)
        ma250 = _ma(closes, 250)
        ret20 = _return(closes, 20)
        ret60 = _return(closes, 60)
        ret120 = _return(closes, 120)
        high_120 = max(closes[-120:]) if len(closes) >= 120 else max(closes)
        high_250 = max(closes[-250:]) if len(closes) >= 250 else max(closes)
        recent_amount = _ma(amounts, 5)
        base_amount = _ma(amounts[-65:-5], 60) if len(amounts) >= 65 else _ma(amounts, 60)
        volume_expansion_ratio = recent_amount / base_amount if base_amount > 0 else 0.0
        max_dd_60 = _max_drawdown(closes[-60:])
        raw.append(
            {
                "stock_code": stock_code,
                "trade_date": trade_date,
                "ma20": ma20,
                "ma60": ma60,
                "ma120": ma120,
                "ma250": ma250,
                "return_20d": ret20,
                "return_60d": ret60,
                "return_120d": ret120,
                "is_ma_bullish": ma20 > ma60 > ma120 > 0 and closes[-1] > ma20,
                "is_breakout_120d": closes[-1] >= high_120,
                "is_breakout_250d": closes[-1] >= high_250,
                "volume_expansion_ratio": volume_expansion_ratio,
                "max_drawdown_60d": max_dd_60,
            }
        )

    ranked = sorted(raw, key=lambda item: item["return_120d"], reverse=True)
    total = max(len(ranked), 1)
    rank_by_code = {item["stock_code"]: idx + 1 for idx, item in enumerate(ranked)}
    metrics: list[TrendMetrics] = []
    for item in raw:
        rank = rank_by_code[item["stock_code"]]
        rs_score = (total - rank + 1) / total * 100
        score = _trend_score(
            rs_score,
            bool(item["is_ma_bullish"]),
            bool(item["is_breakout_120d"]),
            bool(item["is_breakout_250d"]),
            float(item["volume_expansion_ratio"]),
            float(item["max_drawdown_60d"]),
        )
        explanation_parts = [
            f"120日相对强度排名第{rank}/{total}",
            "均线多头排列" if item["is_ma_bullish"] else "均线结构仍需确认",
            "突破250日新高" if item["is_breakout_250d"] else "未突破250日新高",
            f"近5日成交额/60日均值为{item['volume_expansion_ratio']:.2f}",
            f"60日最大回撤{item['max_drawdown_60d']:.2%}",
        ]
        metrics.append(
            TrendMetrics(
                stock_code=str(item["stock_code"]),
                trade_date=item["trade_date"],
                ma20=round(float(item["ma20"]), 4),
                ma60=round(float(item["ma60"]), 4),
                ma120=round(float(item["ma120"]), 4),
                ma250=round(float(item["ma250"]), 4),
                return_20d=round(float(item["return_20d"]), 6),
                return_60d=round(float(item["return_60d"]), 6),
                return_120d=round(float(item["return_120d"]), 6),
                relative_strength_score=round(rs_score, 2),
                relative_strength_rank=rank,
                is_ma_bullish=bool(item["is_ma_bullish"]),
                is_breakout_120d=bool(item["is_breakout_120d"]),
                is_breakout_250d=bool(item["is_breakout_250d"]),
                volume_expansion_ratio=round(float(item["volume_expansion_ratio"]), 4),
                max_drawdown_60d=round(float(item["max_drawdown_60d"]), 6),
                trend_score=score,
                explanation="；".join(explanation_parts),
            )
        )
    return metrics
