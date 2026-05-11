from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundamentalMetric, Industry, IndustryHeat, IndustryKeyword, NewsArticle, Stock, StockScore, TrendSignal
from app.engines.data_gate_engine import assess_research_data_gate
from app.engines.industry_mapping_engine import build_mapping_rules
from app.engines.retail_research_engine import (
    analyze_portfolio_exposure,
    extract_evidence_events,
    map_evidence_events_to_stocks,
    score_stock_pool_candidates,
)
from app.pipeline.utils import latest_trade_date


def retail_research_payload(session: Session, target_date: date | None = None) -> dict[str, Any]:
    report_date = target_date or latest_trade_date(session)
    scores = session.scalars(select(StockScore).where(StockScore.trade_date == report_date)).all()
    score_by_code = {item.stock_code: item for item in scores}
    if not score_by_code:
        return _empty_payload(report_date)

    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True), Stock.code.in_(tuple(score_by_code)))).all()
    trends = session.scalars(select(TrendSignal).where(TrendSignal.trade_date == report_date)).all()
    trend_by_code = {item.stock_code: item for item in trends}
    industries = session.scalars(select(Industry)).all()
    industry_by_id = {item.id: item.name for item in industries}
    heats = session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == report_date)).all()
    heat_by_industry_name = {industry_by_id.get(item.industry_id, ""): item for item in heats}
    fundamentals = session.scalars(
        select(FundamentalMetric)
        .where(FundamentalMetric.stock_code.in_(tuple(score_by_code)), FundamentalMetric.report_date <= report_date)
        .order_by(FundamentalMetric.stock_code, FundamentalMetric.report_date)
    ).all()
    fundamental_by_code: dict[str, FundamentalMetric] = {}
    for row in fundamentals:
        fundamental_by_code[row.stock_code] = row

    keyword_rows = session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True))).all()
    keywords_by_industry: dict[str, list[str]] = defaultdict(list)
    for row in keyword_rows:
        industry_name = industry_by_id.get(row.industry_id)
        if industry_name:
            keywords_by_industry[industry_name].append(row.keyword)
    industry_rules = build_mapping_rules(keywords_by_industry)

    articles = session.scalars(
        select(NewsArticle)
        .where(
            NewsArticle.published_at >= _start_of_window(report_date, days=7),
            NewsArticle.published_at <= _end_of_day(report_date),
        )
        .order_by(NewsArticle.published_at.desc())
    ).all()
    events = extract_evidence_events(list(articles), industry_rules=industry_rules)
    mappings = map_evidence_events_to_stocks(events, stocks, industry_rules=industry_rules)
    mapping_by_code = {item.stock_code: item for item in mappings}
    gates = {
        stock.code: assess_research_data_gate(stock=stock, score=score_by_code.get(stock.code), fundamental=fundamental_by_code.get(stock.code))
        for stock in stocks
    }
    candidates = score_stock_pool_candidates(
        stocks,
        evidence_mappings_by_code=mapping_by_code,
        latest_trend_by_code=trend_by_code,
        latest_heat_by_industry_name=heat_by_industry_name,
        latest_score_by_code=score_by_code,
        latest_fundamental_by_code=fundamental_by_code,
        data_gate_by_code=gates,
    )
    top_candidates = candidates[:12]
    exposure = analyze_portfolio_exposure(
        [{"stock_code": item.stock_code, "weight": max(item.conviction_score, 0.0)} for item in top_candidates if item.grade in {"S", "A", "B"}],
        {item.stock_code: item for item in top_candidates},
    )
    grade_counts: dict[str, int] = defaultdict(int)
    for item in candidates:
        grade_counts[item.grade] += 1
    return {
        "report_date": report_date.isoformat(),
        "summary": {
            "candidate_count": len(candidates),
            "event_count": len(events),
            "s_count": grade_counts.get("S", 0),
            "a_count": grade_counts.get("A", 0),
            "b_count": grade_counts.get("B", 0),
            "c_count": grade_counts.get("C", 0),
        },
        "top_candidates": [
            {
                "stock_code": item.stock_code,
                "stock_name": item.stock_name,
                "industry_name": item.industry_name,
                "grade": item.grade,
                "conviction_score": item.conviction_score,
                "evidence_score": item.evidence_score,
                "industry_heat_score": item.industry_heat_score,
                "trend_score": item.trend_score,
                "quality_score": item.quality_score,
                "valuation_score": item.valuation_score,
                "risk_score": item.risk_score,
                "data_quality_status": item.data_quality_status,
                "industry_logic": item.industry_logic,
                "company_logic": item.company_logic,
                "trend_logic": item.trend_logic,
                "risk_alert": item.risk_alert,
                "falsification_condition": item.falsification_condition,
                "only_social_heat": item.only_social_heat,
                "rationale": list(item.rationale),
            }
            for item in top_candidates
        ],
        "exposure": {
            "total_weight": exposure.total_weight,
            "industry_exposure": list(exposure.industry_exposure),
            "grade_exposure": list(exposure.grade_exposure),
            "quality_exposure": list(exposure.quality_exposure),
            "crowded_industries": list(exposure.crowded_industries),
            "warnings": list(exposure.warnings),
        },
    }


def _empty_payload(report_date: date) -> dict[str, Any]:
    return {
        "report_date": report_date.isoformat(),
        "summary": {"candidate_count": 0, "event_count": 0, "s_count": 0, "a_count": 0, "b_count": 0, "c_count": 0},
        "top_candidates": [],
        "exposure": {"total_weight": 0.0, "industry_exposure": [], "grade_exposure": [], "quality_exposure": [], "crowded_industries": [], "warnings": []},
    }


def _start_of_window(value: date, *, days: int) -> datetime:
    return datetime.combine(value - timedelta(days=days - 1), time.min)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)
