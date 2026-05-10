from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Industry, IndustryHeat, IndustryKeyword, NewsArticle, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.market_meta import market_label
from app.pipeline.industry_mapping_job import industry_mapping_summary

router = APIRouter(prefix="/api/industries", tags=["industry"])


@router.get("/mapping-summary")
def mapping_summary(
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    market_key = _normalize_market_filter(market)
    return industry_mapping_summary(session, markets=(market_key,) if market_key else None)


@router.get("/radar")
def industry_radar(
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    latest_date = session.scalars(select(IndustryHeat.trade_date).order_by(IndustryHeat.trade_date.desc()).limit(1)).first()
    latest_signal_date = _latest_signal_date(session) or latest_date
    market_key = _normalize_market_filter(market)
    industries = {item.id: item for item in session.scalars(select(Industry)).all()}
    keywords_by_industry_id = _keywords_by_industry_id(session)
    market_stats = _market_industry_stats(session, latest_signal_date, market_key)
    maxima = _market_stats_maxima(market_stats)
    heats = []
    if latest_date is not None:
        heats = session.scalars(
            select(IndustryHeat).where(IndustryHeat.trade_date == latest_date).order_by(IndustryHeat.heat_score.desc())
        ).all()
    heats_by_industry_id = {heat.industry_id: heat for heat in heats}
    rows: list[dict[str, object]] = []
    for industry_id, industry in industries.items():
        heat = heats_by_industry_id.get(industry_id)
        industry_name = industry.name
        stats = market_stats.get(industry_name, _empty_market_stats())
        news_heat_score = float(heat.heat_score) if heat else 0.0
        structure_heat_score = _structure_heat_score(stats, maxima)
        composite_heat_score = _composite_heat_score(
            news_heat_score,
            structure_heat_score,
            stats,
            maxima,
            market_key,
        )
        evidence_status = _evidence_status(news_heat_score, structure_heat_score, stats)
        heat_reason = _heat_reason(heat, stats, composite_heat_score, market_key)
        explanation = _radar_explanation(heat, stats, composite_heat_score, heat_reason, market_key)
        evidence_source_mix = _evidence_source_mix(session, industry_name, set(keywords_by_industry_id.get(industry_id, [])))
        rows.append(
            {
                "industry_id": industry_id,
                "name": industry_name,
                "trade_date": heat.trade_date.isoformat() if heat else latest_date.isoformat() if latest_date else None,
                "market_signal_date": latest_signal_date.isoformat() if latest_signal_date else None,
                "heat_score": composite_heat_score,
                "global_heat_score": news_heat_score,
                "news_heat_score": news_heat_score,
                "structure_heat_score": structure_heat_score,
                "evidence_status": evidence_status,
                "heat_1d": heat.heat_1d if heat else 0.0,
                "heat_7d": heat.heat_7d if heat else 0.0,
                "heat_30d": heat.heat_30d if heat else 0.0,
                "heat_change_7d": heat.heat_change_7d if heat else 0.0,
                "heat_change_30d": heat.heat_change_30d if heat else 0.0,
                "market": market_key or "ALL",
                "market_label": market_label(market_key) if market_key else "全市场",
                "related_stock_count": stats["related_stock_count"],
                "scored_stock_count": stats["scored_stock_count"],
                "watch_stock_count": stats["watch_stock_count"],
                "trend_stock_count": stats["trend_stock_count"],
                "bullish_stock_count": stats["bullish_stock_count"],
                "breakout_stock_count": stats["breakout_stock_count"],
                "trend_breadth": stats["trend_breadth"],
                "breakout_breadth": stats["breakout_breadth"],
                "average_final_score": stats["average_final_score"],
                "average_stock_trend_score": stats["average_stock_trend_score"],
                "average_signal_trend_score": stats["average_signal_trend_score"],
                "average_volume_expansion_ratio": stats["average_volume_expansion_ratio"],
                "top_keywords": _loads_json_list(heat.top_keywords) if heat else [],
                "top_articles": _loads_json_list(heat.top_articles) if heat else [],
                "evidence_source_mix": evidence_source_mix,
                "heat_status": "active" if composite_heat_score > 0 else "zero",
                "zero_heat_reason": heat_reason,
                "explanation": explanation,
            }
        )
    orphan_heats = [heat for heat in heats if heat.industry_id not in industries]
    for heat in orphan_heats:
        industry_name = f"industry-{heat.industry_id}"
        stats = market_stats.get(industry_name, _empty_market_stats())
        structure_heat_score = _structure_heat_score(stats, maxima)
        composite_heat_score = _composite_heat_score(
            heat.heat_score,
            structure_heat_score,
            stats,
            maxima,
            market_key,
        )
        evidence_status = _evidence_status(heat.heat_score, structure_heat_score, stats)
        heat_reason = _heat_reason(heat, stats, composite_heat_score, market_key)
        zero_reason = heat_reason or ("主行业表缺失该行业，仅保留历史热度行。" if composite_heat_score <= 0 else "")
        rows.append(
            {
                "industry_id": heat.industry_id,
                "name": industry_name,
                "trade_date": heat.trade_date.isoformat(),
                "market_signal_date": latest_signal_date.isoformat() if latest_signal_date else None,
                "heat_score": composite_heat_score,
                "global_heat_score": heat.heat_score,
                "news_heat_score": heat.heat_score,
                "structure_heat_score": structure_heat_score,
                "evidence_status": evidence_status,
                "heat_1d": heat.heat_1d,
                "heat_7d": heat.heat_7d,
                "heat_30d": heat.heat_30d,
                "heat_change_7d": heat.heat_change_7d,
                "heat_change_30d": heat.heat_change_30d,
                "market": market_key or "ALL",
                "market_label": market_label(market_key) if market_key else "全市场",
                "related_stock_count": stats["related_stock_count"],
                "scored_stock_count": stats["scored_stock_count"],
                "watch_stock_count": stats["watch_stock_count"],
                "trend_stock_count": stats["trend_stock_count"],
                "bullish_stock_count": stats["bullish_stock_count"],
                "breakout_stock_count": stats["breakout_stock_count"],
                "trend_breadth": stats["trend_breadth"],
                "breakout_breadth": stats["breakout_breadth"],
                "average_final_score": stats["average_final_score"],
                "average_stock_trend_score": stats["average_stock_trend_score"],
                "average_signal_trend_score": stats["average_signal_trend_score"],
                "average_volume_expansion_ratio": stats["average_volume_expansion_ratio"],
                "top_keywords": _loads_json_list(heat.top_keywords),
                "top_articles": _loads_json_list(heat.top_articles),
                "evidence_source_mix": _evidence_source_mix(session, industry_name, set()),
                "heat_status": "active" if composite_heat_score > 0 else "zero",
                "zero_heat_reason": zero_reason,
                "explanation": _radar_explanation(heat, stats, composite_heat_score, heat_reason, market_key),
            }
        )
    return sorted(rows, key=lambda row: float(row["heat_score"]), reverse=True)


@router.get("/timeline")
def industry_timeline(limit: int = Query(default=30, ge=1, le=180), session: Session = Depends(get_session)) -> dict[str, object]:
    trade_dates = session.scalars(
        select(IndustryHeat.trade_date).distinct().order_by(IndustryHeat.trade_date.desc()).limit(limit + 1)
    ).all()
    if not trade_dates:
        return {"latest": None, "timeline": []}

    industries = {item.id: item for item in session.scalars(select(Industry)).all()}
    heats_by_date: dict[object, list[IndustryHeat]] = {}
    for trade_date in trade_dates:
        heats_by_date[trade_date] = list(
            session.scalars(
                select(IndustryHeat).where(IndustryHeat.trade_date == trade_date).order_by(IndustryHeat.heat_score.desc())
            ).all()
        )

    timeline: list[dict[str, object]] = []
    for index, trade_date in enumerate(trade_dates[:limit]):
        previous_date = trade_dates[index + 1] if index + 1 < len(trade_dates) else None
        current_rows = heats_by_date.get(trade_date, [])
        previous_rows = {row.industry_id: row for row in heats_by_date.get(previous_date, [])} if previous_date else {}
        rows = [
            _timeline_row(row, industries.get(row.industry_id), previous_rows.get(row.industry_id))
            for row in current_rows
        ]
        rising = sorted(
            [row for row in rows if row["heat_score_delta"] is not None and row["heat_score_delta"] > 0],
            key=lambda row: row["heat_score_delta"],
            reverse=True,
        )
        cooling = sorted(
            [row for row in rows if row["heat_score_delta"] is not None and row["heat_score_delta"] < 0],
            key=lambda row: row["heat_score_delta"],
        )
        total_heat = round(sum(float(row["heat_score"]) for row in rows), 2)
        timeline.append(
            {
                "trade_date": trade_date.isoformat(),
                "previous_date": previous_date.isoformat() if previous_date else None,
                "summary": {
                    "industry_count": len(rows),
                    "hot_industry_count": sum(1 for row in rows if float(row["heat_score"]) >= 20),
                    "rising_count": len(rising),
                    "cooling_count": len(cooling),
                    "total_heat_score": total_heat,
                    "average_heat_score": round(total_heat / max(len(rows), 1), 2),
                },
                "top_industries": rows[:10],
                "rising_industries": rising[:10],
                "cooling_industries": cooling[:10],
                "industries": rows,
            }
        )

    return {"latest": timeline[0] if timeline else None, "timeline": timeline}


@router.get("/{industry_id}")
def industry_detail(
    industry_id: int,
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    history_limit: int = Query(default=60, ge=1, le=240),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    industry = session.get(Industry, industry_id)
    if industry is None:
        raise HTTPException(status_code=404, detail="industry not found")

    keywords = session.scalars(
        select(IndustryKeyword).where(IndustryKeyword.industry_id == industry_id, IndustryKeyword.is_active.is_(True))
    ).all()
    keyword_values = [row.keyword for row in keywords]
    heat_rows = list(
        session.scalars(
            select(IndustryHeat)
            .where(IndustryHeat.industry_id == industry_id)
            .order_by(IndustryHeat.trade_date.desc())
            .limit(history_limit)
        ).all()
    )
    heat_history = _heat_history_payload(heat_rows, industry)
    latest_heat = heat_history[0] if heat_history else None

    market_key = _normalize_market_filter(market)
    related_stocks = _related_stock_rows(session, industry, market_key)
    recent_articles = _related_articles(session, industry.name, set(keyword_values))

    return {
        "industry": {
            "id": industry.id,
            "name": industry.name,
            "description": industry.description,
            "keywords": keyword_values,
        },
        "latest_heat": latest_heat,
        "heat_history": heat_history,
        "summary": {
            "market": market_key or "ALL",
            "market_label": market_label(market_key) if market_key else "全市场",
            "related_stock_count": len(related_stocks),
            "watch_stock_count": sum(1 for row in related_stocks if row["rating"] in {"强观察", "观察"}),
            "strong_watch_count": sum(1 for row in related_stocks if row["rating"] == "强观察"),
            "recent_article_count": len(recent_articles),
        },
        "related_stocks": related_stocks,
        "recent_articles": recent_articles,
    }


def _timeline_row(heat: IndustryHeat, industry: Industry | None, previous: IndustryHeat | None) -> dict[str, object]:
    heat_delta = None if previous is None else round(heat.heat_score - previous.heat_score, 2)
    heat_7d_delta = None if previous is None else round(heat.heat_7d - previous.heat_7d, 2)
    heat_30d_delta = None if previous is None else round(heat.heat_30d - previous.heat_30d, 2)
    return {
        "industry_id": heat.industry_id,
        "name": industry.name if industry else f"industry-{heat.industry_id}",
        "trade_date": heat.trade_date.isoformat(),
        "heat_score": heat.heat_score,
        "heat_score_delta": heat_delta,
        "heat_1d": heat.heat_1d,
        "heat_7d": heat.heat_7d,
        "heat_7d_delta": heat_7d_delta,
        "heat_30d": heat.heat_30d,
        "heat_30d_delta": heat_30d_delta,
        "heat_change_7d": heat.heat_change_7d,
        "heat_change_30d": heat.heat_change_30d,
        "top_keywords": _loads_json_list(heat.top_keywords),
        "top_articles": _loads_json_list(heat.top_articles),
        "explanation": heat.explanation,
    }


def _normalize_market_filter(market: str | None) -> str | None:
    if not market:
        return None
    normalized = market.upper()
    return normalized if normalized in {"A", "US", "HK"} else None


def _empty_market_stats() -> dict[str, float]:
    return {
        "related_stock_count": 0,
        "scored_stock_count": 0,
        "watch_stock_count": 0,
        "trend_stock_count": 0,
        "bullish_stock_count": 0,
        "breakout_stock_count": 0,
        "trend_breadth": 0.0,
        "breakout_breadth": 0.0,
        "average_final_score": 0.0,
        "average_stock_trend_score": 0.0,
        "average_signal_trend_score": 0.0,
        "average_volume_expansion_ratio": 0.0,
        "is_unclassified": 0,
    }


def _latest_signal_date(session: Session):
    score_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    trend_date = session.scalars(select(TrendSignal.trade_date).order_by(TrendSignal.trade_date.desc()).limit(1)).first()
    return max([item for item in [score_date, trend_date] if item is not None], default=None)


def _keywords_by_industry_id(session: Session) -> dict[int, list[str]]:
    rows = session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True))).all()
    keywords: dict[int, list[str]] = {}
    for row in rows:
        keywords.setdefault(row.industry_id, []).append(row.keyword)
    return keywords


