from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
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
    anti_thesis_score: float
    logic_gate_score: float
    logic_gate_status: str
    stage: str
    data_gate_status: str
    investment_thesis: str
    base_case: str
    bull_case: str
    bear_case: str
    logic_gates: list[dict[str, Any]]
    anti_thesis_items: list[dict[str, Any]]
    alternative_data_signals: list[dict[str, Any]]
    valuation_simulation: dict[str, Any]
    contrarian_signal: dict[str, Any]
    sniper_focus: list[str]
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
    valuation_simulation = _valuation_simulation(stock, fundamental, industry_heat, valuation_score)
    valuation_score = _valuation_score_with_ceiling(valuation_score, valuation_simulation)
    logic_gates = _logic_gates(
        stock=stock,
        fundamental=fundamental,
        articles=articles,
        trend_signal=trend_signal,
        valuation_simulation=valuation_simulation,
        trade_date=trade_date,
    )
    logic_gate_score = _logic_gate_score(logic_gates)
    logic_gate_status = _logic_gate_status(logic_gate_score, logic_gates)
    alternative_data_signals = _alternative_data_signals(stock, industry_heat, articles, trade_date)
    contrarian_signal = _contrarian_signal(
        opportunity_score=opportunity_score,
        quality_score=quality_score,
        growth_score=growth_score,
        evidence_score=evidence_score,
        timing_score=timing_score,
        industry_heat=industry_heat,
        trend_signal=trend_signal,
        data_gate=data_gate,
    )
    anti_thesis_items = _anti_thesis_items(
        missing=missing,
        logic_gates=logic_gates,
        valuation_simulation=valuation_simulation,
        stock=stock,
        score=score,
        trend_signal=trend_signal,
        fundamental=fundamental,
    )
    anti_thesis_score = _anti_thesis_pressure(anti_thesis_items)
    sniper_focus = _sniper_focus(logic_gates, alternative_data_signals, valuation_simulation, contrarian_signal, anti_thesis_items)
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
    if logic_gate_status == "FAIL":
        thesis_score = round(thesis_score * 0.86, 2)
    if valuation_simulation.get("valuation_ceiling_status") == "stretched":
        thesis_score = round(thesis_score * 0.92, 2)
    if anti_thesis_score >= 70:
        thesis_score = round(thesis_score * 0.9, 2)
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
        f"研究准入{data_gate.status}（{data_gate.score:.1f}），逻辑门控{logic_gate_status}（{logic_gate_score:.1f}），"
        f"反证压力{anti_thesis_score:.1f}，"
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
        anti_thesis_score=round(anti_thesis_score, 2),
        logic_gate_score=round(logic_gate_score, 2),
        logic_gate_status=logic_gate_status,
        stage=stage,
        data_gate_status=data_gate.status,
        investment_thesis=investment_thesis,
        base_case=base_case,
        bull_case=bull_case,
        bear_case=bear_case,
        logic_gates=logic_gates,
        anti_thesis_items=anti_thesis_items,
        alternative_data_signals=alternative_data_signals,
        valuation_simulation=valuation_simulation,
        contrarian_signal=contrarian_signal,
        sniper_focus=sniper_focus,
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


def _valuation_simulation(stock: Any, fundamental: Any | None, industry_heat: Any | None, valuation_score: float) -> dict[str, Any]:
    market_cap = _number(_field(stock, "market_cap", 0.0))
    heat_score = _number(_field(industry_heat, "heat_score", 0.0))
    revenue_growth = _number(_field(fundamental, "revenue_growth_yoy", 0.0)) if fundamental is not None else 12.0
    profit_growth = _number(_field(fundamental, "profit_growth_yoy", 0.0)) if fundamental is not None else 8.0
    gross_margin = _number(_field(fundamental, "gross_margin", 0.0)) if fundamental is not None else 0.28
    growth_anchor = max(0.0, min(80.0, max(revenue_growth, profit_growth)))
    tam_growth_3y = round(max(1.15, min(4.8, 1.0 + heat_score / 26.0 + growth_anchor / 115.0)), 2)
    market_share = round(max(0.015, min(0.12, 0.025 + valuation_score / 1800.0 + max(gross_margin, 0.0) / 18.0)), 4)
    terminal_multiple = round(max(1.8, min(8.5, 2.2 + growth_anchor / 22.0 + max(gross_margin, 0.0) * 2.2)), 2)
    size_drag = 1.0 + max(0.0, market_cap) / 2600.0
    base_room = (tam_growth_3y * (1.0 + market_share * 5.0) * (1.0 + max(gross_margin, 0.0))) / size_drag
    base_room = round(max(0.35, min(8.0, base_room)), 2)
    scenarios = []
    for name, multiplier, probability in (
        ("bear", 0.62, 0.25),
        ("base", 1.0, 0.5),
        ("bull", 1.55, 0.25),
    ):
        room_multiple = round(max(0.2, min(10.0, base_room * multiplier)), 2)
        scenarios.append(
            {
                "scenario": name,
                "probability": probability,
                "tam_growth_3y": round(max(1.0, tam_growth_3y * (0.75 + multiplier * 0.25)), 2),
                "market_share_assumption": round(max(0.005, min(0.16, market_share * multiplier)), 4),
                "terminal_multiple": round(max(1.2, terminal_multiple * (0.82 + multiplier * 0.18)), 2),
                "room_multiple": room_multiple,
                "model_ceiling_market_cap": round(market_cap * room_multiple, 2) if market_cap > 0 else None,
            }
        )
    base = next(item for item in scenarios if item["scenario"] == "base")
    room_multiple = float(base["room_multiple"])
    if market_cap <= 0:
        status = "insufficient"
    elif room_multiple >= 2.5:
        status = "room"
    elif room_multiple >= 1.25:
        status = "balanced"
    else:
        status = "stretched"
    return {
        "valuation_ceiling_status": status,
        "market_cap_unit": "same_as_stock_market_cap",
        "current_market_cap": market_cap if market_cap > 0 else None,
        "tam_assumptions": {
            "tam_growth_3y": tam_growth_3y,
            "penetration_stage": _penetration_stage(heat_score, growth_anchor),
            "market_share_assumption": market_share,
            "terminal_multiple": terminal_multiple,
            "data_confidence": 0.72 if fundamental is not None and heat_score > 0 else 0.38,
            "source": "deterministic_thesis_model",
        },
        "scenarios": scenarios,
        "summary": _valuation_summary(status, room_multiple),
    }


def _valuation_score_with_ceiling(valuation_score: float, simulation: dict[str, Any]) -> float:
    status = str(simulation.get("valuation_ceiling_status", "insufficient"))
    if status == "room":
        return min(100.0, valuation_score + 8)
    if status == "balanced":
        return min(82.0, valuation_score)
    if status == "stretched":
        return min(58.0, valuation_score)
    return min(52.0, valuation_score)


def _penetration_stage(heat_score: float, growth_anchor: float) -> str:
    if heat_score >= 24 and growth_anchor >= 30:
        return "1_to_10_acceleration"
    if heat_score >= 12 or growth_anchor >= 18:
        return "0_to_1_validation"
    return "pre_validation"


def _valuation_summary(status: str, room_multiple: float) -> str:
    if status == "room":
        return f"基础情景显示仍有约{room_multiple:.1f}倍市值空间弹性，需继续验证收入兑现和份额假设。"
    if status == "balanced":
        return f"基础情景约{room_multiple:.1f}倍空间，逻辑需要更强订单、利润率或份额证据支撑。"
    if status == "stretched":
        return f"基础情景约{room_multiple:.1f}倍空间，估值可能已透支部分中期乐观假设。"
    return "市值或财报输入不足，暂不能形成可靠估值天花板判断。"


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


def _logic_gates(
    *,
    stock: Any,
    fundamental: Any | None,
    articles: list[Any],
    trend_signal: Any | None,
    valuation_simulation: dict[str, Any],
    trade_date: date,
) -> list[dict[str, Any]]:
    text = _article_text(articles)
    stock_name = str(_field(stock, "name", _field(stock, "code", "")))
    revenue_growth = _number(_field(fundamental, "revenue_growth_yoy", 0.0)) if fundamental is not None else 0.0
    profit_growth = _number(_field(fundamental, "profit_growth_yoy", 0.0)) if fundamental is not None else 0.0
    cashflow_quality = _number(_field(fundamental, "cashflow_quality", 0.0)) if fundamental is not None else 0.0
    valuation_status = str(valuation_simulation.get("valuation_ceiling_status", "insufficient"))
    gates = [
        {
            "id": "order_customer_validation",
            "title": "订单/客户验证",
            "metric": "订单、客户、产能利用率或交付节奏出现可复核证据",
            "status": _keyword_gate_status(text, ["订单", "客户", "中标", "交付", "产能", "demand", "order"]),
            "due_date": _due_date(trade_date, 45),
            "source": "news_and_disclosure_proxy",
            "evidence": _evidence_titles(articles, ["订单", "客户", "中标", "交付", "产能", "demand", "order"]),
        },
        {
            "id": "financial_conversion",
            "title": "财报兑现",
            "metric": "收入增长、利润增长和现金流质量同步验证产业逻辑",
            "status": _financial_gate_status(fundamental, revenue_growth, profit_growth, cashflow_quality),
            "due_date": _due_date(trade_date, 100),
            "source": "fundamental_metric",
            "evidence": [
                f"营收同比{revenue_growth:.1f}%",
                f"利润同比{profit_growth:.1f}%",
                f"现金流质量{cashflow_quality:.2f}",
            ] if fundamental is not None else [],
        },
        {
            "id": "yield_or_capacity",
            "title": "良率/产能/交付",
            "metric": "关键产品良率、扩产、交付或供给瓶颈被数据确认",
            "status": _keyword_gate_status(text, ["良率", "扩产", "产线", "产能", "交付", "供给", "yield", "capacity"]),
            "due_date": _due_date(trade_date, 70),
            "source": "alternative_data_proxy",
            "evidence": _evidence_titles(articles, ["良率", "扩产", "产线", "产能", "交付", "供给", "yield", "capacity"]),
        },
        {
            "id": "valuation_ceiling",
            "title": "估值天花板",
            "metric": "3-5年情景模型仍显示足够空间，未被短期热度透支",
            "status": "pass" if valuation_status == "room" else "watch" if valuation_status == "balanced" else "fail",
            "due_date": _due_date(trade_date, 30),
            "source": "tam_valuation_simulation",
            "evidence": [str(valuation_simulation.get("summary", ""))],
        },
    ]
    if str(_field(stock, "industry_level1", "")) in {"AI算力", "半导体", "通信设备"}:
        gates.append(
            {
                "id": "strategic_supply_chain",
                "title": "供应链卡位",
                "metric": f"{stock_name}在关键链路的份额、壁垒或国产替代位置被证据加强",
                "status": _keyword_gate_status(text, ["份额", "壁垒", "国产替代", "龙头", "独供", "供应链", "moat", "share"]),
                "due_date": _due_date(trade_date, 90),
                "source": "industry_chain_proxy",
                "evidence": _evidence_titles(articles, ["份额", "壁垒", "国产替代", "龙头", "独供", "供应链", "moat", "share"]),
            }
        )
    if trend_signal is None:
        gates.append(
            {
                "id": "market_confirmation",
                "title": "市场确认",
                "metric": "趋势信号、相对强度和成交放大确认资金没有持续退出",
                "status": "pending",
                "due_date": _due_date(trade_date, 20),
                "source": "trend_signal",
                "evidence": [],
            }
        )
    return gates


