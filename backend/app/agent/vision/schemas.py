from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedPosition(BaseModel):
    """A single position extracted from a portfolio screenshot."""

    symbol: str | None = None
    name: str | None = None
    quantity: float | None = None
    market_value: float | None = None
    cost: float | None = None
    weight_pct: float | None = None
    unrealized_pnl: float | None = None
    confidence: float = 0.0
    raw_text: str | None = None


class PortfolioImageExtractResponse(BaseModel):
    """Response from a portfolio screenshot extraction request."""

    status: str  # success / vision_unavailable / parse_failed
    broker_name: str | None = None
    account_equity: float | None = None
    cash: float | None = None
    positions: list[ExtractedPosition] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unmapped_rows: list[str] = Field(default_factory=list)
    needs_user_confirmation: bool = True