def _market_industry_stats(session: Session, trade_date, market: str | None) -> dict[str, dict[str, float]]:
    filters = [Stock.is_active.is_(True), Stock.listing_status == "listed", Stock.asset_type == "equity"]
    if market:
        filters.append(Stock.market == market)

    stats: dict[str, dict[str, float]] = {}
    related_rows = session.execute(
        select(Stock.industry_level1, func.count(Stock.id)).where(*filters).group_by(Stock.industry_level1)
    ).all()
    for industry_name, count in related_rows:
        key = industry_name or "未分类"
        stats[key] = _empty_market_stats()
        stats[key]["is_unclassified"] = 1 if _is_unclassified_industry(key) else 0
        stats[key]["related_stock_count"] = int(count or 0)

    if trade_date is not None:
        scored_rows = session.execute(
            select(
                Stock.industry_level1,
                func.count(StockScore.id),
                func.avg(StockScore.final_score),
                func.avg(StockScore.trend_score),
            )
            .join(StockScore, StockScore.stock_code == Stock.code)
            .where(*filters, StockScore.trade_date == trade_date)
            .group_by(Stock.industry_level1)
        ).all()
        for industry_name, count, average_final_score, average_stock_trend_score in scored_rows:
            key = industry_name or "未分类"
            row = stats.setdefault(key, _empty_market_stats())
            row["is_unclassified"] = 1 if _is_unclassified_industry(key) else 0
            row["scored_stock_count"] = int(count or 0)
            row["average_final_score"] = round(float(average_final_score or 0.0), 2)
            row["average_stock_trend_score"] = round(float(average_stock_trend_score or 0.0), 2)

        watch_rows = session.execute(
            select(Stock.industry_level1, func.count(StockScore.id))
            .join(StockScore, StockScore.stock_code == Stock.code)
            .where(*filters, StockScore.trade_date == trade_date, StockScore.rating.in_(["强观察", "观察"]))
            .group_by(Stock.industry_level1)
        ).all()
        for industry_name, count in watch_rows:
            key = industry_name or "未分类"
            row = stats.setdefault(key, _empty_market_stats())
            row["is_unclassified"] = 1 if _is_unclassified_industry(key) else 0
            row["watch_stock_count"] = int(count or 0)

        trend_rows = session.execute(
            select(
                Stock.industry_level1,
                TrendSignal.is_ma_bullish,
                TrendSignal.is_breakout_120d,
                TrendSignal.is_breakout_250d,
                TrendSignal.trend_score,
                TrendSignal.volume_expansion_ratio,
            )
            .join(TrendSignal, TrendSignal.stock_code == Stock.code)
            .where(*filters, TrendSignal.trade_date == trade_date)
        ).all()
        trend_strength_totals: dict[str, dict[str, float]] = {}
        for (
            industry_name,
            is_ma_bullish,
            is_breakout_120d,
            is_breakout_250d,
            signal_trend_score,
            volume_expansion_ratio,
        ) in trend_rows:
            key = industry_name or "未分类"
            row = stats.setdefault(key, _empty_market_stats())
            row["is_unclassified"] = 1 if _is_unclassified_industry(key) else 0
            row["trend_stock_count"] += 1
            totals = trend_strength_totals.setdefault(key, {"trend_score": 0.0, "volume_expansion": 0.0})
            totals["trend_score"] += float(signal_trend_score or 0.0)
            totals["volume_expansion"] += float(volume_expansion_ratio or 0.0)
            if is_ma_bullish:
                row["bullish_stock_count"] += 1
            if is_breakout_120d or is_breakout_250d:
                row["breakout_stock_count"] += 1

        for key, totals in trend_strength_totals.items():
            row = stats[key]
            trend_count = max(float(row["trend_stock_count"]), 1.0)
            row["average_signal_trend_score"] = round(totals["trend_score"] / trend_count, 2)
            row["average_volume_expansion_ratio"] = round(totals["volume_expansion"] / trend_count, 2)

    for row in stats.values():
        trend_count = max(float(row["trend_stock_count"]), 1.0)
        row["trend_breadth"] = round(float(row["bullish_stock_count"]) / trend_count, 4)
        row["breakout_breadth"] = round(float(row["breakout_stock_count"]) / trend_count, 4)
    return stats


