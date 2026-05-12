from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.data_sources.hot_terms_client import HOT_TERMS_SOURCE_MAP, HotTermsEndpoint, HotTermsSourceItem, HotTermsSourceResult, _parse_html_payload
from app.data_sources.mock_data import MockMarketDataClient
from app.db.models import Base, DailyBar, DailyReport, DataIngestionBatch, DataSourceRun, EvidenceChain, FundamentalMetric, Industry, IndustryKeyword, NewsArticle, Stock, StockScore, TenbaggerThesis, TrendSignal, utcnow
from app.pipeline.industry_mapping_job import run_industry_mapping_job
from app.pipeline.daily_report_job import run_daily_report_job
from app.pipeline.evidence_chain_job import run_evidence_chain_job
from app.pipeline.industry_heat_job import run_industry_heat_job
from app.pipeline.ingestion_task_service import claim_next_ingestion_task, create_ingestion_task, enqueue_ingestion_backfill, priority_candidates, run_ingestion_task, run_next_ingestion_task, task_payload
from app.pipeline.hot_terms_ingestion_job import run_hot_terms_ingestion_job
from app.pipeline.market_data_job import run_market_data_job
from app.pipeline.news_ingestion_job import run_news_ingestion_job
from app.pipeline.retail_research_daily import retail_research_payload
from app.pipeline.sector_industry_mapping_job import run_sector_industry_mapping_job
from app.pipeline.stock_universe_job import run_stock_universe_job
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job
from app.pipeline.tenbagger_thesis_job import run_tenbagger_thesis_job
from app.pipeline.trend_signal_job import run_trend_signal_job


class RealSourceMockMarketDataClient(MockMarketDataClient):
    source = "tencent+akshare+mock_fallback"
    last_effective_source = "tencent"

    def fetch_daily_bars(self, stock_code: str, market: str | None = None, end_date: date | None = None, periods: int = 320):
        rows = super().fetch_daily_bars(stock_code, market=market, end_date=end_date, periods=periods)
        real_source = "akshare" if (market or "").upper() == "US" else "tencent"
        self.last_effective_source = real_source
        for row in rows:
            row["source"] = real_source
            row["source_kind"] = "real"
            row["source_confidence"] = 1.0
        return rows


class FakeSectorMappingClient:
    source = "fixture_sector"

    def fetch_a_share_members(self):
        from app.data_sources.sector_mapping_client import SectorIndustryMember

        return [
            SectorIndustryMember(code="000001", name="平安银行", raw_sector="金融行业", industry="银行"),
            SectorIndustryMember(code="600150", name="中国船舶", raw_sector="船舶制造", industry="军工信息化"),
        ]


def test_sector_industry_mapping_job_updates_a_share_unclassified_stocks() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="000001",
                    name="平安银行",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="未分类",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="600150",
                    name="中国船舶",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="未分类",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="AAPL",
                    name="Apple",
                    market="US",
                    board="main",
                    exchange="NASDAQ",
                    industry_level1="未分类",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        result = run_sector_industry_mapping_job(session, client=FakeSectorMappingClient())
        bank = session.scalar(select(Stock).where(Stock.code == "000001"))
        ship = session.scalar(select(Stock).where(Stock.code == "600150"))
        us_stock = session.scalar(select(Stock).where(Stock.code == "AAPL"))

        assert result["updated"] == 2
        assert bank is not None and bank.industry_level1 == "银行"
        assert ship is not None and ship.industry_level1 == "军工信息化"
        assert "sector_industry_mapping_v1" in ship.metadata_json
        assert us_stock is not None and us_stock.industry_level1 == "未分类"
        assert session.scalar(select(Industry).where(Industry.name == "军工信息化")) is not None