def _logic_gate_score(gates: list[dict[str, Any]]) -> float:
    weights = {"pass": 100.0, "watch": 65.0, "pending": 42.0, "fail": 8.0}
    if not gates:
        return 0.0
    return round(sum(weights.get(str(gate.get("status", "pending")), 42.0) for gate in gates) / len(gates), 2)


def _logic_gate_status(score: float, gates: list[dict[str, Any]]) -> str:
    statuses = {str(gate.get("status", "pending")) for gate in gates}
    if "fail" in statuses or score < 45:
        return "FAIL"
    if score >= 76 and "pending" not in statuses:
        return "PASS"
    return "WARN"


def _alternative_data_signals(stock: Any, industry_heat: Any | None, articles: list[Any], trade_date: date) -> list[dict[str, Any]]:
    heat_score = _number(_field(industry_heat, "heat_score", 0.0))
    industry_name = str(_field(stock, "industry_level1", ""))
    text = _article_text(articles)
    compute_signal = min(100.0, heat_score * 2.2 + _keyword_hits(text, ["算力", "GPU", "云", "租赁", "GB200", "H100", "compute"]) * 11)
    customs_signal = min(100.0, heat_score * 1.5 + _keyword_hits(text, ["HBM", "光模块", "CPO", "PCB", "进口", "海关", "module"]) * 13)
    talent_signal = min(100.0, 18 + _keyword_hits(text, ["高管", "核心技术", "招聘", "人才", "离职", "founder", "talent"]) * 16)
    order_signal = min(100.0, heat_score * 1.3 + _keyword_hits(text, ["订单", "客户", "中标", "交付", "产能"]) * 12)
    signals = [
        _alt_signal(
            "compute_rental_price",
            "算力租赁价格溢价 proxy",
            compute_signal,
            "positive" if compute_signal >= 60 else "neutral",
            "pending_connector" if compute_signal < 25 else "proxy_active",
            trade_date,
        ),
        _alt_signal(
            "customs_import",
            "HBM/光模块/关键原材料进出口 proxy",
            customs_signal if industry_name in {"AI算力", "半导体", "通信设备"} else customs_signal * 0.55,
            "positive" if customs_signal >= 55 else "neutral",
            "pending_connector" if customs_signal < 25 else "proxy_active",
            trade_date,
        ),
        _alt_signal(
            "talent_flow",
            "高管/核心技术人员流动 proxy",
            talent_signal,
            "watch" if talent_signal >= 45 else "neutral",
            "pending_connector" if talent_signal < 35 else "proxy_active",
            trade_date,
        ),
        _alt_signal(
            "order_yield",
            "订单/良率/交付草根验证 proxy",
            order_signal,
            "positive" if order_signal >= 60 else "neutral",
            "pending_connector" if order_signal < 30 else "proxy_active",
            trade_date,
        ),
    ]
    return signals


def _alt_signal(
    signal_id: str,
    label: str,
    score: float,
    direction: str,
    coverage_status: str,
    trade_date: date,
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "label": label,
        "score": round(max(0.0, min(100.0, score)), 2),
        "direction": direction,
        "coverage_status": coverage_status,
        "source": "deterministic_proxy",
        "generated_at": trade_date.isoformat(),
    }


def _contrarian_signal(
    *,
    opportunity_score: float,
    quality_score: float,
    growth_score: float,
    evidence_score: float,
    timing_score: float,
    industry_heat: Any | None,
    trend_signal: Any | None,
    data_gate: ResearchDataGate,
) -> dict[str, Any]:
    importance_score = round(opportunity_score * 0.4 + quality_score * 0.22 + growth_score * 0.2 + evidence_score * 0.18, 2)
    heat_change_7d = _number(_field(industry_heat, "heat_change_7d", 0.0))
    heat_change_30d = _number(_field(industry_heat, "heat_change_30d", 0.0))
    drawdown = _number(_field(trend_signal, "max_drawdown_60d", 0.0))
    fear_score = round(max(0.0, -heat_change_7d) * 2.2 + max(0.0, -heat_change_30d) * 0.8 + max(0.0, -drawdown) * 100.0, 2)
    reversal_watch = importance_score >= 62 and fear_score >= 12 and data_gate.status != "FAIL"
    if reversal_watch:
        label = "cold_asset_reversal_watch"
    elif timing_score >= 76 and heat_change_7d >= 0:
        label = "hot_momentum"
    else:
        label = "neutral"
    return {
        "label": label,
        "importance_score": importance_score,
        "fear_score": fear_score,
        "reversal_watch": reversal_watch,
        "heat_change_7d": round(heat_change_7d, 2),
        "heat_change_30d": round(heat_change_30d, 2),
        "max_drawdown_60d": round(drawdown, 4),
        "explanation": _contrarian_explanation(label, importance_score, fear_score),
    }


def _anti_thesis_items(
    *,
    missing: list[str],
    logic_gates: list[dict[str, Any]],
    valuation_simulation: dict[str, Any],
    stock: Any,
    score: Any,
    trend_signal: Any | None,
    fundamental: Any | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in missing[:5]:
        items.append({"type": "missing_evidence", "severity": "medium", "title": item, "action": "补充可复核数据源"})
    for gate in logic_gates:
        status = str(gate.get("status", "pending"))
        if status in {"fail", "pending"}:
            items.append(
                {
                    "type": "logic_gate",
                    "severity": "high" if status == "fail" else "medium",
                    "title": str(gate.get("title", "逻辑门控未完成")),
                    "action": str(gate.get("metric", "继续跟踪关键验证点")),
                }
            )
    if valuation_simulation.get("valuation_ceiling_status") == "stretched":
        items.append(
            {
                "type": "valuation_ceiling",
                "severity": "high",
                "title": "估值空间压缩",
                "action": "重算TAM、份额和终局倍数，避免只因热度追高",
            }
        )
    if _number(_field(trend_signal, "max_drawdown_60d", 0.0)) < -0.25:
        items.append({"type": "trend_risk", "severity": "medium", "title": "60日回撤过深", "action": "确认是否为基本面证伪而非短期波动"})
    if fundamental is not None and _number(_field(fundamental, "cashflow_quality", 0.0)) < 0.65:
        items.append({"type": "cashflow_risk", "severity": "high", "title": "现金流质量偏弱", "action": "核验收入质量和应收账款变化"})
    if bool(_field(stock, "is_st", False)) or _number(_field(score, "risk_penalty", 0.0)) >= 4:
        items.append({"type": "risk_gate", "severity": "high", "title": "风险扣分偏高", "action": "先完成风险复核，暂不升级假设阶段"})
    return _dedupe_anti_items(items)


def _anti_thesis_pressure(items: list[dict[str, Any]]) -> float:
    weights = {"low": 6.0, "medium": 13.0, "high": 22.0}
    return round(min(100.0, sum(weights.get(str(item.get("severity", "medium")), 13.0) for item in items)), 2)


def _sniper_focus(
    logic_gates: list[dict[str, Any]],
    alternative_data_signals: list[dict[str, Any]],
    valuation_simulation: dict[str, Any],
    contrarian_signal: dict[str, Any],
    anti_thesis_items: list[dict[str, Any]],
) -> list[str]:
    focus: list[str] = []
    failing_gate = next((gate for gate in logic_gates if str(gate.get("status")) == "fail"), None)
    pending_gate = next((gate for gate in logic_gates if str(gate.get("status")) == "pending"), None)
    if failing_gate:
        focus.append(f"优先处理逻辑门控：{failing_gate.get('title')}")
    elif pending_gate:
        focus.append(f"补齐关键验证点：{pending_gate.get('title')}")
    if valuation_simulation.get("valuation_ceiling_status") in {"balanced", "stretched", "insufficient"}:
        focus.append(str(valuation_simulation.get("summary", "重算TAM和估值天花板。")))
    weak_alt = [item for item in alternative_data_signals if item.get("coverage_status") == "pending_connector"]
    if weak_alt:
        focus.append(f"替代数据待接入：{weak_alt[0].get('label')}")
    if bool(contrarian_signal.get("reversal_watch")):
        focus.append("反共识观察：逻辑重要但热度/趋势降温，核验恐惧是否来自短期噪音。")
    if anti_thesis_items:
        focus.append(f"反证压力最高项：{anti_thesis_items[0].get('title')}")
    return _dedupe([item for item in focus if item])[:5]


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
        "anti_thesis_score": _number(_field(result, "anti_thesis_score", 0.0)),
        "logic_gate_score": _number(_field(result, "logic_gate_score", 0.0)),
        "logic_gate_status": _field(result, "logic_gate_status", "WARN"),
        "stage": _field(result, "stage", ""),
        "data_gate_status": _field(result, "data_gate_status", ""),
        "investment_thesis": _field(result, "investment_thesis", ""),
        "base_case": _field(result, "base_case", ""),
        "bull_case": _field(result, "bull_case", ""),
        "bear_case": _field(result, "bear_case", ""),
        "logic_gates": _json_list(_field(result, "logic_gates", [])),
        "anti_thesis_items": _json_list(_field(result, "anti_thesis_items", [])),
        "alternative_data_signals": _json_list(_field(result, "alternative_data_signals", [])),
        "valuation_simulation": _json_object(_field(result, "valuation_simulation", {})),
        "contrarian_signal": _json_object(_field(result, "contrarian_signal", {})),
        "sniper_focus": _json_list(_field(result, "sniper_focus", [])),
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


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


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


def _article_text(articles: list[Any]) -> str:
    parts: list[str] = []
    for article in articles:
        parts.extend(
            [
                str(_field(article, "title", "")),
                str(_field(article, "summary", "")),
                str(_field(article, "content", "")),
            ]
        )
    return " ".join(parts)


def _keyword_hits(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in text_lower)


def _keyword_gate_status(text: str, keywords: list[str]) -> str:
    hits = _keyword_hits(text, keywords)
    if hits >= 2:
        return "pass"
    if hits == 1:
        return "watch"
    return "pending"


def _financial_gate_status(fundamental: Any | None, revenue_growth: float, profit_growth: float, cashflow_quality: float) -> str:
    if fundamental is None:
        return "pending"
    if revenue_growth >= 20 and profit_growth >= 20 and cashflow_quality >= 0.85:
        return "pass"
    if revenue_growth < 0 or profit_growth < -10 or cashflow_quality < 0.45:
        return "fail"
    return "watch"


def _due_date(value: date, days: int) -> str:
    return (value + timedelta(days=days)).isoformat()


def _evidence_titles(articles: list[Any], keywords: list[str]) -> list[str]:
    result = []
    for article in articles:
        title = str(_field(article, "title", ""))
        if title and _keyword_hits(title, keywords) > 0:
            result.append(title)
    return result[:4]


def _contrarian_explanation(label: str, importance_score: float, fear_score: float) -> str:
    if label == "cold_asset_reversal_watch":
        return f"逻辑重要度{importance_score:.1f}，恐惧/降温分{fear_score:.1f}，适合作为反共识验证队列。"
    if label == "hot_momentum":
        return f"逻辑重要度{importance_score:.1f}，热度和趋势仍在强化，主要风险是追热。"
    return f"逻辑重要度{importance_score:.1f}，恐惧/降温分{fear_score:.1f}，暂未形成明显反共识信号。"


def _dedupe_anti_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("type", "")), str(item.get("title", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
