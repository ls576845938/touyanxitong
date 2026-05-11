from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.data_gate_engine import ResearchDataGate, assess_research_data_gate
from app.engines.industry_mapping_engine import IndustryMappingRule, map_stock_industry
from app.engines.risk_engine import assess_stock_risk
from app.db.models import (
    DailyBar,
    EvidenceEvent,
    IndustryChainNode,
    RetailPortfolio,
    RetailPosition,
    RetailStockPool,
    SecurityMaster,
    Stock,
    StockScore,
    TradeJournal,
    TradeReview,
    TrendSignal,
    utcnow,
)


INVESTMENT_BOUNDARY = "研究辅助和信息整理，不构成买卖建议、目标价或收益承诺。"
POOL_LEVELS = {"S", "A", "B", "C", "BANNED"}
SOCIAL_SOURCE_TYPES = {"社媒热词", "社区讨论", "social", "community"}
HIGH_QUALITY_SOURCE_TYPES = {"公告", "财报", "产业数据", "价格数据", "新闻", "研报摘要"}
POSITIVE_TERMS = ("上调", "增长", "提升", "扩张", "新增订单", "需求", "资本开支", "涨价", "突破", "中标", "放量")
NEGATIVE_TERMS = ("下调", "下降", "亏损", "减产", "制裁", "禁令", "调查", "违约", "需求放缓", "价格下跌", "风险")

AI_CHAIN_NODES = [
    {
        "name": "AI服务器",
        "level": 1,
        "node_type": "制造",
        "description": "GPU 服务器、整机制造、液冷和高速互联共同承接云厂商 AI 资本开支。",
        "key_metrics": ["AI服务器出货量", "云厂商资本开支", "订单增速", "毛利率"],
        "macro_drivers": ["AI资本开支", "美元指数", "利率"],
        "visible_indicators": ["云厂商 capex 指引", "GPU 交付周期", "ODM 订单"],
        "related_terms": ["AI服务器", "GPU服务器", "算力服务器", "液冷服务器"],
        "region_tags": ["中国", "美国", "中国台湾"],
        "heat_score": 72.0,
        "trend_score": 68.0,
    },
    {
        "name": "光模块",
        "level": 2,
        "node_type": "零部件",
        "description": "800G/1.6T 光模块和 CPO 是 AI 集群网络扩容的重要环节。",
        "key_metrics": ["800G出货量", "1.6T验证进度", "毛利率", "客户集中度"],
        "macro_drivers": ["AI资本开支", "云厂商网络升级"],
        "visible_indicators": ["光模块报价", "海外客户订单", "产能利用率"],
        "related_terms": ["光模块", "CPO", "800G", "1.6T", "光通信"],
        "region_tags": ["中国", "美国"],
        "heat_score": 78.0,
        "trend_score": 74.0,
    },
    {
        "name": "PCB",
        "level": 2,
        "node_type": "零部件",
        "description": "高速 PCB、HDI 和封装载板支撑 AI 服务器与高速光模块。",
        "key_metrics": ["高多层板报价", "产能利用率", "订单可见度", "材料成本"],
        "macro_drivers": ["AI服务器需求", "铜价", "树脂价格"],
        "visible_indicators": ["PCB稼动率", "扩产公告", "客户验证进展"],
        "related_terms": ["PCB", "高多层板", "HDI", "封装载板"],
        "region_tags": ["中国", "中国台湾"],
        "heat_score": 64.0,
        "trend_score": 58.0,
    },
    {
        "name": "液冷",
        "level": 2,
        "node_type": "设备",
        "description": "液冷提高高功耗 AI 服务器散热效率，渗透率受机柜功耗和数据中心设计驱动。",
        "key_metrics": ["液冷渗透率", "机柜功耗", "数据中心建设节奏"],
        "macro_drivers": ["AI资本开支", "电价", "PUE要求"],
        "visible_indicators": ["液冷招标", "数据中心 PUE", "服务器功耗"],
        "related_terms": ["液冷", "冷板", "浸没式液冷", "散热"],
        "region_tags": ["中国", "美国"],
        "heat_score": 69.0,
        "trend_score": 63.0,
    },
    {
        "name": "电源",
        "level": 2,
        "node_type": "零部件",
        "description": "高功率电源、UPS 和电力配套影响 AI 数据中心可靠性与建设节奏。",
        "key_metrics": ["电源功率密度", "UPS订单", "电力配套周期"],
        "macro_drivers": ["电价", "数据中心建设", "铜价"],
        "visible_indicators": ["电源供应订单", "数据中心接电进度"],
        "related_terms": ["电源", "UPS", "电力配套", "功率模块"],
        "region_tags": ["中国", "美国"],
        "heat_score": 55.0,
        "trend_score": 52.0,
    },
]

DEMO_SECURITIES = [
    ("300308", "A", "SZSE", "中际旭创", "光模块", ["光模块", "CPO", "AI算力"], ["光模块"]),
    ("300502", "A", "SZSE", "新易盛", "光模块", ["光模块", "CPO", "AI服务器"], ["光模块"]),
    ("601138", "A", "SSE", "工业富联", "AI服务器", ["AI服务器", "液冷", "算力"], ["AI服务器", "液冷"]),
    ("002463", "A", "SZSE", "沪电股份", "PCB", ["PCB", "AI服务器", "高速板"], ["PCB"]),
    ("300274", "A", "SZSE", "阳光电源", "电源", ["电源", "储能", "数据中心"], ["电源"]),
    ("NVDA", "US", "NASDAQ", "NVIDIA", "AI芯片", ["AI芯片", "GPU", "AI资本开支"], ["AI服务器"]),
]

DEMO_EVIDENCE_SEEDS = [
    {
        "title": "光模块订单交付节奏延续",
        "summary": "AI 光模块订单交付节奏维持高位，仍需继续核验持续性与客户 capex。",
        "source_name": "同花顺",
        "source_url": "https://news.10jqka.com.cn/20260508/c676500001.shtml",
        "source_type": "新闻",
        "symbol": "300308",
        "node_name": "光模块",
        "impact_direction": "positive",
        "impact_strength": 76.0,
        "confidence": 84.0,
        "data_quality_status": "PASS",
        "is_mock": False,
    },
    {
        "title": "GPU 供给节奏改善",
        "summary": "GPU 供应节奏改善有助于上游与服务器链条出货修复，但仍需结合财报与订单确认。",
        "source_name": "WSJ",
        "source_url": "https://wsj.test/markets/1",
        "source_type": "新闻",
        "symbol": "NVDA",
        "node_name": "AI服务器",
        "impact_direction": "positive",
        "impact_strength": 68.0,
        "confidence": 79.0,
        "data_quality_status": "WARN",
        "is_mock": False,
    },
    {
        "title": "Demo: 国产 AI 芯片渠道调研摘要",
        "summary": "该样本故意缺少完整来源引用，只能保留低置信研究跟踪。",
        "source_name": "",
        "source_url": "",
        "source_type": "community",
        "symbol": "300308",
        "node_name": "AI服务器",
        "impact_direction": "uncertain",
        "impact_strength": 42.0,
        "confidence": 88.0,
        "data_quality_status": "FAIL",
        "is_mock": True,
    },
]


def ensure_retail_demo_data(session: Session) -> dict[str, int]:
    existing_security_count = int(session.scalar(select(func.count(SecurityMaster.id))) or 0)
    securities = 0 if existing_security_count else ensure_security_master_from_stocks(session)
    demo_securities = _ensure_demo_securities(session)
    nodes = ensure_ai_chain_nodes(session)
    needs_relation_refresh = existing_security_count == 0 or not session.scalar(
        select(func.count(IndustryChainNode.id)).where(IndustryChainNode.chain_name == "AI算力", IndustryChainNode.related_security_ids != "[]")
    )
    if needs_relation_refresh:
        _attach_security_node_relations(session)
    portfolio = ensure_default_portfolio(session)
    evidence_events = _ensure_demo_evidence_events(session)
    pool_items = _ensure_demo_stock_pool(session)
    trade_count, review_count = _ensure_demo_trade_records(session, portfolio.id)
    session.commit()
    return {
        "security_master_count": securities + demo_securities,
        "industry_chain_node_count": nodes,
        "portfolio_id": portfolio.id,
        "evidence_event_count": evidence_events,
        "stock_pool_count": pool_items,
        "trade_journal_count": trade_count,
        "trade_review_count": review_count,
    }


def ensure_security_master_from_stocks(session: Session) -> int:
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
    existing_rows = session.scalars(select(SecurityMaster)).all()
    existing_by_key = {(row.symbol, row.market): row for row in existing_rows}
    count = 0
    for stock in stocks:
        existing = existing_by_key.get((stock.code, stock.market))
        concepts = _loads_list(stock.concepts)
        products = _infer_products(stock.industry_level1, stock.industry_level2, concepts)
        payload = {
            "exchange": stock.exchange,
            "name": stock.name,
            "company_name": stock.name,
            "industry_level_1": stock.industry_level1,
            "industry_level_2": stock.industry_level2,
            "concept_tags": _dumps(concepts),
            "main_products": _dumps(products),
            "business_summary": _business_summary(stock.name, stock.industry_level1, stock.industry_level2, products),
            "revenue_drivers": _dumps(_revenue_drivers(stock.industry_level1, concepts)),
            "cost_drivers": _dumps(_cost_drivers(stock.industry_level1, concepts)),
            "profit_drivers": _dumps(_profit_drivers(stock.industry_level1, concepts)),
            "macro_sensitivities": _dumps(_macro_sensitivities(stock.industry_level1, concepts)),
            "data_source": stock.source or stock.data_vendor or "stock_universe",
            "source_confidence": 0.75 if str(stock.data_vendor or stock.source).lower() not in {"mock", ""} else 0.45,
        }
        if existing is None:
            existing = SecurityMaster(symbol=stock.code, market=stock.market, **payload)
            session.add(existing)
            existing_by_key[(stock.code, stock.market)] = existing
            count += 1
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    session.flush()
    return count


def ensure_ai_chain_nodes(session: Session) -> int:
    created = 0
    by_name: dict[str, IndustryChainNode] = {}
    for idx, item in enumerate(AI_CHAIN_NODES):
        node = session.scalar(
            select(IndustryChainNode).where(IndustryChainNode.chain_name == "AI算力", IndustryChainNode.name == item["name"])
        )
        payload = {
            "level": int(item["level"]),
            "node_type": str(item["node_type"]),
            "description": str(item["description"]),
            "key_metrics": _dumps(item["key_metrics"]),
            "macro_drivers": _dumps(item["macro_drivers"]),
            "visible_indicators": _dumps(item["visible_indicators"]),
            "related_terms": _dumps(item["related_terms"]),
            "region_tags": _dumps(item["region_tags"]),
            "heat_score": float(item["heat_score"]),
            "trend_score": float(item["trend_score"]),
        }
        if node is None:
            node = IndustryChainNode(name=item["name"], chain_name="AI算力", **payload)
            session.add(node)
            created += 1
        else:
            for key, value in payload.items():
                setattr(node, key, value)
        by_name[item["name"]] = node
    session.flush()

    ai_server = by_name.get("AI服务器")
    if ai_server:
        for name in ("光模块", "PCB", "液冷", "电源"):
            if name in by_name:
                by_name[name].parent_id = ai_server.id
        relation_map = {
            "AI服务器": {"upstream": ["光模块", "PCB", "液冷", "电源"], "downstream": []},
            "光模块": {"upstream": ["PCB"], "downstream": ["AI服务器"]},
            "PCB": {"upstream": [], "downstream": ["光模块", "AI服务器"]},
            "液冷": {"upstream": [], "downstream": ["AI服务器"]},
            "电源": {"upstream": [], "downstream": ["AI服务器"]},
        }
        for name, relation in relation_map.items():
            node = by_name[name]
            node.upstream_node_ids = _dumps([by_name[item].id for item in relation["upstream"] if item in by_name])
            node.downstream_node_ids = _dumps([by_name[item].id for item in relation["downstream"] if item in by_name])
    session.flush()
    return created


def build_security_research_profile(session: Session, symbol: str) -> dict[str, Any] | None:
    ensure_retail_demo_data(session)
    security = _find_security(session, symbol)
    if security is None:
        return None
    related_nodes = _security_nodes(session, security)
    upstream = _nodes_by_ids(session, _loads_ints(security.upstream_node_ids))
    downstream = _nodes_by_ids(session, _loads_ints(security.downstream_node_ids))
    latest_pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
    events = session.scalars(
        select(EvidenceEvent).order_by(EvidenceEvent.event_time.desc(), EvidenceEvent.id.desc()).limit(120)
    ).all()
    related_events = [event for event in events if security.id in _loads_ints(event.affected_security_ids)][:12]
    trend = _latest_trend_for_symbol(session, security.symbol)
    score = _latest_score_for_symbol(session, security.symbol)
    data_quality_status = _profile_data_quality_status(security, related_events, latest_pool)
    risk_tags = _profile_risk_tags(data_quality_status, latest_pool, related_events)
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "basic": _security_payload(security),
        "industry_position": {
            "industry_level_1": security.industry_level_1,
            "industry_level_2": security.industry_level_2,
            "industry_level_3": security.industry_level_3,
            "chain_nodes": [_node_payload(node) for node in related_nodes],
            "upstream": [_node_payload(node) for node in upstream],
            "downstream": [_node_payload(node) for node in downstream],
            "main_products": _loads_list(security.main_products),
            "revenue_drivers": _loads_list(security.revenue_drivers),
            "cost_drivers": _loads_list(security.cost_drivers),
            "profit_drivers": _loads_list(security.profit_drivers),
            "macro_sensitivities": _loads_list(security.macro_sensitivities),
        },
        "evidence_events": [_event_payload(event, session) for event in related_events],
        "stock_pool": _pool_payload(latest_pool, security, session) if latest_pool else None,
        "trend_signal": _trend_payload(trend, score),
        "risk_tags": risk_tags,
        "data_quality_status": data_quality_status,
    }


def build_industry_chain_graph(session: Session, chain_name: str) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    nodes = session.scalars(
        select(IndustryChainNode).where(IndustryChainNode.chain_name == chain_name).order_by(IndustryChainNode.level, IndustryChainNode.id)
    ).all()
    if not nodes and chain_name != "AI算力":
        nodes = session.scalars(
            select(IndustryChainNode).where(IndustryChainNode.chain_name == "AI算力").order_by(IndustryChainNode.level, IndustryChainNode.id)
        ).all()
        chain_name = "AI算力"
    node_by_id = {node.id: node for node in nodes}
    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for node in nodes:
        for target_id in _loads_ints(node.downstream_node_ids):
            if target_id in node_by_id and (node.id, target_id) not in seen:
                seen.add((node.id, target_id))
                edges.append({"source": node.id, "target": target_id, "relation_type": "upstream_downstream", "confidence": 0.72})
        for source_id in _loads_ints(node.upstream_node_ids):
            if source_id in node_by_id and (source_id, node.id) not in seen:
                seen.add((source_id, node.id))
                edges.append({"source": source_id, "target": node.id, "relation_type": "upstream_downstream", "confidence": 0.72})
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "chain_name": chain_name,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_heat_score": max((node.heat_score for node in nodes), default=0.0),
            "data_quality_status": "WARN",
            "data_note": "产业链图谱 v1 由系统种子和现有证券主数据生成，需继续用公告、财报和产业数据校验。",
        },
        "nodes": [_chain_graph_node_payload(node, session) for node in nodes],
        "edges": edges,
    }


def extract_evidence_event(session: Session, payload: dict[str, Any]) -> EvidenceEvent:
    ensure_retail_demo_data(session)
    title = str(payload.get("title") or payload.get("headline") or "").strip()
    raw_text = str(payload.get("raw_text") or payload.get("content") or "")
    summary = str(payload.get("summary") or raw_text[:240] or title)
    if not title:
        title = summary[:80] or "未命名证据事件"
    source_name = str(payload.get("source_name") or payload.get("source") or "").strip()
    source_url = str(payload.get("source_url") or "").strip()
    source_type = str(payload.get("source_type") or "新闻").strip()
    is_mock = bool(payload.get("is_mock", False)) or source_url.startswith("mock://") or source_name.lower() == "mock"
    event_time = _parse_datetime(payload.get("event_time")) or utcnow()
    text = f"{title}\n{summary}\n{raw_text}"
    raw_hash = hashlib.sha256(f"{title}|{summary}|{source_name}|{source_url}|{event_time.isoformat()}".encode("utf-8")).hexdigest()
    existing = session.scalar(select(EvidenceEvent).where(EvidenceEvent.raw_text_hash == raw_hash))
    if existing is not None:
        return existing

    affected_objects = _affected_objects(text)
    nodes = _matched_nodes(session, text, affected_objects)
    securities = _matched_securities(session, text, nodes, affected_objects)
    direction = _impact_direction(text)
    data_quality = _event_data_quality_status(source_name=source_name, source_url=source_url, source_type=source_type, is_mock=is_mock)
    confidence = _event_confidence(
        source_name=source_name,
        source_url=source_url,
        source_type=source_type,
        data_quality_status=data_quality,
        affected_objects=affected_objects,
        securities=securities,
        is_mock=is_mock,
    )
    strength = _event_strength(text, affected_objects, direction)
    event = EvidenceEvent(
        event_time=event_time,
        title=title,
        summary=summary,
        source_name=source_name,
        source_url=source_url,
        source_type=source_type,
        raw_text_hash=raw_hash,
        affected_objects=_dumps(affected_objects),
        affected_node_ids=_dumps([node.id for node in nodes]),
        affected_security_ids=_dumps([security.id for security in securities]),
        impact_direction=direction,
        impact_strength=strength,
        confidence=confidence,
        duration_type=_duration_type(text, source_type),
        logic_chain=_logic_chain(title, affected_objects, nodes, securities, direction),
        risk_notes=_risk_notes(data_quality, source_type, securities),
        evidence_tags=_dumps(_evidence_tags(source_type, affected_objects, data_quality)),
        is_mock=is_mock,
        data_quality_status=data_quality,
    )
    session.add(event)
    session.flush()
    update_chain_heat_from_event(session, event)
    upsert_pool_candidates_from_event(session, event)
    session.commit()
    return event


def update_chain_heat_from_event(session: Session, event: EvidenceEvent) -> None:
    node_ids = _loads_ints(event.affected_node_ids)
    if not node_ids:
        return
    nodes = session.scalars(select(IndustryChainNode).where(IndustryChainNode.id.in_(node_ids))).all()
    direction_boost = -6.0 if event.impact_direction == "negative" else 6.0 if event.impact_direction == "positive" else 1.5
    for node in nodes:
        node.heat_score = _clamp(float(node.heat_score or 0.0) * 0.92 + direction_boost + float(event.impact_strength or 0.0) * 0.08)
        node.trend_score = _clamp(float(node.trend_score or 0.0) * 0.94 + float(event.confidence or 0.0) * 0.06)


def upsert_pool_candidates_from_event(session: Session, event: EvidenceEvent) -> list[RetailStockPool]:
    security_ids = _loads_ints(event.affected_security_ids)
    if not security_ids:
        return []
    securities = session.scalars(select(SecurityMaster).where(SecurityMaster.id.in_(security_ids))).all()
    node_ids = _loads_ints(event.affected_node_ids)
    nodes = session.scalars(select(IndustryChainNode).where(IndustryChainNode.id.in_(node_ids))).all() if node_ids else []
    result: list[RetailStockPool] = []
    for security in securities:
        trend_score = _latest_trend_score(session, security.symbol)
        tenbagger_score = _latest_stock_final_score(session, security.symbol)
        industry_heat_score = max((float(node.heat_score or 0.0) for node in nodes), default=0.0)
        evidence_score = _clamp((float(event.confidence or 0.0) * 0.65) + (float(event.impact_strength or 0.0) * 0.35))
        quality_score = 70.0 if event.data_quality_status == "PASS" else 52.0 if event.data_quality_status == "WARN" else 25.0
        valuation_score = 50.0
        risk_score = _pool_risk_score(event, security)
        conviction_score = calculate_conviction_score(
            evidence_score=evidence_score,
            industry_heat_score=industry_heat_score,
            trend_score=trend_score,
            quality_score=quality_score,
            valuation_score=valuation_score,
            risk_score=risk_score,
        )
        suggested_level = suggest_pool_level(
            data_quality_status=event.data_quality_status,
            source_type=event.source_type,
            evidence_score=evidence_score,
            industry_heat_score=industry_heat_score,
            trend_score=trend_score,
            risk_score=risk_score,
            has_invalidation=True,
            has_source=bool(event.source_name and event.source_url),
        )
        pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
        key_events = [event.id]
        if pool is None:
            pool = RetailStockPool(
                security_id=security.id,
                pool_level=suggested_level,
                pool_reason=f"由证据事件触发的研究候选：{event.title}",
                thesis_summary=_pool_thesis_summary(security, event),
                key_evidence_event_ids=_dumps(key_events),
                related_node_ids=_dumps(node_ids),
                invalidation_conditions=_dumps(_default_invalidation_conditions(security, event)),
                next_tracking_tasks=_dumps(_default_tracking_tasks(security, event)),
                status="watching",
            )
            session.add(pool)
        else:
            key_events = _dedupe_ints(_loads_ints(pool.key_evidence_event_ids) + [event.id])[:20]
            pool.key_evidence_event_ids = _dumps(key_events)
            pool.related_node_ids = _dumps(_dedupe_ints(_loads_ints(pool.related_node_ids) + node_ids))
            if _level_rank(suggested_level) > _level_rank(pool.pool_level):
                pool.pool_level = suggested_level
            pool.pool_reason = f"{pool.pool_reason or ''}\n{event.title}".strip()
            pool.thesis_summary = pool.thesis_summary or _pool_thesis_summary(security, event)
        pool.trend_score = trend_score
        pool.industry_heat_score = industry_heat_score
        pool.evidence_score = evidence_score
        pool.valuation_score = valuation_score
        pool.quality_score = quality_score
        pool.risk_score = risk_score
        pool.tenbagger_score = tenbagger_score
        pool.conviction_score = conviction_score
        apply_stock_pool_gate(pool, session)
        result.append(pool)
    session.flush()
    return result


def calculate_conviction_score(
    *,
    evidence_score: float,
    industry_heat_score: float,
    trend_score: float,
    quality_score: float,
    valuation_score: float,
    risk_score: float,
) -> float:
    return round(
        _clamp(
            0.25 * evidence_score
            + 0.20 * industry_heat_score
            + 0.20 * trend_score
            + 0.15 * quality_score
            + 0.10 * valuation_score
            - 0.10 * risk_score
        ),
        2,
    )


def suggest_pool_level(
    *,
    data_quality_status: str,
    source_type: str,
    evidence_score: float,
    industry_heat_score: float,
    trend_score: float,
    risk_score: float,
    has_invalidation: bool,
    has_source: bool,
) -> str:
    if risk_score >= 90:
        return "BANNED"
    if data_quality_status == "FAIL":
        return "C"
    if source_type in SOCIAL_SOURCE_TYPES and evidence_score < 80:
        return "C"
    if not has_source:
        return "B"
    if evidence_score >= 82 and industry_heat_score >= 72 and trend_score >= 70 and risk_score <= 35 and has_invalidation:
        return "S"
    if evidence_score >= 68 and industry_heat_score >= 60 and trend_score >= 50 and risk_score <= 60:
        return "A"
    if evidence_score >= 50 or industry_heat_score >= 50:
        return "B"
    return "C"


def apply_stock_pool_gate(pool: RetailStockPool, session: Session) -> RetailStockPool:
    event_ids = _loads_ints(pool.key_evidence_event_ids)
    events = session.scalars(select(EvidenceEvent).where(EvidenceEvent.id.in_(event_ids))).all() if event_ids else []
    has_fail = any(event.data_quality_status == "FAIL" or event.is_mock for event in events)
    has_source = any(event.source_name and event.source_url for event in events)
    source_types = {event.source_type for event in events}
    only_social = bool(source_types) and source_types.issubset(SOCIAL_SOURCE_TYPES)
    invalidations = _loads_list(pool.invalidation_conditions)
    missing_s_requirements = [
        not pool.thesis_summary.strip(),
        not invalidations,
        not _loads_list(pool.next_tracking_tasks),
        float(pool.trend_score or 0.0) <= 0,
        float(pool.risk_score or 0.0) <= 0,
    ]
    if pool.pool_level in {"S", "A"} and (has_fail or only_social or not has_source):
        pool.pool_level = "B" if not only_social and has_source else "C"
    if pool.pool_level == "S" and any(missing_s_requirements):
        pool.pool_level = "A"
    pool.conviction_score = calculate_conviction_score(
        evidence_score=float(pool.evidence_score or 0.0),
        industry_heat_score=float(pool.industry_heat_score or 0.0),
        trend_score=float(pool.trend_score or 0.0),
        quality_score=float(pool.quality_score or 0.0),
        valuation_score=float(pool.valuation_score or 0.0),
        risk_score=float(pool.risk_score or 0.0),
    )
    return pool


def recalculate_stock_pool_scores(session: Session) -> dict[str, Any]:
    pools = session.scalars(select(RetailStockPool)).all()
    for pool in pools:
        apply_stock_pool_gate(pool, session)
    session.commit()
    return {"updated": len(pools), "formula": "0.25*evidence + 0.20*industry_heat + 0.20*trend + 0.15*quality + 0.10*valuation - 0.10*risk"}


def ensure_default_portfolio(session: Session) -> RetailPortfolio:
    portfolio = session.get(RetailPortfolio, 1)
    if portfolio is None:
        portfolio = RetailPortfolio(id=1, name="默认研究组合", base_currency="CNY", benchmark="沪深300", cash=100000.0)
        session.add(portfolio)
        session.flush()
    if not session.scalar(select(func.count(RetailPosition.id)).where(RetailPosition.portfolio_id == portfolio.id)):
        ensure_ai_chain_nodes(session)
        _attach_security_node_relations(session)
        defaults = [("300308", 160000.0), ("300502", 120000.0), ("601138", 90000.0)]
        for symbol, value in defaults:
            security = _find_security(session, symbol)
            if security is None:
                continue
            session.add(
                RetailPosition(
                    portfolio_id=portfolio.id,
                    security_id=security.id,
                    quantity=0.0,
                    avg_cost=0.0,
                    market_value=value,
                    industry_exposure=security.industry_level_1,
                    theme_exposure=security.concept_tags,
                    chain_node_exposure=_dumps(_loads_ints(security.upstream_node_ids) + _loads_ints(security.downstream_node_ids)),
                    factor_tags=_dumps(["AI资本开支", "成长", "产业链集中"]),
                )
            )
        session.flush()
        refresh_position_weights(session, portfolio.id)
    return portfolio


def refresh_position_weights(session: Session, portfolio_id: int) -> None:
    positions = session.scalars(select(RetailPosition).where(RetailPosition.portfolio_id == portfolio_id)).all()
    portfolio = session.get(RetailPortfolio, portfolio_id)
    total = float(portfolio.cash if portfolio else 0.0) + sum(float(position.market_value or 0.0) for position in positions)
    for position in positions:
        position.weight = round(float(position.market_value or 0.0) / total, 6) if total else 0.0


def build_portfolio_dashboard(session: Session, portfolio_id: int) -> dict[str, Any] | None:
    ensure_retail_demo_data(session)
    portfolio = session.get(RetailPortfolio, portfolio_id)
    if portfolio is None:
        return None
    refresh_position_weights(session, portfolio_id)
    exposure = calculate_portfolio_exposure(session, portfolio_id)
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "portfolio": _portfolio_payload(portfolio),
        "overview": exposure["overview"],
        "positions": exposure["positions"],
        "industry_exposure": exposure["industry_exposure"],
        "theme_exposure": exposure["theme_exposure"],
        "chain_node_exposure": exposure["chain_node_exposure"],
        "correlation_warnings": exposure["correlation_warnings"],
        "risk_alerts": exposure["risk_alerts"],
    }


def build_retail_daily_context(session: Session, report_date: date) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
    events = session.scalars(
        select(EvidenceEvent)
        .where(EvidenceEvent.event_time >= day_start)
        .order_by(EvidenceEvent.confidence.desc(), EvidenceEvent.id.desc())
        .limit(20)
    ).all()
    if not events:
        events = session.scalars(select(EvidenceEvent).order_by(EvidenceEvent.event_time.desc(), EvidenceEvent.id.desc()).limit(10)).all()
    pools = session.scalars(
        select(RetailStockPool).order_by(RetailStockPool.pool_level.asc(), RetailStockPool.conviction_score.desc()).limit(30)
    ).all()
    portfolio = build_portfolio_dashboard(session, 1)
    pending_reviews = session.scalars(
        select(TradeJournal)
        .where(~TradeJournal.id.in_(select(TradeReview.trade_journal_id)))
        .order_by(TradeJournal.trade_date.desc())
        .limit(10)
    ).all()
    research_tasks: list[str] = []
    for pool in pools[:8]:
        security = session.get(SecurityMaster, pool.security_id)
        for task in _loads_list(pool.next_tracking_tasks)[:2]:
            research_tasks.append(f"{security.name if security else pool.security_id}：{task}")
    research_tasks.extend(f"复盘 {trade.trade_date.isoformat()} 交易记录 #{trade.id}" for trade in pending_reviews[:5])
    if not research_tasks:
        research_tasks.append("补充 S/A 候选的来源证据、趋势证据、风险提示和证伪条件。")
    pool_counts = Counter(pool.pool_level for pool in pools)
    return {
        "summary": {
            "candidate_count": len(pools),
            "event_count": len(events),
            "s_count": pool_counts.get("S", 0),
            "a_count": pool_counts.get("A", 0),
            "b_count": pool_counts.get("B", 0),
            "c_count": pool_counts.get("C", 0),
            "banned_count": pool_counts.get("BANNED", 0),
        },
        "new_evidence_events": [_event_payload(event, session) for event in events],
        "stock_pool_changes": [payload_for_pool(pool, session) for pool in pools],
        "portfolio_risk": portfolio or {},
        "research_tasks": research_tasks[:20],
        "review_questions": review_questions(),
    }


def calculate_portfolio_exposure(session: Session, portfolio_id: int) -> dict[str, Any]:
    portfolio = session.get(RetailPortfolio, portfolio_id)
    if portfolio is None:
        return {}
    positions = session.scalars(select(RetailPosition).where(RetailPosition.portfolio_id == portfolio_id)).all()
    securities = {
        security.id: security
        for security in session.scalars(select(SecurityMaster).where(SecurityMaster.id.in_([p.security_id for p in positions] or [0]))).all()
    }
    total_value = float(portfolio.cash or 0.0) + sum(float(position.market_value or 0.0) for position in positions)
    industry_counter: Counter[str] = Counter()
    theme_counter: Counter[str] = Counter()
    node_counter: Counter[int] = Counter()
    position_rows: list[dict[str, Any]] = []
    for position in positions:
        security = securities.get(position.security_id)
        if security is None:
            continue
        weight = float(position.market_value or 0.0) / total_value if total_value else float(position.weight or 0.0)
        industry = position.industry_exposure or security.industry_level_1 or "未分类"
        industry_counter[industry] += weight
        themes = _loads_list(position.theme_exposure) or _loads_list(security.concept_tags)
        for theme in themes:
            theme_counter[str(theme)] += weight
        node_ids = _loads_ints(position.chain_node_exposure) or _loads_ints(security.upstream_node_ids) + _loads_ints(security.downstream_node_ids)
        for node_id in set(node_ids):
            node_counter[node_id] += weight
        position_rows.append(
            {
                "id": position.id,
                "security": _security_payload(security),
                "quantity": position.quantity,
                "avg_cost": position.avg_cost,
                "market_value": position.market_value,
                "weight": round(weight, 4),
                "unrealized_pnl": position.unrealized_pnl,
                "industry_exposure": industry,
                "theme_exposure": themes,
                "chain_node_exposure": node_ids,
                "factor_tags": _loads_list(position.factor_tags),
            }
        )
    node_names = _node_name_map(session, list(node_counter))
    industry_exposure = _exposure_rows(industry_counter)
    theme_exposure = _exposure_rows(theme_counter)
    chain_node_exposure = [
        {"node_id": node_id, "name": node_names.get(node_id, str(node_id)), "weight": round(weight, 4)}
        for node_id, weight in node_counter.most_common()
    ]
    correlation_warnings = _correlation_warnings(position_rows, node_names)
    risk_alerts = _portfolio_risk_alerts(position_rows, industry_exposure, theme_exposure, chain_node_exposure, correlation_warnings)
    return {
        "overview": {
            "total_asset": round(total_value, 2),
            "cash": round(float(portfolio.cash or 0.0), 2),
            "stock_weight": round(sum(float(row["weight"]) for row in position_rows), 4),
            "position_count": len(position_rows),
            "data_quality_status": "WARN" if position_rows else "FAIL",
            "data_note": "组合暴露为研究辅助视角，默认组合如未录入真实仓位则含 demo/fallback 标记。",
        },
        "positions": position_rows,
        "industry_exposure": industry_exposure,
        "theme_exposure": theme_exposure,
        "chain_node_exposure": chain_node_exposure,
        "correlation_warnings": correlation_warnings,
        "risk_alerts": risk_alerts,
    }


def create_trade_review(session: Session, trade: TradeJournal, payload: dict[str, Any] | None = None) -> TradeReview:
    payload = payload or {}
    review_date = _parse_date(payload.get("review_date")) or date.today()
    current_price = _number(payload.get("current_price"), None)
    security = session.get(SecurityMaster, trade.security_id)
    if current_price is None and security is not None:
        bar = session.scalars(
            select(DailyBar).where(DailyBar.stock_code == security.symbol, DailyBar.trade_date <= review_date).order_by(DailyBar.trade_date.desc()).limit(1)
        ).first()
        current_price = float(bar.close) if bar else None
    current_price = current_price if current_price is not None else float(trade.price or 0.0)
    pnl = (current_price - float(trade.price or 0.0)) * float(trade.quantity or 0.0)
    pnl_pct = ((current_price - float(trade.price or 0.0)) / float(trade.price or 1.0)) if float(trade.price or 0.0) > 0 else 0.0
    benchmark_return = _number(payload.get("benchmark_return"), 0.0) or 0.0
    excess_return = pnl_pct - benchmark_return
    holding_period_days = max((review_date - trade.trade_date).days, 0)
    linked_events = _linked_events(session, trade)
    attribution, error_category = _review_attribution(trade, linked_events, pnl_pct, excess_return, holding_period_days)
    result_type = "success" if pnl_pct >= 0.05 else "failure" if pnl_pct <= -0.05 else "neutral"
    existing = session.scalar(select(TradeReview).where(TradeReview.trade_journal_id == trade.id))
    values = {
        "review_date": review_date,
        "holding_period_days": holding_period_days,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 4),
        "benchmark_return": round(benchmark_return, 4),
        "excess_return": round(excess_return, 4),
        "result_type": result_type,
        "attribution_logic": attribution,
        "what_happened": str(payload.get("what_happened") or _default_what_happened(security, pnl_pct, linked_events)),
        "what_expected": trade.expected_scenario or trade.trade_reason,
        "error_category": error_category,
        "should_update_model_rules": bool(result_type == "failure" and error_category != "no_error"),
        "rule_update_suggestion": str(payload.get("rule_update_suggestion") or _rule_update_suggestion(error_category)),
        "next_action": str(payload.get("next_action") or _next_review_action(result_type, error_category)),
    }
    if existing is None:
        review = TradeReview(trade_journal_id=trade.id, **values)
        session.add(review)
    else:
        review = existing
        for key, value in values.items():
            setattr(review, key, value)
    session.flush()
    return review


def review_questions() -> list[str]:
    return [
        "当时买入/卖出的核心理由是什么？",
        "对应证据是否仍然成立？",
        "股价变化是否来自原始逻辑？",
        "是逻辑错误、节奏错误、仓位错误，还是市场环境变化？",
        "这笔交易应不应该改变股票池等级？",
        "是否需要新增一条模型规则？",
    ]


def _ensure_demo_securities(session: Session) -> int:
    created = 0
    for symbol, market, exchange, name, industry2, concepts, products in DEMO_SECURITIES:
        existing = session.scalar(select(SecurityMaster).where(SecurityMaster.symbol == symbol, SecurityMaster.market == market))
        payload = {
            "exchange": exchange,
            "name": name,
            "company_name": name,
            "industry_level_1": "AI算力",
            "industry_level_2": industry2,
            "concept_tags": _dumps(concepts),
            "main_products": _dumps(products),
            "business_summary": _business_summary(name, "AI算力", industry2, products),
            "revenue_drivers": _dumps(_revenue_drivers("AI算力", concepts)),
            "cost_drivers": _dumps(_cost_drivers("AI算力", concepts)),
            "profit_drivers": _dumps(_profit_drivers("AI算力", concepts)),
            "macro_sensitivities": _dumps(_macro_sensitivities("AI算力", concepts)),
            "data_source": "demo_seed",
            "source_confidence": 0.55,
        }
        if existing is None:
            session.add(SecurityMaster(symbol=symbol, market=market, **payload))
            created += 1
        elif existing.data_source == "demo_seed":
            for key, value in payload.items():
                setattr(existing, key, value)
    session.flush()
    return created


def _ensure_demo_evidence_events(session: Session) -> int:
    created = 0
    node_by_name = {
        node.name: node for node in session.scalars(select(IndustryChainNode).where(IndustryChainNode.chain_name == "AI算力")).all()
    }
    for idx, item in enumerate(DEMO_EVIDENCE_SEEDS):
        existing = session.scalar(select(EvidenceEvent).where(EvidenceEvent.title == item["title"]))
        if existing is not None:
            continue
        security = _find_security(session, str(item["symbol"]))
        node = node_by_name.get(str(item["node_name"]))
        raw_hash = hashlib.sha256(f"demo|{item['title']}|{item['symbol']}".encode("utf-8")).hexdigest()
        event = EvidenceEvent(
            event_time=datetime(2026, 5, 8 + idx, 9, 0, tzinfo=timezone.utc),
            title=str(item["title"]),
            summary=str(item["summary"]),
            source_name=str(item["source_name"]),
            source_url=str(item["source_url"]),
            source_type=str(item["source_type"]),
            raw_text_hash=raw_hash,
            affected_objects=_dumps(["AI算力", item["node_name"], item["symbol"]]),
            affected_node_ids=_dumps([node.id] if node else []),
            affected_security_ids=_dumps([security.id] if security else []),
            impact_direction=str(item["impact_direction"]),
            impact_strength=float(item["impact_strength"]),
            confidence=float(item["confidence"]),
            duration_type="short_term",
            logic_chain=f"{item['title']} -> {item['node_name']} -> {item['symbol']}，仅作研究辅助。",
            risk_notes="需继续核验来源、产业链位置与组合集中度。",
            evidence_tags=_dumps(["ai_compute_demo", item["node_name"]]),
            is_mock=bool(item["is_mock"]),
            data_quality_status=str(item["data_quality_status"]),
        )
        session.add(event)
        created += 1
    session.flush()
    return created


def _ensure_demo_stock_pool(session: Session) -> int:
    created = 0
    for symbol, requested_level in (("300308", "A"), ("NVDA", "B"), ("300502", "S")):
        security = _find_security(session, symbol)
        if security is None:
            continue
        pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
        if pool is None:
            event_ids = [
                event.id
                for event in session.scalars(select(EvidenceEvent).where(EvidenceEvent.affected_security_ids.like(f"%{security.id}%"))).all()
            ]
            pool = RetailStockPool(
                security_id=security.id,
                pool_level=requested_level,
                pool_reason="AI算力 demo 观察池样本，仅作研究辅助。",
                thesis_summary=f"{security.name} 的 demo 观察条目，用于演示证据链和风险提示。",
                key_evidence_event_ids=_dumps(event_ids[:3]),
                related_node_ids=security.upstream_node_ids or security.downstream_node_ids or "[]",
                trend_score=_latest_trend_score(session, security.symbol),
                industry_heat_score=72.0 if security.industry_level_1 == "AI算力" else 55.0,
                evidence_score=78.0 if requested_level != "S" else 52.0,
                valuation_score=50.0,
                quality_score=25.0 if requested_level == "S" else 70.0,
                risk_score=66.0 if requested_level == "S" else 38.0,
                tenbagger_score=_latest_stock_final_score(session, security.symbol),
                conviction_score=0.0,
                user_note="若 data_quality 或来源引用不足，则不得保留 S/A 级。",
                status="watching",
                invalidation_conditions=_dumps(["来源证据被证伪", "趋势结构明显走弱"]),
                next_tracking_tasks=_dumps(["补来源", "查财报", "看组合集中度"]),
            )
            session.add(pool)
            created += 1
        apply_stock_pool_gate(pool, session)
    session.flush()
    return created


def _ensure_demo_trade_records(session: Session, portfolio_id: int) -> tuple[int, int]:
    trade_created = 0
    review_created = 0
    trade = session.scalar(select(TradeJournal).where(TradeJournal.portfolio_id == portfolio_id).order_by(TradeJournal.id).limit(1))
    if trade is None:
        security = _find_security(session, "300308")
        pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id)) if security else None
        linked_events = []
        if security is not None:
            linked_events = [
                event.id
                for event in session.scalars(select(EvidenceEvent).where(EvidenceEvent.affected_security_ids.like(f"%{security.id}%"))).all()
            ]
        trade = TradeJournal(
            portfolio_id=portfolio_id,
            security_id=security.id if security else 1,
            trade_date=date(2026, 5, 9),
            action="watch",
            price=148.5,
            quantity=200.0,
            position_weight_after_trade=0.18,
            trade_reason="demo 研究跟踪记录，不构成系统交易指令。",
            linked_evidence_event_ids=_dumps(linked_events[:2]),
            linked_stock_pool_id=pool.id if pool else None,
            expected_scenario="订单兑现与产业链景气延续。",
            invalidation_condition="核心来源缺失或 data_quality 转 FAIL。",
            risk_assessment="主题集中与来源不完整需要额外提示。",
            user_emotion="calm",
        )
        session.add(trade)
        session.flush()
        trade_created = 1
    review = session.scalar(select(TradeReview).where(TradeReview.trade_journal_id == trade.id))
    if review is None:
        create_trade_review(
            session,
            trade,
            {
                "review_date": "2026-05-10",
                "current_price": 151.0,
                "benchmark_return": 0.01,
                "what_happened": "demo 复盘：产业链证据延续，但仍不足以得出投资建议。",
                "rule_update_suggestion": "缺完整来源时，优先降级股票池等级。",
                "next_action": "continue_watch",
            },
        )
        review_created = 1
    session.flush()
    return trade_created, review_created


def _attach_security_node_relations(session: Session) -> None:
    nodes = session.scalars(select(IndustryChainNode).where(IndustryChainNode.chain_name == "AI算力")).all()
    node_by_name = {node.name: node for node in nodes}
    securities = session.scalars(select(SecurityMaster)).all()
    for security in securities:
        concepts = set(_loads_list(security.concept_tags) + _loads_list(security.main_products) + [security.industry_level_2])
        matched = [
            node
            for node in nodes
            if node.name in concepts or concepts.intersection(set(_loads_list(node.related_terms))) or security.industry_level_1 == node.chain_name
        ]
        if not matched and security.industry_level_1 == "AI算力" and "AI服务器" in node_by_name:
            matched = [node_by_name["AI服务器"]]
        upstream_ids = _dedupe_ints([node.id for node in matched])
        downstream_ids: list[int] = []
        for node in matched:
            downstream_ids.extend(_loads_ints(node.downstream_node_ids))
        security.upstream_node_ids = _dumps(upstream_ids)
        security.downstream_node_ids = _dumps(_dedupe_ints(downstream_ids))
    session.flush()
    for node in nodes:
        related_ids = [
            security.id
            for security in securities
            if node.id in set(_loads_ints(security.upstream_node_ids) + _loads_ints(security.downstream_node_ids))
        ]
        node.related_security_ids = _dumps(_dedupe_ints(related_ids))


def _find_security(session: Session, symbol: str) -> SecurityMaster | None:
    normalized = symbol.strip()
    return session.scalar(
        select(SecurityMaster)
        .where(SecurityMaster.symbol == normalized)
        .order_by(SecurityMaster.market.asc(), SecurityMaster.id.asc())
        .limit(1)
    )


def _matched_nodes(session: Session, text: str, affected_objects: list[str]) -> list[IndustryChainNode]:
    nodes = session.scalars(select(IndustryChainNode)).all()
    text_lower = text.lower()
    result: list[IndustryChainNode] = []
    for node in nodes:
        terms = [node.name, *_loads_list(node.related_terms)]
        if any(str(term).lower() in text_lower for term in terms if str(term).strip()) or node.name in affected_objects:
            result.append(node)
    if not result and any(term in text for term in ("AI", "英伟达", "NVIDIA", "算力", "资本开支")):
        result = session.scalars(select(IndustryChainNode).where(IndustryChainNode.chain_name == "AI算力")).all()
    return result


def _matched_securities(session: Session, text: str, nodes: list[IndustryChainNode], affected_objects: list[str]) -> list[SecurityMaster]:
    securities = session.scalars(select(SecurityMaster)).all()
    text_lower = text.lower()
    matched: list[SecurityMaster] = []
    for security in securities:
        terms = [security.symbol, security.name, security.company_name, *_loads_list(security.concept_tags), *_loads_list(security.main_products)]
        if any(str(term).lower() in text_lower for term in terms if str(term).strip()):
            matched.append(security)
            continue
        if set(_loads_list(security.concept_tags) + _loads_list(security.main_products)).intersection(affected_objects):
            matched.append(security)
    if not matched:
        related_ids: list[int] = []
        for node in nodes:
            related_ids.extend(_loads_ints(node.related_security_ids))
        if related_ids:
            matched = session.scalars(select(SecurityMaster).where(SecurityMaster.id.in_(_dedupe_ints(related_ids))).limit(12)).all()
    return _dedupe_by_id(matched)[:12]


def _affected_objects(text: str) -> list[str]:
    catalog = ["AI算力", "AI服务器", "光模块", "CPO", "PCB", "液冷", "电源", "GPU", "HBM", "数据中心", "云厂商资本开支"]
    result = [term for term in catalog if term.lower() in text.lower()]
    if "英伟达" in text or "NVIDIA" in text:
        result.extend(["AI服务器", "GPU", "云厂商资本开支"])
    if "资本开支" in text and "AI算力" not in result:
        result.append("AI算力")
    return _dedupe_strings(result)


def _event_data_quality_status(*, source_name: str, source_url: str, source_type: str, is_mock: bool) -> str:
    if is_mock:
        return "FAIL"
    if not source_name or not source_url:
        return "WARN"
    if source_type in SOCIAL_SOURCE_TYPES:
        return "WARN"
    return "PASS"


def _event_confidence(
    *,
    source_name: str,
    source_url: str,
    source_type: str,
    data_quality_status: str,
    affected_objects: list[str],
    securities: list[SecurityMaster],
    is_mock: bool,
) -> float:
    confidence = 38.0
    if source_name:
        confidence += 12.0
    if source_url:
        confidence += 16.0
    if source_type in HIGH_QUALITY_SOURCE_TYPES:
        confidence += 12.0
    if source_type in SOCIAL_SOURCE_TYPES:
        confidence -= 8.0
    confidence += min(len(affected_objects) * 4.0, 18.0)
    confidence += min(len(securities) * 2.0, 10.0)
    if data_quality_status == "FAIL" or is_mock:
        confidence = min(confidence, 45.0)
    if not source_name or not source_url:
        confidence = min(confidence, 50.0)
    return round(_clamp(confidence), 2)


def _event_strength(text: str, affected_objects: list[str], direction: str) -> float:
    strength = 45.0 + min(len(affected_objects) * 6.0, 24.0)
    if any(term in text for term in ("资本开支", "订单", "涨价", "出货量", "财报", "公告")):
        strength += 12.0
    if direction == "negative":
        strength += 4.0
    if direction == "uncertain":
        strength -= 8.0
    return round(_clamp(strength), 2)


def _impact_direction(text: str) -> str:
    negative = sum(1 for term in NEGATIVE_TERMS if term in text)
    positive = sum(1 for term in POSITIVE_TERMS if term in text)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    if positive or negative:
        return "neutral"
    return "uncertain"


def _duration_type(text: str, source_type: str) -> str:
    if source_type in SOCIAL_SOURCE_TYPES:
        return "short_term"
    if any(term in text for term in ("资本开支", "产能", "扩产", "订单", "财报")):
        return "medium_term"
    if any(term in text for term in ("政策", "产业趋势", "渗透率")):
        return "long_term"
    return "unknown"


def _logic_chain(title: str, objects: list[str], nodes: list[IndustryChainNode], securities: list[SecurityMaster], direction: str) -> str:
    node_names = " / ".join(node.name for node in nodes[:5]) or "待映射节点"
    security_names = " / ".join(f"{item.name}({item.symbol})" for item in securities[:5]) or "待映射股票"
    direction_text = {"positive": "偏正面", "negative": "偏负面", "neutral": "中性", "uncertain": "不确定"}.get(direction, "不确定")
    return f"{title} -> 影响对象：{' / '.join(objects) or '待确认'} -> 产业链节点：{node_names} -> 相关股票：{security_names} -> 初步方向：{direction_text}。需人工核验公告、财报或产业数据来源。"


def _risk_notes(data_quality: str, source_type: str, securities: list[SecurityMaster]) -> str:
    notes = ["该事件仅用于研究辅助，不构成交易指令。"]
    if data_quality != "PASS":
        notes.append(f"数据质量为 {data_quality}，不能展示为高置信度结论。")
    if source_type in SOCIAL_SOURCE_TYPES:
        notes.append("社媒/社区热度不能单独支持 S/A 观察等级，需要公告、财报或产业数据交叉验证。")
    if not securities:
        notes.append("尚未映射到具体股票，需补充公司产品和客户关系证据。")
    return "".join(notes)


def _evidence_tags(source_type: str, objects: list[str], data_quality: str) -> list[str]:
    tags = [source_type, data_quality]
    tags.extend(objects[:6])
    return _dedupe_strings(tags)


def _profile_data_quality_status(security: SecurityMaster, events: list[EvidenceEvent], pool: RetailStockPool | None) -> str:
    if pool and pool.pool_level in {"S", "A"} and events and all(event.data_quality_status == "PASS" for event in events[:3]):
        return "PASS"
    if security.data_source == "demo_seed" or any(event.data_quality_status == "FAIL" for event in events):
        return "WARN"
    return "WARN" if events else "FAIL"


def _profile_risk_tags(data_quality: str, pool: RetailStockPool | None, events: list[EvidenceEvent]) -> list[str]:
    tags = [f"数据质量{data_quality}"]
    if pool and pool.risk_score >= 70:
        tags.append("风险分较高")
    if any(event.is_mock for event in events):
        tags.append("含mock/fallback证据")
    if not events:
        tags.append("证据链不足")
    return tags


def _security_nodes(session: Session, security: SecurityMaster) -> list[IndustryChainNode]:
    ids = _dedupe_ints(_loads_ints(security.upstream_node_ids) + _loads_ints(security.downstream_node_ids))
    return _nodes_by_ids(session, ids)


def _nodes_by_ids(session: Session, ids: list[int]) -> list[IndustryChainNode]:
    if not ids:
        return []
    return session.scalars(select(IndustryChainNode).where(IndustryChainNode.id.in_(ids))).all()


def _chain_graph_node_payload(node: IndustryChainNode, session: Session) -> dict[str, Any]:
    related_ids = _loads_ints(node.related_security_ids)
    securities = session.scalars(select(SecurityMaster).where(SecurityMaster.id.in_(related_ids[:20] or [0]))).all()
    return {
        "id": node.id,
        "name": node.name,
        "node_type": node.node_type,
        "level": node.level,
        "chain_name": node.chain_name,
        "heat_score": round(float(node.heat_score or 0.0), 2),
        "trend_score": round(float(node.trend_score or 0.0), 2),
        "related_security_count": len(related_ids),
        "top_related_securities": [_security_payload(item) for item in securities[:6]],
        "key_metrics": _loads_list(node.key_metrics),
        "macro_drivers": _loads_list(node.macro_drivers),
        "visible_indicators": _loads_list(node.visible_indicators),
        "data_quality_status": "WARN",
    }


def _node_payload(node: IndustryChainNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "name": node.name,
        "chain_name": node.chain_name,
        "node_type": node.node_type,
        "heat_score": round(float(node.heat_score or 0.0), 2),
        "trend_score": round(float(node.trend_score or 0.0), 2),
        "related_terms": _loads_list(node.related_terms),
    }


def _security_payload(security: SecurityMaster) -> dict[str, Any]:
    return {
        "id": security.id,
        "symbol": security.symbol,
        "exchange": security.exchange,
        "market": security.market,
        "name": security.name,
        "company_name": security.company_name,
        "industry_level_1": security.industry_level_1,
        "industry_level_2": security.industry_level_2,
        "industry_level_3": security.industry_level_3,
        "concept_tags": _loads_list(security.concept_tags),
        "main_products": _loads_list(security.main_products),
        "business_summary": security.business_summary,
        "data_source": security.data_source,
        "source_confidence": security.source_confidence,
    }


def _event_payload(event: EvidenceEvent, session: Session | None = None) -> dict[str, Any]:
    securities = []
    nodes = []
    if session is not None:
        securities = [_security_payload(item) for item in _nodes_noop_security(session, _loads_ints(event.affected_security_ids))]
        nodes = [_node_payload(item) for item in _nodes_by_ids(session, _loads_ints(event.affected_node_ids))]
    return {
        "id": event.id,
        "event_time": event.event_time.isoformat(),
        "title": event.title,
        "summary": event.summary,
        "source_name": event.source_name,
        "source_url": event.source_url,
        "source_type": event.source_type,
        "affected_objects": _loads_list(event.affected_objects),
        "affected_node_ids": _loads_ints(event.affected_node_ids),
        "affected_security_ids": _loads_ints(event.affected_security_ids),
        "affected_nodes": nodes,
        "affected_securities": securities,
        "impact_direction": event.impact_direction,
        "impact_strength": event.impact_strength,
        "confidence": event.confidence,
        "duration_type": event.duration_type,
        "logic_chain": event.logic_chain,
        "risk_notes": event.risk_notes,
        "evidence_tags": _loads_list(event.evidence_tags),
        "is_mock": event.is_mock,
        "data_quality_status": event.data_quality_status,
        "boundary": INVESTMENT_BOUNDARY,
    }


def _nodes_noop_security(session: Session, ids: list[int]) -> list[SecurityMaster]:
    if not ids:
        return []
    return session.scalars(select(SecurityMaster).where(SecurityMaster.id.in_(ids))).all()


def _pool_payload(pool: RetailStockPool, security: SecurityMaster | None, session: Session) -> dict[str, Any]:
    events = session.scalars(select(EvidenceEvent).where(EvidenceEvent.id.in_(_loads_ints(pool.key_evidence_event_ids) or [0]))).all()
    nodes = _nodes_by_ids(session, _loads_ints(pool.related_node_ids))
    return {
        "id": pool.id,
        "security": _security_payload(security) if security else None,
        "security_id": pool.security_id,
        "pool_level": pool.pool_level,
        "pool_reason": pool.pool_reason,
        "thesis_summary": pool.thesis_summary,
        "key_evidence_event_ids": _loads_ints(pool.key_evidence_event_ids),
        "related_node_ids": _loads_ints(pool.related_node_ids),
        "related_nodes": [_node_payload(node) for node in nodes],
        "trend_score": pool.trend_score,
        "industry_heat_score": pool.industry_heat_score,
        "evidence_score": pool.evidence_score,
        "valuation_score": pool.valuation_score,
        "quality_score": pool.quality_score,
        "risk_score": pool.risk_score,
        "tenbagger_score": pool.tenbagger_score,
        "conviction_score": pool.conviction_score,
        "user_note": pool.user_note,
        "status": pool.status,
        "invalidation_conditions": _loads_list(pool.invalidation_conditions),
        "next_tracking_tasks": _loads_list(pool.next_tracking_tasks),
        "data_quality_status": _pool_data_quality(events),
        "boundary": INVESTMENT_BOUNDARY,
    }


def _trend_payload(trend: TrendSignal | None, score: StockScore | None) -> dict[str, Any]:
    return {
        "trend_score": trend.trend_score if trend else score.trend_score if score else None,
        "final_score": score.final_score if score else None,
        "rating": score.rating if score else None,
        "is_ma_bullish": trend.is_ma_bullish if trend else None,
        "is_breakout_120d": trend.is_breakout_120d if trend else None,
        "is_breakout_250d": trend.is_breakout_250d if trend else None,
        "volume_expansion_ratio": trend.volume_expansion_ratio if trend else None,
        "trend_confirmed": bool(trend and trend.trend_score >= 60 and (trend.is_ma_bullish or trend.is_breakout_120d or trend.is_breakout_250d)),
        "note": "没有价格趋势确认时，不标记为趋势确认。",
    }


def _portfolio_payload(portfolio: RetailPortfolio) -> dict[str, Any]:
    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "benchmark": portfolio.benchmark,
        "user_id": portfolio.user_id,
        "cash": portfolio.cash,
        "created_at": portfolio.created_at.isoformat(),
    }


def _review_payload(review: TradeReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "trade_journal_id": review.trade_journal_id,
        "review_date": review.review_date.isoformat(),
        "holding_period_days": review.holding_period_days,
        "pnl": review.pnl,
        "pnl_pct": review.pnl_pct,
        "benchmark_return": review.benchmark_return,
        "excess_return": review.excess_return,
        "result_type": review.result_type,
        "attribution_logic": review.attribution_logic,
        "what_happened": review.what_happened,
        "what_expected": review.what_expected,
        "error_category": review.error_category,
        "should_update_model_rules": review.should_update_model_rules,
        "rule_update_suggestion": review.rule_update_suggestion,
        "next_action": review.next_action,
        "review_questions": review_questions(),
        "boundary": INVESTMENT_BOUNDARY,
    }


def payload_for_event(event: EvidenceEvent, session: Session) -> dict[str, Any]:
    return _event_payload(event, session)


def payload_for_pool(pool: RetailStockPool, session: Session) -> dict[str, Any]:
    security = session.get(SecurityMaster, pool.security_id)
    return _pool_payload(pool, security, session)


def payload_for_review(review: TradeReview) -> dict[str, Any]:
    return _review_payload(review)


def trade_payload(trade: TradeJournal, session: Session) -> dict[str, Any]:
    security = session.get(SecurityMaster, trade.security_id)
    return {
        "id": trade.id,
        "portfolio_id": trade.portfolio_id,
        "security": _security_payload(security) if security else None,
        "security_id": trade.security_id,
        "trade_date": trade.trade_date.isoformat(),
        "action": trade.action,
        "price": trade.price,
        "quantity": trade.quantity,
        "position_weight_after_trade": trade.position_weight_after_trade,
        "trade_reason": trade.trade_reason,
        "linked_evidence_event_ids": _loads_ints(trade.linked_evidence_event_ids),
        "linked_stock_pool_id": trade.linked_stock_pool_id,
        "expected_scenario": trade.expected_scenario,
        "invalidation_condition": trade.invalidation_condition,
        "risk_assessment": trade.risk_assessment,
        "user_emotion": trade.user_emotion,
        "created_at": trade.created_at.isoformat(),
        "boundary": INVESTMENT_BOUNDARY,
    }


def list_evidence_events(
    session: Session,
    *,
    market: str | None = None,
    industry: str | None = None,
    chain_node: str | None = None,
    security: str | None = None,
    impact_direction: str | None = None,
    confidence_min: float | None = None,
    source_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_retail_demo_data(session)
    query = select(EvidenceEvent).order_by(EvidenceEvent.event_time.desc(), EvidenceEvent.id.desc())
    if impact_direction:
        query = query.where(EvidenceEvent.impact_direction == impact_direction)
    if confidence_min is not None:
        query = query.where(EvidenceEvent.confidence >= confidence_min)
    if source_type:
        query = query.where(EvidenceEvent.source_type == source_type)
    if start_date:
        query = query.where(EvidenceEvent.event_time >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
    if end_date:
        query = query.where(EvidenceEvent.event_time <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc))
    rows = session.scalars(query.limit(max(limit * 3, limit))).all()
    filtered: list[EvidenceEvent] = []
    for event in rows:
        if market or industry or security:
            securities = _nodes_noop_security(session, _loads_ints(event.affected_security_ids))
            if market and not any(item.market == market for item in securities):
                continue
            if industry and not any(industry in {item.industry_level_1, item.industry_level_2} for item in securities):
                continue
            if security and not any(security in {item.symbol, item.name} for item in securities):
                continue
        if chain_node:
            nodes = _nodes_by_ids(session, _loads_ints(event.affected_node_ids))
            if not any(chain_node in {node.name, node.chain_name} for node in nodes):
                continue
        filtered.append(event)
        if len(filtered) >= limit:
            break
    return [_event_payload(event, session) for event in filtered]


def list_stock_pool(session: Session, *, pool_level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    ensure_retail_demo_data(session)
    query = select(RetailStockPool).order_by(RetailStockPool.pool_level.asc(), RetailStockPool.conviction_score.desc())
    if pool_level and pool_level in POOL_LEVELS:
        query = query.where(RetailStockPool.pool_level == pool_level)
    return [payload_for_pool(pool, session) for pool in session.scalars(query.limit(limit)).all()]


def _latest_trend_for_symbol(session: Session, symbol: str) -> TrendSignal | None:
    return session.scalars(select(TrendSignal).where(TrendSignal.stock_code == symbol).order_by(TrendSignal.trade_date.desc()).limit(1)).first()


def _latest_score_for_symbol(session: Session, symbol: str) -> StockScore | None:
    return session.scalars(select(StockScore).where(StockScore.stock_code == symbol).order_by(StockScore.trade_date.desc()).limit(1)).first()


def _latest_trend_score(session: Session, symbol: str) -> float:
    trend = _latest_trend_for_symbol(session, symbol)
    if trend:
        return _clamp(float(trend.trend_score or 0.0) * 4.0)
    score = _latest_score_for_symbol(session, symbol)
    return _clamp(float(score.trend_score or 0.0) * 4.0) if score else 0.0


def _latest_stock_final_score(session: Session, symbol: str) -> float:
    score = _latest_score_for_symbol(session, symbol)
    return _clamp(float(score.final_score or 0.0)) if score else 0.0


def _pool_risk_score(event: EvidenceEvent, security: SecurityMaster) -> float:
    score = 42.0
    if event.data_quality_status == "FAIL":
        score += 28.0
    elif event.data_quality_status == "WARN":
        score += 12.0
    if event.source_type in SOCIAL_SOURCE_TYPES:
        score += 16.0
    if event.impact_direction == "negative":
        score += 18.0
    if security.data_source == "demo_seed":
        score += 8.0
    return _clamp(score)


def _pool_thesis_summary(security: SecurityMaster, event: EvidenceEvent) -> str:
    return f"{security.name}({security.symbol}) 的研究线索来自“{event.title}”。当前仅表示观察优先级，需继续核验证据来源、趋势结构、估值与证伪条件。"


def _default_invalidation_conditions(security: SecurityMaster, event: EvidenceEvent) -> list[str]:
    return [
        f"{security.industry_level_2 or security.industry_level_1} 相关订单或需求被公告/财报证伪",
        "价格趋势跌破关键均线且相对强度持续走弱",
        f"核心证据事件“{event.title}”的来源被证伪或缺少后续确认",
    ]


def _default_tracking_tasks(security: SecurityMaster, event: EvidenceEvent) -> list[str]:
    return [
        f"核验 {security.name} 最新公告/财报是否支撑该事件逻辑",
        "补充产业数据或价格数据，避免只依赖热词",
        "检查组合中同产业链节点是否过度集中",
    ]


def _pool_data_quality(events: list[EvidenceEvent]) -> str:
    if not events:
        return "FAIL"
    if any(event.data_quality_status == "FAIL" for event in events):
        return "FAIL"
    if any(event.data_quality_status == "WARN" for event in events):
        return "WARN"
    return "PASS"


def _business_summary(name: str, industry1: str, industry2: str, products: list[str]) -> str:
    product_text = "、".join(products) if products else industry2 or industry1
    return f"{name} 当前在系统中映射到 {industry1}/{industry2 or '未细分'}，核心关注产品为 {product_text}。该描述用于研究辅助，需用公司公告和财报继续核验。"


def _infer_products(industry1: str, industry2: str, concepts: list[Any]) -> list[str]:
    products = [str(item) for item in concepts if str(item).strip()][:4]
    if industry2 and industry2 not in products:
        products.insert(0, industry2)
    if industry1 == "AI算力":
        for item in ["AI服务器", "光模块", "液冷", "PCB"]:
            if item in concepts and item not in products:
                products.append(item)
    return _dedupe_strings(products)[:6]


def _revenue_drivers(industry: str, concepts: list[Any]) -> list[str]:
    if industry == "AI算力" or "AI算力" in concepts:
        return ["AI资本开支", "云厂商订单", "高速互联升级", "产品迭代"]
    return [f"{industry or '所属行业'}需求", "订单增速", "产品价格"]


def _cost_drivers(industry: str, concepts: list[Any]) -> list[str]:
    if industry == "AI算力" or "PCB" in concepts:
        return ["芯片/器件成本", "铜价", "产能利用率", "汇率"]
    return ["原材料价格", "人工成本", "汇率"]


def _profit_drivers(industry: str, concepts: list[Any]) -> list[str]:
    if industry == "AI算力" or "光模块" in concepts:
        return ["高端产品占比", "毛利率", "海外客户结构", "规模效应"]
    return ["毛利率", "费用率", "产能利用率"]


def _macro_sensitivities(industry: str, concepts: list[Any]) -> list[str]:
    if industry == "AI算力" or "AI算力" in concepts:
        return ["AI资本开支", "美元指数", "利率", "铜价", "电价"]
    return ["利率", "汇率", "原材料价格", "终端需求"]


def _exposure_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"name": name, "weight": round(weight, 4)} for name, weight in counter.most_common()]


def _node_name_map(session: Session, node_ids: list[int]) -> dict[int, str]:
    if not node_ids:
        return {}
    return {node.id: node.name for node in session.scalars(select(IndustryChainNode).where(IndustryChainNode.id.in_(node_ids))).all()}


def _correlation_warnings(position_rows: list[dict[str, Any]], node_names: dict[int, str]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for idx, left in enumerate(position_rows):
        for right in position_rows[idx + 1 :]:
            overlap = set(left["theme_exposure"]).intersection(right["theme_exposure"])
            node_overlap = set(left["chain_node_exposure"]).intersection(right["chain_node_exposure"])
            same_industry = left["industry_exposure"] == right["industry_exposure"]
            if same_industry or len(overlap) >= 2 or node_overlap:
                warnings.append(
                    {
                        "securities": [left["security"], right["security"]],
                        "reason": "同产业/主题/产业链节点暴露重叠",
                        "overlap_themes": sorted(overlap),
                        "overlap_nodes": [node_names.get(node_id, str(node_id)) for node_id in sorted(node_overlap)],
                        "risk_note": "这类持仓可能不是完全分散，而是同一产业趋势下的多节点押注。",
                    }
                )
    return warnings[:12]


def _portfolio_risk_alerts(
    positions: list[dict[str, Any]],
    industries: list[dict[str, Any]],
    themes: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
) -> list[str]:
    alerts: list[str] = []
    for position in positions:
        if position["weight"] >= 0.35:
            alerts.append(f"{position['security']['name']} 单票权重 {position['weight']:.0%}，存在集中度风险。")
    if industries and industries[0]["weight"] >= 0.55:
        alerts.append(f"组合中 {industries[0]['weight']:.0%} 暴露在 {industries[0]['name']}，需要确认是否为主动同向押注。")
    if themes and themes[0]["weight"] >= 0.60:
        alerts.append(f"主题 {themes[0]['name']} 权重 {themes[0]['weight']:.0%}，可能存在伪分散风险。")
    if nodes and nodes[0]["weight"] >= 0.45:
        alerts.append(f"产业链节点 {nodes[0]['name']} 权重 {nodes[0]['weight']:.0%}，需跟踪单一节点证据变化。")
    if correlations:
        alerts.append("检测到高相关持仓，建议复核是否都依赖同一产业趋势或宏观因子。")
    if not alerts:
        alerts.append("未触发集中度阈值，但组合暴露仍需定期复核。")
    return alerts


def _linked_events(session: Session, trade: TradeJournal) -> list[EvidenceEvent]:
    ids = _loads_ints(trade.linked_evidence_event_ids)
    if not ids:
        return []
    return session.scalars(select(EvidenceEvent).where(EvidenceEvent.id.in_(ids))).all()


def _review_attribution(
    trade: TradeJournal,
    events: list[EvidenceEvent],
    pnl_pct: float,
    excess_return: float,
    holding_period_days: int,
) -> tuple[str, str]:
    has_positive = any(event.impact_direction == "positive" for event in events)
    has_negative = any(event.impact_direction == "negative" for event in events)
    if trade.user_emotion in {"FOMO", "fear", "revenge"} and pnl_pct < 0:
        return "timing_bad", "emotion_error"
    if trade.position_weight_after_trade >= 0.35 and pnl_pct < 0:
        return "position_size_bad", "sizing_error"
    if abs(excess_return) < 0.02:
        return "market_beta", "macro_error"
    if pnl_pct > 0 and has_positive and not has_negative:
        return "thesis_correct", "no_error"
    if pnl_pct < 0 and has_positive and holding_period_days < 30:
        return "timing_bad", "timing_error"
    if pnl_pct < 0:
        return "thesis_wrong", "logic_error"
    return "luck", "no_error"


def _default_what_happened(security: SecurityMaster | None, pnl_pct: float, events: list[EvidenceEvent]) -> str:
    name = security.name if security else "该标的"
    event_text = "；".join(event.title for event in events[:3]) or "未关联证据"
    return f"{name} 复盘期收益 {pnl_pct:.2%}，关联证据：{event_text}。需人工确认收益来源是否来自原始逻辑。"


def _rule_update_suggestion(error_category: str) -> str:
    mapping = {
        "logic_error": "补充反证清单和证据来源权重，避免单一叙事进入高等级观察。",
        "timing_error": "加入趋势确认和回撤阈值，避免逻辑成立但节奏过早。",
        "sizing_error": "加入单票和同产业链权重上限。",
        "emotion_error": "记录情绪标签，FOMO/fear/revenge 交易不自动提升股票池等级。",
        "macro_error": "加入宏观敏感变量和市场 beta 判断。",
    }
    return mapping.get(error_category, "暂无需要新增的模型规则。")


def _next_review_action(result_type: str, error_category: str) -> str:
    if result_type == "failure" and error_category in {"logic_error", "data_error"}:
        return "downgrade_pool"
    if result_type == "failure":
        return "add_risk_tag"
    if result_type == "success":
        return "continue_watch"
    return "continue_watch"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _loads_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return [value] if value else []
        return parsed if isinstance(parsed, list) else []
    return []


def _loads_ints(value: Any) -> list[int]:
    result: list[int] = []
    for item in _loads_list(value):
        try:
            result.append(int(item))
        except Exception:
            continue
    return result


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dedupe_strings(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _dedupe_ints(items: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dedupe_by_id(items: list[SecurityMaster]) -> list[SecurityMaster]:
    seen: set[int] = set()
    result: list[SecurityMaster] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result


def _number(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _level_rank(level: str) -> int:
    return {"BANNED": -1, "C": 0, "B": 1, "A": 2, "S": 3}.get(level, 0)


@dataclass(frozen=True)
class RetailEvidenceEvent:
    event_key: str
    published_date: date
    title: str
    summary: str
    source: str
    source_kind: str
    source_confidence: float
    matched_keywords: tuple[str, ...]
    related_industries: tuple[str, ...]
    related_stocks: tuple[str, ...]
    signal_types: tuple[str, ...]
    trend_evidence: bool
    risk_flags: tuple[str, ...]
    falsification_conditions: tuple[str, ...]
    strength: float
    social_only: bool
    source_url: str = ""


@dataclass(frozen=True)
class RetailStockEvidenceMapping:
    stock_code: str
    stock_name: str
    industry_name: str
    event_count: int
    direct_event_count: int
    industry_event_count: int
    social_event_count: int
    social_only_event_count: int
    evidence_score: float
    industry_logic: str
    company_logic: str
    trend_logic: str
    risk_alert: str
    falsification_condition: str
    only_social_heat: bool
    event_keys: tuple[str, ...] = field(default_factory=tuple)
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RetailStockPoolCandidate:
    stock_code: str
    stock_name: str
    industry_name: str
    grade: str
    data_quality_status: str
    conviction_score: float
    evidence_score: float
    industry_heat_score: float
    trend_score: float
    quality_score: float
    valuation_score: float
    risk_score: float
    industry_logic: str
    company_logic: str
    trend_logic: str
    risk_alert: str
    falsification_condition: str
    only_social_heat: bool
    rationale: tuple[str, ...] = field(default_factory=tuple)
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RetailPortfolioExposure:
    total_weight: float
    industry_exposure: tuple[dict[str, Any], ...]
    grade_exposure: tuple[dict[str, Any], ...]
    quality_exposure: tuple[dict[str, Any], ...]
    crowded_industries: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RetailTradeReviewInput:
    stock_code: str
    stock_name: str
    action: str
    entry_candidate: RetailStockPoolCandidate
    exit_candidate: RetailStockPoolCandidate | None
    realized_return: float
    holding_days: int
    exit_reason: str = ""


@dataclass(frozen=True)
class RetailTradeReviewAttribution:
    stock_code: str
    stock_name: str
    action: str
    realized_return: float
    outcome: str
    primary_driver: str
    secondary_driver: str
    attribution_breakdown: dict[str, float]
    review: str


@dataclass(frozen=True)
class RetailTradeReviewSummary:
    trades: tuple[RetailTradeReviewAttribution, ...]
    driver_summary: tuple[dict[str, Any], ...]
    average_return: float
    win_rate: float


StockEvidenceMapping = RetailStockEvidenceMapping
StockPoolCandidate = RetailStockPoolCandidate
TradeReviewInput = RetailTradeReviewInput


def extract_evidence_events(
    rows: list[Any],
    *,
    industry_rules: list[IndustryMappingRule] | None = None,
) -> list[RetailEvidenceEvent]:
    events: list[RetailEvidenceEvent] = []
    for row in rows:
        title = str(_rr_field(row, "title", "")).strip()
        summary = str(_rr_field(row, "summary", _rr_field(row, "content", ""))).strip()
        source = str(_rr_field(row, "source", "unknown") or "unknown")
        source_kind = str(_rr_field(row, "source_kind", "news") or "news")
        source_confidence = _rr_clamp(
            _rr_float(_rr_field(row, "source_confidence", _rr_default_source_confidence(source_kind))),
            0.0,
            1.0,
        )
        matched_keywords = tuple(_rr_string_list(_rr_field(row, "matched_keywords", [])))
        related_industries = tuple(_rr_string_list(_rr_field(row, "related_industries", [])))
        related_stocks = tuple(_rr_string_list(_rr_field(row, "related_stocks", [])))
        text = " ".join(part for part in (title, summary) if part).lower()
        if not related_industries and industry_rules:
            related_industries = tuple(_rr_infer_industries_from_text(text, matched_keywords, industry_rules))
        trend_evidence = any(hint in text for hint in _RR_TREND_HINTS)
        risk_flags = tuple(sorted({hint for hint in _RR_RISK_HINTS if hint in text}))
        signal_types = _rr_signal_types(
            source_kind=source_kind,
            industries=related_industries,
            stocks=related_stocks,
            trend_evidence=trend_evidence,
            risk_flags=risk_flags,
        )
        social_only = source_kind in _RR_SOCIAL_SOURCE_KINDS and "industry" not in signal_types and "company" not in signal_types
        falsification_conditions = _rr_falsification_conditions(
            related_industries=related_industries,
            related_stocks=related_stocks,
            trend_evidence=trend_evidence,
            risk_flags=risk_flags,
        )
        strength = _rr_event_strength(
            source_kind=source_kind,
            source_confidence=source_confidence,
            industry_count=len(related_industries),
            stock_count=len(related_stocks),
            trend_evidence=trend_evidence,
            risk_count=len(risk_flags),
            social_only=social_only,
        )
        events.append(
            RetailEvidenceEvent(
                event_key=_rr_event_key(title, _rr_field(row, "source_url", ""), _rr_field(row, "published_at", None)),
                published_date=_rr_to_date(_rr_field(row, "published_at", date.today())),
                title=title,
                summary=summary,
                source=source,
                source_kind=source_kind,
                source_confidence=round(source_confidence, 2),
                matched_keywords=matched_keywords,
                related_industries=related_industries,
                related_stocks=related_stocks,
                signal_types=signal_types,
                trend_evidence=trend_evidence,
                risk_flags=risk_flags,
                falsification_conditions=falsification_conditions,
                strength=round(strength, 2),
                social_only=social_only,
                source_url=str(_rr_field(row, "source_url", "")),
            )
        )
    return sorted(events, key=lambda item: (item.published_date, item.strength, item.event_key), reverse=True)


def map_evidence_events_to_stocks(
    events: list[RetailEvidenceEvent],
    stocks: list[Any],
    *,
    industry_rules: list[IndustryMappingRule] | None = None,
) -> list[RetailStockEvidenceMapping]:
    mappings: list[RetailStockEvidenceMapping] = []
    for stock in stocks:
        stock_code = str(_rr_field(stock, "code"))
        stock_name = str(_rr_field(stock, "name", stock_code))
        industry_name = _rr_stock_industry_name(stock, industry_rules)
        matched_rows: list[tuple[RetailEvidenceEvent, bool, bool, float]] = []
        for event in events:
            direct_match = stock_code in event.related_stocks or stock_name.lower() in f"{event.title} {event.summary}".lower()
            industry_match = bool(industry_name and industry_name in event.related_industries)
            if not direct_match and not industry_match:
                continue
            weight = event.strength * (1.0 if direct_match else 0.55)
            if event.source_kind in _RR_SOCIAL_SOURCE_KINDS:
                weight *= 0.9
            matched_rows.append((event, direct_match, industry_match, weight))
        if not matched_rows:
            continue
        matched_rows.sort(key=lambda item: (item[3], item[0].published_date), reverse=True)
        direct_count = sum(1 for _, direct, _, _ in matched_rows if direct)
        industry_count = sum(1 for _, _, industry_match, _ in matched_rows if industry_match)
        social_count = sum(1 for event, _, _, _ in matched_rows if event.source_kind in _RR_SOCIAL_SOURCE_KINDS)
        social_only_count = sum(1 for event, _, _, _ in matched_rows if event.social_only)
        weights = [weight for _, _, _, weight in matched_rows]
        evidence_score = _rr_clamp(
            sum(weights[:3]) / max(min(len(weights), 3), 1)
            + min(24.0, len(matched_rows) * 7.0)
            + direct_count * 6.0,
            0.0,
            100.0,
        )
        industry_titles = [event.title for event, _, industry_match, _ in matched_rows if industry_match][:2]
        company_titles = [event.title for event, direct, _, _ in matched_rows if direct][:2]
        trend_titles = [event.title for event, _, _, _ in matched_rows if event.trend_evidence][:2]
        risk_flags = _rr_dedupe([flag for event, _, _, _ in matched_rows for flag in event.risk_flags])
        falsification_conditions = _rr_dedupe(
            [condition for event, _, _, _ in matched_rows for condition in event.falsification_conditions]
        )
        source_refs = tuple(
            {
                "title": event.title,
                "url": event.source_url,
                "source": event.source,
                "source_kind": event.source_kind,
            }
            for event, _, _, _ in matched_rows[:5]
        )
        mappings.append(
            RetailStockEvidenceMapping(
                stock_code=stock_code,
                stock_name=stock_name,
                industry_name=industry_name,
                event_count=len(matched_rows),
                direct_event_count=direct_count,
                industry_event_count=industry_count,
                social_event_count=social_count,
                social_only_event_count=social_only_count,
                evidence_score=round(evidence_score, 2),
                industry_logic="；".join(industry_titles) if industry_titles else "",
                company_logic="；".join(company_titles) if company_titles else "",
                trend_logic="；".join(trend_titles) if trend_titles else "",
                risk_alert="；".join(risk_flags) if risk_flags else "",
                falsification_condition="；".join(falsification_conditions) if falsification_conditions else "",
                only_social_heat=len(matched_rows) == social_only_count and social_only_count > 0,
                event_keys=tuple(event.event_key for event, _, _, _ in matched_rows),
                source_refs=source_refs,
            )
        )
    return sorted(mappings, key=lambda item: (item.evidence_score, item.event_count, item.stock_code), reverse=True)


def score_stock_pool_candidates(
    stocks: list[Any],
    *,
    evidence_mappings_by_code: dict[str, RetailStockEvidenceMapping],
    latest_trend_by_code: dict[str, Any],
    latest_heat_by_industry_name: dict[str, Any],
    latest_score_by_code: dict[str, Any] | None = None,
    latest_fundamental_by_code: dict[str, Any] | None = None,
    data_gate_by_code: dict[str, ResearchDataGate] | None = None,
) -> list[RetailStockPoolCandidate]:
    candidates: list[RetailStockPoolCandidate] = []
    score_by_code = latest_score_by_code or {}
    fundamental_by_code = latest_fundamental_by_code or {}
    gate_by_code = data_gate_by_code or {}
    for stock in stocks:
        stock_code = str(_rr_field(stock, "code"))
        stock_name = str(_rr_field(stock, "name", stock_code))
        mapping = evidence_mappings_by_code.get(stock_code)
        score = score_by_code.get(stock_code)
        fundamental = fundamental_by_code.get(stock_code)
        industry_name = mapping.industry_name if mapping else str(_rr_field(stock, "industry_level1", ""))
        trend = latest_trend_by_code.get(stock_code)
        heat = latest_heat_by_industry_name.get(industry_name)
        gate = gate_by_code.get(stock_code) or assess_research_data_gate(stock=stock, score=score, fundamental=fundamental)
        evidence_score = _rr_candidate_evidence_score(mapping, score)
        industry_heat_score = round(_rr_heat_score_100(heat), 2)
        trend_score = round(_rr_trend_score_100(trend, score), 2)
        quality_score = round(_rr_quality_score_100(gate, score), 2)
        valuation_score = round(_rr_valuation_score_100(stock, fundamental), 2)
        risk_score = round(_rr_risk_score_100(stock, trend, score), 2)
        conviction_score = round(
            0.25 * evidence_score
            + 0.20 * industry_heat_score
            + 0.20 * trend_score
            + 0.15 * quality_score
            + 0.10 * valuation_score
            - 0.10 * risk_score,
            2,
        )
        industry_logic = mapping.industry_logic if mapping and mapping.industry_logic else str(_rr_field(heat, "explanation", ""))
        company_logic = mapping.company_logic if mapping and mapping.company_logic else _rr_company_logic(stock, fundamental, score)
        trend_logic = mapping.trend_logic if mapping and mapping.trend_logic else str(_rr_field(trend, "explanation", ""))
        risk_alert = mapping.risk_alert if mapping and mapping.risk_alert else assess_stock_risk(stock, trend).explanation
        falsification_condition = mapping.falsification_condition if mapping and mapping.falsification_condition else _rr_default_falsification_condition(industry_name, trend)
        grade = _rr_grade_candidate(
            conviction_score=conviction_score,
            data_quality_status=gate.status,
            only_social_heat=bool(mapping.only_social_heat) if mapping else False,
            industry_logic=industry_logic,
            company_logic=company_logic,
            trend_logic=trend_logic,
            risk_alert=risk_alert,
            falsification_condition=falsification_condition,
        )
        rationale = _rr_candidate_rationale(
            evidence_score=evidence_score,
            industry_heat_score=industry_heat_score,
            trend_score=trend_score,
            quality_score=quality_score,
            valuation_score=valuation_score,
            risk_score=risk_score,
            gate=gate,
            only_social_heat=bool(mapping.only_social_heat) if mapping else False,
        )
        candidates.append(
            RetailStockPoolCandidate(
                stock_code=stock_code,
                stock_name=stock_name,
                industry_name=industry_name,
                grade=grade,
                data_quality_status=gate.status,
                conviction_score=conviction_score,
                evidence_score=evidence_score,
                industry_heat_score=industry_heat_score,
                trend_score=trend_score,
                quality_score=quality_score,
                valuation_score=valuation_score,
                risk_score=risk_score,
                industry_logic=industry_logic,
                company_logic=company_logic,
                trend_logic=trend_logic,
                risk_alert=risk_alert,
                falsification_condition=falsification_condition,
                only_social_heat=bool(mapping.only_social_heat) if mapping else False,
                rationale=rationale,
                source_refs=mapping.source_refs if mapping else (),
            )
        )
    return sorted(candidates, key=lambda item: (item.conviction_score, item.evidence_score, item.stock_code), reverse=True)


def analyze_portfolio_exposure(
    positions: list[Any],
    candidates_by_code: dict[str, RetailStockPoolCandidate],
) -> RetailPortfolioExposure:
    normalized_positions = _rr_normalized_positions(positions)
    industry_totals: dict[str, float] = {}
    grade_totals: dict[str, float] = {}
    quality_totals: dict[str, float] = {}
    warnings: list[str] = []
    low_quality_weight = 0.0
    social_only_weight = 0.0
    for stock_code, weight in normalized_positions:
        candidate = candidates_by_code.get(stock_code)
        if candidate is None:
            continue
        industry = candidate.industry_name or "未分类"
        industry_totals[industry] = industry_totals.get(industry, 0.0) + weight
        grade_totals[candidate.grade] = grade_totals.get(candidate.grade, 0.0) + weight
        quality_totals[candidate.data_quality_status] = quality_totals.get(candidate.data_quality_status, 0.0) + weight
        if candidate.data_quality_status == "FAIL":
            low_quality_weight += weight
        if candidate.only_social_heat:
            social_only_weight += weight
    industry_exposure = tuple(
        {"industry": industry, "weight": round(weight, 4), "weight_pct": round(weight * 100, 2)}
        for industry, weight in sorted(industry_totals.items(), key=lambda item: item[1], reverse=True)
    )
    crowded_industries = tuple(item for item in industry_exposure if float(item["weight"]) >= 0.35)
    grade_exposure = tuple(
        {"grade": grade, "weight": round(weight, 4), "weight_pct": round(weight * 100, 2)}
        for grade, weight in sorted(grade_totals.items(), key=lambda item: item[1], reverse=True)
    )
    quality_exposure = tuple(
        {"status": status, "weight": round(weight, 4), "weight_pct": round(weight * 100, 2)}
        for status, weight in sorted(quality_totals.items(), key=lambda item: item[1], reverse=True)
    )
    if crowded_industries:
        warnings.append(f"主题集中度偏高：{crowded_industries[0]['industry']} 权重 {crowded_industries[0]['weight_pct']:.1f}%。")
    if low_quality_weight > 0.0:
        warnings.append(f"数据门控 FAIL 暴露 {low_quality_weight * 100:.1f}%，需限制仓位。")
    if social_only_weight > 0.0:
        warnings.append(f"纯社媒热词暴露 {social_only_weight * 100:.1f}%，不能上调为高确信仓位。")
    return RetailPortfolioExposure(
        total_weight=round(sum(weight for _, weight in normalized_positions), 4),
        industry_exposure=industry_exposure,
        grade_exposure=grade_exposure,
        quality_exposure=quality_exposure,
        crowded_industries=crowded_industries,
        warnings=tuple(warnings),
    )


def attribute_trade_reviews(trades: list[RetailTradeReviewInput]) -> RetailTradeReviewSummary:
    attributions: list[RetailTradeReviewAttribution] = []
    driver_totals: dict[str, int] = {}
    returns: list[float] = []
    wins = 0
    for trade in trades:
        entry = trade.entry_candidate
        exit_candidate = trade.exit_candidate or entry
        returns.append(trade.realized_return)
        if trade.realized_return > 0:
            wins += 1
        breakdown = _rr_attribution_breakdown(entry, exit_candidate, trade.realized_return)
        ordered = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)
        primary_driver = ordered[0][0]
        secondary_driver = ordered[1][0] if len(ordered) > 1 else ordered[0][0]
        driver_totals[primary_driver] = driver_totals.get(primary_driver, 0) + 1
        outcome = "win" if trade.realized_return > 0 else "flat" if trade.realized_return == 0 else "loss"
        review = (
            f"{trade.stock_name} {trade.action} 复盘：收益 {trade.realized_return:.1%}，"
            f"主因 {primary_driver}，次因 {secondary_driver}；持有 {trade.holding_days} 天。"
            f"{trade.exit_reason or '需继续校验执行与证据演变。'}"
        )
        attributions.append(
            RetailTradeReviewAttribution(
                stock_code=trade.stock_code,
                stock_name=trade.stock_name,
                action=trade.action,
                realized_return=trade.realized_return,
                outcome=outcome,
                primary_driver=primary_driver,
                secondary_driver=secondary_driver,
                attribution_breakdown={key: round(value, 4) for key, value in breakdown.items()},
                review=review,
            )
        )
    driver_summary = tuple(
        {"driver": driver, "count": count}
        for driver, count in sorted(driver_totals.items(), key=lambda item: item[1], reverse=True)
    )
    return RetailTradeReviewSummary(
        trades=tuple(attributions),
        driver_summary=driver_summary,
        average_return=round(sum(returns) / max(len(returns), 1), 6),
        win_rate=round(wins / max(len(trades), 1), 4),
    )


_RR_SOCIAL_SOURCE_KINDS = {"community", "social", "forum"}
_RR_TREND_HINTS = (
    "订单",
    "扩产",
    "涨价",
    "突破",
    "新高",
    "需求",
    "capex",
    "backlog",
    "shipment",
    "出货",
    "ai服务器",
    "gpu",
    "数据中心",
    "景气",
)
_RR_RISK_HINTS = ("风险", "减持", "监管", "库存", "价格战", "延期", "诉讼", "波动", "竞争加剧", "产能过剩", "回撤")


def _rr_field(row: Any, field: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _rr_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _rr_clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _rr_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                loaded = json.loads(text)
            except Exception:
                loaded = []
            return [str(item) for item in loaded if str(item).strip()]
        return [text]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _rr_default_source_confidence(source_kind: str) -> float:
    return {"news": 0.9, "rss": 0.8, "community": 0.56, "social": 0.45}.get(source_kind, 0.6)


def _rr_to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _rr_event_key(title: str, source_url: Any, published_at: Any) -> str:
    payload = f"{title}|{source_url}|{_rr_to_date(published_at).isoformat()}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()[:12]


def _rr_infer_industries_from_text(text: str, matched_keywords: tuple[str, ...], rules: list[IndustryMappingRule]) -> list[str]:
    scores: list[tuple[float, str]] = []
    keyword_set = {keyword.lower() for keyword in matched_keywords}
    for rule in rules:
        matched = []
        for keyword in rule.keywords:
            normalized = keyword.lower()
            if normalized in keyword_set or normalized in text:
                matched.append(keyword)
        if matched:
            scores.append((len(set(matched)) + (0.5 if rule.industry.lower() in text else 0.0), rule.industry))
    return [industry for _, industry in sorted(scores, reverse=True)[:3]]


def _rr_signal_types(
    *,
    source_kind: str,
    industries: tuple[str, ...],
    stocks: tuple[str, ...],
    trend_evidence: bool,
    risk_flags: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    if industries:
        result.append("industry")
    if stocks:
        result.append("company")
    if trend_evidence:
        result.append("trend")
    if risk_flags:
        result.append("risk")
    if source_kind in _RR_SOCIAL_SOURCE_KINDS:
        result.append("social")
    return tuple(result)


def _rr_falsification_conditions(
    *,
    related_industries: tuple[str, ...],
    related_stocks: tuple[str, ...],
    trend_evidence: bool,
    risk_flags: tuple[str, ...],
) -> tuple[str, ...]:
    conditions: list[str] = []
    for industry_name in related_industries[:2]:
        conditions.append(f"{industry_name} 热度未转化为订单、收入和利润兑现")
    if related_stocks:
        conditions.append("公司公告与订单证据无法继续验证")
    if trend_evidence:
        conditions.append("趋势强度回落且无法守住中期均线")
    if risk_flags:
        conditions.append("风险提示演变为正式公告或财务损失")
    return tuple(_rr_dedupe(conditions))


def _rr_event_strength(
    *,
    source_kind: str,
    source_confidence: float,
    industry_count: int,
    stock_count: int,
    trend_evidence: bool,
    risk_count: int,
    social_only: bool,
) -> float:
    score = source_confidence * 55.0
    if source_kind in {"rss", "news"}:
        score += 10.0
    if source_kind in _RR_SOCIAL_SOURCE_KINDS:
        score -= 5.0
    score += min(15.0, industry_count * 7.0)
    score += min(15.0, stock_count * 7.0)
    if trend_evidence:
        score += 10.0
    if risk_count:
        score += min(8.0, risk_count * 3.0)
    if social_only:
        score *= 0.6
    return _rr_clamp(score, 0.0, 100.0)


def _rr_stock_industry_name(stock: Any, industry_rules: list[IndustryMappingRule] | None) -> str:
    industry_name = str(_rr_field(stock, "industry_level1", "") or "")
    if industry_name and industry_name not in {"未分类", "未知", "unknown"}:
        return industry_name
    if not industry_rules:
        return industry_name
    match = map_stock_industry(stock, industry_rules)
    return match.industry if match else industry_name


def _rr_candidate_evidence_score(mapping: RetailStockEvidenceMapping | None, score: Any | None) -> float:
    mapped_score = mapping.evidence_score if mapping else 0.0
    confidence_score = _rr_float(_rr_field(score, "evidence_confidence", 0.0)) * 100.0
    news_score = _rr_float(_rr_field(score, "news_confidence", 0.0)) * 100.0
    if mapped_score <= 0.0:
        return round(confidence_score * 0.7 + news_score * 0.3, 2)
    return round(_rr_clamp(mapped_score * 0.7 + confidence_score * 0.2 + news_score * 0.1, 0.0, 100.0), 2)


def _rr_heat_score_100(heat: Any | None) -> float:
    return _rr_clamp(_rr_float(_rr_field(heat, "heat_score", 0.0)) / 30.0 * 100.0, 0.0, 100.0)


def _rr_trend_score_100(trend: Any | None, score: Any | None) -> float:
    value = _rr_float(_rr_field(trend, "trend_score", _rr_field(score, "trend_score", 0.0)))
    return _rr_clamp(value / 25.0 * 100.0, 0.0, 100.0)


def _rr_quality_score_100(gate: ResearchDataGate, score: Any | None) -> float:
    if _rr_float(gate.score) > 0:
        return _rr_clamp(_rr_float(gate.score), 0.0, 100.0)
    return _rr_clamp(
        _rr_float(_rr_field(score, "source_confidence", 0.0)) * 25.0
        + _rr_float(_rr_field(score, "data_confidence", 0.0)) * 35.0
        + _rr_float(_rr_field(score, "fundamental_confidence", 0.0)) * 40.0,
        0.0,
        100.0,
    )


def _rr_valuation_score_100(stock: Any, fundamental: Any | None) -> float:
    market_cap = _rr_float(_rr_field(stock, "market_cap", 0.0))
    if market_cap <= 0:
        base = 45.0
    elif market_cap <= 300:
        base = 82.0
    elif market_cap <= 800:
        base = 74.0
    elif market_cap <= 2000:
        base = 64.0
    else:
        base = 48.0
    growth = max(_rr_float(_rr_field(fundamental, "revenue_growth_yoy", 0.0)), _rr_float(_rr_field(fundamental, "profit_growth_yoy", 0.0)))
    cashflow_quality = _rr_float(_rr_field(fundamental, "cashflow_quality", 0.0))
    debt_ratio = _rr_float(_rr_field(fundamental, "debt_ratio", 0.0))
    base += min(14.0, max(growth, 0.0) * 0.22)
    base += min(8.0, max(cashflow_quality - 0.8, 0.0) * 12.0)
    if debt_ratio > 0.65:
        base -= 8.0
    return _rr_clamp(base, 0.0, 100.0)


def _rr_risk_score_100(stock: Any, trend: Any | None, score: Any | None) -> float:
    penalty = _rr_float(_rr_field(score, "risk_penalty", 0.0))
    if penalty <= 0:
        penalty = assess_stock_risk(stock, trend).penalty
    return _rr_clamp(penalty * 10.0, 0.0, 100.0)


def _rr_company_logic(stock: Any, fundamental: Any | None, score: Any | None) -> str:
    if fundamental is not None:
        return (
            f"营收同比{_rr_float(_rr_field(fundamental, 'revenue_growth_yoy', 0.0)):.1f}%，"
            f"利润同比{_rr_float(_rr_field(fundamental, 'profit_growth_yoy', 0.0)):.1f}%，"
            f"现金流质量{_rr_float(_rr_field(fundamental, 'cashflow_quality', 0.0)):.2f}。"
        )
    explanation = str(_rr_field(score, "explanation", "")).strip()
    if explanation:
        return explanation
    return f"{_rr_field(stock, 'name', _rr_field(stock, 'code', ''))} 缺少连续基本面，需要补财报与订单证据。"


def _rr_default_falsification_condition(industry_name: str, trend: Any | None) -> str:
    conditions = [f"{industry_name or '主题'} 无法兑现为订单和收入"] if industry_name else []
    if trend is not None:
        conditions.append("趋势走弱且无法维持中期均线支撑")
    return "；".join(_rr_dedupe(conditions)) or "核心证据无法继续验证"


def _rr_grade_candidate(
    *,
    conviction_score: float,
    data_quality_status: str,
    only_social_heat: bool,
    industry_logic: str,
    company_logic: str,
    trend_logic: str,
    risk_alert: str,
    falsification_condition: str,
) -> str:
    if conviction_score >= 82:
        grade = "S"
    elif conviction_score >= 72:
        grade = "A"
    elif conviction_score >= 58:
        grade = "B"
    else:
        grade = "C"
    if only_social_heat:
        return "C"
    if data_quality_status == "FAIL" and grade in {"S", "A"}:
        grade = "B" if conviction_score >= 58 else "C"
    has_required = all(
        item.strip()
        for item in (industry_logic, company_logic, trend_logic, risk_alert, falsification_condition)
    )
    if grade in {"S", "A"} and not has_required:
        grade = "B" if conviction_score >= 58 else "C"
    return grade


def _rr_candidate_rationale(
    *,
    evidence_score: float,
    industry_heat_score: float,
    trend_score: float,
    quality_score: float,
    valuation_score: float,
    risk_score: float,
    gate: ResearchDataGate,
    only_social_heat: bool,
) -> tuple[str, ...]:
    reasons = [
        f"evidence {evidence_score:.1f}",
        f"industry_heat {industry_heat_score:.1f}",
        f"trend {trend_score:.1f}",
        f"quality {quality_score:.1f}",
        f"valuation {valuation_score:.1f}",
        f"risk {risk_score:.1f}",
        f"gate {gate.status}",
    ]
    if only_social_heat:
        reasons.append("仅有社媒热词且无产业证据")
    reasons.extend(gate.reasons[:2])
    return tuple(_rr_dedupe(reasons))


def _rr_normalized_positions(positions: list[Any]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for row in positions:
        code = str(_rr_field(row, "stock_code", _rr_field(row, "code", ""))).strip()
        if not code:
            continue
        weight = _rr_float(_rr_field(row, "weight", _rr_field(row, "exposure", 0.0)))
        rows.append((code, max(weight, 0.0)))
    total = sum(weight for _, weight in rows)
    if total <= 0:
        equal = round(1.0 / max(len(rows), 1), 4)
        return [(code, equal) for code, _ in rows]
    return [(code, round(weight / total, 6)) for code, weight in rows]


def _rr_attribution_breakdown(
    entry: RetailStockPoolCandidate,
    exit_candidate: RetailStockPoolCandidate,
    realized_return: float,
) -> dict[str, float]:
    direction = 1.0 if realized_return >= 0 else -1.0
    evidence_delta = (exit_candidate.evidence_score - entry.evidence_score) * direction
    trend_delta = (exit_candidate.trend_score - entry.trend_score) * direction
    industry_delta = (exit_candidate.industry_heat_score - entry.industry_heat_score) * direction
    risk_delta = (entry.risk_score - exit_candidate.risk_score) * direction
    valuation_component = (entry.valuation_score - 55.0) if realized_return >= 0 else (70.0 - entry.valuation_score)
    buckets = {
        "evidence_break" if realized_return < 0 else "evidence_validation": max(evidence_delta, 0.0) + max(abs(realized_return) * 100 - 5, 0.0) * 0.12,
        "trend_reversal" if realized_return < 0 else "trend_follow_through": max(trend_delta, 0.0) + abs(realized_return) * 100 * 0.08,
        "industry_reversal" if realized_return < 0 else "industry_tailwind": max(industry_delta, 0.0) + abs(realized_return) * 100 * 0.06,
        "risk_exposure" if realized_return < 0 else "risk_control": max(risk_delta, 0.0) + max(entry.risk_score - 20.0, 0.0) * 0.05,
        "valuation_mismatch" if realized_return < 0 else "valuation_discipline": max(valuation_component, 0.0) * 0.1,
    }
    return {key: round(value, 4) for key, value in buckets.items()}


def _rr_dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