def _market_stats_maxima(market_stats: dict[str, dict[str, float]]) -> dict[str, float]:
    classified_rows = [row for row in market_stats.values() if not row.get("is_unclassified")]
    rows = classified_rows or list(market_stats.values())
    return {
        "related_stock_count": max((row["related_stock_count"] for row in rows), default=0),
        "scored_stock_count": max((row["scored_stock_count"] for row in rows), default=0),
        "watch_stock_count": max((row["watch_stock_count"] for row in rows), default=0),
        "trend_stock_count": max((row["trend_stock_count"] for row in rows), default=0),
        "breakout_stock_count": max((row["breakout_stock_count"] for row in rows), default=0),
        "average_final_score": max((row["average_final_score"] for row in rows), default=0.0),
        "average_stock_trend_score": max((row["average_stock_trend_score"] for row in rows), default=0.0),
        "average_signal_trend_score": max((row["average_signal_trend_score"] for row in rows), default=0.0),
        "average_volume_expansion_ratio": max((row["average_volume_expansion_ratio"] for row in rows), default=0.0),
    }


def _composite_heat_score(
    news_heat_score: float,
    structure_heat_score: float,
    stats: dict[str, float],
    maxima: dict[str, float],
    market: str | None,
) -> float:
    related_count = float(stats["related_stock_count"])
    if market and related_count <= 0:
        return 0.0

    related_factor = min(1.0, related_count / max(float(maxima["related_stock_count"]), 1.0))
    market_news_factor = (0.45 + related_factor * 0.55) if market else 1.0
    composite = (
        min(max(float(news_heat_score), 0.0), 30.0) / 30.0 * 11.0 * market_news_factor
        + min(max(float(structure_heat_score), 0.0), 30.0) / 30.0 * 19.0
    )
    if stats.get("is_unclassified"):
        composite *= 0.35
    if composite <= 0:
        return 0.0
    return round(min(30.0, composite), 2)


def _structure_heat_score(stats: dict[str, float], maxima: dict[str, float]) -> float:
    related_factor = min(1.0, float(stats["related_stock_count"]) / max(float(maxima["related_stock_count"]), 1.0))
    scored_factor = min(1.0, float(stats["scored_stock_count"]) / max(float(maxima["scored_stock_count"]), 1.0))
    watch_factor = min(1.0, float(stats["watch_stock_count"]) / max(float(maxima["watch_stock_count"]), 1.0))
    trend_factor = min(1.0, float(stats["trend_stock_count"]) / max(float(maxima["trend_stock_count"]), 1.0))
    breakout_factor = min(1.0, float(stats["breakout_stock_count"]) / max(float(maxima["breakout_stock_count"]), 1.0))
    final_score_factor = float(stats["average_final_score"]) / max(float(maxima["average_final_score"]), 100.0)
    stock_trend_score_factor = float(stats["average_stock_trend_score"]) / max(float(maxima["average_stock_trend_score"]), 30.0)
    signal_trend_score_factor = float(stats["average_signal_trend_score"]) / max(float(maxima["average_signal_trend_score"]), 30.0)
    volume_factor = min(
        float(stats["average_volume_expansion_ratio"]) / max(float(maxima["average_volume_expansion_ratio"]), 1.5),
        1.0,
    )
    strength_score = (
        final_score_factor * 3.0
        + stock_trend_score_factor * 2.0
        + signal_trend_score_factor * 2.5
        + volume_factor * 1.5
    )
    score = (
        scored_factor * 6.0
        + watch_factor * 6.0
        + float(stats["trend_breadth"]) * trend_factor * 8.0
        + float(stats["breakout_breadth"]) * breakout_factor * 5.0
        + strength_score
    )
    score *= 0.85 + related_factor * 0.15
    if stats.get("is_unclassified"):
        score *= 0.35
    if score <= 0:
        return 0.0
    return round(min(30.0, score), 2)


