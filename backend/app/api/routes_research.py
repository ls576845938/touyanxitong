from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DataSourceRun, EvidenceChain, Industry, IndustryHeat, IndustryKeyword, NewsArticle, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.pipeline.hot_terms_ingestion_job import run_hot_terms_ingestion_job

router = APIRouter(prefix="/api/research", tags=["research"])

WATCH_RATINGS = {"强观察", "观察"}

HOT_SOURCE_CATALOG = [
    {"key": "xueqiu", "label": "雪球", "kind": "community"},
    {"key": "reddit", "label": "Reddit", "kind": "community"},
    {"key": "tonghuashun", "label": "同花顺", "kind": "market_media"},
    {"key": "eastmoney", "label": "东方财富", "kind": "market_media"},
    {"key": "taoguba", "label": "淘股吧", "kind": "community"},
    {"key": "ibkr", "label": "盈透", "kind": "broker"},
    {"key": "wsj", "label": "华尔街日报", "kind": "professional_media"},
    {"key": "reuters_markets", "label": "Reuters Markets", "kind": "professional_media"},
    {"key": "cnbc_markets", "label": "CNBC Markets", "kind": "market_media"},
    {"key": "marketwatch", "label": "MarketWatch", "kind": "market_media"},
    {"key": "barrons", "label": "Barron's", "kind": "professional_media"},
    {"key": "investing", "label": "Investing.com", "kind": "market_media"},
    {"key": "industry_heat", "label": "系统产业热度", "kind": "internal"},
    {"key": "local_news", "label": "本地资讯库", "kind": "internal"},
]

HOT_SOURCE_LABELS = {item["key"]: item["label"] for item in HOT_SOURCE_CATALOG}
EXTERNAL_HOT_SOURCE_KEYS = {item["key"] for item in HOT_SOURCE_CATALOG if item["kind"] != "internal"}
HOT_TERM_STOPWORDS = {
    "热度值",
    "概念活跃",
    "概念走强",
    "最新部署",
    "重磅会议",
    "财经要闻",
    "公司新闻",
    "每日必读",
    "滚动新闻",
    "同花顺原创",
    "互动平台",
    "国内经济",
    "国际经济",
    "comments",
    "comment",
    "market",
    "markets",
    "stock",
    "stocks",
    "wsj",
    "google",
}


@router.get("/tasks")
def research_tasks(
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    watch_only: bool = Query(default=True),
    limit: int = Query(default=120, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return _research_tasks_payload(
        session=session,
        market=market,
        board=board,
        priority=priority,
        task_type=task_type,
        watch_only=watch_only,
        limit=limit,
    )


@router.get("/brief")
def research_brief(
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    watch_only: bool = Query(default=True),
    limit: int = Query(default=80, ge=1, le=300),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    payload = _research_tasks_payload(
        session=session,
        market=market,
        board=board,
        priority=None,
        task_type=None,
        watch_only=watch_only,
        limit=limit,
    )
    tasks = list(payload["tasks"])
    focus_stocks = _focus_stocks(tasks)
    focus_industries = _focus_industries(tasks)
    top_tasks = [task for task in tasks if task["priority"] == "high"][:20] or tasks[:20]
    brief = {
        "latest_date": payload["latest_date"],
        "filters": {
            "market": market.upper() if market and market.upper() != "ALL" else "ALL",
            "board": board.lower() if board and board.lower() != "all" else "all",
            "watch_only": watch_only,
            "limit": limit,
        },
        "summary": payload["summary"],
        "focus_stocks": focus_stocks,
        "focus_industries": focus_industries,
        "top_tasks": top_tasks,
    }
    return {**brief, "markdown": _brief_markdown(brief)}


@router.get("/hot-terms")
def research_hot_terms(
    window: str = Query(default="1d", description="1d or 7d"),
    limit: int = Query(default=80, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    window_key = _normalize_hot_window(window)
    if window_key not in {"1d", "7d"}:
        raise HTTPException(status_code=400, detail="window must be 1d or 7d")
    return _hot_terms_payload_v2(session=session, window=window_key, limit=limit)


@router.post("/hot-terms/refresh")
def refresh_research_hot_terms(
    sources: str | None = Query(default=None, description="Comma separated source keys"),
    limit_per_source: int = Query(default=12, ge=1, le=40),
    timeout_seconds: int = Query(default=5, ge=2, le=15),
    window: str = Query(default="1d", description="1d or 7d snapshot after refresh"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    window_key = _normalize_hot_window(window)
    if window_key not in {"1d", "7d"}:
        raise HTTPException(status_code=400, detail="window must be 1d or 7d")
    source_keys = [item.strip() for item in sources.split(",") if item.strip()] if sources else None
    result = run_hot_terms_ingestion_job(
        session,
        source_keys=source_keys,
        limit_per_source=limit_per_source,
        timeout_seconds=timeout_seconds,
    )
    return {
        **result,
        "snapshot": _hot_terms_payload_v2(session=session, window=window_key, limit=80),
    }


def _hot_terms_payload_v2(*, session: Session, window: str, limit: int) -> dict[str, object]:
    days = 1 if window == "1d" else 7
    latest_heat_date = session.scalars(
        select(IndustryHeat.trade_date).order_by(IndustryHeat.trade_date.desc()).limit(1)
    ).first()
    latest_article_dt = session.scalars(
        select(NewsArticle.published_at).order_by(NewsArticle.published_at.desc()).limit(1)
    ).first()

    heat_start_date = latest_heat_date - timedelta(days=days - 1) if latest_heat_date else None
    article_start_dt = _window_start_datetime(latest_article_dt, days)
    industry_keyword_map = _industry_keyword_map(session)
    industry_terms_by_name = _industry_terms_by_name(session)

    term_stats: dict[str, dict[str, Any]] = {}
    industry_stats: dict[str, dict[str, Any]] = {}
    platform_terms: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    source_counts: Counter[str] = Counter()
    article_count = 0
    matched_article_count = 0
    unmatched_article_count = 0

    if heat_start_date:
        heat_query = (
            select(IndustryHeat, Industry)
            .join(Industry, Industry.id == IndustryHeat.industry_id)
            .where(IndustryHeat.trade_date >= heat_start_date)
            .order_by(IndustryHeat.heat_score.desc())
        )
        for heat, industry in session.execute(heat_query).all():
            industry_name = industry.name
            score = _industry_heat_score(heat)
            _add_industry_stat(industry_stats, industry_name, score, "industry_heat", heat.trade_date.isoformat())
            source_counts["industry_heat"] += 1
            for keyword in _extract_keyword_texts(heat.top_keywords):
                term_score = 5 + score * 0.22
                _add_term_stat(
                    term_stats,
                    keyword,
                    term_score,
                    "industry_heat",
                    industry_name,
                    heat.trade_date.isoformat(),
                    None,
                )
                _add_platform_term(platform_terms, "industry_heat", keyword, term_score, industry_name)

    if article_start_dt:
        article_query = (
            select(NewsArticle)
            .where(NewsArticle.published_at >= article_start_dt)
            .order_by(NewsArticle.published_at.desc())
            .limit(1600)
        )
        for article in session.scalars(article_query).all():
            article_count += 1
            source_key = _normalize_hot_source(article.source, article.source_kind)
            industries, keywords = _verified_article_signal(
                article,
                industry_keyword_map=industry_keyword_map,
                industry_terms_by_name=industry_terms_by_name,
                source_key=source_key,
            )
            if not keywords and not industries:
                unmatched_article_count += 1
                continue
            matched_article_count += 1
            source_counts[source_key] += 1
            article_score = _article_score(article)
            published_at = _iso_datetime(article.published_at)

            for industry_name in industries:
                _add_industry_stat(industry_stats, industry_name, article_score, source_key, published_at)

            for keyword in keywords:
                inferred_industries = industries or industry_keyword_map.get(keyword.lower(), [])
                if not inferred_industries:
                    continue
                for industry_name in inferred_industries[:4]:
                    _add_term_stat(
                        term_stats,
                        keyword,
                        article_score,
                        source_key,
                        industry_name,
                        published_at,
                        _hot_term_example(article),
                    )
                    _add_platform_term(platform_terms, source_key, keyword, article_score, industry_name)

    source_runs = _latest_hot_source_runs(session)
    hot_terms = _format_hot_terms(term_stats, limit)
    hot_industries = _format_hot_industries(industry_stats, hot_terms, limit=min(40, limit))
    formatted_platform_terms = _format_platform_terms(platform_terms, source_counts, source_runs, limit=12)
    latest_date = _latest_snapshot_date(latest_heat_date, latest_article_dt)
    data_lag_days = _data_lag_days(latest_date)

    return {
        "latest_date": latest_date,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "summary": {
            "term_count": len(hot_terms),
            "industry_count": len(hot_industries),
            "article_count": article_count,
            "source_count": sum(1 for count in source_counts.values() if count > 0),
            "matched_article_count": matched_article_count,
            "unmatched_article_count": unmatched_article_count,
            "data_lag_days": data_lag_days,
            "is_stale": data_lag_days is not None and data_lag_days > 0,
            "data_mode": "database_aggregate",
        },
        "sources": _format_hot_sources(source_counts, source_runs),
        "hot_terms": hot_terms,
        "hot_industries": hot_industries,
        "platform_terms": formatted_platform_terms,
    }


def _research_tasks_payload(
    *,
    session: Session,
    market: str | None,
    board: str | None,
    priority: str | None,
    task_type: str | None,
    watch_only: bool,
    limit: int,
) -> dict[str, object]:
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"latest_date": None, "summary": _summary([]), "tasks": []}

    query = (
        select(EvidenceChain, Stock, StockScore, TrendSignal)
        .join(Stock, Stock.code == EvidenceChain.stock_code)
        .join(StockScore, (StockScore.stock_code == EvidenceChain.stock_code) & (StockScore.trade_date == EvidenceChain.trade_date))
        .join(TrendSignal, (TrendSignal.stock_code == EvidenceChain.stock_code) & (TrendSignal.trade_date == EvidenceChain.trade_date))
        .where(EvidenceChain.trade_date == latest_date)
        .order_by(StockScore.final_score.desc())
    )
    if market and market.upper() != "ALL":
        query = query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        query = query.where(Stock.board == board.lower())
    if watch_only:
        query = query.where(StockScore.rating.in_(WATCH_RATINGS))

    tasks: list[dict[str, object]] = []
    for evidence, stock, score, trend in session.execute(query).all():
        tasks.extend(_build_stock_tasks(evidence, stock, score, trend))

    if priority and priority.lower() != "all":
        tasks = [task for task in tasks if str(task["priority"]).lower() == priority.lower()]
    if task_type and task_type.lower() != "all":
        tasks = [task for task in tasks if str(task["task_type"]).lower() == task_type.lower()]

    tasks = sorted(tasks, key=lambda task: (float(task["priority_score"]), float(task["final_score"] or 0)), reverse=True)[:limit]
    return {
        "latest_date": latest_date.isoformat(),
        "summary": _summary(tasks),
        "tasks": tasks,
    }


def _build_stock_tasks(evidence: EvidenceChain, stock: Stock, score: StockScore, trend: TrendSignal) -> list[dict[str, object]]:
    questions = [str(item) for item in _loads_json_list(evidence.questions_to_verify)]
    source_refs = _loads_json_list(evidence.source_refs)
    tasks: list[dict[str, object]] = []
    for index, question in enumerate(questions):
        tasks.append(
            _task_payload(
                evidence=evidence,
                stock=stock,
                score=score,
                trend=trend,
                task_index=index,
                task_type="verify_question",
                title=_task_title(index, question),
                detail=question,
                source_refs=source_refs,
            )
        )
    if score.rating in WATCH_RATINGS:
        tasks.append(
            _task_payload(
                evidence=evidence,
                stock=stock,
                score=score,
                trend=trend,
                task_index=len(tasks),
                task_type="risk_review",
                title="核验风险摘要",
                detail=evidence.risk_summary,
                source_refs=source_refs,
            )
        )
    return tasks


def _task_payload(
    *,
    evidence: EvidenceChain,
    stock: Stock,
    score: StockScore,
    trend: TrendSignal,
    task_index: int,
    task_type: str,
    title: str,
    detail: str,
    source_refs: list[object],
) -> dict[str, object]:
    priority_score = _priority_score(score, trend, task_type)
    return {
        "id": f"{evidence.trade_date.isoformat()}-{stock.code}-{task_type}-{task_index}",
        "trade_date": evidence.trade_date.isoformat(),
        "stock_code": stock.code,
        "stock_name": stock.name,
        "market": stock.market,
        "board": stock.board,
        "industry": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "task_type": task_type,
        "priority": _priority_label(priority_score),
        "priority_score": round(priority_score, 2),
        "title": title,
        "detail": detail,
        "rating": score.rating,
        "final_score": score.final_score,
        "industry_score": score.industry_score,
        "company_score": score.company_score,
        "trend_score": score.trend_score,
        "risk_penalty": score.risk_penalty,
        "relative_strength_rank": trend.relative_strength_rank,
        "is_ma_bullish": trend.is_ma_bullish,
        "is_breakout_120d": trend.is_breakout_120d,
        "is_breakout_250d": trend.is_breakout_250d,
        "source_refs": source_refs,
    }


def _task_title(index: int, question: str) -> str:
    titles = ["核验产业兑现", "核验产业链地位", "核验趋势支撑", "核验估值与财务风险"]
    return titles[index] if index < len(titles) else question[:24]


def _priority_score(score: StockScore, trend: TrendSignal, task_type: str) -> float:
    rating_bonus = 16 if score.rating == "强观察" else 10 if score.rating == "观察" else 4 if score.rating == "弱观察" else 0
    trend_bonus = 4 if trend.is_breakout_250d else 2 if trend.is_breakout_120d else 0
    risk_bonus = min(score.risk_penalty * 3, 18)
    type_bonus = 8 if task_type == "risk_review" else 0
    return score.final_score + rating_bonus + trend_bonus + risk_bonus + type_bonus


def _priority_label(priority_score: float) -> str:
    if priority_score >= 88:
        return "high"
    if priority_score >= 72:
        return "medium"
    return "low"


def _summary(tasks: list[dict[str, object]]) -> dict[str, object]:
    priority_counts = Counter(str(task["priority"]) for task in tasks)
    type_counts = Counter(str(task["task_type"]) for task in tasks)
    market_counts = Counter(str(task["market"]) for task in tasks)
    stock_codes = {str(task["stock_code"]) for task in tasks}
    return {
        "task_count": len(tasks),
        "stock_count": len(stock_codes),
        "high_priority_count": priority_counts["high"],
        "medium_priority_count": priority_counts["medium"],
        "low_priority_count": priority_counts["low"],
        "risk_task_count": type_counts["risk_review"],
        "question_task_count": type_counts["verify_question"],
        "market_breakdown": dict(market_counts),
    }


def _focus_stocks(tasks: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task["stock_code"])].append(task)
    rows: list[dict[str, object]] = []
    for stock_code, stock_tasks in grouped.items():
        first = stock_tasks[0]
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": first["stock_name"],
                "market": first["market"],
                "board": first["board"],
                "industry": first["industry"],
                "industry_level2": first["industry_level2"],
                "rating": first["rating"],
                "final_score": first["final_score"],
                "task_count": len(stock_tasks),
                "high_priority_count": sum(1 for task in stock_tasks if task["priority"] == "high"),
                "risk_task_count": sum(1 for task in stock_tasks if task["task_type"] == "risk_review"),
                "top_task_titles": [str(task["title"]) for task in stock_tasks[:3]],
                "priority_score": max(float(task["priority_score"]) for task in stock_tasks),
            }
        )
    return sorted(rows, key=lambda row: (float(row["priority_score"]), float(row["final_score"] or 0)), reverse=True)[:limit]


def _focus_industries(tasks: list[dict[str, object]], limit: int = 10) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task["industry"])].append(task)
    rows: list[dict[str, object]] = []
    for industry, industry_tasks in grouped.items():
        stock_codes = {str(task["stock_code"]) for task in industry_tasks}
        rows.append(
            {
                "industry": industry,
                "task_count": len(industry_tasks),
                "stock_count": len(stock_codes),
                "high_priority_count": sum(1 for task in industry_tasks if task["priority"] == "high"),
                "risk_task_count": sum(1 for task in industry_tasks if task["task_type"] == "risk_review"),
                "average_priority_score": round(sum(float(task["priority_score"]) for task in industry_tasks) / max(len(industry_tasks), 1), 2),
                "top_stocks": [
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "final_score": row["final_score"],
                    }
                    for row in _focus_stocks(industry_tasks, limit=3)
                ],
            }
        )
    return sorted(rows, key=lambda row: (int(row["high_priority_count"]), float(row["average_priority_score"])), reverse=True)[:limit]


def _brief_markdown(brief: dict[str, object]) -> str:
    latest_date = brief["latest_date"] or "-"
    summary = brief["summary"]
    focus_stocks = list(brief["focus_stocks"])
    focus_industries = list(brief["focus_industries"])
    top_tasks = list(brief["top_tasks"])
    filters = brief["filters"]
    lines = [
        f"# AlphaRadar 每日研究工作单 {latest_date}",
        "",
        "> 研究辅助清单，仅用于整理证据、风险和待验证事项，不构成交易指令。",
        "",
        "## 筛选范围",
        f"- market: {filters['market']}",
        f"- board: {filters['board']}",
        f"- watch_only: {filters['watch_only']}",
        "",
        "## 今日概览",
        f"- 任务数：{summary['task_count']}",
        f"- 涉及股票：{summary['stock_count']}",
        f"- 高优先级：{summary['high_priority_count']}",
        f"- 风险核验：{summary['risk_task_count']}",
        f"- 验证事项：{summary['question_task_count']}",
        "",
        "## 处理顺序",
        "1. 先处理高优先级风险核验。",
        "2. 再处理高分股票的产业兑现和产业链地位核验。",
        "3. 最后处理趋势支撑、估值、财务质量和证据来源复核。",
        "",
        "## 重点股票",
    ]
    if focus_stocks:
        for row in focus_stocks[:10]:
            lines.append(
                f"- [ ] {row['stock_name']} {row['stock_code']} | {row['industry']} | {row['rating']} | score {float(row['final_score']):.1f} | tasks {row['task_count']} | high {row['high_priority_count']}"
            )
            for title in list(row["top_task_titles"])[:2]:
                lines.append(f"  - {title}")
    else:
        lines.append("- 暂无重点股票。")

    lines.extend(["", "## 赛道分布"])
    if focus_industries:
        for row in focus_industries:
            top_stocks = " / ".join(f"{item['stock_name']}({item['stock_code']})" for item in row["top_stocks"])
            lines.append(
                f"- {row['industry']}：任务 {row['task_count']}，股票 {row['stock_count']}，高优先级 {row['high_priority_count']}，风险 {row['risk_task_count']}；重点：{top_stocks or '-'}"
            )
    else:
        lines.append("- 暂无赛道任务。")

    lines.extend(["", "## 高优先级任务"])
    if top_tasks:
        for task in top_tasks[:20]:
            lines.append(
                f"- [ ] {task['stock_name']} {task['stock_code']} | {task['title']} | priority {float(task['priority_score']):.1f}"
            )
            lines.append(f"  - {task['detail']}")
    else:
        lines.append("- 暂无高优先级任务。")

    lines.extend(
        [
            "",
            "## 复盘记录要求",
            "- 每条结论必须记录证据来源和生成日期。",
            "- 证据不足时保留为待验证，不上升为结论。",
            "- 风险核验未完成前，不把候选提升为重点研究对象。",
        ]
    )
    return "\n".join(lines)


def _hot_terms_payload(session: Session, window: str, limit: int) -> dict[str, object]:
    window_days = 1 if window == "1d" else 7
    latest_heat_date = session.scalars(select(IndustryHeat.trade_date).order_by(IndustryHeat.trade_date.desc()).limit(1)).first()
    latest_article_at = session.scalars(select(NewsArticle.published_at).order_by(NewsArticle.published_at.desc()).limit(1)).first()
    anchor_date = latest_heat_date or (latest_article_at.date() if latest_article_at else None) or date.today()
    window_start_date = anchor_date - timedelta(days=window_days - 1)
    window_start_dt = datetime.combine(window_start_date, datetime.min.time(), tzinfo=timezone.utc)
    window_end_dt = datetime.combine(anchor_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    industries = {row.id: row for row in session.scalars(select(Industry)).all()}
    keyword_rows = session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True))).all()
    heat_rows = list(
        session.scalars(
            select(IndustryHeat)
            .where(IndustryHeat.trade_date >= window_start_date, IndustryHeat.trade_date <= anchor_date)
            .order_by(IndustryHeat.trade_date.desc(), IndustryHeat.heat_score.desc())
        ).all()
    )
    articles = list(
        session.scalars(
            select(NewsArticle)
            .where(NewsArticle.published_at >= window_start_dt, NewsArticle.published_at < window_end_dt)
            .order_by(NewsArticle.published_at.desc())
        ).all()
    )

    keyword_to_industry_names: dict[str, set[str]] = defaultdict(set)
    industry_keywords_by_name: dict[str, set[str]] = defaultdict(set)
    for row in keyword_rows:
        industry = industries.get(row.industry_id)
        industry_name = industry.name if industry else f"industry-{row.industry_id}"
        keyword_to_industry_names[row.keyword].add(industry_name)
        industry_keywords_by_name[industry_name].add(row.keyword)

    industry_rows: dict[str, dict[str, Any]] = {}
    term_rows: dict[str, dict[str, Any]] = {}
    article_source_counts: Counter[str] = Counter()

    def ensure_industry_row(industry_name: str) -> dict[str, Any]:
        row = industry_rows.get(industry_name)
        if row is None:
            row = {
                "industry_id": None,
                "name": industry_name,
                "score": 0.0,
                "heat_score": 0.0,
                "heat_rows": 0,
                "article_count": 0,
                "keyword_count": 0,
                "top_keywords": Counter(),
                "related_terms": Counter(),
                "article_sources": Counter(),
                "latest_trade_date": None,
                "latest_trade_date_obj": None,
                "latest_heat_score": 0.0,
                "heat_1d": 0.0,
                "heat_7d": 0.0,
                "heat_30d": 0.0,
                "heat_change_7d": 0.0,
                "heat_change_30d": 0.0,
                "source_mix": set(),
                "source_status": "empty",
                "explanation": "",
            }
            industry_rows[industry_name] = row
        return row

    def ensure_term_row(term: str) -> dict[str, Any]:
        row = term_rows.get(term)
        if row is None:
            row = {
                "term": term,
                "score": 0.0,
                "heat_mentions": 0,
                "article_mentions": 0,
                "keyword_mentions": 0,
                "industry_mentions": 0,
                "related_industries": set(),
                "article_sources": Counter(),
                "source_mix": set(),
                "source_status": "empty",
            }
            term_rows[term] = row
        return row

    for heat in heat_rows:
        industry = industries.get(heat.industry_id)
        industry_name = industry.name if industry else f"industry-{heat.industry_id}"
        industry_row = ensure_industry_row(industry_name)
        industry_row["industry_id"] = heat.industry_id
        industry_row["heat_rows"] += 1
        industry_row["heat_score"] += float(heat.heat_score or 0.0)
        industry_row["source_mix"].add("industry_heat")
        if industry_row["latest_trade_date_obj"] is None or heat.trade_date >= industry_row["latest_trade_date_obj"]:
            industry_row["latest_trade_date_obj"] = heat.trade_date
            industry_row["latest_trade_date"] = heat.trade_date.isoformat()
            industry_row["latest_heat_score"] = float(heat.heat_score or 0.0)
            industry_row["heat_1d"] = float(heat.heat_1d or 0.0)
            industry_row["heat_7d"] = float(heat.heat_7d or 0.0)
            industry_row["heat_30d"] = float(heat.heat_30d or 0.0)
            industry_row["heat_change_7d"] = float(heat.heat_change_7d or 0.0)
            industry_row["heat_change_30d"] = float(heat.heat_change_30d or 0.0)
            industry_row["explanation"] = heat.explanation
        for keyword in _loads_json_list(heat.top_keywords):
            term = str(keyword).strip()
            if not term:
                continue
            industry_row["top_keywords"][term] += 1
            industry_row["related_terms"][term] += 1
            term_row = ensure_term_row(term)
            term_row["heat_mentions"] += 1
            term_row["score"] += 3.0
            term_row["source_mix"].add("industry_heat")
            term_row["related_industries"].add(industry_name)

    for article in articles:
        article_keywords = {str(item).strip() for item in _loads_json_list(article.matched_keywords) if str(item).strip()}
        article_industries = {str(item).strip() for item in _loads_json_list(article.related_industries) if str(item).strip()}
        source_name = str(article.source or "unknown")
        article_source_counts[source_name] += 1
        matched_industries: set[str] = set(article_industries)
        for keyword in article_keywords:
            term_row = ensure_term_row(keyword)
            term_row["article_mentions"] += 1
            term_row["score"] += 2.4
            term_row["source_mix"].add("news_article")
            term_row["article_sources"][source_name] += 1
            for industry_name in keyword_to_industry_names.get(keyword, set()):
                matched_industries.add(industry_name)
                term_row["related_industries"].add(industry_name)
        for industry_name in matched_industries:
            industry_row = ensure_industry_row(industry_name)
            industry_row["article_count"] += 1
            industry_row["article_sources"][source_name] += 1
            industry_row["source_mix"].add("news_article")
            for keyword in article_keywords:
                industry_row["related_terms"][keyword] += 1
            for keyword in industry_keywords_by_name.get(industry_name, set()):
                industry_row["keyword_count"] += 1
                term_row = ensure_term_row(keyword)
                term_row["industry_mentions"] += 1
                term_row["score"] += 1.4
                term_row["source_mix"].add("industry_keyword")
                term_row["related_industries"].add(industry_name)

    for keyword_row in keyword_rows:
        industry = industries.get(keyword_row.industry_id)
        industry_name = industry.name if industry else f"industry-{keyword_row.industry_id}"
        industry_row = ensure_industry_row(industry_name)
        industry_row["keyword_count"] += 1
        industry_row["source_mix"].add("industry_keyword")
        term_row = ensure_term_row(keyword_row.keyword)
        term_row["keyword_mentions"] += 1
        term_row["score"] += 1.2
        term_row["source_mix"].add("industry_keyword")
        term_row["related_industries"].add(industry_name)

    for industry_row in industry_rows.values():
        if industry_row["heat_score"] > 0:
            industry_row["score"] += float(industry_row["heat_score"])
        industry_row["score"] += float(industry_row["article_count"]) * 4.5
        industry_row["score"] += float(industry_row["keyword_count"]) * 1.5
        industry_row["source_status"] = _source_mix_label(industry_row["source_mix"])

    for term_row in term_rows.values():
        term_row["score"] += float(term_row["industry_mentions"]) * 1.6
        term_row["source_status"] = _source_mix_label(term_row["source_mix"])

    industries_payload = sorted(
        (
            {
                "industry_id": row["industry_id"],
                "name": row["name"],
                "score": round(float(row["score"]), 2),
                "heat_score": round(float(row["heat_score"]), 2),
                "heat_rows": int(row["heat_rows"]),
                "article_count": int(row["article_count"]),
                "keyword_count": int(row["keyword_count"]),
                "latest_trade_date": row["latest_trade_date"],
                "latest_heat_score": round(float(row["latest_heat_score"]), 2),
                "heat_1d": round(float(row["heat_1d"]), 2),
                "heat_7d": round(float(row["heat_7d"]), 2),
                "heat_30d": round(float(row["heat_30d"]), 2),
                "heat_change_7d": round(float(row["heat_change_7d"]), 2),
                "heat_change_30d": round(float(row["heat_change_30d"]), 2),
                "top_keywords": [term for term, _count in row["top_keywords"].most_common(8)],
                "related_terms": [term for term, _count in row["related_terms"].most_common(10)],
                "article_sources": dict(row["article_sources"]),
                "source_mix": sorted(row["source_mix"]),
                "source_status": row["source_status"],
                "explanation": row["explanation"],
            }
            for row in industry_rows.values()
        ),
        key=lambda item: (float(item["score"]), float(item["heat_score"])),
        reverse=True,
    )[:limit]

    terms_payload = sorted(
        (
            {
                "term": row["term"],
                "score": round(float(row["score"]), 2),
                "heat_mentions": int(row["heat_mentions"]),
                "article_mentions": int(row["article_mentions"]),
                "keyword_mentions": int(row["keyword_mentions"]),
                "industry_mentions": int(row["industry_mentions"]),
                "related_industries": sorted(row["related_industries"]),
                "article_sources": dict(row["article_sources"]),
                "source_mix": sorted(row["source_mix"]),
                "source_status": row["source_status"],
            }
            for row in term_rows.values()
        ),
        key=lambda item: (float(item["score"]), int(item["article_mentions"]), int(item["heat_mentions"])),
        reverse=True,
    )[:limit]

    available_source_families = sum(1 for flag in [bool(heat_rows), bool(articles), bool(keyword_rows)] if flag)
    source_status = "local_aggregate" if available_source_families == 3 else "partial" if available_source_families > 0 else "empty"

    return {
        "window": window,
        "window_days": window_days,
        "source_status": source_status,
        "source_mix": sorted(
            [
                flag
                for flag, present in {
                    "industry_heat": bool(heat_rows),
                    "news_article": bool(articles),
                    "industry_keyword": bool(keyword_rows),
                }.items()
                if present
            ]
        ),
        "latest_trade_date": anchor_date.isoformat() if anchor_date else None,
        "window_start_date": window_start_date.isoformat() if window_start_date else None,
        "summary": {
            "industry_count": len(industries_payload),
            "term_count": len(terms_payload),
            "heat_row_count": len(heat_rows),
            "article_count": len(articles),
            "keyword_count": len(keyword_rows),
            "article_source_count": len(article_source_counts),
        },
        "source_breakdown": {
            "industry_heat_rows": len(heat_rows),
            "news_article_rows": len(articles),
            "industry_keyword_rows": len(keyword_rows),
            "article_sources": dict(article_source_counts),
        },
        "industries": industries_payload,
        "terms": terms_payload,
    }


def _source_mix_label(source_mix: set[str]) -> str:
    ordered = [item for item in ["industry_heat", "news_article", "industry_keyword"] if item in source_mix]
    if not ordered:
        return "empty"
    if len(ordered) == 1:
        return ordered[0]
    if len(ordered) == 3:
        return "local_aggregate"
    return "partial"


def _loads_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _loads_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_hot_window(window: str | None) -> str:
    normalized = (window or "1d").strip().lower()
    if normalized in {"today", "daily", "1", "1d"}:
        return "1d"
    if normalized in {"week", "weekly", "7", "7d"}:
        return "7d"
    return normalized


def _window_start_datetime(latest_article_dt: datetime | None, days: int) -> datetime | None:
    if latest_article_dt is None:
        return None
    start_date = latest_article_dt.date() - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, time.min)
    if latest_article_dt.tzinfo is not None:
        start_dt = start_dt.replace(tzinfo=latest_article_dt.tzinfo)
    return start_dt


def _industry_keyword_map(session: Session) -> dict[str, list[str]]:
    rows = session.execute(
        select(IndustryKeyword, Industry)
        .join(Industry, Industry.id == IndustryKeyword.industry_id)
        .where(IndustryKeyword.is_active == True)  # noqa: E712
    ).all()
    mapping: dict[str, list[str]] = defaultdict(list)
    for keyword, industry in rows:
        term = keyword.keyword.strip().lower()
        if term and industry.name not in mapping[term]:
            mapping[term].append(industry.name)
    return dict(mapping)


def _industry_terms_by_name(session: Session) -> dict[str, list[str]]:
    rows = session.execute(
        select(IndustryKeyword, Industry)
        .join(Industry, Industry.id == IndustryKeyword.industry_id)
        .where(IndustryKeyword.is_active == True)  # noqa: E712
    ).all()
    mapping: dict[str, list[str]] = defaultdict(list)
    for keyword, industry in rows:
        mapping[industry.name].extend([industry.name, keyword.keyword])
    return {industry: _dedupe_strings(terms) for industry, terms in mapping.items()}


def _industry_heat_score(heat: IndustryHeat) -> float:
    return max(
        float(heat.heat_score or 0),
        float(heat.heat_1d or 0),
        float(heat.heat_7d or 0) * 0.82,
        float(heat.heat_change_7d or 0) + 12 if float(heat.heat_change_7d or 0) > 0 else 0,
    )


def _article_score(article: NewsArticle) -> float:
    confidence = max(float(article.source_confidence or 0.3), 0.2)
    source_weight = {
        "professional_media": 1.2,
        "professional": 1.2,
        "market_media": 1.12,
        "media": 1.12,
        "news": 1.15,
        "rss": 1.05,
        "broker": 1.05,
        "community": 0.88,
        "mock": 0.6,
    }.get(str(article.source_kind or "").lower(), 1.0)
    keyword_bonus = min(len(_loads_json_list(article.matched_keywords)) * 1.2, 8)
    return 8 * confidence * source_weight + keyword_bonus + 4


def _article_industries(article: NewsArticle, industry_keyword_map: dict[str, list[str]]) -> list[str]:
    industries = [str(item).strip() for item in _loads_json_list(article.related_industries) if str(item).strip()]
    if industries:
        return _dedupe_strings(industries)
    inferred: list[str] = []
    for keyword in _extract_keyword_texts(article.matched_keywords):
        inferred.extend(industry_keyword_map.get(keyword.lower(), []))
    return _dedupe_strings(inferred)


def _verified_article_signal(
    article: NewsArticle,
    *,
    industry_keyword_map: dict[str, list[str]],
    industry_terms_by_name: dict[str, list[str]],
    source_key: str,
) -> tuple[list[str], list[str]]:
    if source_key not in EXTERNAL_HOT_SOURCE_KEYS:
        industries = _article_industries(article, industry_keyword_map)
        return industries, _article_hot_keywords(article, industry_keyword_map, industries, source_key)

    text = " ".join(
        str(value or "")
        for value in [article.title, article.summary, article.content]
        if value
    )
    stored_industries = [
        str(item).strip()
        for item in _loads_json_list(article.related_industries)
        if str(item).strip()
    ]
    keyword_candidates = _dedupe_strings(
        [
            *_extract_keyword_texts(article.matched_keywords),
            *_title_terms(article.title),
        ]
    )
    valid_keywords: list[str] = []
    valid_industries: list[str] = []

    for keyword in keyword_candidates:
        if not _is_hot_term_candidate(keyword):
            continue
        if not _hot_keyword_supported_by_text(
            keyword,
            text,
            industry_keyword_map=industry_keyword_map,
            industry_terms_by_name=industry_terms_by_name,
        ):
            continue
        valid_keywords.append(keyword)
        valid_industries.extend(industry_keyword_map.get(keyword.lower(), []))
        if keyword in industry_terms_by_name:
            valid_industries.append(keyword)

    for industry in stored_industries:
        if _hot_industry_supported_by_text(industry, text, industry_terms_by_name):
            valid_industries.append(industry)

    industries = _dedupe_strings(valid_industries)
    keywords = _dedupe_strings(valid_keywords)
    if industries and not keywords:
        keywords = [industry for industry in industries if _is_hot_term_candidate(industry)][:4]
    return industries, keywords


def _hot_keyword_supported_by_text(
    keyword: str,
    text: str,
    *,
    industry_keyword_map: dict[str, list[str]],
    industry_terms_by_name: dict[str, list[str]],
) -> bool:
    mapped_industries = industry_keyword_map.get(keyword.lower(), [])
    is_industry_name = keyword in industry_terms_by_name
    if not mapped_industries and not is_industry_name:
        return False
    if _term_matches_hot_text(text, keyword):
        return True
    if is_industry_name:
        return _hot_industry_supported_by_text(keyword, text, industry_terms_by_name)
    return any(
        _hot_industry_supported_by_text(industry, text, industry_terms_by_name)
        for industry in mapped_industries
    )


def _hot_industry_supported_by_text(industry: str, text: str, industry_terms_by_name: dict[str, list[str]]) -> bool:
    if _term_matches_hot_text(text, industry):
        return True
    terms = [*industry_terms_by_name.get(industry, []), *_hot_industry_aliases(industry)]
    return any(_term_matches_hot_text(text, term) for term in terms)


def _term_matches_hot_text(text: str, term: str) -> bool:
    clean = str(term).strip()
    if not clean:
        return False
    lowered = clean.lower()
    normalized = text.lower()
    if _is_ascii_term(lowered):
        return re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", normalized) is not None
    return lowered in normalized


def _is_ascii_term(value: str) -> bool:
    return bool(value) and all(ord(char) < 128 for char in value)


def _hot_industry_aliases(industry: str) -> list[str]:
    normalized = industry.lower()
    terms: list[str] = []
    if any(flag in normalized for flag in ["半导体", "芯片", "ai算力"]):
        terms.extend(["ai", "chip", "chips", "semiconductor", "semiconductors", "nvidia", "intel"])
    if any(flag in normalized for flag in ["新能源车", "汽车", "动力电池"]):
        terms.extend(["ev", "electric vehicle", "electric vehicles", "battery", "batteries"])
    if any(flag in normalized for flag in ["油气", "能源"]):
        terms.extend(["oil", "gas", "lng", "crude", "aramco"])
    if any(flag in normalized for flag in ["黄金", "贵金属"]):
        terms.extend(["gold", "silver", "precious metals"])
    if "机器人" in normalized:
        terms.extend(["robot", "robots", "robotics"])
    if "低空" in normalized or "无人机" in normalized:
        terms.extend(["drone", "drones", "evtol"])
    if "创新药" in normalized or "医药" in normalized:
        terms.extend(["drug", "drugs", "pharma", "biotech", "wegovy"])
    if "银行" in normalized:
        terms.extend(["bank", "banks", "credit"])
    if "物流" in normalized or "航运" in normalized:
        terms.extend(["shipping", "logistics", "freight"])
    if "军工" in normalized or "卫星" in normalized:
        terms.extend(["defense", "military", "satellite", "space"])
    return terms


def _extract_keyword_texts(raw: str) -> list[str]:
    values = _loads_json_list(raw)
    keywords: list[str] = []
    for item in values:
        if isinstance(item, str):
            keywords.append(item)
        elif isinstance(item, dict):
            value = item.get("keyword") or item.get("term") or item.get("name") or item.get("label")
            if value:
                keywords.append(str(value))
    return _dedupe_strings(_clean_term(value) for value in keywords)


def _article_hot_keywords(
    article: NewsArticle,
    industry_keyword_map: dict[str, list[str]],
    industries: list[str],
    source_key: str,
) -> list[str]:
    matched_keywords = [
        keyword
        for keyword in _extract_keyword_texts(article.matched_keywords)
        if _is_hot_term_candidate(keyword)
    ]
    if matched_keywords:
        return matched_keywords

    title_terms = [term for term in _title_terms(article.title) if _is_hot_term_candidate(term)]
    if not title_terms:
        return [industry for industry in industries if _is_hot_term_candidate(industry)][:4]

    mapped_terms = [term for term in title_terms if industry_keyword_map.get(term.lower())]
    if mapped_terms:
        return mapped_terms

    if industries:
        return [industry for industry in industries if _is_hot_term_candidate(industry)][:4]

    return []


def _title_terms(title: str) -> list[str]:
    normalized = re.sub(r"[+-]?\d+(?:\.\d+)?%?", " ", title)
    normalized = re.sub(r"热度值\s*\S*", " ", normalized, flags=re.IGNORECASE)
    separators = " ,，。；;:：/|｜-()（）[]【】#<>《》“”\"'·"
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    return _dedupe_strings(
        token.strip()
        for token in normalized.split()
        if _is_hot_term_candidate(token.strip())
    )[:8]


def _is_hot_term_candidate(term: str) -> bool:
    clean = _clean_term(term)
    if not clean:
        return False
    lowered = clean.lower()
    if lowered in HOT_TERM_STOPWORDS:
        return False
    if clean.isdigit() or len(clean) < 2 or len(clean) > 32:
        return False
    if re.fullmatch(r"[\d.万亿%+\-]+", clean):
        return False
    return True


def _clean_term(value: object) -> str:
    term = str(value).strip()
    return term[:32]


def _dedupe_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _normalize_hot_source(source: str, source_kind: str) -> str:
    haystack = f"{source} {source_kind}".lower()
    if "雪球" in source or "xueqiu" in haystack:
        return "xueqiu"
    if "reddit" in haystack:
        return "reddit"
    if "同花顺" in source or "tonghuashun" in haystack or "10jqka" in haystack or "ths" in haystack:
        return "tonghuashun"
    if "东方财富" in source or "eastmoney" in haystack:
        return "eastmoney"
    if "淘股吧" in source or "taoguba" in haystack:
        return "taoguba"
    if "盈透" in source or "interactive brokers" in haystack or "ibkr" in haystack:
        return "ibkr"
    if "华尔街日报" in source or "wall street journal" in haystack or "wsj" in haystack:
        return "wsj"
    if "reuters" in haystack or "路透" in source:
        return "reuters_markets"
    if "cnbc" in haystack:
        return "cnbc_markets"
    if "marketwatch" in haystack:
        return "marketwatch"
    if "barron" in haystack:
        return "barrons"
    if "investing" in haystack:
        return "investing"
    return "local_news"


def _add_term_stat(
    term_stats: dict[str, dict[str, Any]],
    term: str,
    score: float,
    source_key: str,
    industry: str,
    latest_at: str | None,
    example: dict[str, Any] | None,
) -> None:
    clean = _clean_term(term)
    if not clean:
        return
    stat = term_stats.setdefault(
        clean.lower(),
        {
            "term": clean,
            "score": 0.0,
            "mentions": 0,
            "sources": Counter(),
            "industries": Counter(),
            "latest_at": latest_at,
            "examples": [],
        },
    )
    stat["score"] += score
    stat["mentions"] += 1
    stat["sources"][source_key] += 1
    if industry and industry != "未映射":
        stat["industries"][industry] += 1
    if latest_at and (not stat["latest_at"] or latest_at > stat["latest_at"]):
        stat["latest_at"] = latest_at
    if example and len(stat["examples"]) < 3:
        stat["examples"].append(example)


def _hot_term_example(article: NewsArticle) -> dict[str, Any]:
    match_reason_raw = str(getattr(article, "match_reason", "") or "")
    is_synthetic = bool(getattr(article, "is_synthetic", False)) or _looks_synthetic_article(article)
    return {
        "title": article.title,
        "source": article.source,
        "url": article.source_url,
        "source_channel": str(getattr(article, "source_channel", "") or ""),
        "source_label": str(getattr(article, "source_label", "") or article.source),
        "source_rank": int(getattr(article, "source_rank", 0) or 0),
        "match_reason": _format_match_reason(match_reason_raw),
        "match_reason_raw": match_reason_raw,
        "is_synthetic": is_synthetic,
    }


def _looks_synthetic_article(article: NewsArticle) -> bool:
    source = str(getattr(article, "source", "") or "").lower()
    source_url = str(getattr(article, "source_url", "") or "").lower()
    return (
        source.startswith("mock")
        or "fallback" in source
        or source_url.startswith("mock:")
        or source_url.startswith("fallback:")
        or "mock://" in source_url
    )


def _format_match_reason(raw: str) -> str:
    reason = _loads_json_object(raw)
    if not reason:
        return ""
    pieces: list[str] = []
    primary = str(reason.get("primary") or "").strip()
    if primary:
        pieces.append(f"primary={primary}")
    for key, label in [("keyword", "关键词"), ("industry", "产业"), ("alias", "别名")]:
        values = [str(item).strip() for item in reason.get(key, []) if str(item).strip()] if isinstance(reason.get(key), list) else []
        if values:
            pieces.append(f"{label}: {'/'.join(values[:4])}")
    unmatched = [str(item).strip() for item in reason.get("unmatched", []) if str(item).strip()] if isinstance(reason.get("unmatched"), list) else []
    if unmatched and not pieces:
        pieces.append(f"未匹配: {'/'.join(unmatched[:3])}")
    return " | ".join(pieces)


def _add_industry_stat(
    industry_stats: dict[str, dict[str, Any]],
    industry: str,
    score: float,
    source_key: str,
    latest_at: str | None,
) -> None:
    clean = industry.strip()
    if not clean:
        return
    stat = industry_stats.setdefault(
        clean,
        {"industry": clean, "score": 0.0, "mentions": 0, "sources": Counter(), "latest_at": latest_at},
    )
    stat["score"] += score
    stat["mentions"] += 1
    stat["sources"][source_key] += 1
    if latest_at and (not stat["latest_at"] or latest_at > stat["latest_at"]):
        stat["latest_at"] = latest_at


def _add_platform_term(
    platform_terms: dict[str, dict[str, dict[str, Any]]],
    source_key: str,
    term: str,
    score: float,
    industry: str,
) -> None:
    clean = _clean_term(term)
    if not clean:
        return
    bucket = platform_terms[source_key]
    stat = bucket.setdefault(
        clean.lower(),
        {"term": clean, "score": 0.0, "mentions": 0, "industries": Counter()},
    )
    stat["score"] += score
    stat["mentions"] += 1
    if industry and industry != "未映射":
        stat["industries"][industry] += 1


def _format_hot_terms(term_stats: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    max_score = max((float(item["score"]) for item in term_stats.values()), default=1.0)
    rows: list[dict[str, Any]] = []
    for stat in term_stats.values():
        rows.append(
            {
                "term": stat["term"],
                "score": round(float(stat["score"]), 2),
                "intensity": round(min(float(stat["score"]) / max(max_score, 1.0), 1.0), 4),
                "mentions": int(stat["mentions"]),
                "sources": _counter_labels(stat["sources"]),
                "industries": _counter_labels(stat["industries"], limit=5),
                "latest_at": stat["latest_at"],
                "examples": stat["examples"],
            }
        )
    return sorted(rows, key=lambda row: (float(row["score"]), int(row["mentions"])), reverse=True)[:limit]


def _format_hot_industries(
    industry_stats: dict[str, dict[str, Any]],
    hot_terms: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    terms_by_industry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for term in hot_terms:
        for industry in term["industries"]:
            terms_by_industry[str(industry["label"])].append({"term": term["term"], "score": term["score"]})
    max_score = max((float(item["score"]) for item in industry_stats.values()), default=1.0)
    rows: list[dict[str, Any]] = []
    for stat in industry_stats.values():
        industry = str(stat["industry"])
        rows.append(
            {
                "industry": industry,
                "score": round(float(stat["score"]), 2),
                "intensity": round(min(float(stat["score"]) / max(max_score, 1.0), 1.0), 4),
                "mentions": int(stat["mentions"]),
                "sources": _counter_labels(stat["sources"]),
                "top_terms": sorted(terms_by_industry.get(industry, []), key=lambda row: float(row["score"]), reverse=True)[:6],
                "latest_at": stat["latest_at"],
            }
        )
    return sorted(rows, key=lambda row: (float(row["score"]), int(row["mentions"])), reverse=True)[:limit]


def _format_platform_terms(
    platform_terms: dict[str, dict[str, dict[str, Any]]],
    source_counts: Counter[str],
    source_runs: dict[str, DataSourceRun],
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in _format_hot_sources(source_counts, source_runs):
        source_key = str(source["key"])
        terms = []
        for stat in platform_terms.get(source_key, {}).values():
            terms.append(
                {
                    "term": stat["term"],
                    "score": round(float(stat["score"]), 2),
                    "mentions": int(stat["mentions"]),
                    "industries": _counter_labels(stat["industries"], limit=4),
                }
            )
        rows.append(
            {
                **source,
                "terms": sorted(terms, key=lambda row: (float(row["score"]), int(row["mentions"])), reverse=True)[:limit],
            }
        )
    return rows


def _format_hot_sources(source_counts: Counter[str], source_runs: dict[str, DataSourceRun] | None = None) -> list[dict[str, Any]]:
    source_runs = source_runs or {}
    rows: list[dict[str, Any]] = []
    known = {item["key"] for item in HOT_SOURCE_CATALOG}
    for item in HOT_SOURCE_CATALOG:
        key = str(item["key"])
        count = int(source_counts[key])
        run = source_runs.get(key)
        run_total = int(run.rows_total) if run else 0
        run_inserted = int(run.rows_inserted) if run else 0
        run_skipped = int(run.rows_updated) if run else 0
        run_irrelevant = max(run_total - run_inserted - run_skipped, 0)
        connector_status = run.status if run else ("internal_ready" if item["kind"] == "internal" else "pending_connector")
        window_data_status = "active" if count > 0 else ("internal_ready" if item["kind"] == "internal" else "empty")
        rows.append(
            {
                "key": key,
                "label": item["label"],
                "kind": item["kind"],
                "status": _hot_source_status(count=count, kind=str(item["kind"]), run=run),
                "connector_status": connector_status,
                "window_data_status": window_data_status,
                "article_count": count,
                "last_run_status": run.status if run else None,
                "last_error": run.error if run and run.error else "",
                "last_run_at": _iso_datetime(run.finished_at) if run else None,
                "connector_item_count": run_total,
                "last_inserted": run_inserted,
                "last_skipped": run_skipped,
                "last_irrelevant": run_irrelevant,
                "relevance_rate": round((run_inserted + run_skipped) / run_total, 4) if run_total else None,
            }
        )
    for key, count in source_counts.items():
        if key in known:
            continue
        run = source_runs.get(key)
        run_total = int(run.rows_total) if run else 0
        run_inserted = int(run.rows_inserted) if run else 0
        run_skipped = int(run.rows_updated) if run else 0
        run_irrelevant = max(run_total - run_inserted - run_skipped, 0)
        connector_status = run.status if run else "pending_connector"
        window_data_status = "active" if count > 0 else "empty"
        rows.append(
            {
                "key": key,
                "label": HOT_SOURCE_LABELS.get(key, key),
                "kind": "external",
                "status": _hot_source_status(count=int(count), kind="external", run=run),
                "connector_status": connector_status,
                "window_data_status": window_data_status,
                "article_count": int(count),
                "last_run_status": run.status if run else None,
                "last_error": run.error if run and run.error else "",
                "last_run_at": _iso_datetime(run.finished_at) if run else None,
                "connector_item_count": run_total,
                "last_inserted": run_inserted,
                "last_skipped": run_skipped,
                "last_irrelevant": run_irrelevant,
                "relevance_rate": round((run_inserted + run_skipped) / run_total, 4) if run_total else None,
            }
        )
    return rows


def _hot_source_status(*, count: int, kind: str, run: DataSourceRun | None) -> str:
    if kind == "internal":
        return "active" if count > 0 else "internal_ready"
    if run is None:
        return "active" if count > 0 else "pending_connector"
    if run.status == "failed":
        return "error"
    if run.status == "partial":
        return "degraded"
    if count > 0:
        return "active"
    if run.status in {"success", "empty"}:
        return "connected_empty"
    return run.status or "pending_connector"


def _latest_hot_source_runs(session: Session) -> dict[str, DataSourceRun]:
    rows = session.scalars(
        select(DataSourceRun)
        .where(DataSourceRun.job_name.like("hot_terms_%"))
        .order_by(DataSourceRun.finished_at.desc(), DataSourceRun.started_at.desc())
    ).all()
    latest: dict[str, DataSourceRun] = {}
    for row in rows:
        key = row.effective_source or row.job_name.removeprefix("hot_terms_")
        if key not in latest:
            latest[key] = row
    return latest


def _counter_labels(counter: Counter[str], limit: int = 6) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": HOT_SOURCE_LABELS.get(key, key),
            "count": int(count),
        }
        for key, count in counter.most_common(limit)
    ]


def _latest_snapshot_date(latest_heat_date: Any, latest_article_dt: datetime | None) -> str | None:
    candidates: list[str] = []
    if latest_heat_date:
        candidates.append(latest_heat_date.isoformat())
    if latest_article_dt:
        candidates.append(latest_article_dt.date().isoformat())
    return max(candidates) if candidates else None


def _data_lag_days(latest_date: str | None) -> int | None:
    if not latest_date:
        return None
    try:
        parsed = datetime.fromisoformat(latest_date).date()
    except ValueError:
        return None
    return max((datetime.now(timezone.utc).date() - parsed).days, 0)


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
