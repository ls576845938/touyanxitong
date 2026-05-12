from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentTaskType
from app.agent.runtime.base import AgentRuntimeResult, RuntimeAdapter


class MockRuntimeAdapter(RuntimeAdapter):
    provider_name = "mock"

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        task_type = str(context.get("task_type") or AgentTaskType.STOCK_DEEP_RESEARCH)
        if task_type == AgentTaskType.INDUSTRY_CHAIN_RADAR:
            return self._industry_report(prompt, context, skill_template)
        if task_type == AgentTaskType.TREND_POOL_SCAN:
            return self._trend_pool_report(prompt, context, skill_template)
        if task_type == AgentTaskType.TENBAGGER_CANDIDATE:
            return self._tenbagger_report(prompt, context, skill_template)
        if task_type == AgentTaskType.DAILY_MARKET_BRIEF:
            return self._daily_brief(prompt, context, skill_template)
        return self._stock_report(prompt, context, skill_template)

    def _stock_report(self, prompt: str, context: dict[str, Any], _: str) -> AgentRuntimeResult:
        stock = _tool_data(context, "market.get_stock_basic")
        trend = _tool_data(context, "market.get_price_trend")
        score = _tool_data(context, "scoring.get_score_breakdown")
        mapping = _tool_data(context, "industry.get_industry_mapping")
        evidence = _tool_data(context, "evidence.get_stock_evidence")
        risks = _tool_data(context, "scoring.get_risk_flags")
        stock_name = stock.get("name") or context.get("primary_symbol") or "未识别标的"
        stock_code = stock.get("code") or context.get("primary_symbol") or ""
        title = f"个股深度投研：{stock_name}"
        evidence_refs = _evidence_refs(evidence)
        warnings = _warnings_from_context(context)

        md = f"""# {title}
## 1. 核心结论
- 用户问题：{prompt}
- 当前定位：{stock_name} {stock_code} 的分析应以趋势、产业链位置、评分拆解和证据质量共同验证。
- 观察结论：{_stock_conclusion(stock, trend, score)}

## 2. 公司与业务画像
- 证券代码：{stock_code or "unavailable"}
- 所属市场：{stock.get("market", "unavailable")}
- 一级行业：{stock.get("industry_level1", "unavailable")}
- 二级行业：{stock.get("industry_level2", "unavailable")}
- 概念标签：{_join(stock.get("concepts"))}
- 数据来源：stock、daily_bar、security/universe metadata。

## 3. 产业链位置
- 映射状态：{mapping.get("status", "unavailable")}
- 行业/主题：{mapping.get("industry", stock.get("industry_level1", "unavailable"))}
- 依据：{mapping.get("reason", "当前映射证据不足，需要人工复核产业链位置。")}

## 4. 趋势状态
- 最新交易日：{trend.get("trade_date", "unavailable")}
- 近窗口收益：{_fmt_pct(trend.get("window_return_pct"))}
- 趋势分：{_fmt_num(trend.get("trend_score"))}
- 相对强度排名：{trend.get("relative_strength_rank", "unavailable")}
- 均线结构：{"多头排列" if trend.get("is_ma_bullish") else "未确认多头排列"}
- 量能状态：{_fmt_num(trend.get("volume_expansion_ratio"))} 倍。

## 5. 评分拆解
- 综合评分：{_fmt_num(score.get("final_score"))}，评级：{score.get("rating", "unavailable")}
- 产业趋势分：{_fmt_num(score.get("industry_score"))}
- 公司质量分：{_fmt_num(score.get("company_score"))}
- 股价趋势分：{_fmt_num(score.get("trend_score"))}
- 催化分：{_fmt_num(score.get("catalyst_score"))}
- 风险扣分：{_fmt_num(score.get("risk_penalty"))}
- 评分依据：{score.get("explanation", "当前评分数据不足。")}

## 6. 证据链
- 摘要：{evidence.get("summary", "当前证据不足。")}
- 产业逻辑：{evidence.get("industry_logic", "unavailable")}
- 公司逻辑：{evidence.get("company_logic", "unavailable")}
- 趋势逻辑：{evidence.get("trend_logic", "unavailable")}
- 催化逻辑：{evidence.get("catalyst_logic", "unavailable")}
- 来源引用：{_join_refs(evidence_refs)}

## 7. 风险提示与风险因素
- 风险标签：{_join(risks.get("flags"))}
- 风险说明：{risks.get("explanation", evidence.get("risk_summary", "仍需复核数据完整性和证据真实性。"))}
- 数据质量：{_join(warnings) if warnings else "未触发额外数据质量提示。"}

## 8. 后续观察清单
- 跟踪下一期趋势分、相对强度排名和成交额放大是否延续。
- 复核产业链催化是否能被公告、订单、财报或第三方数据确认。
- 对照反证信息，检查风险扣分项是否扩大。

## 9. 不确定性说明
- 当前报告是基于平台已有结构化数据的自动整理，不构成投资建议。
- 若行情、基本面、新闻或产业映射数据缺失，结论只能作为待验证观察线索。
"""
        return AgentRuntimeResult(
            title=title,
            summary=_strip_md_bullets(_stock_conclusion(stock, trend, score)),
            content_md=md,
            content_json={"task_type": "stock_deep_research", "stock": stock, "trend": trend, "score": score, "evidence": evidence},
            evidence_refs=evidence_refs,
            warnings=warnings,
        )

    def _industry_report(self, prompt: str, context: dict[str, Any], _: str) -> AgentRuntimeResult:
        keyword = str(context.get("primary_industry") or "产业链")
        chain = _tool_data(context, "industry.get_industry_chain")
        heatmap = _tool_data(context, "industry.get_industry_heatmap")
        stocks = _tool_data(context, "industry.get_related_stocks_by_industry")
        evidence = _tool_data(context, "evidence.get_industry_evidence")
        title = f"产业链雷达：{keyword}"
        hot_rows = heatmap.get("rows") or []
        stock_rows = stocks.get("stocks") or []
        evidence_refs = _evidence_refs(evidence)
        warnings = _warnings_from_context(context)
        md = f"""# {title}
## 1. 今日产业链热度
- 用户问题：{prompt}
- 热度状态：{heatmap.get("status", "unavailable")}
- 最高热度节点/行业：{_top_names(hot_rows, "name")}
- 数据来源：industry_heat、stock_score、trend_signal、news_article。

## 2. 上中下游节点
- 节点数量：{len(chain.get("nodes") or [])}
- 节点清单：{_top_names(chain.get("nodes") or [], "name", limit=12)}
- 说明：{chain.get("description", "当前产业链结构数据不足，需补齐节点关系。")}

## 3. 核心股票
- 相关股票：{_top_stock_names(stock_rows)}
- 评分依据：按平台最新综合评分、趋势分和产业映射结果排序。

## 4. 动量扩散路径
- 当前强势扩散观察：{_industry_momentum_text(stock_rows)}
- 需要继续验证是否从单点催化扩散到多节点、多股票的趋势共振。

## 5. 催化剂与证据
- 证据摘要：{evidence.get("summary", "当前证据不足。")}
- 近期催化：{_top_names(evidence.get("articles") or [], "title", limit=5)}
- 来源引用：{_join_refs(evidence_refs)}

## 6. 风险提示与反证
- 若热度主要来自低置信度来源或模拟数据，需要降低结论权重。
- 若相关股票数量少、趋势分分化，产业链强度可能只是局部表现。
- 数据质量：{_join(warnings) if warnings else "未触发额外数据质量提示。"}

## 7. 观察清单
- 跟踪热度是否连续多日维持。
- 跟踪核心节点是否出现新增真实来源证据。
- 跟踪相关股票评分和趋势分是否同步改善。
"""
        return AgentRuntimeResult(
            title=title,
            summary=f"{keyword} 已完成产业链热度、节点、相关股票和证据链整理。",
            content_md=md,
            content_json={"task_type": "industry_chain_radar", "keyword": keyword, "chain": chain, "heatmap": heatmap, "stocks": stocks, "evidence": evidence},
            evidence_refs=evidence_refs,
            warnings=warnings,
        )

    def _trend_pool_report(self, prompt: str, context: dict[str, Any], _: str) -> AgentRuntimeResult:
        momentum = _tool_data(context, "market.get_momentum_rank")
        top_scores = _tool_data(context, "scoring.get_top_scored_stocks")
        rows = top_scores.get("stocks") or momentum.get("stocks") or []
        warnings = _warnings_from_context(context)
        title = "趋势股票池扫描"
        md = f"""# {title}
## 1. 筛选条件
- 用户问题：{prompt}
- 筛选逻辑：综合评分、趋势分、相对强度、突破状态和风险扣分。
- 数据来源：stock_score、trend_signal、stock。

## 2. S级观察池
{_pool_section(rows, min_score=80)}

## 3. A级观察池
{_pool_section(rows, min_score=70, max_score=80)}

## 4. B级观察池
{_pool_section(rows, min_score=60, max_score=70)}

## 5. 剔除名单与原因
- 本次 MVP 仅返回候选观察池。剔除项需结合风险标签、数据门控和人工复核补充。

## 6. 风险提示
- 趋势强不代表确定性，短期拥挤、成交额异常放大和数据缺口都需要验证。
- 数据质量：{_join(warnings) if warnings else "未触发额外数据质量提示。"}

## 7. 下一步人工验证问题
- 评分靠前股票是否有真实来源证据支撑。
- 行业热度是否能解释趋势扩散。
- 是否存在财报、监管、流动性或估值反证。
"""
        return AgentRuntimeResult(
            title=title,
            summary=f"已整理 {len(rows)} 个趋势观察候选，需继续做证据和风险复核。",
            content_md=md,
            content_json={"task_type": "trend_pool_scan", "rows": rows},
            evidence_refs=[],
            warnings=warnings,
        )

    def _tenbagger_report(self, prompt: str, context: dict[str, Any], _: str) -> AgentRuntimeResult:
        top_scores = _tool_data(context, "scoring.get_top_scored_stocks")
        rows = top_scores.get("stocks") or []
        warnings = _warnings_from_context(context)
        title = "十倍股早期特征候选"
        md = f"""# {title}
## 1. 筛选逻辑
- 用户问题：{prompt}
- MVP 逻辑：产业空间、公司质量、趋势确认、催化证据、风险扣分共同筛选候选。

## 2. 候选列表
{_candidate_rows(rows)}

## 3. 产业空间
- 优先观察高产业分、高热度行业中的候选，但必须验证行业空间和公司受益链条。

## 4. 公司质量
- 使用公司质量分作为粗筛，财务质量不足时只能进入待验证清单。

## 5. 趋势确认
- 使用趋势分、相对强度和突破状态辅助判断，不能单独作为结论。

## 6. 催化剂
- 催化分高的候选需要关联真实来源证据，避免只依赖热词。

## 7. 估值与风险
- 市值、估值、财务、回撤、数据源质量都需要人工复核。
- 数据质量：{_join(warnings) if warnings else "未触发额外数据质量提示。"}

## 8. 证据缺口
- 补齐公告、财报、订单、产业数据和反证信息后再调整候选等级。
"""
        return AgentRuntimeResult(
            title=title,
            summary=f"已生成 {len(rows)} 个早期特征候选的观察清单。",
            content_md=md,
            content_json={"task_type": "tenbagger_candidate", "rows": rows},
            evidence_refs=[],
            warnings=warnings,
        )

    def _daily_brief(self, prompt: str, context: dict[str, Any], _: str) -> AgentRuntimeResult:
        daily = _tool_data(context, "report.get_latest_daily_report")
        heatmap = _tool_data(context, "industry.get_industry_heatmap")
        momentum = _tool_data(context, "market.get_momentum_rank")
        warnings = _warnings_from_context(context)
        title = "每日市场简报"
        md = f"""# {title}
## 1. 今日最强产业链
- 用户问题：{prompt}
- 行业热度：{_top_names(heatmap.get("rows") or [], "name", limit=5)}

## 2. 新增催化事件
- 最新日报：{daily.get("title", "unavailable")}
- 摘要：{daily.get("market_summary", "当前日报数据不足。")}

## 3. 高动量股票
- 高动量观察：{_top_stock_names(momentum.get("stocks") or [])}

## 4. 风险预警
- { _join(daily.get("risk_alerts")) if daily.get("risk_alerts") else "当前风险预警数据不足，需要查看数据质量门。" }
- 数据质量：{_join(warnings) if warnings else "未触发额外数据质量提示。"}

## 5. 明日观察清单
- 复核热度延续性。
- 复核高动量股票的证据链和风险标签。
- 关注低置信度数据源对结论的影响。
"""
        return AgentRuntimeResult(
            title=title,
            summary="已生成市场简报、强产业链、高动量股票和风险预警整理。",
            content_md=md,
            content_json={"task_type": "daily_market_brief", "daily": daily, "heatmap": heatmap, "momentum": momentum},
            evidence_refs=[],
            warnings=warnings,
        )


