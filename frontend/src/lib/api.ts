const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "";
const DEFAULT_GET_CACHE_MS = 30_000;
const getCache = new Map<string, { expiresAt: number; promise?: Promise<unknown>; value?: unknown }>();

export type MarketSummary = {
  stock_count: number;
  latest_trade_date: string | null;
  watch_count: number;
  industry_heat_records: number;
  latest_report_title: string | null;
  markets: MarketSegment[];
  boundary: string;
};

export type MarketSegment = {
  market: string;
  label: string;
  stock_count: number;
  watch_count: number;
  boards: {
    board: string;
    label: string;
    stock_count: number;
    watch_count: number;
  }[];
};

export type DataStatus = {
  coverage: {
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    stock_count: number;
    stocks_with_bars: number;
    coverage_ratio: number;
    latest_trade_date: string | null;
  }[];
  source_coverage?: {
    source_kind: string;
    source: string;
    bars_count: number;
    stocks_with_bars: number;
    first_trade_date: string | null;
    latest_trade_date: string | null;
  }[];
  runs: {
    job_name: string;
    requested_source: string;
    effective_source: string;
    source_kind?: string;
    source_confidence?: number;
    markets: string[];
    status: string;
    rows_inserted: number;
    rows_updated: number;
    rows_total: number;
    error: string;
    started_at: string;
    finished_at: string | null;
  }[];
};

export type DataQuality = {
  status: "PASS" | "WARN" | "FAIL";
  summary: {
    stock_count: number;
    issue_count: number;
    fail_count: number;
    warn_count: number;
    min_required_bars: number;
    preferred_bars: number;
    stocks_with_real_bars?: number;
  };
  segments: {
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    status: "PASS" | "WARN" | "FAIL";
    formal_research_allowed?: boolean;
    backfill_priority?: "high" | "medium" | "low";
    recommended_action?: string;
    blocking_reasons?: string[];
    stock_count: number;
    stocks_with_bars: number;
    stocks_with_required_history: number;
    stocks_with_preferred_history: number;
    coverage_ratio: number;
    real_coverage_ratio?: number;
    required_history_ratio: number;
    preferred_history_ratio: number;
    avg_bars: number;
    latest_trade_date: string | null;
    source_kind_coverage?: Record<string, {
      stocks_with_bars: number;
      coverage_ratio: number;
      bars_count: number;
    }>;
  }[];
  issues: {
    code: string;
    name: string;
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    severity: "WARN" | "FAIL";
    issue_type: string;
    message: string;
    remediation?: {
      action: string;
      api?: string;
      payload?: Record<string, unknown>;
    };
    bars_count: number;
    latest_trade_date: string | null;
    source_kinds?: string[];
    real_bars_count?: number;
  }[];
};

export type QualityBackfillPlan = {
  focus: string;
  periods: number;
  limit_per_segment: number;
  next_actions: string[];
  segments: {
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    status: "PASS" | "WARN" | "FAIL";
    priority: "high" | "medium" | "low";
    reason: string;
    stats: {
      stock_count: number;
      stocks_with_bars: number;
      without_bars: number;
      stocks_with_required_history: number;
      stocks_with_preferred_history: number;
      stocks_with_real_bars: number;
      coverage_ratio: number;
      required_history_ratio: number;
      preferred_history_ratio: number;
      real_coverage_ratio: number;
      latest_trade_date: string | null;
    };
    candidate_count: number;
    candidates: {
      code: string;
      name: string;
      market: string;
      board: string;
      bars_count: number;
      latest_trade_date: string | null;
      priority_reason?: string;
    }[];
    queue_payload: {
      markets: string[];
      board: string;
      batches_per_market: number;
      batch_limit: number;
      periods: number;
    };
    queue_api: string;
    queue_command: string;
  }[];
};

export type IngestionPlan = {
  mode: string;
  settings: {
    mock_data: boolean;
    market_data_source: string;
    enabled_markets: string[];
    max_stocks_per_market: number;
    market_data_periods: number;
  };
  markets: {
    market: string;
    label: string;
    stock_count: number;
    stocks_with_bars: number;
    coverage_ratio: number;
    latest_trade_date: string | null;
    next_batch_size: number;
    remaining_without_bars: number;
    next_batch_offset: number;
  }[];
  quality_backfill_focus?: QualityBackfillPlan;
  discovery_commands: string[];
  recommended_commands: string[];
  safety_rules: string[];
};

export type BackfillManifest = {
  status: string;
  updated_at: string | null;
  finished_at: string | null;
  manifest_path: string | null;
  database?: {
    url?: string;
    path?: string | null;
  };
  totals?: {
    batches?: number;
    inserted?: number;
    updated?: number;
    failed_symbols?: number;
    processed_symbols?: number;
  };
  coverage?: {
    market: string;
    eligible_symbols: number;
    covered_symbols: number;
    partial_symbols: number;
    empty_symbols: number;
    coverage_ratio: number;
    average_bars: number;
    latest_trade_date: string | null;
    complete_bars_threshold: number;
  }[];
};

export type InstrumentRow = {
  code: string;
  name: string;
  market: string;
  market_label: string;
  board: string;
  board_label: string;
  exchange: string;
  asset_type: string;
  currency: string;
  listing_status: string;
  industry_level1: string;
  industry_level2: string;
  market_cap: number;
  float_market_cap: number;
  listing_date: string | null;
  delisting_date: string | null;
  is_st: boolean;
  is_etf: boolean;
  is_adr: boolean;
  is_active: boolean;
  source: string;
  data_vendor: string;
  bars_count: number;
  latest_trade_date: string | null;
  updated_at: string;
};

export type InstrumentsResponse = {
  total: number;
  limit: number;
  offset: number;
  rows: InstrumentRow[];
};

export type InstrumentNavigation = {
  current: InstrumentRow;
  previous: InstrumentRow | null;
  next: InstrumentRow | null;
  scope: {
    market: string;
    market_label: string;
    board: string;
    board_label: string;
  };
};

export type IngestionBatch = {
  batch_key: string;
  job_name: string;
  market: string;
  board: string;
  source: string;
  status: string;
  offset: number;
  requested: number;
  processed: number;
  inserted: number;
  updated: number;
  failed: number;
  error: string;
  started_at: string;
  finished_at: string | null;
};

