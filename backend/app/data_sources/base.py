from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol


class MarketDataClient(Protocol):
    source: str

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Return stock universe rows normalized to AlphaRadar's stock contract."""

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        """Return daily OHLCV rows normalized to AlphaRadar's daily_bar contract."""
