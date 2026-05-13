from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.agent.guardrails import RISK_DISCLAIMER, sanitize_financial_text
from app.db.models import ResearchThesis


def generate_theses_from_report(
    report_date: date,
    top_industries: list[dict[str, Any]],
    top_trend_stocks: list[dict[str, Any]],
    risk_alerts: list[str],
    market_summary: str,
) -> list[dict[str, Any]]:
    """Generate 3-5 structured theses from daily report context using deterministic rules.

    Each thesis dict contains:
        subject_type, subject_id, subject_name, thesis_title, thesis_body,
        direction, horizon_days, confidence, evidence_refs, key_metrics,
        invalidation_conditions, risk_flags
    """
    theses: list[dict[str, Any]] = []

    # 1. Market-level thesis
    market_thesis = _build_market_thesis(report_date, top_trend_stocks, market_summary)
    if market_thesis:
        theses.append(market_thesis)

    # 2. Industry-level theses (top 2 by heat)
    for industry in top_industries[:2]:
        industry_thesis = _build_industry_thesis(industry)
        if industry_thesis:
            theses.append(industry_thesis)

    # 3. Stock-level thesis (top stock with notable characteristics)
    for stock in top_trend_stocks[:1]:
        stock_thesis = _build_stock_thesis(stock)
        if stock_thesis:
            theses.append(stock_thesis)

    # 4. Risk-aware thesis (if significant risks exist)
    if risk_alerts:
        risk_thesis = _build_risk_thesis(risk_alerts)
        if risk_thesis:
            theses.append(risk_thesis)

    # Fill up to 5 theses with additional industry/stock theses
    if len(theses) < 3 and len(top_industries) > 2:
        extra = _build_industry_thesis(top_industries[2])
        if extra:
            theses.append(extra)
    if len(theses) < 4 and len(top_trend_stocks) > 1:
        extra = _build_stock_thesis(top_trend_stocks[1])
        if extra:
            theses.append(extra)

    # Sanitize through guardrails
    for thesis in theses:
        safe_title, _ = sanitize_financial_text(thesis["thesis_title"])
        safe_body, _ = sanitize_financial_text(thesis["thesis_body"])
        thesis["thesis_title"] = safe_title
        thesis["thesis_body"] = safe_body

    # NOTE: When saving these thesis dicts as ResearchThesis rows in the
    # pipeline / daily report job, call create_review_schedule(thesis, session)
    # from app.engines.thesis_review_engine after each session.flush() to
    # auto-create pending ResearchThesisReview rows.

    return theses[:5]


def extract_theses_from_agent_claims(
    session: Session,
    run_id: int,
    claims: list[dict[str, Any]],
    artifact_id: int,
) -> list[int]:
    """Convert agent artifact claims into ResearchThesis records.

    Returns list of saved ResearchThesis IDs.
    """
    thesis_ids: list[int] = []
    if not claims:
        return thesis_ids

    for claim in claims:
        text = claim.get("text", "")
        if not text or len(text.strip()) < 10:
            continue

        safe_text, _ = sanitize_financial_text(text)
        safe_text = safe_text.strip()
        if not safe_text:
            continue

        # Skip purely descriptive claims that don't constitute a thesis
        if not _is_thesis_worthy(safe_text):
            continue

        direction = _detect_direction(safe_text)
        claim_conf = str(claim.get("confidence", "low"))
        confidence_map = {"high": 80, "medium": 55, "low": 30}
        confidence = confidence_map.get(claim_conf, 50)
        section = claim.get("section", "")
        horizon = _detect_horizon(section)
        subject_type = _detect_subject_type(section, safe_text)
        subject_name = safe_text[:128]
        thesis_title = safe_text[:100]

        # Generate invalidation conditions specific to this thesis direction
        invalidation = _build_invalidation_conditions(direction, subject_type)
        # Generate minimal risk flags
        risk_flags = _build_risk_flags(subject_type, safe_text)

        thesis = ResearchThesis(
            source_type="agent_run",
            source_id=str(run_id),
            subject_type=subject_type,
            subject_id=subject_type,
            subject_name=subject_name,
            thesis_title=thesis_title,
            thesis_body=safe_text,
            direction=direction,
            horizon_days=horizon,
            confidence=float(confidence),
            evidence_refs_json=json.dumps(claim.get("evidence_ref_ids", []), ensure_ascii=False),
            key_metrics_json="{}",
            invalidation_conditions_json=json.dumps(invalidation, ensure_ascii=False),
            risk_flags_json=json.dumps(risk_flags, ensure_ascii=False),
        )
        session.add(thesis)
        session.flush()

        # Hook: auto-create review schedule for the newly saved thesis.
        # This creates pending ResearchThesisReview rows at 5d, 20d (if applicable)
        # and at thesis.horizon_days.
        from app.engines.thesis_review_engine import create_review_schedule

        create_review_schedule(thesis, session)

        thesis_ids.append(thesis.id)

    return thesis_ids


