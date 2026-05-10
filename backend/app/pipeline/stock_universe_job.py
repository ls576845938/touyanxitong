from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.data_sources.market_classifier import normalize_markets
from app.data_sources.mock_data import INDUSTRY_SEEDS
from app.data_sources.provider import get_market_data_client
from app.db.models import FundamentalMetric, Industry, IndustryKeyword, Stock
from app.pipeline.data_run import record_data_run


def run_stock_universe_job(session: Session, markets: tuple[str, ...] | None = None) -> dict[str, int]:
    requested_markets = normalize_markets(markets, settings.enabled_markets)
    client = get_market_data_client()
    started_at = datetime.now(timezone.utc)
    industry_count = 0
    keyword_count = 0
    inserted = 0
    updated = 0
    fundamental_upserts = 0

    try:
        for seed in INDUSTRY_SEEDS:
            industry = session.scalar(select(Industry).where(Industry.name == seed["name"]))
            if industry is None:
                industry = Industry(name=seed["name"], description=seed["description"])
                session.add(industry)
                session.flush()
                industry_count += 1
            else:
                industry.description = seed["description"]
            for keyword in seed["keywords"]:
                row = session.scalar(
                    select(IndustryKeyword).where(
                        IndustryKeyword.industry_id == industry.id,
                        IndustryKeyword.keyword == keyword,
                    )
                )
                if row is None:
                    session.add(IndustryKeyword(industry_id=industry.id, keyword=keyword, weight=1.0, is_active=True))
                    keyword_count += 1

        source_rows = client.fetch_stock_list(markets=requested_markets)
        source_rows_by_code: dict[str, dict] = {}
        duplicate_count = 0
        for item in source_rows:
            code = str(item["code"]).strip()
            if not code:
                continue
            if code in source_rows_by_code:
                duplicate_count += 1
            source_rows_by_code[code] = item
        if duplicate_count:
            logger.warning("stock universe source returned {} duplicate codes; keeping latest row per code", duplicate_count)
        effective_source = str(getattr(client, "last_effective_source", client.source))
        for item in source_rows_by_code.values():
            stock = session.scalar(select(Stock).where(Stock.code == item["code"]))
            industry_level1 = item["industry_level1"]
            industry_level2 = item["industry_level2"]
            concepts = item["concepts"] if isinstance(item["concepts"], str) else json.dumps(item["concepts"], ensure_ascii=False)
            if stock is not None and industry_level1 in {"", "未分类"} and stock.industry_level1 not in {"", "未分类"}:
                industry_level1 = stock.industry_level1
                industry_level2 = stock.industry_level2
                concepts = stock.concepts
            payload = {
                "name": item["name"],
                "market": item.get("market", "A"),
                "board": item.get("board", "main"),
                "exchange": item["exchange"],
                "industry_level1": industry_level1,
                "industry_level2": industry_level2,
                "concepts": concepts,
                "asset_type": item.get("asset_type", "equity"),
                "currency": item.get("currency", _currency_for_market(item.get("market", "A"))),
                "listing_status": item.get("listing_status", "listed"),
                "market_cap": float(item["market_cap"]),
                "float_market_cap": float(item["float_market_cap"]),
                "listing_date": item["listing_date"],
                "delisting_date": item.get("delisting_date"),
                "is_st": bool(item["is_st"]),
                "is_etf": bool(item.get("is_etf", False)),
                "is_adr": bool(item.get("is_adr", False)),
                "is_active": bool(item["is_active"]),
                "source": client.source,
                "data_vendor": item.get("data_vendor", effective_source),
                "metadata_json": item.get("metadata_json", "{}"),
            }
            if stock is None:
                session.add(Stock(code=str(item["code"]), **payload))
                inserted += 1
            else:
                for key, value in payload.items():
                    setattr(stock, key, value)
                updated += 1
        if hasattr(client, "fetch_fundamentals"):
            for item in client.fetch_fundamentals(markets=requested_markets):
                metric = session.scalar(
                    select(FundamentalMetric).where(
                        FundamentalMetric.stock_code == item["stock_code"],
                        FundamentalMetric.report_date == item["report_date"],
                        FundamentalMetric.period == item.get("period", "FY"),
                        FundamentalMetric.source == item.get("source", client.source),
                    )
                )
                payload = {
                    "revenue_growth_yoy": float(item.get("revenue_growth_yoy", 0.0) or 0.0),
                    "profit_growth_yoy": float(item.get("profit_growth_yoy", 0.0) or 0.0),
                    "gross_margin": float(item.get("gross_margin", 0.0) or 0.0),
                    "roe": float(item.get("roe", 0.0) or 0.0),
                    "debt_ratio": float(item.get("debt_ratio", 0.0) or 0.0),
                    "cashflow_quality": float(item.get("cashflow_quality", 0.0) or 0.0),
                    "report_title": item.get("report_title", ""),
                    "source_url": item.get("source_url", ""),
                }
                if metric is None:
                    session.add(
                        FundamentalMetric(
                            stock_code=item["stock_code"],
                            report_date=item["report_date"],
                            period=item.get("period", "FY"),
                            source=item.get("source", client.source),
                            **payload,
                        )
                    )
                else:
                    for key, value in payload.items():
                        setattr(metric, key, value)
                fundamental_upserts += 1
        session.commit()
        record_data_run(
            session,
            job_name="stock_universe",
            effective_source=effective_source,
            markets=requested_markets,
            status="success",
            rows_inserted=inserted,
            rows_updated=updated,
            rows_total=inserted + updated,
            started_at=started_at,
        )
        logger.info(
            "stock universe updated: inserted={}, updated={}, fundamentals={}, industries={}, keywords={}",
            inserted,
            updated,
            fundamental_upserts,
            industry_count,
            keyword_count,
        )
        return {
            "stocks": inserted + updated,
            "inserted": inserted,
            "updated": updated,
            "fundamentals": fundamental_upserts,
            "industries": industry_count,
            "keywords": keyword_count,
        }
    except Exception as exc:
        session.rollback()
        record_data_run(
            session,
            job_name="stock_universe",
            effective_source=client.source,
            markets=requested_markets,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        raise


def _currency_for_market(market: str) -> str:
    return {"A": "CNY", "US": "USD", "HK": "HKD"}.get(str(market).upper(), "CNY")