def _tool_data(context: dict[str, Any], name: str) -> dict[str, Any]:
    value = context.get("tool_results", {}).get(name, {})
    return value if isinstance(value, dict) else {}


def _warnings_from_context(context: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for result in context.get("tool_results", {}).values():
        if isinstance(result, dict) and result.get("status") == "unavailable":
            warnings.append(str(result.get("message") or "部分数据暂不可用。"))
        if isinstance(result, dict) and result.get("data_quality_warning"):
            warnings.append(str(result["data_quality_warning"]))
    return _dedupe(warnings)


def _stock_conclusion(stock: dict[str, Any], trend: dict[str, Any], score: dict[str, Any]) -> str:
    if stock.get("status") == "unavailable":
        return "当前未识别到明确股票，无法形成个股观察结论。"
    if trend.get("status") == "unavailable" or score.get("status") == "unavailable":
        return "当前趋势或评分数据不足，只能进入待补数观察。"
    trend_score = float(trend.get("trend_score") or 0.0)
    final_score = float(score.get("final_score") or 0.0)
    if trend.get("is_ma_bullish") and trend_score >= 70 and final_score >= 70:
        return "趋势结构和综合评分处于较强观察区间，但仍需证据链和风险项确认。"
    if trend_score >= 55 or final_score >= 60:
        return "存在一定观察价值，关键在于趋势延续和证据质量能否继续确认。"
    return "当前信号偏弱或数据不足，适合放入跟踪清单等待进一步确认。"


def _evidence_refs(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    refs = evidence.get("source_refs") or evidence.get("evidence_refs") or []
    return [item for item in refs if isinstance(item, dict)]


def _join_refs(refs: list[dict[str, Any]]) -> str:
    if not refs:
        return "当前暂无结构化来源引用。"
    titles = [str(item.get("title") or item.get("source") or item.get("url") or item) for item in refs[:6]]
    return "；".join(titles)


def _join(value: Any) -> str:
    if not value:
        return "unavailable"
    if isinstance(value, list):
        return "、".join(str(item) for item in value[:8]) if value else "unavailable"
    return str(value)


def _fmt_num(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.2f}"
    return "unavailable"


def _fmt_pct(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.2f}%"
    return "unavailable"


def _top_names(rows: list[Any], key: str, limit: int = 8) -> str:
    names = [str(row.get(key)) for row in rows if isinstance(row, dict) and row.get(key)]
    return "、".join(names[:limit]) if names else "unavailable"


def _top_stock_names(rows: list[Any], limit: int = 8) -> str:
    names = []
    for row in rows[:limit]:
        if isinstance(row, dict):
            names.append(f"{row.get('name', '')}({row.get('code', '')})")
    return "、".join(names) if names else "unavailable"


def _industry_momentum_text(rows: list[Any]) -> str:
    if not rows:
        return "当前相关股票数据不足。"
    bullish = [row for row in rows if isinstance(row, dict) and row.get("is_ma_bullish")]
    return f"{len(bullish)} 个相关股票呈现多头结构，需观察是否扩散到更多节点。" if bullish else "尚未看到明确多点趋势扩散。"


def _pool_section(rows: list[Any], *, min_score: float, max_score: float | None = None) -> str:
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = float(row.get("final_score") or 0.0)
        if score < min_score:
            continue
        if max_score is not None and score >= max_score:
            continue
        selected.append(row)
    if not selected:
        return "- 当前没有满足该档位的候选。"
    return "\n".join(
        f"- {row.get('name')}({row.get('code')})：综合评分 {float(row.get('final_score') or 0):.1f}，趋势分 {float(row.get('trend_score') or 0):.1f}，评级 {row.get('rating', 'unavailable')}。"
        for row in selected[:8]
    )


def _candidate_rows(rows: list[Any]) -> str:
    if not rows:
        return "- 当前数据不足，无法生成候选列表。"
    return "\n".join(
        f"- {row.get('name')}({row.get('code')})：综合评分 {float(row.get('final_score') or 0):.1f}，产业 {float(row.get('industry_score') or 0):.1f}，公司 {float(row.get('company_score') or 0):.1f}，趋势 {float(row.get('trend_score') or 0):.1f}。"
        for row in rows[:10]
        if isinstance(row, dict)
    )


def _strip_md_bullets(value: str) -> str:
    return value.replace("- ", "").strip()


def _dedupe(items: list[str]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows
