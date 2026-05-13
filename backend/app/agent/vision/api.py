from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.vision.schemas import (
    ConfirmImportRequest,
    PortfolioImageExtractResponse,
)
from app.agent.vision.adapter import VisionPortfolioExtractor
from app.db.models import RiskEvent, RiskPortfolio, RiskPosition, Stock
from app.db.session import get_session

router = APIRouter(prefix="/api/agent/vision", tags=["agent-vision"])

# Allowed image MIME types
ALLOWED_IMAGE_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
})

_MAX_IMAGE_MB = 20
_MAX_IMAGE_BYTES = _MAX_IMAGE_MB * 1024 * 1024

RISK_BOUNDARY = "风险监控与组合管理，不构成投资建议。"


# ── Helper utilities ─────────────────────────────────────────────────


def _portfolio_payload(portfolio: RiskPortfolio) -> dict[str, Any]:
    return {
        "id": portfolio.id,
        "user_id": portfolio.user_id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "total_equity": portfolio.total_equity,
        "cash": portfolio.cash,
        "current_drawdown_pct": portfolio.current_drawdown_pct,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
        "updated_at": portfolio.updated_at.isoformat() if portfolio.updated_at else None,
    }


def _position_payload(position: RiskPosition) -> dict[str, Any]:
    return {
        "id": position.id,
        "portfolio_id": position.portfolio_id,
        "symbol": position.symbol,
        "name": position.name,
        "market": position.market,
        "quantity": position.quantity,
        "avg_cost": position.avg_cost,
        "last_price": position.last_price,
        "market_value": position.market_value,
        "position_pct": position.position_pct,
        "industry": position.industry,
        "updated_at": position.updated_at.isoformat() if position.updated_at else None,
    }


def _create_risk_event(
    db_session: Session,
    user_id: str | None,
    portfolio_id: int | None,
    event_type: str,
    severity: str,
    message: str,
    related_symbol: str | None = None,
    related_theme: str | None = None,
    payload_json: str | None = None,
) -> RiskEvent:
    event = RiskEvent(
        user_id=user_id,
        portfolio_id=portfolio_id,
        event_type=event_type,
        severity=severity,
        message=message,
        related_symbol=related_symbol,
        related_theme=related_theme,
        payload_json=payload_json,
    )
    db_session.add(event)
    return event


def _lookup_stock(session: Session, symbol: str) -> Stock | None:
    """Look up stock by symbol (code) or name."""
    stock = session.scalar(select(Stock).where(Stock.code == symbol).limit(1))
    if stock is None:
        stock = session.scalar(select(Stock).where(Stock.name == symbol).limit(1))
    return stock


# ── Extraction endpoint (existing) ───────────────────────────────────


@router.post("/extract-portfolio", response_model=PortfolioImageExtractResponse)
async def extract_portfolio(
    image: UploadFile = File(...),
    broker_hint: str | None = Form(None),
    market_hint: str | None = Form(None),
    user_hint: str | None = Form(None),
) -> PortfolioImageExtractResponse:
    """Extract portfolio positions from a broker screenshot.

    Requires a Vision-capable LLM (e.g. gpt-4o) to be configured via
    ``OPENAI_API_KEY``.  The image is validated and immediately passed to
    the extractor; **no image data is persisted or logged**.
    """
    # --- Validate content type ------------------------------------------------
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{image.content_type}'. "
            f"Accepted: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}.",
        )

    # --- Read bytes (stream to memory only) -----------------------------------
    image_bytes = await image.read()

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large ({len(image_bytes) / 1024 / 1024:.1f} MiB). "
            f"Maximum: {_MAX_IMAGE_MB} MiB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    # --- Delegate to extraction adapter ---------------------------------------
    # NOTE: image_bytes is intentionally NOT logged or persisted anywhere.
    extractor = VisionPortfolioExtractor()
    return extractor.extract(
        image_bytes,
        broker_hint=broker_hint,
        market_hint=market_hint,
        user_hint=user_hint,
    )


# ── Confirm-import endpoint (new) ────────────────────────────────────


@router.post("/confirm-portfolio-import")
def confirm_portfolio_import(
    req: ConfirmImportRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """User-confirmed portfolio import. Writes positions to ``risk_positions``.

    The caller (frontend) should present the extraction result to the user
    for confirmation before calling this endpoint.  The ``positions`` field
    must contain the final set of positions the user has confirmed.
    """
    # --- 1. Resolve or create portfolio ---------------------------------------
    portfolio = None
    if req.portfolio_id is not None:
        portfolio = session.get(RiskPortfolio, req.portfolio_id)

    if portfolio is None:
        portfolio = RiskPortfolio(
            user_id="screenshot_import",
            name="截图导入组合",
            base_currency="CNY",
            total_equity=req.account_equity or 0.0,
            cash=req.cash or 0.0,
        )
        session.add(portfolio)
        session.flush()  # get portfolio.id

        _create_risk_event(
            session,
            portfolio.user_id,
            portfolio.id,
            event_type="plan_created",
            severity="info",
            message=f"组合 '{portfolio.name}' 已通过截图导入创建",
        )

    # --- 2. Update portfolio-level financials ---------------------------------
    if req.account_equity is not None:
        portfolio.total_equity = req.account_equity
    if req.cash is not None:
        portfolio.cash = req.cash
    portfolio.updated_at = datetime.now(timezone.utc)

    # --- 3. Fetch existing positions ------------------------------------------
    existing_positions: dict[str, RiskPosition] = {}
    for row in session.scalars(
        select(RiskPosition).where(RiskPosition.portfolio_id == portfolio.id)
    ).all():
        existing_positions[row.symbol] = row

    # --- 4. Apply import mode -------------------------------------------------
    incoming_symbols = {pos.symbol for pos in req.positions}

    if req.import_mode == "replace":
        # Delete positions not in the incoming list
        for symbol, pos in existing_positions.items():
            if symbol not in incoming_symbols:
                session.delete(pos)
        existing_positions = {
            s: p for s, p in existing_positions.items() if s in incoming_symbols
        }

    elif req.import_mode == "append":
        # Only add symbols that don't already exist
        req.positions = [
            pos for pos in req.positions if pos.symbol not in existing_positions
        ]

    # "merge" is the default — upsert by symbol (no filtering needed)

    # --- 5. Upsert each confirmed position ------------------------------------
    now = datetime.now(timezone.utc)
    for confirmed in req.positions:
        existing = existing_positions.get(confirmed.symbol)
        is_new = existing is None

        if is_new:
            position = RiskPosition(
                portfolio_id=portfolio.id,
                symbol=confirmed.symbol,
            )
            session.add(position)
        else:
            position = existing

        position.name = confirmed.name or position.name or confirmed.symbol
        position.market = confirmed.market or position.market or "A"
        position.quantity = confirmed.quantity
        position.market_value = confirmed.market_value
        position.avg_cost = confirmed.cost
        position.updated_at = now

        # Auto-populate industry from Stock data if available
        if position.name:
            stock = _lookup_stock(session, position.symbol)
            if stock and stock.industry_level1 and not position.industry:
                position.industry = stock.industry_level1

        _create_risk_event(
            session,
            portfolio.user_id,
            portfolio.id,
            event_type="plan_created" if is_new else "plan_reviewed",
            severity="info",
            message=f"已{'新增' if is_new else '更新'}仓位 {confirmed.symbol}"
            + (f" ({confirmed.name})" if confirmed.name else ""),
            related_symbol=confirmed.symbol,
        )

    # --- 6. Recalculate position_pct for all positions ------------------------
    total_equity = portfolio.total_equity or 1.0  # avoid div-by-zero
    all_positions = session.scalars(
        select(RiskPosition).where(RiskPosition.portfolio_id == portfolio.id)
    ).all()
    for pos in all_positions:
        if pos.market_value is not None and total_equity > 0:
            pos.position_pct = round((pos.market_value / total_equity) * 100, 4)
        else:
            pos.position_pct = None

    session.commit()

    # --- 7. Build response ----------------------------------------------------
    return {
        "boundary": RISK_BOUNDARY,
        "portfolio": _portfolio_payload(portfolio),
        "positions": [_position_payload(p) for p in all_positions],
        "import_mode": req.import_mode,
        "positions_count": len(all_positions),
    }
