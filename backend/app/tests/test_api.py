from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DataSourceRun, Industry, IndustryHeat, IndustryKeyword, NewsArticle, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.data_sources.mock_data import MockMarketDataClient
from app.main import app
from app.pipeline.daily_report_job import run_daily_report_job
from app.pipeline.evidence_chain_job import run_evidence_chain_job
from app.pipeline.industry_heat_job import run_industry_heat_job
from app.pipeline.market_data_job import run_market_data_job
from app.pipeline.news_ingestion_job import run_news_ingestion_job
from app.pipeline.stock_universe_job import run_stock_universe_job
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job
from app.pipeline.tenbagger_thesis_job import run_tenbagger_thesis_job
from app.pipeline.trend_signal_job import run_trend_signal_job


class MixedSourceMarketDataClient(MockMarketDataClient):
    source = "tencent+akshare+mock_fallback"
    last_effective_source = "tencent"

    def fetch_daily_bars(self, stock_code: str, market: str | None = None, end_date: date | None = None, periods: int = 320):
        rows = super().fetch_daily_bars(stock_code, market=market, end_date=end_date, periods=periods)
        if stock_code == "835185":
            return rows
        real_source = "akshare" if (market or "").upper() == "US" else "tencent"
        self.last_effective_source = real_source
        for row in rows:
            row["source"] = real_source
            row["source_kind"] = "real"
            row["source_confidence"] = 1.0
        return rows


def seed_app_database(Session: sessionmaker) -> None:
    with Session() as session:
        run_stock_universe_job(session)
        run_market_data_job(session, client=MixedSourceMarketDataClient())
        run_news_ingestion_job(session)
        run_industry_heat_job(session)
        run_trend_signal_job(session)
        run_tenbagger_score_job(session)
        run_evidence_chain_job(session)
        run_tenbagger_thesis_job(session)
        run_daily_report_job(session)


def test_api_contracts_return_research_outputs(tmp_path) -> None:
    db_path = tmp_path / "api.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    seed_app_database(Session)

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    summary = client.get("/api/market/summary")
    assert summary.status_code == 200
    assert "研究辅助" in summary.json()["boundary"]
    assert {item["market"] for item in summary.json()["markets"]} == {"A", "US", "HK"}

    data_status = client.get("/api/market/data-status")
    assert data_status.status_code == 200
    assert data_status.json()["coverage"]
    assert {row["status"] for row in data_status.json()["runs"]} == {"success"}

    data_quality = client.get("/api/market/data-quality")
    assert data_quality.status_code == 200
    assert data_quality.json()["status"] == "FAIL"
    assert data_quality.json()["segments"]
    assert data_quality.json()["summary"]["stock_count"] > 0
    assert any(issue["issue_type"] == "non_real_bars" for issue in data_quality.json()["issues"])

    ingestion_plan = client.get("/api/market/ingestion-plan")
    assert ingestion_plan.status_code == 200
    assert ingestion_plan.json()["markets"]
    assert ingestion_plan.json()["settings"]["max_stocks_per_market"] > 0
    assert ingestion_plan.json()["discovery_commands"]
    assert "batch-offset" in ingestion_plan.json()["recommended_commands"][0]
    assert "--max-stocks-per-market" in ingestion_plan.json()["recommended_commands"][0]

    instruments = client.get("/api/market/instruments?market=A&board=chinext&limit=5")
    assert instruments.status_code == 200
    assert instruments.json()["total"] > 0
    assert {row["market"] for row in instruments.json()["rows"]} == {"A"}
    assert {row["board"] for row in instruments.json()["rows"]} == {"chinext"}
    assert instruments.json()["rows"][0]["asset_type"] == "equity"

    navigation = client.get("/api/market/instruments/300308/navigation")
    assert navigation.status_code == 200
    assert navigation.json()["current"]["code"] == "300308"
    assert navigation.json()["scope"]["board"] == "chinext"

    alias_navigation = client.get("/api/market/instruments/英伟达/navigation")
    assert alias_navigation.status_code == 200
    assert alias_navigation.json()["current"]["code"] == "NVDA"

    alias_evidence = client.get("/api/stocks/英伟达/evidence")
    assert alias_evidence.status_code == 200
    assert alias_evidence.json()["stock"]["code"] == "NVDA"

    ingestion_batches = client.get("/api/market/ingestion-batches")
    assert ingestion_batches.status_code == 200
    assert ingestion_batches.json()
    assert ingestion_batches.json()[0]["job_name"] == "market_data"

    priority = client.get("/api/market/ingestion-priority?market=A&board=chinext&limit=3")
    assert priority.status_code == 200
    assert priority.json()["candidates"] == []

    task = client.post(
        "/api/market/ingestion-tasks",
        json={"task_type": "single", "market": "A", "stock_code": "300308", "source": "mock", "periods": 320},
    )
    assert task.status_code == 200
    assert task.json()["status"] == "pending"
    assert "lease" in task.json()
    assert "heartbeat_at" in task.json()
    assert "progress" in task.json()

    task_run = client.post(f"/api/market/ingestion-tasks/{task.json()['id']}/run")
    assert task_run.status_code == 200
    assert task_run.json()["status"] == "success"
    assert task_run.json()["progress"] == 1.0

    ingestion_tasks = client.get("/api/market/ingestion-tasks")
    assert ingestion_tasks.status_code == 200
    assert ingestion_tasks.json()[0]["task_type"] == "single"

    backfill = client.post(
        "/api/market/ingestion-tasks/backfill",
        json={"markets": ["A"], "board": "chinext", "source": "mock", "batches_per_market": 2, "batch_limit": 5, "periods": 320},
    )
    assert backfill.status_code == 200
    assert backfill.json()["queued_count"] >= 1
    assert backfill.json()["queued_tasks"][0]["task_type"] == "batch"

    research_universe = client.get("/api/market/research-universe")
    assert research_universe.status_code == 200
    assert research_universe.json()["summary"]["eligible_count"] > 0
    assert research_universe.json()["segments"]
    assert "trusted_data_sources" in research_universe.json()
    assert all("exclusion_reasons" in segment for segment in research_universe.json()["segments"])

    research_universe_rows = client.get("/api/market/research-universe?include_rows=true&row_limit=3")
    assert research_universe_rows.status_code == 200
    assert research_universe_rows.json()["rows"]
    assert {"exclusion_reasons", "data_source_trust", "selected_bar_source"}.issubset(research_universe_rows.json()["rows"][0])

    watchlist_changes = client.get("/api/watchlist/changes")
    assert watchlist_changes.status_code == 200
    assert watchlist_changes.json()["summary"]["latest_watch_count"] >= 0
    assert "new_entries" in watchlist_changes.json()

    watchlist_timeline = client.get("/api/watchlist/timeline?market=A&board=chinext")
    assert watchlist_timeline.status_code == 200
    assert watchlist_timeline.json()["latest"]["summary"]["latest_watch_count"] >= 0

    industries = client.get("/api/industries/radar")
    assert industries.status_code == 200
    assert len(industries.json()) >= 44
    assert "top_keywords" in industries.json()[0]
    assert "global_heat_score" in industries.json()[0]
    assert "news_heat_score" in industries.json()[0]
    assert "structure_heat_score" in industries.json()[0]
    assert "evidence_status" in industries.json()[0]
    assert "zero_heat_reason" in industries.json()[0]
    assert {
        "related_stock_count",
        "scored_stock_count",
        "watch_stock_count",
        "trend_breadth",
        "breakout_breadth",
    }.issubset(industries.json()[0])
    assert any(row["heat_score"] == 0 and row["zero_heat_reason"] for row in industries.json())

    a_industries = client.get("/api/industries/radar?market=A")
    assert a_industries.status_code == 200
    assert len(a_industries.json()) >= 44
    assert {row["market"] for row in a_industries.json()} == {"A"}
    assert any(row["related_stock_count"] > 0 for row in a_industries.json())
    assert all(row["global_heat_score"] == row["news_heat_score"] for row in a_industries.json())
    adjusted_row = next(row for row in a_industries.json() if row["related_stock_count"] > 0)
    assert "global_heat_score" in adjusted_row
    assert "heat_score" in adjusted_row
    assert "structure_heat_score" in adjusted_row
    assert "watch_stock_count" in adjusted_row

    us_industries = client.get("/api/industries/radar?market=US")
    assert us_industries.status_code == 200
    a_battery = next(row for row in a_industries.json() if row["name"] == "固态电池")
    us_battery = next(row for row in us_industries.json() if row["name"] == "固态电池")
    assert a_battery["heat_score"] > 0
    assert us_battery["related_stock_count"] == 0
    assert next(row for row in us_industries.json() if row["name"] == "固态电池")["heat_score"] == 0

    mapping_summary = client.get("/api/industries/mapping-summary")
    assert mapping_summary.status_code == 200
    assert mapping_summary.json()["total_stocks"] > 0
    assert "unclassified_count" in mapping_summary.json()
    assert mapping_summary.json()["by_industry"]

    industry_timeline = client.get("/api/industries/timeline")
    assert industry_timeline.status_code == 200
    assert industry_timeline.json()["latest"]["summary"]["industry_count"] > 0
    assert "top_keywords" in industry_timeline.json()["latest"]["top_industries"][0]
    assert "heat_score_delta" in industry_timeline.json()["latest"]["top_industries"][0]

    industry_id = industry_timeline.json()["latest"]["top_industries"][0]["industry_id"]
    industry_detail = client.get(f"/api/industries/{industry_id}")
    assert industry_detail.status_code == 200
    assert industry_detail.json()["industry"]["keywords"]
    assert industry_detail.json()["latest_heat"]["industry_id"] == industry_id
    assert industry_detail.json()["summary"]["related_stock_count"] > 0
    assert industry_detail.json()["related_stocks"][0]["code"]
    assert industry_detail.json()["recent_articles"]

    a_industry_detail = client.get(f"/api/industries/{industry_id}?market=A")
    assert a_industry_detail.status_code == 200
    assert a_industry_detail.json()["summary"]["market"] == "A"
    assert {row["market"] for row in a_industry_detail.json()["related_stocks"]} == {"A"}

    trend_pool = client.get("/api/stocks/trend-pool")
    assert trend_pool.status_code == 200
    first = trend_pool.json()[0]
    assert first["final_score"] >= 0
    assert first["research_eligible"] is True
    assert "research_gate" in first
    assert "source_confidence" in first["confidence"]
    assert "fundamental_confidence" in first["confidence"]
    assert "news_confidence" in first["confidence"]
    assert first["confidence"]["level"] in {"high", "medium", "low", "insufficient", "unknown"}
    assert first["fundamental_summary"]["status"] in {"complete", "partial"}
    assert first["news_evidence_status"] in {"active", "partial", "missing"}

    us_pool = client.get("/api/stocks/trend-pool?market=US")
    assert us_pool.status_code == 200
    assert us_pool.json()
    assert {row["market"] for row in us_pool.json()} == {"US"}

    chinext_pool = client.get("/api/stocks/trend-pool?market=A&board=chinext")
    assert chinext_pool.status_code == 200
    assert chinext_pool.json()
    assert {row["board"] for row in chinext_pool.json()} == {"chinext"}

    evidence = client.get(f"/api/stocks/{first['code']}/evidence")
    assert evidence.status_code == 200
    assert "买入" not in evidence.text
    assert "source_refs" in evidence.json()["evidence"]
    assert "confidence" in evidence.json()["score"]
    assert "research_gate" in evidence.json()["score"]
    assert "evidence_status" in evidence.json()["evidence"]

    source_comparison = client.get(f"/api/stocks/{first['code']}/source-comparison")
    assert source_comparison.status_code == 200
    assert source_comparison.json()["sources"][0]["bars_count"] > 0

    stock_ingest = client.post(f"/api/stocks/{first['code']}/ingest?source=mock")
    assert stock_ingest.status_code == 200
    assert stock_ingest.json()["status"] == "success"

    history = client.get(f"/api/stocks/{first['code']}/history")
    assert history.status_code == 200
    assert history.json()["stock"]["code"] == first["code"]
    assert history.json()["latest"]["trade_date"] == evidence.json()["evidence"]["trade_date"]
    assert history.json()["history"][0]["source_refs"]
    assert "score_delta" in history.json()["history"][0]

    research_tasks = client.get("/api/research/tasks?market=A&board=chinext&watch_only=false")
    assert research_tasks.status_code == 200
    assert research_tasks.json()["latest_date"] == evidence.json()["evidence"]["trade_date"]
    assert research_tasks.json()["summary"]["task_count"] > 0
    assert research_tasks.json()["summary"]["stock_count"] > 0
    assert research_tasks.json()["tasks"][0]["stock_code"]
    assert research_tasks.json()["tasks"][0]["priority"] in {"high", "medium", "low"}
    assert {task["market"] for task in research_tasks.json()["tasks"]} == {"A"}
    assert {task["board"] for task in research_tasks.json()["tasks"]} == {"chinext"}

    research_brief = client.get("/api/research/brief?market=A&board=chinext&watch_only=false")
    assert research_brief.status_code == 200
    assert research_brief.json()["latest_date"] == research_tasks.json()["latest_date"]
    assert research_brief.json()["summary"]["task_count"] == research_tasks.json()["summary"]["task_count"]
    assert research_brief.json()["focus_stocks"]
    assert research_brief.json()["focus_industries"]
    assert "AlphaRadar 每日研究工作单" in research_brief.json()["markdown"]
    assert "交易指令" in research_brief.json()["markdown"]

    theses = client.get("/api/research/thesis?limit=5")
    assert theses.status_code == 200
    thesis_payload = theses.json()
    assert thesis_payload["rows"]
    assert "average_logic_gate_score" in thesis_payload["summary"]
    assert "average_anti_thesis_score" in thesis_payload["summary"]
    assert "contrarian_count" in thesis_payload["summary"]
    thesis_row = thesis_payload["rows"][0]
    assert {
        "logic_gate_score",
        "logic_gate_status",
        "logic_gates",
        "alternative_data_signals",
        "valuation_simulation",
        "contrarian_signal",
        "anti_thesis_items",
        "sniper_focus",
        "marginal_changes",
    }.issubset(thesis_row)
    assert thesis_row["logic_gates"]
    assert thesis_row["alternative_data_signals"]
    assert "valuation_ceiling_status" in thesis_row["valuation_simulation"]
    assert "label" in thesis_row["contrarian_signal"]
    assert thesis_row["marginal_changes"]
    assert "买入" not in theses.text

    logic_filtered = client.get(f"/api/research/thesis?logic_gate_status={thesis_row['logic_gate_status']}&limit=5")
    assert logic_filtered.status_code == 200
    assert logic_filtered.json()["rows"]
    assert {row["logic_gate_status"] for row in logic_filtered.json()["rows"]} == {thesis_row["logic_gate_status"]}

    contrarian = client.get("/api/research/thesis?contrarian_only=true&limit=20")
    assert contrarian.status_code == 200
    assert "contrarian_count" in contrarian.json()["summary"]
    assert all(row["contrarian_signal"]["reversal_watch"] for row in contrarian.json()["rows"])

    thesis_detail = client.get(f"/api/research/thesis/{thesis_row['stock_code']}")
    assert thesis_detail.status_code == 200
    assert thesis_detail.json()["latest"]["stock_code"] == thesis_row["stock_code"]
    assert thesis_detail.json()["latest"]["logic_gates"]
    assert thesis_detail.json()["history"]

    missing_thesis = client.get("/api/research/thesis/NOT_A_CODE")
    assert missing_thesis.status_code == 404

    data_gate = client.get("/api/research/data-gate?limit=5")
    assert data_gate.status_code == 200
    assert "formal_ready_ratio" in data_gate.json()["summary"]

    backtest_latest = client.get("/api/research/backtest/latest")
    assert backtest_latest.status_code == 200
    assert {"latest", "runs"}.issubset(backtest_latest.json())

    report = client.get("/api/reports/latest")
    assert report.status_code == 200
    assert "AlphaRadar 每日投研雷达" in report.json()["full_markdown"]
    assert "## 今日运行状态" in report.json()["full_markdown"]
    assert report.json()["data_quality"]["status"] == "FAIL"
    assert report.json()["research_universe"]["summary"]["eligible_count"] > 0
    assert report.json()["watchlist_changes"]["summary"]["latest_watch_count"] >= 0

    report_list = client.get("/api/reports")
    assert report_list.status_code == 200
    assert report_list.json()[0]["report_date"] == report.json()["report_date"]

    report_by_date = client.get(f"/api/reports/{report.json()['report_date']}")
    assert report_by_date.status_code == 200
    assert report_by_date.json()["title"] == report.json()["title"]
    app.dependency_overrides.clear()


def test_research_hot_terms_contract_and_source_status(tmp_path) -> None:
    db_path = tmp_path / "hot_terms_api.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
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
                IndustryKeyword(industry_id=robot.id, keyword="减速器", weight=1.0, is_active=True),
                IndustryHeat(
                    industry_id=ai.id,
                    trade_date=date(2026, 5, 8),
                    heat_score=16,
                    heat_1d=16,
                    heat_7d=12,
                    top_keywords='["光模块"]',
                    explanation="AI算力热度上行",
                ),
                NewsArticle(
                    title="光模块 demand is rising with AI算力 capex",
                    content="",
                    summary="",
                    source="reddit",
                    source_kind="community",
                    source_confidence=0.56,
                    source_url="https://reddit.test/r/stocks/1",
                    published_at=datetime(2026, 5, 8, 9, tzinfo=timezone.utc),
                    matched_keywords='["光模块"]',
                    related_industries='["AI算力"]',
                    related_stocks="[]",
                ),
                NewsArticle(
                    title="AI算力订单延续增长，光模块与液冷环节关注度提升",
                    content="",
                    summary="",
                    source="mock",
                    source_kind="mock",
                    source_confidence=0.3,
                    source_url="mock://news/2026-05-08/1",
                    published_at=datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc),
                    matched_keywords='["光模块"]',
                    related_industries='["AI算力"]',
                    related_stocks="[]",
                    is_synthetic=False,
                ),
                NewsArticle(
                    title="机器人 减速器 新订单",
                    content="",
                    summary="",
                    source="wsj",
                    source_kind="professional_media",
                    source_confidence=0.78,
                    source_url="https://wsj.test/markets/1",
                    published_at=datetime(2026, 5, 8, 10, tzinfo=timezone.utc),
                    matched_keywords="[]",
                    related_industries="[]",
                    related_stocks="[]",
                ),
                NewsArticle(
                    title="同花顺 光模块 产业链更新",
                    content="",
                    summary="",
                    source="tonghuashun",
                    source_kind="market_media",
                    source_confidence=0.74,
                    source_url="https://news.10jqka.com.cn/20260508/c676500001.shtml",
                    published_at=datetime(2026, 5, 8, 11, tzinfo=timezone.utc),
                    matched_keywords='["光模块"]',
                    related_industries='["AI算力"]',
                    related_stocks="[]",
                ),
                NewsArticle(
                    title="Apollo holds talks to sell private credit fund",
                    content="",
                    summary="",
                    source="wsj",
                    source_kind="professional_media",
                    source_confidence=0.78,
                    source_url="https://wsj.test/markets/noise",
                    published_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
                    matched_keywords="[]",
                    related_industries="[]",
                    related_stocks="[]",
                ),
                NewsArticle(
                    title="Reuters AI chip suppliers lift optical module sentiment",
                    content="AI infrastructure and Nvidia capex remain the context.",
                    summary="Reuters market story tied to AI supply chain sentiment.",
                    source="reuters_markets",
                    source_kind="professional_media",
                    source_confidence=0.8,
                    source_channel="google_ai_semis",
                    source_label="Reuters Markets",
                    source_rank=1,
                    source_url="https://reuters.test/markets/ai-chips",
                    published_at=datetime(2026, 5, 8, 13, tzinfo=timezone.utc),
                    matched_keywords='["光模块"]',
                    related_industries='["AI算力"]',
                    related_stocks="[]",
                    match_reason='{"primary":"keyword","keyword":["光模块"],"industry":["AI算力"],"alias":["ai","nvidia"],"unmatched":[]}',
                    is_synthetic=False,
                ),
                DataSourceRun(
                    job_name="hot_terms_eastmoney",
                    requested_source="hot_terms",
                    effective_source="eastmoney",
                    source_kind="market_media",
                    source_confidence=0.76,
                    markets="[]",
                    status="failed",
                    rows_inserted=0,
                    rows_updated=0,
                    rows_total=0,
                    error="fixture network failure",
                    started_at=datetime(2026, 5, 8, 11, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 5, 8, 11, tzinfo=timezone.utc),
                ),
                DataSourceRun(
                    job_name="hot_terms_wsj",
                    requested_source="hot_terms",
                    effective_source="wsj",
                    source_kind="professional",
                    source_confidence=0.82,
                    markets="[]",
                    status="failed",
                    rows_inserted=0,
                    rows_updated=0,
                    rows_total=6,
                    error="fixture latest connector failure",
                    started_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    try:
        response = client.get("/api/research/hot-terms?window=today&limit=10")
        payload = response.json()

        assert response.status_code == 200
        assert payload["window"] == "1d"
        assert {"latest_date", "updated_at", "summary", "sources", "hot_terms", "hot_industries", "platform_terms"}.issubset(payload)
        assert payload["summary"]["data_mode"] == "database_aggregate"
        assert payload["summary"]["matched_article_count"] == 5
        assert payload["summary"]["unmatched_article_count"] == 1
        assert "data_lag_days" in payload["summary"]
        assert any(term["term"] == "光模块" for term in payload["hot_terms"])
        assert any(term["term"] == "减速器" for term in payload["hot_terms"])
        assert all(term["term"].lower() != "apollo" for term in payload["hot_terms"])
        source_status = {source["key"]: source["status"] for source in payload["sources"]}
        assert source_status["reddit"] == "active"
        assert source_status["tonghuashun"] == "active"
        assert source_status["eastmoney"] == "error"
        assert source_status["wsj"] == "error"
        assert source_status["reuters_markets"] == "active"
        assert source_status["industry_heat"] == "active"
        wsj_source = next(source for source in payload["sources"] if source["key"] == "wsj")
        assert wsj_source["connector_status"] == "failed"
        assert wsj_source["window_data_status"] == "active"
        assert wsj_source["last_irrelevant"] == 6
        assert any(source["key"] == "reuters_markets" and source["terms"] for source in payload["platform_terms"])
        optical = next(term for term in payload["hot_terms"] if term["term"] == "光模块")
        example = next(item for item in optical["examples"] if item["source"] == "reuters_markets")
        assert example["source_channel"] == "google_ai_semis"
        assert example["source_label"] == "Reuters Markets"
        assert example["source_rank"] == 1
        assert example["is_synthetic"] is False
        assert "关键词" in example["match_reason"]
        mock_example = next(item for item in optical["examples"] if item["source"] == "mock")
        assert mock_example["is_synthetic"] is True

        invalid = client.get("/api/research/hot-terms?window=month")
        assert invalid.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_research_hot_terms_refresh_endpoint(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "hot_terms_refresh.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ai = Industry(name="AI算力", description="")
        session.add(ai)
        session.flush()
        session.add(IndustryKeyword(industry_id=ai.id, keyword="光模块", weight=1.0, is_active=True))
        session.commit()

    def fake_run_hot_terms_ingestion_job(session, *, source_keys=None, limit_per_source=12, timeout_seconds=5):
        assert limit_per_source == 3
        assert timeout_seconds == 2
        session.add(
            NewsArticle(
                title="雪球 光模块 热榜",
                content="",
                summary="",
                source="xueqiu",
                source_kind="community",
                source_confidence=0.58,
                source_url="https://xueqiu.test/hot/1",
                published_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
                matched_keywords='["光模块"]',
                related_industries='["AI算力"]',
                related_stocks="[]",
            )
        )
        session.add(
            DataSourceRun(
                job_name="hot_terms_xueqiu",
                requested_source="hot_terms",
                effective_source="xueqiu",
                source_kind="community",
                source_confidence=0.58,
                markets="[]",
                status="success",
                rows_inserted=1,
                rows_updated=0,
                rows_total=1,
                error="",
                started_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
                finished_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
            )
        )
        session.commit()
        return {
            "status": "success",
            "inserted": 1,
            "skipped": 0,
            "failed_sources": 0,
            "source_count": 1,
            "sources": [{"key": "xueqiu", "label": "雪球", "status": "success", "fetched": 1, "inserted": 1, "skipped": 0, "error": ""}],
        }

    from app.api import routes_research

    monkeypatch.setattr(routes_research, "run_hot_terms_ingestion_job", fake_run_hot_terms_ingestion_job)

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    try:
        response = client.post("/api/research/hot-terms/refresh?limit_per_source=3&timeout_seconds=2")
        payload = response.json()

        assert response.status_code == 200
        assert payload["inserted"] == 1
        assert payload["snapshot"]["summary"]["matched_article_count"] == 1
        assert any(source["key"] == "xueqiu" and source["status"] == "active" for source in payload["snapshot"]["sources"])
    finally:
        app.dependency_overrides.clear()


def test_research_hot_terms_does_not_promote_generic_title_terms(tmp_path) -> None:
    db_path = tmp_path / "hot_terms_generic_titles.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ai = Industry(name="AI算力", description="")
        session.add(ai)
        session.flush()
        session.add(IndustryKeyword(industry_id=ai.id, keyword="光模块", weight=1.0, is_active=True))
        session.add(
            NewsArticle(
                title="最新部署 每日必读 财经要闻",
                content="",
                summary="",
                source="local_news",
                source_kind="mock",
                source_confidence=0.3,
                source_url="https://local.test/noise",
                published_at=datetime(2026, 5, 8, 9, tzinfo=timezone.utc),
                matched_keywords="[]",
                related_industries='["AI算力"]',
                related_stocks="[]",
            )
        )
        session.commit()

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    try:
        response = client.get("/api/research/hot-terms?window=1d&limit=10")
        payload = response.json()
        terms = {row["term"] for row in payload["hot_terms"]}

        assert response.status_code == 200
        assert "AI算力" in terms
        assert "最新部署" not in terms
        assert "每日必读" not in terms
        assert "财经要闻" not in terms
    finally:
        app.dependency_overrides.clear()


def test_industry_radar_scores_structured_evidence_without_news(tmp_path) -> None:
    db_path = tmp_path / "structured_heat.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    trade_date = date(2026, 5, 7)

    with Session() as session:
        no_news = Industry(name="结构化证据行业", description="")
        mapped_only = Industry(name="仅映射行业", description="")
        quiet = Industry(name="空行业", description="")
        session.add_all([no_news, mapped_only, quiet])
        session.flush()
        session.add_all(
            [
                IndustryHeat(
                    industry_id=no_news.id,
                    trade_date=trade_date,
                    heat_score=0,
                    explanation="资讯热度为0：近30日未匹配到有效资讯证据。",
                ),
                IndustryHeat(
                    industry_id=quiet.id,
                    trade_date=trade_date,
                    heat_score=0,
                    explanation="资讯热度为0：近30日未匹配到有效资讯证据。",
                ),
                Stock(
                    code="STRUCT1",
                    name="结构化样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="结构化证据行业",
                    industry_level2="样本",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
                Stock(
                    code="MAPPED1",
                    name="仅映射样本",
                    market="A",
                    board="main",
                    exchange="SSE",
                    industry_level1="仅映射行业",
                    industry_level2="样本",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                ),
                StockScore(stock_code="STRUCT1", trade_date=trade_date, final_score=82, rating="观察"),
                TrendSignal(
                    stock_code="STRUCT1",
                    trade_date=trade_date,
                    is_ma_bullish=True,
                    is_breakout_120d=True,
                    trend_score=18,
                ),
            ]
        )
        session.commit()

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/industries/radar?market=A")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()}
    assert rows["结构化证据行业"]["news_heat_score"] == 0
    assert rows["结构化证据行业"]["structure_heat_score"] > 0
    assert rows["结构化证据行业"]["heat_score"] > 0
    assert rows["结构化证据行业"]["evidence_status"] == "structure_active"
    assert "资讯热度为0" in rows["结构化证据行业"]["zero_heat_reason"]
    assert "已评分股票" in rows["结构化证据行业"]["explanation"]
    assert rows["仅映射行业"]["related_stock_count"] == 1
    assert rows["仅映射行业"]["structure_heat_score"] == 0
    assert rows["仅映射行业"]["heat_score"] == 0
    assert rows["仅映射行业"]["evidence_status"] == "mapped_only"
    assert rows["空行业"]["heat_score"] == 0
    assert rows["空行业"]["evidence_status"] == "no_evidence"
