from __future__ import annotations

GOLDEN_CASES = [
    {
        "prompt": "帮我分析中际旭创是不是还在主升趋势",
        "expected_task_type": "stock_deep_research",
        "required_phrases": ["风险提示", "不构成任何投资建议"],
    },
    {
        "prompt": "帮我找 AI 服务器产业链今天最强的节点",
        "expected_task_type": "industry_chain_radar",
        "required_phrases": ["产业链雷达", "证据"],
    },
    {
        "prompt": "帮我筛出当前强势股股票池",
        "expected_task_type": "trend_pool_scan",
        "required_phrases": ["趋势股票池扫描", "风险提示"],
    },
]
