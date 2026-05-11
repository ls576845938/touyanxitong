from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import EvidenceEvent, RetailStockPool, TradeJournal, TradeReview
from app.db.session import SCHEMA_VERSION, get_schema_version, get_session, init_db
from app.main import app


def _client_with_seed(tmp_path):
    db_path = tmp_path / "retail-ops.sqlite"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    init_db(engine, database_url)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    return client, Session


def test_retail_ops_schema_and_seed_data(tmp_path) -> None:
    client, Session = _client_with_seed(tmp_path)

    with Session() as session:
        assert get_schema_version(session.bind) == SCHEMA_VERSION
        assert session.scalar(select(EvidenceEvent).limit(1)) is not None
        assert session.scalar(select(RetailStockPool).limit(1)) is not None
        assert session.scalar(select(TradeJournal).limit(1)) is not None
        assert session.scalar(select(TradeReview).limit(1)) is not None

        missing_source_confidences = [
            float(row.confidence)
            for row in session.scalars(select(EvidenceEvent)).all()
            if not row.source_name or not row.source_url
        ]
        assert missing_source_confidences
        assert max(missing_source_confidences) <= 50.0

        pool_rows = session.scalars(select(RetailStockPool)).all()
        assert pool_rows
        assert all(row.pool_level not in {"S", "A"} for row in pool_rows if float(row.quality_score or 0.0) <= 30.0)

    app.dependency_overrides.clear()
    client.close()


def test_retail_ops_core_endpoints_return_research_payloads(tmp_path) -> None:
    client, _Session = _client_with_seed(tmp_path)

    profile = client.get("/api/securities/300308/research-profile")
    assert profile.status_code == 200
    assert "研究辅助" in profile.json()["boundary"]
    assert profile.json()["basic"]["symbol"] == "300308"
    assert profile.json()["stock_pool"] is not None

    graph = client.get("/api/industry-chain/AI%E7%AE%97%E5%8A%9B/graph")
    assert graph.status_code == 200
    assert graph.json()["chain_name"] == "AI算力"
    assert graph.json()["nodes"]
    assert graph.json()["edges"]

    events = client.get("/api/evidence-events")
    assert events.status_code == 200
    assert events.json()["events"]
    assert any((not row["source_name"] or not row["source_url"]) and row["confidence"] <= 50 for row in events.json()["events"])
    assert all("boundary" in row for row in events.json()["events"])

    pool = client.get("/api/retail-stock-pool")
    assert pool.status_code == 200
    assert pool.json()["items"]
    fail_rows = [row for row in pool.json()["items"] if row["data_quality_status"] == "FAIL"]
    assert fail_rows
    assert all(row["pool_level"] not in {"S", "A"} for row in fail_rows)

    dashboard = client.get("/api/portfolio/1/dashboard/exposure/correlation-warning")
    assert dashboard.status_code == 200
    assert dashboard.json()["exposure"]["positions"]
    assert dashboard.json()["correlation_warning"]["warnings"]
    assert dashboard.json()["correlation_warning"]["risk_alerts"]

    journal = client.get("/api/trade-journal")
    assert journal.status_code == 200
    assert journal.json()["trades"]
    assert "研究辅助" in journal.json()["boundary"]

    review = client.get("/api/trade-review")
    assert review.status_code == 200
    assert review.json()["reviews"]
    assert "研究辅助" in review.json()["boundary"]

    app.dependency_overrides.clear()
    client.close()


def test_retail_ops_post_endpoints_enforce_constraints(tmp_path) -> None:
    client, _Session = _client_with_seed(tmp_path)

    created_event = client.post(
        "/api/evidence-events",
        json={
            "title": "无链接来源样本",
            "summary": "只有口头摘要，没有完整来源链接。",
            "source_name": "",
            "source_url": "",
            "source_type": "新闻",
            "raw_text": "AI算力 口头摘要",
        },
    )
    assert created_event.status_code == 200
    event_payload = created_event.json()["event"]
    assert event_payload["confidence"] <= 50
    assert event_payload["data_quality_status"] in {"WARN", "FAIL"}

    created_pool = client.post(
        "/api/retail-stock-pool",
        json={
            "symbol": "300308",
            "pool_level": "S",
            "pool_reason": "尝试手工抬级",
            "quality_score": 25,
            "risk_score": 70,
            "key_evidence_event_ids": [event_payload["id"]],
            "next_tracking_tasks": ["补充正式来源"],
            "invalidation_conditions": ["来源无法核验"],
        },
    )
    assert created_pool.status_code == 200
    assert created_pool.json()["pool_level"] not in {"S", "A"}

    created_trade = client.post(
        "/api/trade-journal",
        json={
            "symbol": "300308",
            "portfolio_id": 1,
            "trade_date": "2026-05-11",
            "action": "watch",
            "price": 152.0,
            "quantity": 100,
            "trade_reason": "研究跟踪记录",
            "linked_evidence_event_ids": [event_payload["id"]],
        },
    )
    assert created_trade.status_code == 200
    trade_payload = created_trade.json()
    assert trade_payload["security"]["symbol"] == "300308"

    created_review = client.post(
        "/api/trade-review",
        json={
            "trade_journal_id": trade_payload["id"],
            "review_date": "2026-05-11",
            "current_price": 151.0,
            "benchmark_return": 0.01,
            "what_happened": "研究假设需要继续验证。",
        },
    )
    assert created_review.status_code == 200
    assert created_review.json()["trade_journal_id"] == trade_payload["id"]
    assert "研究辅助" in created_review.json()["boundary"]

    app.dependency_overrides.clear()
    client.close()