def _is_unclassified_industry(industry_name: str | None) -> bool:
    normalized = (industry_name or "").strip()
    return normalized in {"", "未分类", "其他", "其它", "unknown", "Unknown", "UNKNOWN"}


def _evidence_status(news_heat_score: float, structure_heat_score: float, stats: dict[str, float]) -> str:
    if float(news_heat_score or 0.0) > 0:
        return "news_active"
    if float(structure_heat_score or 0.0) > 0:
        return "structure_active"
    if stats["related_stock_count"] > 0:
        return "mapped_only"
    return "no_evidence"


def _heat_reason(heat: IndustryHeat | None, stats: dict[str, float], heat_score: float, market: str | None) -> str:
    if heat_score > 0:
        if heat is None or float(heat.heat_score or 0.0) <= 0:
            return f"资讯热度为0；综合热度来自{_source_summary(stats)}。"
        return ""
    if market and stats["related_stock_count"] <= 0:
        return f"当前{market_label(market)}范围内没有该行业已上市股票映射，市场口径热度显示为0。"
    if stats["related_stock_count"] > 0 and not _has_structure_evidence(stats):
        return "综合热度为0：当前仅有股票映射，暂无评分、趋势、观察池或资讯证据。"
    if heat is None:
        return "综合热度为0：当前最新交易日没有该行业资讯热度记录，且无股票/趋势/观察池证据。"
    if float(heat.heat_score or 0.0) <= 0:
        return heat.explanation or "综合热度为0：近30日未匹配到有效资讯证据，且无股票/趋势/观察池证据。"
    return "综合热度为0：缺少当前市场的关联股票、评分、趋势和观察池证据。"


def _has_structure_evidence(stats: dict[str, float]) -> bool:
    return any(
        float(stats[key]) > 0
        for key in [
            "scored_stock_count",
            "watch_stock_count",
            "trend_stock_count",
            "bullish_stock_count",
            "breakout_stock_count",
        ]
    )


def _source_summary(stats: dict[str, float]) -> str:
    sources: list[str] = []
    if stats["scored_stock_count"]:
        sources.append(f"{int(stats['scored_stock_count'])}只已评分股票")
    if stats["watch_stock_count"]:
        sources.append(f"{int(stats['watch_stock_count'])}只观察池股票")
    if stats["trend_stock_count"]:
        sources.append(
            f"趋势覆盖{int(stats['trend_stock_count'])}只、趋势宽度{float(stats['trend_breadth']):.0%}"
        )
    if stats["breakout_stock_count"]:
        sources.append(f"{int(stats['breakout_stock_count'])}只突破股票")
    if stats["average_final_score"]:
        sources.append(f"平均综合评分{float(stats['average_final_score']):.1f}")
    if stats["average_signal_trend_score"]:
        sources.append(f"平均趋势分{float(stats['average_signal_trend_score']):.1f}")
    if stats["average_volume_expansion_ratio"]:
        sources.append(f"平均量能放大{float(stats['average_volume_expansion_ratio']):.2f}倍")
    if stats["related_stock_count"]:
        sources.append(f"{int(stats['related_stock_count'])}只关联股票")
    return "、".join(sources) if sources else "暂无结构化证据"


def _radar_explanation(
    heat: IndustryHeat | None,
    stats: dict[str, float],
    heat_score: float,
    heat_reason: str,
    market: str | None,
) -> str:
    if heat_score <= 0:
        return heat_reason
    source_summary = _source_summary(stats)
    scope = market_label(market) if market else "全市场"
    if heat is not None and float(heat.heat_score or 0.0) > 0:
        base = heat.explanation
        return f"{base} 综合热度按{scope}口径叠加{source_summary}。"
    return f"资讯热度为0；综合热度按{scope}口径来自{source_summary}。"


def _heat_history_payload(heat_rows_desc: list[IndustryHeat], industry: Industry) -> list[dict[str, object]]:
    rows_asc = list(reversed(heat_rows_desc))
    previous_by_date: dict[object, IndustryHeat | None] = {}
    previous: IndustryHeat | None = None
    for row in rows_asc:
        previous_by_date[row.trade_date] = previous
        previous = row
    return [_timeline_row(row, industry, previous_by_date[row.trade_date]) for row in heat_rows_desc]


