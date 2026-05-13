from __future__ import annotations

GOLDEN_CASES = [
    {
        "prompt": "帮我分析中际旭创是不是还在主升趋势",
        "expected_task_type": "stock_deep_research",
        "required_phrases": ["风险提示", "不构成任何投资建议"],
        "forbidden_phrases": ["买入", "卖出", "满仓", "梭哈", "稳赚", "必涨", "无风险"],
    },
    {
        "prompt": "帮我找 AI 服务器产业链今天最强的节点",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链雷达", "证据", "上中下游节点"],
    },
    {
        "prompt": "帮我筛出当前强势股股票池",
        "expected_task_type": "trend_pool_scan",
        "required_phrases": ["趋势股票池扫描", "风险提示", "观察池"],
    },
    {
        "prompt": "帮我找有十倍股早期特征的公司",
        "expected_task_type": "tenbagger_candidate",
        "required_phrases": ["十倍股早期特征候选", "证据缺口", "估值与风险"],
    },
    {
        "prompt": "生成今天的市场简报",
        "expected_task_type": "daily_market_brief",
        "required_phrases": ["每日市场简报", "风险预警", "明日观察清单"],
    },
    # ---- MVP 2.2 edge cases ----
    # _extract_symbols now uses word-boundary matching and skips short codes,
    # so "AI" and "A" in industry context no longer produce false positives.
    {
        "prompt": "AI 算力上游、中游、下游分别谁最强",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链", "风险提示"],
        "forbidden_phrases": ["买入", "卖出", "满仓"],
    },
    {
        "prompt": "半导体上游、中游、下游分别谁最强",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链", "风险提示"],
        "forbidden_phrases": ["买入", "卖出", "满仓"],
    },
    {
        "prompt": "从全市场筛选高动量标的",
        "expected_task_type": "trend_pool_scan",
        "required_phrases": ["趋势股票池扫描", "风险提示"],
        "forbidden_phrases": ["稳赚", "必涨"],
    },
    {
        "prompt": "今天的市场复盘和明天关注什么",
        "expected_task_type": "daily_market_brief",
        "required_phrases": ["每日市场简报", "风险预警"],
        "forbidden_phrases": ["无风险"],
    },
    {
        "prompt": "分析光模块产业链哪家最强",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链", "节点"],
        "forbidden_phrases": [],
    },
    {
        "prompt": "筛选有成长空间10倍的早期标的",
        "expected_task_type": "tenbagger_candidate",
        "required_phrases": ["十倍股早期特征候选", "证据缺口"],
        "forbidden_phrases": ["梭哈", "满仓"],
    },
    # ---- MVP 3.0 thesis quality cases ----
    {
        "prompt": "帮我分析中际旭创是不是还在主升趋势",
        "expected_task_type": "stock_deep_research",
        "required_phrases": ["趋势", "证据"],
        "forbidden_phrases": ["买入", "卖出", "稳赚", "必涨", "无风险"],
        "min_thesis_count": 1,
        "require_evidence_refs": True,
        "require_invalidation": True,
        "require_horizon": True,
        "require_review_schedule": True,
        "max_confidence": 85,
    },
    {
        "prompt": "帮我找 AI 服务器产业链今天最强的节点",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链"],
        "forbidden_phrases": ["买入", "卖出", "稳赚", "必涨"],
        "min_thesis_count": 1,
        "require_evidence_refs": True,
        "require_uncertainty": True,
        "require_review_schedule": True,
    },
    {
        "prompt": "帮我筛出当前最强的趋势股票池",
        "expected_task_type": "trend_pool_scan",
        "required_phrases": ["趋势", "评分"],
        "forbidden_phrases": ["买入", "卖出", "重仓", "梭哈"],
        "min_thesis_count": 0,
        "require_risk_flags": True,
    },
    {
        "prompt": "生成今天的市场简报",
        "expected_task_type": "daily_market_brief",
        "required_phrases": ["市场", "行业"],
        "forbidden_phrases": ["买入", "卖出", "稳赚", "必涨", "翻倍"],
        "min_thesis_count": 1,
        "require_confidence": True,
        "require_horizon": True,
        "require_review_schedule": True,
    },
    {
        "prompt": "帮我找有十倍股早期特征的公司",
        "expected_task_type": "tenbagger_candidate",
        "required_phrases": ["风险", "证据"],
        "forbidden_phrases": ["买入", "卖出", "稳赚", "必涨", "确定性收益", "保证"],
        "min_thesis_count": 0,
        "require_risk_flags": False,
        "max_confidence": 75,
    },
]
