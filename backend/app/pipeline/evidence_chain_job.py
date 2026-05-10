from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import EvidenceChain, FundamentalMetric, Industry, IndustryHeat, NewsArticle, Stock, StockScore, TrendSignal
from app.engines.evidence_chain_engine import build_evidence_chain
from app.pipeline.utils import json_list, latest_trade_date


def run_evidence_chain_job(session: Session, trade_date: date | None = None) -> dict[str, int]:
    target_date = trade_date or latest_trade_date(session)
    scores = session.scalars(select(StockScore).where(StockScore.trade_date == target_date)).all()
    trends = session.scalars(select(TrendSignal).where(TrendSignal.trade_date == target_date)).all()
    industries = session.scalars(select(Industry)).all()
    heats = session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == target_date)).all()
    industry_name_by_id = {item.id: item.name for item in industries}
    heat_by_industry_name = {industry_name_by_id.get(item.industry_id, ""): item for item in heats}
    score_by_code = {item.stock_code: item for item in scores}
    trend_by_code = {item.stock_code: item for item in trends}
    evidence_codes = set(score_by_code) & set(trend_by_code)
    if not evidence_codes:
        session.execute(delete(EvidenceChain).where(EvidenceChain.trade_date == target_date))
        session.commit()
        logger.info("evidence chains generated: 0")
        return {"evidence_chains": 0}
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True), Stock.code.in_(evidence_codes))).all()
    articles = session.scalars(select(NewsArticle)).all()
    articles_by_stock: dict[str, list[NewsArticle]] = defaultdict(list)
    for article in articles:
        for code in json_list(article.related_stocks):
            articles_by_stock[str(code)].append(article)
    fundamentals = session.scalars(
        select(FundamentalMetric)
        .where(FundamentalMetric.stock_code.in_(evidence_codes), FundamentalMetric.report_date <= target_date)
        .order_by(FundamentalMetric.stock_code, FundamentalMetric.report_date)
    ).all()
    fundamental_by_code: dict[str, FundamentalMetric] = {}
    for item in fundamentals:
        fundamental_by_code[item.stock_code] = item
    count = 0
    session.execute(delete(EvidenceChain).where(EvidenceChain.trade_date == target_date, EvidenceChain.stock_code.not_in(evidence_codes)))
    for stock in stocks:
        result = build_evidence_chain(
            stock,
            score_by_code.get(stock.code),
            trend_by_code.get(stock.code),
            heat_by_industry_name.get(stock.industry_level1),
            articles_by_stock.get(stock.code, []),
            target_date,
            fundamental_by_code.get(stock.code),
        )
        existing = session.scalar(
            select(EvidenceChain).where(EvidenceChain.stock_code == result.stock_code, EvidenceChain.trade_date == result.trade_date)
        )
        payload = {
            "summary": result.summary,
            "industry_logic": result.industry_logic,
            "company_logic": result.company_logic,
            "trend_logic": result.trend_logic,
            "catalyst_logic": result.catalyst_logic,
            "risk_summary": result.risk_summary,
            "questions_to_verify": json.dumps(result.questions_to_verify, ensure_ascii=False),
            "source_refs": json.dumps(result.source_refs, ensure_ascii=False),
        }
        if existing is None:
            session.add(EvidenceChain(stock_code=result.stock_code, trade_date=result.trade_date, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        count += 1
    session.commit()
    logger.info("evidence chains generated: {}", count)
    return {"evidence_chains": count}
