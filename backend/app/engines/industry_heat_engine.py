from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class IndustryHeatMetrics:
    industry_id: int
    trade_date: date
    heat_1d: float
    heat_7d: float
    heat_30d: float
    heat_change_7d: float
    heat_change_30d: float
    top_keywords: list[str]
    top_articles: list[str]
    heat_score: float
    explanation: str


def _json_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _published_date(article: Any) -> date:
    value = article["published_at"] if isinstance(article, dict) else article.published_at
    if isinstance(value, datetime):
        return value.date()
    return value


def _field(obj: Any, field: str) -> Any:
    return obj[field] if isinstance(obj, dict) else getattr(obj, field)


def _optional_field(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _source_kind(article: Any) -> str:
    source = str(_optional_field(article, "source", "mock") or "mock")
    return str(_optional_field(article, "source_kind", None) or ("mock" if source == "mock" else "news"))


def _source_confidence(article: Any) -> float:
    try:
        confidence = float(_optional_field(article, "source_confidence"))
    except (AttributeError, KeyError, TypeError, ValueError):
        confidence = {"mock": 0.3, "rss": 0.8, "news": 0.9}.get(_source_kind(article), 0.6)
    return max(0.0, min(1.0, confidence))


def _source_weight(article: Any) -> float:
    kind_weight = {"mock": 0.45, "rss": 0.85, "news": 0.95}.get(_source_kind(article), 0.65)
    return kind_weight * _source_confidence(article)


def calculate_industry_heat(
    industries: list[Any],
    keywords_by_industry: dict[int, list[Any]],
    articles: list[Any],
    trade_date: date,
) -> list[IndustryHeatMetrics]:
    drafts: list[dict[str, Any]] = []
    for industry in industries:
        industry_id = int(_field(industry, "id"))
        keyword_rows = keywords_by_industry.get(industry_id, [])
        keyword_weights = {str(_field(row, "keyword")): float(_field(row, "weight")) for row in keyword_rows}
        if not keyword_weights:
            drafts.append(
                {
                    "industry_id": industry_id,
                    "heat_1d": 0.0,
                    "heat_7d": 0.0,
                    "heat_30d": 0.0,
                    "heat_change_7d": 0.0,
                    "heat_change_30d": 0.0,
                    "top_keywords": [],
                    "top_articles": [],
                    "raw_score": 0.0,
                    "explanation": "资讯热度为0：行业未配置有效关键词，无法匹配资讯证据。",
                }
            )
            continue

        daily_scores: dict[int, float] = {1: 0.0, 7: 0.0, 30: 0.0}
        previous_7 = 0.0
        previous_30 = 0.0
        keyword_counter: Counter[str] = Counter()
        article_titles: list[str] = []
        source_counter: Counter[str] = Counter()
        matched_article_count = 0

        for article in articles:
            pub_date = _published_date(article)
            days_ago = (trade_date - pub_date).days
            if days_ago < 0:
                continue
            matched = set(_json_list(_field(article, "matched_keywords")))
            score = sum(weight for keyword, weight in keyword_weights.items() if keyword in matched)
            if score <= 0:
                continue
            score *= _source_weight(article)
            matched_article_count += 1
            source_counter[_source_kind(article)] += 1
            for keyword in matched:
                if keyword in keyword_weights:
                    keyword_counter[keyword] += 1
            if days_ago <= 0:
                daily_scores[1] += score
            if days_ago < 7:
                daily_scores[7] += score
                article_titles.append(str(_field(article, "title")))
            elif days_ago < 14:
                previous_7 += score
            if days_ago < 30:
                daily_scores[30] += score
            elif days_ago < 60:
                previous_30 += score

        heat_1d = daily_scores[1]
        heat_7d = daily_scores[7]
        heat_30d = daily_scores[30]
        heat_change_7d = (heat_7d - previous_7) / max(previous_7, 1.0)
        heat_change_30d = (heat_30d - previous_30) / max(previous_30, 1.0)
        top_keywords = [keyword for keyword, _ in keyword_counter.most_common(6)]
        top_articles = article_titles[:5]
        raw_score = (
            heat_1d * 2.4
            + heat_7d * 0.85
            + heat_30d * 0.18
            + max(heat_change_7d, 0) * 2.2
            + max(heat_change_30d, 0) * 0.8
            + len(top_keywords) * 0.35
        )
        real_source_count = sum(count for kind, count in source_counter.items() if kind != "mock")
        coverage_confidence = min(1.0, matched_article_count / 3)
        if matched_article_count > 0 and real_source_count == 0:
            coverage_confidence = min(coverage_confidence, 0.55)
        raw_score *= coverage_confidence
        source_summary = "、".join(f"{kind}:{count}" for kind, count in sorted(source_counter.items())) or "none"
        explanation = (
            f"近1日资讯热度{heat_1d:.1f}，近7日资讯热度{heat_7d:.1f}，"
            f"7日变化{heat_change_7d:.1%}，核心关键词：{', '.join(top_keywords) or '暂无'}。"
            f"证据来源：{source_summary}，资讯覆盖置信度{coverage_confidence:.0%}。"
        )
        if raw_score <= 0:
            explanation = f"资讯热度为0：近30日未匹配到有效资讯证据。{explanation}"
        elif coverage_confidence < 0.6:
            explanation = f"资讯覆盖不足，热度已降权。{explanation}"
        drafts.append(
            {
                "industry_id": industry_id,
                "heat_1d": heat_1d,
                "heat_7d": heat_7d,
                "heat_30d": heat_30d,
                "heat_change_7d": heat_change_7d,
                "heat_change_30d": heat_change_30d,
                "top_keywords": top_keywords,
                "top_articles": top_articles,
                "raw_score": raw_score,
                "explanation": explanation,
            }
        )

    max_raw_score = max((float(row["raw_score"]) for row in drafts), default=0.0)
    metrics: list[IndustryHeatMetrics] = []
    for draft in drafts:
        raw_score = float(draft["raw_score"])
        heat_score = 0.0 if max_raw_score <= 0 else min(30.0, raw_score / max_raw_score * 30.0)
        metrics.append(
            IndustryHeatMetrics(
                industry_id=int(draft["industry_id"]),
                trade_date=trade_date,
                heat_1d=round(float(draft["heat_1d"]), 4),
                heat_7d=round(float(draft["heat_7d"]), 4),
                heat_30d=round(float(draft["heat_30d"]), 4),
                heat_change_7d=round(float(draft["heat_change_7d"]), 6),
                heat_change_30d=round(float(draft["heat_change_30d"]), 6),
                top_keywords=list(draft["top_keywords"]),
                top_articles=list(draft["top_articles"]),
                heat_score=round(heat_score, 2),
                explanation=str(draft["explanation"]),
            )
        )
    return metrics