def thesis_to_markdown(theses: list[dict[str, Any]]) -> str:
    """Convert thesis dicts into a markdown section for daily report inclusion."""
    if not theses:
        return ""

    lines = [
        "## 今日核心观点",
        "",
        "以下观点基于系统规则的量化信号生成，仅用于投研线索整理，不构成投资建议。",
        "",
    ]
    for i, thesis in enumerate(theses, 1):
        direction_label_map = {
            "positive": "偏多",
            "negative": "偏空",
            "neutral": "中性",
            "mixed": "多空交织",
        }
        horizon_label_map = {5: "短期", 20: "中期", 60: "长期"}
        direction_label = direction_label_map.get(thesis.get("direction", "neutral"), "中性")
        horizon_label = horizon_label_map.get(thesis.get("horizon_days", 20), "中期")

        lines.append(f"### {i}. {thesis.get('thesis_title', '')}")
        lines.append("")
        lines.append(f"{thesis.get('thesis_body', '')}")
        lines.append("")
        lines.append(
            f"> 方向：{direction_label} | "
            f"置信度：{thesis.get('confidence', 50)}/100 | "
            f"时间框架：{horizon_label}（{thesis.get('horizon_days', 20)}个交易日）"
        )

        key_metrics = thesis.get("key_metrics", [])
        if key_metrics:
            metric_strs: list[str] = []
            for m in key_metrics:
                if isinstance(m, dict):
                    metric_strs.append(f"{m.get('name', '')}: {m.get('value', '')}")
                elif isinstance(m, str):
                    metric_strs.append(m)
            if metric_strs:
                lines.append(f"> 关注指标：{' | '.join(metric_strs[:5])}")

        invalidation = thesis.get("invalidation_conditions", [])
        if invalidation:
            cond_strs: list[str] = []
            for c in invalidation:
                if isinstance(c, dict):
                    cond_strs.append(str(c.get("condition", "")))
                elif isinstance(c, str):
                    cond_strs.append(c)
            if cond_strs:
                lines.append(f"> 证伪条件：{'；'.join(cond_strs[:3])}")

        risk_flags = thesis.get("risk_flags", [])
        if risk_flags:
            flag_strs = [str(f) for f in risk_flags[:3]]
            lines.append(f"> 风险提示：{'；'.join(flag_strs)}")

        lines.append("")

    lines.append("---")
    lines.append(RISK_DISCLAIMER)
    return "\n".join(lines)


def _build_market_thesis(
    report_date: date,
    top_trend_stocks: list[dict[str, Any]],
    market_summary: str,
) -> dict[str, Any] | None:
    """Build a market-level aggregate thesis."""
    if not top_trend_stocks:
        return None

    scores = [float(s.get("final_score", 0) or 0) for s in top_trend_stocks[:10]]
    avg_score = sum(scores) / len(scores) if scores else 0
    strong_count = sum(1 for s in scores if s >= 70)
    weak_count = sum(1 for s in scores if s < 40)

    if avg_score >= 60 and strong_count >= 3:
        direction = "positive"
        confidence = min(80, 50 + int(strong_count * 10))
        title = "市场整体趋势偏强，结构性机会集中"
        body = (
            f"当前前10评分样本平均分{avg_score:.0f}，高分样本（>=70）{strong_count}只，"
            f"低分样本（<40）{weak_count}只，强势标的数量占优。"
            "结构性机会存在于前列赛道和趋势增强个股中，但需关注持续性。"
        )
    elif avg_score >= 40:
        direction = "neutral"
        confidence = 50
        title = "市场整体中性，结构性分化明显"
        body = (
            f"当前前10评分样本平均分{avg_score:.0f}，高分样本（>=70）{strong_count}只，"
            f"低分样本（<40）{weak_count}只，市场呈现分化格局。"
            "需关注持续性信号的确认和趋势强化方向。"
        )
    else:
        direction = "mixed"
        confidence = 30
        title = "市场整体偏弱，等待趋势信号改善"
        body = (
            f"当前前10评分样本平均分{avg_score:.0f}，高分样本（>=70）{strong_count}只，"
            f"低分样本（<40）{weak_count}只，整体强度不足。"
            "需等待明确催化事件或趋势信号的改善确认。"
        )

    return {
        "subject_type": "market",
        "subject_id": None,
        "subject_name": "大盘综合分析",
        "thesis_title": title,
        "thesis_body": body,
        "direction": direction,
        "horizon_days": 20,
        "confidence": confidence,
        "evidence_refs": [
            {"source": "stock_score", "metric": "top10_avg_score", "value": round(avg_score, 2)},
            {"source": "stock_score", "metric": "strong_count_ge70", "value": strong_count},
        ],
        "key_metrics": [
            {"name": "前10平均评分", "value": round(avg_score, 2)},
            {"name": "强势样本数(>=70)", "value": strong_count},
            {"name": "偏弱样本数(<40)", "value": weak_count},
        ],
        "invalidation_conditions": [
            "市场评分连续3个交易日下降",
            "强势股数量减少至不足2只",
            "评分样本覆盖率大幅下降",
        ],
        "risk_flags": [
            "整体评分不代表个股表现，个体差异较大",
            "结构性行情下需关注板块轮动风险",
            "结果仅用于研究线索整理",
        ],
    }


def _build_industry_thesis(industry: dict[str, Any]) -> dict[str, Any] | None:
    """Build a thesis for a single industry/top_industry entry."""
    heat_score = float(industry.get("heat_score", 0) or 0)
    industry_id = industry.get("industry_id")
    explanation = str(industry.get("explanation", "") or "")
    top_keywords = industry.get("top_keywords", [])
    industry_label = f"产业ID {industry_id}" if industry_id else "未分类"
    keyword_hint = ""
    if isinstance(top_keywords, list) and top_keywords:
        keyword_hint = f"，关键词：{'/'.join(str(k) for k in top_keywords[:4])}"

    if heat_score >= 60:
        direction = "positive"
        confidence = min(75, 40 + int(heat_score / 3))
        title = f"{industry_label}热度维持较强扩散"
        body = (
            f"{industry_label}当前热度分{heat_score:.1f}，{explanation}"
            f"{keyword_hint}。产业热度仍在扩散区间，但需观察"
            "持续性信号确认是否为趋势而非单日脉冲。"
        )
    elif heat_score >= 30:
        direction = "neutral"
        confidence = 50
        title = f"{industry_label}热度处于中性区间"
        body = (
            f"{industry_label}当前热度分{heat_score:.1f}，{explanation}"
            f"{keyword_hint}。热度中等，暂未形成明确趋势方向，"
            "需关注后续变化。"
        )
    else:
        direction = "mixed"
        confidence = 35
        title = f"{industry_label}热度偏低，趋势尚未形成"
        body = (
            f"{industry_label}当前热度分{heat_score:.1f}，{explanation}"
            f"{keyword_hint}。热度偏低，暂未形成明显产业趋势，"
            "需等待催化信号。"
        )

    return {
        "subject_type": "industry",
        "subject_id": str(industry_id) if industry_id is not None else None,
        "subject_name": industry_label,
        "thesis_title": title,
        "thesis_body": body,
        "direction": direction,
        "horizon_days": 20,
        "confidence": confidence,
        "evidence_refs": [
            {"source": "industry_heat", "industry_id": industry_id, "heat_score": round(heat_score, 2)},
        ],
        "key_metrics": [
            {"name": "热度分", "value": round(heat_score, 2)},
        ],
        "invalidation_conditions": [
            f"{industry_label}热度连续3个交易日回落超过15%",
            "同产业核心标的出现趋势反转信号",
            "产业关键数据出现证伪",
        ],
        "risk_flags": [
            "产业热度不代表该产业内所有个股表现",
            "短期热度脉冲后存在回落风险",
            "需结合基本面、估值和订单数据进行交叉验证",
        ],
    }


def _build_stock_thesis(stock: dict[str, Any]) -> dict[str, Any] | None:
    """Build a thesis for a single top_trend_stock entry."""
    code = stock.get("code", "")
    name = stock.get("name", "")
    if not code or not name:
        return None

    final_score = float(stock.get("final_score", 0) or 0)
    trend_score = float(stock.get("trend_score", 0) or 0)
    risk_penalty = float(stock.get("risk_penalty", 0) or 0)
    rating = str(stock.get("rating", "") or "仅记录")
    is_ma_bullish = bool(stock.get("is_ma_bullish", False))
    is_breakout = bool(stock.get("is_breakout_120d", False) or stock.get("is_breakout_250d", False))
    rs_rank = int(stock.get("relative_strength_rank", 0) or 0)

    # Determine direction from actual signal data, not hardcoded neutral
    if risk_penalty >= 3:
        direction = "negative"
        confidence = 45
        title = f"{name}存在风险信号，需核验"
        body = (
            f"{name}（{code}）当前风险扣分{risk_penalty:.1f}，"
            f"综合评分{final_score:.1f}，评级{rating}。"
            "风险扣分较高，需核验风险来源是否已被市场充分定价。"
        )
    elif (final_score >= 55 and trend_score >= 40) or (is_ma_bullish and final_score >= 45):
        direction = "positive"
        confidence = min(75, 45 + int(final_score / 8))
        signal_desc = []
        if is_ma_bullish:
            signal_desc.append("均线多头排列")
        if is_breakout:
            signal_desc.append("突破阶段新高")
        signal_str = "，".join(signal_desc) if signal_desc else "趋势偏强"
        title = f"{name}{signal_str}，持续跟踪验证"
        body = (
            f"{name}（{code}）当前综合评分{final_score:.1f}，趋势分{trend_score:.1f}，"
            f"评级{rating}，{signal_str}。RS排名{rs_rank}，"
            "需关注成交量变化和趋势持续性，是否形成有效突破仍需验证。"
        )
    elif final_score < 30:
        direction = "negative"
        confidence = 40
        title = f"{name}评分偏低，观察拐点"
        body = (
            f"{name}（{code}）当前综合评分{final_score:.1f}（偏低），趋势分{trend_score:.1f}，"
            f"评级{rating}。评分偏弱，等待趋势拐点确认。"
        )
    else:
        # Middle zone (final_score 30-55 or trend_score < 40): lean positive
        # unless risk penalty is significant
        if risk_penalty >= 2:
            direction = "negative"
            confidence = 42
            title = f"{name}风险信号偏高，谨慎观察"
        else:
            direction = "positive"
            confidence = 42
            title = f"{name}评分{final_score:.0f}分，趋势待确认但偏多"
        body = (
            f"{name}（{code}）当前综合评分{final_score:.1f}，趋势分{trend_score:.1f}，"
            f"评级{rating}。均线{'多头' if is_ma_bullish else '非多头'}排列，RS排名{rs_rank}。"
            "信号不够强烈，需结合更多证据验证方向。"
        )

    return {
        "subject_type": "stock",
        "subject_id": code,
        "subject_name": name,
        "thesis_title": title,
        "thesis_body": body,
        "direction": direction,
        "horizon_days": 5,
        "confidence": confidence,
        "evidence_refs": [
            {"source": "stock_score", "code": code, "final_score": round(final_score, 2)},
            {"source": "stock_score", "trend_score": round(trend_score, 2)},
        ],
        "key_metrics": [
            {"name": "综合评分", "value": round(final_score, 2)},
            {"name": "趋势分", "value": round(trend_score, 2)},
            {"name": "风险扣分", "value": round(risk_penalty, 2)},
        ],
        "invalidation_conditions": [
            f"{name}股价跌破20日均线",
            f"{name}成交量持续萎缩至20日均量以下",
            f"{name}评级下调至弱观察或以下",
        ],
        "risk_flags": [
            "个股评分仅为研究线索，不构成投资建议",
            "趋势增强后存在均值回归风险",
            "需结合基本面、估值和产业逻辑综合判断",
        ],
    }


