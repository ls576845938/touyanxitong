from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_DIR / "data" / "alpha_radar.db"
SCHEMA_VERSION = 16


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    apply: Callable[[Engine], None]


def canonical_database_url(database_url: str | None = None) -> str:
    raw_url = database_url or settings.database_url
    if not raw_url.startswith("sqlite"):
        return raw_url

    parsed = make_url(raw_url)
    database = parsed.database
    if not database or database == ":memory:":
        return raw_url

    database_path = Path(database)
    if database_path.is_absolute():
        resolved = database_path
    elif database_path.name == "alpha_radar.db" and database_path.parent in {Path("."), Path("")}:
        resolved = DEFAULT_SQLITE_PATH
    else:
        resolved = PROJECT_ROOT / database_path
    return parsed.set(database=resolved.as_posix()).render_as_string(hide_password=False)


def sqlite_database_path(database_url: str | None = None) -> Path | None:
    raw_url = canonical_database_url(database_url)
    if not raw_url.startswith("sqlite"):
        return None
    database = make_url(raw_url).database
    if not database or database == ":memory:":
        return None
    return Path(database)


def _ensure_sqlite_parent(database_url: str) -> None:
    path = sqlite_database_path(database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


database_url = canonical_database_url(settings.database_url)
engine = create_engine(
    database_url,
    connect_args=_connect_args(database_url),
    future=True,
    pool_pre_ping=settings.database_pool_pre_ping,
)


if database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(target_engine: Engine | None = None, target_database_url: str | None = None) -> None:
    active_engine = target_engine or engine
    active_url = target_database_url or database_url
    _ensure_sqlite_parent(active_url)
    Base.metadata.create_all(bind=active_engine)
    run_schema_migrations(active_engine)
    from app.engines.retail_research_engine import ensure_retail_demo_data

    with Session(active_engine) as session:
        ensure_retail_demo_data(session)
        session.commit()


def run_schema_migrations(target_engine: Engine | None = None) -> None:
    active_engine = target_engine or engine
    _ensure_schema_migration_table(active_engine)
    applied_versions = _applied_schema_versions(active_engine)
    for migration in SCHEMA_MIGRATIONS:
        if migration.version in applied_versions:
            continue
        migration.apply(active_engine)
        _record_schema_migration(active_engine, migration.version, migration.name)


def get_schema_version(target_engine: Engine | None = None) -> int:
    active_engine = target_engine or engine
    inspector = inspect(active_engine)
    if not inspector.has_table("schema_migration"):
        return 0
    with active_engine.connect() as connection:
        version = connection.execute(text("SELECT MAX(version) FROM schema_migration")).scalar()
    return int(version or 0)


def get_database_info(
    target_engine: Engine | None = None,
    target_database_url: str | None = None,
) -> dict[str, object]:
    active_engine = target_engine or engine
    active_url = canonical_database_url(target_database_url or database_url)
    db_path = sqlite_database_path(active_url)
    info: dict[str, object] = {
        "dialect": active_engine.dialect.name,
        "path": str(db_path) if db_path else None,
        "schema_version": None,
        "expected_schema_version": SCHEMA_VERSION,
        "schema_current": False,
        "available": False,
    }
    try:
        version = get_schema_version(active_engine)
    except SQLAlchemyError as exc:
        info["error"] = str(exc)
        return info
    info["schema_version"] = version
    info["schema_current"] = version >= SCHEMA_VERSION
    info["available"] = True
    return info


def _ensure_schema_migration_table(target_engine: Engine) -> None:
    with target_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migration (
                    version INTEGER PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    applied_at VARCHAR(32) NOT NULL
                )
                """
            )
        )


def _applied_schema_versions(target_engine: Engine) -> set[int]:
    with target_engine.connect() as connection:
        rows = connection.execute(text("SELECT version FROM schema_migration")).scalars().all()
    return {int(row) for row in rows}


def _record_schema_migration(target_engine: Engine, version: int, name: str) -> None:
    applied_at = datetime.now(timezone.utc).isoformat()
    with target_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO schema_migration (version, name, applied_at)
                VALUES (:version, :name, :applied_at)
                """
            ),
            {"version": version, "name": name, "applied_at": applied_at},
        )


def _migration_base_schema(_: Engine) -> None:
    """Version marker for the SQLAlchemy metadata-created base schema."""


def _migration_fundamental_metric_schema(target_engine: Engine) -> None:
    """Add scoring confidence columns while metadata creates fundamental_metric."""
    _ensure_stock_score_confidence_columns(target_engine)


def _migration_industry_chain_graph_schema(_: Engine) -> None:
    """Version marker for chain graph tables created from SQLAlchemy metadata."""


def _migration_tenbagger_research_loop_schema(_: Engine) -> None:
    """Version marker for thesis and backtest tables created from SQLAlchemy metadata."""


def _migration_tenbagger_sniper_schema(target_engine: Engine) -> None:
    """Add structured tenbagger logic-sniper fields to existing local databases."""
    _ensure_tenbagger_sniper_columns(target_engine)


def _migration_agent_orchestrator_schema(target_engine: Engine) -> None:
    """Version marker plus indexes for Agent one-click research tables."""
    _ensure_agent_orchestrator_indexes(target_engine)


def _migration_api_performance_indexes(target_engine: Engine) -> None:
    """Add composite indexes for interactive dashboard/API reads."""
    _ensure_api_performance_indexes(target_engine)


def _migration_retail_research_loop_schema(target_engine: Engine) -> None:
    """Version marker plus indexes for retail research loop tables."""
    _ensure_retail_research_indexes(target_engine)


def _ensure_lightweight_migrations(target_engine: Engine) -> None:
    """Apply tiny additive migrations for local MVP databases.

    This avoids asking users to delete their SQLite DB when the stock contract
    gains safe nullable/defaulted columns.
    """
    inspector = inspect(target_engine)
    if not inspector.has_table("stock"):
        return
    existing = {column["name"] for column in inspector.get_columns("stock")}
    alters: list[str] = []
    boolean_default = "false" if target_engine.dialect.name == "postgresql" else "0"
    if "market" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN market VARCHAR(16) DEFAULT 'A'")
    if "board" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN board VARCHAR(24) DEFAULT 'main'")
    if "asset_type" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN asset_type VARCHAR(24) DEFAULT 'equity'")
    if "currency" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN currency VARCHAR(8) DEFAULT 'CNY'")
    if "listing_status" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN listing_status VARCHAR(24) DEFAULT 'listed'")
    if "delisting_date" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN delisting_date DATE")
    if "is_etf" not in existing:
        alters.append(f"ALTER TABLE stock ADD COLUMN is_etf BOOLEAN DEFAULT {boolean_default}")
    if "is_adr" not in existing:
        alters.append(f"ALTER TABLE stock ADD COLUMN is_adr BOOLEAN DEFAULT {boolean_default}")
    if "data_vendor" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN data_vendor VARCHAR(64) DEFAULT 'mock'")
    if "metadata_json" not in existing:
        alters.append("ALTER TABLE stock ADD COLUMN metadata_json TEXT DEFAULT '{}'")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))


def _ensure_stock_score_confidence_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("stock_score"):
        return
    existing = {column["name"] for column in inspector.get_columns("stock_score")}
    alters: list[str] = []
    if "raw_score" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN raw_score FLOAT DEFAULT 0")
    if "source_confidence" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN source_confidence FLOAT DEFAULT 0")
    if "data_confidence" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN data_confidence FLOAT DEFAULT 0")
    if "fundamental_confidence" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN fundamental_confidence FLOAT DEFAULT 0")
    if "news_confidence" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN news_confidence FLOAT DEFAULT 0")
    if "evidence_confidence" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN evidence_confidence FLOAT DEFAULT 0")
    if "confidence_level" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN confidence_level VARCHAR(24) DEFAULT 'unknown'")
    if "confidence_reasons" not in existing:
        alters.append("ALTER TABLE stock_score ADD COLUMN confidence_reasons TEXT DEFAULT '[]'")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))


def _ensure_tenbagger_sniper_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("tenbagger_thesis"):
        return
    existing = {column["name"] for column in inspector.get_columns("tenbagger_thesis")}
    alters: list[str] = []
    if "anti_thesis_score" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN anti_thesis_score FLOAT DEFAULT 0")
    if "logic_gate_score" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN logic_gate_score FLOAT DEFAULT 0")
    if "logic_gate_status" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN logic_gate_status VARCHAR(16) DEFAULT 'WARN'")
    if "logic_gates" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN logic_gates TEXT DEFAULT '[]'")
    if "anti_thesis_items" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN anti_thesis_items TEXT DEFAULT '[]'")
    if "alternative_data_signals" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN alternative_data_signals TEXT DEFAULT '[]'")
    if "valuation_simulation" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN valuation_simulation TEXT DEFAULT '{}'")
    if "contrarian_signal" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN contrarian_signal TEXT DEFAULT '{}'")
    if "sniper_focus" not in existing:
        alters.append("ALTER TABLE tenbagger_thesis ADD COLUMN sniper_focus TEXT DEFAULT '[]'")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))


def _ensure_news_article_source_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("news_article"):
        return
    existing = {column["name"] for column in inspector.get_columns("news_article")}
    alters: list[str] = []
    if "source_kind" not in existing:
        alters.append("ALTER TABLE news_article ADD COLUMN source_kind VARCHAR(24) DEFAULT 'mock'")
    if "source_confidence" not in existing:
        alters.append("ALTER TABLE news_article ADD COLUMN source_confidence FLOAT DEFAULT 0.3")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))


def _ensure_news_article_hot_terms_trace_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("news_article"):
        return
    existing = {column["name"] for column in inspector.get_columns("news_article")}
    alters: list[str] = []
    boolean_default = "false" if target_engine.dialect.name == "postgresql" else "0"
    match_reason_default = '\'{"primary":"none","keyword":[],"industry":[],"alias":[],"unmatched":["none"]}\''
    if "source_channel" not in existing:
        alters.append("ALTER TABLE news_article ADD COLUMN source_channel VARCHAR(64) DEFAULT ''")
    if "source_label" not in existing:
        alters.append("ALTER TABLE news_article ADD COLUMN source_label VARCHAR(64) DEFAULT ''")
    if "source_rank" not in existing:
        alters.append("ALTER TABLE news_article ADD COLUMN source_rank INTEGER DEFAULT 0")
    if "match_reason" not in existing:
        alters.append(f"ALTER TABLE news_article ADD COLUMN match_reason TEXT DEFAULT {match_reason_default}")
    if "is_synthetic" not in existing:
        alters.append(f"ALTER TABLE news_article ADD COLUMN is_synthetic BOOLEAN DEFAULT {boolean_default}")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))
            if _table_has_columns(
                target_engine,
                "news_article",
                {"source_channel", "source_label", "source_rank", "match_reason", "is_synthetic", "source", "source_kind"},
            ):
                connection.execute(
                    text(
                        f"""
                        UPDATE news_article
                        SET source_channel = COALESCE(NULLIF(source_channel, ''), ''),
                            source_label = COALESCE(NULLIF(source_label, ''), source),
                            source_rank = COALESCE(source_rank, 0),
                            match_reason = COALESCE(NULLIF(match_reason, ''), {match_reason_default}),
                            is_synthetic = COALESCE(is_synthetic, {boolean_default})
                        """
                    )
                )


def _migration_mark_mock_news_synthetic(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("news_article"):
        return
    if not _table_has_columns(target_engine, "news_article", {"source", "source_url", "is_synthetic"}):
        return
    boolean_true = "true" if target_engine.dialect.name == "postgresql" else "1"
    with target_engine.begin() as connection:
        connection.execute(
            text(
                f"""
                UPDATE news_article
                SET is_synthetic = {boolean_true}
                WHERE LOWER(COALESCE(source, '')) LIKE 'mock%'
                   OR LOWER(COALESCE(source, '')) LIKE '%fallback%'
                   OR LOWER(COALESCE(source_url, '')) LIKE 'mock:%'
                   OR LOWER(COALESCE(source_url, '')) LIKE 'fallback:%'
                   OR LOWER(COALESCE(source_url, '')) LIKE '%mock://%'
                """
            )
        )


def ingestion_task_runtime_column_definitions(target_engine: Engine) -> dict[str, str]:
    datetime_type = "TIMESTAMP WITH TIME ZONE" if target_engine.dialect.name == "postgresql" else "DATETIME"
    return {
        "worker_id": "VARCHAR(128)",
        "heartbeat_at": datetime_type,
        "lease_expires_at": datetime_type,
        "progress": "FLOAT DEFAULT 0",
        "last_error": "TEXT DEFAULT ''",
        "last_stock": "VARCHAR(32)",
    }


def _ensure_ingestion_task_runtime_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    if not inspector.has_table("data_ingestion_task"):
        return
    existing = {column["name"] for column in inspector.get_columns("data_ingestion_task")}
    missing = [(name, column_type) for name, column_type in ingestion_task_runtime_column_definitions(target_engine).items() if name not in existing]
    if missing:
        with target_engine.begin() as connection:
            for name, column_type in missing:
                connection.execute(text(f"ALTER TABLE data_ingestion_task ADD COLUMN {name} {column_type}"))


def _ensure_market_source_quality_columns(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    alters: list[str] = []
    if inspector.has_table("daily_bar"):
        existing = {column["name"] for column in inspector.get_columns("daily_bar")}
        if "source_kind" not in existing:
            alters.append("ALTER TABLE daily_bar ADD COLUMN source_kind VARCHAR(16) DEFAULT 'mock'")
        if "source_confidence" not in existing:
            alters.append("ALTER TABLE daily_bar ADD COLUMN source_confidence FLOAT DEFAULT 0.1")
    if inspector.has_table("data_source_run"):
        existing = {column["name"] for column in inspector.get_columns("data_source_run")}
        if "source_kind" not in existing:
            alters.append("ALTER TABLE data_source_run ADD COLUMN source_kind VARCHAR(16) DEFAULT 'mock'")
        if "source_confidence" not in existing:
            alters.append("ALTER TABLE data_source_run ADD COLUMN source_confidence FLOAT DEFAULT 0.1")
    if alters:
        with target_engine.begin() as connection:
            for statement in alters:
                connection.execute(text(statement))
            if _table_has_columns(target_engine, "daily_bar", {"source", "source_kind", "source_confidence"}):
                connection.execute(
                    text(
                        """
                        UPDATE daily_bar
                        SET source_kind = CASE
                                WHEN lower(source) IN ('akshare', 'baostock', 'databento', 'eodhd', 'fmp', 'polygon', 'tencent', 'tiingo', 'tushare', 'twelvedata', 'yahoo') THEN 'real'
                                WHEN lower(source) LIKE '%fallback%' THEN 'fallback'
                                WHEN lower(source) = 'mock' THEN 'mock'
                                ELSE 'unknown'
                            END,
                            source_confidence = CASE
                                WHEN lower(source) IN ('akshare', 'baostock', 'databento', 'eodhd', 'fmp', 'polygon', 'tencent', 'tiingo', 'tushare', 'twelvedata', 'yahoo') THEN 1.0
                                WHEN lower(source) LIKE '%fallback%' THEN 0.35
                                WHEN lower(source) = 'mock' THEN 0.1
                                ELSE 0.0
                            END
                        """
                    )
                )
            if _table_has_columns(target_engine, "data_source_run", {"requested_source", "effective_source", "source_kind", "source_confidence"}):
                connection.execute(
                    text(
                        """
                        UPDATE data_source_run
                        SET source_kind = CASE
                                WHEN lower(effective_source) IN ('akshare', 'baostock', 'databento', 'eodhd', 'fmp', 'polygon', 'tencent', 'tiingo', 'tushare', 'twelvedata', 'yahoo') THEN 'real'
                                WHEN lower(effective_source) LIKE '%fallback%' THEN 'fallback'
                                WHEN lower(effective_source) = 'mock' AND lower(requested_source) NOT IN ('mock', '') THEN 'fallback'
                                WHEN lower(effective_source) = 'mock' THEN 'mock'
                                ELSE 'unknown'
                            END,
                            source_confidence = CASE
                                WHEN lower(effective_source) IN ('akshare', 'baostock', 'databento', 'eodhd', 'fmp', 'polygon', 'tencent', 'tiingo', 'tushare', 'twelvedata', 'yahoo') THEN 1.0
                                WHEN lower(effective_source) LIKE '%fallback%' THEN 0.35
                                WHEN lower(effective_source) = 'mock' AND lower(requested_source) NOT IN ('mock', '') THEN 0.35
                                WHEN lower(effective_source) = 'mock' THEN 0.1
                                ELSE 0.0
                            END
                        """
                    )
                )


def _ensure_stock_asset_classification(target_engine: Engine) -> None:
    """Keep existing local security masters from treating unsupported rows as common equities."""
    if not _table_has_columns(target_engine, "stock", {"market", "asset_type", "name", "code", "is_etf"}):
        return
    statements = [
        """
        UPDATE stock
        SET asset_type = 'other'
        WHERE market = 'A'
          AND asset_type = 'equity'
          AND (
              name LIKE '%定转%'
              OR name LIKE '%转债%'
              OR name LIKE '%债%'
              OR name LIKE '%优先%'
              OR name LIKE '%权证%'
              OR code LIKE '81%'
          )
        """,
        """
        UPDATE stock
        SET asset_type = 'etf', is_etf = 1
        WHERE market = 'A'
          AND asset_type = 'equity'
          AND (name LIKE '%ETF%' OR name LIKE '%LOF%' OR name LIKE '%基金%')
        """,
        """
        UPDATE stock
        SET asset_type = 'other'
        WHERE market = 'US'
          AND asset_type = 'equity'
          AND (
              code LIKE '%.%'
              OR code LIKE '%\\_%' ESCAPE '\\'
              OR code LIKE '%0%'
              OR code LIKE '%1%'
              OR code LIKE '%2%'
              OR code LIKE '%3%'
              OR code LIKE '%4%'
              OR code LIKE '%5%'
              OR code LIKE '%6%'
              OR code LIKE '%7%'
              OR code LIKE '%8%'
              OR code LIKE '%9%'
              OR name LIKE '%Warrant%'
              OR name LIKE '%Unit%'
              OR name LIKE '%Right%'
              OR name LIKE '%Preferred%'
          )
        """,
        """
        UPDATE stock
        SET asset_type = 'etf', is_etf = 1
        WHERE market = 'US'
          AND asset_type = 'equity'
          AND (
              name LIKE '% ETF%'
              OR name LIKE '% ETN%'
              OR name LIKE '% Trust%'
              OR name LIKE '% Fund%'
          )
        """,
    ]
    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_ingestion_status_classification(target_engine: Engine) -> None:
    statements: list[str] = []
    if _table_has_columns(
        target_engine,
        "data_ingestion_batch",
        {"status", "error", "processed", "failed", "inserted", "updated"},
    ):
        statements.extend(
            [
                """
                UPDATE data_ingestion_batch
                SET status = 'failed',
                    error = CASE WHEN error = '' THEN 'provider returned no usable bars for selected stocks' ELSE error END
                WHERE status = 'success'
                  AND processed > 0
                  AND failed >= processed
                  AND (inserted + updated) = 0
                """,
                """
                UPDATE data_ingestion_batch
                SET status = 'partial',
                    error = CASE WHEN error = '' THEN 'provider returned no usable bars for part of selected stocks' ELSE error END
                WHERE status = 'success'
                  AND processed > 0
                  AND failed > 0
                  AND failed < processed
                """,
                """
                UPDATE data_ingestion_batch
                SET error = 'provider returned no usable bars for selected stocks'
                WHERE status = 'failed'
                  AND error = ''
                  AND processed > 0
                  AND failed >= processed
                  AND (inserted + updated) = 0
                """,
            ]
        )
    if _table_has_columns(target_engine, "data_source_run", {"job_name", "status", "error", "rows_total"}):
        statements.append(
            """
            UPDATE data_source_run
            SET status = 'failed',
                error = CASE WHEN error = '' THEN 'provider returned no usable bars for selected stocks' ELSE error END
            WHERE job_name = 'market_data'
              AND status = 'success'
              AND rows_total = 0
            """
        )
    if statements:
        with target_engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


def _ensure_query_indexes(target_engine: Engine) -> None:
    statements = [
        (
            "stock",
            {"market", "board", "asset_type", "listing_status"},
            "CREATE INDEX IF NOT EXISTS ix_stock_market_board_asset_status ON stock (market, board, asset_type, listing_status)",
        ),
        (
            "stock",
            {"market", "is_active", "market_cap"},
            "CREATE INDEX IF NOT EXISTS ix_stock_market_active_cap ON stock (market, is_active, market_cap)",
        ),
        (
            "daily_bar",
            {"stock_code", "trade_date"},
            "CREATE INDEX IF NOT EXISTS ix_daily_bar_stock_date ON daily_bar (stock_code, trade_date)",
        ),
        (
            "trend_signal",
            {"trade_date", "trend_score"},
            "CREATE INDEX IF NOT EXISTS ix_trend_signal_date_score ON trend_signal (trade_date, trend_score)",
        ),
        (
            "stock_score",
            {"trade_date", "final_score"},
            "CREATE INDEX IF NOT EXISTS ix_stock_score_date_score ON stock_score (trade_date, final_score)",
        ),
        (
            "data_ingestion_batch",
            {"status", "started_at"},
            "CREATE INDEX IF NOT EXISTS ix_data_ingestion_batch_status_started ON data_ingestion_batch (status, started_at)",
        ),
        (
            "data_ingestion_task",
            {"status", "priority", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_data_ingestion_task_status_priority ON data_ingestion_task (status, priority, created_at)",
        ),
        (
            "data_ingestion_task",
            {"market", "board", "status"},
            "CREATE INDEX IF NOT EXISTS ix_data_ingestion_task_market_board ON data_ingestion_task (market, board, status)",
        ),
    ]
    with target_engine.begin() as connection:
        for table, columns, statement in statements:
            if _table_has_columns(target_engine, table, columns):
                connection.execute(text(statement))


def _ensure_api_performance_indexes(target_engine: Engine) -> None:
    statements = [
        (
            "daily_bar",
            {"stock_code", "source", "trade_date"},
            "CREATE INDEX IF NOT EXISTS ix_daily_bar_stock_source_date ON daily_bar (stock_code, source, trade_date)",
        ),
        (
            "daily_bar",
            {"source_kind", "source", "stock_code", "trade_date"},
            "CREATE INDEX IF NOT EXISTS ix_daily_bar_source_kind_source_stock_date ON daily_bar (source_kind, source, stock_code, trade_date)",
        ),
        (
            "daily_bar",
            {"source_kind", "stock_code"},
            "CREATE INDEX IF NOT EXISTS ix_daily_bar_stock_source_kind ON daily_bar (stock_code, source_kind)",
        ),
        (
            "industry_heat",
            {"trade_date", "heat_score"},
            "CREATE INDEX IF NOT EXISTS ix_industry_heat_date_score ON industry_heat (trade_date, heat_score)",
        ),
        (
            "data_source_run",
            {"finished_at", "id"},
            "CREATE INDEX IF NOT EXISTS ix_data_source_run_finished_id ON data_source_run (finished_at, id)",
        ),
    ]
    with target_engine.begin() as connection:
        for table, columns, statement in statements:
            if _table_has_columns(target_engine, table, columns):
                connection.execute(text(statement))


def _ensure_retail_research_indexes(target_engine: Engine) -> None:
    statements = [
        (
            "security_master",
            {"symbol", "market"},
            "CREATE INDEX IF NOT EXISTS ix_security_master_symbol_market ON security_master (symbol, market)",
        ),
        (
            "industry_chain_node",
            {"chain_name", "heat_score"},
            "CREATE INDEX IF NOT EXISTS ix_industry_chain_node_chain_heat ON industry_chain_node (chain_name, heat_score)",
        ),
        (
            "evidence_event",
            {"event_time", "confidence", "data_quality_status"},
            "CREATE INDEX IF NOT EXISTS ix_evidence_event_time_conf_quality ON evidence_event (event_time, confidence, data_quality_status)",
        ),
        (
            "retail_stock_pool",
            {"pool_level", "conviction_score", "status"},
            "CREATE INDEX IF NOT EXISTS ix_retail_stock_pool_level_score_status ON retail_stock_pool (pool_level, conviction_score, status)",
        ),
        (
            "retail_position",
            {"portfolio_id", "weight"},
            "CREATE INDEX IF NOT EXISTS ix_retail_position_portfolio_weight ON retail_position (portfolio_id, weight)",
        ),
        (
            "trade_journal",
            {"portfolio_id", "trade_date"},
            "CREATE INDEX IF NOT EXISTS ix_trade_journal_portfolio_date ON trade_journal (portfolio_id, trade_date)",
        ),
        (
            "trade_review",
            {"trade_journal_id", "review_date"},
            "CREATE INDEX IF NOT EXISTS ix_trade_review_journal_review_date ON trade_review (trade_journal_id, review_date)",
        ),
    ]
    with target_engine.begin() as connection:
        for table, columns, statement in statements:
            if _table_has_columns(target_engine, table, columns):
                connection.execute(text(statement))


def _ensure_agent_orchestrator_indexes(target_engine: Engine) -> None:
    statements = [
        (
            "agent_runs",
            {"status", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_agent_runs_status_created ON agent_runs (status, created_at)",
        ),
        (
            "agent_steps",
            {"run_id", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_agent_steps_run_created ON agent_steps (run_id, created_at)",
        ),
        (
            "agent_tool_calls",
            {"run_id", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_run_created ON agent_tool_calls (run_id, created_at)",
        ),
        (
            "agent_artifacts",
            {"run_id", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_agent_artifacts_run_created ON agent_artifacts (run_id, created_at)",
        ),
        (
            "agent_skills",
            {"skill_type", "is_system", "created_at"},
            "CREATE INDEX IF NOT EXISTS ix_agent_skills_type_system_created ON agent_skills (skill_type, is_system, created_at)",
        ),
    ]
    with target_engine.begin() as connection:
        for table, columns, statement in statements:
            if _table_has_columns(target_engine, table, columns):
                connection.execute(text(statement))


def _table_has_columns(target_engine: Engine, table_name: str, columns: set[str]) -> bool:
    inspector = inspect(target_engine)
    if not inspector.has_table(table_name):
        return False
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    return columns.issubset(existing)


def _ensure_operational_status_and_indexes(target_engine: Engine) -> None:
    _ensure_stock_asset_classification(target_engine)
    _ensure_ingestion_status_classification(target_engine)
    _ensure_query_indexes(target_engine)
    _ensure_api_performance_indexes(target_engine)


SCHEMA_MIGRATIONS = [
    SchemaMigration(1, "base_schema", _migration_base_schema),
    SchemaMigration(2, "stock_contract_additive_columns", _ensure_lightweight_migrations),
    SchemaMigration(3, "stock_score_confidence_columns", _ensure_stock_score_confidence_columns),
    SchemaMigration(4, "operational_status_and_indexes", _ensure_operational_status_and_indexes),
    SchemaMigration(5, "ingestion_task_runtime_columns", _ensure_ingestion_task_runtime_columns),
    SchemaMigration(6, "fundamental_metric_schema", _migration_fundamental_metric_schema),
    SchemaMigration(7, "news_article_source_columns", _ensure_news_article_source_columns),
    SchemaMigration(8, "market_source_quality_columns", _ensure_market_source_quality_columns),
    SchemaMigration(9, "industry_chain_graph_schema", _migration_industry_chain_graph_schema),
    SchemaMigration(10, "tenbagger_research_loop_schema", _migration_tenbagger_research_loop_schema),
    SchemaMigration(11, "api_performance_indexes", _migration_api_performance_indexes),
    SchemaMigration(12, "retail_research_loop_schema", _migration_retail_research_loop_schema),
    SchemaMigration(13, "news_article_hot_terms_trace_columns", _ensure_news_article_hot_terms_trace_columns),
    SchemaMigration(14, "mark_mock_news_synthetic", _migration_mark_mock_news_synthetic),
    SchemaMigration(15, "tenbagger_sniper_schema", _migration_tenbagger_sniper_schema),
    SchemaMigration(16, "agent_orchestrator_schema", _migration_agent_orchestrator_schema),
]


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
