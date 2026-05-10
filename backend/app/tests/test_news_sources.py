from __future__ import annotations

import json
from types import SimpleNamespace

from app.data_sources import news_client
from app.data_sources.mock_data import INDUSTRY_SEEDS
from app.data_sources.news_client import GoogleNewsRssClient, RssFeed, RssNewsClient, get_news_client


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


def test_get_news_client_auto_uses_free_google_news_rss(monkeypatch) -> None:
    monkeypatch.setattr(
        news_client,
        "settings",
        SimpleNamespace(mock_data=False, news_data_source="auto", news_rss_feeds=()),
    )

    client = get_news_client()

    assert isinstance(client, GoogleNewsRssClient)
    assert client.source == "google_news_rss"
    assert client.source_kind == "rss"


def test_google_news_feeds_cover_industry_names_and_keywords() -> None:
    feeds = news_client._google_news_feeds()
    joined_context = " ".join(feed.query_context for feed in feeds)

    assert len(feeds) == len(INDUSTRY_SEEDS)
    assert all(feed.url.startswith("https://news.google.com/rss/search?") for feed in feeds)
    for seed in INDUSTRY_SEEDS:
        assert seed["name"] in joined_context
        for keyword in seed["keywords"]:
            assert keyword in joined_context


def test_auto_client_limits_items_and_uses_fake_urlopen(monkeypatch) -> None:
    payload = """
    <rss><channel><title>Google News</title>
      <item>
        <title>AI服务器订单增长</title>
        <description>光模块需求提升</description>
        <link>https://example.com/a</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
      <item>
        <title>第二条不应抓取</title>
        <description>机器人</description>
        <link>https://example.com/b</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    seen_urls: list[str] = []

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        return FakeResponse(payload)

    monkeypatch.setattr(news_client.urllib.request, "urlopen", fake_urlopen)
    client = RssNewsClient(
        [RssFeed("https://news.google.com/rss/search?q=AI%E7%AE%97%E5%8A%9B", "AI算力")],
        max_items_per_feed=1,
    )

    rows = client.fetch_articles()

    assert seen_urls == ["https://news.google.com/rss/search?q=AI%E7%AE%97%E5%8A%9B"]
    assert len(rows) == 1
    assert rows[0]["source_kind"] == "rss"
    assert rows[0]["source_confidence"] == 0.8
    assert json.loads(rows[0]["matched_keywords"])


def test_rss_client_continues_when_one_feed_fails(monkeypatch) -> None:
    payload = """
    <rss><channel><title>Fixture RSS</title>
      <item>
        <title>机器人融资进展</title>
        <description>产业链订单改善</description>
        <link>https://example.com/robot</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def fake_urlopen(request, timeout):
        if "bad-feed" in request.full_url:
            raise OSError("network failed")
        return FakeResponse(payload)

    monkeypatch.setattr(news_client.urllib.request, "urlopen", fake_urlopen)
    client = RssNewsClient(
        [
            RssFeed("https://example.com/bad-feed.xml", "半导体 芯片"),
            RssFeed("https://example.com/good-feed.xml", "机器人"),
        ]
    )

    rows = client.fetch_articles()

    assert len(rows) == 1
    assert rows[0]["source_url"] == "https://example.com/robot"
    assert "机器人" in json.loads(rows[0]["related_industries"])


def test_query_context_matches_industry_when_title_and_summary_do_not_repeat_keywords(monkeypatch) -> None:
    payload = """
    <rss><channel><title>Search Feed</title>
      <item>
        <title>新产线验证通过</title>
        <description>公司披露阶段性进展</description>
        <link>https://example.com/solid-state</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    monkeypatch.setattr(news_client.urllib.request, "urlopen", lambda request, timeout: FakeResponse(payload))
    client = RssNewsClient([RssFeed("https://example.com/rss.xml", "固态电池 电解质")])

    row = client.fetch_articles()[0]

    assert "固态电池" in json.loads(row["matched_keywords"])
    assert json.loads(row["related_industries"]) == ["固态电池"]


def test_query_context_can_match_industry_name_not_present_in_keyword_list(monkeypatch) -> None:
    payload = """
    <rss><channel><title>Search Feed</title>
      <item>
        <title>订单进展更新</title>
        <description>公司披露阶段性进展</description>
        <link>https://example.com/software-service</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    monkeypatch.setattr(news_client.urllib.request, "urlopen", lambda request, timeout: FakeResponse(payload))
    client = RssNewsClient([RssFeed("https://example.com/rss.xml", "软件服务")])

    row = client.fetch_articles()[0]

    assert "软件服务" in json.loads(row["matched_keywords"])
    assert json.loads(row["related_industries"]) == ["软件服务"]


def test_rss_client_dedupes_and_normalizes_articles(monkeypatch) -> None:
    payload = """
    <rss><channel><title>Fixture RSS</title>
      <item>
        <title> AI算力 &amp; 光模块 </title>
        <description><![CDATA[<p>CPO&nbsp;需求提升</p>]]></description>
        <link>https://example.com/duplicate</link>
        <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    monkeypatch.setattr(news_client.urllib.request, "urlopen", lambda request, timeout: FakeResponse(payload))
    client = RssNewsClient(
        [
            RssFeed("https://example.com/feed-a.xml", "AI算力"),
            RssFeed("https://example.com/feed-b.xml", "AI算力"),
        ]
    )

    rows = client.fetch_articles()

    assert len(rows) == 1
    assert rows[0]["title"] == "AI算力 & 光模块"
    assert rows[0]["summary"] == "CPO 需求提升"
    assert rows[0]["source"] == "Fixture RSS"
    assert rows[0]["source_url"] == "https://example.com/duplicate"
