from __future__ import annotations

import email.utils
import html
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import quote_plus, urljoin

logger = logging.getLogger(__name__)

EndpointKind = Literal["rss", "html"]


@dataclass(frozen=True)
class HotTermsEndpoint:
    url: str
    kind: EndpointKind
    channel: str
    fallback: bool = False


@dataclass(frozen=True)
class HotTermsSource:
    key: str
    label: str
    kind: str
    confidence: float
    endpoints: tuple[HotTermsEndpoint, ...]


@dataclass(frozen=True)
class HotTermsSourceItem:
    source_key: str
    source_label: str
    source_kind: str
    source_confidence: float
    channel: str
    title: str
    summary: str
    source_url: str
    published_at: datetime
    rank: int = 0


@dataclass(frozen=True)
class HotTermsSourceResult:
    key: str
    label: str
    kind: str
    status: str
    items: list[HotTermsSourceItem]
    error: str = ""
    fetched_at: datetime | None = None


def _google_site_feed(site: str, query: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(f'site:{site} {query}')}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    )


def _google_news_feed(query: str, *, hl: str = "en-US", gl: str = "US", ceid: str = "US:en") -> str:
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={quote_plus(hl)}&gl={quote_plus(gl)}&ceid={quote_plus(ceid)}"
    )


HOT_TERMS_SOURCES: tuple[HotTermsSource, ...] = (
    HotTermsSource(
        key="xueqiu",
        label="雪球",
        kind="community",
        confidence=0.58,
        endpoints=(
            HotTermsEndpoint("https://xueqiu.com/hot/spot", "html", "hot_spot"),
            HotTermsEndpoint(_google_site_feed("xueqiu.com", "股票 热点"), "rss", "google_site", fallback=True),
        ),
    ),
    HotTermsSource(
        key="reddit",
        label="Reddit",
        kind="community",
        confidence=0.56,
        endpoints=(
            HotTermsEndpoint("https://www.reddit.com/r/stocks/.rss", "rss", "r/stocks"),
            HotTermsEndpoint("https://www.reddit.com/r/investing/.rss", "rss", "r/investing"),
            HotTermsEndpoint("https://www.reddit.com/r/wallstreetbets/.rss", "rss", "r/wallstreetbets"),
        ),
    ),
    HotTermsSource(
        key="tonghuashun",
        label="同花顺",
        kind="market_media",
        confidence=0.74,
        endpoints=(
            HotTermsEndpoint("https://stock.10jqka.com.cn/fupan/", "html", "review_hot_boards"),
            HotTermsEndpoint("https://q.10jqka.com.cn/gn/", "html", "concept_boards"),
            HotTermsEndpoint("https://q.10jqka.com.cn/thshy/", "html", "industry_boards"),
            HotTermsEndpoint(
                _google_site_feed("10jqka.com.cn", "q.10jqka.com.cn AI算力 光模块 半导体 机器人 新能源车 低空经济 概念 板块 when:7d"),
                "rss",
                "google_concept_industry_site",
                fallback=True,
            ),
        ),
    ),
    HotTermsSource(
        key="eastmoney",
        label="东方财富",
        kind="market_media",
        confidence=0.76,
        endpoints=(
            HotTermsEndpoint("https://group.eastmoney.com/HotMarket.html", "html", "hot_market"),
            HotTermsEndpoint("https://stock.eastmoney.com/", "html", "stock", fallback=True),
        ),
    ),
    HotTermsSource(
        key="taoguba",
        label="淘股吧",
        kind="community",
        confidence=0.54,
        endpoints=(HotTermsEndpoint("https://www.tgb.cn/", "html", "home"),),
    ),
    HotTermsSource(
        key="ibkr",
        label="盈透",
        kind="broker",
        confidence=0.82,
        endpoints=(
            HotTermsEndpoint("https://www.interactivebrokers.com/en/general/about/press-releases.php", "html", "press_releases"),
            HotTermsEndpoint("https://www.interactivebrokers.com/en/about/news-at-ibkr.php", "html", "news_at_ibkr", fallback=True),
        ),
    ),
    HotTermsSource(
        key="wsj",
        label="华尔街日报",
        kind="professional_media",
        confidence=0.78,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:wsj.com markets stocks earnings when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:wsj.com Nvidia AI chips semiconductor stocks when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:wsj.com EV battery electric vehicles autos when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:wsj.com oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
    HotTermsSource(
        key="reuters_markets",
        label="Reuters Markets",
        kind="professional_media",
        confidence=0.8,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:reuters.com/markets stocks earnings market when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:reuters.com/technology AI semiconductor Nvidia when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:reuters.com/business/autos-transportation EV battery electric vehicle when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:reuters.com/business/energy oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
    HotTermsSource(
        key="cnbc_markets",
        label="CNBC Markets",
        kind="market_media",
        confidence=0.77,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:cnbc.com/markets stocks market when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:cnbc.com AI chips semiconductor Nvidia when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:cnbc.com EV battery autos Tesla when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:cnbc.com oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
    HotTermsSource(
        key="marketwatch",
        label="MarketWatch",
        kind="market_media",
        confidence=0.76,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:marketwatch.com stocks market earnings when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:marketwatch.com AI semiconductor Nvidia chips when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:marketwatch.com EV battery autos when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:marketwatch.com oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
    HotTermsSource(
        key="barrons",
        label="Barron's",
        kind="professional_media",
        confidence=0.77,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:barrons.com stocks market earnings when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:barrons.com AI semiconductor Nvidia chips when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:barrons.com EV battery autos when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:barrons.com oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
    HotTermsSource(
        key="investing",
        label="Investing.com",
        kind="market_media",
        confidence=0.72,
        endpoints=(
            HotTermsEndpoint(_google_news_feed("site:investing.com/news stocks market earnings when:1d"), "rss", "google_markets_1d"),
            HotTermsEndpoint(_google_news_feed("site:investing.com/news AI semiconductor Nvidia chips when:7d"), "rss", "google_ai_semis", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:investing.com/news EV battery autos when:7d"), "rss", "google_ev_battery", fallback=True),
            HotTermsEndpoint(_google_news_feed("site:investing.com/news oil gas energy commodities when:7d"), "rss", "google_energy", fallback=True),
        ),
    ),
)

HOT_TERMS_SOURCE_MAP = {source.key: source for source in HOT_TERMS_SOURCES}

_DIAGNOSTIC_SOURCE_KEYS = frozenset({"tonghuashun", "wsj"})


class HotTermsSourceClient:
    def __init__(self, timeout_seconds: int = 5, user_agent: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; AlphaRadar/0.1; +https://localhost)"
        )

    def fetch_all(
        self,
        *,
        source_keys: Sequence[str] | None = None,
        limit_per_source: int = 12,
    ) -> list[HotTermsSourceResult]:
        requested = {key.strip() for key in source_keys or () if key.strip()}
        sources = [source for source in HOT_TERMS_SOURCES if not requested or source.key in requested]
        return [self.fetch_source(source, limit_per_source=limit_per_source) for source in sources]

    def fetch_source(self, source: HotTermsSource, *, limit_per_source: int = 12) -> HotTermsSourceResult:
        fetched_at = datetime.now(timezone.utc)
        items: list[HotTermsSourceItem] = []
        fetch_errors: list[str] = []
        empty_channels: list[str] = []
        seen: set[str] = set()
        for endpoint in source.endpoints:
            if len(items) >= limit_per_source:
                break
            try:
                raw_items = self._fetch_endpoint(source, endpoint, limit=max(limit_per_source - len(items), 1))
            except (OSError, TimeoutError, ET.ParseError, ValueError) as exc:
                fetch_errors.append(f"{endpoint.channel}: {exc}")
                logger.warning("hot terms source failed: source=%s url=%s error=%s", source.key, endpoint.url, exc)
                continue
            if not raw_items and source.key in _DIAGNOSTIC_SOURCE_KEYS:
                empty_channels.append(endpoint.channel)
            for item in raw_items:
                key = _item_key(item)
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
                if len(items) >= limit_per_source:
                    break
        diagnostics = [_empty_channel_error(source, empty_channels)] if source.key in _DIAGNOSTIC_SOURCE_KEYS and empty_channels else []
        errors = [*fetch_errors, *diagnostics]
        if items and errors:
            status = "partial"
        elif items:
            status = "success"
        elif fetch_errors:
            status = "failed"
        else:
            status = "empty"
        return HotTermsSourceResult(
            key=source.key,
            label=source.label,
            kind=source.kind,
            status=status,
            items=items,
            error="; ".join(errors)[:1000],
            fetched_at=fetched_at,
        )

    def _fetch_endpoint(
        self,
        source: HotTermsSource,
        endpoint: HotTermsEndpoint,
        *,
        limit: int,
    ) -> list[HotTermsSourceItem]:
        payload = self._read_url(endpoint.url)
        if endpoint.kind == "rss":
            return _parse_rss_payload(source, endpoint, payload, limit=limit)
        return _parse_html_payload(source, endpoint, payload, limit=limit)

    def _read_url(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read()


class _AnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth > 0:
            return
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if tag != "a" or self._href is None:
            return
        text = _clean_text(" ".join(self._text_parts))
        href = urljoin(self.base_url, self._href)
        self._href = None
        self._text_parts = []
        if _looks_like_title(text) and href.startswith(("http://", "https://")):
            self.anchors.append((text, href))

    def handle_data(self, data: str) -> None:
        if self._href is not None and self._ignored_depth == 0:
            self._text_parts.append(data)


def _parse_rss_payload(
    source: HotTermsSource,
    endpoint: HotTermsEndpoint,
    payload: bytes,
    *,
    limit: int,
) -> list[HotTermsSourceItem]:
    root = ET.fromstring(payload)
    rows: list[HotTermsSourceItem] = []
    items = list(root.findall("./channel/item"))
    if items:
        for rank, item in enumerate(items[:limit], start=1):
            row = _rss_item_to_row(source, endpoint, item, rank)
            if row is not None:
                rows.append(row)
        return rows
    entries = list(root.findall("{http://www.w3.org/2005/Atom}entry"))
    for rank, entry in enumerate(entries[:limit], start=1):
        row = _rss_item_to_row(source, endpoint, entry, rank)
        if row is not None:
            rows.append(row)
    return rows


def _parse_html_payload(
    source: HotTermsSource,
    endpoint: HotTermsEndpoint,
    payload: bytes,
    *,
    limit: int,
) -> list[HotTermsSourceItem]:
    text = _decode_html(payload)
    parser = _AnchorParser(endpoint.url)
    parser.feed(text)
    rows: list[HotTermsSourceItem] = []
    seen: set[str] = set()
    for title, url in parser.anchors:
        if source.key == "tonghuashun" and not _is_tonghuashun_article_url(url):
            continue
        key = url.lower() if source.key == "tonghuashun" else f"{title.lower()}|{url.lower()}"
        if key in seen or _is_low_signal_link(title, url):
            continue
        seen.add(key)
        rows.append(
            HotTermsSourceItem(
                source_key=source.key,
                source_label=source.label,
                source_kind=source.kind,
                source_confidence=source.confidence,
                channel=endpoint.channel,
                title=title,
                summary="",
                source_url=url,
                published_at=datetime.now(timezone.utc),
                rank=len(rows) + 1,
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _rss_item_to_row(
    source: HotTermsSource,
    endpoint: HotTermsEndpoint,
    item: ET.Element,
    rank: int,
) -> HotTermsSourceItem | None:
    title = _clean_text(
        _element_text(item.find("title")) or _element_text(item.find("{http://www.w3.org/2005/Atom}title"))
    )
    if not title:
        return None
    summary = _clean_text(
        _element_text(item.find("description"))
        or _element_text(item.find("summary"))
        or _element_text(item.find("{http://www.w3.org/2005/Atom}summary"))
        or _element_text(item.find("{http://www.w3.org/2005/Atom}content"))
    )
    return HotTermsSourceItem(
        source_key=source.key,
        source_label=source.label,
        source_kind=source.kind,
        source_confidence=source.confidence,
        channel=endpoint.channel,
        title=title,
        summary=summary[:500],
        source_url=_rss_link(item) or endpoint.url,
        published_at=_rss_published_at(item),
        rank=rank,
    )


def _rss_link(item: ET.Element) -> str:
    raw = _element_text(item.find("link")) or _element_text(item.find("{http://www.w3.org/2005/Atom}link"))
    if raw:
        return raw
    atom_link = item.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return str(atom_link.attrib.get("href") or "")
    return ""


def _rss_published_at(item: ET.Element) -> datetime:
    raw = (
        _element_text(item.find("pubDate"))
        or _element_text(item.find("published"))
        or _element_text(item.find("updated"))
        or _element_text(item.find("{http://www.w3.org/2005/Atom}published"))
        or _element_text(item.find("{http://www.w3.org/2005/Atom}updated"))
    )
    if raw:
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _element_text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _looks_like_title(text: str) -> bool:
    if not (4 <= len(text) <= 96):
        return False
    if text.lower() in {"login", "register", "more", "首页", "登录", "注册", "更多", "广告"}:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", text))


def _is_low_signal_link(title: str, url: str) -> bool:
    normalized = f"{title} {url}".lower()
    low_signal = (
        "javascript:",
        "mailto:",
        "login",
        "register",
        "privacy",
        "cookie",
        "advert",
        "download",
        "客户端",
        "登录",
        "注册",
    )
    return any(flag in normalized for flag in low_signal)


def _is_tonghuashun_article_url(url: str) -> bool:
    return bool(re.search(r"//(?:news|stock|yuanchuang)\.10jqka\.com\.cn/20\d{6}/c\d+\.shtml", url))


def _item_key(item: HotTermsSourceItem) -> str:
    if item.source_url:
        return item.source_url.strip().lower()
    return f"{item.source_key}:{item.title.strip().lower()}"


def _empty_channel_error(source: HotTermsSource, channels: Sequence[str]) -> str:
    unique_channels = ", ".join(dict.fromkeys(channel for channel in channels if channel))
    return f"{source.label} returned no parseable hot terms from channels: {unique_channels}"


def source_keys() -> Iterable[str]:
    return HOT_TERMS_SOURCE_MAP.keys()