export type IngestionTask = {
  id: number;
  task_key: string;
  task_type: string;
  market: string;
  board: string;
  stock_code: string | null;
  source: string;
  status: string;
  priority: number;
  batch_limit: number;
  periods: number;
  requested: number;
  processed: number;
  inserted: number;
  updated: number;
  failed: number;
  retry_count: number;
  max_retries: number;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type IngestionPriorityCandidate = {
  code: string;
  name: string;
  market: string;
  board: string;
  market_cap: number;
  float_market_cap: number;
  bars_count: number;
  missing_bars: number;
  latest_trade_date: string | null;
  priority_score: number;
};

export type IngestionPriority = {
  market: string;
  board: string;
  limit: number;
  periods: number;
  candidates: IngestionPriorityCandidate[];
};

export type IngestionBackfillResult = {
  markets: string[];
  board: string;
  batches_per_market: number;
  batch_limit: number;
  periods: number;
  queued_count: number;
  skipped_count: number;
  queued_tasks: IngestionTask[];
  skipped: {
    market: string;
    board: string;
    reason: string;
    pending: number;
  }[];
};

export type IngestionQueueRunResult = {
  tasks_run: number;
  max_tasks: number;
  stopped_reason: string;
  tasks: IngestionTask[];
};

export type ResearchUniverse = {
  summary: {
    stock_count: number;
    eligible_count: number;
    excluded_count: number;
    eligible_ratio: number;
  };
  segments: {
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    stock_count: number;
    eligible_count: number;
    excluded_count: number;
    eligible_ratio: number;
  }[];
  rules: Record<string, Record<string, number>>;
  rows: {
    code: string;
    name: string;
    market: string;
    market_label: string;
    board: string;
    board_label: string;
    eligible: boolean;
    exclusion_reasons: string[];
    market_cap: number;
    float_market_cap: number;
    bars_count: number;
    latest_trade_date: string | null;
    latest_close: number;
    avg_amount_20d: number;
    avg_volume_20d: number;
  }[];
};

export type IndustryRadarRow = {
  industry_id: number;
  name: string;
  trade_date: string | null;
  heat_score: number;
  global_heat_score?: number | null;
  news_heat_score?: number | null;
  structure_heat_score?: number | null;
  heat_1d: number;
  heat_7d: number;
  heat_30d: number;
  heat_change_7d: number;
  heat_change_30d: number;
  market: string;
  market_label: string;
  related_stock_count: number;
  scored_stock_count: number;
  watch_stock_count: number;
  top_keywords: string[];
  top_articles: string[];
  heat_status?: "active" | "zero" | string;
  evidence_status?: "news_active" | "structure_active" | "mapped_only" | "no_evidence" | string;
  trend_breadth?: number | null;
  breakout_breadth?: number | null;
  zero_heat_reason?: string;
  explanation: string;
};

export type IndustryTimelineRow = {
  industry_id: number;
  name: string;
  trade_date: string;
  heat_score: number;
  global_heat_score?: number | null;
  news_heat_score?: number | null;
  structure_heat_score?: number | null;
  heat_score_delta: number | null;
  heat_1d: number;
  heat_7d: number;
  heat_7d_delta: number | null;
  heat_30d: number;
  heat_30d_delta: number | null;
  heat_change_7d: number;
  heat_change_30d: number;
  top_keywords: string[];
  top_articles: string[];
  heat_status?: "active" | "zero" | string;
  evidence_status?: "news_active" | "structure_active" | "mapped_only" | "no_evidence" | string;
  trend_breadth?: number | null;
  breakout_breadth?: number | null;
  zero_heat_reason?: string;
  explanation: string;
};

export type IndustryTimelineItem = {
  trade_date: string;
  previous_date: string | null;
  summary: {
    industry_count: number;
    hot_industry_count: number;
    rising_count: number;
    cooling_count: number;
    total_heat_score: number;
    average_heat_score: number;
  };
  top_industries: IndustryTimelineRow[];
  rising_industries: IndustryTimelineRow[];
  cooling_industries: IndustryTimelineRow[];
  industries: IndustryTimelineRow[];
};

export type IndustryTimeline = {
  latest: IndustryTimelineItem | null;
  timeline: IndustryTimelineItem[];
};

export type IndustryDetailStock = {
  code: string;
  name: string;
  market: string;
  board: string;
  exchange: string;
  industry_level2: string;
  concepts: string[];
  market_cap: number;
  float_market_cap: number;
  trade_date: string | null;
  final_score: number | null;
  rating: string | null;
  industry_score: number | null;
  company_score: number | null;
  trend_score: number | null;
  catalyst_score: number | null;
  risk_penalty: number | null;
  relative_strength_rank: number | null;
  is_ma_bullish: boolean | null;
  is_breakout_120d: boolean | null;
  is_breakout_250d: boolean | null;
};

export type IndustryDetail = {
  industry: {
    id: number;
    name: string;
    description: string;
    keywords: string[];
  };
  latest_heat: IndustryTimelineRow | null;
  heat_history: IndustryTimelineRow[];
  summary: {
    market: string;
    market_label: string;
    related_stock_count: number;
    watch_stock_count: number;
    strong_watch_count: number;
    recent_article_count: number;
  };
  related_stocks: IndustryDetailStock[];
  recent_articles: {
    title: string;
    summary: string;
    source: string;
    source_kind?: string;
    source_confidence?: number;
    source_channel?: string;
    source_label?: string;
    source_rank?: number;
    source_url: string;
    published_at: string;
    matched_keywords: string[];
    related_stocks: string[];
    match_reason?: string;
    is_synthetic?: boolean;
  }[];
};

export type ChainNode = {
  node_key: string;
  name: string;
  layer: string;
  node_type: string;
  description?: string;
  industry_names?: string[];
  tags?: string[];
  heat?: number | null;
  momentum?: number | null;
  intensity?: number | null;
  anchor_companies?: string[];
  indicators?: {
    label: string;
    value: string | number | null;
    change?: number | null;
    unit?: string;
    trend?: string;
  }[];
  stock_count?: number | null;
};

export type ChainEdge = {
  source: string;
  target: string;
  relation_type?: string;
  flow?: string;
  weight?: number | null;
  heat?: number | null;
  intensity?: number | null;
};

export type ChainLayer = {
  key: string;
  label: string;
  count?: number | null;
  order?: number | null;
};

export type ChainRegion = {
  region_key: string;
  label: string;
  heat?: number | null;
  intensity?: number | null;
  share?: number | null;
  summary?: string;
  country_count?: number | null;
  hubs?: string[];
  industries?: string[];
  x?: number | null;
  y?: number | null;
};

export type ChainRoute = {
  from_key: string;
  to_key: string;
  flow?: string;
  weight?: number | null;
  heat?: number | null;
  intensity?: number | null;
};

export type ChainOverview = {
  summary: {
    snapshot_date?: string | null;
    node_count?: number | null;
    edge_count?: number | null;
    region_count?: number | null;
    [key: string]: unknown;
  };
  layers: Array<ChainLayer | string>;
  nodes: ChainNode[];
  edges: ChainEdge[];
  regions?: ChainRegion[];
  default_focus_node_key?: string | null;
};

export type ChainMappedIndustry = {
  id?: number | string;
  node_key?: string;
  name: string;
  market?: string;
  heat?: number | null;
};

export type ChainLeaderStock = {
  code: string;
  name: string;
  market?: string;
  board?: string;
  market_cap?: number | null;
  final_score?: number | null;
  industry_level2?: string;
  reason?: string;
};

export type ChainNodeIndicator = {
  label: string;
  value: string | number | null;
  change?: number | null;
  unit?: string;
  trend?: string;
};

export type ChainNodeDetail = {
  node: ChainNode;
  upstream: ChainNode[];
  downstream: ChainNode[];
  same_layer?: ChainNode[];
  edges: ChainEdge[];
  mapped_industries?: Array<ChainMappedIndustry | string>;
  leader_stocks?: ChainLeaderStock[];
  regions?: ChainRegion[];
  indicators?: ChainNodeIndicator[];
  heat_explanation?: string[];
};

export type ChainGeo = {
  node_key: string;
  regions: ChainRegion[];
  routes: ChainRoute[];
};

export type ChainTimelinePoint = {
  date?: string;
  trade_date?: string;
  heat?: number | null;
  momentum?: number | null;
  intensity?: number | null;
  label?: string;
  summary?: string;
  regions?: { region_key: string; heat?: number | null; intensity?: number | null }[];
};

export type ChainTimeline = {
  node_key: string;
  timeline: ChainTimelinePoint[];
};

export type TrendPoolRow = {
  code: string;
  name: string;
  market: string;
  board: string;
  exchange: string;
  industry: string;
  industry_level2: string;
  final_score: number;
  rating: string;
  industry_score: number;
  company_score: number;
  trend_score: number;
  catalyst_score: number;
  risk_penalty: number;
  relative_strength_rank: number;
  is_ma_bullish: boolean;
  is_breakout_120d: boolean;
  is_breakout_250d: boolean;
  volume_expansion_ratio: number;
  research_eligible: boolean;
  research_gate?: ResearchGate;
  confidence?: ScoreConfidence;
  fundamental_summary?: FundamentalSummary;
  news_evidence_status?: EvidenceStatus;
  explanation: string;
};

export type EvidenceStatus = "active" | "partial" | "missing" | "sourced" | "needs_verification" | string;

export type ScoreConfidence = {
  source_confidence: number | null;
  data_confidence: number | null;
  fundamental_confidence: number | null;
  news_confidence: number | null;
  evidence_confidence: number | null;
  combined_confidence: number | null;
  level: "high" | "medium" | "low" | "insufficient" | "unknown" | string;
  reasons: string[];
};

export type ResearchGate = {
  passed: boolean;
  status: "pass" | "review" | string;
  reasons: string[];
};

export type FundamentalSummary = {
  status: "complete" | "partial" | "unknown" | string;
  market_cap?: number;
  float_market_cap?: number;
  confidence: number | null;
  missing_items: string[];
};

export type DailyReport = {
  report_date: string;
  title: string;
  market_summary: string;
  top_industries: Record<string, unknown>[];
  top_trend_stocks: TrendPoolRow[];
  new_watchlist_stocks: TrendPoolRow[];
  risk_alerts: string[];
  data_quality: DataQuality;
  research_universe: ResearchUniverse;
  watchlist_changes: WatchlistChanges;
  full_markdown: string;
};

export type ReportSummary = {
  report_date: string;
  title: string;
  market_summary: string;
  watch_count: number;
  risk_count: number;
  created_at: string;
};

export type WatchlistChangeRow = {
  code: string;
  name: string;
  market: string;
  board: string;
  industry: string;
  change_type: string;
  rating: string | null;
  previous_rating: string | null;
  final_score: number | null;
  previous_score: number | null;
  score_delta: number | null;
};

export type WatchlistChanges = {
  latest_date: string | null;
  previous_date: string | null;
  summary: {
    latest_watch_count: number;
    previous_watch_count: number;
    new_count: number;
    removed_count: number;
    upgraded_count: number;
    downgraded_count: number;
    score_gainer_count: number;
    score_loser_count: number;
  };
  new_entries: WatchlistChangeRow[];
  removed_entries: WatchlistChangeRow[];
  upgraded: WatchlistChangeRow[];
  downgraded: WatchlistChangeRow[];
  score_gainers: WatchlistChangeRow[];
  score_losers: WatchlistChangeRow[];
};

export type WatchlistTopRow = {
  code: string;
  name: string;
  market: string;
  board: string;
  industry: string;
  rating: string;
  final_score: number;
  industry_score: number;
  company_score: number;
  trend_score: number;
  catalyst_score: number;
  risk_penalty: number;
};

export type WatchlistTimelineItem = {
  trade_date: string;
  previous_date: string | null;
  summary: WatchlistChanges["summary"];
  new_entries: WatchlistChangeRow[];
  removed_entries: WatchlistChangeRow[];
  upgraded: WatchlistChangeRow[];
  downgraded: WatchlistChangeRow[];
  score_gainers: WatchlistChangeRow[];
  score_losers: WatchlistChangeRow[];
  watchlist_top: WatchlistTopRow[];
};

export type WatchlistTimeline = {
  market: string;
  board: string;
  latest: WatchlistTimelineItem | null;
  timeline: WatchlistTimelineItem[];
};

export type BarRow = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
};

