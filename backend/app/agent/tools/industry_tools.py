from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Industry, IndustryChainNode, IndustryHeat, IndustryKeyword, Stock, StockScore, TrendSignal
from app.services.stock_resolver import resolve_stock


def get_industry_mapping(session: Session, symbol_or_keyword: str | None) -> dict[str, Any]:
    value = (symbol_or_keyword or "").strip()
    stock = resolve_stock(session, value)
    if stock is not None:
        return {
            "status": "ok",
            "code": stock.code,
            "name": stock.name,
            "industry": stock.industry_level1,
            "industry_level2": stock.industry_level2,
            "concepts": _loads_list(stock.concepts),
            "reason": "来自 stock 表行业字段和概念标签。",
            "data_source": "stock",
        }
    industry = _find_industry(session, value)
    if industry is None:
        return {"status": "unavailable", "message": f"未识别行业或主题：{value}"}
    keywords = session.scalars(select(IndustryKeyword).where(IndustryKeyword.industry_id == industry.id)).all()
    return {
        "status": "ok",
        "industry": industry.name,
        "industry_id": industry.id,
        "keywords": [row.keyword for row in keywords],
        "reason": "来自 industry 与 industry_keyword 主题映射。",
        "data_source": "industry/industry_keyword",
    }


def get_industry_chain(session: Session, keyword: str | None) -> dict[str, Any]:
    value = _normalize_keyword(keyword)
    query = select(IndustryChainNode).order_by(IndustryChainNode.level.asc(), IndustryChainNode.heat_score.desc()).limit(80)
    if value:
        like = f"%{value}%"
        compact_like = f"%{value.replace(' ', '')}%"
        query = query.where(
            or_(
                IndustryChainNode.chain_name.ilike(like),
                IndustryChainNode.name.ilike(like),
                IndustryChainNode.related_terms.ilike(like),
                IndustryChainNode.chain_name.ilike(compact_like),
                IndustryChainNode.name.ilike(compact_like),
            )
        )
    nodes = list(session.scalars(query).all())
    if not nodes and value:
        nodes = list(
            session.scalars(
                select(IndustryChainNode).order_by(IndustryChainNode.heat_score.desc(), IndustryChainNode.level.asc()).limit(30)
            ).all()
        )
    if not nodes:
        return {"status": "unavailable", "message": "产业链节点数据不足", "nodes": []}
    rows = [
        {
            "id": node.id,
            "name": node.name,
            "level": node.level,
            "chain_name": node.chain_name,
            "node_type": node.node_type,
            "description": node.description,
            "heat_score": node.heat_score,
            "trend_score": node.trend_score,
            "related_security_ids": _loads_list(node.related_security_ids),
            "data_source": "industry_chain_node",
        }
        for node in nodes
    ]
    return {
        "status": "ok",
        "keyword": keyword or "",
        "description": "来自 Alpha Radar 产业链节点库。",
        "nodes": rows,
        "data_source": "industry_chain_node",
    }


def get_related_stocks_by_industry(session: Session, industry: str | None, limit: int = 20) -> dict[str, Any]:
    value = (industry or "").strip()
    mapped = _find_industry(session, value)
    industry_name = mapped.name if mapped else value
    if not industry_name:
        return {"status": "unavailable", "message": "缺少行业关键词", "stocks": []}
    stocks = list(
        session.scalars(
            select(Stock)
            .where(Stock.industry_level1 == industry_name, Stock.is_active.is_(True), Stock.asset_type == "equity")
            .limit(500)
        ).all()
    )
    if not stocks:
        return {"status": "unavailable", "message": f"{industry_name} 暂无相关股票", "stocks": []}
    latest_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    score_by_code = {}
    trend_by_code = {}
    codes = [stock.code for stock in stocks]
    if latest_date is not None:
        score_by_code = {
            row.stock_code: row
            for row in session.scalars(select(StockScore).where(StockScore.trade_date == latest_date, StockScore.stock_code.in_(codes))).all()
        }
        trend_by_code = {
            row.stock_code: row
            for row in session.scalars(select(TrendSignal).where(TrendSignal.trade_date == latest_date, TrendSignal.stock_code.in_(codes))).all()
        }
    rows = []
    for stock in stocks:
        score = score_by_code.get(stock.code)
        trend = trend_by_code.get(stock.code)
        rows.append(
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "industry": stock.industry_level1,
                "industry_level2": stock.industry_level2,
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
    rows.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    return {"status": "ok", "industry": industry_name, "stocks": rows[: max(1, min(limit, 100))], "data_source": "stock/stock_score/trend_signal"}


def get_industry_heatmap(session: Session, keyword_or_scope: str | None = None, limit: int = 20) -> dict[str, Any]:
    latest_date = session.scalars(select(IndustryHeat.trade_date).order_by(IndustryHeat.trade_date.desc()).limit(1)).first()
    if latest_date is None:
        return {"status": "unavailable", "message": "行业热度数据不足", "rows": []}
    query = (
        select(IndustryHeat, Industry)
        .join(Industry, Industry.id == IndustryHeat.industry_id)
        .where(IndustryHeat.trade_date == latest_date)
        .order_by(IndustryHeat.heat_score.desc())
        .limit(max(1, min(limit, 100)))
    )
    keyword = _normalize_keyword(keyword_or_scope)
    if keyword and keyword.upper() not in {"ALL", "A", "US", "HK"}:
        like = f"%{keyword}%"
        query = query.where(or_(Industry.name.ilike(like), Industry.description.ilike(like)))
    rows = [
        {
            "industry_id": industry.id,
            "name": industry.name,
            "trade_date": heat.trade_date.isoformat(),
            "heat_score": heat.heat_score,
            "heat_1d": heat.heat_1d,
            "heat_7d": heat.heat_7d,
            "heat_30d": heat.heat_30d,
            "heat_change_7d": heat.heat_change_7d,
            "top_keywords": _loads_list(heat.top_keywords),
            "top_articles": _loads_list(heat.top_articles),
            "explanation": heat.explanation,
        }
        for heat, industry in session.execute(query).all()
    ]
    if not rows and keyword:
        return get_industry_heatmap(session, None, limit)
    return {"status": "ok", "keyword": keyword_or_scope or "ALL", "rows": rows, "data_source": "industry_heat"}


def _find_industry(session: Session, keyword: str) -> Industry | None:
    value = _normalize_keyword(keyword)
    if not value:
        return None
    industry = session.scalars(select(Industry).where(Industry.name == value).limit(1)).first()
    if industry is not None:
        return industry
    like = f"%{value}%"
    industry = session.scalars(select(Industry).where(Industry.name.ilike(like)).limit(1)).first()
    if industry is not None:
        return industry
    keyword_row = session.scalars(select(IndustryKeyword).where(IndustryKeyword.keyword.ilike(like)).limit(1)).first()
    if keyword_row is None:
        return None
    return session.get(Industry, keyword_row.industry_id)


def _normalize_keyword(value: str | None) -> str:
    return (value or "").strip().replace(" ", "")


def _loads_list(raw: str | None) -> list[Any]:
    import json

    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []
