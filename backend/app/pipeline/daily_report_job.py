from __future__ import annotations

import json
from datetime import date

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, DailyReport, EvidenceChain, IndustryHeat, Stock, StockScore, TrendSignal
from app.engines.report_context import build_report_context
from app.engines.report_engine import build_daily_report
from app.engines.retail_research_engine import build_retail_daily_context
from app.pipeline.utils import latest_available_date, latest_trade_date


def run_daily_report_job(session: Session, report_date: date | None = None) -> dict[str, int | str]:
    requested_date = report_date or latest_trade_date(session)
    target_date = latest_available_date(session, StockScore.trade_date, requested_date) or requested_date
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
    stocks_by_code = {stock.code: stock for stock in stocks}
    scores = session.scalars(select(StockScore).where(StockScore.trade_date == target_date)).all()
    heats = session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == target_date)).all()
    evidence = session.scalars(select(EvidenceChain).where(EvidenceChain.trade_date == target_date)).all()
    evidence_by_code = {item.stock_code: item for item in evidence}
    context = build_report_context(session, target_date)
    retail_context = build_retail_daily_context(session, target_date)
    covered_stock_count = session.scalar(
        select(func.count(func.distinct(DailyBar.stock_code))).where(DailyBar.trade_date <= target_date)
    )
    trend_signal_count = session.scalar(
        select(func.count(func.distinct(TrendSignal.stock_code))).where(TrendSignal.trade_date == target_date)
    )
    result = build_daily_report(
        target_date,
        heats,
        scores,
        evidence_by_code,
        stocks_by_code,
        data_quality=context["data_quality"],
        research_universe=context["research_universe"],
        watchlist_changes=context["watchlist_changes"],
        scan_summary={
            "security_master_count": len(stocks),
            "covered_stock_count": int(covered_stock_count or 0),
            "trend_signal_count": int(trend_signal_count or 0),
            "scored_stock_count": len(scores),
        },
        retail_research=retail_context,
    )
    payload = {
        "title": result.title,
        "market_summary": result.market_summary,
        "top_industries": json.dumps(result.top_industries, ensure_ascii=False),
        "top_trend_stocks": json.dumps(result.top_trend_stocks, ensure_ascii=False),
        "new_watchlist_stocks": json.dumps(result.new_watchlist_stocks, ensure_ascii=False),
        "risk_alerts": json.dumps(result.risk_alerts, ensure_ascii=False),
        "full_markdown": result.full_markdown,
    }
    existing = session.scalar(select(DailyReport).where(DailyReport.report_date == result.report_date))
    if existing is None:
        session.add(DailyReport(report_date=result.report_date, **payload))
        count = 1
    else:
        for key, value in payload.items():
            setattr(existing, key, value)
        count = 0
    session.commit()
    logger.info("daily report generated: {} (requested={}, effective={})", result.title, requested_date, target_date)
    return {"daily_reports": count, "report_date": target_date.isoformat()}
