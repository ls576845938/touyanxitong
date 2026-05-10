from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.db.models import Base, DailyBar, Stock
from app.engines.data_quality_engine import StockDataProfile, assess_market_data_quality
from app.db.session import (
    DEFAULT_SQLITE_PATH,
    SCHEMA_VERSION,
    canonical_database_url,
    get_database_info,
    get_schema_version,
    init_db,
    run_schema_migrations,
    sqlite_database_path,
)
from app.pipeline.research_universe import research_universe_payload


def test_default_sqlite_url_resolves_to_backend_data_path() -> None:
    resolved = canonical_database_url("sqlite:///./alpha_radar.db")

    assert sqlite_database_path(resolved) == DEFAULT_SQLITE_PATH
    assert resolved.endswith("/backend/data/alpha_radar.db")


def test_schema_migrations_are_versioned_and_add_legacy_columns(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE stock (
                    id INTEGER PRIMARY KEY,
                    code VARCHAR(16),
                    name VARCHAR(64),
                    exchange VARCHAR(16),
                    industry_level1 VARCHAR(64)
                )
                """
            )
        )
        connection.execute(text("CREATE TABLE stock_score (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE data_ingestion_task (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE daily_bar (id INTEGER PRIMARY KEY, source VARCHAR(64))"))
        connection.execute(text("CREATE TABLE data_source_run (id INTEGER PRIMARY KEY, requested_source VARCHAR(64), effective_source VARCHAR(64))"))

    run_schema_migrations(engine)

    inspector = inspect(engine)
    stock_columns = {column["name"] for column in inspector.get_columns("stock")}
    score_columns = {column["name"] for column in inspector.get_columns("stock_score")}
    task_columns = {column["name"] for column in inspector.get_columns("data_ingestion_task")}
    with engine.connect() as connection:
        migration_rows = connection.execute(text("SELECT version, name FROM schema_migration ORDER BY version")).all()

    bar_columns = {column["name"] for column in inspector.get_columns("daily_bar")} if inspector.has_table("daily_bar") else set()
    run_columns = {column["name"] for column in inspector.get_columns("data_source_run")} if inspector.has_table("data_source_run") else set()

    assert {"market", "board", "asset_type", "currency", "is_etf", "metadata_json"}.issubset(stock_columns)
    assert {"raw_score", "data_confidence", "confidence_level", "confidence_reasons"}.issubset(score_columns)
    assert {"worker_id", "heartbeat_at", "lease_expires_at", "progress", "last_error", "last_stock"}.issubset(task_columns)
    assert {"source_kind", "source_confidence"}.issubset(bar_columns)
    assert {"source_kind", "source_confidence"}.issubset(run_columns)
    assert get_schema_version(engine) == SCHEMA_VERSION
    assert [row.version for row in migration_rows] == list(range(1, SCHEMA_VERSION + 1))


def test_data_quality_distinguishes_mock_from_real_coverage() -> None:
    start = date(2026, 1, 1)
    bars = [
        {
            "trade_date": start + timedelta(days=index),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000.0,
            "amount": 10000.0,
            "source": "mock",
            "source_kind": "mock",
        }
        for index in range(60)
    ]

    result = assess_market_data_quality(
        [StockDataProfile(code="MOCK", name="Mock 样本", market="A", board="main", bars=bars)],
        min_required_bars=60,
        preferred_bars=60,
    )

    assert result["status"] == "FAIL"
    assert result["segments"][0]["coverage_ratio"] == 1.0
    assert result["segments"][0]["real_coverage_ratio"] == 0.0
    assert result["segments"][0]["source_kind_coverage"]["mock"]["bars_count"] == 60
    assert any(issue["issue_type"] == "non_real_bars" for issue in result["issues"])


def test_research_universe_eligibility_requires_real_daily_bar_source_kind() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                _stock("MOCK_ONLY", source="mock", data_vendor="mock"),
                _stock("FALLBACK_ONLY", source="tencent+mock_fallback", data_vendor="tencent+mock_fallback"),
                _stock("TENCENT_REAL", source="tencent", data_vendor="tencent"),
                _stock("AKSHARE_REAL", source="akshare", data_vendor="akshare"),
            ]
        )
        session.flush()
        session.add_all(_daily_bars("MOCK_ONLY", source="mock", source_kind="mock", source_confidence=0.1))
        session.add_all(_daily_bars("FALLBACK_ONLY", source="mock", source_kind="fallback", source_confidence=0.35))
        session.add_all(_daily_bars("TENCENT_REAL", source="tencent", source_kind="real", source_confidence=1.0))
        session.add_all(_daily_bars("AKSHARE_REAL", source="akshare", source_kind="real", source_confidence=1.0))
        session.commit()

        result = research_universe_payload(session, target_date=date(2026, 5, 7))

    rows = {row["code"]: row for row in result["rows"]}
    assert rows["MOCK_ONLY"]["eligible"] is False
    assert rows["FALLBACK_ONLY"]["eligible"] is False
    assert "untrusted_data_source" in rows["MOCK_ONLY"]["exclusion_reasons"]
    assert "untrusted_data_source" in rows["FALLBACK_ONLY"]["exclusion_reasons"]
    assert rows["TENCENT_REAL"]["eligible"] is True
    assert rows["AKSHARE_REAL"]["eligible"] is True
    assert result["summary"]["eligible_count"] == 2


def test_database_info_reports_sqlite_path_and_schema_version(tmp_path) -> None:
    db_path = tmp_path / "alpha.sqlite"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)

    init_db(engine, database_url)
    info = get_database_info(engine, database_url)

    assert info["dialect"] == "sqlite"
    assert info["path"] == str(db_path)
    assert info["schema_version"] == SCHEMA_VERSION
    assert info["expected_schema_version"] == SCHEMA_VERSION
    assert info["schema_current"] is True
    assert info["available"] is True


def test_health_exposes_database_and_schema_info(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "get_database_info",
        lambda: {
            "dialect": "sqlite",
            "path": "/tmp/alpha.sqlite",
            "schema_version": SCHEMA_VERSION,
            "expected_schema_version": SCHEMA_VERSION,
            "schema_current": True,
            "available": True,
        },
    )
    monkeypatch.setattr(main_module, "database_url", "sqlite:////tmp/alpha.sqlite")

    client = TestClient(main_module.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "AlphaRadar",
        "database_url": "sqlite:////tmp/alpha.sqlite",
        "database_dialect": "sqlite",
        "database_path": "/tmp/alpha.sqlite",
        "schema_version": SCHEMA_VERSION,
        "schema_expected_version": SCHEMA_VERSION,
        "schema_current": True,
        "database_available": True,
    }


def _stock(code: str, source: str, data_vendor: str) -> Stock:
    return Stock(
        code=code,
        name=f"{code} 样本",
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
        is_st=False,
        is_etf=False,
        is_active=True,
        source=source,
        data_vendor=data_vendor,
    )


def _daily_bars(stock_code: str, source: str, source_kind: str, source_confidence: float) -> list[DailyBar]:
    return [
        DailyBar(
            stock_code=stock_code,
            trade_date=date(2025, 12, 1) + timedelta(days=idx),
            open=10,
            high=11,
            low=9,
            close=10,
            pre_close=10,
            volume=1_000_000,
            amount=50_000_000,
            pct_chg=0,
            source=source,
            source_kind=source_kind,
            source_confidence=source_confidence,
        )
        for idx in range(160)
    ]
