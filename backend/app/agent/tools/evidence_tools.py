from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceChain, EvidenceEvent, Industry, IndustryKeyword, NewsArticle
from app.services.stock_resolver import resolve_stock


def get_stock_evidence(session: Session, symbol: str | None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol or "")
    if stock is None:
        return {"status": "unavailable", "message": f"未识别股票：{symbol or ''}", "source_refs": []}
    evidence = session.scalars(
        select(EvidenceChain)
        .where(EvidenceChain.stock_code == stock.code)
        .order_by(EvidenceChain.trade_date.desc())
        .limit(1)
    ).first()
    if evidence is None:
        return {"status": "unavailable", "message": f"{stock.name} 暂无证据链", "source_refs": []}
    return {
        "status": "ok",
        "code": stock.code,
        "name": stock.name,
        "trade_date": evidence.trade_date.isoformat(),
        "summary": evidence.summary,
        "industry_logic": evidence.industry_logic,
        "company_logic": evidence.company_logic,
        "trend_logic": evidence.trend_logic,
        "catalyst_logic": evidence.catalyst_logic,
        "risk_summary": evidence.risk_summary,
        "questions_to_verify": _loads_list(evidence.questions_to_verify),
        "source_refs": _loads_list(evidence.source_refs),
        "data_source": "evidence_chain",
    }


def get_industry_evidence(session: Session, keyword: str | None, limit: int = 12) -> dict[str, Any]:
    industry_names, keywords = _industry_terms(session, keyword)
    articles = _matching_articles(session, industry_names, keywords, limit=limit)
    if not articles:
        return {
            "status": "unavailable",
            "message": f"{keyword or '行业'} 暂无近期结构化证据",
            "summary": "当前行业证据不足。",
            "articles": [],
            "source_refs": [],
        }
    refs = [
        {"title": row["title"], "source": row["source"], "url": row["source_url"], "published_at": row["published_at"]}
        for row in articles
    ]
    return {
        "status": "ok",
        "keyword": keyword or "",
        "summary": f"找到 {len(articles)} 条近期行业证据，需继续区分真实来源、模拟来源和低置信度来源。",
        "articles": articles,
        "source_refs": refs,
        "data_source": "news_article",
    }


def get_recent_catalysts(session: Session, symbol_or_industry: str | None, limit: int = 10) -> dict[str, Any]:
    stock = resolve_stock(session, symbol_or_industry or "")
    terms = {symbol_or_industry or ""}
    if stock is not None:
        terms.update({stock.code, stock.name, stock.industry_level1, stock.industry_level2})
    industry_names, keywords = _industry_terms(session, symbol_or_industry)
    terms.update(industry_names)
    terms.update(keywords)

    article_rows = _matching_articles(session, industry_names | {stock.industry_level1} if stock else industry_names, terms, limit=limit)
    event_rows = []
    events = session.scalars(select(EvidenceEvent).order_by(EvidenceEvent.event_time.desc()).limit(120)).all()
    for event in events:
        text = " ".join(
            [
                event.title,
                event.summary,
                event.logic_chain,
                " ".join(str(item) for item in _loads_list(event.affected_objects)),
            ]
        )
        if any(term and term in text for term in terms):
            event_rows.append(
                {
                    "id": event.id,
                    "title": event.title,
                    "summary": event.summary,
                    "source_name": event.source_name,
                    "source_url": event.source_url,
                    "event_time": event.event_time.isoformat(),
                    "confidence": event.confidence,
                    "impact_direction": event.impact_direction,
                    "risk_notes": event.risk_notes,
                }
            )
        if len(event_rows) >= limit:
            break
    if not article_rows and not event_rows:
        return {"status": "unavailable", "message": "近期催化数据不足", "catalysts": []}
    return {
        "status": "ok",
        "catalysts": article_rows[:limit] + event_rows[:limit],
        "data_source": "news_article/evidence_event",
    }


def get_evidence_summary(session: Session, symbol_or_keyword: str | None) -> dict[str, Any]:
    stock = resolve_stock(session, symbol_or_keyword or "")
    if stock is not None:
        return get_stock_evidence(session, stock.code)
    return get_industry_evidence(session, symbol_or_keyword)


def _industry_terms(session: Session, keyword: str | None) -> tuple[set[str], set[str]]:
    value = (keyword or "").strip()
    industry_names: set[str] = set()
    keywords: set[str] = {value} if value else set()
    if value:
        like = f"%{value.replace(' ', '')}%"
        industries = session.scalars(select(Industry).where(Industry.name.ilike(like)).limit(10)).all()
        industry_names.update(row.name for row in industries)
        keyword_rows = session.scalars(select(IndustryKeyword).where(IndustryKeyword.keyword.ilike(like)).limit(20)).all()
        keywords.update(row.keyword for row in keyword_rows)
        for row in keyword_rows:
            industry = session.get(Industry, row.industry_id)
            if industry is not None:
                industry_names.add(industry.name)
    return industry_names, keywords


def _matching_articles(session: Session, industries: set[str], keywords: set[str], limit: int = 12) -> list[dict[str, Any]]:
    rows = []
    articles = session.scalars(select(NewsArticle).order_by(NewsArticle.published_at.desc()).limit(300)).all()
    compact_keywords = {item.replace(" ", "") for item in keywords if item}
    for article in articles:
        article_industries = {str(item) for item in _loads_list(article.related_industries)}
        article_keywords = {str(item) for item in _loads_list(article.matched_keywords)}
        text = f"{article.title}{article.summary}".replace(" ", "")
        if not (article_industries & industries or article_keywords & keywords or any(item and item in text for item in compact_keywords)):
            continue
        rows.append(
            {
                "title": article.title,
                "summary": article.summary,
                "source": article.source,
                "source_kind": getattr(article, "source_kind", "mock"),
                "source_confidence": getattr(article, "source_confidence", 0.3),
                "source_url": article.source_url,
                "published_at": article.published_at.isoformat(),
                "matched_keywords": list(article_keywords),
                "related_industries": list(article_industries),
                "related_stocks": _loads_list(article.related_stocks),
                "is_synthetic": bool(getattr(article, "is_synthetic", False)),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _loads_list(raw: str | None) -> list[Any]:
    import json

    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []
