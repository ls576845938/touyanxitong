RISK_DISCLAIMER = "本模块仅用于风险预算测算和仓位计划记录，不构成任何投资建议、买卖建议或收益承诺。市场有风险，决策需独立判断。"

FORBIDDEN_TERMS: dict[str, str] = {
    "建议买入": "风险预算测算中",
    "建议卖出": "风险暴露评估中",
    "应该买": "是否执行需由用户独立判断",
    "应该卖": "是否执行需由用户独立判断",
    "可以重仓": "风险暴露较高，需谨慎评估",
    "满仓": "风险暴露达到上限",
    "梭哈": "避免单一方向过度暴露",
    "加杠杆": "谨慎评估风险暴露",
    "稳赚": "存在不确定性",
    "必涨": "仍需进一步确认",
    "无风险": "风险尚未充分暴露",
    "保证收益": "收益预期需独立评估",
    "仓位推荐": "风险预算上限",
}


def sanitize_risk_output(text: str) -> str:
    for forbidden, replacement in FORBIDDEN_TERMS.items():
        text = text.replace(forbidden, replacement)
    return text
