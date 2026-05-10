from __future__ import annotations

from datetime import date

from app.db.session import SessionLocal, init_db
from app.pipeline.daily_report_job import run_daily_report_job
from app.pipeline.evidence_chain_job import run_evidence_chain_job
from app.pipeline.industry_heat_job import run_industry_heat_job
from app.pipeline.industry_mapping_job import run_industry_mapping_job
from app.pipeline.market_data_job import run_market_data_job
from app.pipeline.news_ingestion_job import run_news_ingestion_job
from app.pipeline.sector_industry_mapping_job import run_sector_industry_mapping_job
from app.pipeline.stock_universe_job import run_stock_universe_job
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job
from app.pipeline.trend_signal_job import run_trend_signal_job


def run_daily_pipeline(
    *,
    markets: tuple[str, ...] | None = None,
    max_stocks_per_market: int | None = None,
    stock_codes: tuple[str, ...] | None = None,
    end_date: date | None = None,
    periods: int | None = None,
    batch_offset: int = 0,
) -> dict[str, dict[str, int] | dict[str, str | int]]:
    init_db()
    target_date = end_date
    results: dict[str, dict[str, int] | dict[str, str | int]] = {}
    with SessionLocal() as session:
        results["stock_universe"] = run_stock_universe_job(session, markets=markets)
        results["sector_industry_mapping"] = run_sector_industry_mapping_job(session, markets=markets)
        results["industry_mapping"] = run_industry_mapping_job(session, markets=markets)
        results["market_data"] = run_market_data_job(
            session,
            end_date=end_date,
            markets=markets,
            max_stocks_per_market=max_stocks_per_market,
            stock_codes=stock_codes,
            periods=periods,
            batch_offset=batch_offset,
        )
        results["news_ingestion"] = run_news_ingestion_job(session, published_date=target_date)
        results["industry_heat"] = run_industry_heat_job(session, trade_date=target_date)
        results["trend_signal"] = run_trend_signal_job(session, trade_date=target_date)
        results["tenbagger_score"] = run_tenbagger_score_job(session, trade_date=target_date)
        results["evidence_chain"] = run_evidence_chain_job(session, trade_date=target_date)
        results["daily_report"] = run_daily_report_job(session, report_date=target_date)
    return results
