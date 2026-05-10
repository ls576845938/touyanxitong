from __future__ import annotations

import json
from datetime import date, timedelta
from collections import defaultdict

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Industry, IndustryHeat, IndustryKeyword, NewsArticle
from app.engines.industry_heat_engine import calculate_industry_heat
from app.pipeline.utils import latest_trade_date


def run_industry_heat_job(session: Session, trade_date: date | None = None) -> dict[str, int]:
    target_date = trade_date or latest_trade_date(session)
    industries = session.scalars(select(Industry)).all()
    keywords = session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True))).all()
    keywords_by_industry: dict[int, list[IndustryKeyword]] = defaultdict(list)
    for keyword in keywords:
        keywords_by_industry[keyword.industry_id].append(keyword)
    articles = session.scalars(
        select(NewsArticle).where(NewsArticle.published_at >= target_date - timedelta(days=60))
    ).all()
    metrics = calculate_industry_heat(industries, keywords_by_industry, articles, target_date)
    for item in metrics:
        existing = session.scalar(
            select(IndustryHeat).where(IndustryHeat.industry_id == item.industry_id, IndustryHeat.trade_date == item.trade_date)
        )
        payload = {
            "heat_1d": item.heat_1d,
            "heat_7d": item.heat_7d,
            "heat_30d": item.heat_30d,
            "heat_change_7d": item.heat_change_7d,
            "heat_change_30d": item.heat_change_30d,
            "top_keywords": json.dumps(item.top_keywords, ensure_ascii=False),
            "top_articles": json.dumps(item.top_articles, ensure_ascii=False),
            "heat_score": item.heat_score,
            "explanation": item.explanation,
        }
        if existing is None:
            session.add(IndustryHeat(industry_id=item.industry_id, trade_date=item.trade_date, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    session.commit()
    logger.info("industry heat calculated: {}", len(metrics))
    return {"industry_heat": len(metrics)}
