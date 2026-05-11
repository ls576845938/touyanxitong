from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, EvidenceEvent, IndustryChainNode, RetailStockPool, SecurityMaster
from app.db.session import get_session
from app.main import app


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'retail_api.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_security_master_and_industry_chain_bootstrap(tmp_path) -> None:
    with _client(tmp_path) as client:
        profile = client.get("/api/securities/300308/research-profile")
        assert profile.status_code == 200
        payload = profile.json()
        assert payload["basic"]["symbol"] == "300308"
        assert payload["basic"]["industry_level_1"] == "AI算力"
        assert "研究辅助" in payload["boundary"]
        assert payload["industry_position"]["chain_nodes"]
        assert payload["data_quality_status"] in {"PASS", "WARN", "FAIL"}

        graph = client.get("/api/industry-chain/AI算力/graph")
        assert graph.status_code == 200
        graph_payload = graph.json()
        assert graph_payload["summary"]["node_count"] >= 5
        assert {"AI服务器", "光模块", "PCB", "液冷", "电源"}.issubset({row["name"] for row in graph_payload["nodes"]})
        assert graph_payload["edges"]


def test_evidence_event_extracts_ai_compute_case_and_gates_missing_source(tmp_path) -> None:
    with _client(tmp_path) as client:
        missing_source = client.post(
            "/api/evidence-events/extract",
            json={
                "title": "AI算力热词提及光模块和PCB",
                "summary": "没有来源链接的热词只能作为低置信度研究线索。",
                "source_type": "社媒热词",
            },
        )
        assert missing_source.status_code == 200
        assert missing_source.json()["confidence"] <= 50
        assert missing_source.json()["data_quality_status"] == "WARN"

        event = client.post(
            "/api/evidence-events/extract",
            json={
                "title": "英伟达上调AI资本开支，AI服务器需求带动光模块、PCB、液冷和电源订单",
                "summary": "公开新闻显示云厂商AI资本开支延续，相关产业链节点需要跟踪。",
                "source_name": "Example News",
                "source_url": "https://example.com/ai-capex",
                "source_type": "新闻",
            },
        )
        assert event.status_code == 200
        payload = event.json()
        assert payload["data_quality_status"] == "PASS"
        assert payload["impact_direction"] == "positive"
        assert {"AI服务器", "光模块", "PCB", "液冷", "电源"}.issubset(set(payload["affected_objects"]))
        assert len(payload["affected_node_ids"]) >= 5
        assert len(payload["affected_security_ids"]) >= 3
        assert "买入" not in event.text

        events = client.get("/api/evidence-events?confidence_min=50&chain_node=AI算力")
        assert events.status_code == 200
        assert len(events.json()["events"]) >= 1

        pool = client.get("/api/retail-stock-pool")
        assert pool.status_code == 200
        rows = pool.json()["items"]
        assert rows
        assert all("boundary" in row for row in rows)
        assert all(row["pool_level"] not in {"S", "A"} for row in rows if row["data_quality_status"] == "FAIL")


def test_portfolio_exposure_trade_journal_and_review(tmp_path) -> None:
    with _client(tmp_path) as client:
        event = client.post(
            "/api/evidence-events/extract",
            json={
                "title": "AI服务器订单增长带动光模块和液冷需求",
                "summary": "用于关联交易日志的结构化证据。",
                "source_name": "Example News",
                "source_url": "https://example.com/order",
                "source_type": "新闻",
            },
        ).json()

        dashboard = client.get("/api/portfolio/1/dashboard")
        assert dashboard.status_code == 200
        dashboard_payload = dashboard.json()
        assert dashboard_payload["positions"]
        assert dashboard_payload["industry_exposure"]
        assert dashboard_payload["theme_exposure"]
        assert dashboard_payload["chain_node_exposure"]
        assert dashboard_payload["risk_alerts"]
        assert dashboard_payload["correlation_warnings"]

        trade = client.post(
            "/api/trade-journal",
            json={
                "portfolio_id": 1,
                "symbol": "300308",
                "trade_date": "2026-05-11",
                "action": "watch",
                "price": 100,
                "quantity": 10,
                "position_weight_after_trade": 0.12,
                "trade_reason": "记录研究观察理由，非系统买卖建议。",
                "linked_evidence_event_ids": [event["id"]],
                "expected_scenario": "AI资本开支证据继续被公告或产业数据确认。",
                "invalidation_condition": "订单证据无法复核或趋势持续走弱。",
                "risk_assessment": "同产业链持仓集中，需要控制组合暴露。",
                "user_emotion": "calm",
            },
        )
        assert trade.status_code == 200
        assert "买入" not in trade.text

        review = client.post(
            "/api/trade-review",
            json={
                "trade_journal_id": trade.json()["id"],
                "review_date": "2026-05-20",
                "current_price": 108,
                "benchmark_return": 0.02,
            },
        )
        assert review.status_code == 200
        review_payload = review.json()
        assert review_payload["attribution_logic"] in {"thesis_correct", "market_beta", "luck", "timing_bad"}
        assert review_payload["review_questions"]
        assert "研究辅助" in review_payload["boundary"]


def test_retail_tables_are_created_by_metadata(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'retail_models.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as session:
        assert session.scalar(select(SecurityMaster).limit(1)) is None
        assert session.scalar(select(IndustryChainNode).limit(1)) is None
        assert session.scalar(select(EvidenceEvent).limit(1)) is None
        assert session.scalar(select(RetailStockPool).limit(1)) is None
