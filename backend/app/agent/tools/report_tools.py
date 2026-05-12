from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.schemas import AgentTaskType
from app.agent.skills.registry import load_skill_template
from app.db.models import DailyReport, StockScore


def get_latest_daily_report(session: Session) -> dict[str, Any]:
    latest_score_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    query = select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)
    if latest_score_date is not None:
        query = query.where(DailyReport.report_date <= latest_score_date)
    report = session.scalars(query).first()
    if report is None:
        return {"status": "unavailable", "message": "日报数据不足，请先运行 daily pipeline"}
    return {
        "status": "ok",
        "report_date": report.report_date.isoformat(),
        "title": report.title,
        "market_summary": report.market_summary,
        "top_industries": _loads_list(report.top_industries),
        "top_trend_stocks": _loads_list(report.top_trend_stocks),
        "new_watchlist_stocks": _loads_list(report.new_watchlist_stocks),
        "risk_alerts": _loads_list(report.risk_alerts),
        "full_markdown": report.full_markdown,
        "data_source": "daily_report",
    }


def generate_report_outline(task_type: str) -> dict[str, Any]:
    try:
        template = load_skill_template(task_type)
    except FileNotFoundError:
        template = load_skill_template(AgentTaskType.STOCK_DEEP_RESEARCH)
    headings = [line.strip() for line in template.splitlines() if line.startswith("#")]
    return {"status": "ok", "task_type": task_type, "headings": headings, "data_source": "agent_skill_template"}


def format_research_report(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "message": "报告格式化由 runtime adapter 完成。",
        "context_keys": sorted(context.keys()),
        "data_source": "agent_context",
    }


def _loads_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []
