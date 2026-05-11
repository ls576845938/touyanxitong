from __future__ import annotations

from app.data_sources.hot_terms_client import HOT_TERMS_SOURCE_MAP, HotTermsSourceClient


class FailingHotTermsClient(HotTermsSourceClient):
    def _read_url(self, url: str) -> bytes:
        raise OSError("network blocked")


class EmptyFeedHotTermsClient(HotTermsSourceClient):
    def _read_url(self, url: str) -> bytes:
        return b"<?xml version='1.0' encoding='UTF-8'?><rss><channel></channel></rss>"


class RssFixtureHotTermsClient(HotTermsSourceClient):
    def _read_url(self, url: str) -> bytes:
        return b"""<?xml version='1.0' encoding='UTF-8'?>
<rss>
  <channel>
    <item>
      <title>Chip stocks rally as AI server demand accelerates</title>
      <link>https://example.com/chips-rally</link>
      <description>Semiconductor suppliers and AI infrastructure names led market gains.</description>
      <pubDate>Mon, 11 May 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Chip stocks rally as AI server demand accelerates</title>
      <link>https://example.com/chips-rally</link>
      <description>Duplicate item should be deduplicated by source URL.</description>
      <pubDate>Mon, 11 May 2026 08:01:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_tonghuashun_marks_failure_without_synthetic_fallback() -> None:
    client = FailingHotTermsClient()

    result = client.fetch_source(HOT_TERMS_SOURCE_MAP["tonghuashun"], limit_per_source=3)

    assert result.status == "failed"
    assert result.items == []
    assert "network blocked" in result.error
    assert "industry_fallback" not in result.error


def test_wsj_empty_feed_reports_diagnostic_without_synthetic_items() -> None:
    client = EmptyFeedHotTermsClient()

    result = client.fetch_source(HOT_TERMS_SOURCE_MAP["wsj"], limit_per_source=2)

    assert result.status == "empty"
    assert result.items == []
    assert "returned no parseable hot terms" in result.error
    assert "industry_fallback" not in result.error


def test_wsj_source_uses_multiple_industry_discovery_feeds() -> None:
    urls = " ".join(endpoint.url for endpoint in HOT_TERMS_SOURCE_MAP["wsj"].endpoints)

    assert "Nvidia" in urls
    assert "semiconductor" in urls
    assert "EV" in urls
    assert "oil" in urls


def test_tonghuashun_source_uses_narrow_board_endpoints() -> None:
    urls = {endpoint.url for endpoint in HOT_TERMS_SOURCE_MAP["tonghuashun"].endpoints}

    assert "https://stock.10jqka.com.cn/fupan/" in urls
    assert "https://q.10jqka.com.cn/gn/" in urls
    assert "https://q.10jqka.com.cn/thshy/" in urls
    assert all("today_list" not in url for url in urls)
    assert all("stocknews_list" not in url for url in urls)


def test_professional_media_alternative_sources_exist() -> None:
    for source_key in ("reuters_markets", "cnbc_markets", "marketwatch", "barrons", "investing"):
        source = HOT_TERMS_SOURCE_MAP[source_key]
        assert source.kind in {"professional_media", "market_media"}
        assert any(endpoint.kind == "rss" for endpoint in source.endpoints)


def test_alternative_english_source_parses_rss_without_synthetic_items() -> None:
    client = RssFixtureHotTermsClient()

    result = client.fetch_source(HOT_TERMS_SOURCE_MAP["reuters_markets"], limit_per_source=2)

    assert result.status == "success"
    assert len(result.items) == 1
    assert result.items[0].source_key == "reuters_markets"
    assert result.items[0].channel == "google_markets_1d"
    assert result.items[0].title == "Chip stocks rally as AI server demand accelerates"
    assert result.items[0].source_url == "https://example.com/chips-rally"
    assert "synthetic" not in result.error.lower()
