from __future__ import annotations

import importlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Industry, IndustryHeat, Stock, StockScore, TrendSignal


@dataclass
class ChainSeedBundle:
    layers: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    regions: list[dict[str, Any]]
    default_focus_node_key: str | None
    available: bool
    error: str | None = None


def build_chain_overview(session: Session, market: str | None) -> dict[str, object]:
    bundle = _load_chain_seed_contract()
    graph = _build_graph_snapshot(session, bundle, market)
    nodes = [_node_overview_payload(item, graph) for item in graph["ordered_nodes"]]
    max_node_heat = max((float(row["heat_score"]) for row in nodes), default=0.0)
    return {
        "summary": {
            "market": market or "ALL",
            "layer_count": len(bundle.layers),
            "node_count": len(bundle.nodes),
            "edge_count": len(bundle.edges),
            "region_count": len(bundle.regions),
            "active_node_count": sum(1 for row in nodes if float(row["heat_score"]) > 0),
            "average_heat_score": _round(sum(float(row["heat_score"]) for row in nodes) / max(len(nodes), 1)),
            "latest_heat_date": _iso_date(graph["latest_heat_date"]),
            "snapshot_date": _iso_date(graph["latest_heat_date"] or graph["latest_score_date"] or graph["latest_trend_date"]),
            "latest_score_date": _iso_date(graph["latest_score_date"]),
            "latest_trend_date": _iso_date(graph["latest_trend_date"]),
            "max_heat_score": _round(max_node_heat),
            "seed_status": _seed_status_payload(bundle),
        },
        "layers": bundle.layers,
        "nodes": nodes,
        "edges": [_edge_payload(edge, graph) for edge in bundle.edges],
        "regions": [_region_payload(region, graph) for region in bundle.regions],
        "default_focus_node_key": bundle.default_focus_node_key,
    }


def build_chain_node_detail(session: Session, node_key: str, market: str | None) -> dict[str, object] | None:
    bundle = _load_chain_seed_contract()
    graph = _build_graph_snapshot(session, bundle, market)
    node = graph["node_by_key"].get(node_key)
    if node is None:
        return None

    metrics = graph["metrics_by_node_key"][node_key]
    upstream, downstream, same_layer = _adjacent_nodes(node_key, graph)
    mapped_industries = [_industry_payload(row) for row in metrics["industry_rows"]]
    regions = [_region_payload(region, graph) for region in graph["regions_by_node_key"].get(node_key, [])]
    local_edges = [
        _edge_payload(edge, graph)
        for edge in graph["edges"]
        if edge.get("source") == node_key
        or edge.get("target") == node_key
        or str(edge.get("source")) in {str(item["node_key"]) for item in upstream + downstream}
        and str(edge.get("target")) in {str(item["node_key"]) for item in upstream + downstream}
    ]
    heat_explanation = [part for part in str(metrics["explanation"] or "").split("；") if part]

    return {
        "node": _node_overview_payload(node, graph),
        "market": market or "ALL",
        "heat": {
            "heat_score": metrics["heat_score"],
            "base_heat_score": metrics["base_heat_score"],
            "propagated_heat_score": metrics["propagated_heat_score"],
            "industry_heat_score": metrics["industry_heat_score"],
            "stock_signal_score": metrics["stock_signal_score"],
            "industry_count": len(metrics["industry_rows"]),
            "stock_count": len(metrics["stocks"]),
            "leading_stock_count": len(metrics["leading_stocks"]),
            "evidence_status": metrics["evidence_status"],
            "explanation": metrics["explanation"],
        },
        "mapped_industries": mapped_industries,
        "edges": local_edges,
        "leader_stocks": metrics["leading_stocks"],
        "leading_stocks": metrics["leading_stocks"],
        "regions": regions,
        "indicators": _indicator_payloads(node),
        "anchor_companies": list(node.get("anchor_companies") or []),
        "tags": list(node.get("tags") or []),
        "upstream": upstream,
        "downstream": downstream,
        "same_layer": same_layer,
        "heat_explanation": heat_explanation,
        "seed_status": _seed_status_payload(bundle),
    }


def build_chain_geo(session: Session, node_key: str, market: str | None) -> dict[str, object] | None:
    bundle = _load_chain_seed_contract()
    graph = _build_graph_snapshot(session, bundle, market)
    node = graph["node_by_key"].get(node_key)
    if node is None:
        return None

    focus_score = graph["metrics_by_node_key"][node_key]["heat_score"]
    focus_regions = graph["regions_by_node_key"].get(node_key, [])
    routes: list[dict[str, object]] = []
    seen_route_keys: set[tuple[str, str]] = set()
    for edge in bundle.edges:
        if edge.get("source") != node_key and edge.get("target") != node_key:
            continue
        other_key = edge.get("target") if edge.get("source") == node_key else edge.get("source")
        if other_key not in graph["node_by_key"]:
            continue
        other_regions = graph["regions_by_node_key"].get(other_key, [])
        for focus_region in focus_regions or bundle.regions[:1]:
            for region in other_regions:
                route_key = (str(focus_region.get("region_key")), str(region.get("region_key")))
                if route_key in seen_route_keys or route_key[0] == route_key[1]:
                    continue
                seen_route_keys.add(route_key)
                other_score = graph["metrics_by_node_key"][other_key]["heat_score"]
                route_heat = _round((focus_score + other_score) / 2.0)
                routes.append(
                    {
                        "from_key": focus_region.get("region_key"),
                        "to_key": region.get("region_key"),
                        "from_node_key": node_key,
                        "to_node_key": other_key,
                        "to_node_name": graph["node_by_key"][other_key].get("name"),
                        "region_key": region.get("region_key"),
                        "region_label": region.get("label"),
                        "relation_type": edge.get("relation_type") or "",
                        "flow": edge.get("flow") or "",
                        "weight": _round(float(edge.get("weight") or 0.0), 4),
                        "heat": route_heat,
                        "intensity": _intensity(route_heat),
                        "route_heat": route_heat,
                    }
                )
    if not routes:
        ranked_regions = sorted(
            [_region_payload(region, graph) for region in bundle.regions],
            key=lambda row: float(row["heat_score"]),
            reverse=True,
        )[:4]
        hub = ranked_regions[0] if ranked_regions else None
        if hub:
            for region in ranked_regions[1:]:
                route_heat = _round((float(hub["heat_score"]) + float(region["heat_score"])) / 2.0)
                routes.append(
                    {
                        "from_key": hub["region_key"],
                        "to_key": region["region_key"],
                        "flow": "区域热力联动",
                        "weight": 0.4,
                        "heat": route_heat,
                        "intensity": _intensity(route_heat),
                        "route_heat": route_heat,
                    }
                )

    return {
        "node_key": node_key,
        "market": market or "ALL",
        "regions": [_region_payload(region, graph) for region in bundle.regions],
        "routes": sorted(routes, key=lambda row: (float(row["route_heat"]), float(row["weight"])), reverse=True),
        "seed_status": _seed_status_payload(bundle),
    }


def build_chain_timeline(session: Session, node_key: str, limit: int) -> dict[str, object] | None:
    bundle = _load_chain_seed_contract()
    node = {str(item.get("node_key")): item for item in bundle.nodes}.get(node_key)
    if node is None:
        return None

    industry_names = [str(item) for item in node.get("industry_names") or [] if str(item).strip()]
    if not industry_names:
        return {
            "node_key": node_key,
            "timeline": [],
            "summary": {
                "latest_trade_date": None,
                "point_count": 0,
                "max_heat_score": 0.0,
                "explanation": "该节点未配置映射行业，时间序列返回空结果。",
            },
            "seed_status": _seed_status_payload(bundle),
        }

    industries = session.scalars(select(Industry).where(Industry.name.in_(industry_names))).all()
    industry_by_id = {row.id: row for row in industries}
    industry_ids = list(industry_by_id.keys())
    if not industry_ids:
        return {
            "node_key": node_key,
            "timeline": [],
            "summary": {
                "latest_trade_date": None,
                "point_count": 0,
                "max_heat_score": 0.0,
                "explanation": "映射行业未出现在当前库中，时间序列热度为0。",
            },
            "seed_status": _seed_status_payload(bundle),
        }

    heat_rows = session.scalars(
        select(IndustryHeat)
        .where(IndustryHeat.industry_id.in_(industry_ids))
        .order_by(IndustryHeat.trade_date.desc(), IndustryHeat.industry_id.asc())
    ).all()

    grouped: dict[date, list[IndustryHeat]] = defaultdict(list)
    for row in heat_rows:
        grouped[row.trade_date].append(row)

    points: list[dict[str, object]] = []
    for trade_date, rows in sorted(grouped.items(), key=lambda item: item[0], reverse=True)[:limit]:
        avg_heat = sum(float(row.heat_score or 0.0) for row in rows) / max(len(rows), 1)
        points.append(
            {
                "trade_date": trade_date.isoformat(),
                "heat_score": _round(avg_heat / 30.0 * 100.0),
                "heat": _round(avg_heat / 30.0 * 100.0),
                "momentum": _round(avg_heat / 30.0 * 100.0),
                "intensity": _intensity(_round(avg_heat / 30.0 * 100.0)),
                "raw_heat_score": _round(avg_heat),
                "industry_count": len(rows),
                "label": f"{len(rows)}个映射行业",
                "summary": f"平均行业热度 {_round(avg_heat)}",
                "industries": [_industry_payload(industry_by_id.get(row.industry_id), heat=row) for row in rows],
            }
        )

    return {
        "node_key": node_key,
        "timeline": points,
        "summary": {
            "latest_trade_date": points[0]["trade_date"] if points else None,
            "point_count": len(points),
            "max_heat_score": max((float(row["heat_score"]) for row in points), default=0.0),
            "explanation": "节点时间序列按映射行业的 IndustryHeat 聚合。",
        },
        "seed_status": _seed_status_payload(bundle),
    }


def _build_graph_snapshot(session: Session, bundle: ChainSeedBundle, market: str | None) -> dict[str, Any]:
    nodes = [dict(item) for item in bundle.nodes]
    node_by_key = {str(item.get("node_key")): item for item in nodes if item.get("node_key")}
    edges = [dict(item) for item in bundle.edges]
    industries = session.scalars(select(Industry)).all()
    industry_by_name = {row.name: row for row in industries}
    latest_heat_date = session.scalars(select(IndustryHeat.trade_date).order_by(IndustryHeat.trade_date.desc()).limit(1)).first()
    latest_score_date = session.scalars(select(StockScore.trade_date).order_by(StockScore.trade_date.desc()).limit(1)).first()
    latest_trend_date = session.scalars(select(TrendSignal.trade_date).order_by(TrendSignal.trade_date.desc()).limit(1)).first()

    heat_by_industry_id: dict[int, IndustryHeat] = {}
    if latest_heat_date is not None:
        heat_by_industry_id = {
            row.industry_id: row
            for row in session.scalars(select(IndustryHeat).where(IndustryHeat.trade_date == latest_heat_date)).all()
        }

    stock_filters = [Stock.is_active.is_(True), Stock.listing_status == "listed", Stock.asset_type == "equity"]
    if market:
        stock_filters.append(Stock.market == market)
    stocks = session.scalars(select(Stock).where(*stock_filters)).all()
    stocks_by_industry: dict[str, list[Stock]] = defaultdict(list)
    all_stock_codes = []
    for stock in stocks:
        stocks_by_industry[stock.industry_level1].append(stock)
        all_stock_codes.append(stock.code)

    score_by_code: dict[str, StockScore] = {}
    if latest_score_date is not None and all_stock_codes:
        score_by_code = {
            row.stock_code: row
            for row in session.scalars(
                select(StockScore).where(StockScore.trade_date == latest_score_date, StockScore.stock_code.in_(all_stock_codes))
            ).all()
        }

    trend_by_code: dict[str, TrendSignal] = {}
    if latest_trend_date is not None and all_stock_codes:
        trend_by_code = {
            row.stock_code: row
            for row in session.scalars(
                select(TrendSignal).where(TrendSignal.trade_date == latest_trend_date, TrendSignal.stock_code.in_(all_stock_codes))
            ).all()
        }

    metrics_by_node_key: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = str(node.get("node_key"))
        metrics_by_node_key[key] = _compute_node_metrics(
            node=node,
            industry_by_name=industry_by_name,
            heat_by_industry_id=heat_by_industry_id,
            stocks_by_industry=stocks_by_industry,
            score_by_code=score_by_code,
            trend_by_code=trend_by_code,
            latest_heat_date=latest_heat_date,
            latest_score_date=latest_score_date,
            latest_trend_date=latest_trend_date,
        )

    propagated = defaultdict(float)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in metrics_by_node_key or target not in metrics_by_node_key:
            continue
        base_score = float(metrics_by_node_key[source]["base_heat_score"])
        weight = min(max(float(edge.get("weight") or 0.0), 0.0), 1.0)
        propagated[target] += base_score * weight * 0.18

    for key, metrics in metrics_by_node_key.items():
        metrics["propagated_heat_score"] = _round(propagated.get(key, 0.0))
        metrics["heat_score"] = _round(min(100.0, float(metrics["base_heat_score"]) + float(metrics["propagated_heat_score"])))
        if metrics["heat_score"] <= 0:
            metrics["explanation"] = metrics["explanation"] or "当前没有可用行业热度、评分或趋势数据。"

    regions_by_node_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for region in bundle.regions:
        for key in region.get("node_keys") or []:
            regions_by_node_key[str(key)].append(region)

    return {
        "ordered_nodes": nodes,
        "node_by_key": node_by_key,
        "edges": edges,
        "metrics_by_node_key": metrics_by_node_key,
        "regions_by_node_key": regions_by_node_key,
        "latest_heat_date": latest_heat_date,
        "latest_score_date": latest_score_date,
        "latest_trend_date": latest_trend_date,
    }


def _compute_node_metrics(
    *,
    node: dict[str, Any],
    industry_by_name: dict[str, Industry],
    heat_by_industry_id: dict[int, IndustryHeat],
    stocks_by_industry: dict[str, list[Stock]],
    score_by_code: dict[str, StockScore],
    trend_by_code: dict[str, TrendSignal],
    latest_heat_date: date | None,
    latest_score_date: date | None,
    latest_trend_date: date | None,
) -> dict[str, Any]:
    industry_rows: list[dict[str, Any]] = []
    stocks: list[Stock] = []
    seen_stock_codes: set[str] = set()
    for industry_name in [str(item) for item in node.get("industry_names") or [] if str(item).strip()]:
        industry = industry_by_name.get(industry_name)
        if industry is not None:
            heat = heat_by_industry_id.get(industry.id)
            industry_rows.append({"industry": industry, "heat": heat})
        for stock in stocks_by_industry.get(industry_name, []):
            if stock.code in seen_stock_codes:
                continue
            seen_stock_codes.add(stock.code)
            stocks.append(stock)

    heat_values = [float(row["heat"].heat_score or 0.0) for row in industry_rows if row["heat"] is not None]
    industry_heat_score = _round((sum(heat_values) / max(len(heat_values), 1)) / 30.0 * 55.0) if heat_values else 0.0

    scored_rows = [score_by_code.get(stock.code) for stock in stocks if score_by_code.get(stock.code) is not None]
    trend_rows = [trend_by_code.get(stock.code) for stock in stocks if trend_by_code.get(stock.code) is not None]
    avg_final = sum(float(row.final_score or 0.0) for row in scored_rows) / max(len(scored_rows), 1) if scored_rows else 0.0
    avg_trend = sum(float(row.trend_score or 0.0) for row in trend_rows) / max(len(trend_rows), 1) if trend_rows else 0.0
    watch_ratio = (
        sum(1 for row in scored_rows if str(row.rating) in {"强观察", "观察"}) / max(len(scored_rows), 1) if scored_rows else 0.0
    )
    stock_signal_score = _round(min(45.0, avg_final / 100.0 * 25.0 + avg_trend / 100.0 * 12.0 + watch_ratio * 8.0))
    base_heat_score = _round(min(100.0, industry_heat_score + stock_signal_score))

    evidence: list[str] = []
    if heat_values:
        evidence.append(f"{len(heat_values)}个映射行业有热度记录")
    elif latest_heat_date is not None and industry_rows:
        evidence.append("映射行业存在，但最新热度为0")
    elif industry_rows:
        evidence.append("映射行业存在，但暂无 IndustryHeat 数据")

    if scored_rows:
        evidence.append(f"{len(scored_rows)}只股票有评分，均值{avg_final:.1f}")
    if trend_rows:
        evidence.append(f"{len(trend_rows)}只股票有趋势信号，均值{avg_trend:.1f}")
    if stocks and not scored_rows and not trend_rows:
        date_hint = latest_score_date or latest_trend_date
        if date_hint is None:
            evidence.append("已映射股票，但暂无评分和趋势表数据")
        else:
            evidence.append(f"已映射股票，但{date_hint.isoformat()}无评分和趋势记录")

    if not industry_rows and not stocks:
        evidence_status = "no_mapping"
    elif base_heat_score > 0:
        evidence_status = "active"
    elif stocks or industry_rows:
        evidence_status = "mapped_only"
    else:
        evidence_status = "empty"

    leading_stocks = [_leading_stock_payload(stock, score_by_code.get(stock.code), trend_by_code.get(stock.code)) for stock in stocks]
    leading_stocks.sort(key=lambda row: (float(row["final_score"] or 0.0), float(row["trend_signal_score"] or 0.0)), reverse=True)

    return {
        "industry_rows": industry_rows,
        "stocks": stocks,
        "leading_stocks": leading_stocks[:8],
        "industry_heat_score": industry_heat_score,
        "stock_signal_score": stock_signal_score,
        "base_heat_score": base_heat_score,
        "propagated_heat_score": 0.0,
        "heat_score": base_heat_score,
        "evidence_status": evidence_status,
        "explanation": "；".join(evidence) if evidence else "当前没有可用行业热度、评分或趋势数据。",
    }


def _adjacent_nodes(node_key: str, graph: dict[str, Any]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    upstream: list[dict[str, object]] = []
    downstream: list[dict[str, object]] = []
    same_layer: list[dict[str, object]] = []
    node = graph["node_by_key"][node_key]
    same_layer_seen: set[str] = set()

    for edge in graph["edges"]:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if target == node_key and source in graph["node_by_key"]:
            payload = _adjacent_node_payload(source, edge, graph)
            upstream.append(payload)
            if graph["node_by_key"][source].get("layer") == node.get("layer") and source not in same_layer_seen:
                same_layer.append(payload)
                same_layer_seen.add(source)
        if source == node_key and target in graph["node_by_key"]:
            payload = _adjacent_node_payload(target, edge, graph)
            downstream.append(payload)
            if graph["node_by_key"][target].get("layer") == node.get("layer") and target not in same_layer_seen:
                same_layer.append(payload)
                same_layer_seen.add(target)

    upstream.sort(key=lambda row: float(row["heat_score"]), reverse=True)
    downstream.sort(key=lambda row: float(row["heat_score"]), reverse=True)
    same_layer.sort(key=lambda row: float(row["heat_score"]), reverse=True)
    return upstream, downstream, same_layer


def _adjacent_node_payload(node_key: str, edge: dict[str, Any], graph: dict[str, Any]) -> dict[str, object]:
    node = graph["node_by_key"][node_key]
    metrics = graph["metrics_by_node_key"][node_key]
    return {
        "node_key": node_key,
        "name": node.get("name"),
        "layer": node.get("layer"),
        "node_type": node.get("node_type"),
        "relation_type": edge.get("relation_type") or "",
        "flow": edge.get("flow") or "",
        "weight": _round(float(edge.get("weight") or 0.0), 4),
        "heat_score": metrics["heat_score"],
        "heat": metrics["heat_score"],
        "momentum": metrics["heat_score"],
        "intensity": _intensity(metrics["heat_score"]),
        "evidence_status": metrics["evidence_status"],
    }


def _node_overview_payload(node: dict[str, Any], graph: dict[str, Any]) -> dict[str, object]:
    key = str(node.get("node_key"))
    metrics = graph["metrics_by_node_key"][key]
    return {
        "node_key": key,
        "name": node.get("name"),
        "layer": node.get("layer"),
        "node_type": node.get("node_type"),
        "description": node.get("description") or "",
        "industry_names": list(node.get("industry_names") or []),
        "tags": list(node.get("tags") or []),
        "anchor_companies": list(node.get("anchor_companies") or []),
        "indicators": _indicator_payloads(node),
        "heat_score": metrics["heat_score"],
        "heat": metrics["heat_score"],
        "momentum": metrics["heat_score"],
        "intensity": _intensity(metrics["heat_score"]),
        "base_heat_score": metrics["base_heat_score"],
        "propagated_heat_score": metrics["propagated_heat_score"],
        "industry_heat_score": metrics["industry_heat_score"],
        "stock_signal_score": metrics["stock_signal_score"],
        "stock_count": len(metrics["stocks"]),
        "evidence_status": metrics["evidence_status"],
        "explanation": metrics["explanation"],
    }


def _edge_payload(edge: dict[str, Any], graph: dict[str, Any]) -> dict[str, object]:
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    source_score = float(graph["metrics_by_node_key"].get(source, {}).get("heat_score", 0.0))
    target_score = float(graph["metrics_by_node_key"].get(target, {}).get("heat_score", 0.0))
    return {
        "source": source,
        "target": target,
        "relation_type": edge.get("relation_type") or "",
        "flow": edge.get("flow") or "",
        "weight": _round(float(edge.get("weight") or 0.0), 4),
        "activity_score": _round((source_score + target_score) / 2.0),
        "heat": _round((source_score + target_score) / 2.0),
        "intensity": _intensity(_round((source_score + target_score) / 2.0)),
    }


def _region_payload(region: dict[str, Any], graph: dict[str, Any]) -> dict[str, object]:
    node_keys = [str(item) for item in region.get("node_keys") or []]
    scores = [float(graph["metrics_by_node_key"].get(key, {}).get("heat_score", 0.0)) for key in node_keys]
    heat_score = _round(sum(scores) / max(len(scores), 1)) if scores else 0.0
    x = float(region.get("x") or 0.0)
    y = float(region.get("y") or 0.0)
    if 0 <= x <= 100:
        x *= 10.0
    if 0 <= y <= 100:
        y *= 6.2
    return {
        "region_key": region.get("region_key"),
        "label": region.get("label"),
        "x": x,
        "y": y,
        "geo_role": region.get("geo_role") or "",
        "specialty": region.get("specialty") or "",
        "summary": region.get("specialty") or "",
        "node_keys": node_keys,
        "listed_hubs": list(region.get("listed_hubs") or []),
        "hubs": list(region.get("listed_hubs") or []),
        "industries": [str(graph["node_by_key"].get(key, {}).get("name") or key) for key in node_keys[:8]],
        "country_count": len(region.get("listed_hubs") or []),
        "share": _round(heat_score),
        "heat_score": heat_score,
        "heat": heat_score,
        "intensity": _intensity(heat_score),
    }


def _industry_payload(row: dict[str, Any] | Industry | None, heat: IndustryHeat | None = None) -> dict[str, object]:
    if isinstance(row, dict):
        industry = row.get("industry")
        heat = row.get("heat")
    else:
        industry = row
    if industry is None:
        return {
            "industry_id": None,
            "id": None,
            "name": "",
            "description": "",
            "trade_date": _iso_date(getattr(heat, "trade_date", None)),
            "heat_score": _round(float(getattr(heat, "heat_score", 0.0) or 0.0)),
            "heat": _round(float(getattr(heat, "heat_score", 0.0) or 0.0)),
        }
    return {
        "industry_id": industry.id,
        "id": industry.id,
        "name": industry.name,
        "description": industry.description,
        "trade_date": _iso_date(getattr(heat, "trade_date", None)),
        "heat_score": _round(float(getattr(heat, "heat_score", 0.0) or 0.0)),
        "heat": _round(float(getattr(heat, "heat_score", 0.0) or 0.0)),
        "heat_7d": _round(float(getattr(heat, "heat_7d", 0.0) or 0.0)),
        "heat_30d": _round(float(getattr(heat, "heat_30d", 0.0) or 0.0)),
    }


def _leading_stock_payload(stock: Stock, score: StockScore | None, trend: TrendSignal | None) -> dict[str, object]:
    return {
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "exchange": stock.exchange,
        "board": stock.board,
        "industry_level1": stock.industry_level1,
        "industry_level2": stock.industry_level2,
        "final_score": _round(float(score.final_score or 0.0)) if score else 0.0,
        "rating": score.rating if score else "仅映射",
        "industry_score": _round(float(score.industry_score or 0.0)) if score else 0.0,
        "company_score": _round(float(score.company_score or 0.0)) if score else 0.0,
        "stock_trend_score": _round(float(score.trend_score or 0.0)) if score else 0.0,
        "trend_signal_score": _round(float(trend.trend_score or 0.0)) if trend else 0.0,
        "is_ma_bullish": bool(trend.is_ma_bullish) if trend else False,
        "is_breakout_120d": bool(trend.is_breakout_120d) if trend else False,
        "is_breakout_250d": bool(trend.is_breakout_250d) if trend else False,
    }


def _seed_status_payload(bundle: ChainSeedBundle) -> dict[str, object]:
    return {
        "available": bundle.available,
        "error": bundle.error,
        "node_count": len(bundle.nodes),
        "edge_count": len(bundle.edges),
        "region_count": len(bundle.regions),
    }


def _indicator_payloads(node: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in list(node.get("indicators") or []):
        if not isinstance(item, dict):
            rows.append({"label": str(item), "value": None})
            continue
        rows.append(
            {
                "label": str(item.get("label") or item.get("name") or item.get("code") or "指标"),
                "value": item.get("value") if "value" in item else item.get("code"),
                "unit": item.get("unit") or "",
                "trend": item.get("trend") or item.get("type") or "",
                "change": item.get("change"),
                "weight": item.get("weight"),
            }
        )
    return rows


def _load_chain_seed_contract() -> ChainSeedBundle:
    try:
        module = importlib.import_module("app.services.chain_seed")
    except ModuleNotFoundError as exc:
        return ChainSeedBundle([], [], [], [], None, available=False, error=f"chain seed unavailable: {exc.name}")
    except Exception as exc:  # pragma: no cover
        return ChainSeedBundle([], [], [], [], None, available=False, error=f"chain seed import failed: {exc}")

    return ChainSeedBundle(
        layers=list(getattr(module, "CHAIN_LAYERS", []) or []),
        nodes=list(getattr(module, "CHAIN_NODES", []) or []),
        edges=list(getattr(module, "CHAIN_EDGES", []) or []),
        regions=list(getattr(module, "WORLD_REGIONS", []) or []),
        default_focus_node_key=getattr(module, "DEFAULT_FOCUS_NODE_KEY", None),
        available=True,
        error=None,
    )


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _round(value: float, digits: int = 2) -> float:
    return round(float(value or 0.0), digits)


def _intensity(value: float) -> float:
    return _round(min(max(float(value or 0.0) / 100.0, 0.0), 1.0), 4)
