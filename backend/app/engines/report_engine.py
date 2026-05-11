from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DailyReportResult:
    report_date: date
    title: str
    market_summary: str
    top_industries: list[dict[str, Any]]
    top_trend_stocks: list[dict[str, Any]]
    new_watchlist_stocks: list[dict[str, Any]]
    risk_alerts: list[str]
    full_markdown: str


def build_daily_report(
    report_date: date,
    industries: list[Any],
    scores: list[Any],
    evidence_by_code: dict[str, Any],
    stocks_by_code: dict[str, Any],
    data_quality: dict[str, Any] | None = None,
    research_universe: dict[str, Any] | None = None,
    watchlist_changes: dict[str, Any] | None = None,
    scan_summary: dict[str, Any] | None = None,
    retail_research: dict[str, Any] | None = None,
) -> DailyReportResult:
    top_industries = [
        {
            "industry_id": heat.industry_id,
            "heat_score": round(float(heat.heat_score), 2),
            "explanation": heat.explanation,
            "top_keywords": json.loads(heat.top_keywords) if isinstance(heat.top_keywords, str) else heat.top_keywords,
        }
        for heat in sorted(industries, key=lambda row: row.heat_score, reverse=True)[:10]
    ]
    ranked_scores = sorted(scores, key=lambda row: row.final_score, reverse=True)
    top_trend_stocks = []
    new_watchlist_stocks = []
    risk_alerts = []
    for score in ranked_scores[:30]:
        stock = stocks_by_code.get(score.stock_code)
        if not stock:
            continue
        row = {
            "code": score.stock_code,
            "name": stock.name,
            "market": stock.market,
            "board": stock.board,
            "exchange": stock.exchange,
            "industry": stock.industry_level1,
            "industry_level2": stock.industry_level2,
            "final_score": round(float(score.final_score), 2),
            "raw_score": round(float(getattr(score, "raw_score", score.final_score)), 2),
            "rating": score.rating,
            "industry_score": score.industry_score,
            "company_score": score.company_score,
            "trend_score": score.trend_score,
            "catalyst_score": score.catalyst_score,
            "risk_penalty": score.risk_penalty,
            "confidence": {
                "data_confidence": round(float(getattr(score, "data_confidence", 0.0) or 0.0), 2),
                "evidence_confidence": round(float(getattr(score, "evidence_confidence", 0.0) or 0.0), 2),
                "level": getattr(score, "confidence_level", "unknown"),
            },
            "explanation": score.explanation,
        }
        top_trend_stocks.append(row)
        if score.rating in {"强观察", "观察"}:
            new_watchlist_stocks.append(row)
        if score.risk_penalty >= 3:
            risk_alerts.append(f"{stock.name} 风险扣分{score.risk_penalty:.1f}：{score.explanation}")

    quality_status = data_quality.get("status") if data_quality else "UNKNOWN"
    universe_summary = research_universe.get("summary", {}) if research_universe else {}
    changes_summary = watchlist_changes.get("summary", {}) if watchlist_changes else {}
    retail_summary = retail_research.get("summary", {}) if retail_research else {}
    scan = scan_summary or {}
    security_master_count = scan.get("security_master_count", universe_summary.get("stock_count", len(stocks_by_code)))
    covered_stock_count = scan.get("covered_stock_count", "-")
    trend_signal_count = scan.get("trend_signal_count", len(scores))
    market_summary = (
        f"AlphaRadar 当前证券主数据 {security_master_count} 只，"
        f"已有行情覆盖 {covered_stock_count} 只，"
        f"今日完成 {len(scores)} 只有效评分扫描，"
        f"生成 {len(new_watchlist_stocks)} 个观察池候选；"
        f"零售线索 S/A {retail_summary.get('s_count', 0) + retail_summary.get('a_count', 0)} 个；"
        f"数据质量 {quality_status}，研究池准入 {universe_summary.get('eligible_count', '-')}/{universe_summary.get('stock_count', '-')}。"
        "结果仅用于投研线索整理。"
    )
    markdown_lines = [
        "# AlphaRadar 每日投研雷达",
        "",
        "## 今日市场摘要",
        market_summary,
        "",
        "## 今日运行状态",
        f"- 数据质量：{quality_status}，FAIL {_nested(data_quality, 'summary', 'fail_count')}，WARN {_nested(data_quality, 'summary', 'warn_count')}。",
        f"- 扫描口径：证券主数据 {security_master_count} 只，已有行情覆盖 {covered_stock_count} 只，趋势信号 {trend_signal_count} 只，有效评分 {len(scores)} 只。",
        f"- 研究股票池：可研究 {universe_summary.get('eligible_count', '-')}/{universe_summary.get('stock_count', '-')}，准入率 {_pct(universe_summary.get('eligible_ratio'))}。",
        f"- 观察池变化：当前 {changes_summary.get('latest_watch_count', '-')}，新进 {changes_summary.get('new_count', '-')}，移出 {changes_summary.get('removed_count', '-')}。",
        "",
        "## 观察池变化",
    ]
    _append_watchlist_change_section(markdown_lines, watchlist_changes)
    markdown_lines.extend(
        [
            "",
            "## 研究股票池准入",
        ]
    )
    _append_universe_section(markdown_lines, research_universe)
    markdown_lines.extend(
        [
            "",
            "## 数据质量",
        ]
    )
    _append_data_quality_section(markdown_lines, data_quality)
    markdown_lines.extend([
        "",
        "## 今日热度较高赛道",
    ])
    for item in top_industries:
        markdown_lines.append(f"- 产业ID {item['industry_id']}：热度分 {item['heat_score']}，{item['explanation']}")
    markdown_lines.extend(["", "## 今日趋势增强观察样本"])
    for item in top_trend_stocks[:10]:
        markdown_lines.append(f"- {item['name']}（{item['code']}）：{item['rating']}，总分 {item['final_score']}。")
    markdown_lines.extend(["", "## 新进入观察池"])
    for item in new_watchlist_stocks[:10]:
        markdown_lines.append(f"- {item['name']}（{item['code']}）：{item['industry']}，{item['explanation']}")
    markdown_lines.extend(["", "## 重点证据链"])
    for item in new_watchlist_stocks[:5]:
        evidence = evidence_by_code.get(item["code"])
        if evidence:
            markdown_lines.append(f"- {item['name']}：{evidence.summary}")
    markdown_lines.extend(["", "## 零售线索候选"])
    _append_retail_research_section(markdown_lines, retail_research)
    markdown_lines.extend(["", "## 风险预警"])
    if risk_alerts:
        markdown_lines.extend(f"- {alert}" for alert in risk_alerts[:10])
    else:
        markdown_lines.append("- 今日样本未触发高风险扣分阈值，但仍需人工核验估值、财报与公告。")
    markdown_lines.extend(
        [
            "",
            "## 明日待跟踪事项",
            "- 跟踪产业热度是否持续，而不是单日脉冲。",
            "- 核验观察池公司的公告、财报和订单兑现证据。",
            "- 对趋势增强股票检查是否存在高位情绪过热。",
        ]
    )
    return DailyReportResult(
        report_date=report_date,
        title=f"AlphaRadar 每日投研雷达 {report_date.isoformat()}",
        market_summary=market_summary,
        top_industries=top_industries,
        top_trend_stocks=top_trend_stocks,
        new_watchlist_stocks=new_watchlist_stocks,
        risk_alerts=risk_alerts,
        full_markdown="\n".join(markdown_lines),
    )


