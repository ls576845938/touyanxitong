from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
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
    source_channel: Mapped[str] = mapped_column(String(64), default="")
    source_label: Mapped[str] = mapped_column(String(64), default="")
    source_rank: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")
    related_industries: Mapped[str] = mapped_column(Text, default="[]")
    related_stocks: Mapped[str] = mapped_column(Text, default="[]")
    match_reason: Mapped[str] = mapped_column(Text, default='{"primary":"none","keyword":[],"industry":[],"alias":[],"unmatched":["none"]}')
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


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


class TenbaggerThesis(Base):
    __tablename__ = "tenbagger_thesis"
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uq_tenbagger_thesis_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), ForeignKey("stock.code"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    thesis_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    growth_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    valuation_score: Mapped[float] = mapped_column(Float, default=0.0)
    timing_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    readiness_score: Mapped[float] = mapped_column(Float, default=0.0)
    anti_thesis_score: Mapped[float] = mapped_column(Float, default=0.0)
    logic_gate_score: Mapped[float] = mapped_column(Float, default=0.0)
    logic_gate_status: Mapped[str] = mapped_column(String(16), default="WARN", index=True)
    stage: Mapped[str] = mapped_column(String(32), default="discovery", index=True)
    data_gate_status: Mapped[str] = mapped_column(String(16), default="FAIL", index=True)
    investment_thesis: Mapped[str] = mapped_column(Text, default="")
    base_case: Mapped[str] = mapped_column(Text, default="")
    bull_case: Mapped[str] = mapped_column(Text, default="")
    bear_case: Mapped[str] = mapped_column(Text, default="")
    logic_gates: Mapped[str] = mapped_column(Text, default="[]")
    anti_thesis_items: Mapped[str] = mapped_column(Text, default="[]")
    alternative_data_signals: Mapped[str] = mapped_column(Text, default="[]")
    valuation_simulation: Mapped[str] = mapped_column(Text, default="{}")
    contrarian_signal: Mapped[str] = mapped_column(Text, default="{}")
    sniper_focus: Mapped[str] = mapped_column(Text, default="[]")
    key_milestones: Mapped[str] = mapped_column(Text, default="[]")
    disconfirming_evidence: Mapped[str] = mapped_column(Text, default="[]")
    missing_evidence: Mapped[str] = mapped_column(Text, default="[]")
    source_refs: Mapped[str] = mapped_column(Text, default="[]")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stock: Mapped[Stock] = relationship("Stock")


class SignalBacktestRun(Base):
    __tablename__ = "signal_backtest_run"
    __table_args__ = (UniqueConstraint("run_key", name="uq_signal_backtest_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=120, index=True)
    min_score: Mapped[float] = mapped_column(Float, default=0.0)
    market: Mapped[str] = mapped_column(String(16), default="ALL", index=True)
    board: Mapped[str] = mapped_column(String(24), default="all", index=True)
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    average_forward_return: Mapped[float] = mapped_column(Float, default=0.0)
    median_forward_return: Mapped[float] = mapped_column(Float, default=0.0)
    average_max_return: Mapped[float] = mapped_column(Float, default=0.0)
    hit_rate_2x: Mapped[float] = mapped_column(Float, default=0.0)
    hit_rate_5x: Mapped[float] = mapped_column(Float, default=0.0)
    hit_rate_10x: Mapped[float] = mapped_column(Float, default=0.0)
    bucket_summary: Mapped[str] = mapped_column(Text, default="[]")
    rating_summary: Mapped[str] = mapped_column(Text, default="[]")
    confidence_summary: Mapped[str] = mapped_column(Text, default="[]")
    failures: Mapped[str] = mapped_column(Text, default="[]")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityMaster(Base):
    __tablename__ = "security_master"
    __table_args__ = (UniqueConstraint("symbol", "market", name="uq_security_master_symbol_market"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="", index=True)
    market: Mapped[str] = mapped_column(String(16), default="A", index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    company_name: Mapped[str] = mapped_column(String(128), default="")
    industry_level_1: Mapped[str] = mapped_column(String(64), default="", index=True)
    industry_level_2: Mapped[str] = mapped_column(String(64), default="")
    industry_level_3: Mapped[str] = mapped_column(String(64), default="")
    concept_tags: Mapped[str] = mapped_column(Text, default="[]")
    main_products: Mapped[str] = mapped_column(Text, default="[]")
    business_summary: Mapped[str] = mapped_column(Text, default="")
    revenue_drivers: Mapped[str] = mapped_column(Text, default="[]")
    cost_drivers: Mapped[str] = mapped_column(Text, default="[]")
    profit_drivers: Mapped[str] = mapped_column(Text, default="[]")
    macro_sensitivities: Mapped[str] = mapped_column(Text, default="[]")
    upstream_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    downstream_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    related_security_ids: Mapped[str] = mapped_column(Text, default="[]")
    data_source: Mapped[str] = mapped_column(String(64), default="stock_universe", index=True)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IndustryChainNode(Base):
    __tablename__ = "industry_chain_node"
    __table_args__ = (UniqueConstraint("chain_name", "name", name="uq_industry_chain_node_chain_name"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    level: Mapped[int] = mapped_column(Integer, default=0, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("industry_chain_node.id"), nullable=True, index=True)
    chain_name: Mapped[str] = mapped_column(String(96), index=True)
    node_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    key_metrics: Mapped[str] = mapped_column(Text, default="[]")
    macro_drivers: Mapped[str] = mapped_column(Text, default="[]")
    visible_indicators: Mapped[str] = mapped_column(Text, default="[]")
    related_terms: Mapped[str] = mapped_column(Text, default="[]")
    related_security_ids: Mapped[str] = mapped_column(Text, default="[]")
    upstream_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    downstream_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    region_tags: Mapped[str] = mapped_column(Text, default="[]")
    heat_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EvidenceEvent(Base):
    __tablename__ = "evidence_event"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(32), default="新闻", index=True)
    raw_text_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    affected_objects: Mapped[str] = mapped_column(Text, default="[]")
    affected_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    affected_security_ids: Mapped[str] = mapped_column(Text, default="[]")
    impact_direction: Mapped[str] = mapped_column(String(16), default="uncertain", index=True)
    impact_strength: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    duration_type: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    logic_chain: Mapped[str] = mapped_column(Text, default="")
    risk_notes: Mapped[str] = mapped_column(Text, default="")
    evidence_tags: Mapped[str] = mapped_column(Text, default="[]")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    data_quality_status: Mapped[str] = mapped_column(String(16), default="WARN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RetailStockPool(Base):
    __tablename__ = "retail_stock_pool"
    __table_args__ = (UniqueConstraint("security_id", name="uq_retail_stock_pool_security"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(Integer, ForeignKey("security_master.id"), index=True)
    pool_level: Mapped[str] = mapped_column(String(16), default="C", index=True)
    pool_reason: Mapped[str] = mapped_column(Text, default="")
    thesis_summary: Mapped[str] = mapped_column(Text, default="")
    key_evidence_event_ids: Mapped[str] = mapped_column(Text, default="[]")
    related_node_ids: Mapped[str] = mapped_column(Text, default="[]")
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    industry_heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    valuation_score: Mapped[float] = mapped_column(Float, default=50.0)
    quality_score: Mapped[float] = mapped_column(Float, default=50.0)
    risk_score: Mapped[float] = mapped_column(Float, default=50.0)
    tenbagger_score: Mapped[float] = mapped_column(Float, default=0.0)
    conviction_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    user_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="watching", index=True)
    invalidation_conditions: Mapped[str] = mapped_column(Text, default="[]")
    next_tracking_tasks: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RetailPortfolio(Base):
    __tablename__ = "retail_portfolio"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="默认研究组合", index=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="CNY")
    benchmark: Mapped[str] = mapped_column(String(64), default="沪深300")
    user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RetailPosition(Base):
    __tablename__ = "retail_position"
    __table_args__ = (UniqueConstraint("portfolio_id", "security_id", name="uq_retail_position_portfolio_security"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("retail_portfolio.id"), index=True)
    security_id: Mapped[int] = mapped_column(Integer, ForeignKey("security_master.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    market_value: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    industry_exposure: Mapped[str] = mapped_column(String(96), default="")
    theme_exposure: Mapped[str] = mapped_column(Text, default="[]")
    chain_node_exposure: Mapped[str] = mapped_column(Text, default="[]")
    factor_tags: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TradeJournal(Base):
    __tablename__ = "trade_journal"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("retail_portfolio.id"), index=True)
    security_id: Mapped[int] = mapped_column(Integer, ForeignKey("security_master.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(24), default="watch", index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    position_weight_after_trade: Mapped[float] = mapped_column(Float, default=0.0)
    trade_reason: Mapped[str] = mapped_column(Text, default="")
    linked_evidence_event_ids: Mapped[str] = mapped_column(Text, default="[]")
    linked_stock_pool_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("retail_stock_pool.id"), nullable=True, index=True)
    expected_scenario: Mapped[str] = mapped_column(Text, default="")
    invalidation_condition: Mapped[str] = mapped_column(Text, default="")
    risk_assessment: Mapped[str] = mapped_column(Text, default="")
    user_emotion: Mapped[str] = mapped_column(String(24), default="calm", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeReview(Base):
    __tablename__ = "trade_review"
    __table_args__ = (UniqueConstraint("trade_journal_id", name="uq_trade_review_journal"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_journal_id: Mapped[int] = mapped_column(Integer, ForeignKey("trade_journal.id"), index=True)
    review_date: Mapped[date] = mapped_column(Date, index=True)
    holding_period_days: Mapped[int] = mapped_column(Integer, default=0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_return: Mapped[float] = mapped_column(Float, default=0.0)
    excess_return: Mapped[float] = mapped_column(Float, default=0.0)
    result_type: Mapped[str] = mapped_column(String(16), default="unfinished", index=True)
    attribution_logic: Mapped[str] = mapped_column(String(32), default="luck", index=True)
    what_happened: Mapped[str] = mapped_column(Text, default="")
    what_expected: Mapped[str] = mapped_column(Text, default="")
    error_category: Mapped[str] = mapped_column(String(32), default="no_error", index=True)
    should_update_model_rules: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_update_suggestion: Mapped[str] = mapped_column(Text, default="")
    next_action: Mapped[str] = mapped_column(String(32), default="continue_watch", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(64), default="auto", index=True)
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    runtime_provider: Mapped[str] = mapped_column(String(32), default="mock", index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    selected_symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_industries_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id"), index=True)
    agent_role: Mapped[str] = mapped_column(String(64), default="orchestrator", index=True)
    step_name: Mapped[str] = mapped_column(String(96), default="", index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(96), default="", index=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentArtifact(Base):
    __tablename__ = "agent_artifacts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), default="research_report", index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    skill_type: Mapped[str] = mapped_column(String(64), default="custom", index=True)
    skill_md: Mapped[str] = mapped_column(Text, default="")
    skill_config_json: Mapped[str] = mapped_column(Text, default="{}")
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentFollowup(Base):
    __tablename__ = "agent_followups"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(32), default="auto")
    answer_md: Mapped[str] = mapped_column(Text, default="")
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    saved_artifact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def _normalized_confidence(value: int | float | None) -> float:
    try:
        numeric = float(value or 0.0)
    except Exception:
        numeric = 0.0
    return max(0.0, min(100.0, numeric))


@event.listens_for(EvidenceEvent, "before_insert")
@event.listens_for(EvidenceEvent, "before_update")
def _enforce_evidence_event_constraints(_mapper, _connection, target: EvidenceEvent) -> None:
    target.confidence = _normalized_confidence(target.confidence)
    source_name = str(target.source_name or "").strip()
    source_url = str(target.source_url or "").strip()
    if not source_name or not source_url:
        target.confidence = min(target.confidence, 50.0)
    target.data_quality_status = str(target.data_quality_status or "WARN").upper()
    if target.is_mock and target.data_quality_status != "FAIL":
        target.data_quality_status = "FAIL"


@event.listens_for(RetailStockPool, "before_insert")
@event.listens_for(RetailStockPool, "before_update")
def _normalize_stock_pool_level(_mapper, _connection, target: RetailStockPool) -> None:
    level = str(target.pool_level or "C").upper()
    if float(target.quality_score or 0.0) <= 30.0 and level in {"S", "A"}:
        level = "C"
    target.pool_level = level
