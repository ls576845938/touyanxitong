from __future__ import annotations

import email.utils
import html
import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Protocol
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs

from app.config import settings
from app.data_sources.mock_data import INDUSTRY_SEEDS, MockNewsClient

logger = logging.getLogger(__name__)


class NewsClient(Protocol):
    source: str
    source_kind: str
    source_confidence: float

    def fetch_articles(self, published_date: date | None = None) -> list[dict[str, Any]]:
        ...


def get_news_client() -> NewsClient:
    requested = settings.news_data_source.lower()
    if settings.mock_data or requested == "mock":
        return MockNewsClient()
    if requested in {"rss", "news"} and settings.news_rss_feeds:
        return RssNewsClient(settings.news_rss_feeds)
    if requested in {"auto", "rss", "news"}:
        return GoogleNewsRssClient()
    return MockNewsClient()


@dataclass(frozen=True)
class RssFeed:
    url: str
    query_context: str = ""


class RssNewsClient:
    source = "rss"
    source_kind = "rss"
    source_confidence = 0.8

    def __init__(
        self,
        feed_urls: Iterable[str | RssFeed],
        timeout_seconds: int = 8,
        max_items_per_feed: int = 20,
    ) -> None:
        self.feeds = tuple(_coerce_feed(feed) for feed in feed_urls)
        self.timeout_seconds = timeout_seconds
        self.max_items_per_feed = max_items_per_feed

    def fetch_articles(self, published_date: date | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for feed in self.feeds:
            try:
                rows.extend(self._fetch_feed(feed, published_date))
            except (OSError, ET.ParseError, TimeoutError, ValueError) as exc:
                logger.warning("news rss feed failed: url=%s error=%s", feed.url, exc)
        return _dedupe_articles(rows)

    def _fetch_feed(self, feed: RssFeed | str, published_date: date | None) -> list[dict[str, Any]]:
        feed = _coerce_feed(feed)
        feed_url = feed.url
        request = urllib.request.Request(feed_url, headers={"User-Agent": "AlphaRadar/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read()
        root = ET.fromstring(payload)
        feed_title = (
            _text(root.find("./channel/title"))
            or _text(root.find("{http://www.w3.org/2005/Atom}title"))
            or "rss"
        )
        items = list(root.findall("./channel/item"))
        if not items:
            items = list(root.findall("{http://www.w3.org/2005/Atom}entry"))
        return [
            row
            for row in (
                self._normalize_item(item, feed_url, feed_title, query_context=feed.query_context)
                for item in items[: self.max_items_per_feed]
            )
            if row is not None and (published_date is None or row["published_at"].date() == published_date)
        ]

    def _normalize_item(
        self, item: ET.Element, feed_url: str, feed_title: str, query_context: str = ""
    ) -> dict[str, Any] | None:
        title = _clean_text(_text(item.find("title")) or _text(item.find("{http://www.w3.org/2005/Atom}title")))
        if not title:
            return None
        summary = _clean_text(
            _text(item.find("description"))
            or _text(item.find("summary"))
            or _text(item.find("{http://www.w3.org/2005/Atom}summary"))
            or title
        )
        link = _link(item) or feed_url
        published_at = _published_at(item)
        matched_keywords, related_industries = _match_industry_terms(f"{title} {summary} {query_context}")
        return {
            "title": title,
            "content": summary,
            "summary": summary[:500],
            "source": feed_title[:64],
            "source_kind": self.source_kind,
            "source_confidence": self.source_confidence,
            "source_url": link,
            "published_at": published_at,
            "matched_keywords": json.dumps(matched_keywords, ensure_ascii=False),
            "related_industries": json.dumps(related_industries, ensure_ascii=False),
            "related_stocks": "[]",
        }


class GoogleNewsRssClient(RssNewsClient):
    source = "google_news_rss"
    source_kind = "rss"
    source_confidence = 0.8

    def __init__(self, timeout_seconds: int = 8, max_items_per_feed: int = 10) -> None:
        super().__init__(_google_news_feeds(), timeout_seconds=timeout_seconds, max_items_per_feed=max_items_per_feed)


def normalize_news_article(item: dict[str, Any], default_source: str = "news") -> dict[str, Any]:
    source = str(item.get("source") or default_source)
    source_kind = str(item.get("source_kind") or _infer_source_kind(source))
    source_confidence = float(item.get("source_confidence") or _default_source_confidence(source_kind))
    return {
        **item,
        "source": source[:64],
        "source_kind": source_kind[:24],
        "source_confidence": max(0.0, min(1.0, source_confidence)),
    }


def _infer_source_kind(source: str) -> str:
    normalized = source.lower()
    if normalized == "mock" or normalized.startswith("mock"):
        return "mock"
    if "rss" in normalized:
        return "rss"
    return "news"


def _default_source_confidence(source_kind: str) -> float:
    return {"mock": 0.3, "rss": 0.8, "news": 0.9}.get(source_kind, 0.6)


def _match_industry_terms(text: str) -> tuple[list[str], list[str]]:
    matched_keywords: list[str] = []
    related_industries: list[str] = []
    normalized = text.lower()
    for industry in INDUSTRY_SEEDS:
        industry_matched = False
        terms = _dedupe([str(industry["name"]), *(str(keyword) for keyword in industry["keywords"])])
        for term in terms:
            if term.lower() in normalized:
                matched_keywords.append(term)
                industry_matched = True
        if industry_matched:
            related_industries.append(str(industry["name"]))
    return _dedupe(matched_keywords), _dedupe(related_industries)


def _google_news_feeds() -> list[RssFeed]:
    feeds: list[RssFeed] = []
    for industry in INDUSTRY_SEEDS:
        terms = _dedupe([str(industry["name"]), *(str(keyword) for keyword in industry["keywords"])])
        query = " OR ".join(f'"{term}"' if " " in term else term for term in terms)
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )
        feeds.append(RssFeed(url=url, query_context=" ".join(terms)))
    return feeds


def _coerce_feed(feed: str | RssFeed) -> RssFeed:
    if isinstance(feed, RssFeed):
        return feed
    return RssFeed(url=str(feed), query_context=_query_context_from_url(str(feed)))


def _query_context_from_url(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    raw_query = parse_qs(parsed.query).get("q", [""])[0]
    return re.sub(r"\s+", " ", unquote_plus(raw_query).replace('"', " ").replace(" OR ", " ")).strip()


def _dedupe_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = _article_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _article_key(row: dict[str, Any]) -> str:
    source_url = str(row.get("source_url") or "").strip().lower()
    if source_url:
        return source_url
    return _clean_text(str(row.get("title") or "")).lower()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            rows.append(value)
    return rows


def _published_at(item: ET.Element) -> datetime:
    raw = (
        _text(item.find("pubDate"))
        or _text(item.find("published"))
        or _text(item.find("updated"))
        or _text(item.find("{http://www.w3.org/2005/Atom}published"))
        or _text(item.find("{http://www.w3.org/2005/Atom}updated"))
    )
    if raw:
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.combine(date.today(), time(9, 0), tzinfo=timezone.utc)


def _link(item: ET.Element) -> str:
    raw = _text(item.find("link")) or _text(item.find("{http://www.w3.org/2005/Atom}link"))
    if raw:
        return raw
    atom_link = item.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return str(atom_link.attrib.get("href") or "")
    return ""


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()