def _append_watchlist_change_section(markdown_lines: list[str], watchlist_changes: dict[str, Any] | None) -> None:
    if not watchlist_changes:
        markdown_lines.append("- 暂无观察池变化数据。")
        return
    new_entries = watchlist_changes.get("new_entries", [])[:10]
    removed_entries = watchlist_changes.get("removed_entries", [])[:10]
    upgraded = watchlist_changes.get("upgraded", [])[:10]
    downgraded = watchlist_changes.get("downgraded", [])[:10]
    if new_entries:
        markdown_lines.append("### 新进观察")
        markdown_lines.extend(f"- {item['name']}（{item['code']}）：{item.get('rating') or '-'}，总分 {item.get('final_score') or '-'}。" for item in new_entries)
    if removed_entries:
        markdown_lines.append("### 移出观察")
        markdown_lines.extend(f"- {item['name']}（{item['code']}）：前评级 {item.get('previous_rating') or '-'}，前分数 {item.get('previous_score') or '-'}。" for item in removed_entries)
    if upgraded:
        markdown_lines.append("### 评级提升")
        markdown_lines.extend(
            f"- {item['name']}（{item['code']}）：{item.get('previous_rating') or '-'} → {item.get('rating') or '-'}，分数变化 {item.get('score_delta') or 0}。"
            for item in upgraded
        )
    if downgraded:
        markdown_lines.append("### 评级下降")
        markdown_lines.extend(
            f"- {item['name']}（{item['code']}）：{item.get('previous_rating') or '-'} → {item.get('rating') or '-'}，分数变化 {item.get('score_delta') or 0}。"
            for item in downgraded
        )
    if not new_entries and not removed_entries and not upgraded and not downgraded:
        markdown_lines.append("- 今日观察池没有显著变化。")


def _append_universe_section(markdown_lines: list[str], research_universe: dict[str, Any] | None) -> None:
    if not research_universe:
        markdown_lines.append("- 暂无研究股票池准入数据。")
        return
    for segment in research_universe.get("segments", [])[:10]:
        markdown_lines.append(
            f"- {segment.get('market_label', segment.get('market'))}/{segment.get('board_label', segment.get('board'))}："
            f"{segment.get('eligible_count')}/{segment.get('stock_count')} 可研究，准入率 {_pct(segment.get('eligible_ratio'))}。"
        )


def _append_data_quality_section(markdown_lines: list[str], data_quality: dict[str, Any] | None) -> None:
    if not data_quality:
        markdown_lines.append("- 暂无数据质量结果。")
        return
    for segment in data_quality.get("segments", [])[:10]:
        markdown_lines.append(
            f"- {segment.get('market_label', segment.get('market'))}/{segment.get('board_label', segment.get('board'))}："
            f"{segment.get('status')}，覆盖 {_pct(segment.get('coverage_ratio'))}，长期历史 {_pct(segment.get('preferred_history_ratio'))}。"
        )
    issues = data_quality.get("issues", [])[:5]
    if issues:
        markdown_lines.append("### 需处理的数据问题")
        markdown_lines.extend(f"- {item['name']}（{item['code']}）：{item['message']}" for item in issues)


def _append_retail_research_section(markdown_lines: list[str], retail_research: dict[str, Any] | None) -> None:
    if not retail_research:
        markdown_lines.append("- 暂无散户投研闭环数据。")
        return
    summary = retail_research.get("summary", {})
    markdown_lines.append(
        f"- 股票池候选 {summary.get('candidate_count', 0)} 个，证据事件 {summary.get('event_count', 0)} 条，"
        f"S {summary.get('s_count', 0)} / A {summary.get('a_count', 0)} / B {summary.get('b_count', 0)} / C {summary.get('c_count', 0)}。"
    )
    events = retail_research.get("new_evidence_events", [])
    markdown_lines.append("### 新增证据事件")
    if events:
        for event in events[:8]:
            markdown_lines.append(
                f"- {event.get('title')}：方向 {event.get('impact_direction')}，置信度 {event.get('confidence')}，"
                f"数据质量 {event.get('data_quality_status')}。"
            )
    else:
        markdown_lines.append("- 暂无新增结构化证据事件。")
    pools = retail_research.get("stock_pool_changes", [])
    markdown_lines.append("### 股票池变化")
    if pools:
        for pool in pools[:8]:
            security = pool.get("security") or {}
            markdown_lines.append(
                f"- {security.get('name', '-')}（{security.get('symbol', '-')}）：观察等级 {pool.get('pool_level')}，"
                f"conviction {pool.get('conviction_score')}，风险分 {pool.get('risk_score')}。"
            )
    else:
        markdown_lines.append("- 暂无股票池变化。")
    portfolio = retail_research.get("portfolio_risk", {})
    warnings = portfolio.get("risk_alerts", []) if isinstance(portfolio, dict) else []
    if warnings:
        markdown_lines.append("### 组合暴露提示")
        markdown_lines.extend(f"- {item}" for item in warnings[:5])
    tasks = retail_research.get("research_tasks", [])
    markdown_lines.append("### 今日研究任务")
    if tasks:
        markdown_lines.extend(f"- {task}" for task in tasks[:10])
    else:
        markdown_lines.append("- 补齐 S/A 候选的来源证据、趋势证据、风险提示和证伪条件。")


def _nested(payload: dict[str, Any] | None, first: str, second: str) -> Any:
    if not payload:
        return "-"
    return payload.get(first, {}).get(second, "-")


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except Exception:
        return "-"
