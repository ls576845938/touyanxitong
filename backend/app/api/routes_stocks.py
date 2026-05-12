from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, EvidenceChain, FundamentalMetric, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.engines.data_gate_engine import assess_research_data_gate
from app.pipeline.ingestion_task_service import create_ingestion_task, run_ingestion_task, source_comparison, task_payload
from app.pipeline.research_universe import eligible_stock_codes
from app.services.stock_resolver import resolve_stock

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/trend-pool")
def trend_pool(
    rating: str | None = Query(default=None),
    min_score: float = Query(default=0),
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    exclude_st: bool = Query(default=True),
    research_universe_only: bool = Query(default=True),
    limit: int = Query(default=300, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return []
    query = (
        select(StockScore, Stock, TrendSignal)
        .join(Stock, Stock.code == StockScore.stock_code)
        .join(TrendSignal, (TrendSignal.stock_code == StockScore.stock_code) & (TrendSignal.trade_date == StockScore.trade_date))
        .where(StockScore.trade_date == latest_date, StockScore.final_score >= min_score)
        .order_by(StockScore.final_score.desc())
    )
    if rating:
        query = query.where(StockScore.rating == rating)
    if market and market.upper() != "ALL":
        query = query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    if exclude_st:
        query = query.where(Stock.is_st.is_(False))
    prefetch_limit = min(max(offset + limit, limit) * (3 if research_universe_only else 1), 2000)
    query = query.limit(prefetch_limit)
    candidates = session.execute(query).all()
    candidate_stocks = [stock for _, stock, _ in candidates]
    eligible = _eligible_stock_codes_for_stocks(session, candidate_stocks)
    rows: list[dict[str, object]] = []
    for score, stock, trend in candidates:
        research_eligible = stock.code in eligible
        if research_universe_only and not research_eligible:
            continue
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "board": stock.board,
                "exchange": stock.exchange,
                "industry": stock.industry_level1,
                "industry_level2": stock.industry_level2,
                "final_score": score.final_score,
                "rating": score.rating,
                "raw_score": score.raw_score,
                "industry_score": score.industry_score,
                "company_score": score.company_score,
                "trend_score": score.trend_score,
                "catalyst_score": score.catalyst_score,
                "risk_penalty": score.risk_penalty,
                "relative_strength_rank": trend.relative_strength_rank,
                "is_ma_bullish": trend.is_ma_bullish,
                "is_breakout_120d": trend.is_breakout_120d,
                "is_breakout_250d": trend.is_breakout_250d,
                "volume_expansion_ratio": trend.volume_expansion_ratio,
                "research_eligible": research_eligible,
                "research_gate": _research_gate_payload(research_eligible, score),
                "confidence": _score_confidence_payload(score),
                "fundamental_summary": _fundamental_summary(stock, score),
                "news_evidence_status": _news_evidence_status(score),
                "explanation": score.explanation,
            }
        )
    return rows[offset : offset + limit]


@router.get("/{code}/history")
def stock_history(code: str, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = resolve_stock(session, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    resolved_code = stock.code

    scores = list(
        session.scalars(select(StockScore).where(StockScore.stock_code == resolved_code).order_by(StockScore.trade_date)).all()
    )
    if not scores:
        return {
            "stock": _stock_payload(stock),
            "latest": None,
            "history": [],
        }

    trade_dates = [score.trade_date for score in scores]
    trends = {
        row.trade_date: row
        for row in session.scalars(
            select(TrendSignal).where(TrendSignal.stock_code == resolved_code, TrendSignal.trade_date.in_(trade_dates))
        ).all()
    }
    evidence_rows = {
        row.trade_date: row
        for row in session.scalars(
            select(EvidenceChain).where(EvidenceChain.stock_code == resolved_code, EvidenceChain.trade_date.in_(trade_dates))
        ).all()
    }

    rows: list[dict[str, object]] = []
    previous_score: float | None = None
    for score in scores:
        trend = trends.get(score.trade_date)
        evidence = evidence_rows.get(score.trade_date)
        score_delta = None if previous_score is None else score.final_score - previous_score
        previous_score = score.final_score
        rows.append(
            {
                "trade_date": score.trade_date.isoformat(),
                "final_score": score.final_score,
                "rating": score.rating,
                "raw_score": score.raw_score,
                "industry_score": score.industry_score,
                "company_score": score.company_score,
                "trend_score": score.trend_score,
                "catalyst_score": score.catalyst_score,
                "risk_penalty": score.risk_penalty,
                "score_delta": score_delta,
                "confidence": _score_confidence_payload(score),
                "news_evidence_status": _news_evidence_status(score),
                "score_explanation": score.explanation,
                "relative_strength_rank": trend.relative_strength_rank if trend else None,
                "is_ma_bullish": trend.is_ma_bullish if trend else None,
                "is_breakout_120d": trend.is_breakout_120d if trend else None,
                "is_breakout_250d": trend.is_breakout_250d if trend else None,
                "volume_expansion_ratio": trend.volume_expansion_ratio if trend else None,
                "max_drawdown_60d": trend.max_drawdown_60d if trend else None,
                "trend_explanation": trend.explanation if trend else "",
                "summary": evidence.summary if evidence else "",
                "risk_summary": evidence.risk_summary if evidence else "",
                "questions_to_verify": _loads_json_list(evidence.questions_to_verify) if evidence else [],
                "source_refs": _loads_json_list(evidence.source_refs) if evidence else [],
            }
        )

    rows_desc = list(reversed(rows))
    return {
        "stock": _stock_payload(stock),
        "latest": rows_desc[0],
        "history": rows_desc,
    }


@router.get("/{code}/evidence")
def stock_evidence(code: str, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = resolve_stock(session, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    resolved_code = stock.code
    evidence = session.scalars(
        select(EvidenceChain).where(EvidenceChain.stock_code == resolved_code).order_by(EvidenceChain.trade_date.desc()).limit(1)
    ).first()
    score = session.scalars(
        select(StockScore).where(StockScore.stock_code == resolved_code).order_by(StockScore.trade_date.desc()).limit(1)
    ).first()
    trend = session.scalars(
        select(TrendSignal).where(TrendSignal.stock_code == resolved_code).order_by(TrendSignal.trade_date.desc()).limit(1)
    ).first()
    fundamental = None
    if score is not None:
        fundamental = session.scalars(
            select(FundamentalMetric)
            .where(FundamentalMetric.stock_code == resolved_code, FundamentalMetric.report_date <= score.trade_date)
            .order_by(FundamentalMetric.report_date.desc())
            .limit(1)
        ).first()
    research_eligible = resolved_code in eligible_stock_codes(session, stocks=[stock])
    return {
        "stock": _stock_payload(stock),
        "score": {
            "final_score": score.final_score if score else None,
            "rating": score.rating if score else None,
            "raw_score": score.raw_score if score else None,
            "industry_score": score.industry_score if score else None,
            "company_score": score.company_score if score else None,
            "trend_score": score.trend_score if score else None,
            "catalyst_score": score.catalyst_score if score else None,
            "risk_penalty": score.risk_penalty if score else None,
            "confidence": _score_confidence_payload(score) if score else _empty_score_confidence(),
            "research_gate": _formal_research_gate_payload(stock, score, fundamental, research_eligible),
            "fundamental_summary": _fundamental_summary(stock, score) if score else _fundamental_summary(stock, None),
            "news_evidence_status": _news_evidence_status(score) if score else "missing",
            "explanation": score.explanation if score else "",
        },
        "trend": {
            "ma20": trend.ma20 if trend else None,
            "ma60": trend.ma60 if trend else None,
            "ma120": trend.ma120 if trend else None,
            "ma250": trend.ma250 if trend else None,
            "relative_strength_rank": trend.relative_strength_rank if trend else None,
            "is_ma_bullish": trend.is_ma_bullish if trend else None,
            "is_breakout_120d": trend.is_breakout_120d if trend else None,
            "is_breakout_250d": trend.is_breakout_250d if trend else None,
            "explanation": trend.explanation if trend else "",
        },
        "evidence": {
            "trade_date": evidence.trade_date.isoformat() if evidence else "",
            "summary": evidence.summary if evidence else "当前证据不足，不能形成有效观察结论。",
            "industry_logic": evidence.industry_logic if evidence else "尚未生成产业证据链，请先补齐行情、新闻或运行 daily pipeline。",
            "company_logic": evidence.company_logic if evidence else "暂无公司层面的结构化证据。",
            "trend_logic": evidence.trend_logic if evidence else "暂无可用趋势证据。",
            "catalyst_logic": evidence.catalyst_logic if evidence else "暂无可用催化证据。",
            "risk_summary": evidence.risk_summary if evidence else "证据不足本身就是风险，不能据此形成观察结论。",
            "evidence_status": _evidence_status(evidence),
            "questions_to_verify": _loads_json_list(evidence.questions_to_verify) if evidence else ["补齐日K数据后重新计算趋势指标。", "补齐公告、财报和新闻来源后重新生成证据链。"],
            "source_refs": _loads_json_list(evidence.source_refs) if evidence else [],
        },
    }


@router.get("/{code}/bars")
def stock_bars(code: str, limit: int = Query(default=260, le=1000), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    stock = resolve_stock(session, code)
    resolved_code = stock.code if stock else code
    rows = session.scalars(
        select(DailyBar).where(DailyBar.stock_code == resolved_code).order_by(DailyBar.trade_date.desc()).limit(limit)
    ).all()
    return [
        {
            "time": row.trade_date.isoformat(),
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "amount": row.amount,
        }
        for row in reversed(rows)
    ]


@router.get("/{code}/source-comparison")
def stock_source_comparison(code: str, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = resolve_stock(session, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    payload = source_comparison(session, stock.code)
    payload["stock"] = _stock_payload(stock)
    return payload


@router.post("/{code}/ingest")
def ingest_stock(
    code: str,
    source: str = Query(default="akshare"),
    periods: int = Query(default=320, ge=60, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    stock = resolve_stock(session, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    task = create_ingestion_task(
        session,
        task_type="single",
        market=stock.market,
        board=stock.board,
        stock_code=stock.code,
        source=source,
        periods=periods,
        priority=10_000,
    )
    return task_payload(run_ingestion_task(session, task))


def _eligible_stock_codes_for_stocks(session: Session, stocks: list[Stock]) -> set[str]:
    return eligible_stock_codes(session, stocks=stocks)


def _bars_by_stock(session: Session, stock_codes: list[str]) -> dict[str, list[DailyBar]]:
    if not stock_codes:
        return {}
    rows = session.scalars(select(DailyBar).where(DailyBar.stock_code.in_(stock_codes)).order_by(DailyBar.stock_code, DailyBar.trade_date)).all()
    grouped: dict[str, list[DailyBar]] = {}
    for row in rows:
        grouped.setdefault(row.stock_code, []).append(row)
    return grouped


def _stock_payload(stock: Stock) -> dict[str, object]:
    return {
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "board": stock.board,
        "exchange": stock.exchange,
        "industry_level1": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "concepts": _loads_json_list(stock.concepts),
        "market_cap": stock.market_cap,
        "float_market_cap": stock.float_market_cap,
        "is_st": stock.is_st,
        "is_active": stock.is_active,
    }


def _empty_score_confidence() -> dict[str, object]:
    return {
        "source_confidence": None,
        "data_confidence": None,
        "fundamental_confidence": None,
        "news_confidence": None,
        "evidence_confidence": None,
        "combined_confidence": None,
        "level": "unknown",
        "reasons": [],
    }


def _score_confidence_payload(score: StockScore) -> dict[str, object]:
    if score.confidence_level and score.confidence_level != "unknown":
        data_confidence = float(score.data_confidence or 0.0)
        evidence_confidence = float(score.evidence_confidence or 0.0)
        source_confidence = float(score.source_confidence or 0.0) or _parse_confidence_value(score.explanation, "数据源置信度", data_confidence)
        fundamental_confidence = float(score.fundamental_confidence or 0.0) or _parse_confidence_value(score.explanation, "基本面置信度", data_confidence)
        news_confidence = float(score.news_confidence or 0.0) or _parse_confidence_value(score.explanation, "资讯置信度", evidence_confidence)
        combined_confidence = _parse_confidence_value(
            score.explanation,
            "综合置信度",
            source_confidence * 0.2 + data_confidence * 0.3 + fundamental_confidence * 0.25 + news_confidence * 0.25,
        )
        return {
            "source_confidence": round(source_confidence, 2),
            "data_confidence": round(data_confidence, 2),
            "fundamental_confidence": round(fundamental_confidence, 2),
            "news_confidence": round(news_confidence, 2),
            "evidence_confidence": round(evidence_confidence, 2),
            "combined_confidence": round(combined_confidence, 2),
            "level": score.confidence_level,
            "reasons": _loads_json_list(score.confidence_reasons),
        }
    explanation = score.explanation
    payload = _empty_score_confidence()
    data_match = re.search(r"数据置信度([0-9.]+)", explanation)
    evidence_match = re.search(r"证据置信度([0-9.]+)", explanation)
    source_match = re.search(r"数据源置信度([0-9.]+)", explanation)
    fundamental_match = re.search(r"基本面置信度([0-9.]+)", explanation)
    news_match = re.search(r"资讯置信度([0-9.]+)", explanation)
    combined_match = re.search(r"综合置信度([0-9.]+)（([a-z]+)）", explanation)
    reasons_match = re.search(r"原因：(.+?)。风险说明", explanation)
    if source_match:
        payload["source_confidence"] = float(source_match.group(1))
    if data_match:
        payload["data_confidence"] = float(data_match.group(1))
    if fundamental_match:
        payload["fundamental_confidence"] = float(fundamental_match.group(1))
    if news_match:
        payload["news_confidence"] = float(news_match.group(1))
    if evidence_match:
        payload["evidence_confidence"] = float(evidence_match.group(1))
    if combined_match:
        payload["combined_confidence"] = float(combined_match.group(1))
        payload["level"] = combined_match.group(2)
    if reasons_match:
        reason_text = reasons_match.group(1)
        payload["reasons"] = [] if reason_text == "数据和证据覆盖正常" else reason_text.split("、")
    return payload


def _parse_confidence_value(explanation: str, label: str, fallback: float) -> float:
    match = re.search(rf"{label}([0-9.]+)", explanation)
    if not match:
        return round(max(0.0, min(1.0, fallback)), 2)
    return round(max(0.0, min(1.0, float(match.group(1)))), 2)


def _research_gate_payload(research_eligible: bool, score: StockScore | None) -> dict[str, object]:
    confidence = _score_confidence_payload(score) if score else _empty_score_confidence()
    combined = confidence.get("combined_confidence")
    pass_confidence = isinstance(combined, float | int) and float(combined) >= 0.6
    passed = bool(research_eligible and pass_confidence)
    reasons: list[str] = []
    if not research_eligible:
        reasons.append("未通过研究股票池准入")
    if not pass_confidence:
        reasons.append("评分可信度不足")
    if not reasons:
        reasons.append("研究准入和评分可信度满足观察要求")
    return {"passed": passed, "status": "pass" if passed else "review", "reasons": reasons}


def _formal_research_gate_payload(
    stock: Stock,
    score: StockScore | None,
    fundamental: FundamentalMetric | None,
    research_eligible: bool,
) -> dict[str, object]:
    base = _research_gate_payload(research_eligible, score)
    gate = assess_research_data_gate(stock=stock, score=score, fundamental=fundamental)
    passed = bool(base["passed"] and gate.status == "PASS")
    status = "pass" if passed else "blocked" if gate.status == "FAIL" else "review"
    reasons = [str(item) for item in base["reasons"]]
    reasons.extend(reason for reason in gate.reasons if reason not in reasons)
    return {
        "passed": passed,
        "status": status,
        "formal_status": gate.status,
        "gate_score": gate.score,
        "reasons": reasons,
        "required_actions": gate.required_actions,
    }


def _fundamental_summary(stock: Stock, score: StockScore | None) -> dict[str, object]:
    missing: list[str] = []
    if float(stock.market_cap or 0.0) <= 0:
        missing.append("市值")
    if float(stock.float_market_cap or 0.0) <= 0:
        missing.append("流通市值")
    if not stock.is_active:
        missing.append("上市状态")
    if stock.is_st:
        missing.append("ST状态")
    confidence = _score_confidence_payload(score) if score else _empty_score_confidence()
    return {
        "status": "complete" if not missing else "partial",
        "market_cap": stock.market_cap,
        "float_market_cap": stock.float_market_cap,
        "confidence": confidence.get("fundamental_confidence"),
        "missing_items": missing,
    }


def _news_evidence_status(score: StockScore | None) -> str:
    if score is None:
        return "missing"
    confidence = _score_confidence_payload(score)
    news_confidence = confidence.get("news_confidence")
    if isinstance(news_confidence, float | int) and float(news_confidence) >= 0.66:
        return "active"
    if isinstance(news_confidence, float | int) and float(news_confidence) > 0:
        return "partial"
    return "missing"


def _evidence_status(evidence: EvidenceChain | None) -> str:
    if evidence is None:
        return "missing"
    refs = _loads_json_list(evidence.source_refs)
    questions = _loads_json_list(evidence.questions_to_verify)
    if refs:
        return "sourced"
    if questions:
        return "needs_verification"
    return "missing"


def _loads_json_list(raw: str) -> list[object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