def _build_risk_thesis(risk_alerts: list[str]) -> dict[str, Any] | None:
    """Build a thesis about notable risk signals."""
    if not risk_alerts:
        return None

    risk_count = len(risk_alerts)
    sample_risks = risk_alerts[:3]

    direction = "negative"
    confidence = min(70, 40 + risk_count * 10)

    risk_detail = "；".join(sample_risks)
    if risk_count > 3:
        risk_detail += f"；另有{risk_count - 3}条风险提示"

    title = "当前市场存在需要关注的风险信号"
    body = (
        f"今日触发{risk_count}条风险预警。主要风险包括：{risk_detail}。"
        "需逐一核验风险是否已被市场定价，以及是否会引发连锁反应。"
    )

    return {
        "subject_type": "theme",
        "subject_id": None,
        "subject_name": "风险主题",
        "thesis_title": title,
        "thesis_body": body,
        "direction": direction,
        "horizon_days": 5,
        "confidence": confidence,
        "evidence_refs": [
            {"source": "risk_alerts", "count": risk_count, "alerts": sample_risks},
        ],
        "key_metrics": [
            {"name": "风险预警数", "value": risk_count},
        ],
        "invalidation_conditions": [
            "风险因素被公司公告或官方数据证伪",
            "市场整体反弹修复，相关风险消化",
            "风险标的评级恢复至正常水平",
        ],
        "risk_flags": [
            "风险预警不代表必然发生，需结合实际情况判断",
            "单一公司风险不应外推至整个行业或市场",
            "建议独立复核每条风险提示的数据来源",
        ],
    }


def _is_thesis_worthy(text: str) -> bool:
    """Return True if the claim text contains judgment/opinion, not just description."""
    judgment_keywords = {
        "判断", "结论", "趋势", "走强", "走弱", "回落", "回升",
        "偏强", "偏弱", "看好", "谨慎", "风险", "需验证", "需确认",
        "优于", "弱于", "强于", "扩散", "收缩", "加速", "减速",
        "改善", "恶化", "突破", "承压", "支撑", "阻力",
        "仍处于", "可能", "预计", "关键", "值得", "应当",
    }
    lower = text.lower()
    # Also accept claims that are long enough to be substantive
    if len(text) > 80:
        return True
    return any(kw in lower for kw in judgment_keywords)


def _build_invalidation_conditions(direction: str, subject_type: str) -> list[dict[str, str]]:
    """Build sensible invalidation conditions based on thesis direction and type."""
    conditions: list[dict[str, str]] = []
    if direction == "positive":
        conditions.append({"type": "trend_break", "description": "趋势转为横盘或下行，收盘价跌破近20日均线"})
        conditions.append({"type": "volume_fade", "description": "成交量持续萎缩至近5日均量的50%以下"})
    elif direction == "negative":
        conditions.append({"type": "trend_reversal", "description": "价格企稳回升并站上近20日均线"})
        conditions.append({"type": "catalyst_positive", "description": "出现实质性利好事件改变基本面判断"})
    else:
        conditions.append({"type": "direction_emerges", "description": "出现明确的向上或向下突破信号"})
        conditions.append({"type": "evidence_accumulates", "description": "新证据出现使判断方向变得明确"})

    if subject_type == "industry":
        conditions.append({"type": "heat_shift", "description": "行业热度连续3日下降且排名跌出前10"})
    elif subject_type == "stock":
        conditions.append({"type": "score_drop", "description": "综合评分下降超过10分或评级下调"})
    return conditions


def _build_risk_flags(subject_type: str, text: str) -> list[dict[str, str]]:
    """Build minimal risk flags for the thesis. Always returns at least one entry."""
    flags: list[dict[str, str]] = []
    lower = text.lower()
    if subject_type == "stock":
        flags.append({"flag": "个股风险", "detail": "个股受公告、财报、行业政策等因素影响，存在不确定性"})
    # Always add at least one risk flag
    if not flags:
        flags.append({"flag": "信息不完整", "detail": "当前分析基于可用数据，可能存在未覆盖的风险因素"})
    if "风险" not in lower and "不确定性" not in lower:
        flags.append({"flag": "信息不完整", "detail": "当前分析基于可用数据，可能存在未覆盖的风险因素"})
    return flags


def _detect_direction(text: str) -> str:
    """Detect thesis direction from text using keyword heuristics.

    Returns 'positive', 'negative', or 'neutral' based on weighted keyword
    scoring of the text.  Weights are calibrated to nudge ambiguous texts
    toward a useful direction rather than default to neutral.
    """
    positive_keywords = {
        # Strong directional signals (weight 3)
        "多头排列": 3, "突破新高": 3, "持续走牛": 3, "加速上行": 3,
        "强势突破": 3, "放量上涨": 3, "趋势延续": 3,
        # Medium signals (weight 2)
        "均线多头": 2, "站上均线": 2, "量价齐升": 2, "底部抬升": 2,
        "资金流入": 2, "景气上行": 2, "业绩超预期": 2,
        # Light signals (weight 1)
        "增强": 1, "提升": 1, "突破": 1, "增长": 1, "扩散": 1,
        "强势": 1, "利好": 1, "上行": 1, "回升": 1, "扩张": 1,
        "走强": 1, "加速": 1, "改善": 1, "偏强": 1,
        "bullish": 1, "positive": 1, "upside": 1, "growth": 1,
    }
    negative_keywords = {
        # Strong directional signals (weight 3)
        "空头排列": 3, "跌破支撑": 3, "持续走熊": 3, "加速下行": 3,
        "放量下跌": 3, "趋势逆转": 3, "破位下行": 3,
        # Medium signals (weight 2)
        "均线空头": 2, "跌破均线": 2, "量价背离": 2, "顶部信号": 2,
        "资金流出": 2, "景气下行": 2, "业绩不及预期": 2,
        # Light signals (weight 1)
        "回落": 1, "风险": 1, "下跌": 1, "恶化": 1, "减弱": 1,
        "利空": 1, "下行": 1, "收缩": 1, "承压": 1, "降温": 1,
        "走弱": 1, "减速": 1, "下滑": 1, "亏损": 1, "偏弱": 1,
        "bearish": 1, "negative": 1, "downside": 1, "decline": 1,
    }

    lower = text.lower()
    pos_score = sum(weight for kw, weight in positive_keywords.items() if kw in lower)
    neg_score = sum(weight for kw, weight in negative_keywords.items() if kw in lower)

    # If we have any signal, prefer a direction
    # Only return neutral when both scores are truly zero
    if pos_score > neg_score:
        return "positive"
    if neg_score > pos_score:
        return "negative"

    # Both equal: check context clues for tie-breaking
    if pos_score > 0:  # tied but non-zero → mixed
        return "mixed"

    # Truly no signal: check for "观察" / "强观察" (mild positive context)
    if "强观察" in text or "主升" in text or "看涨" in text or "看好" in text:
        return "positive"
    if "排除" in text or "看跌" in text or "看空" in text:
        return "negative"

    return "neutral"


def _detect_horizon(section: str) -> int:
    """Map agent claim section to thesis horizon in trading days."""
    section_lower = section.lower()
    if any(kw in section_lower for kw in {"短期", "短期", "日线", "日内", "技术"}):
        return 5
    if any(kw in section_lower for kw in {"长期", "长期", "年线", "宏观"}):
        return 60
    return 20


def _detect_subject_type(section: str, text: str) -> str:
    """Detect subject type from agent claim section and text."""
    combined = (section + " " + text).lower()
    if any(kw in combined for kw in {"行业", "产业", "赛道", "板块", "industry"}):
        return "industry"
    if any(kw in combined for kw in {"股票", "个股", "公司", "标的", "stock", "company"}):
        return "stock"
    if any(kw in combined for kw in {"宏观", "大盘", "市场", "market", "macro"}):
        return "market"
    return "theme"
