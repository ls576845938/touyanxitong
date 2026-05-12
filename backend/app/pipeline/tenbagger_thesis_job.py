from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import FundamentalMetric, Industry, IndustryHeat, NewsArticle, Stock, StockScore, TenbaggerThesis, TrendSignal
from app.engines.tenbagger_thesis_engine import build_tenbagger_thesis
from app.pipeline.utils import json_list, latest_available_date, latest_trade_date


def run_tenbagger_thesis_job(session: Session, trade_date: date | None = None) -> dict[str, int | str]:
    requested_date = trade_date or latest_trade_date(session)
    target_date = latest_available_date(session, StockScore.trade_date, requested_date) or requested_date
    scores = session.scalars(select(StockScore).where(StockScore.trade_date == target_date)).all()
    if not scores:
        session.execute(delete(TenbaggerThesis).where(TenbaggerThesis.trade_date == requested_date))
        session.commit()
        logger.info("tenbagger theses generated: 0")
        return {"tenbagger_theses": 0, "effective_date": target_date.isoformat()}

    codes = {score.stock_code for score in scores}
    stocks = session.scalars(select(Stock).where(Stock.code.in_(codes))).all()
    trends = session.scalars(select(TrendSignal).where(TrendSignal.trade_date == target_date, TrendSignal.stock_code.in_(codes))).all()
    industries = session.scalars(select(Industry)).all()
    heats = session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == target_date)).all()
    articles = session.scalars(select(NewsArticle).where(NewsArticle.published_at <= _end_of_day(target_date))).all()
    fundamentals = session.scalars(
        select(FundamentalMetric)
        .where(FundamentalMetric.stock_code.in_(codes), FundamentalMetric.report_date <= target_date)
        .order_by(FundamentalMetric.stock_code, FundamentalMetric.report_date)
    ).all()

    score_by_code = {item.stock_code: item for item in scores}
    stock_by_code = {item.code: item for item in stocks}
    trend_by_code = {item.stock_code: item for item in trends}
    industry_name_by_id = {item.id: item.name for item in industries}
    heat_by_industry_name = {industry_name_by_id.get(item.industry_id, ""): item for item in heats}
    articles_by_stock: dict[str, list[NewsArticle]] = defaultdict(list)
    for article in articles:
        for code in json_list(article.related_stocks):
            articles_by_stock[str(code)].append(article)
    fundamental_by_code: dict[str, FundamentalMetric] = {}
    for item in fundamentals:
        fundamental_by_code[item.stock_code] = item

    thesis_codes = set(stock_by_code) & set(score_by_code)
    session.execute(delete(TenbaggerThesis).where(TenbaggerThesis.trade_date == target_date, TenbaggerThesis.stock_code.not_in(thesis_codes)))
    count = 0
    for code in thesis_codes:
        stock = stock_by_code[code]
        score = score_by_code[code]
        result = build_tenbagger_thesis(
            stock=stock,
            score=score,
            trend_signal=trend_by_code.get(code),
            industry_heat=heat_by_industry_name.get(stock.industry_level1),
            articles=articles_by_stock.get(code, []),
            trade_date=target_date,
            fundamental=fundamental_by_code.get(code),
        )
        payload = {
            "thesis_score": result.thesis_score,
            "opportunity_score": result.opportunity_score,
            "growth_score": result.growth_score,
            "quality_score": result.quality_score,
            "valuation_score": result.valuation_score,
            "timing_score": result.timing_score,
            "evidence_score": result.evidence_score,
            "risk_score": result.risk_score,
            "readiness_score": result.readiness_score,
            "anti_thesis_score": result.anti_thesis_score,
            "logic_gate_score": result.logic_gate_score,
            "logic_gate_status": result.logic_gate_status,
            "stage": result.stage,
            "data_gate_status": result.data_gate_status,
            "investment_thesis": result.investment_thesis,
            "base_case": result.base_case,
            "bull_case": result.bull_case,
            "bear_case": result.bear_case,
            "logic_gates": json.dumps(result.logic_gates, ensure_ascii=False),
            "anti_thesis_items": json.dumps(result.anti_thesis_items, ensure_ascii=False),
            "alternative_data_signals": json.dumps(result.alternative_data_signals, ensure_ascii=False),
            "valuation_simulation": json.dumps(result.valuation_simulation, ensure_ascii=False),
            "contrarian_signal": json.dumps(result.contrarian_signal, ensure_ascii=False),
            "sniper_focus": json.dumps(result.sniper_focus, ensure_ascii=False),
            "key_milestones": json.dumps(result.key_milestones, ensure_ascii=False),
            "disconfirming_evidence": json.dumps(result.disconfirming_evidence, ensure_ascii=False),
            "missing_evidence": json.dumps(result.missing_evidence, ensure_ascii=False),
            "source_refs": json.dumps(result.source_refs, ensure_ascii=False),
            "explanation": result.explanation,
        }
        existing = session.scalar(
            select(TenbaggerThesis).where(TenbaggerThesis.stock_code == code, TenbaggerThesis.trade_date == target_date)
        )
        if existing is None:
            session.add(TenbaggerThesis(stock_code=code, trade_date=target_date, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        count += 1

    session.commit()
    logger.info("tenbagger theses generated: {} (requested={}, effective={})", count, requested_date, target_date)
    return {"tenbagger_theses": count, "effective_date": target_date.isoformat()}


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)
