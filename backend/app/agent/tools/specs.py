from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ToolSpec -- a lightweight, serialisable specification for an MCP-ready tool
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """Specification for an MCP-ready tool.

    Fields
    ------
    name : str
        Unique tool identifier (snake_case).
    category : str
        One of "market", "industry", "scoring", "evidence", "report".
    description : str
        Chinese description of the tool's purpose.
    input_schema : dict
        JSON-Schema-like description of parameters (session is excluded).
    output_schema : dict
        JSON-Schema-like description of the return structure.
    read_only : bool
        Always True for Alpha Radar data tools.
    risk_level : str
        "low" or "medium".
    timeout_ms : int
        Recommended timeout in milliseconds.
    examples : list[dict]
        Example invocations showing typical usage.
    unavailable_behavior : str
        What happens when the requested data is not available.
    """

    name: str
    category: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    read_only: bool = True
    risk_level: str = "low"
    timeout_ms: int = 15000
    examples: list[dict[str, Any]] = field(default_factory=list)
    unavailable_behavior: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_mcp_dict(self) -> dict[str, Any]:
        """Convert this spec into a standard MCP tool manifest entry."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Helper: standard output shapes shared across tools
# ---------------------------------------------------------------------------

_OK_OUTPUT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ok", "unavailable"],
            "description": "Request outcome: ok or unavailable",
        },
    },
    "required": ["status"],
}

_OK_LIST_OUTPUT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "unavailable"]},
    },
}

_UNAVAILABLE_MSG: str = (
    "Returns status='unavailable' with a human-readable message field when the "
    "requested data cannot be found or has not been computed yet."
)

# ===================================================================
# Pydantic models for input / output schemas (used with model_json_schema)
# ===================================================================
# Each tool defines an Input and Output model.  Complex nested data uses
# dict[str, Any] / list[dict[str, Any]] rather than deep nesting.

# ------------------------------------------------------------------
# MARKET INPUTS (4)
# ------------------------------------------------------------------


class GetStockBasicInput(BaseModel):
    symbol_or_name: str = Field(
        description="股票代码（如 000001）或股票名称（如 平安银行）"
    )


class GetPriceTrendInput(BaseModel):
    symbol: str = Field(description="股票代码或名称")
    window: str | None = Field(
        default=None,
        description="区间窗口，如 60d、120d、250d，默认 120d",
    )


class GetMomentumRankInput(BaseModel):
    scope: str | None = Field(
        default=None,
        description="市场范围：A / US / HK / 留空表示全部",
    )
    window: str | None = Field(
        default=None,
        description="动量区间窗口字符串（传递给趋势信号的上下文）",
    )
    limit: int | None = Field(
        default=None,
        description="返回条数，最大 100，默认 20",
    )


class GetMarketCoverageStatusInput(BaseModel):
    pass


# ------------------------------------------------------------------
# MARKET OUTPUTS (4)
# ------------------------------------------------------------------


class GetStockBasicOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = Field(default=None, description="股票代码")
    name: str | None = Field(default=None, description="股票名称")
    market: str | None = Field(default=None, description="市场（A/US/HK）")
    board: str | None = Field(default=None, description="板块")
    exchange: str | None = Field(default=None, description="交易所")
    industry_level1: str | None = Field(default=None, description="一级行业")
    industry_level2: str | None = Field(default=None, description="二级行业")
    concepts: list[str] | None = Field(default=None, description="概念标签列表")
    market_cap: float | None = Field(default=None, description="总市值")
    float_market_cap: float | None = Field(default=None, description="流通市值")
    is_st: bool | None = Field(default=None, description="是否ST")
    is_active: bool | None = Field(default=None, description="是否活跃")
    data_source: str | None = None


class GetPriceTrendOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = None
    name: str | None = None
    trade_date: str | None = Field(default=None, description="最新交易日")
    close: float | None = Field(default=None, description="最新收盘价")
    window: str | None = Field(default=None, description="实际使用的区间")
    window_return_pct: float | None = Field(
        default=None, description="区间收益率百分比"
    )
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    ma250: float | None = None
    trend_score: float | None = None
    relative_strength_rank: float | None = None
    is_ma_bullish: bool | None = None
    is_breakout_120d: bool | None = None
    is_breakout_250d: bool | None = None
    volume_expansion_ratio: float | None = None
    max_drawdown_60d: float | None = None
    explanation: str | None = None
    data_source: str | None = None


class GetMomentumRankOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    window: str | None = None
    scope: str | None = None
    stocks: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetMarketCoverageStatusOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    stock_count: int | None = None
    stocks_with_bars: int | None = None
    bar_coverage_ratio: float | None = None
    latest_trade_date: str | None = None
    latest_trend_date: str | None = None
    data_source: str | None = None


# ------------------------------------------------------------------
# INDUSTRY INPUTS (4)
# ------------------------------------------------------------------


class GetIndustryMappingInput(BaseModel):
    symbol_or_keyword: str = Field(
        description="股票代码、股票名称或行业关键词",
    )


class GetIndustryChainInput(BaseModel):
    keyword: str | None = Field(
        default=None,
        description="产业链关键词，留空返回全部节点",
    )


class GetRelatedStocksByIndustryInput(BaseModel):
    industry: str = Field(description="行业名称或关键词")
    limit: int | None = Field(
        default=None,
        description="返回条数，最大 100，默认 20",
    )


class GetIndustryHeatmapInput(BaseModel):
    keyword_or_scope: str | None = Field(
        default=None,
        description="行业关键词或市场范围（A/US/HK/ALL），留空默认 ALL",
    )
    limit: int | None = Field(
        default=None,
        description="返回条数，最大 100，默认 20",
    )


# ------------------------------------------------------------------
# INDUSTRY OUTPUTS (4)
# ------------------------------------------------------------------


class GetIndustryMappingOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = None
    name: str | None = None
    industry: str | None = None
    industry_id: int | None = None
    industry_level2: str | None = None
    concepts: list[str] | None = None
    keywords: list[str] | None = None
    reason: str | None = None
    data_source: str | None = None


class GetIndustryChainOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    keyword: str | None = None
    nodes: list[dict[str, Any]] | None = None
    description: str | None = None
    data_source: str | None = None


class GetRelatedStocksByIndustryOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    industry: str | None = None
    stocks: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetIndustryHeatmapOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    keyword: str | None = None
    rows: list[dict[str, Any]] | None = None
    data_source: str | None = None


# ------------------------------------------------------------------
# SCORING INPUTS (4)
# ------------------------------------------------------------------


class GetStockScoreInput(BaseModel):
    symbol: str = Field(description="股票代码或名称")


class GetScoreBreakdownInput(BaseModel):
    symbol: str = Field(description="股票代码或名称")


class GetTopScoredStocksInput(BaseModel):
    scope: str | None = Field(
        default=None,
        description="市场范围：A / US / HK / 留空表示全部",
    )
    limit: int | None = Field(
        default=None,
        description="返回条数，最大 100，默认 20",
    )


class GetRiskFlagsInput(BaseModel):
    symbol: str = Field(description="股票代码或名称")


# ------------------------------------------------------------------
# SCORING OUTPUTS (4)
# ------------------------------------------------------------------


class GetStockScoreOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = None
    name: str | None = None
    market: str | None = None
    industry: str | None = None
    trade_date: str | None = None
    final_score: float | None = None
    raw_score: float | None = None
    rating: str | None = None
    industry_score: float | None = None
    company_score: float | None = None
    trend_score: float | None = None
    catalyst_score: float | None = None
    risk_penalty: float | None = None
    confidence_level: str | None = None
    confidence_reasons: list[str] | None = None
    explanation: str | None = None
    data_source: str | None = None


class GetScoreBreakdownOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    breakdown: dict[str, Any] | None = Field(
        default=None,
        description="各维度得分拆解（industry_score/company_score/trend_score/catalyst_score/risk_penalty）",
    )
    scoring_basis: str | None = Field(
        default=None,
        description="评分公式说明",
    )


class GetTopScoredStocksOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    scope: str | None = None
    trade_date: str | None = None
    stocks: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetRiskFlagsOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = None
    name: str | None = None
    penalty: float | None = Field(default=None, description="风险扣分")
    flags: list[str] | None = Field(default=None, description="风险标签列表")
    explanation: str | None = None
    data_source: str | None = None


# ------------------------------------------------------------------
# EVIDENCE INPUTS (4)
# ------------------------------------------------------------------


class GetStockEvidenceInput(BaseModel):
    symbol: str = Field(description="股票代码或名称")


class GetIndustryEvidenceInput(BaseModel):
    keyword: str = Field(description="行业关键词")
    limit: int | None = Field(
        default=None,
        description="返回文章条数，最大 50，默认 12",
    )


class GetRecentCatalystsInput(BaseModel):
    symbol_or_industry: str = Field(
        description="股票代码/名称或行业关键词",
    )
    limit: int | None = Field(
        default=None,
        description="返回条数，最大 50，默认 10",
    )


class GetEvidenceSummaryInput(BaseModel):
    symbol_or_keyword: str = Field(
        description="股票代码/名称 或 行业关键词",
    )


# ------------------------------------------------------------------
# EVIDENCE OUTPUTS (4)
# ------------------------------------------------------------------


class GetStockEvidenceOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    code: str | None = None
    name: str | None = None
    trade_date: str | None = None
    summary: str | None = None
    industry_logic: str | None = None
    company_logic: str | None = None
    trend_logic: str | None = None
    catalyst_logic: str | None = None
    risk_summary: str | None = None
    questions_to_verify: list[str] | None = None
    source_refs: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetIndustryEvidenceOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    keyword: str | None = None
    summary: str | None = None
    articles: list[dict[str, Any]] | None = None
    source_refs: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetRecentCatalystsOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    catalysts: list[dict[str, Any]] | None = None
    data_source: str | None = None


class GetEvidenceSummaryOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    # Inherits fields from get_stock_evidence or get_industry_evidence
    # based on actual dispatch at runtime.


# ------------------------------------------------------------------
# REPORT INPUTS (3)
# ------------------------------------------------------------------


class GetLatestDailyReportInput(BaseModel):
    pass


class GenerateReportOutlineInput(BaseModel):
    task_type: str = Field(
        description=(
            "任务类型标识符，如 stock_deep_research、industry_overview、"
            "daily_watch 等"
        ),
    )


class FormatResearchReportInput(BaseModel):
    context: dict[str, Any] = Field(
        description="研究报告上下文字典",
    )


# ------------------------------------------------------------------
# REPORT OUTPUTS (3)
# ------------------------------------------------------------------


class GetLatestDailyReportOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    report_date: str | None = None
    title: str | None = None
    market_summary: str | None = None
    top_industries: list[dict[str, Any]] | None = None
    top_trend_stocks: list[dict[str, Any]] | None = None
    new_watchlist_stocks: list[dict[str, Any]] | None = None
    risk_alerts: list[dict[str, Any]] | None = None
    full_markdown: str | None = None
    data_source: str | None = None


class GenerateReportOutlineOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    task_type: str | None = None
    headings: list[str] | None = Field(
        default=None,
        description="Markdown 标题行列表",
    )
    data_source: str | None = None


class FormatResearchReportOutput(BaseModel):
    status: str = Field(description="ok 或 unavailable")
    message: str | None = None
    context_keys: list[str] | None = Field(
        default=None,
        description="排序后的上下文键列表",
    )
    data_source: str | None = None


# ===================================================================
# MARKET TOOLS  (4 tools)
# ===================================================================

MARKET_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_stock_basic",
        category="market",
        description="查询股票基础信息，包括代码、名称、市场、板块、行业、概念标签、市值、ST状态等。",
        input_schema=GetStockBasicInput.model_json_schema(),
        output_schema=GetStockBasicOutput.model_json_schema(),
        examples=[
            {
                "symbol_or_name": "000001",
                "description": "按股票代码查询平安银行",
            },
            {
                "symbol_or_name": "贵州茅台",
                "description": "按股票名称查询",
            },
        ],
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_price_trend",
        category="market",
        description="查询股票价格趋势数据，包括最新收盘价、区间收益率、均线、趋势评分、相对强度排名、突破信号、最大回撤等。",
        input_schema=GetPriceTrendInput.model_json_schema(),
        output_schema=GetPriceTrendOutput.model_json_schema(),
        examples=[
            {"symbol": "000001", "window": "60d"},
            {"symbol": "贵州茅台"},
        ],
        timeout_ms=15000,
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_momentum_rank",
        category="market",
        description="查询全市场动量排名，按趋势评分降序排列，可指定市场范围和区间窗口。",
        input_schema=GetMomentumRankInput.model_json_schema(),
        output_schema=GetMomentumRankOutput.model_json_schema(),
        examples=[
            {"scope": "A", "limit": 10},
            {"scope": "US", "window": "60d", "limit": 20},
        ],
        timeout_ms=30000,
        unavailable_behavior="Returns status='unavailable' with empty stocks list when trend signal data is insufficient.",
    ),
    ToolSpec(
        name="get_market_coverage_status",
        category="market",
        description="查询行情数据覆盖状态，包括股票总数、有行情数据的股票数、覆盖率、最新交易日等。",
        input_schema=GetMarketCoverageStatusInput.model_json_schema(),
        output_schema=GetMarketCoverageStatusOutput.model_json_schema(),
        examples=[{}],
        timeout_ms=10000,
        unavailable_behavior="Always returns status='ok' with current statistics; never returns unavailable.",
    ),
]


# ===================================================================
# INDUSTRY TOOLS  (4 tools)
# ===================================================================

INDUSTRY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_industry_mapping",
        category="industry",
        description="查询股票或关键词的行业归属。输入股票代码/名称返回行业分类和概念标签；输入行业关键词返回行业映射及关联关键词。",
        input_schema=GetIndustryMappingInput.model_json_schema(),
        output_schema=GetIndustryMappingOutput.model_json_schema(),
        examples=[
            {"symbol_or_keyword": "000001"},
            {"symbol_or_keyword": "白酒"},
        ],
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_industry_chain",
        category="industry",
        description="查询产业链节点数据，包括节点名称、层级、热度评分、趋势评分及相关证券。可输入关键词过滤。",
        input_schema=GetIndustryChainInput.model_json_schema(),
        output_schema=GetIndustryChainOutput.model_json_schema(),
        examples=[
            {"keyword": "锂电池"},
            {},
        ],
        timeout_ms=30000,
        unavailable_behavior="Returns status='unavailable' with empty nodes list when chain node data is insufficient.",
    ),
    ToolSpec(
        name="get_related_stocks_by_industry",
        category="industry",
        description="按行业查询相关股票列表，返回行业内的活跃股票及其评分、趋势信号。",
        input_schema=GetRelatedStocksByIndustryInput.model_json_schema(),
        output_schema=GetRelatedStocksByIndustryOutput.model_json_schema(),
        examples=[
            {"industry": "白酒", "limit": 10},
            {"industry": "半导体"},
        ],
        timeout_ms=20000,
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_industry_heatmap",
        category="industry",
        description="查询行业热度热力图数据，包括各行业的热度评分、短期/中期热度变化、关键词和热门文章。",
        input_schema=GetIndustryHeatmapInput.model_json_schema(),
        output_schema=GetIndustryHeatmapOutput.model_json_schema(),
        examples=[
            {"keyword_or_scope": "A", "limit": 10},
            {"keyword_or_scope": "新能源"},
        ],
        timeout_ms=30000,
        unavailable_behavior="Returns status='unavailable' with empty rows list when industry heat data is insufficient.",
    ),
]


# ===================================================================
# SCORING TOOLS  (4 tools)
# ===================================================================

SCORING_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_stock_score",
        category="scoring",
        description="查询单只股票的综合评分，包含最终得分、各维度得分（行业/公司/趋势/催化）、评级和置信度。",
        input_schema=GetStockScoreInput.model_json_schema(),
        output_schema=GetStockScoreOutput.model_json_schema(),
        examples=[
            {"symbol": "000001"},
            {"symbol": "腾讯控股"},
        ],
        timeout_ms=15000,
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_score_breakdown",
        category="scoring",
        description="查询股票评分的详细分项拆解，包含行业、公司、趋势、催化各维度得分及风险扣分，以及评分公式说明。",
        input_schema=GetScoreBreakdownInput.model_json_schema(),
        output_schema=GetScoreBreakdownOutput.model_json_schema(),
        examples=[
            {"symbol": "000001"},
            {"symbol": "贵州茅台"},
        ],
        timeout_ms=15000,
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_top_scored_stocks",
        category="scoring",
        description="查询全市场评分最高的股票排行榜，按综合评分降序排列，可按市场范围过滤。",
        input_schema=GetTopScoredStocksInput.model_json_schema(),
        output_schema=GetTopScoredStocksOutput.model_json_schema(),
        examples=[
            {"scope": "A", "limit": 10},
            {"scope": "US"},
        ],
        timeout_ms=30000,
        unavailable_behavior="Returns status='unavailable' with empty stocks list when scoring data is insufficient.",
    ),
    ToolSpec(
        name="get_risk_flags",
        category="scoring",
        description="查询股票的风险标签列表，基于风险引擎评估结果，包括风险扣分、风险说明及人工复核建议。",
        input_schema=GetRiskFlagsInput.model_json_schema(),
        output_schema=GetRiskFlagsOutput.model_json_schema(),
        examples=[
            {"symbol": "000001"},
            {"symbol": "腾讯控股"},
        ],
        risk_level="medium",
        timeout_ms=15000,
        unavailable_behavior="Returns status='unavailable' with empty flags list when stock is not recognised.",
    ),
]


# ===================================================================
# EVIDENCE TOOLS  (4 tools)
# ===================================================================

EVIDENCE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_stock_evidence",
        category="evidence",
        description="查询个股的证据链，包括行业逻辑、公司逻辑、趋势逻辑、催化逻辑、风险总结、待验证问题及信源引用。",
        input_schema=GetStockEvidenceInput.model_json_schema(),
        output_schema=GetStockEvidenceOutput.model_json_schema(),
        examples=[
            {"symbol": "000001"},
            {"symbol": "贵州茅台"},
        ],
        unavailable_behavior="Returns status='unavailable' with empty source_refs when no evidence chain exists for the stock.",
    ),
    ToolSpec(
        name="get_industry_evidence",
        category="evidence",
        description="查询行业的结构化证据，包括近期相关新闻文章、信源引用及摘要说明。",
        input_schema=GetIndustryEvidenceInput.model_json_schema(),
        output_schema=GetIndustryEvidenceOutput.model_json_schema(),
        examples=[
            {"keyword": "白酒", "limit": 5},
            {"keyword": "人工智能"},
        ],
        timeout_ms=20000,
        unavailable_behavior=_UNAVAILABLE_MSG,
    ),
    ToolSpec(
        name="get_recent_catalysts",
        category="evidence",
        description="查询近期催化事件，包括相关新闻文章和证据事件，按时间倒序排列，支持按股票或行业筛选。",
        input_schema=GetRecentCatalystsInput.model_json_schema(),
        output_schema=GetRecentCatalystsOutput.model_json_schema(),
        examples=[
            {"symbol_or_industry": "000001"},
            {"symbol_or_industry": "新能源"},
        ],
        timeout_ms=20000,
        unavailable_behavior="Returns status='unavailable' with empty catalysts list when no recent event data is found.",
    ),
    ToolSpec(
        name="get_evidence_summary",
        category="evidence",
        description="智能路由查询证据摘要：输入股票代码/名称返回个股证据链，输入行业关键词返回行业证据。",
        input_schema=GetEvidenceSummaryInput.model_json_schema(),
        output_schema=GetEvidenceSummaryOutput.model_json_schema(),
        examples=[
            {"symbol_or_keyword": "000001"},
            {"symbol_or_keyword": "半导体"},
        ],
        unavailable_behavior="Dispatches to get_stock_evidence or get_industry_evidence; inherits their unavailable behavior.",
    ),
]


# ===================================================================
# REPORT TOOLS  (3 tools)
# ===================================================================

REPORT_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_latest_daily_report",
        category="report",
        description="获取最新一期日报数据，包含市场摘要、热门行业、趋势股票、关注列表、风险提醒及完整Markdown。",
        input_schema=GetLatestDailyReportInput.model_json_schema(),
        output_schema=GetLatestDailyReportOutput.model_json_schema(),
        examples=[{}],
        timeout_ms=10000,
        unavailable_behavior="Returns status='unavailable' when no daily report has been generated yet.",
    ),
    ToolSpec(
        name="generate_report_outline",
        category="report",
        description="根据任务类型生成研究报告大纲（Markdown标题层级），支持多种投研任务类型。不依赖数据库会话。",
        input_schema=GenerateReportOutlineInput.model_json_schema(),
        output_schema=GenerateReportOutlineOutput.model_json_schema(),
        examples=[
            {"task_type": "stock_deep_research"},
            {"task_type": "daily_watch"},
        ],
        timeout_ms=5000,
        unavailable_behavior="Falls back to default template if the requested task type template is not found.",
    ),
    ToolSpec(
        name="format_research_report",
        category="report",
        description="格式化研究报告上下文，返回可用的上下文键列表。格式化工序由 runtime adapter 完成。不依赖数据库会话。",
        input_schema=FormatResearchReportInput.model_json_schema(),
        output_schema=FormatResearchReportOutput.model_json_schema(),
        examples=[
            {"context": {"symbol": "000001", "scores": {}, "evidence": {}}},
        ],
        timeout_ms=5000,
        unavailable_behavior="Always returns status='ok'; processes whatever context is provided.",
    ),
]


# ------------------------------------------------------------------
# WATCHLIST INPUTS (1)
# ------------------------------------------------------------------


class AddToWatchlistInput(BaseModel):
    thesis_id: int = Field(description="研报论点 ID（ResearchThesis）")
    user_id: str | None = Field(
        default=None,
        description="用户标识符，用于用户隔离。留空则对所有用户可见。",
    )
    priority: str | None = Field(
        default=None,
        description="优先级：S / A / B，默认 B",
    )


class AddToWatchlistOutput(BaseModel):
    status: str = Field(description="ok 或 error")
    message: str | None = Field(default=None, description="操作结果描述")
    item: dict[str, Any] | None = Field(default=None, description="创建的观察池条目")


# ===================================================================
# WATCHLIST TOOLS  (1 tool)
# ===================================================================

WATCHLIST_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="add_to_watchlist",
        category="watchlist",
        description=(
            "将研报论点添加到观察池（观察池）。"
            "从研报论点自动提取关注理由、关键指标、失效条件。"
            "不会重复添加同一论点。"
        ),
        input_schema=AddToWatchlistInput.model_json_schema(),
        output_schema=AddToWatchlistOutput.model_json_schema(),
        read_only=False,
        risk_level="medium",
        timeout_ms=10000,
        examples=[
            {"thesis_id": 1, "description": "按论点 ID 添加到观察池"},
            {"thesis_id": 1, "user_id": "user_a", "priority": "A", "description": "指定用户和优先级"},
        ],
        unavailable_behavior="Returns status='error' with message when thesis_id is not found.",
    ),
]


# ===================================================================
# AGGREGATE HELPERS
# ===================================================================

_ALL_TOOLS: list[ToolSpec] = (
    MARKET_TOOLS + INDUSTRY_TOOLS + SCORING_TOOLS + EVIDENCE_TOOLS + REPORT_TOOLS + WATCHLIST_TOOLS
)

_TOOL_MAP: dict[str, ToolSpec] = {spec.name: spec for spec in _ALL_TOOLS}

_CATEGORY_MAP: dict[str, list[ToolSpec]] = {
    "market": MARKET_TOOLS,
    "industry": INDUSTRY_TOOLS,
    "scoring": SCORING_TOOLS,
    "evidence": EVIDENCE_TOOLS,
    "report": REPORT_TOOLS,
    "watchlist": WATCHLIST_TOOLS,
}


def get_all_specs() -> list[ToolSpec]:
    """Return every registered ToolSpec."""
    return list(_ALL_TOOLS)


def get_spec_by_name(name: str) -> ToolSpec | None:
    """Look up a single spec by its tool name."""
    return _TOOL_MAP.get(name)


def get_specs_by_category(category: str) -> list[ToolSpec]:
    """Return all specs for a given category."""
    return list(_CATEGORY_MAP.get(category, []))


def build_mcp_manifest() -> dict[str, Any]:
    """Build an enhanced MCP tool manifest (no MCP SDK required).

    The manifest follows the MCP protocol shape extended with read-only policy
    and full tool metadata.
    """
    return {
        "protocol": "mcp",
        "version": "1.0",
        "server_info": {
            "name": "alpha-radar-agent",
            "version": "2.2",
        },
        "capabilities": {
            "tools": {"read_only": True},
        },
        "read_only_policy": (
            "All tools are read-only. No trading, order placement, "
            "or portfolio modification."
        ),
        "tools": [spec.to_dict() for spec in _ALL_TOOLS],
    }
