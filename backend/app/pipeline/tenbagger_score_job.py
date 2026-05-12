from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import FundamentalMetric, Industry, IndustryHeat, NewsArticle, Stock, StockScore, TrendSignal
from app.engines.tenbagger_score_engine import calculate_stock_scores
from app.pipeline.utils import json_list, latest_available_date, latest_trade_date


def run_tenbagger_score_job(session: Session, trade_date: date | None = None) -> dict[str, int | str]:
    requested_date = trade_date or latest_trade_date(session)
    target_date = latest_available_date(session, TrendSignal.trade_date, requested_date) or requested_date
    trends = session.scalars(select(TrendSignal).where(TrendSignal.trade_date == target_date)).all()
    trend_by_code = {item.stock_code: item for item in trends}
    trend_codes = set(trend_by_code)
    if not trend_codes:
        session.execute(delete(StockScore).where(StockScore.trade_date == requested_date))
        session.commit()
        logger.info("tenbagger early signal scores calculated: 0")
        return {"stock_scores": 0, "effective_date": target_date.isoformat()}
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True), Stock.code.in_(trend_codes))).all()
    industries = session.scalars(select(Industry)).all()
    industry_name_by_id = {item.id: item.name for item in industries}
    heats = session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == target_date)).all()
    heat_by_industry_name = {industry_name_by_id.get(item.industry_id, ""): item for item in heats}
    articles = session.scalars(select(NewsArticle).where(NewsArticle.published_at <= _end_of_day(target_date))).all()
    articles_by_stock: dict[str, list[NewsArticle]] = defaultdict(list)
    for article in articles:
        for code in json_list(article.related_stocks):
            articles_by_stock[str(code)].append(article)
    fundamentals = session.scalars(
        select(FundamentalMetric)
        .where(FundamentalMetric.stock_code.in_(trend_codes), FundamentalMetric.report_date <= target_date)
        .order_by(FundamentalMetric.stock_code, FundamentalMetric.report_date)
    ).all()
    fundamental_by_code: dict[str, FundamentalMetric] = {}
    for item in fundamentals:
        fundamental_by_code[item.stock_code] = item
    metrics = calculate_stock_scores(stocks, trend_by_code, heat_by_industry_name, articles_by_stock, target_date, fundamental_by_code)
    metric_codes = {item.stock_code for item in metrics}
    session.execute(delete(StockScore).where(StockScore.trade_date == target_date, StockScore.stock_code.not_in(metric_codes)))
    for item in metrics:
        existing = session.scalar(
            select(StockScore).where(StockScore.stock_code == item.stock_code, StockScore.trade_date == item.trade_date)
        )
        payload = item.__dict__.copy()
        payload.pop("stock_code")
        payload.pop("trade_date")
        payload["confidence_reasons"] = json.dumps(payload["confidence_reasons"], ensure_ascii=False)
        if existing is None:
            session.add(StockScore(stock_code=item.stock_code, trade_date=item.trade_date, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    session.commit()
    logger.info(
        "tenbagger early signal scores calculated: {} (requested={}, effective={})",
        len(metrics),
        requested_date,
        target_date,
    )
    return {"stock_scores": len(metrics), "effective_date": target_date.isoformat()}


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)
