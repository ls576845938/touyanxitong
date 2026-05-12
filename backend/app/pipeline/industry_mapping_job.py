from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_sources.market_classifier import normalize_markets
from app.data_sources.mock_data import INDUSTRY_SEEDS
from app.db.models import Industry, IndustryKeyword, Stock
from app.engines.industry_mapping_engine import (
    IndustryMappingMatch,
    build_mapping_rules,
    extract_mapping_metadata,
    is_unclassified,
    map_stock_industry,
    merge_mapping_metadata,
)
from app.pipeline.data_run import record_data_run


def run_industry_mapping_job(
    session: Session,
    *,
    markets: tuple[str, ...] | None = None,
    min_confidence: float = 0.35,
    dry_run: bool = False,
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc)
    market_scope = normalize_markets(markets, None) if markets else ("ALL",)
    rules = build_mapping_rules(_industry_keywords(session))
    query = select(Stock).where(Stock.asset_type == "equity")
    if markets:
        query = query.where(Stock.market.in_(market_scope))
    stocks = list(session.scalars(query.order_by(Stock.market, Stock.code)).all())

    mapped = 0
    fallback_mapped = 0
    unmapped = 0
    skipped_strong = 0
    below_confidence = 0
    by_industry: dict[str, int] = {}
    samples: list[dict[str, object]] = []

    try:
        for stock in stocks:
            if not is_unclassified(stock.industry_level1):
                skipped_strong += 1
                continue
            match = map_stock_industry(stock, rules)
            if match is None:
                match = _fallback_match(stock)
                fallback_mapped += 1
            elif match.confidence < min_confidence:
                fallback = _fallback_match(stock)
                if fallback is None:
                    below_confidence += 1
                    continue
                match = fallback
                fallback_mapped += 1
            else:
                mapped += 1
            if match is None:
                unmapped += 1
                continue
            by_industry[match.industry] = by_industry.get(match.industry, 0) + 1
            if len(samples) < 20:
                samples.append(
                    {
                        "code": stock.code,
                        "name": stock.name,
                        "market": stock.market,
                        "industry": match.industry,
                        "confidence": match.confidence,
                        "reason": match.reason,
                    }
                )
            if not dry_run:
                _ensure_industry(session, match.industry)
                stock.industry_level1 = match.industry
                stock.metadata_json = merge_mapping_metadata(stock.metadata_json, match)

        if not dry_run:
            session.commit()
            record_data_run(
                session,
                job_name="industry_mapping_v1",
                effective_source="rules-v1",
                markets=market_scope,
                status="success",
                rows_updated=mapped + fallback_mapped,
                rows_total=len(stocks),
                started_at=started_at,
            )
        else:
            session.rollback()
    except Exception as exc:
        session.rollback()
        record_data_run(
            session,
            job_name="industry_mapping_v1",
            effective_source="rules-v1",
            markets=market_scope,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        raise

    result = {
        "total_stocks": len(stocks),
        "eligible_unclassified": mapped + fallback_mapped + unmapped + below_confidence,
        "mapped": mapped,
        "fallback_mapped": fallback_mapped,
        "unmapped": unmapped,
        "below_confidence": below_confidence,
        "skipped_strong": skipped_strong,
        "by_industry": dict(sorted(by_industry.items(), key=lambda item: item[1], reverse=True)),
        "samples": samples,
        "dry_run": dry_run,
    }
    logger.info("industry mapping v1 completed: {}", result)
    return result


def industry_mapping_summary(session: Session, *, markets: tuple[str, ...] | None = None) -> dict[str, object]:
    market_scope = normalize_markets(markets, None) if markets else None
    filters = [Stock.asset_type == "equity"]
    if market_scope:
        filters.append(Stock.market.in_(market_scope))

    total = session.scalar(select(func.count()).select_from(Stock).where(*filters)) or 0
    unclassified = session.scalar(
        select(func.count()).select_from(Stock).where(*filters, Stock.industry_level1.in_(["", "未分类", "未知", "未知行业"]))
    ) or 0
    industry_rows = session.execute(
        select(Stock.industry_level1, func.count(Stock.id)).where(*filters).group_by(Stock.industry_level1)
    ).all()
    mapped_stock_rows = session.scalars(
        select(Stock).where(*filters).order_by(Stock.updated_at.desc(), Stock.id.desc())
    ).all()
    mapped_samples = []
    mapped_count = 0
    for stock in mapped_stock_rows:
        mapping = extract_mapping_metadata(stock.metadata_json)
        if not mapping:
            continue
        mapped_count += 1
        if len(mapped_samples) < 20:
            mapped_samples.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "market": stock.market,
                    "industry": stock.industry_level1,
                    "confidence": mapping.get("confidence"),
                    "reason": mapping.get("reason"),
                }
            )

    return {
        "total_stocks": int(total),
        "unclassified_count": int(unclassified),
        "classified_count": int(total) - int(unclassified),
        "mapped_metadata_sample_count": mapped_count,
        "markets": list(market_scope) if market_scope else ["ALL"],
        "by_industry": [
            {"industry": industry or "未分类", "stock_count": int(count or 0)}
            for industry, count in sorted(industry_rows, key=lambda row: int(row[1] or 0), reverse=True)
        ],
        "mapped_samples": mapped_samples,
    }


def _industry_keywords(session: Session) -> dict[str, list[str]]:
    industries = {row.id: row.name for row in session.scalars(select(Industry)).all()}
    keywords: dict[str, list[str]] = {name: [] for name in industries.values()}
    for row in session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True))).all():
        industry = industries.get(row.industry_id)
        if industry:
            keywords.setdefault(industry, []).append(row.keyword)
    if keywords:
        return keywords
    return {str(seed["name"]): [str(item) for item in seed["keywords"]] for seed in INDUSTRY_SEEDS}


def _ensure_industry(session: Session, industry_name: str) -> None:
    if session.scalar(select(Industry).where(Industry.name == industry_name)) is None:
        session.add(Industry(name=industry_name, description="由行业映射规则自动补充。"))
        session.flush()


def _fallback_match(stock: Stock) -> IndustryMappingMatch:
    market = str(stock.market or "").upper() or "UNKNOWN"
    confidence = 0.18
    reason = (
        "低置信度兜底分类到综合行业：规则库、名称模式和概念字段均未给出可验证行业，"
        "该标签仅用于避免页面进入未分类桶，不作为强行业判断。"
    )
    return IndustryMappingMatch(
        industry="综合行业",
        confidence=confidence,
        reason=reason,
        matched_keywords=("fallback_unclassified",),
        evidence=(
            {"field": "market", "keyword": market},
            {"field": "name", "keyword": str(stock.name or "")[:32]},
        ),
    )
