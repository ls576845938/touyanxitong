from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DailyBar, DataIngestionBatch, DataSourceRun, Stock, utcnow
from app.db.session import DEFAULT_SQLITE_PATH, canonical_database_url, sqlite_database_path
from app.pipeline.backfill_manifest import build_backfill_manifest, market_data_coverage
from app.pipeline.ingestion_task_service import claim_next_ingestion_task, create_ingestion_task


def test_default_sqlite_url_resolves_to_backend_data_path() -> None:
    resolved = canonical_database_url("sqlite:///./alpha_radar.db")

    assert sqlite_database_path(resolved) == DEFAULT_SQLITE_PATH
    assert str(DEFAULT_SQLITE_PATH).endswith("backend/data/alpha_radar.db")
    assert sqlite_database_path("sqlite:///:memory:") is None


def test_backfill_manifest_summarizes_coverage_batches_and_resume_state() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add_all(
            [
                _stock("AAA", "A"),
                _stock("BBB", "A"),
                _stock("EMPTY", "A"),
                _stock("AAPL", "US"),
            ]
        )
        session.add_all(
            [
                _bar("AAA", date(2026, 5, 7)),
                _bar("AAA", date(2026, 5, 8)),
                _bar("BBB", date(2026, 5, 8)),
                _bar("AAPL", date(2026, 5, 8)),
                _bar("AAPL", date(2026, 5, 9)),
            ]
        )
        session.add(
            DataIngestionBatch(
                batch_key="batch-1",
                job_name="market_data",
                market="A",
                source="mock",
                status="partial",
                requested=3,
                processed=2,
                inserted=3,
                updated=1,
                failed=1,
            )
        )
        session.add(
            DataSourceRun(
                job_name="market_data",
                requested_source="mock",
                effective_source="mock",
                markets='["A"]',
                status="partial",
                rows_inserted=3,
                rows_updated=1,
                rows_total=4,
                started_at=utcnow(),
                finished_at=utcnow(),
            )
        )
        session.commit()
        task = create_ingestion_task(session, task_type="batch", market="A", source="mock", batch_limit=2, periods=2)
        claimed = claim_next_ingestion_task(session, worker_id="manifest-worker", lease_seconds=300)
        assert claimed is not None
        claimed.requested = 2
        claimed.processed = 1
        claimed.failed = 1
        claimed.error = "failed_symbols=[BBB:no_usable_bars]"
        session.add(claimed)
        session.execute(
            text(
                """
                UPDATE data_ingestion_task
                SET progress = 0.5,
                    last_error = :last_error,
                    last_stock = 'BBB'
                WHERE id = :task_id
                """
            ),
            {"task_id": task.id, "last_error": claimed.error},
        )
        session.commit()

        coverage = market_data_coverage(session, markets=("A", "US"), complete_bars=2)
        manifest = build_backfill_manifest(
            session,
            status="running",
            markets=("A", "US"),
            source="mock",
            periods=2,
            complete_bars=2,
            totals={"batches": 1, "inserted": 3},
            attempts={"AAA": 1, "BBB": 2},
            started_at="2026-05-09T00:00:00+00:00",
            last_batch={"market": "A", "codes": ["AAA", "BBB"]},
        )

    a_coverage = next(row for row in coverage if row["market"] == "A")
    us_coverage = next(row for row in coverage if row["market"] == "US")
    assert a_coverage["eligible_symbols"] == 3
    assert a_coverage["covered_symbols"] == 1
    assert a_coverage["partial_symbols"] == 1
    assert a_coverage["empty_symbols"] == 1
    assert us_coverage["coverage_ratio"] == 1.0
    # Database path depends on the configured database URL in settings.
    # When using an in-memory or PostgreSQL database the path will be None.
    if manifest["database"]["path"] is not None:
        assert manifest["database"]["path"].endswith("backend/data/alpha_radar.db")
    assert manifest["batches"]["by_status"][0]["status"] == "partial"
    assert manifest["data_sources"]["daily_bar_sources"][0]["source"] == "mock"
    assert manifest["resume"]["attempted_symbols"] == 2
    assert manifest["last_batch"]["codes"] == ["AAA", "BBB"]
    assert manifest["tasks"]["latest"][0]["status"] == "running"
    assert manifest["tasks"]["latest"][0]["worker_id"] == "manifest-worker"
    assert manifest["tasks"]["latest"][0]["progress"] == 0.5
    assert "BBB:no_usable_bars" in manifest["tasks"]["latest"][0]["last_error"]


def _stock(code: str, market: str) -> Stock:
    return Stock(
        code=code,
        name=f"{code} sample",
        market=market,
        board="main",
        exchange=market,
        industry_level1="未分类",
        industry_level2="",
        asset_type="equity",
        is_etf=False,
        listing_status="listed",
        is_active=True,
    )


def _bar(stock_code: str, trade_date: date) -> DailyBar:
    return DailyBar(
        stock_code=stock_code,
        trade_date=trade_date,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        pre_close=10.0,
        volume=1000.0,
        amount=10500.0,
        pct_chg=5.0,
        adj_factor=1.0,
        source="mock",
    )
