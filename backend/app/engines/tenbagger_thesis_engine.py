from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.engines.data_gate_engine import ResearchDataGate, assess_research_data_gate


@dataclass(frozen=True)
class TenbaggerThesisResult:
    stock_code: str
    trade_date: date
    thesis_score: float
    opportunity_score: float
    growth_score: float
    quality_score: float
    valuation_score: float
    timing_score: float
    evidence_score: float
    risk_score: float
    readiness_score: float
    stage: str
    data_gate_status: str
    investment_thesis: str
    base_case: str
    bull_case: str
    bear_case: str
    key_milestones: list[str]
    disconfirming_evidence: list[str]
    missing_evidence: list[str]
    source_refs: list[dict[str, str]]
    explanation: str


def build_tenbagger_thesis(
    *,
    stock: Any,
    score: Any,
    trend_signal: Any | None,
    industry_heat: Any | None,
    articles: list[Any],
    trade_date: date,
    fundamental: Any | None = None,
) -> TenbaggerThesisResult:
    data_gate = assess_research_data_gate(stock=stock, score=score, fundamental=fundamental)
    missing = _missing_evidence(stock, score, fundamental, articles)
    opportunity_score = _opportunity_score(stock, industry_heat, missing)
    growth_score = _growth_score(fundamental)
    quality_score = _quality_score(fundamental)
    valuation_score = _valuation_score(stock, fundamental)
    timing_score = _timing_score(score, trend_signal)
    evidence_score = _evidence_score(score, data_gate, articles)
    risk_score = _risk_score(stock, score, trend_signal)
    readiness_score = round(min(data_gate.score, evidence_score, 100 - len(missing) * 4), 2)
    thesis_score = round(
        opportunity_score * 0.18
        + growth_score * 0.20
        + quality_score * 0.16
        + valuation_score * 0.12
        + timing_score * 0.14
        + evidence_score * 0.12
        + risk_score * 0.08,
        2,
    )
    if data_gate.status == "FAIL":
        thesis_score = round(thesis_score * 0.65, 2)
    elif data_gate.status == "WARN":
        thesis_score = round(thesis_score * 0.85, 2)
    stage = _stage(thesis_score, readiness_score, data_gate)
    stock_name = str(_field(stock, "name", _field(stock, "code", "")))
    industry_name = str(_field(stock, "industry_level1", "未分类") or "未分类")
    investment_thesis = _investment_thesis(stock_name, industry_name, thesis_score, stage, data_gate)
    base_case = _base_case(stock, fundamental, thesis_score)
    bull_case = _bull_case(stock, fundamental, industry_heat)
    bear_case = _bear_case(stock, data_gate, missing)
    key_milestones = _key_milestones(fundamental)
    disconfirming_evidence = _disconfirming_evidence()
    source_refs = _source_refs(articles, fundamental)
    explanation = (
        f"十倍股假设分{thesis_score:.1f}：空间{opportunity_score:.1f}、成长{growth_score:.1f}、"
        f"质量{quality_score:.1f}、估值容忍{valuation_score:.1f}、趋势{timing_score:.1f}、"
        f"证据{evidence_score:.1f}、风险{risk_score:.1f}。"
        f"研究准入{data_gate.status}（{data_gate.score:.1f}），"
        f"阶段为{stage}。缺口：{'；'.join(missing) if missing else '暂无核心缺口'}。"
    )
    return TenbaggerThesisResult(
        stock_code=str(_field(stock, "code")),
        trade_date=trade_date,
        thesis_score=thesis_score,
        opportunity_score=round(opportunity_score, 2),
        growth_score=round(growth_score, 2),
        quality_score=round(quality_score, 2),
        valuation_score=round(valuation_score, 2),
        timing_score=round(timing_score, 2),
        evidence_score=round(evidence_score, 2),
        risk_score=round(risk_score, 2),
        readiness_score=readiness_score,
        stage=stage,
        data_gate_status=data_gate.status,
        investment_thesis=investment_thesis,
        base_case=base_case,
        bull_case=bull_case,
        bear_case=bear_case,
        key_milestones=key_milestones,
        disconfirming_evidence=disconfirming_evidence,
        missing_evidence=missing,
        source_refs=source_refs,
        explanation=explanation,
    )


def _opportunity_score(stock: Any, industry_heat: Any | None, missing: list[str]) -> float:
    heat_score = _number(_field(industry_heat, "heat_score", 0.0))
    score = min(42.0, heat_score / 30 * 42)
    market_cap = _number(_field(stock, "market_cap", 0.0))
    if 80 <= market_cap <= 700:
        score += 22
    elif 700 < market_cap <= 2500:
        score += 15
    elif market_cap > 2500:
        score += 8
    elif market_cap > 0:
        score += 10
    industry_name = str(_field(stock, "industry_level1", ""))
    if industry_name and industry_name not in {"未分类", "未知", "unknown"}:
        score += 16
    if any("TAM" in item or "空间" in item for item in missing):
        score = min(score, 68)
    return min(100.0, score)


