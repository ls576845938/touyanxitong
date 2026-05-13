from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PositionPlan,
    PositionPlanReview,
    ResearchThesis,
    RiskPortfolio,
    WatchlistItem,
)
from app.db.session import get_session
from app.risk.calculators import calculate_position_size
from app.risk.guardrails import RISK_DISCLAIMER, sanitize_risk_output
from app.risk.schemas import PositionSizeRequest

router = APIRouter(prefix="/api/risk", tags=["risk-plan"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRICE_KEYWORDS = ["price", "价格", "跌破", "站上", "止", "止损", "破位", "支撑"]


def _loads_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _extract_invalidation_price_from_conditions(conditions: list[str]) -> float | None:
    """Try to auto-detect an invalidation / stop price from text conditions.

    Scans each condition for price-related keywords and extracts the last
    numeric value found in a matching condition.
    """
    for condition in conditions:
        lower = condition.lower()
        if not any(kw in lower for kw in _PRICE_KEYWORDS):
            continue
        matches = re.findall(r"(\d+\.?\d*)", condition)
        if matches:
            return float(matches[-1])
    return None


def _price_based_conditions_exist(conditions: list[str]) -> bool:
    """Return True if at least one condition contains a price-related keyword."""
    for condition in conditions:
        lower = condition.lower()
        if any(kw in lower for kw in _PRICE_KEYWORDS):
            return True
        if re.search(r"[跌涨站破止]+\s*\d+\.?\d*", condition):
            return True
    return False


def _plan_row(plan: PositionPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "portfolio_id": plan.portfolio_id,
        "thesis_id": plan.thesis_id,
        "watchlist_item_id": plan.watchlist_item_id,
        "symbol": plan.symbol,
        "subject_name": plan.subject_name,
        "subject_type": plan.subject_type,
        "entry_price": plan.entry_price,
        "invalidation_price": plan.invalidation_price,
        "risk_per_share": plan.risk_per_share,
        "risk_per_trade_pct": plan.risk_per_trade_pct,
        "max_loss_amount": plan.max_loss_amount,
        "calculated_quantity": plan.calculated_quantity,
        "calculated_position_value": plan.calculated_position_value,
        "calculated_position_pct": plan.calculated_position_pct,
        "theme_exposure_after_pct": plan.theme_exposure_after_pct,
        "industry_exposure_after_pct": plan.industry_exposure_after_pct,
        "status": plan.status,
        "warnings": _loads_json_list(plan.warnings_json),
        "constraints": _loads_json_list(plan.constraints_json),
        "calculation": json.loads(plan.calculation_json) if plan.calculation_json != "{}" else {},
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _review_row(r: PositionPlanReview) -> dict[str, Any]:
    return {
        "id": r.id,
        "position_plan_id": r.position_plan_id,
        "review_date": r.review_date.isoformat() if r.review_date else None,
        "status": r.status,
        "actual_price": r.actual_price,
        "realized_risk_pct": r.realized_risk_pct,
        "review_note": r.review_note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _get_or_create_portfolio(session: Session, user_id: str | None) -> RiskPortfolio:
    """Return the user's default portfolio (or first available, or a fresh default)."""
    if user_id:
        portfolio = session.scalar(
            select(RiskPortfolio)
            .where(RiskPortfolio.user_id == user_id)
            .order_by(RiskPortfolio.id.asc())
        )
        if portfolio:
            return portfolio
    portfolio = session.scalar(select(RiskPortfolio).order_by(RiskPortfolio.id.asc()))
    if portfolio:
        return portfolio
    portfolio = RiskPortfolio(
        user_id=user_id,
        name="默认组合",
        total_equity=100000.0,
        cash=100000.0,
    )
    session.add(portfolio)
    session.flush()
    return portfolio


def _run_position_calculation(
    session: Session,
    plan: PositionPlan,
    portfolio: RiskPortfolio | None = None,
) -> None:
    """Re-run the position-size calculator and update the plan's calculated fields."""
    if portfolio is None and plan.portfolio_id:
        portfolio = session.get(RiskPortfolio, plan.portfolio_id)
    if portfolio is None:
        portfolio = _get_or_create_portfolio(session, plan.user_id)

    account_equity = portfolio.total_equity if portfolio.total_equity > 0 else 100000.0
    available_cash = portfolio.cash if portfolio.cash > 0 else account_equity

    calc_result = calculate_position_size(
        PositionSizeRequest(
            account_equity=account_equity,
            available_cash=available_cash,
            symbol=plan.symbol,
            entry_price=plan.entry_price,
            invalidation_price=plan.invalidation_price,
            risk_per_trade_pct=plan.risk_per_trade_pct,
            thesis_id=plan.thesis_id,
            subject_name=plan.subject_name,
        )
    )

    plan.risk_per_share = calc_result.risk_per_share
    plan.max_loss_amount = calc_result.max_loss_amount
    plan.calculated_quantity = calc_result.rounded_quantity
    plan.calculated_position_value = calc_result.estimated_position_value
    plan.calculated_position_pct = calc_result.estimated_position_pct

    warnings = list(calc_result.warnings or [])
    constraints = list(calc_result.constraints_applied or [])
    if calc_result.error:
        warnings.append(calc_result.error)

    plan.warnings_json = _dumps_json(warnings)
    plan.constraints_json = _dumps_json(constraints)
    plan.calculation_json = _dumps_json(
        {
            "account_equity": account_equity,
            "available_cash": available_cash,
            "risk_per_trade_pct": plan.risk_per_trade_pct,
            "invalidation_price": plan.invalidation_price,
            "entry_price": plan.entry_price,
            "risk_per_share": calc_result.risk_per_share,
            "max_loss_amount": calc_result.max_loss_amount,
            "raw_quantity": calc_result.raw_quantity,
            "rounded_quantity": calc_result.rounded_quantity,
            "estimated_position_value": calc_result.estimated_position_value,
            "estimated_position_pct": calc_result.estimated_position_pct,
            "effective_risk_pct": calc_result.effective_risk_pct,
            "cash_required": calc_result.cash_required,
            "cash_after": calc_result.cash_after,
            "explanation": calc_result.calculation_explain,
        }
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/position-plans")
def create_position_plan(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a position (risk-budget) plan from a thesis or watchlist item.

    The plan is a **risk budget plan**, NOT a trade recommendation.  It
    calculates the maximum position size that fits within the user's risk
    constraints and stores the result as a **draft**.  No trade is ever
    executed automatically.
    """
    thesis_id = payload.get("thesis_id")
    watchlist_item_id = payload.get("watchlist_item_id")
    user_id = payload.get("user_id")

    if not thesis_id and not watchlist_item_id:
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output("需要提供 thesis_id 或 watchlist_item_id"),
        )

    # --- Load source & extract conditions ---
    thesis: ResearchThesis | None = None
    conditions: list[str] = []
    symbol: str | None = None
    subject_name: str | None = None
    subject_type: str = "stock"
    entry_price_context: float | None = None

    if thesis_id:
        thesis = session.get(ResearchThesis, thesis_id)
        if thesis is None:
            raise HTTPException(status_code=404, detail="研报/论点未找到")
        conditions = _loads_json_list(thesis.invalidation_conditions_json)
        symbol = thesis.subject_id if thesis.subject_type == "stock" else (thesis.subject_id or "")
        subject_name = thesis.subject_name
        subject_type = thesis.subject_type
    elif watchlist_item_id:
        watchlist_item = session.get(WatchlistItem, watchlist_item_id)
        if watchlist_item is None:
            raise HTTPException(status_code=404, detail="观察池条目未找到")
        conditions = _loads_json_list(watchlist_item.invalidation_conditions_json)
        symbol = watchlist_item.stock_code or watchlist_item.subject_id or ""
        subject_name = watchlist_item.subject_name
        subject_type = watchlist_item.subject_type

        # Try to extract entry price context from watch_metrics
        metrics = _loads_json_list(watchlist_item.watch_metrics_json)
        for m in metrics:
            if isinstance(m, dict) and m.get("metric") in (
                "price",
                "current_price",
                "entry_price",
                "close",
            ):
                try:
                    entry_price_context = float(m.get("value", 0))
                except (ValueError, TypeError):
                    pass
                break

        # If watchlist links to a thesis, prefer thesis invalidation conditions
        if watchlist_item.source_thesis_id:
            linked_thesis = session.get(ResearchThesis, watchlist_item.source_thesis_id)
            if linked_thesis:
                thesis = linked_thesis
                thesis_conditions = _loads_json_list(thesis.invalidation_conditions_json)
                if thesis_conditions:
                    conditions = thesis_conditions

    if not conditions:
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output("缺少无效条件，无法创建仓位计划"),
        )

    # --- Determine invalidation price ---
    has_price_condition = _price_based_conditions_exist(conditions)
    invalidation_price = payload.get("invalidation_price")

    if invalidation_price is None and has_price_condition:
        invalidation_price = _extract_invalidation_price_from_conditions(conditions)

    if invalidation_price is None:
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output(
                "缺少无效条件，无法创建仓位计划。条件中未包含价格信息，"
                "请手动提供无效价格（invalidation_price）"
            ),
        )

    # --- Determine entry price ---
    entry_price = payload.get("entry_price") or entry_price_context or 0.0
    if entry_price <= 0:
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output("请提供入场参考价格（entry_price）"),
        )

    risk_per_trade_pct = float(payload.get("risk_per_trade_pct", 1.0))

    # --- Resolve portfolio ---
    portfolio_id = payload.get("portfolio_id")
    portfolio: RiskPortfolio | None = None
    if portfolio_id:
        portfolio = session.get(RiskPortfolio, portfolio_id)
    if portfolio is None:
        portfolio = _get_or_create_portfolio(session, user_id)
        portfolio_id = portfolio.id

    account_equity = portfolio.total_equity if portfolio.total_equity > 0 else 100000.0
    available_cash = portfolio.cash if portfolio.cash > 0 else account_equity

    # --- Run position-size calculation ---
    calc_result = calculate_position_size(
        PositionSizeRequest(
            account_equity=account_equity,
            available_cash=available_cash,
            symbol=symbol,
            entry_price=float(entry_price),
            invalidation_price=float(invalidation_price),
            risk_per_trade_pct=risk_per_trade_pct,
            thesis_id=thesis_id,
            subject_name=subject_name,
        )
    )

    warnings: list[str] = list(calc_result.warnings or [])
    constraints: list[str] = list(calc_result.constraints_applied or [])
    if calc_result.error:
        warnings.append(calc_result.error)

    calculation_detail: dict[str, Any] = {
        "account_equity": account_equity,
        "available_cash": available_cash,
        "risk_per_trade_pct": risk_per_trade_pct,
        "invalidation_price": invalidation_price,
        "entry_price": entry_price,
        "risk_per_share": calc_result.risk_per_share,
        "max_loss_amount": calc_result.max_loss_amount,
        "raw_quantity": calc_result.raw_quantity,
        "rounded_quantity": calc_result.rounded_quantity,
        "estimated_position_value": calc_result.estimated_position_value,
        "estimated_position_pct": calc_result.estimated_position_pct,
        "effective_risk_pct": calc_result.effective_risk_pct,
        "cash_required": calc_result.cash_required,
        "cash_after": calc_result.cash_after,
        "explanation": calc_result.calculation_explain,
    }

    # --- Create the plan (always starts as draft) ---
    plan = PositionPlan(
        user_id=user_id,
        portfolio_id=portfolio_id,
        thesis_id=thesis_id,
        watchlist_item_id=watchlist_item_id,
        symbol=symbol,
        subject_name=subject_name,
        subject_type=subject_type,
        entry_price=float(entry_price),
        invalidation_price=float(invalidation_price),
        risk_per_share=calc_result.risk_per_share,
        risk_per_trade_pct=risk_per_trade_pct,
        max_loss_amount=calc_result.max_loss_amount,
        calculated_quantity=calc_result.rounded_quantity,
        calculated_position_value=calc_result.estimated_position_value,
        calculated_position_pct=calc_result.estimated_position_pct,
        status="draft",
        warnings_json=_dumps_json(warnings),
        constraints_json=_dumps_json(constraints),
        calculation_json=_dumps_json(calculation_detail),
    )

    session.add(plan)
    session.commit()
    session.refresh(plan)

    result = _plan_row(plan)
    result["disclaimer"] = RISK_DISCLAIMER
    result["calculation_explain"] = calc_result.calculation_explain

    return result


@router.get("/position-plans")
def list_position_plans(
    status: str | None = Query(default=None, description="Filter by status: draft/active/invalidated/reviewed/archived"),
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    user_id: str | None = Query(default=None, description="Filter by user_id"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List position plans with optional filters."""
    query = select(PositionPlan).order_by(PositionPlan.created_at.desc())

    if status:
        query = query.where(PositionPlan.status == status)
    if symbol:
        query = query.where(PositionPlan.symbol == symbol)
    if user_id:
        query = query.where(PositionPlan.user_id == user_id)

    total = len(session.scalars(query).all())
    rows = session.scalars(query.offset(offset).limit(limit)).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [_plan_row(r) for r in rows],
        "disclaimer": RISK_DISCLAIMER,
    }


@router.get("/position-plans/{plan_id}")
def get_position_plan(
    plan_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get a single position plan with its review history."""
    plan = session.get(PositionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="仓位计划未找到")

    reviews = session.scalars(
        select(PositionPlanReview)
        .where(PositionPlanReview.position_plan_id == plan_id)
        .order_by(PositionPlanReview.review_date.desc())
    ).all()

    return {
        "plan": _plan_row(plan),
        "reviews": [_review_row(r) for r in reviews],
        "disclaimer": RISK_DISCLAIMER,
    }


@router.patch("/position-plans/{plan_id}")
def update_position_plan(
    plan_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update a position plan's entry_price, invalidation_price, or risk_per_trade_pct.

    When any of these fields change, the position-size calculation is re-run
    and the calculated_* fields are refreshed.
    """
    plan = session.get(PositionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="仓位计划未找到")

    # Only allow updates on draft or active plans
    if plan.status not in ("draft", "active"):
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output(
                f"当前状态（{plan.status}）不允许修改"
            ),
        )

    recalculate = False
    if "entry_price" in payload:
        plan.entry_price = float(payload["entry_price"])
        recalculate = True
    if "invalidation_price" in payload:
        plan.invalidation_price = (
            float(payload["invalidation_price"])
            if payload["invalidation_price"] is not None
            else None
        )
        recalculate = True
    if "risk_per_trade_pct" in payload:
        plan.risk_per_trade_pct = float(payload["risk_per_trade_pct"])
        recalculate = True

    if recalculate and plan.invalidation_price is not None and plan.entry_price > 0:
        _run_position_calculation(session, plan)

    session.commit()
    session.refresh(plan)

    result = _plan_row(plan)
    result["disclaimer"] = RISK_DISCLAIMER
    return result


@router.post("/position-plans/{plan_id}/activate")
def activate_position_plan(
    plan_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Activate a position plan (draft -> active).

    Activation means the user has reviewed and confirmed the risk budget plan.
    It does NOT place any trade.
    """
    plan = session.get(PositionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="仓位计划未找到")

    if plan.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output(f"只有草稿状态的计划可以激活，当前状态为 {plan.status}"),
        )

    if plan.invalidation_price is None:
        raise HTTPException(
            status_code=400,
            detail=sanitize_risk_output("激活前请先设置无效价格（invalidation_price）"),
        )

    plan.status = "active"
    session.commit()
    session.refresh(plan)

    result = _plan_row(plan)
    result["disclaimer"] = RISK_DISCLAIMER
    result["message"] = "仓位计划已激活（未执行任何交易）"
    return result


@router.post("/position-plans/{plan_id}/archive")
def archive_position_plan(
    plan_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Archive a position plan."""
    plan = session.get(PositionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="仓位计划未找到")

    plan.status = "archived"
    session.commit()
    session.refresh(plan)

    result = _plan_row(plan)
    result["disclaimer"] = RISK_DISCLAIMER
    result["message"] = "仓位计划已归档"
    return result


@router.post("/position-plans/{plan_id}/review")
def create_plan_review(
    plan_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a review for a position plan.

    Checks whether the risk budget was respected based on actual price
    movement since the plan was created.
    """
    plan = session.get(PositionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="仓位计划未找到")

    actual_price = payload.get("actual_price")
    raw_review_date = payload.get("review_date")
    review_date: date
    if raw_review_date and isinstance(raw_review_date, str):
        review_date = date.fromisoformat(raw_review_date)
    else:
        review_date = date.today()

    review_note = payload.get("review_note")

    # Determine review status based on actual price
    status = "inconclusive"
    realized_risk_pct: float | None = None

    if actual_price is not None and plan.entry_price > 0 and plan.invalidation_price is not None:
        actual_price = float(actual_price)
        risk_per_share = plan.entry_price - plan.invalidation_price
        if risk_per_share > 0:
            price_change = plan.entry_price - actual_price
            realized_risk_pct = max(0.0, min(100.0, (price_change / risk_per_share) * 100.0))

        if actual_price >= plan.entry_price:
            status = "respected_plan"
        elif actual_price <= plan.invalidation_price:
            status = "exceeded_risk"
        else:
            status = "inconclusive"

    review = PositionPlanReview(
        position_plan_id=plan_id,
        review_date=review_date,
        status=status,
        actual_price=actual_price,
        realized_risk_pct=realized_risk_pct,
        review_note=review_note,
    )
    session.add(review)

    # Update plan status based on review
    if status == "exceeded_risk":
        plan.status = "invalidated"
    elif status == "respected_plan":
        if plan.status != "archived":
            plan.status = "reviewed"

    session.commit()
    session.refresh(review)

    return {
        "plan_id": plan_id,
        "review": _review_row(review),
        "disclaimer": RISK_DISCLAIMER,
    }