def test_industry_mapping_job_maps_only_unclassified_stocks() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ai = Industry(name="AI算力", description="")
        robot = Industry(name="机器人", description="")
        session.add_all([ai, robot])
        session.flush()
        session.add_all(
            [
                IndustryKeyword(industry_id=ai.id, keyword="光模块", weight=1.0, is_active=True),
                IndustryKeyword(industry_id=ai.id, keyword="CPO", weight=1.0, is_active=True),
                IndustryKeyword(industry_id=robot.id, keyword="减速器", weight=1.0, is_active=True),
                Stock(
                    code="MAP1",
                    name="测试光模块",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="未分类",
                    industry_level2="光模块",
                    concepts='["CPO"]',
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="KEEP1",
                    name="强分类样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="半导体",
                    industry_level2="光模块",
                    concepts='["CPO"]',
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        result = run_industry_mapping_job(session)
        mapped = session.scalar(select(Stock).where(Stock.code == "MAP1"))
        kept = session.scalar(select(Stock).where(Stock.code == "KEEP1"))
        run = session.scalar(select(DataSourceRun).where(DataSourceRun.job_name == "industry_mapping_v1"))

        assert result["mapped"] == 1
        assert result["skipped_strong"] == 1
        assert mapped is not None
        assert mapped.industry_level1 == "AI算力"
        assert "industry_mapping_v1" in mapped.metadata_json
        assert kept is not None
        assert kept.industry_level1 == "半导体"
        assert run is not None
        assert run.status == "success"


def test_daily_pipeline_jobs_are_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        run_stock_universe_job(session)
        run_market_data_job(session, client=RealSourceMockMarketDataClient())
        run_news_ingestion_job(session)
        run_industry_heat_job(session)
        run_trend_signal_job(session)
        run_tenbagger_score_job(session)
        run_evidence_chain_job(session)
        run_tenbagger_thesis_job(session)
        run_daily_report_job(session)

        stock_count = len(session.scalars(select(Stock)).all())
        markets = {row.market for row in session.scalars(select(Stock)).all()}
        a_boards = {row.board for row in session.scalars(select(Stock).where(Stock.market == "A")).all()}
        trend_count = len(session.scalars(select(TrendSignal)).all())
        score_count = len(session.scalars(select(StockScore)).all())
        thesis_count = len(session.scalars(select(TenbaggerThesis)).all())
        evidence_count = len(session.scalars(select(EvidenceChain)).all())
        fundamental_count = len(session.scalars(select(FundamentalMetric)).all())
        report_count = len(session.scalars(select(DailyReport)).all())
        report = session.scalar(select(DailyReport))
        retail = retail_research_payload(session)
        data_runs = session.scalars(select(DataSourceRun)).all()

        assert stock_count >= 5
        assert markets == {"A", "US", "HK"}
        assert {"main", "chinext", "star", "bse"}.issubset(a_boards)
        assert trend_count == stock_count
        assert score_count == stock_count
        assert thesis_count == stock_count
        assert evidence_count == stock_count
        assert fundamental_count == stock_count
        assert report_count == 1
        assert report is not None
        assert "## 零售线索候选" in report.full_markdown
        assert retail["summary"]["candidate_count"] == stock_count
        assert retail["top_candidates"]
        assert all(score.company_score > 0 for score in session.scalars(select(StockScore)).all())
        assert any("营收同比" in chain.company_logic for chain in session.scalars(select(EvidenceChain)).all())
        assert {row.job_name for row in data_runs} == {"stock_universe", "market_data"}
        assert {row.status for row in data_runs} == {"success"}

        run_market_data_job(session, client=RealSourceMockMarketDataClient())
        run_news_ingestion_job(session)
        run_trend_signal_job(session)
        run_tenbagger_score_job(session)
        run_evidence_chain_job(session)
        run_tenbagger_thesis_job(session)
        run_daily_report_job(session)

        assert len(session.scalars(select(TrendSignal)).all()) == trend_count
        assert len(session.scalars(select(StockScore)).all()) == score_count
        assert len(session.scalars(select(TenbaggerThesis)).all()) == thesis_count
        assert len(session.scalars(select(EvidenceChain)).all()) == evidence_count
        assert len(session.scalars(select(FundamentalMetric)).all()) == fundamental_count
        assert len(session.scalars(select(DailyReport)).all()) == report_count

        limited = run_market_data_job(session, markets=("A",), max_stocks_per_market=1, periods=10, client=MockMarketDataClient())
        assert limited["stocks_requested"] >= 1
        assert limited["stocks_processed"] == 1
        assert limited["skipped_by_limit"] >= 1
        assert limited["periods"] == 10


def test_downstream_jobs_fall_back_to_latest_available_signal_snapshot() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        run_stock_universe_job(session)
        run_market_data_job(session, client=RealSourceMockMarketDataClient())
        run_news_ingestion_job(session)
        run_industry_heat_job(session)
        run_trend_signal_job(session)

        signal_date = session.scalars(select(TrendSignal.trade_date).order_by(TrendSignal.trade_date.desc()).limit(1)).first()
        assert signal_date is not None
        sparse_date = signal_date + timedelta(days=3)
        stock = session.scalars(select(Stock).order_by(Stock.code).limit(1)).first()
        assert stock is not None
        session.add(
            DailyBar(
                stock_code=stock.code,
                trade_date=sparse_date,
                open=10,
                high=11,
                low=9,
                close=10.5,
                pre_close=10,
                volume=1000,
                amount=10_000,
                pct_chg=5,
                adj_factor=1,
                source="sparse_fixture",
                source_kind="mock",
                source_confidence=0.2,
            )
        )
        session.commit()

        score_result = run_tenbagger_score_job(session)
        evidence_result = run_evidence_chain_job(session)
        thesis_result = run_tenbagger_thesis_job(session)
        report_result = run_daily_report_job(session)

        assert score_result["effective_date"] == signal_date.isoformat()
        assert evidence_result["effective_date"] == signal_date.isoformat()
        assert thesis_result["effective_date"] == signal_date.isoformat()
        assert report_result["report_date"] == signal_date.isoformat()
        assert session.scalar(select(StockScore).where(StockScore.trade_date == sparse_date)) is None
        assert session.scalar(select(EvidenceChain).where(EvidenceChain.trade_date == sparse_date)) is None


def test_news_ingestion_persists_source_metadata() -> None:
    class OneArticleClient:
        source = "fixture"

        def fetch_articles(self, published_date=None):
            return [
                {
                    "title": "AI算力真实资讯样本",
                    "content": "光模块需求提升",
                    "summary": "光模块需求提升",
                    "source": "Fixture RSS",
                    "source_kind": "rss",
                    "source_confidence": 0.8,
                    "source_url": "https://example.com/news/1",
                    "published_at": date(2026, 5, 8),
                    "matched_keywords": '["AI算力", "光模块"]',
                    "related_industries": '["AI算力"]',
                    "related_stocks": "[]",
                }
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        result = run_news_ingestion_job(session, client=OneArticleClient())
        article = session.scalar(select(NewsArticle))

        assert result == {"inserted": 1, "skipped": 0}
        assert article is not None
        assert article.source_kind == "rss"
        assert article.source_confidence == 0.8


def test_hot_terms_ingestion_persists_external_source_and_is_idempotent() -> None:
    class OneHotTermsClient:
        def fetch_all(self, source_keys=None, limit_per_source=12):
            return [
                HotTermsSourceResult(
                    key="reddit",
                    label="Reddit",
                    kind="community",
                    status="success",
                    items=[
                        HotTermsSourceItem(
                            source_key="reddit",
                            source_label="Reddit",
                            source_kind="community",
                            source_confidence=0.56,
                            channel="r/stocks",
                            title="光模块 demand is rising with AI算力 capex",
                            summary="CPO and optical module supply chain discussion",
                            source_url="https://reddit.test/r/stocks/1",
                            published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
                            rank=1,
                        ),
                        HotTermsSourceItem(
                            source_key="reddit",
                            source_label="Reddit",
                            source_kind="community",
                            source_confidence=0.56,
                            channel="r/stocks",
                            title="Weekend portfolio chat with no mapped industry signal",
                            summary="General discussion without investable industry keywords",
                            source_url="https://reddit.test/r/stocks/noise",
                            published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
                            rank=2,
                        )
                    ],
                )
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        industry = Industry(name="AI算力", description="")
        session.add(industry)
        session.flush()
        session.add(IndustryKeyword(industry_id=industry.id, keyword="光模块", weight=1.0, is_active=True))
        session.commit()

        result = run_hot_terms_ingestion_job(session, client=OneHotTermsClient())
        article = session.scalar(select(NewsArticle).where(NewsArticle.source == "reddit"))
        run = session.scalar(select(DataSourceRun).where(DataSourceRun.job_name == "hot_terms_reddit"))

        assert result["inserted"] == 1
        assert result["skipped"] == 0
        assert result["sources"][0]["irrelevant"] == 1
        assert article is not None
        assert article.source_kind == "community"
        assert article.source_channel == "r/stocks"
        assert article.source_label == "Reddit"
        assert article.source_rank == 1
        assert article.is_synthetic is False
        assert {"AI算力", "光模块"}.issubset(set(json.loads(article.matched_keywords)))
        assert json.loads(article.related_industries) == ["AI算力"]
        assert json.loads(article.match_reason) == {
            "primary": "keyword",
            "keyword": ["光模块"],
            "industry": ["AI算力"],
            "alias": ["ai"],
            "unmatched": [],
        }
        assert run is not None
        assert run.status == "success"

        second = run_hot_terms_ingestion_job(session, client=OneHotTermsClient())
        assert second["inserted"] == 0
        assert second["skipped"] == 1


def test_hot_terms_ingestion_skips_synthetic_items() -> None:
    class SyntheticHotTermsItem:
        def __init__(self) -> None:
            self.source_key = "reddit"
            self.source_label = "Reddit"
            self.source_kind = "community"
            self.source_confidence = 0.56
            self.channel = "r/stocks"
            self.title = "AI算力 synthetic placeholder should never be stored"
            self.summary = "光模块 synthetic summary"
            self.source_url = "https://reddit.test/r/stocks/synthetic"
            self.published_at = datetime(2026, 5, 8, tzinfo=timezone.utc)
            self.rank = 1
            self.is_synthetic = True

    class SyntheticHotTermsClient:
        def fetch_all(self, source_keys=None, limit_per_source=12):
            return [
                HotTermsSourceResult(
                    key="reddit",
                    label="Reddit",
                    kind="community",
                    status="success",
                    items=[SyntheticHotTermsItem()],
                )
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        industry = Industry(name="AI算力", description="")
        session.add(industry)
        session.flush()
        session.add(IndustryKeyword(industry_id=industry.id, keyword="光模块", weight=1.0, is_active=True))
        session.commit()

        result = run_hot_terms_ingestion_job(session, client=SyntheticHotTermsClient())

        assert result["inserted"] == 0
        assert result["sources"][0]["irrelevant"] == 1
        assert session.scalar(select(NewsArticle.id)) is None


def test_hot_terms_ingestion_requires_word_boundary_for_short_latin_aliases() -> None:
    class NoisyHotTermsClient:
        def fetch_all(self, source_keys=None, limit_per_source=12):
            return [
                HotTermsSourceResult(
                    key="reddit",
                    label="Reddit",
                    kind="community",
                    status="success",
                    items=[
                        HotTermsSourceItem(
                            source_key="reddit",
                            source_label="Reddit",
                            source_kind="community",
                            source_confidence=0.56,
                            channel="r/stocks",
                            title="Retail pain trade is plain market chatter",
                            summary="Said again without any mapped industry evidence.",
                            source_url="https://reddit.test/r/stocks/noisy-ai-substring",
                            published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
                            rank=1,
                        ),
                        HotTermsSourceItem(
                            source_key="reddit",
                            source_label="Reddit",
                            source_kind="community",
                            source_confidence=0.56,
                            channel="r/stocks",
                            title="Nvidia AI server capex lifts optical module demand",
                            summary="AI infrastructure orders are still the core discussion.",
                            source_url="https://reddit.test/r/stocks/ai-server",
                            published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
                            rank=2,
                        ),
                        HotTermsSourceItem(
                            source_key="reddit",
                            source_label="Reddit",
                            source_kind="community",
                            source_confidence=0.56,
                            channel="r/investing",
                            title="Seven automakers discussed broad demand but no breakout",
                            summary="The word seven should not trigger the short alias itself.",
                            source_url="https://reddit.test/r/investing/seven-automakers",
                            published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
                            rank=3,
                        ),
                    ],
                )
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ai_industry = Industry(name="AI算力", description="")
        ev_industry = Industry(name="新能源车", description="")
        session.add_all([ai_industry, ev_industry])
        session.flush()
        session.add_all(
            [
                IndustryKeyword(industry_id=ai_industry.id, keyword="光模块", weight=1.0, is_active=True),
                IndustryKeyword(industry_id=ev_industry.id, keyword="电池", weight=1.0, is_active=True),
            ]
        )
        session.commit()

        result = run_hot_terms_ingestion_job(session, client=NoisyHotTermsClient())
        articles = session.scalars(select(NewsArticle).where(NewsArticle.source == "reddit")).all()

        assert result["inserted"] == 1
        assert result["sources"][0]["irrelevant"] == 2
        assert len(articles) == 1
        assert articles[0].source_url.endswith("/ai-server")
        assert json.loads(articles[0].related_industries) == ["AI算力"]
        assert json.loads(articles[0].match_reason) == {
            "primary": "alias",
            "keyword": [],
            "industry": ["AI算力"],
            "alias": ["ai", "nvidia"],
            "unmatched": [],
        }


def test_tonghuashun_hot_terms_parser_keeps_article_links_only() -> None:
    source = HOT_TERMS_SOURCE_MAP["tonghuashun"]
    endpoint = HotTermsEndpoint("https://news.10jqka.com.cn/today_list/", "html", "today")
    payload = """
    <html><body>
      <a href="http://stock.10jqka.com.cn/">股票</a>
      <a href="http://news.10jqka.com.cn/today_list/">财经要闻</a>
      <a href="http://news.10jqka.com.cn/20260511/c676588198.shtml">金融精准支持科技创新</a>
      <a href="http://news.10jqka.com.cn/20260511/c676588198.shtml">金融机构进一步加强服务的长段落摘要</a>
      <a href="http://stock.10jqka.com.cn/20260511/c676500001.shtml">芯片设备板块热度提升</a>
    </body></html>
    """.encode()

    items = _parse_html_payload(source, endpoint, payload, limit=10)

    assert [item.title for item in items] == ["金融精准支持科技创新", "芯片设备板块热度提升"]
    assert all("10jqka.com.cn/20260511/c" in item.source_url for item in items)


def test_wsj_hot_terms_uses_recent_google_news_discovery() -> None:
    urls = [endpoint.url for endpoint in HOT_TERMS_SOURCE_MAP["wsj"].endpoints]

    assert any("when%3A1d" in url for url in urls)


def test_trend_signal_job_uses_research_universe_gate() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    start = date(2025, 1, 1)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="GOOD",
                    name="合格样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="AI算力",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    market_cap=500,
                    float_market_cap=300,
                    is_active=True,
                    is_st=False,
                    source="mock",
                    data_vendor="mock",
                ),
                Stock(
                    code="SHORT",
                    name="历史不足样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="AI算力",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    market_cap=500,
                    float_market_cap=300,
                    is_active=True,
                    is_st=False,
                    source="mock",
                    data_vendor="mock",
                ),
            ]
        )
        for code, count in {"GOOD": 160, "SHORT": 80}.items():
            for idx in range(count):
                session.add(
                    DailyBar(
                        stock_code=code,
                        trade_date=start + timedelta(days=idx),
                        open=10 + idx * 0.01,
                        high=10.5 + idx * 0.01,
                        low=9.5 + idx * 0.01,
                        close=10.2 + idx * 0.01,
                        pre_close=10,
                        volume=1_000_000,
                        amount=50_000_000,
                            pct_chg=0.1,
                            adj_factor=1.0,
                            source="tencent",
                            source_kind="real",
                            source_confidence=1.0,
                        )
                    )
        session.add(TrendSignal(stock_code="SHORT", trade_date=start + timedelta(days=159), trend_score=99))
        session.commit()

        result = run_trend_signal_job(session, trade_date=start + timedelta(days=159))
        signals = session.scalars(select(TrendSignal)).all()

        assert result["trend_signals"] == 1
        assert {signal.stock_code for signal in signals} == {"GOOD"}


def test_market_data_batch_fails_when_provider_has_no_usable_bars() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            Stock(
                code="NO_BARS",
                name="无行情样本",
                market="A",
                board="main",
                exchange="SSE",
                industry_level1="未分类",
                industry_level2="",
                asset_type="equity",
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()

        result = run_market_data_job(
            session,
            markets=("A",),
            max_stocks_per_market=1,
            periods=60,
            client=MockMarketDataClient(),
        )
        batch = session.scalars(select(DataIngestionBatch)).first()
        run = session.scalars(select(DataSourceRun)).first()

        assert result["stocks_processed"] == 1
        assert result["missing_stocks"] == 1
        assert result["status"] == "failed"
        assert batch is not None
        assert batch.status == "failed"
        assert batch.failed == 1
        assert run is not None
        assert run.status == "failed"
        assert result["failed_symbols"] == [{"code": "NO_BARS", "market": "A", "error": "no_usable_bars"}]
        assert "NO_BARS:no_usable_bars" in batch.error


def test_market_data_job_marks_mock_bars_as_low_confidence() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            Stock(
                code="300308",
                name="中际旭创",
                market="A",
                board="chinext",
                exchange="SZSE",
                industry_level1="未分类",
                industry_level2="",
                asset_type="equity",
                is_etf=False,
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()

        result = run_market_data_job(session, markets=("A",), max_stocks_per_market=1, periods=60, client=MockMarketDataClient())
        bar = session.scalars(select(DailyBar).where(DailyBar.stock_code == "300308")).first()
        run = session.scalars(select(DataSourceRun).where(DataSourceRun.job_name == "market_data")).first()

        assert result["status"] == "success"
        assert bar is not None
        assert bar.source == "mock"
        assert bar.source_kind == "mock"
        assert bar.source_confidence == 0.1
        assert run is not None
        assert run.source_kind == "mock"
        assert run.source_confidence == 0.1


def test_no_usable_bars_ingestion_task_is_terminal() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            Stock(
                code="NO_BARS",
                name="无行情样本",
                market="A",
                board="main",
                exchange="SSE",
                industry_level1="未分类",
                industry_level2="",
                asset_type="equity",
                is_etf=False,
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()
        task = create_ingestion_task(session, task_type="single", market="A", stock_code="NO_BARS", source="mock", periods=60)

        result = run_ingestion_task(session, task)
        next_task = claim_next_ingestion_task(session)

        assert result.status == "failed"
        assert result.retry_count == result.max_retries + 1
        assert "NO_BARS:no_usable_bars" in result.error
        assert next_task is None


def test_ingestion_task_claim_does_not_duplicate_running_task() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        task = create_ingestion_task(session, task_type="batch", market="A", source="mock")

        claimed = claim_next_ingestion_task(session, worker_id="worker-a", lease_seconds=300)
        duplicate = claim_next_ingestion_task(session, worker_id="worker-b", lease_seconds=300)

        assert claimed is not None
        assert claimed.id == task.id
        assert duplicate is None
        payload = task_payload(claimed)
        assert payload["status"] == "running"
        assert payload["worker_id"] == "worker-a"
        assert payload["lease_expires_at"] is not None
        assert payload["heartbeat_at"] is not None
        assert payload["progress"] == 0.0


def test_ingestion_task_claim_recovers_stale_running_task() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        task = create_ingestion_task(session, task_type="batch", market="A", source="mock")
        first = claim_next_ingestion_task(session, worker_id="worker-a", lease_seconds=300)
        assert first is not None

        stale_at = (utcnow() - timedelta(hours=1)).isoformat()
        session.execute(
            text(
                """
                UPDATE data_ingestion_task
                SET heartbeat_at = :stale_at,
                    lease_expires_at = :stale_at
                WHERE id = :task_id
                """
            ),
            {"stale_at": stale_at, "task_id": task.id},
        )
        session.commit()

        reclaimed = claim_next_ingestion_task(session, worker_id="worker-b", lease_seconds=300, stale_after_seconds=60)

        assert reclaimed is not None
        assert reclaimed.id == task.id
        payload = task_payload(reclaimed)
        assert payload["worker_id"] == "worker-b"
        assert payload["status"] == "running"
        assert "stale running task recovered" in payload["last_error"]


def test_run_next_ingestion_task_executes_claimed_task() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            Stock(
                code="300308",
                name="中际旭创",
                market="A",
                board="chinext",
                exchange="SZSE",
                industry_level1="未分类",
                industry_level2="",
                asset_type="equity",
                is_etf=False,
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()
        task = create_ingestion_task(session, task_type="single", market="A", stock_code="300308", source="mock", periods=60)

        result = run_next_ingestion_task(session, worker_id="queue-worker")

        assert result is not None
        assert result.id == task.id
        assert result.status == "success"
        assert result.processed == 1
        assert task_payload(result)["progress"] == 1.0


def test_ingestion_priority_skips_recent_unusable_symbols() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="BAD",
                    name="坏行情样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="GOOD",
                    name="正常行情样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
            ]
        )
        task = create_ingestion_task(session, task_type="batch", market="A", source="mock")
        task.status = "success"
        task.error = "failed_symbols=[BAD:no_usable_bars]"
        task.finished_at = utcnow()
        session.add(task)
        session.commit()

        candidates = priority_candidates(session, market="A", limit=5, periods=60)

        assert {item["code"] for item in candidates} == {"GOOD"}


def test_us_priority_candidates_filter_noise_and_recent_failures() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="GOOD",
                    name="Good Common Stock",
                    market="US",
                    board="nasdaq",
                    exchange="NASDAQ",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=1000,
                    float_market_cap=900,
                ),
                Stock(
                    code="COOL",
                    name="Cooldown Common Stock",
                    market="US",
                    board="nyse",
                    exchange="NYSE",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=900,
                    float_market_cap=800,
                ),
                Stock(
                    code="ABCDW",
                    name="Noise Warrant",
                    market="US",
                    board="nasdaq",
                    exchange="NASDAQ",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=0,
                    float_market_cap=0,
                ),
                Stock(
                    code="LEVX",
                    name="Direxion Daily AI Bull 2X Shares",
                    market="US",
                    board="amex",
                    exchange="AMEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=1000,
                    float_market_cap=1000,
                ),
                Stock(
                    code="RREVU",
                    name="RRE Ventures Acquisition Corp U",
                    market="US",
                    board="nasdaq",
                    exchange="NASDAQ",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=3,
                    float_market_cap=3,
                ),
                Stock(
                    code="ANABV",
                    name="AnaptysBio Inc WI",
                    market="US",
                    board="nasdaq",
                    exchange="NASDAQ",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=12,
                    float_market_cap=12,
                ),
            ]
        )
        task = create_ingestion_task(session, task_type="batch", market="US", source="mock")
        task.status = "failed"
        task.error = "failed_symbols=[COOL:no_usable_bars]"
        task.finished_at = utcnow()
        session.add(task)
        session.commit()

        candidates = priority_candidates(session, market="US", board="all", limit=10, periods=60)

        assert [item["code"] for item in candidates] == ["GOOD"]


def test_hk_priority_candidates_filter_bond_and_note_rows() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="00700.HK",
                    name="腾讯控股",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="04101.HK",
                    name="EFN 3.19 2611",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="04233.HK",
                    name="HKGB SUKUK 2702",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="04304.HK",
                    name="ZJ XC INV B2701",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="06003.HK",
                    name="XIANPORT B2610B",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="06012.HK",
                    name="PEAK RE PSGCSB",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        candidates = priority_candidates(session, market="HK", board="all", limit=10, periods=60)

        assert [item["code"] for item in candidates] == ["00700.HK"]


def test_enqueue_ingestion_backfill_skips_when_pending_queue_is_sufficient() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        create_ingestion_task(session, task_type="batch", market="HK", source="mock")
        create_ingestion_task(session, task_type="batch", market="HK", source="mock")

        result = enqueue_ingestion_backfill(
            session,
            markets=("HK",),
            source="mock",
            batches_per_market=2,
            batch_limit=5,
            periods=60,
        )

        assert result["queued_count"] == 0
        assert result["skipped_count"] == 1
        assert result["skipped"] == [
            {"market": "HK", "board": "all", "reason": "pending_queue_already_sufficient", "pending": 2}
        ]


def test_market_data_job_marks_hk_and_bse_provider_failures_with_stable_error_codes() -> None:
    class ProviderFailureClient:
        source = "fixture"

        def fetch_stock_list(self, markets=None):
            return []

        def fetch_daily_bars(self, stock_code, market=None, end_date=None, periods=320):
            raise RuntimeError("upstream timeout")

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="00700.HK",
                    name="腾讯控股",
                    market="HK",
                    board="hk_main",
                    exchange="HKEX",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=1000,
                    float_market_cap=900,
                ),
                Stock(
                    code="835185",
                    name="贝特瑞",
                    market="A",
                    board="bse",
                    exchange="BSE",
                    industry_level1="未分类",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=800,
                    float_market_cap=700,
                ),
            ]
        )
        session.commit()

        result = run_market_data_job(
            session,
            markets=("HK", "A"),
            max_stocks_per_market=1,
            periods=60,
            client=ProviderFailureClient(),
        )

        assert result["status"] == "failed"
        assert {"code": "00700.HK", "market": "HK", "error": "hk_provider_failed"} in result["failed_symbols"]
        assert {"code": "835185", "market": "A", "error": "bse_provider_failed"} in result["failed_symbols"]


def test_market_data_job_upserts_duplicate_provider_rows() -> None:
    class DuplicateBarClient:
        source = "duplicate"

        def fetch_stock_list(self, markets=None):
            return []

        def fetch_daily_bars(self, stock_code, market=None, end_date=None, periods=320):
            return [
                {
                    "stock_code": stock_code,
                    "trade_date": date(2026, 5, 8),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "pre_close": 10.0,
                    "volume": 1000.0,
                    "amount": 10500.0,
                    "pct_chg": 5.0,
                    "adj_factor": 1.0,
                    "source": "duplicate",
                },
                {
                    "stock_code": stock_code,
                    "trade_date": date(2026, 5, 8),
                    "open": 10.0,
                    "high": 11.2,
                    "low": 9.5,
                    "close": 10.8,
                    "pre_close": 10.0,
                    "volume": 1200.0,
                    "amount": 12960.0,
                    "pct_chg": 8.0,
                    "adj_factor": 1.0,
                    "source": "duplicate",
                },
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            Stock(
                code="DUP",
                name="重复行情样本",
                market="A",
                board="main",
                exchange="SSE",
                industry_level1="未分类",
                industry_level2="",
                asset_type="equity",
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()

        first = run_market_data_job(session, markets=("A",), max_stocks_per_market=1, periods=60, client=DuplicateBarClient())
        second = run_market_data_job(session, markets=("A",), max_stocks_per_market=1, periods=60, client=DuplicateBarClient())

        rows = session.scalars(select(DailyBar).where(DailyBar.stock_code == "DUP")).all()
        assert first["status"] == "success"
        assert second["status"] == "success"
        assert len(rows) == 1
        assert rows[0].close == 10.8


def test_market_data_job_filters_unsupported_us_rows() -> None:
    class RecordingBarClient:
        source = "recording"

        def __init__(self) -> None:
            self.codes: list[str] = []

        def fetch_stock_list(self, markets=None):
            return []

        def fetch_daily_bars(self, stock_code, market=None, end_date=None, periods=320):
            self.codes.append(stock_code)
            return [
                {
                    "stock_code": stock_code,
                    "trade_date": date(2026, 5, 8),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "pre_close": 10.0,
                    "volume": 1000.0,
                    "amount": 10500.0,
                    "pct_chg": 5.0,
                    "adj_factor": 1.0,
                    "source": "recording",
                }
            ]

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                Stock(
                    code="AAPL",
                    name="Apple Inc.",
                    market="US",
                    board="nasdaq",
                    exchange="US",
                    industry_level1="未分类",
                    industry_level2="",
                    asset_type="equity",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                    market_cap=1000,
                    float_market_cap=900,
                ),
                Stock(
                    code="105.AAPL22",
                    name="Apple structured row",
                    market="US",
                    board="other",
                    exchange="US",
                    industry_level1="未分类",
                    industry_level2="",
                    asset_type="other",
                    is_etf=False,
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="SPY",
                    name="SPDR S&P 500 ETF Trust",
                    market="US",
                    board="nyse",
                    exchange="US",
                    industry_level1="未分类",
                    industry_level2="",
                    asset_type="etf",
                    is_etf=True,
                    listing_status="listed",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        client = RecordingBarClient()
        result = run_market_data_job(session, markets=("US",), max_stocks_per_market=10, periods=60, client=client)

        assert result["stocks_requested"] == 1
        assert result["stocks_processed"] == 1
        assert client.codes == ["AAPL"]
