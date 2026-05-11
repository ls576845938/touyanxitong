from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceEvent, RetailPortfolio, RetailPosition, RetailStockPool, SecurityMaster, TradeJournal, TradeReview
from app.db.session import get_session
from app.engines.retail_research_engine import (
    INVESTMENT_BOUNDARY,
    apply_stock_pool_gate,
    build_industry_chain_graph,
    build_portfolio_dashboard,
    build_security_research_profile,
    calculate_portfolio_exposure,
    create_trade_review,
    ensure_retail_demo_data,
    extract_evidence_event,
    list_evidence_events,
    list_stock_pool,
    payload_for_event,
    payload_for_pool,
    payload_for_review,
    recalculate_stock_pool_scores,
    refresh_position_weights,
    review_questions,
    trade_payload,
)

router = APIRouter(prefix="/api", tags=["retail-research"])


@router.get("/securities/{symbol}/research-profile")
def security_research_profile(symbol: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    payload = build_security_research_profile(session, symbol)
    if payload is None:
        raise HTTPException(status_code=404, detail="security not found")
    return payload


@router.get("/industry-chain/{chain_name}/graph")
def industry_chain_graph(chain_name: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return build_industry_chain_graph(session, chain_name)


@router.get("/evidence-events")
def evidence_events(
    market: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    chain_node: str | None = Query(default=None),
    security: str | None = Query(default=None),
    impact_direction: str | None = Query(default=None),
    confidence_min: float | None = Query(default=None, ge=0, le=100),
    source_type: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "events": list_evidence_events(
            session,
            market=market.upper() if market and market.upper() != "ALL" else None,
            industry=industry,
            chain_node=chain_node,
            security=security,
            impact_direction=impact_direction,
            confidence_min=confidence_min,
            source_type=source_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        ),
    }


@router.post("/evidence-events/extract")
def extract_evidence(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    event = extract_evidence_event(session, payload)
    return payload_for_event(event, session)


@router.post("/evidence-events")
def create_evidence_event(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    event = extract_evidence_event(session, payload)
    return {"boundary": INVESTMENT_BOUNDARY, "event": payload_for_event(event, session)}


@router.get("/evidence-events/{event_id}")
def evidence_event_detail(event_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    event = session.get(EvidenceEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evidence event not found")
    return payload_for_event(event, session)


@router.get("/retail-stock-pool")
def retail_stock_pool(
    pool_level: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "formula": "conviction_score = 0.25*evidence + 0.20*industry_heat + 0.20*trend + 0.15*quality + 0.10*valuation - 0.10*risk",
        "items": list_stock_pool(session, pool_level=pool_level, limit=limit),
    }


@router.post("/retail-stock-pool/add")
def add_retail_stock_pool(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    security = _security_from_payload(session, payload)
    if security is None:
        raise HTTPException(status_code=404, detail="security not found")
    pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
    if pool is None:
        pool = RetailStockPool(security_id=security.id)
        session.add(pool)
    pool.pool_level = str(payload.get("pool_level") or payload.get("level") or pool.pool_level or "C").upper()
    pool.pool_reason = str(payload.get("pool_reason") or payload.get("reason") or pool.pool_reason or "人工加入研究观察池")
    pool.thesis_summary = str(payload.get("thesis_summary") or pool.thesis_summary or "该条目为人工观察对象，需补齐证据链、风险提示和证伪条件。")
    pool.user_note = str(payload.get("user_note") or pool.user_note or "")
    pool.status = str(payload.get("status") or pool.status or "watching")
    pool.trend_score = _float_payload(payload, "trend_score", pool.trend_score)
    pool.industry_heat_score = _float_payload(payload, "industry_heat_score", pool.industry_heat_score)
    pool.evidence_score = _float_payload(payload, "evidence_score", pool.evidence_score)
    pool.valuation_score = _float_payload(payload, "valuation_score", pool.valuation_score)
    pool.quality_score = _float_payload(payload, "quality_score", pool.quality_score)
    pool.risk_score = _float_payload(payload, "risk_score", pool.risk_score)
    pool.tenbagger_score = _float_payload(payload, "tenbagger_score", pool.tenbagger_score)
    pool.key_evidence_event_ids = _json_list_payload(payload.get("key_evidence_event_ids"), pool.key_evidence_event_ids)
    pool.related_node_ids = _json_list_payload(payload.get("related_node_ids"), pool.related_node_ids)
    pool.invalidation_conditions = _json_list_payload(
        payload.get("invalidation_conditions"),
        pool.invalidation_conditions if pool.invalidation_conditions != "[]" else ["研究逻辑被公告/财报证伪", "趋势证据持续走弱"],
    )
    pool.next_tracking_tasks = _json_list_payload(
        payload.get("next_tracking_tasks"),
        pool.next_tracking_tasks if pool.next_tracking_tasks != "[]" else ["补充来源证据", "复核产业链位置", "检查组合集中度"],
    )
    apply_stock_pool_gate(pool, session)
    session.commit()
    return payload_for_pool(pool, session)


@router.post("/retail-stock-pool")
def create_retail_stock_pool(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    return add_retail_stock_pool(payload, session)


@router.post("/retail-stock-pool/update-level")
def update_retail_stock_pool_level(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    security = _security_from_payload(session, payload)
    pool = None
    if security is not None:
        pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
    if pool is None and payload.get("pool_id"):
        pool = session.get(RetailStockPool, int(payload["pool_id"]))
    if pool is None:
        raise HTTPException(status_code=404, detail="stock pool item not found")
    requested_level = str(payload.get("pool_level") or payload.get("level") or pool.pool_level).upper()
    pool.pool_level = requested_level
    if payload.get("user_note") is not None:
        pool.user_note = str(payload["user_note"])
    if payload.get("pool_reason") is not None:
        pool.pool_reason = str(payload["pool_reason"])
    apply_stock_pool_gate(pool, session)
    session.commit()
    result = payload_for_pool(pool, session)
    result["requested_level"] = requested_level
    result["applied_level"] = pool.pool_level
    return result


@router.post("/retail-stock-pool/recalculate-scores")
def recalculate_retail_stock_pool(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {**recalculate_stock_pool_scores(session), "boundary": INVESTMENT_BOUNDARY}


@router.get("/retail-stock-pool/{security_id}")
def retail_stock_pool_detail(security_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    pool = None
    try:
        numeric_id = int(security_id)
        pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == numeric_id))
    except ValueError:
        security = session.scalar(select(SecurityMaster).where(SecurityMaster.symbol == security_id).limit(1))
        if security is not None:
            pool = session.scalar(select(RetailStockPool).where(RetailStockPool.security_id == security.id))
    if pool is None:
        raise HTTPException(status_code=404, detail="stock pool item not found")
    return payload_for_pool(pool, session)


@router.get("/portfolio/{portfolio_id}/dashboard")
def portfolio_dashboard(portfolio_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    payload = build_portfolio_dashboard(session, portfolio_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return payload


@router.get("/portfolio/{portfolio_id}/dashboard/exposure/correlation-warning")
def portfolio_dashboard_exposure_correlation_warning(
    portfolio_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    payload = build_portfolio_dashboard(session, portfolio_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "portfolio": payload["portfolio"],
        "exposure": {
            "overview": payload["overview"],
            "positions": payload["positions"],
            "industry_exposure": payload["industry_exposure"],
            "theme_exposure": payload["theme_exposure"],
            "chain_node_exposure": payload["chain_node_exposure"],
        },
        "correlation_warning": {
            "warnings": payload["correlation_warnings"],
            "risk_alerts": payload["risk_alerts"],
        },
    }


@router.post("/portfolio/{portfolio_id}/positions")
def upsert_portfolio_position(portfolio_id: int, payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    portfolio = session.get(RetailPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    security = _security_from_payload(session, payload)
    if security is None:
        raise HTTPException(status_code=404, detail="security not found")
    position = session.scalar(select(RetailPosition).where(RetailPosition.portfolio_id == portfolio_id, RetailPosition.security_id == security.id))
    if position is None:
        position = RetailPosition(portfolio_id=portfolio_id, security_id=security.id)
        session.add(position)
    position.quantity = _float_payload(payload, "quantity", position.quantity)
    position.avg_cost = _float_payload(payload, "avg_cost", position.avg_cost)
    position.market_value = _float_payload(payload, "market_value", position.market_value)
    position.unrealized_pnl = _float_payload(payload, "unrealized_pnl", position.unrealized_pnl)
    position.industry_exposure = str(payload.get("industry_exposure") or security.industry_level_1)
    position.theme_exposure = _json_list_payload(payload.get("theme_exposure"), security.concept_tags)
    position.chain_node_exposure = _json_list_payload(
        payload.get("chain_node_exposure"),
        security.upstream_node_ids if security.upstream_node_ids != "[]" else security.downstream_node_ids,
    )
    position.factor_tags = _json_list_payload(payload.get("factor_tags"), position.factor_tags)
    session.flush()
    refresh_position_weights(session, portfolio_id)
    session.commit()
    dashboard = build_portfolio_dashboard(session, portfolio_id)
    return dashboard or {}


@router.get("/portfolio/{portfolio_id}/exposure")
def portfolio_exposure(portfolio_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    payload = calculate_portfolio_exposure(session, portfolio_id)
    if not payload:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return {**payload, "boundary": INVESTMENT_BOUNDARY}


@router.get("/portfolio/{portfolio_id}/correlation-warning")
def portfolio_correlation_warning(portfolio_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    payload = calculate_portfolio_exposure(session, portfolio_id)
    if not payload:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return {
        "boundary": INVESTMENT_BOUNDARY,
        "warnings": payload["correlation_warnings"],
        "risk_alerts": payload["risk_alerts"],
    }


@router.post("/trade-journal")
def create_trade_journal(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    portfolio_id = int(payload.get("portfolio_id") or 1)
    portfolio = session.get(RetailPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    security = _security_from_payload(session, payload)
    if security is None:
        raise HTTPException(status_code=404, detail="security not found")
    trade_date = payload.get("trade_date")
    parsed_date = date.fromisoformat(str(trade_date)) if trade_date else date.today()
    trade = TradeJournal(
        portfolio_id=portfolio_id,
        security_id=security.id,
        trade_date=parsed_date,
        action=str(payload.get("action") or "watch"),
        price=_float_payload(payload, "price", 0.0),
        quantity=_float_payload(payload, "quantity", 0.0),
        position_weight_after_trade=_float_payload(payload, "position_weight_after_trade", 0.0),
        trade_reason=str(payload.get("trade_reason") or payload.get("reason") or "记录研究动作，非系统买卖建议。"),
        linked_evidence_event_ids=_json_list_payload(payload.get("linked_evidence_event_ids"), "[]"),
        linked_stock_pool_id=int(payload["linked_stock_pool_id"]) if payload.get("linked_stock_pool_id") else None,
        expected_scenario=str(payload.get("expected_scenario") or ""),
        invalidation_condition=str(payload.get("invalidation_condition") or ""),
        risk_assessment=str(payload.get("risk_assessment") or "需控制仓位、核验证据来源和组合集中度。"),
        user_emotion=str(payload.get("user_emotion") or "calm"),
    )
    session.add(trade)
    session.commit()
    return trade_payload(trade, session)


@router.get("/trade-journal")
def list_trade_journal(portfolio_id: int | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    query = select(TradeJournal).order_by(TradeJournal.trade_date.desc(), TradeJournal.id.desc())
    if portfolio_id:
        query = query.where(TradeJournal.portfolio_id == portfolio_id)
    rows = session.scalars(query.limit(200)).all()
    return {"boundary": INVESTMENT_BOUNDARY, "trades": [trade_payload(row, session) for row in rows]}


@router.get("/trade-journal/{trade_id}")
def trade_journal_detail(trade_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    trade = session.get(TradeJournal, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade journal not found")
    return trade_payload(trade, session)


@router.post("/trade-review")
def create_review(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    trade_id = int(payload.get("trade_journal_id") or payload.get("trade_id") or 0)
    trade = session.get(TradeJournal, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade journal not found")
    review = create_trade_review(session, trade, payload)
    session.commit()
    return payload_for_review(review)


@router.get("/trade-review")
def list_trade_review(
    portfolio_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_retail_demo_data(session)
    query = select(TradeReview).join(TradeJournal, TradeJournal.id == TradeReview.trade_journal_id).order_by(
        TradeReview.review_date.desc(),
        TradeReview.id.desc(),
    )
    if portfolio_id is not None:
        query = query.where(TradeJournal.portfolio_id == portfolio_id)
    rows = session.scalars(query.limit(limit)).all()
    return {"boundary": INVESTMENT_BOUNDARY, "reviews": [payload_for_review(row) for row in rows]}


@router.get("/trade-review/{trade_journal_id}")
def trade_review_detail(trade_journal_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    review = session.scalar(select(TradeReview).where(TradeReview.trade_journal_id == trade_journal_id))
    if review is None:
        return {
            "boundary": INVESTMENT_BOUNDARY,
            "trade_journal_id": trade_journal_id,
            "review": None,
            "review_questions": review_questions(),
        }
    return payload_for_review(review)


def _security_from_payload(session: Session, payload: dict[str, Any]) -> SecurityMaster | None:
    if payload.get("security_id"):
        security = session.get(SecurityMaster, int(payload["security_id"]))
        if security is not None:
            return security
    symbol = str(payload.get("symbol") or payload.get("stock_code") or "").strip()
    if not symbol:
        return None
    return session.scalar(select(SecurityMaster).where(SecurityMaster.symbol == symbol).order_by(SecurityMaster.market.asc()).limit(1))


def _float_payload(payload: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except Exception:
        return float(default or 0.0)


def _json_list_payload(value: Any, default: Any) -> str:
    if value is None:
        if isinstance(default, str):
            return default
        return _json_list_payload(default, "[]")
    if isinstance(value, str):
        return value if value.startswith("[") else f'["{value}"]'
    return __import__("json").dumps(value, ensure_ascii=False)