def _related_stock_rows(session: Session, industry: Industry, market: str | None = None) -> list[dict[str, object]]:
    query = select(Stock).where(Stock.industry_level1 == industry.name, Stock.is_active.is_(True))
    if market:
        query = query.where(Stock.market == market)
    stocks = list(session.scalars(query).all())
    if not stocks:
        return []
    stock_codes = [stock.code for stock in stocks]
    latest_date = session.scalars(
        select(StockScore.trade_date)
        .where(StockScore.stock_code.in_(stock_codes))
        .order_by(StockScore.trade_date.desc())
        .limit(1)
    ).first()
    score_by_code = {}
    trend_by_code = {}
    if latest_date is not None:
        score_by_code = {
            row.stock_code: row
            for row in session.scalars(
                select(StockScore).where(StockScore.trade_date == latest_date, StockScore.stock_code.in_(stock_codes))
            ).all()
        }
        trend_by_code = {
            row.stock_code: row
            for row in session.scalars(
                select(TrendSignal).where(TrendSignal.trade_date == latest_date, TrendSignal.stock_code.in_(stock_codes))
            ).all()
        }

    rows: list[dict[str, object]] = []
    for stock in stocks:
        score = score_by_code.get(stock.code)
        trend = trend_by_code.get(stock.code)
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "board": stock.board,
                "exchange": stock.exchange,
                "industry_level2": stock.industry_level2,
                "concepts": _loads_json_list(stock.concepts),
                "market_cap": stock.market_cap,
                "float_market_cap": stock.float_market_cap,
                "trade_date": latest_date.isoformat() if latest_date else None,
                "final_score": score.final_score if score else None,
                "rating": score.rating if score else None,
                "industry_score": score.industry_score if score else None,
                "company_score": score.company_score if score else None,
                "trend_score": score.trend_score if score else None,
                "catalyst_score": score.catalyst_score if score else None,
                "risk_penalty": score.risk_penalty if score else None,
                "relative_strength_rank": trend.relative_strength_rank if trend else None,
                "is_ma_bullish": trend.is_ma_bullish if trend else None,
                "is_breakout_120d": trend.is_breakout_120d if trend else None,
                "is_breakout_250d": trend.is_breakout_250d if trend else None,
            }
        )
    return sorted(rows, key=lambda row: float(row["final_score"] or 0), reverse=True)


def _related_articles(session: Session, industry_name: str, keywords: set[str], limit: int = 12) -> list[dict[str, object]]:
    articles = session.scalars(select(NewsArticle).order_by(NewsArticle.published_at.desc()).limit(200)).all()
    rows: list[dict[str, object]] = []
    for article in articles:
        article_industries = {str(item) for item in _loads_json_list(article.related_industries)}
        article_keywords = {str(item) for item in _loads_json_list(article.matched_keywords)}
        if industry_name not in article_industries and not (keywords & article_keywords):
            continue
        rows.append(
            {
                "title": article.title,
                "summary": article.summary,
                "source": article.source,
                "source_kind": getattr(article, "source_kind", "mock"),
                "source_confidence": round(float(getattr(article, "source_confidence", 0.3) or 0.0), 2),
                "source_url": article.source_url,
                "published_at": article.published_at.isoformat(),
                "matched_keywords": list(article_keywords),
                "related_stocks": _loads_json_list(article.related_stocks),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _evidence_source_mix(session: Session, industry_name: str, keywords: set[str], limit: int = 200) -> dict[str, object]:
    articles = session.scalars(select(NewsArticle).order_by(NewsArticle.published_at.desc()).limit(limit)).all()
    counts: dict[str, int] = {}
    confidence_total = 0.0
    matched_count = 0
    for article in articles:
        article_industries = {str(item) for item in _loads_json_list(article.related_industries)}
        article_keywords = {str(item) for item in _loads_json_list(article.matched_keywords)}
        if industry_name not in article_industries and not (keywords & article_keywords):
            continue
        kind = str(getattr(article, "source_kind", "mock") or "mock")
        counts[kind] = counts.get(kind, 0) + 1
        confidence_total += float(getattr(article, "source_confidence", 0.3) or 0.0)
        matched_count += 1
    real_count = sum(count for kind, count in counts.items() if kind != "mock")
    coverage_status = "real_news" if real_count else "mock_only" if matched_count else "none"
    return {
        "counts": counts,
        "matched_article_count": matched_count,
        "real_source_count": real_count,
        "average_source_confidence": round(confidence_total / matched_count, 2) if matched_count else 0.0,
        "coverage_status": coverage_status,
    }


def _loads_json_list(raw: str) -> list[object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
