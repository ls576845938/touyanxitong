from __future__ import annotations

import re


RISK_DISCLAIMER = "本报告仅用于投研分析和信息整理，不构成任何投资建议。市场有风险，决策需独立判断。"

FORBIDDEN_REPLACEMENTS: dict[str, str] = {
    "买入": "纳入观察池",
    "卖出": "移出观察并复核风险",
    "满仓": "提高关注度但控制风险暴露",
    "梭哈": "避免单一方向过度暴露",
    "稳赚": "存在不确定性",
    "必涨": "仍需进一步确认",
    "无风险": "风险尚未充分暴露",
}


def sanitize_financial_output(content: str, *, data_quality_warnings: list[str] | None = None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    sanitized = content
    for forbidden, replacement in FORBIDDEN_REPLACEMENTS.items():
        if forbidden in sanitized:
            sanitized = sanitized.replace(forbidden, replacement)
            warnings.append(f"已替换不合规措辞：{forbidden}")

    sanitized = re.sub(r"建议\s*加仓", "建议跟踪观察", sanitized)
    sanitized = re.sub(r"建议\s*减仓", "建议复核风险暴露", sanitized)
    sanitized = re.sub(r"目标价\s*[:：]?\s*[\d.]+", "估值情景需独立复核", sanitized)

    if data_quality_warnings:
        warning_block = "\n".join(f"- {item}" for item in data_quality_warnings)
        if warning_block and warning_block not in sanitized:
            sanitized = f"{sanitized.rstrip()}\n\n## 数据质量风险提示\n{warning_block}\n"
        warnings.extend(data_quality_warnings)

    if RISK_DISCLAIMER not in sanitized:
        sanitized = f"{sanitized.rstrip()}\n\n---\n{RISK_DISCLAIMER}\n"

    return sanitized, _dedupe(warnings)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows
