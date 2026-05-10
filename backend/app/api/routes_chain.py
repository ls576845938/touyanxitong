from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.chain_graph_engine import (
    build_chain_geo,
    build_chain_node_detail,
    build_chain_overview,
    build_chain_timeline,
)

router = APIRouter(prefix="/api/chain", tags=["industry-chain"])


@router.get("/overview")
def chain_overview(
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    market_key = _normalize_market_filter(market)
    return build_chain_overview(session, market_key)


@router.get("/nodes/{node_key}")
def chain_node_detail(
    node_key: str,
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    market_key = _normalize_market_filter(market)
    payload = build_chain_node_detail(session, node_key, market_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="chain node not found")
    return payload


@router.get("/geo")
def chain_geo(
    node_key: str = Query(..., min_length=1),
    market: str | None = Query(default=None, description="ALL, A, US or HK"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    market_key = _normalize_market_filter(market)
    payload = build_chain_geo(session, node_key, market_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="chain node not found")
    return payload


@router.get("/timeline")
def chain_timeline(
    node_key: str = Query(..., min_length=1),
    limit: int = Query(default=36, ge=1, le=180),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    payload = build_chain_timeline(session, node_key, limit)
    if payload is None:
        raise HTTPException(status_code=404, detail="chain node not found")
    return payload


def _normalize_market_filter(market: str | None) -> str | None:
    if not market:
        return None
    normalized = market.upper()
    if normalized == "ALL":
        return None
    return normalized if normalized in {"A", "US", "HK"} else None
