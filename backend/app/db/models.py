from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(16), default="A", index=True)
    board: Mapped[str] = mapped_column(String(24), default="main", index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    industry_level1: Mapped[str] = mapped_column(String(64), index=True)
    industry_level2: Mapped[str] = mapped_column(String(64), default="")
    concepts: Mapped[str] = mapped_column(Text, default="[]")
    asset_type: Mapped[str] = mapped_column(String(24), default="equity", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", index=True)
    listing_status: Mapped[str] = mapped_column(String(24), default="listed", index=True)
    market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    float_market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_st: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_adr: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="mock")
    data_vendor: Mapped[str] = mapped_column(String(64), default="mock", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DailyBar(Base):
    __tablename__ = "daily_bar"
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", "source", name="uq_daily_bar_code_date_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    pre_close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    pct_chg: Mapped[float] = mapped_column(Float)
    adj_factor: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(64), default="mock")
    source_kind: Mapped[str] = mapped_column(String(16), default="mock", index=True)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stock: Mapped[Stock] = relationship("Stock")


class FundamentalMetric(Base):
    __tablename__ = "fundamental_metric"
    __table_args__ = (
        UniqueConstraint("stock_code", "report_date", "period", "source", name="uq_fundamental_metric_code_report_period_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(16), default="FY", index=True)
    revenue_growth_yoy: Mapped[float] = mapped_column(Float, default=0.0)
    profit_growth_yoy: Mapped[float] = mapped_column(Float, default=0.0)
    gross_margin: Mapped[float] = mapped_column(Float, default=0.0)
    roe: Mapped[float] = mapped_column(Float, default=0.0)
    debt_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    cashflow_quality: Mapped[float] = mapped_column(Float, default=0.0)
    report_title: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="mock", index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stock: Mapped[Stock] = relationship("Stock")


class Industry(Base):
    __tablename__ = "industry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("industry.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IndustryKeyword(Base):
    __tablename__ = "industry_keyword"
    __table_args__ = (UniqueConstraint("industry_id", "keyword", name="uq_industry_keyword"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("industry.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(64), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    industry: Mapped[Industry] = relationship("Industry")


class ChainNode(Base):
    __tablename__ = "chain_node"
    __table_args__ = (UniqueConstraint("node_key", name="uq_chain_node_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    layer: Mapped[str] = mapped_column(String(32), index=True)
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chain_node.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    physical_inputs: Mapped[str] = mapped_column(Text, default="[]")
    physical_outputs: Mapped[str] = mapped_column(Text, default="[]")
    gics_codes: Mapped[str] = mapped_column(Text, default="[]")
    isic_codes: Mapped[str] = mapped_column(Text, default="[]")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChainEdge(Base):
    __tablename__ = "chain_edge"
    __table_args__ = (UniqueConstraint("source_node_id", "target_node_id", "relation_type", name="uq_chain_edge_relation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    target_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="physical_flow", index=True)
    flow: Mapped[str] = mapped_column(String(128), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    direction: Mapped[str] = mapped_column(String(16), default="forward", index=True)
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChainNodeIndustryMap(Base):
    __tablename__ = "chain_node_industry_map"
    __table_args__ = (UniqueConstraint("node_id", "industry_id", "role", name="uq_chain_node_industry_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("industry.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="mapped", index=True)
    exposure: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainNodeStockMap(Base):
    __tablename__ = "chain_node_stock_map"
    __table_args__ = (UniqueConstraint("node_id", "stock_code", "role", name="uq_chain_node_stock_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="leader", index=True)
    exposure: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainNodeRegion(Base):
    __tablename__ = "chain_node_region"
    __table_args__ = (UniqueConstraint("node_id", "region_key", "geo_role", name="uq_chain_node_region_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    region_key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(96), default="")
    geo_role: Mapped[str] = mapped_column(String(32), default="capacity", index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainNodeIndicator(Base):
    __tablename__ = "chain_node_indicator"
    __table_args__ = (UniqueConstraint("node_id", "instrument_type", "instrument_code", name="uq_chain_node_indicator"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    instrument_type: Mapped[str] = mapped_column(String(32), index=True)
    instrument_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(64), default="seed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainNodeHeat(Base):
    __tablename__ = "chain_node_heat"
    __table_args__ = (UniqueConstraint("node_id", "trade_date", name="uq_chain_node_heat_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("chain_node.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    momentum_score: Mapped[float] = mapped_column(Float, default=0.0)
    stock_momentum: Mapped[float] = mapped_column(Float, default=0.0)
    industry_heat: Mapped[float] = mapped_column(Float, default=0.0)
    commodity_signal: Mapped[float] = mapped_column(Float, default=0.0)
    news_heat: Mapped[float] = mapped_column(Float, default=0.0)
    geo_heat: Mapped[float] = mapped_column(Float, default=0.0)
    propagated_heat: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsArticle(Base):
    __tablename__ = "news_article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="mock")
    source_kind: Mapped[str] = mapped_column(String(24), default="mock", index=True)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.3)
    source_url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")
    related_industries: Mapped[str] = mapped_column(Text, default="[]")
    related_stocks: Mapped[str] = mapped_column(Text, default="[]")


class TrendSignal(Base):
    __tablename__ = "trend_signal"
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uq_trend_signal_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    ma20: Mapped[float] = mapped_column(Float, default=0.0)
    ma60: Mapped[float] = mapped_column(Float, default=0.0)
    ma120: Mapped[float] = mapped_column(Float, default=0.0)
    ma250: Mapped[float] = mapped_column(Float, default=0.0)
    return_20d: Mapped[float] = mapped_column(Float, default=0.0)
    return_60d: Mapped[float] = mapped_column(Float, default=0.0)
    return_120d: Mapped[float] = mapped_column(Float, default=0.0)
    relative_strength_score: Mapped[float] = mapped_column(Float, default=0.0)
    relative_strength_rank: Mapped[int] = mapped_column(Integer, default=0)
    is_ma_bullish: Mapped[bool] = mapped_column(Boolean, default=False)
    is_breakout_120d: Mapped[bool] = mapped_column(Boolean, default=False)
    is_breakout_250d: Mapped[bool] = mapped_column(Boolean, default=False)
    volume_expansion_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_60d: Mapped[float] = mapped_column(Float, default=0.0)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IndustryHeat(Base):
    __tablename__ = "industry_heat"
    __table_args__ = (UniqueConstraint("industry_id", "trade_date", name="uq_industry_heat_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("industry.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    heat_1d: Mapped[float] = mapped_column(Float, default=0.0)
    heat_7d: Mapped[float] = mapped_column(Float, default=0.0)
    heat_30d: Mapped[float] = mapped_column(Float, default=0.0)
    heat_change_7d: Mapped[float] = mapped_column(Float, default=0.0)
    heat_change_30d: Mapped[float] = mapped_column(Float, default=0.0)
    top_keywords: Mapped[str] = mapped_column(Text, default="[]")
    top_articles: Mapped[str] = mapped_column(Text, default="[]")
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    industry: Mapped[Industry] = relationship("Industry")


class StockScore(Base):
    __tablename__ = "stock_score"
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uq_stock_score_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    industry_score: Mapped[float] = mapped_column(Float, default=0.0)
    company_score: Mapped[float] = mapped_column(Float, default=0.0)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    catalyst_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    raw_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    fundamental_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    news_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_level: Mapped[str] = mapped_column(String(24), default="unknown")
    confidence_reasons: Mapped[str] = mapped_column(Text, default="[]")
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[str] = mapped_column(String(16), default="仅记录")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stock: Mapped[Stock] = relationship("Stock")


class EvidenceChain(Base):
    __tablename__ = "evidence_chain"
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uq_evidence_chain_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    industry_logic: Mapped[str] = mapped_column(Text, default="")
    company_logic: Mapped[str] = mapped_column(Text, default="")
    trend_logic: Mapped[str] = mapped_column(Text, default="")
    catalyst_logic: Mapped[str] = mapped_column(Text, default="")
    risk_summary: Mapped[str] = mapped_column(Text, default="")
    questions_to_verify: Mapped[str] = mapped_column(Text, default="[]")
    source_refs: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyReport(Base):
    __tablename__ = "daily_report"
    __table_args__ = (UniqueConstraint("report_date", name="uq_daily_report_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(Text)
    market_summary: Mapped[str] = mapped_column(Text, default="")
    top_industries: Mapped[str] = mapped_column(Text, default="[]")
    top_trend_stocks: Mapped[str] = mapped_column(Text, default="[]")
    new_watchlist_stocks: Mapped[str] = mapped_column(Text, default="[]")
    risk_alerts: Mapped[str] = mapped_column(Text, default="[]")
    full_markdown: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataSourceRun(Base):
    __tablename__ = "data_source_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    requested_source: Mapped[str] = mapped_column(String(64), default="mock")
    effective_source: Mapped[str] = mapped_column(String(64), default="mock")
    source_kind: Mapped[str] = mapped_column(String(16), default="mock", index=True)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.1)
    markets: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataIngestionBatch(Base):
    __tablename__ = "data_ingestion_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(16), default="ALL", index=True)
    board: Mapped[str] = mapped_column(String(24), default="all", index=True)
    source: Mapped[str] = mapped_column(String(64), default="mock")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    offset: Mapped[int] = mapped_column(Integer, default=0)
    requested: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataIngestionTask(Base):
    __tablename__ = "data_ingestion_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String(24), default="batch", index=True)
    market: Mapped[str] = mapped_column(String(16), default="ALL", index=True)
    board: Mapped[str] = mapped_column(String(24), default="all", index=True)
    stock_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="mock", index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    batch_offset: Mapped[int] = mapped_column(Integer, default=0)
    batch_limit: Mapped[int] = mapped_column(Integer, default=20)
    periods: Mapped[int] = mapped_column(Integer, default=320)
    requested: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    rate_limit_seconds: Mapped[float] = mapped_column(Float, default=0.2)
    error: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_stock: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist_item"
    __table_args__ = (UniqueConstraint("stock_code", name="uq_watchlist_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="观察")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
