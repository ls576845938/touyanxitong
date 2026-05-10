from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskAssessment:
    penalty: float
    flags: list[str]
    explanation: str


def assess_stock_risk(stock: Any, trend_signal: Any | None) -> RiskAssessment:
    flags: list[str] = []
    penalty = 0.0

    if getattr(stock, "is_st", False):
        penalty += 4.0
        flags.append("ST或风险警示")
    if not getattr(stock, "is_active", True):
        penalty += 5.0
        flags.append("非活跃或退市风险")

    market_cap = float(getattr(stock, "market_cap", 0.0) or 0.0)
    if market_cap < 80:
        penalty += 1.5
        flags.append("市值偏小，流动性和波动风险需额外验证")

    if trend_signal is not None:
        drawdown = float(getattr(trend_signal, "max_drawdown_60d", 0.0) or 0.0)
        if drawdown < -0.25:
            penalty += 2.0
            flags.append("近60日回撤较深")
        volume_expansion = float(getattr(trend_signal, "volume_expansion_ratio", 0.0) or 0.0)
        if volume_expansion > 3.5:
            penalty += 1.5
            flags.append("成交额短期异常放大，需警惕情绪过热")

    penalty = min(10.0, round(penalty, 2))
    explanation = "；".join(flags) if flags else "未触发核心风险扣分项，但仍需核验估值、财务质量和公告真实性。"
    return RiskAssessment(penalty=penalty, flags=flags, explanation=explanation)
