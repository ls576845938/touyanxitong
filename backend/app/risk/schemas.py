from pydantic import BaseModel, Field


class PositionSizeRequest(BaseModel):
    account_equity: float = Field(..., gt=0)
    available_cash: float | None = None
    symbol: str
    entry_price: float = Field(..., gt=0)
    invalidation_price: float | None = None  # REQUIRED for valid plan
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=5.0)
    max_single_position_pct: float | None = None
    max_theme_exposure_pct: float | None = None
    current_drawdown_pct: float | None = None
    market: str | None = None
    lot_size: int | None = None
    thesis_id: int | None = None
    subject_name: str | None = None


class PositionSizeResponse(BaseModel):
    symbol: str
    entry_price: float
    invalidation_price: float | None
    risk_per_share: float | None
    max_loss_amount: float | None
    raw_quantity: float | None
    rounded_quantity: int | None
    estimated_position_value: float | None
    estimated_position_pct: float | None
    effective_risk_pct: float
    cash_required: float | None
    cash_after: float | None
    warnings: list[str]
    constraints_applied: list[str]
    calculation_explain: str
    disclaimer: str
    error: str | None = None  # non-None means calculation failed
