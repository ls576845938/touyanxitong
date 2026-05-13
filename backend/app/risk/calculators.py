import math

from app.risk.drawdown import get_drawdown_multiplier as _get_drawdown_status
from app.risk.guardrails import RISK_DISCLAIMER, sanitize_risk_output
from app.risk.schemas import PositionSizeRequest, PositionSizeResponse


def _resolve_lot_size(market: str | None, lot_size: int | None) -> int:
    """Determine the minimum lot/trading unit for the given market."""
    if lot_size is not None:
        return lot_size
    if market == "A":
        return 100
    return 1


def calculate_position_size(req: PositionSizeRequest) -> PositionSizeResponse:
    """Core position-sizing engine.

    Calculates the maximum position size for a single trade based on the
    account equity, risk-per-trade percentage, invalidation stop price, and
    optional constraints (drawdown, max position %, cash available, lot size).
    """

    warnings: list[str] = []
    constraints_applied: list[str] = []

    risk_pct = req.risk_per_trade_pct

    # --- Warning: high risk-per-trade ---
    if risk_pct > 2.0:
        warnings.append("单笔风险比例超过2%，风险暴露较高")

    # --- Resolve lot size ---
    lot_size = _resolve_lot_size(req.market, req.lot_size)
    if req.lot_size is None:
        if req.market is None:
            warnings.append("无法确定最小交易单位，默认1")
        elif req.market not in ("A",):
            warnings.append("无法确定最小交易单位，默认1")
        constraints_applied.append("最小交易单位对齐")

    # --- Resolve drawdown multiplier ---
    drawdown_multiplier = 1.0
    if req.current_drawdown_pct is None:
        warnings.append("未提供回撤数据，无法应用回撤熔断规则")
    else:
        dd_status = _get_drawdown_status(req.current_drawdown_pct)
        drawdown_multiplier = dd_status["multiplier"]
        # Add contextual drawdown warnings
        warnings.extend(dd_status["warnings"])
        constraints_applied.append(
            f"回撤熔断: {dd_status['label']}(乘数={dd_status['multiplier']})"
        )

    # --- Warning: missing theme exposure ---
    if req.max_theme_exposure_pct is None:
        warnings.append("未设置主题/板块最大暴露比例，无法约束主题级风险")

    # ===== Error: missing invalidation price =====
    if req.invalidation_price is None:
        return PositionSizeResponse(
            symbol=req.symbol,
            entry_price=req.entry_price,
            invalidation_price=None,
            risk_per_share=None,
            max_loss_amount=None,
            raw_quantity=None,
            rounded_quantity=None,
            estimated_position_value=None,
            estimated_position_pct=None,
            effective_risk_pct=0.0,
            cash_required=None,
            cash_after=None,
            warnings=warnings,
            constraints_applied=constraints_applied,
            calculation_explain=sanitize_risk_output(
                "缺少无效条件，无法计算仓位计划。请提供止损价/无效点。"
            ),
            disclaimer=RISK_DISCLAIMER,
            error="缺少无效条件，无法计算仓位计划。请提供止损价/无效点。",
        )

    # ===== Error: invalidation >= entry =====
    if req.invalidation_price >= req.entry_price:
        return PositionSizeResponse(
            symbol=req.symbol,
            entry_price=req.entry_price,
            invalidation_price=req.invalidation_price,
            risk_per_share=None,
            max_loss_amount=None,
            raw_quantity=None,
            rounded_quantity=None,
            estimated_position_value=None,
            estimated_position_pct=None,
            effective_risk_pct=0.0,
            cash_required=None,
            cash_after=None,
            warnings=warnings,
            constraints_applied=constraints_applied,
            calculation_explain=sanitize_risk_output(
                "无效点价格必须低于入场参考价"
            ),
            disclaimer=RISK_DISCLAIMER,
            error="无效点价格必须低于入场参考价",
        )

    # ===== Core calculation =====
    base_risk_amount = req.account_equity * risk_pct / 100.0
    risk_amount = base_risk_amount * drawdown_multiplier

    risk_per_share = max(0.01, req.entry_price - req.invalidation_price)
    raw_quantity = risk_amount / risk_per_share

    # Round down to nearest lot
    raw_lots = raw_quantity / lot_size
    rounded_lots = int(math.floor(raw_lots))
    rounded_quantity = rounded_lots * lot_size

    # Position value & percentage
    position_value = rounded_quantity * req.entry_price
    position_pct = position_value / req.account_equity * 100.0

    # ===== Constraint: cap at 100% of equity =====
    max_by_equity = int(req.account_equity / req.entry_price)
    max_by_equity_rounded = (max_by_equity // lot_size) * lot_size
    if rounded_quantity > max_by_equity_rounded:
        warnings.append("计算仓位比例超过100%，已自动调整至100%上限")
        constraints_applied.append("百分比上限调整")
        rounded_quantity = max_by_equity_rounded
        position_value = rounded_quantity * req.entry_price
        position_pct = position_value / req.account_equity * 100.0

    # ===== Constraint: max single position % =====
    if req.max_single_position_pct is not None:
        max_by_position_val = req.account_equity * req.max_single_position_pct / 100.0
        max_by_position_qty = int(max_by_position_val / req.entry_price)
        max_by_position_rounded = (max_by_position_qty // lot_size) * lot_size
        if rounded_quantity > max_by_position_rounded:
            warnings.append(
                f"仓位比例({position_pct:.2f}%)超过最大单标限制"
                f"({req.max_single_position_pct}%)"
            )
            constraints_applied.append("最大单标限制")
            rounded_quantity = max_by_position_rounded
            position_value = rounded_quantity * req.entry_price
            position_pct = position_value / req.account_equity * 100.0

    # ===== Constraint: available cash =====
    cash_after: float | None = None
    if req.available_cash is not None:
        if position_value > req.available_cash:
            max_by_cash_qty = int(req.available_cash / req.entry_price)
            max_by_cash_rounded = (max_by_cash_qty // lot_size) * lot_size
            warnings.append(
                f"持仓价值({position_value:.2f})超过可用现金({req.available_cash:.2f})"
            )
            constraints_applied.append("可用现金限制")
            rounded_quantity = max_by_cash_rounded
            position_value = rounded_quantity * req.entry_price
            position_pct = position_value / req.account_equity * 100.0
        cash_after = req.available_cash - position_value

    cash_required = position_value if position_value > 0 else None

    # ===== Effective risk after constraints =====
    effective_risk_pct = (
        (rounded_quantity * risk_per_share) / req.account_equity * 100.0
        if rounded_quantity > 0
        else 0.0
    )

    # ===== Build calculation explanation =====
    explain_parts = [
        f"基于账户权益 {req.account_equity:.2f}，风险比例 {risk_pct}%，"
        f"回撤乘数 {drawdown_multiplier}，最大亏损预算 {risk_amount:.2f}。",
        f"每股风险 {risk_per_share:.2f}"
        f"（入场 {req.entry_price} - 无效 {req.invalidation_price}），"
        f"理论数量 {raw_quantity:.2f}，对齐最小交易单位({lot_size})后为 {rounded_quantity}。",
        f"预估持仓价值 {position_value:.2f}，占账户 {position_pct:.2f}%。",
    ]
    explain = "".join(explain_parts)

    # ===== Warning: near-zero position =====
    if rounded_quantity == 0 and raw_quantity > 0:
        warnings.append(
            f"风险预算不足以买入1个单位(lot_size={lot_size})，建议增大风险预算或降低入场价"
        )

    return PositionSizeResponse(
        symbol=req.symbol,
        entry_price=req.entry_price,
        invalidation_price=req.invalidation_price,
        risk_per_share=risk_per_share,
        max_loss_amount=risk_amount,
        raw_quantity=raw_quantity,
        rounded_quantity=rounded_quantity,
        estimated_position_value=position_value,
        estimated_position_pct=position_pct,
        effective_risk_pct=effective_risk_pct,
        cash_required=cash_required,
        cash_after=cash_after,
        warnings=warnings,
        constraints_applied=constraints_applied,
        calculation_explain=sanitize_risk_output(explain),
        disclaimer=RISK_DISCLAIMER,
        error=None,
    )
