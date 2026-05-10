from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.data_sources.http_utils import fetch_json, normalized_bar, parse_date, urlencode


class TiingoClient:
    """Tiingo EOD adapter for US daily bars.

    The first integration only implements historical daily bars because the
    stock master remains better handled by AKShare/Tushare in the MVP.
    """

    source = "tiingo"

    def __init__(self, token: str | None) -> None:
        if not token:
            raise RuntimeError("Tiingo token is missing")
        self.token = token

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        if (market or "US").upper() != "US":
            return []
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        symbol = stock_code.strip().upper().replace("_", ".")
        params = urlencode({"startDate": start.isoformat(), "endDate": end.isoformat(), "token": self.token})
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?{params}"
        payload = fetch_json(url, timeout=20)
        rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for item in payload if isinstance(payload, list) else []:
            trade_date = parse_date(item.get("date"))
            if trade_date is None or trade_date > end:
                continue
            close = item.get("adjClose") or item.get("close")
            open_price = item.get("adjOpen") or item.get("open")
            high = item.get("adjHigh") or item.get("high")
            low = item.get("adjLow") or item.get("low")
            bar = normalized_bar(
                stock_code=stock_code,
                trade_date=trade_date,
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                pre_close=previous_close or close,
                volume=item.get("adjVolume") or item.get("volume"),
                amount=None,
                adj_factor=1.0,
                source=self.source,
            )
            if bar is not None:
                rows.append(bar)
                previous_close = float(bar["close"])
        return rows[-max(1, periods) :]
