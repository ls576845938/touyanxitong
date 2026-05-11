from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchDataGate:
    status: str
    score: float
    reasons: list[str]
    required_actions: list[str]


def assess_research_data_gate(
    *,
    stock: Any | None = None,
    score: Any | None = None,
    fundamental: Any | None = None,
) -> ResearchDataGate:
    """Conservative gate for using a row in the formal tenbagger workflow."""

    reasons: list[str] = []
    actions: list[str] = []
    gate_score = 100.0
    hard_fail = False

    if stock is not None:
        if bool(_field(stock, "is_st", False)):
            hard_fail = True
            gate_score -= 35
            reasons.append("ST或风险警示标的不能进入正式研究闭环")
            actions.append("移出正式候选，仅保留风险观察")
        if not bool(_field(stock, "is_active", True)):
            hard_fail = True
            gate_score -= 35
            reasons.append("非活跃或退市风险标的不能进入正式研究闭环")
            actions.append("确认上市状态和交易状态")
        if str(_field(stock, "asset_type", "equity")) != "equity":
            hard_fail = True
            gate_score -= 25
            reasons.append("非普通股资产类型")
            actions.append("从十倍股股票研究池剔除")

    if fundamental is not None and _is_mock_like_source(_field(fundamental, "source", "")):
        hard_fail = True
        gate_score -= 35
        reasons.append("基本面仍来自 mock/fallback，不能进入正式研究闭环")
        actions.append("接入真实财报来源后重新生成 thesis")

    if score is None:
        hard_fail = True
        gate_score -= 45
        reasons.append("缺少评分快照")
        actions.append("先运行趋势、评分和证据链 pipeline")
    else:
        source_confidence = _number(_field(score, "source_confidence", 0.0))
        data_confidence = _number(_field(score, "data_confidence", 0.0))
        fundamental_confidence = _number(_field(score, "fundamental_confidence", 0.0))
        news_confidence = _number(_field(score, "news_confidence", 0.0))
        evidence_confidence = _number(_field(score, "evidence_confidence", 0.0))

        if source_confidence < 0.75:
            hard_fail = True
            gate_score -= 35
            reasons.append(f"行情来源置信度不足：{source_confidence:.2f}")
            actions.append("补齐 real 行情源，禁止用 mock/fallback 做正式研究")
        if data_confidence < 0.65:
            hard_fail = True
            gate_score -= 25
            reasons.append(f"结构化数据置信度不足：{data_confidence:.2f}")
            actions.append("补齐市值、上市日期、日线历史和成交额")
        if fundamental is None or fundamental_confidence < 0.7:
            gate_score -= 20
            reasons.append("真实连续基本面证据不足")
            actions.append("接入最近8个季度财报和现金流质量数据")
        if news_confidence < 0.4:
            gate_score -= 8
            reasons.append("个股新闻/公告证据不足")
            actions.append("补充公告、财报电话会和订单事件证据")
        if evidence_confidence < 0.45:
            gate_score -= 8
            reasons.append("产业/个股证据链覆盖不足")
            actions.append("补充产业链、客户、产品和催化证据")

    gate_score = round(max(0.0, min(100.0, gate_score)), 2)
    if hard_fail:
        status = "FAIL"
    elif gate_score < 75 or reasons:
        status = "WARN"
    else:
        status = "PASS"
    if not reasons:
        reasons.append("正式研究数据门通过")
    return ResearchDataGate(status=status, score=gate_score, reasons=reasons, required_actions=_dedupe(actions))


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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _is_mock_like_source(source: Any) -> bool:
    normalized = str(source or "").lower()
    return normalized == "mock" or "fallback" in normalized