export type StockEvidence = {
  stock: {
    code: string;
    name: string;
    market: string;
    board: string;
    exchange: string;
    industry_level1: string;
    industry_level2: string;
    concepts: string[];
    market_cap: number;
    float_market_cap: number;
    is_st: boolean;
    is_active: boolean;
  };
  score: {
    final_score: number | null;
    rating: string | null;
    industry_score: number | null;
    company_score: number | null;
    trend_score: number | null;
    catalyst_score: number | null;
    risk_penalty: number | null;
    confidence: ScoreConfidence;
    research_gate: ResearchGate;
    fundamental_summary: FundamentalSummary;
    news_evidence_status: EvidenceStatus;
    explanation: string;
  };
  trend: {
    ma20: number | null;
    ma60: number | null;
    ma120: number | null;
    ma250: number | null;
    relative_strength_rank: number | null;
    is_ma_bullish: boolean | null;
    is_breakout_120d: boolean | null;
    is_breakout_250d: boolean | null;
    explanation: string;
  };
  evidence: {
    trade_date: string;
    summary: string;
    industry_logic: string;
    company_logic: string;
    trend_logic: string;
    catalyst_logic: string;
    risk_summary: string;
    evidence_status: EvidenceStatus;
    questions_to_verify: string[];
    source_refs: { title: string; url: string; source: string }[];
  };
};

export type StockHistoryRow = {
  trade_date: string;
  final_score: number;
  rating: string;
  industry_score: number;
  company_score: number;
  trend_score: number;
  catalyst_score: number;
  risk_penalty: number;
  score_delta: number | null;
  score_explanation: string;
  relative_strength_rank: number | null;
  is_ma_bullish: boolean | null;
  is_breakout_120d: boolean | null;
  is_breakout_250d: boolean | null;
  volume_expansion_ratio: number | null;
  max_drawdown_60d: number | null;
  trend_explanation: string;
  summary: string;
  risk_summary: string;
  confidence?: ScoreConfidence;
  news_evidence_status?: EvidenceStatus;
  questions_to_verify: string[];
  source_refs: { title: string; url: string; source: string }[];
};

export type StockHistory = {
  stock: StockEvidence["stock"];
  latest: StockHistoryRow | null;
  history: StockHistoryRow[];
};

export type SourceComparison = {
  stock_code: string;
  stock: StockEvidence["stock"];
  sources: {
    source: string;
    bars_count: number;
    first_trade_date: string | null;
    latest_trade_date: string | null;
  }[];
};

