from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_sources.market_classifier import normalize_markets
from app.data_sources.sector_mapping_client import SectorMappingClient, get_sector_mapping_client
from app.db.models import Industry, IndustryKeyword, Stock
from app.engines.industry_mapping_engine import is_unclassified
from app.pipeline.data_run import record_data_run


SECTOR_MAPPING_VERSION = "sector_industry_mapping_v1"


def run_sector_industry_mapping_job(
    session: Session,
    *,
    markets: tuple[str, ...] | None = None,
    client: SectorMappingClient | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc)
    market_scope = normalize_markets(markets, None) if markets else ("ALL",)
    if markets and "A" not in market_scope:
        return {
            "source": "sina_sector",
            "markets": list(market_scope),
            "members": 0,
            "updated": 0,
            "skipped_market": True,
        }

    client = client or get_sector_mapping_client()
    try:
        members = client.fetch_a_share_members()
    except Exception as exc:  # pragma: no cover - depends on external source
        session.rollback()
        record_data_run(
            session,
            job_name=SECTOR_MAPPING_VERSION,
            effective_source=getattr(client, "source", "sector_mapping"),
            markets=("A",),
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        logger.warning("sector industry mapping failed: {}", exc)
        return {
            "source": getattr(client, "source", "sector_mapping"),
            "markets": ["A"],
            "members": 0,
            "updated": 0,
            "failed": True,
            "error": str(exc),
        }

    by_code = {}
    ensured_industry_keywords: set[tuple[str, str]] = set()
    for member in members:
        by_code[member.code] = member
        keyword_key = (member.industry, member.raw_sector)
        if keyword_key not in ensured_industry_keywords:
            _ensure_industry(session, member.industry, member.raw_sector)
            ensured_industry_keywords.add(keyword_key)

    stocks = session.scalars(select(Stock).where(Stock.market == "A", Stock.asset_type == "equity")).all()
    updated = 0
    skipped_classified = 0
    missing_stock_members = 0
    by_industry: Counter[str] = Counter()
    samples: list[dict[str, object]] = []

    for stock in stocks:
        member = by_code.get(stock.code)
        if member is None:
            missing_stock_members += 1
            continue
        if not is_unclassified(stock.industry_level1):
            skipped_classified += 1
            continue
        updated += 1
        by_industry[member.industry] += 1
        if len(samples) < 20:
            samples.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "raw_sector": member.raw_sector,
                    "industry": member.industry,
                }
            )
        if dry_run:
            continue
        stock.industry_level1 = member.industry
        stock.industry_level2 = member.raw_sector
        stock.metadata_json = _merge_metadata(
            stock.metadata_json,
            {
                "version": SECTOR_MAPPING_VERSION,
                "source": member.source,
                "raw_sector": member.raw_sector,
                "industry": member.industry,
                "confidence": 0.82,
            },
        )

    if dry_run:
        session.rollback()
    else:
        session.commit()
        record_data_run(
            session,
            job_name=SECTOR_MAPPING_VERSION,
            effective_source=getattr(client, "source", "sector_mapping"),
            markets=("A",),
            status="success",
            rows_updated=updated,
            rows_total=len(stocks),
            started_at=started_at,
        )

    result = {
        "source": getattr(client, "source", "sector_mapping"),
        "markets": ["A"],
        "members": len(by_code),
        "stocks_seen": len(stocks),
        "updated": updated,
        "skipped_classified": skipped_classified,
        "missing_stock_members": missing_stock_members,
        "by_industry": dict(by_industry.most_common()),
        "samples": samples,
        "dry_run": dry_run,
    }
    logger.info("sector industry mapping completed: {}", result)
    return result


def _ensure_industry(session: Session, industry_name: str, raw_sector: str) -> None:
    industry = session.scalar(select(Industry).where(Industry.name == industry_name))
    if industry is None:
        industry = Industry(name=industry_name, description=f"由免费行业成分源映射维护：{raw_sector}")
        session.add(industry)
        session.flush()
    keyword = session.scalar(
        select(IndustryKeyword).where(IndustryKeyword.industry_id == industry.id, IndustryKeyword.keyword == raw_sector)
    )
    if keyword is None:
        session.add(IndustryKeyword(industry_id=industry.id, keyword=raw_sector, weight=1.0, is_active=True))


def _merge_metadata(raw_metadata: str | None, payload: dict[str, object]) -> str:
    try:
        metadata = json.loads(raw_metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[SECTOR_MAPPING_VERSION] = payload
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)
