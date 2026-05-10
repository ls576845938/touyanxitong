from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_sources.news_client import get_news_client
from app.data_sources.news_client import normalize_news_article
from app.db.models import NewsArticle


def run_news_ingestion_job(session: Session, published_date: date | None = None, client=None) -> dict[str, int]:
    client = client or get_news_client()
    inserted = 0
    skipped = 0
    for item in client.fetch_articles(published_date=published_date):
        item = normalize_news_article(item, default_source=getattr(client, "source", "news"))
        existing = session.scalar(select(NewsArticle).where(NewsArticle.source_url == item["source_url"]))
        if existing is not None:
            skipped += 1
            continue
        session.add(NewsArticle(**item))
        inserted += 1
    session.commit()
    logger.info("news ingested: inserted={}, skipped={}", inserted, skipped)
    return {"inserted": inserted, "skipped": skipped}
