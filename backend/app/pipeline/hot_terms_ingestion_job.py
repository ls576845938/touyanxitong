from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_sources.hot_terms_client import HotTermsSourceClient, HotTermsSourceItem, HotTermsSourceResult
from app.db.models import DataSourceRun, Industry, IndustryKeyword, NewsArticle


@dataclass(frozen=True)
class IndustryTermMatcher:
    terms_by_industry: dict[str, list[str]]
    aliases_by_industry: dict[str, list[str]]

    def match(self, text: str) -> tuple[list[str], list[str], dict[str, list[str] | str]]:
        keyword_matches: list[str] = []
        industry_matches: list[str] = []
        alias_matches: list[str] = []
        for industry, terms in self.terms_by_industry.items():
            industry_matched = False
            for term in terms:
                clean = term.strip()
                if clean and _term_matches_text(text, clean):
                    if clean == industry:
                        industry_matches.append(clean)
                    else:
                        keyword_matches.append(clean)
                    industry_matched = True
            for alias in self.aliases_by_industry.get(industry, []):
                clean = alias.strip()
                if clean and _term_matches_text(text, clean):
                    alias_matches.append(clean)
                    industry_matched = True
            if industry_matched:
                industry_matches.append(industry)
        matched_keywords = _dedupe_strings([*keyword_matches, *industry_matches])[:16]
        related_industries = _dedupe_strings(industry_matches)[:8]
        reasons = _build_match_reason(keyword_matches, industry_matches, alias_matches)
        return matched_keywords, related_industries, reasons


def run_hot_terms_ingestion_job(
    session: Session,
    *,
    source_keys: Sequence[str] | None = None,
    limit_per_source: int = 12,
    timeout_seconds: int = 5,
    client: HotTermsSourceClient | None = None,
) -> dict[str, Any]:
    client = client or HotTermsSourceClient(timeout_seconds=timeout_seconds)
    matcher = _industry_term_matcher(session)
    results = client.fetch_all(source_keys=source_keys, limit_per_source=limit_per_source)

    inserted_total = 0
    skipped_total = 0
    source_payloads: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc)

    for result in results:
        inserted = 0
        skipped = 0
        irrelevant = 0
        for item in result.items:
            if bool(getattr(item, "is_synthetic", False)):
                irrelevant += 1
                continue
            article = _normalize_hot_source_item(item, matcher)
            if not _article_has_industry_signal(article):
                irrelevant += 1
                continue
            if _existing_article_id(session, article) is not None:
                skipped += 1
                continue
            session.add(NewsArticle(**article))
            inserted += 1

        _record_hot_terms_source_run(
            session,
            result,
            inserted=inserted,
            skipped=skipped,
            irrelevant=irrelevant,
            started_at=started_at,
        )
        inserted_total += inserted
        skipped_total += skipped
        source_payloads.append(
            {
                "key": result.key,
                "label": result.label,
                "status": result.status,
                "fetched": len(result.items),
                "inserted": inserted,
                "skipped": skipped,
                "irrelevant": irrelevant,
                "error": result.error,
            }
        )

    session.commit()
    failed = sum(1 for result in results if result.status == "failed")
    status = "failed" if failed == len(results) and results else "partial" if failed else "success"
    payload = {
        "status": status,
        "inserted": inserted_total,
        "skipped": skipped_total,
        "failed_sources": failed,
        "source_count": len(results),
        "sources": source_payloads,
    }
    logger.info(
        "hot terms ingested: status={} inserted={} skipped={} failed_sources={}",
        status,
        inserted_total,
        skipped_total,
        failed,
    )
    return payload


def _industry_term_matcher(session: Session) -> IndustryTermMatcher:
    rows = session.execute(
        select(IndustryKeyword, Industry)
        .join(Industry, Industry.id == IndustryKeyword.industry_id)
        .where(IndustryKeyword.is_active.is_(True))
    ).all()
    terms_by_industry: dict[str, list[str]] = defaultdict(list)
    for keyword, industry in rows:
        terms_by_industry[industry.name].extend([industry.name, keyword.keyword])
    normalized_terms = {industry: _dedupe_strings(terms) for industry, terms in terms_by_industry.items()}
    return IndustryTermMatcher(normalized_terms, _industry_aliases(normalized_terms.keys()))


def _normalize_hot_source_item(item: HotTermsSourceItem, matcher: IndustryTermMatcher) -> dict[str, Any]:
    text = " ".join(value for value in [item.title, item.summary, item.channel] if value)
    matched_keywords, related_industries, match_reason = matcher.match(text)
    published_at = item.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    summary = item.summary or item.title
    return {
        "title": item.title[:500],
        "content": summary[:2000],
        "summary": summary[:500],
        "source": item.source_key[:64],
        "source_kind": item.source_kind[:24],
        "source_confidence": max(0.0, min(1.0, float(item.source_confidence))),
        "source_channel": item.channel[:64],
        "source_label": item.source_label[:64],
        "source_rank": max(0, int(item.rank)),
        "source_url": item.source_url,
        "published_at": published_at.astimezone(timezone.utc),
        "matched_keywords": json.dumps(matched_keywords, ensure_ascii=False),
        "related_industries": json.dumps(related_industries, ensure_ascii=False),
        "related_stocks": "[]",
        "match_reason": json.dumps(match_reason, ensure_ascii=False),
        "is_synthetic": bool(getattr(item, "is_synthetic", False)),
    }


def _article_has_industry_signal(article: dict[str, Any]) -> bool:
    return bool(_loads_json_list(str(article["matched_keywords"])) or _loads_json_list(str(article["related_industries"])))


def _existing_article_id(session: Session, article: dict[str, Any]) -> int | None:
    source_url = str(article.get("source_url") or "").strip()
    if source_url:
        existing = session.scalar(select(NewsArticle.id).where(NewsArticle.source_url == source_url))
        if existing is not None:
            return int(existing)
    return session.scalar(
        select(NewsArticle.id).where(
            NewsArticle.source == str(article["source"]),
            NewsArticle.title == str(article["title"]),
        )
    )


def _record_hot_terms_source_run(
    session: Session,
    result: HotTermsSourceResult,
    *,
    inserted: int,
    skipped: int,
    irrelevant: int,
    started_at: datetime,
) -> None:
    source_kind = {
        "professional_media": "professional",
        "market_media": "market_media",
        "community": "community",
        "broker": "broker",
    }.get(result.kind, result.kind[:16])
    session.add(
        DataSourceRun(
            job_name=f"hot_terms_{result.key}",
            requested_source="hot_terms",
            effective_source=result.key,
            source_kind=source_kind[:16],
            source_confidence=_source_confidence(result.kind),
            markets="[]",
            status=result.status if result.status in {"success", "partial", "failed", "empty"} else "partial",
            rows_inserted=inserted,
            rows_updated=skipped,
            rows_total=inserted + skipped + irrelevant,
            error=_run_error(result.error, irrelevant),
            started_at=started_at,
            finished_at=result.fetched_at or datetime.now(timezone.utc),
        )
    )


def _source_confidence(kind: str) -> float:
    return {
        "professional_media": 0.82,
        "market_media": 0.76,
        "broker": 0.8,
        "community": 0.56,
    }.get(kind, 0.6)


def _run_error(error: str, irrelevant: int) -> str:
    parts = [error] if error else []
    if irrelevant:
        parts.append(f"irrelevant_filtered={irrelevant}")
    return "; ".join(parts)[:1000]


def _loads_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _build_match_reason(
    keyword_matches: Sequence[str],
    industry_matches: Sequence[str],
    alias_matches: Sequence[str],
) -> dict[str, list[str] | str]:
    keyword = _dedupe_strings(keyword_matches)[:16]
    industry = _dedupe_strings(industry_matches)[:8]
    alias = _dedupe_strings(alias_matches)[:16]
    primary = "none"
    if keyword:
        primary = "keyword"
    elif alias:
        primary = "alias"
    elif industry:
        primary = "industry"
    return {
        "primary": primary,
        "keyword": keyword,
        "industry": industry,
        "alias": alias,
        "unmatched": ["none"] if primary == "none" else [],
    }


def _term_matches_text(text: str, term: str) -> bool:
    clean = term.strip()
    if not clean:
        return False
    normalized = text.lower()
    lowered = clean.lower()
    if _is_ascii_token(lowered):
        return re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", normalized) is not None
    return lowered in normalized


def _is_ascii_token(value: str) -> bool:
    return bool(value) and all(ord(char) < 128 for char in value)


def _industry_aliases(industry_names: Sequence[str]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for industry in industry_names:
        normalized = industry.lower()
        terms: list[str] = []
        if any(flag in normalized for flag in ["半导体", "芯片", "ai算力"]):
            terms.extend(["ai", "chip", "chips", "semiconductor", "semiconductors", "nvidia", "intel"])
        if any(flag in normalized for flag in ["新能源车", "汽车", "动力电池"]):
            terms.extend(["ev", "electric vehicle", "electric vehicles", "battery", "batteries"])
        if any(flag in normalized for flag in ["油气", "能源"]):
            terms.extend(["oil", "gas", "lng", "crude", "aramco"])
        if any(flag in normalized for flag in ["黄金", "贵金属"]):
            terms.extend(["gold", "silver", "precious metals"])
        if "机器人" in normalized:
            terms.extend(["robot", "robots", "robotics"])
        if "低空" in normalized or "无人机" in normalized:
            terms.extend(["drone", "drones", "evtol"])
        if "创新药" in normalized or "医药" in normalized:
            terms.extend(["drug", "drugs", "pharma", "biotech", "wegovy"])
        if "银行" in normalized:
            terms.extend(["bank", "banks", "credit"])
        if "物流" in normalized or "航运" in normalized:
            terms.extend(["shipping", "logistics", "freight"])
        if "军工" in normalized or "卫星" in normalized:
            terms.extend(["defense", "military", "satellite", "space"])
        if terms:
            aliases[industry] = terms
    return aliases


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(value)
    return rows