export type ResearchTask = {
  id: string;
  trade_date: string;
  stock_code: string;
  stock_name: string;
  market: string;
  board: string;
  industry: string;
  industry_level2: string;
  task_type: "verify_question" | "risk_review";
  priority: "high" | "medium" | "low";
  priority_score: number;
  title: string;
  detail: string;
  rating: string;
  final_score: number;
  industry_score: number;
  company_score: number;
  trend_score: number;
  risk_penalty: number;
  relative_strength_rank: number;
  is_ma_bullish: boolean;
  is_breakout_120d: boolean;
  is_breakout_250d: boolean;
  source_refs: { title: string; url: string; source: string }[];
};

export type ResearchTasks = {
  latest_date: string | null;
  summary: {
    task_count: number;
    stock_count: number;
    high_priority_count: number;
    medium_priority_count: number;
    low_priority_count: number;
    risk_task_count: number;
    question_task_count: number;
    market_breakdown: Record<string, number>;
  };
  tasks: ResearchTask[];
};

export type HotTermFacet = {
  key: string;
  label: string;
  count: number;
};

export type ResearchHotTerm = {
  term: string;
  score: number;
  intensity: number;
  mentions: number;
  sources: HotTermFacet[];
  industries: HotTermFacet[];
  latest_at: string | null;
  examples: {
    title: string;
    source: string;
    url?: string;
    source_channel?: string;
    source_label?: string;
    source_rank?: number;
    match_reason?: string;
    match_reason_raw?: string;
    is_synthetic?: boolean;
  }[];
};

export type ResearchHotIndustry = {
  industry: string;
  score: number;
  intensity: number;
  mentions: number;
  sources: HotTermFacet[];
  top_terms: { term: string; score: number }[];
  latest_at: string | null;
};

export type ResearchHotSource = {
  key: string;
  label: string;
  kind: string;
  status: "active" | "pending_connector" | "internal_ready" | "connected_empty" | "degraded" | "error" | string;
  connector_status?: string;
  window_data_status?: string;
  article_count: number;
  last_run_status?: string | null;
  last_error?: string;
  last_run_at?: string | null;
  connector_item_count?: number;
  last_inserted?: number;
  last_skipped?: number;
  last_irrelevant?: number;
  relevance_rate?: number | null;
};

export type ResearchPlatformTerms = ResearchHotSource & {
  terms: {
    term: string;
    score: number;
    mentions: number;
    industries: HotTermFacet[];
  }[];
};

export type ResearchHotTermsSummary = {
  term_count: number;
  industry_count: number;
  article_count: number;
  matched_article_count?: number;
  unmatched_article_count?: number;
  data_lag_days?: number | null;
  is_stale?: boolean;
  source_count: number;
  data_mode: string;
};

export type ResearchHotTerms = {
  latest_date: string | null;
  updated_at: string;
  window: "1d" | "7d" | string;
  summary: ResearchHotTermsSummary;
  sources: ResearchHotSource[];
  hot_terms: ResearchHotTerm[];
  hot_industries: ResearchHotIndustry[];
  platform_terms: ResearchPlatformTerms[];
};

export type ResearchHotTermsRefresh = {
  status: string;
  inserted: number;
  skipped: number;
  failed_sources: number;
  source_count: number;
  sources: {
    key: string;
    label: string;
    status: string;
    fetched: number;
    inserted: number;
    skipped: number;
    irrelevant?: number;
    error: string;
  }[];
  snapshot: ResearchHotTerms;
};

export type ResearchFocusStock = {
  stock_code: string;
  stock_name: string;
  market: string;
  board: string;
  industry: string;
  industry_level2: string;
  rating: string;
  final_score: number;
  task_count: number;
  high_priority_count: number;
  risk_task_count: number;
  top_task_titles: string[];
  priority_score: number;
};

export type ResearchFocusIndustry = {
  industry: string;
  task_count: number;
  stock_count: number;
  high_priority_count: number;
  risk_task_count: number;
  average_priority_score: number;
  top_stocks: {
    stock_code: string;
    stock_name: string;
    final_score: number;
  }[];
};

export type ResearchBrief = {
  latest_date: string | null;
  filters: {
    market: string;
    board: string;
    watch_only: boolean;
    limit: number;
  };
  summary: ResearchTasks["summary"];
  focus_stocks: ResearchFocusStock[];
  focus_industries: ResearchFocusIndustry[];
  top_tasks: ResearchTask[];
  markdown: string;
};

export type TenbaggerThesisRow = {
  stock_code: string;
  trade_date: string;
  thesis_score: number;
  opportunity_score: number;
  growth_score: number;
  quality_score: number;
  valuation_score: number;
  timing_score: number;
  evidence_score: number;
  risk_score: number;
  readiness_score: number;
  anti_thesis_score: number;
  logic_gate_score: number;
  logic_gate_status: string;
  stage: string;
  data_gate_status: string;
  investment_thesis: string;
  base_case: string;
  bull_case: string;
  bear_case: string;
  logic_gates: TenbaggerLogicGate[];
  anti_thesis_items: TenbaggerAntiThesisItem[];
  alternative_data_signals: TenbaggerAlternativeSignal[];
  valuation_simulation: TenbaggerValuationSimulation;
  contrarian_signal: TenbaggerContrarianSignal;
  sniper_focus: string[];
  marginal_changes?: string[];
  key_milestones: string[];
  disconfirming_evidence: string[];
  missing_evidence: string[];
  source_refs: { title: string; url: string; source: string; source_kind: string }[];
  explanation: string;
  stock: {
    code: string;
    name: string;
    market: string;
    board: string;
    industry: string;
    industry_level2: string;
    market_cap: number;
    float_market_cap: number;
  };
  score: {
    final_score: number;
    raw_score: number;
    rating: string;
    industry_score: number;
    company_score: number;
    trend_score: number;
    catalyst_score: number;
    risk_penalty: number;
    confidence_level: string;
    source_confidence: number;
    data_confidence: number;
    fundamental_confidence: number;
    news_confidence: number;
    evidence_confidence: number;
  };
};

export type TenbaggerLogicGate = {
  id: string;
  title: string;
  metric: string;
  status: "pass" | "watch" | "pending" | "fail" | string;
  due_date: string;
  source: string;
  evidence: string[];
};

export type TenbaggerAntiThesisItem = {
  type: string;
  severity: "low" | "medium" | "high" | string;
  title: string;
  action: string;
};

export type TenbaggerAlternativeSignal = {
  id: string;
  label: string;
  score: number;
  direction: "positive" | "neutral" | "watch" | string;
  coverage_status: "proxy_active" | "pending_connector" | string;
  source: string;
  generated_at: string;
};

export type TenbaggerValuationSimulation = {
  valuation_ceiling_status?: "room" | "balanced" | "stretched" | "insufficient" | string;
  market_cap_unit?: string;
  current_market_cap?: number | null;
  tam_assumptions?: {
    tam_growth_3y?: number;
    penetration_stage?: string;
    market_share_assumption?: number;
    terminal_multiple?: number;
    data_confidence?: number;
    source?: string;
  };
  scenarios?: {
    scenario: "bear" | "base" | "bull" | string;
    probability: number;
    tam_growth_3y: number;
    market_share_assumption: number;
    terminal_multiple: number;
    room_multiple: number;
    model_ceiling_market_cap: number | null;
  }[];
  summary?: string;
};

export type TenbaggerContrarianSignal = {
  label?: "cold_asset_reversal_watch" | "hot_momentum" | "neutral" | string;
  importance_score?: number;
  fear_score?: number;
  reversal_watch?: boolean;
  heat_change_7d?: number;
  heat_change_30d?: number;
  max_drawdown_60d?: number;
  explanation?: string;
};

export type TenbaggerThesisList = {
  latest_date: string | null;
  summary: {
    count: number;
    average_thesis_score: number;
    average_logic_gate_score?: number;
    average_anti_thesis_score?: number;
    candidate_count: number;
    verification_count: number;
    blocked_count: number;
    contrarian_count?: number;
    stage_counts: Record<string, number>;
    gate_counts: Record<string, number>;
    logic_gate_counts?: Record<string, number>;
  };
  rows: TenbaggerThesisRow[];
};

export type ResearchDataGate = {
  latest_date: string | null;
  summary: {
    count: number;
    pass_count: number;
    warn_count: number;
    fail_count: number;
    formal_ready_ratio: number;
  };
  rows: {
    code: string;
    name: string;
    market: string;
    board: string;
    industry: string;
    final_score: number;
    rating: string;
    status: "PASS" | "WARN" | "FAIL";
    gate_score: number;
    reasons: string[];
    required_actions: string[];
  }[];
};

export type SignalBacktestRun = {
  run_key?: string;
  as_of_date: string;
  horizon_days: number;
  min_score: number;
  market: string;
  board: string;
  status: string;
  sample_count: number;
  average_forward_return: number;
  median_forward_return: number;
  average_max_return: number;
  hit_rate_2x: number;
  hit_rate_5x: number;
  hit_rate_10x: number;
  bucket_summary: {
    bucket: string;
    sample_count: number;
    average_forward_return: number;
    median_forward_return: number;
    average_max_return: number;
    hit_rate_2x: number;
    hit_rate_5x: number;
    hit_rate_10x: number;
  }[];
  rating_summary: {
    bucket: string;
    sample_count: number;
    average_forward_return: number;
    median_forward_return: number;
    average_max_return: number;
    hit_rate_2x: number;
    hit_rate_5x: number;
    hit_rate_10x: number;
  }[];
  confidence_summary: {
    bucket: string;
    sample_count: number;
    average_forward_return: number;
    median_forward_return: number;
    average_max_return: number;
    hit_rate_2x: number;
    hit_rate_5x: number;
    hit_rate_10x: number;
  }[];
  failures: string[];
  explanation: string;
  created_at?: string;
};

export type SignalBacktestLatest = {
  latest: SignalBacktestRun | null;
  runs: SignalBacktestRun[];
};

export type SignalBacktestRunResponse = {
  result: {
    backtest_runs: number;
    run_key: string;
    sample_count: number;
  };
  run: SignalBacktestRun | null;
};

// ---------------------------------------------------------------------------
// Research Thesis (general, not tenbagger-specific)
// ---------------------------------------------------------------------------
export type ResearchThesis = {
  id: number;
  source_type: string;
  subject_type: string;
  subject_id: string;
  subject_name: string;
  thesis_title: string;
  thesis_body: string;
  direction: "positive" | "negative" | "neutral" | "mixed";
  horizon_days: number;
  confidence: number;
  evidence_refs_json: string;
  key_metrics_json: string;
  invalidation_conditions_json: string;
  risk_flags_json: string;
  status: string;
  created_at: string;
  review_date?: string | null;
  review_result?: string | null;
};

// ---------------------------------------------------------------------------
// Watchlist Item (thesis-centric)
// ---------------------------------------------------------------------------
export type WatchlistItemEnhanced = {
  id: number;
  subject_type: string;
  subject_id: string;
  subject_name: string;
  thesis_title: string;
  direction: string;
  reason: string;
  watch_metrics_json: string;
  invalidation_conditions_json: string;
  priority: "S" | "A" | "B";
  status: string;
  source_thesis_id?: number | null;
  thesis?: ResearchThesis | null;
  review_status?: string | null;
  review_date?: string | null;
  review_result?: string | null;
  created_at: string;
  updated_at: string;
};

// ---------------------------------------------------------------------------
// Thesis Analytics & Review
// ---------------------------------------------------------------------------
export interface ThesisAnalytics {
  snapshot_date: string;
  sample_size: number;
  hit_count: number;
  missed_count: number;
  invalidated_count: number;
  inconclusive_count: number;
  hit_rate: number | null;
  miss_rate: number | null;
  inconclusive_rate: number | null;
  by_subject_type_json: string;
  by_direction_json: string;
  by_horizon_json: string;
  by_confidence_bucket_json: string;
  by_source_type_json: string;
  calibration_report_json: string;
  low_sample_warnings_json: string;
}

export interface AnnotationSummary {
  total: number;
  useful_rate: number | null;
  evidence_weak_rate: number | null;
  too_vague_rate: number | null;
  by_label: Record<string, number>;
}

export interface ReportQualityPoint {
  score_date: string;
  quality_score: number;
  thesis_count: number;
  evidence_count: number;
  avg_confidence: number;
  hit_rate_5d: number | null;
  hit_rate_20d: number | null;
  review_backed: boolean;
}

export type AgentTaskType =
  | "stock_deep_research"
  | "industry_chain_radar"
  | "trend_pool_scan"
  | "tenbagger_candidate"
  | "daily_market_brief"
  | "auto";

export type AgentRunRequest = {
  user_prompt: string;
  task_type?: AgentTaskType;
  symbols?: string[];
  industry_keywords?: string[];
  risk_preference?: string | null;
  time_window?: string | null;
  save_as_skill?: boolean;
};

export type AgentRunResponse = {
  run_id: number;
  status: string;
  selected_task_type: AgentTaskType;
  report_title: string;
  summary: string;
  artifact_id: number | null;
  warnings: string[];
};

export type AgentRunDetail = {
  id: number;
  user_id: string | null;
  task_type: AgentTaskType;
  user_prompt: string;
  runtime_provider: string;
  status: string;
  selected_symbols: string[];
  selected_industries: string[];
  created_at: string;
  completed_at: string | null;
  error_message: string;
  latest_artifact: AgentArtifact | null;
};

export type AgentStep = {
  id: number;
  run_id: number;
  step_name: string;
  agent_role: string;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_message: string;
  created_at: string;
};

export type AgentArtifact = {
  id: number;
  run_id: number;
  artifact_type: string;
  title: string;
  content_md: string;
  content_json: Record<string, unknown>;
  evidence_refs: Record<string, unknown>[];
  claims: AgentArtifactClaim[];
  claim_refs: AgentArtifactClaimRef[];
  risk_disclaimer: string;
  created_at: string;
};

export type AgentArtifactClaim = {
  id: string;
  section: string;
  text: string;
  evidence_ref_ids: string[];
  source_tools: string[];
  confidence: string;
  uncertainty: string;
  user_prompt: string;
};

export type AgentArtifactClaimRef = {
  claim_id: string;
  evidence_ref_ids: string[];
  evidence_refs: Record<string, unknown>[];
  source_tools: string[];
  missing_evidence_ref_ids: string[];
  has_evidence: boolean;
};

export type AgentSkill = {
  id: number | string;
  name: string;
  description: string;
  skill_type: AgentTaskType | string;
  skill_md: string;
  skill_config: Record<string, unknown>;
  owner_user_id: string | null;
  is_system: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type AgentSSEEvent = {
  event: string;
  run_id: number;
  seq?: number;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type AgentFollowupRequest = {
  message: string;
  mode?: "explain" | "expand_risk" | "evidence_drilldown" | "compare" | "generate_checklist" | "auto";
  save_as_artifact?: boolean;
};

export type AgentFollowupResponse = {
  run_id: number;
  followup_id: number;
  message: string;
  mode: string;
  answer_md: string;
  evidence_refs: Record<string, unknown>[];
  warnings: string[];
  saved_artifact_id: number | null;
  created_at: string;
};

export type AgentMessage = {
  id?: number;
  role: string;
  content: string;
  followup_id?: number | null;
  mode?: string;
  created_at: string;
};

export type RuntimeHealth = {
  runtime_provider: string;
  llm_configured: boolean;
  hermes_configured: boolean;
  streaming_supported: boolean;
  followup_llm_enabled: boolean;
  fallback_enabled: boolean;
  warnings: string[];
};

export type AgentRunListItem = {
  id: number;
  task_type: string;
  status: string;
  report_title: string;
  created_at: string;
  completed_at: string | null;
  user_id: string | null;
};

// ---------------------------------------------------------------------------
// Risk Budget types
// ---------------------------------------------------------------------------

export interface PositionSizeRequest {
  account_equity: number
  available_cash?: number
  symbol: string
  entry_price: number
  invalidation_price?: number
  risk_per_trade_pct: number
  max_single_position_pct?: number
  max_theme_exposure_pct?: number
  current_drawdown_pct?: number
  market?: string
  lot_size?: number
}

export interface PositionSizeResponse {
  symbol: string
  entry_price: number
  invalidation_price: number | null
  risk_per_share: number | null
  max_loss_amount: number | null
  raw_quantity: number | null
  rounded_quantity: number | null
  estimated_position_value: number | null
  estimated_position_pct: number | null
  effective_risk_pct: number
  cash_required: number | null
  cash_after: number | null
  warnings: string[]
  constraints_applied: string[]
  calculation_explain: string
  disclaimer: string
  error: string | null
}

export interface RiskPortfolio {
  id: number
  name: string
  total_equity: number
  available_cash: number
  created_at: string
  updated_at: string
}

export interface ExposureItem {
  symbol?: string
  name?: string
  industry?: string
  theme?: string
  exposure_pct: number
  limit_pct: number
  over_limit: boolean
}

export interface ExposureData {
  portfolio_id: number
  single_stock_exposure: ExposureItem[]
  industry_exposure: ExposureItem[]
  theme_exposure: ExposureItem[]
  current_risk_rules: string[]
}

export interface PositionPlan {
  id: number
  symbol: string
  entry_price: number
  invalidation_price: number | null
  calculated_position_pct: number | null
  estimated_position_value: number | null
  status: string
  warnings: string[]
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// User identity (X-Alpha-User-Id header)
// ---------------------------------------------------------------------------

function getUserId(): string {
  if (typeof window === "undefined") return "anonymous";
  try {
    let id = localStorage.getItem("alpha_user_id");
    if (!id) {
      id = "user_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("alpha_user_id", id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

async function getJson<T>(path: string, options?: { cacheMs?: number }): Promise<T> {
  const cacheMs = options?.cacheMs ?? DEFAULT_GET_CACHE_MS;
  const cacheKey = `${API_BASE_URL}${path}`;
  const now = Date.now();
  if (cacheMs > 0) {
    const cached = getCache.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      if ("value" in cached) return cached.value as T;
      if (cached.promise) return cached.promise as Promise<T>;
    }
  }

  const request = fetch(cacheKey, {
    cache: "no-store",
    headers: { "X-Alpha-User-Id": getUserId() },
  }).then((response) => {
    if (!response.ok) {
      throw new Error(`${path} failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
  });

  if (cacheMs > 0) {
    getCache.set(cacheKey, { expiresAt: now + cacheMs, promise: request });
    request
      .then((value) => getCache.set(cacheKey, { expiresAt: Date.now() + cacheMs, value }))
      .catch(() => getCache.delete(cacheKey));
  }

  return request;
}

async function safeGetJson<T>(path: string): Promise<T | null> {
  try {
    return await getJson<T>(path, { cacheMs: 0 });
  } catch (err) {
    if (err instanceof Error && /404|not found/i.test(err.message)) {
      return null;
    }
    throw err;
  }
}

async function safeGetJsonArray<T>(path: string): Promise<T[]> {
  try {
    return await getJson<T[]>(path, { cacheMs: 0 });
  } catch (err) {
    if (err instanceof Error && /404|not found/i.test(err.message)) {
      return [];
    }
    throw err;
  }
}

export const api = {
  marketSummary: () => getJson<MarketSummary>("/api/market/summary"),
  marketSegments: () => getJson<MarketSegment[]>("/api/market/segments"),
  dataStatus: (options?: { includeSourceCoverage?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.includeSourceCoverage) params.set("include_source_coverage", "true");
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<DataStatus>(`/api/market/data-status${suffix}`);
  },
  dataQuality: () => getJson<DataQuality>("/api/market/data-quality"),
  dataQualityBackfillPlan: () => getJson<QualityBackfillPlan>("/api/market/data-quality/backfill-plan"),
  ingestionPlan: () => getJson<IngestionPlan>("/api/market/ingestion-plan"),
  backfillManifest: () => getJson<BackfillManifest>("/api/market/backfill-manifest"),
  instruments: (filters?: { market?: string; board?: string; assetType?: string; q?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.assetType && filters.assetType !== "all") params.set("asset_type", filters.assetType);
    if (filters?.q) params.set("q", filters.q);
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.offset) params.set("offset", String(filters.offset));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<InstrumentsResponse>(`/api/market/instruments${suffix}`);
  },
  instrumentNavigation: (code: string) => getJson<InstrumentNavigation>(`/api/market/instruments/${encodeURIComponent(code)}/navigation`),
  ingestionBatches: () => getJson<IngestionBatch[]>("/api/market/ingestion-batches"),
  ingestionTasks: () => getJson<IngestionTask[]>("/api/market/ingestion-tasks"),
  ingestionPriority: (filters?: { market?: string; board?: string; limit?: number; periods?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.periods) params.set("periods", String(filters.periods));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<IngestionPriority>(`/api/market/ingestion-priority${suffix}`);
  },
  createIngestionTask: (payload: { task_type: "batch" | "single"; market: string; board?: string; stock_code?: string; source?: string; batch_limit?: number; periods?: number }) =>
    postJson<IngestionTask>("/api/market/ingestion-tasks", payload),
  createIngestionBackfill: (payload: { markets: string[]; board?: string; source?: string; batches_per_market?: number; batch_limit?: number; periods?: number }) =>
    postJson<IngestionBackfillResult>("/api/market/ingestion-tasks/backfill", payload),
  runIngestionTask: (taskId: number) => postJson<IngestionTask>(`/api/market/ingestion-tasks/${taskId}/run`, {}),
  runNextIngestionTask: () => postJson<IngestionTask>("/api/market/ingestion-tasks/run-next", {}),
  runIngestionQueue: (maxTasks = 3) => postJson<IngestionQueueRunResult>(`/api/market/ingestion-tasks/run-queue?max_tasks=${maxTasks}`, {}),
  industryRadar: (filters?: { market?: string }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<IndustryRadarRow[]>(`/api/industries/radar${suffix}`);
  },
  industryTimeline: (limit = 30) => getJson<IndustryTimeline>(`/api/industries/timeline?limit=${limit}`),
  industryDetail: (industryId: number | string, filters?: { market?: string }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<IndustryDetail>(`/api/industries/${industryId}${suffix}`);
  },
  chainOverview: (filters?: { market?: string }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ChainOverview>(`/api/chain/overview${suffix}`);
  },
  chainNode: (nodeKey: string, filters?: { market?: string }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ChainNodeDetail>(`/api/chain/nodes/${encodeURIComponent(nodeKey)}${suffix}`);
  },
  chainGeo: (filters: { nodeKey: string; market?: string }) => {
    const params = new URLSearchParams();
    params.set("node_key", filters.nodeKey);
    if (filters.market && filters.market !== "ALL") params.set("market", filters.market);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ChainGeo>(`/api/chain/geo${suffix}`);
  },
  chainTimeline: (filters: { nodeKey: string; limit?: number }) => {
    const params = new URLSearchParams();
    params.set("node_key", filters.nodeKey);
    if (filters.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ChainTimeline>(`/api/chain/timeline${suffix}`);
  },
  researchTasks: (filters?: { market?: string; board?: string; priority?: string; taskType?: string; watchOnly?: boolean; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.priority && filters.priority !== "all") params.set("priority", filters.priority);
    if (filters?.taskType && filters.taskType !== "all") params.set("task_type", filters.taskType);
    if (typeof filters?.watchOnly === "boolean") params.set("watch_only", String(filters.watchOnly));
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ResearchTasks>(`/api/research/tasks${suffix}`);
  },
  researchBrief: (filters?: { market?: string; board?: string; watchOnly?: boolean; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (typeof filters?.watchOnly === "boolean") params.set("watch_only", String(filters.watchOnly));
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ResearchBrief>(`/api/research/brief${suffix}`);
  },
  researchHotTerms: (filters?: { window?: "1d" | "7d"; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.window) params.set("window", filters.window);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ResearchHotTerms>(`/api/research/hot-terms${suffix}`);
  },
  refreshHotTerms: (options?: { sources?: string[]; limitPerSource?: number; timeoutSeconds?: number; window?: "1d" | "7d" }) => {
    const params = new URLSearchParams();
    if (options?.sources?.length) params.set("sources", options.sources.join(","));
    if (options?.limitPerSource) params.set("limit_per_source", String(options.limitPerSource));
    if (options?.timeoutSeconds) params.set("timeout_seconds", String(options.timeoutSeconds));
    if (options?.window) params.set("window", options.window);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return postJson<ResearchHotTermsRefresh>(`/api/research/hot-terms/refresh${suffix}`, {});
  },
  hotTerms: (filters?: { window?: "1d" | "7d"; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.window) params.set("window", filters.window);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ResearchHotTerms>(`/api/research/hot-terms${suffix}`);
  },
  tenbaggerTheses: (filters?: { market?: string; board?: string; stage?: string; dataGateStatus?: string; logicGateStatus?: string; contrarianOnly?: boolean; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.stage && filters.stage !== "all") params.set("stage", filters.stage);
    if (filters?.dataGateStatus && filters.dataGateStatus !== "ALL") params.set("data_gate_status", filters.dataGateStatus);
    if (filters?.logicGateStatus && filters.logicGateStatus !== "ALL") params.set("logic_gate_status", filters.logicGateStatus);
    if (filters?.contrarianOnly) params.set("contrarian_only", "true");
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.offset) params.set("offset", String(filters.offset));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<TenbaggerThesisList>(`/api/research/thesis${suffix}`);
  },
  tenbaggerThesis: (code: string) => getJson<{ latest: TenbaggerThesisRow; history: TenbaggerThesisRow[] }>(`/api/research/thesis/${encodeURIComponent(code)}`),
  researchDataGate: (filters?: { market?: string; board?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<ResearchDataGate>(`/api/research/data-gate${suffix}`);
  },
  latestBacktest: () => getJson<SignalBacktestLatest>("/api/research/backtest/latest"),
  runBacktest: (payload: { as_of_date?: string | null; horizon_days?: number; min_score?: number; market?: string; board?: string }) =>
    postJson<SignalBacktestRunResponse>("/api/research/backtest/run", payload),
  researchUniverse: () => getJson<ResearchUniverse>("/api/market/research-universe"),
  trendPool: (filters?: { market?: string; board?: string; researchUniverseOnly?: boolean; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.researchUniverseOnly === false) params.set("research_universe_only", "false");
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.offset) params.set("offset", String(filters.offset));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<TrendPoolRow[]>(`/api/stocks/trend-pool${suffix}`);
  },
  latestReport: () => getJson<DailyReport>("/api/reports/latest"),
  reports: () => getJson<ReportSummary[]>("/api/reports"),
  reportByDate: (date: string) => getJson<DailyReport>(`/api/reports/${date}`),
  watchlistChanges: () => getJson<WatchlistChanges>("/api/watchlist/changes"),
  watchlistTimeline: (filters?: { market?: string; board?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (filters?.market && filters.market !== "ALL") params.set("market", filters.market);
    if (filters?.board && filters.board !== "all") params.set("board", filters.board);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return getJson<WatchlistTimeline>(`/api/watchlist/timeline${suffix}`);
  },
  stockEvidence: (code: string) => getJson<StockEvidence>(`/api/stocks/${code}/evidence`),
  stockHistory: (code: string) => getJson<StockHistory>(`/api/stocks/${code}/history`),
  stockBars: (code: string) => getJson<BarRow[]>(`/api/stocks/${code}/bars`),
  sourceComparison: (code: string) => getJson<SourceComparison>(`/api/stocks/${code}/source-comparison`),
  ingestStock: (code: string, source = "akshare") => postJson<IngestionTask>(`/api/stocks/${code}/ingest?source=${encodeURIComponent(source)}`, {}),
  agentRun: (payload: AgentRunRequest) => postJson<AgentRunResponse>("/api/agent/runs", payload),
  agentRunDetail: (runId: number) => getJson<AgentRunDetail>(`/api/agent/runs/${runId}`, { cacheMs: 0 }),
  agentRunSteps: (runId: number) => getJson<AgentStep[]>(`/api/agent/runs/${runId}/steps`, { cacheMs: 0 }),
  agentRunArtifacts: (runId: number) => getJson<AgentArtifact[]>(`/api/agent/runs/${runId}/artifacts`, { cacheMs: 0 }),
  agentSkills: () => getJson<AgentSkill[]>("/api/agent/skills", { cacheMs: 0 }),
  agentSkill: (skillId: number | string) => getJson<AgentSkill>(`/api/agent/skills/${encodeURIComponent(String(skillId))}`, { cacheMs: 0 }),
  createAgentSkill: (payload: {
    name: string;
    description?: string;
    skill_type?: AgentTaskType | string;
    skill_md?: string;
    skill_config?: Record<string, unknown>;
    owner_user_id?: string | null;
    is_system?: boolean;
  }) => postJson<AgentSkill>("/api/agent/skills", payload),
  agentRunEvents: (runId: number, sinceSeq?: number) => {
    const params = sinceSeq != null ? `?since_seq=${sinceSeq}` : '';
    return new EventSource(`${API_BASE_URL}/api/agent/runs/${runId}/events${params}`);
  },
  agentRunFollowup: (runId: number, payload: AgentFollowupRequest) =>
    postJson<AgentFollowupResponse>(`/api/agent/runs/${runId}/followups`, payload),
  agentRunMessages: (runId: number) =>
    getJson<AgentMessage[]>(`/api/agent/runs/${runId}/messages`, { cacheMs: 0 }),
  // Runtime health
  agentRuntimeHealth: () => getJson<RuntimeHealth>("/api/agent/runtime/health"),
  // Run history
  agentRunList: (params?: { limit?: number; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return getJson<AgentRunListItem[]>(`/api/agent/runs${suffix}`, { cacheMs: 0 });
  },
  // Export URLs (not JSON endpoints -- direct download / open in tab)
  agentRunExportMarkdownUrl: (runId: number) => `${API_BASE_URL}/api/agent/runs/${runId}/export/markdown`,
  agentRunExportHtmlUrl: (runId: number) => `${API_BASE_URL}/api/agent/runs/${runId}/export/html`,
  agentRunExportPrintUrl: (runId: number) => `${API_BASE_URL}/api/agent/runs/${runId}/export/print`,
  agentRunExportRichHtmlUrl: (runId: number) => `${API_BASE_URL}/api/agent/runs/${runId}/export/print`,

  // ---------------------------------------------------------------------------
  // Research Theses API
  // ---------------------------------------------------------------------------
  fetchTheses: (params?: { source_type?: string; status?: string; subject_type?: string; subject_id?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.source_type) query.set("source_type", params.source_type);
    if (params?.status) query.set("status", params.status);
    if (params?.subject_type) query.set("subject_type", params.subject_type);
    if (params?.subject_id) query.set("subject_id", params.subject_id);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return getJson<{ total: number; rows: ResearchThesis[] }>(`/api/research/theses${suffix}`, { cacheMs: 0 }).then((data) => data.rows ?? []);
  },
  fetchThesis: (id: number) => getJson<ResearchThesis>(`/api/research/theses/${id}`, { cacheMs: 0 }),

  // ---------------------------------------------------------------------------
  // Watchlist Items API (thesis-centric)
  // ---------------------------------------------------------------------------
  fetchWatchlistItems: (params?: { status?: string; priority?: string; subject_type?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.priority) query.set("priority", params.priority);
    if (params?.subject_type) query.set("subject_type", params.subject_type);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return getJson<{ total: number; rows: WatchlistItemEnhanced[] }>(`/api/watchlist/items${suffix}`, { cacheMs: 0 }).then((data) => data.rows ?? []);
  },
  addToWatchlist: (payload: { thesis_id?: number; subject_type?: string; subject_id?: string; subject_name?: string; thesis_title?: string; direction?: string; reason?: string; priority?: string }) =>
    postJson<WatchlistItemEnhanced>("/api/watchlist/items", payload),
  archiveWatchlistItem: (itemId: number) => postJson<WatchlistItemEnhanced>(`/api/watchlist/items/${itemId}/archive`, {}),
  updateWatchlistItem: (itemId: number, payload: { reason?: string; priority?: string }) =>
    postJson<WatchlistItemEnhanced>(`/api/watchlist/items/${itemId}`, payload),

  // ---------------------------------------------------------------------------
  // Thesis Analytics & Review
  // ---------------------------------------------------------------------------
  fetchThesisAnalytics: () => safeGetJson<ThesisAnalytics>("/api/research/thesis-analytics"),
  fetchAnnotationSummary: () => safeGetJson<AnnotationSummary>("/api/research/annotations/summary"),
  fetchReportQualityTimeseries: (params?: { source_type?: string; start_date?: string; end_date?: string }) => {
    const query = new URLSearchParams();
    if (params?.source_type) query.set("source_type", params.source_type);
    if (params?.start_date) query.set("start_date", params.start_date);
    if (params?.end_date) query.set("end_date", params.end_date);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return safeGetJson<{ total: number; rows: ReportQualityPoint[] }>(`/api/research/report-quality${suffix}`).then((data) => data?.rows ?? []);
  },

  // ---------------------------------------------------------------------------
  // Risk Budget API
  // ---------------------------------------------------------------------------
  calculatePositionSize: (req: PositionSizeRequest) => postJson<PositionSizeResponse>("/api/risk/calculate-position-size", req),
  fetchPortfolios: () => safeGetJsonArray<RiskPortfolio>("/api/risk/portfolios"),
  createPortfolio: (data: { name: string; total_equity: number; available_cash?: number }) =>
    postJson<RiskPortfolio>("/api/risk/portfolios", data),
  fetchExposure: (portfolioId: number) => safeGetJson<ExposureData>(`/api/risk/portfolios/${portfolioId}/exposure`),
  fetchPositionPlans: (params?: { status?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return safeGetJsonArray<PositionPlan>(`/api/risk/position-plans${suffix}`);
  },
  createPositionPlan: (data: {
    symbol: string;
    entry_price: number;
    invalidation_price?: number | null;
    calculated_position_pct?: number | null;
    estimated_position_value?: number | null;
    warnings?: string[];
  }) => postJson<PositionPlan>("/api/risk/position-plans", data),
  activatePlan: (planId: number) => postJson<PositionPlan>(`/api/risk/position-plans/${planId}/activate`, {}),
  archivePlan: (planId: number) => postJson<PositionPlan>(`/api/risk/position-plans/${planId}/archive`, {}),
};


async function postJson<T>(path: string, payload: unknown): Promise<T> {
  getCache.clear();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Alpha-User-Id": getUserId() },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    throw new Error(`${path} failed: ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  return response.json() as Promise<T>;
}
