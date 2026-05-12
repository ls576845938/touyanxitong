from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


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
# MARKET TOOLS  (4 tools)
# ===================================================================

MARKET_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_stock_basic",
        category="market",
        description="查询股票基础信息，包括代码、名称、市场、板块、行业、概念标签、市值、ST状态等。",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_or_name": {
                    "type": "string",
                    "description": "股票代码（如 000001）或股票名称（如 平安银行）",
                },
            },
            "required": ["symbol_or_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "code": {"type": "string", "description": "股票代码"},
                "name": {"type": "string", "description": "股票名称"},
                "market": {"type": "string", "description": "市场（A/US/HK）"},
                "board": {"type": "string", "description": "板块"},
                "exchange": {"type": "string", "description": "交易所"},
                "industry_level1": {"type": "string", "description": "一级行业"},
                "industry_level2": {"type": "string", "description": "二级行业"},
                "concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "概念标签列表",
                },
                "market_cap": {"type": "number", "description": "总市值"},
                "float_market_cap": {"type": "number", "description": "流通市值"},
                "is_st": {"type": "boolean", "description": "是否ST"},
                "is_active": {"type": "boolean", "description": "是否活跃"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或名称",
                },
                "window": {
                    "type": "string",
                    "description": "区间窗口，如 60d、120d、250d，默认 120d",
                },
            },
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "code": {"type": "string"},
                "name": {"type": "string"},
                "trade_date": {"type": "string", "description": "最新交易日"},
                "close": {"type": "number", "description": "最新收盘价"},
                "window": {"type": "string", "description": "实际使用的区间"},
                "window_return_pct": {
                    "type": "number",
                    "description": "区间收益率百分比",
                },
                "ma20": {"type": "number"},
                "ma60": {"type": "number"},
                "ma120": {"type": "number"},
                "ma250": {"type": "number"},
                "trend_score": {"type": "number"},
                "relative_strength_rank": {"type": "number"},
                "is_ma_bullish": {"type": "boolean"},
                "is_breakout_120d": {"type": "boolean"},
                "is_breakout_250d": {"type": "boolean"},
                "volume_expansion_ratio": {"type": "number"},
                "max_drawdown_60d": {"type": "number"},
                "explanation": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "市场范围：A / US / HK / 留空表示全部",
                },
                "window": {
                    "type": "string",
                    "description": "动量区间窗口字符串（传递给趋势信号的上下文）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，最大 100，默认 20",
                },
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "window": {"type": "string"},
                "scope": {"type": "string"},
                "stocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "market": {"type": "string"},
                            "industry": {"type": "string"},
                            "trade_date": {"type": "string"},
                            "trend_score": {"type": "number"},
                            "relative_strength_rank": {"type": "number"},
                            "is_ma_bullish": {"type": "boolean"},
                            "is_breakout_120d": {"type": "boolean"},
                            "is_breakout_250d": {"type": "boolean"},
                            "volume_expansion_ratio": {"type": "number"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "stock_count": {"type": "integer"},
                "stocks_with_bars": {"type": "integer"},
                "bar_coverage_ratio": {"type": "number"},
                "latest_trade_date": {"type": "string"},
                "latest_trend_date": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol_or_keyword": {
                    "type": "string",
                    "description": "股票代码、股票名称或行业关键词",
                },
            },
            "required": ["symbol_or_keyword"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "industry": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "产业链关键词，留空返回全部节点",
                },
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "keyword": {"type": "string"},
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                            "level": {"type": "integer"},
                            "chain_name": {"type": "string"},
                            "node_type": {"type": "string"},
                            "description": {"type": "string"},
                            "heat_score": {"type": "number"},
                            "trend_score": {"type": "number"},
                            "related_security_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "description": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "industry": {
                    "type": "string",
                    "description": "行业名称或关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，最大 100，默认 20",
                },
            },
            "required": ["industry"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "industry": {"type": "string", "description": "匹配到的行业名称"},
                "stocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "market": {"type": "string"},
                            "industry": {"type": "string"},
                            "final_score": {"type": "number"},
                            "rating": {"type": "string"},
                            "trend_score": {"type": "number"},
                            "is_ma_bullish": {"type": "boolean"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "keyword_or_scope": {
                    "type": "string",
                    "description": "行业关键词或市场范围（A/US/HK/ALL），留空默认 ALL",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，最大 100，默认 20",
                },
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "keyword": {"type": "string"},
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "industry_id": {"type": "integer"},
                            "name": {"type": "string"},
                            "trade_date": {"type": "string"},
                            "heat_score": {"type": "number"},
                            "heat_1d": {"type": "number"},
                            "heat_7d": {"type": "number"},
                            "heat_30d": {"type": "number"},
                            "heat_change_7d": {"type": "number"},
                            "top_keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "top_articles": {"type": "array"},
                            "explanation": {"type": "string"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或名称",
                },
            },
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "code": {"type": "string"},
                "name": {"type": "string"},
                "market": {"type": "string"},
                "industry": {"type": "string"},
                "trade_date": {"type": "string"},
                "final_score": {"type": "number"},
                "raw_score": {"type": "number"},
                "rating": {"type": "string"},
                "industry_score": {"type": "number"},
                "company_score": {"type": "number"},
                "trend_score": {"type": "number"},
                "catalyst_score": {"type": "number"},
                "risk_penalty": {"type": "number"},
                "confidence_level": {"type": "string"},
                "confidence_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "explanation": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或名称",
                },
            },
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "breakdown": {
                    "type": "object",
                    "properties": {
                        "industry_score": {"type": "number"},
                        "company_score": {"type": "number"},
                        "trend_score": {"type": "number"},
                        "catalyst_score": {"type": "number"},
                        "risk_penalty": {"type": "number"},
                    },
                },
                "scoring_basis": {
                    "type": "string",
                    "description": "评分公式说明",
                },
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "市场范围：A / US / HK / 留空表示全部",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，最大 100，默认 20",
                },
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "scope": {"type": "string"},
                "trade_date": {"type": "string"},
                "stocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "market": {"type": "string"},
                            "industry": {"type": "string"},
                            "final_score": {"type": "number"},
                            "rating": {"type": "string"},
                            "industry_score": {"type": "number"},
                            "company_score": {"type": "number"},
                            "trend_score": {"type": "number"},
                            "catalyst_score": {"type": "number"},
                            "risk_penalty": {"type": "number"},
                            "confidence_level": {"type": "string"},
                            "explanation": {"type": "string"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或名称",
                },
            },
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "code": {"type": "string"},
                "name": {"type": "string"},
                "penalty": {"type": "number", "description": "风险扣分"},
                "flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "风险标签列表",
                },
                "explanation": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或名称",
                },
            },
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "code": {"type": "string"},
                "name": {"type": "string"},
                "trade_date": {"type": "string"},
                "summary": {"type": "string"},
                "industry_logic": {"type": "string"},
                "company_logic": {"type": "string"},
                "trend_logic": {"type": "string"},
                "catalyst_logic": {"type": "string"},
                "risk_summary": {"type": "string"},
                "questions_to_verify": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "source_refs": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "行业关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回文章条数，最大 50，默认 12",
                },
            },
            "required": ["keyword"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "keyword": {"type": "string"},
                "summary": {"type": "string"},
                "articles": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "source_refs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "source": {"type": "string"},
                            "url": {"type": "string"},
                            "published_at": {"type": "string"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol_or_industry": {
                    "type": "string",
                    "description": "股票代码/名称或行业关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，最大 50，默认 10",
                },
            },
            "required": ["symbol_or_industry"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "catalysts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "source_name": {"type": "string"},
                            "source_url": {"type": "string"},
                            "event_time": {"type": "string"},
                            "confidence": {"type": "number"},
                            "impact_direction": {"type": "string"},
                            "risk_notes": {"type": "string"},
                        },
                    },
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "symbol_or_keyword": {
                    "type": "string",
                    "description": "股票代码/名称 或 行业关键词",
                },
            },
            "required": ["symbol_or_keyword"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "report_date": {"type": "string"},
                "title": {"type": "string"},
                "market_summary": {"type": "string"},
                "top_industries": {"type": "array"},
                "top_trend_stocks": {"type": "array"},
                "new_watchlist_stocks": {"type": "array"},
                "risk_alerts": {"type": "array"},
                "full_markdown": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
        examples=[{}],
        timeout_ms=10000,
        unavailable_behavior="Returns status='unavailable' when no daily report has been generated yet.",
    ),
    ToolSpec(
        name="generate_report_outline",
        category="report",
        description="根据任务类型生成研究报告大纲（Markdown标题层级），支持多种投研任务类型。不依赖数据库会话。",
        input_schema={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "任务类型标识符，如 stock_deep_research、industry_overview、daily_watch 等",
                },
            },
            "required": ["task_type"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "task_type": {"type": "string"},
                "headings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Markdown 标题行列表",
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
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
        input_schema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "description": "研究报告上下文字典",
                },
            },
            "required": ["context"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "message": {"type": "string"},
                "context_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "排序后的上下文键列表",
                },
                "data_source": {"type": "string"},
            },
            "required": ["status"],
        },
        examples=[
            {"context": {"symbol": "000001", "scores": {}, "evidence": {}}},
        ],
        timeout_ms=5000,
        unavailable_behavior="Always returns status='ok'; processes whatever context is provided.",
    ),
]


# ===================================================================
# AGGREGATE HELPERS
# ===================================================================

_ALL_TOOLS: list[ToolSpec] = (
    MARKET_TOOLS + INDUSTRY_TOOLS + SCORING_TOOLS + EVIDENCE_TOOLS + REPORT_TOOLS
)

_TOOL_MAP: dict[str, ToolSpec] = {spec.name: spec for spec in _ALL_TOOLS}

_CATEGORY_MAP: dict[str, list[ToolSpec]] = {
    "market": MARKET_TOOLS,
    "industry": INDUSTRY_TOOLS,
    "scoring": SCORING_TOOLS,
    "evidence": EVIDENCE_TOOLS,
    "report": REPORT_TOOLS,
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
    """Build a standard MCP tool manifest (no MCP SDK required)."""
    return {
        "protocol": "mcp",
        "version": "1.0",
        "serverInfo": {
            "name": "alpha-radar-agent",
            "version": "2.1.0",
        },
        "tools": [spec.to_mcp_dict() for spec in _ALL_TOOLS],
    }