def _growth_score(fundamental: Any | None) -> float:
    if fundamental is None:
        return 28.0
    revenue_growth = _number(_field(fundamental, "revenue_growth_yoy", 0.0))
    profit_growth = _number(_field(fundamental, "profit_growth_yoy", 0.0))
    return min(100.0, _metric(revenue_growth, -10, 45, 48) + _metric(profit_growth, -20, 60, 52))


def _quality_score(fundamental: Any | None) -> float:
    if fundamental is None:
        return 25.0
    gross_margin = _number(_field(fundamental, "gross_margin", 0.0))
    roe = _number(_field(fundamental, "roe", 0.0))
    debt_ratio = _number(_field(fundamental, "debt_ratio", 0.0))
    cashflow_quality = _number(_field(fundamental, "cashflow_quality", 0.0))
    return min(
        100.0,
        _metric(gross_margin, 0.12, 0.60, 28)
        + _metric(roe, 0.02, 0.25, 26)
        + _metric(cashflow_quality, 0.35, 1.45, 28)
        + _metric(debt_ratio, 0.85, 0.2, 18),
    )


def _valuation_score(stock: Any, fundamental: Any | None) -> float:
    market_cap = _number(_field(stock, "market_cap", 0.0))
    if market_cap <= 0:
        return 25.0
    growth = 0.0
    if fundamental is not None:
        growth = max(
            _number(_field(fundamental, "revenue_growth_yoy", 0.0)),
            _number(_field(fundamental, "profit_growth_yoy", 0.0)),
        )
    size_room = 45 if market_cap <= 300 else 35 if market_cap <= 900 else 24 if market_cap <= 2500 else 12
    growth_room = _metric(growth, 0, 50, 45) if fundamental is not None else 15
    return min(100.0, size_room + growth_room + 10)


def _timing_score(score: Any, trend_signal: Any | None) -> float:
    trend_score = _number(_field(score, "trend_score", 0.0))
    result = min(68.0, trend_score / 25 * 68)
    if bool(_field(trend_signal, "is_breakout_250d", False)):
        result += 14
    elif bool(_field(trend_signal, "is_breakout_120d", False)):
        result += 8
    if bool(_field(trend_signal, "is_ma_bullish", False)):
        result += 10
    volume_expansion = _number(_field(trend_signal, "volume_expansion_ratio", 0.0))
    if 1.2 <= volume_expansion <= 3.0:
        result += 8
    return min(100.0, result)


def _evidence_score(score: Any, data_gate: ResearchDataGate, articles: list[Any]) -> float:
    confidence = (
        _number(_field(score, "source_confidence", 0.0)) * 20
        + _number(_field(score, "data_confidence", 0.0)) * 25
        + _number(_field(score, "fundamental_confidence", 0.0)) * 25
        + _number(_field(score, "news_confidence", 0.0)) * 15
        + _number(_field(score, "evidence_confidence", 0.0)) * 15
    )
    article_bonus = min(10.0, len(articles) * 2.5)
    return min(100.0, confidence * 0.85 + data_gate.score * 0.10 + article_bonus)


def _risk_score(stock: Any, score: Any, trend_signal: Any | None) -> float:
    result = 100.0 - _number(_field(score, "risk_penalty", 0.0)) * 10
    drawdown = _number(_field(trend_signal, "max_drawdown_60d", 0.0))
    if drawdown < -0.25:
        result -= 12
    if bool(_field(stock, "is_st", False)):
        result -= 40
    return max(0.0, result)


def _stage(thesis_score: float, readiness_score: float, data_gate: ResearchDataGate) -> str:
    if data_gate.status == "FAIL":
        return "blocked"
    if thesis_score >= 78 and readiness_score >= 80:
        return "candidate"
    if thesis_score >= 62 and readiness_score >= 60:
        return "verification"
    return "discovery"


def _missing_evidence(stock: Any, score: Any, fundamental: Any | None, articles: list[Any]) -> list[str]:
    missing = [
        "TAM/渗透率/行业空间未结构化",
        "估值倍数和3-5年情景模型未接入",
        "竞争优势、管理层和资本配置证据未结构化",
    ]
    if fundamental is None or _number(_field(score, "fundamental_confidence", 0.0)) < 0.7:
        missing.append("连续季度真实财报和现金流证据不足")
    if not articles or _number(_field(score, "news_confidence", 0.0)) < 0.4:
        missing.append("公告、订单、客户和财报电话会证据不足")
    if str(_field(stock, "industry_level1", "")) in {"", "未分类", "未知", "unknown"}:
        missing.append("行业归类仍未验证")
    return _dedupe(missing)


def _investment_thesis(stock_name: str, industry_name: str, thesis_score: float, stage: str, data_gate: ResearchDataGate) -> str:
    return (
        f"{stock_name}处于{industry_name}方向，当前十倍股研究假设分为{thesis_score:.1f}，"
        f"阶段为{stage}。该结论只代表研究线索强弱；正式推进前必须先处理数据门控"
        f"{data_gate.status}中的待办。"
    )


def _base_case(stock: Any, fundamental: Any | None, thesis_score: float) -> str:
    if fundamental is None:
        return "中性情景：缺少真实连续财报，暂只能依据趋势、行业热度和基础库做线索观察。"
    return (
        f"中性情景：若营收同比维持在{_number(_field(fundamental, 'revenue_growth_yoy', 0.0)):.1f}%附近、"
        f"现金流质量保持{_number(_field(fundamental, 'cashflow_quality', 0.0)):.2f}以上，"
        f"当前研究假设可维持在{thesis_score:.1f}附近。"
    )


def _bull_case(stock: Any, fundamental: Any | None, industry_heat: Any | None) -> str:
    heat = _number(_field(industry_heat, "heat_score", 0.0))
    if fundamental is None:
        return "乐观情景：需要先证明产业需求能转化为订单、收入和利润率扩张。"
    return (
        f"乐观情景：产业热度{heat:.1f}继续扩散，收入和利润增速同步上行，"
        "公司在关键环节取得份额提升，同时估值没有被提前透支。"
    )


def _bear_case(stock: Any, data_gate: ResearchDataGate, missing: list[str]) -> str:
    return (
        f"悲观情景：数据门控为{data_gate.status}，且仍缺{'、'.join(missing[:3])}。"
        "若后续订单或财报无法验证产业逻辑，应从十倍股候选降级。"
    )


def _key_milestones(fundamental: Any | None) -> list[str]:
    milestones = [
        "连续两个报告期收入增速不低于行业增速",
        "利润增速高于收入增速，体现经营杠杆",
        "订单、客户或产能证据能解释未来12个月增长",
        "估值情景表显示3-5年仍有足够市值空间",
    ]
    if fundamental is None:
        milestones.insert(0, "补齐最近8个季度真实财报快照")
    return milestones


def _disconfirming_evidence() -> list[str]:
    return [
        "收入增长来自一次性项目，不能连续兑现",
        "毛利率或现金流质量持续恶化",
        "产业链地位被证伪，订单无法转化为利润",
        "估值已提前反映乐观情景，风险收益不再对称",
        "减持、诉讼、监管或财务真实性风险升高",
    ]


def _source_refs(articles: list[Any], fundamental: Any | None) -> list[dict[str, str]]:
    refs = [
        {
            "title": str(_field(article, "title", "")),
            "url": str(_field(article, "source_url", "")),
            "source": str(_field(article, "source", "")),
            "source_kind": str(_field(article, "source_kind", "")),
        }
        for article in articles[:5]
    ]
    if fundamental is not None:
        refs.append(
            {
                "title": str(_field(fundamental, "report_title", "财务快照")),
                "url": str(_field(fundamental, "source_url", "")),
                "source": str(_field(fundamental, "source", "")),
                "source_kind": "fundamental",
            }
        )
    return refs


def thesis_to_payload(result: Any) -> dict[str, Any]:
    return {
        "stock_code": _field(result, "stock_code"),
        "trade_date": _date_text(_field(result, "trade_date")),
        "thesis_score": _number(_field(result, "thesis_score", 0.0)),
        "opportunity_score": _number(_field(result, "opportunity_score", 0.0)),
        "growth_score": _number(_field(result, "growth_score", 0.0)),
        "quality_score": _number(_field(result, "quality_score", 0.0)),
        "valuation_score": _number(_field(result, "valuation_score", 0.0)),
        "timing_score": _number(_field(result, "timing_score", 0.0)),
        "evidence_score": _number(_field(result, "evidence_score", 0.0)),
        "risk_score": _number(_field(result, "risk_score", 0.0)),
        "readiness_score": _number(_field(result, "readiness_score", 0.0)),
        "stage": _field(result, "stage", ""),
        "data_gate_status": _field(result, "data_gate_status", ""),
        "investment_thesis": _field(result, "investment_thesis", ""),
        "base_case": _field(result, "base_case", ""),
        "bull_case": _field(result, "bull_case", ""),
        "bear_case": _field(result, "bear_case", ""),
        "key_milestones": _json_list(_field(result, "key_milestones", [])),
        "disconfirming_evidence": _json_list(_field(result, "disconfirming_evidence", [])),
        "missing_evidence": _json_list(_field(result, "missing_evidence", [])),
        "source_refs": _json_list(_field(result, "source_refs", [])),
        "explanation": _field(result, "explanation", ""),
    }


def _metric(value: float, low: float, high: float, points: float) -> float:
    if high == low:
        return 0.0
    if high > low:
        normalized = (value - low) / (high - low)
    else:
        normalized = (low - value) / (low - high)
    return max(0.0, min(points, normalized * points))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []
    return []


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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
