from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.data_sources.http_utils import fetch_json, normalized_bar, parse_date, urlencode


class PolygonClient:
    """Polygon.io adapter for US adjusted daily aggregate bars."""

    source = "polygon"

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise RuntimeError("Polygon API key is missing")
        self.api_key = api_key

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
        params = urlencode({"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key})
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}?{params}"
        payload = fetch_json(url, timeout=20)
        if str(payload.get("status", "")).upper() not in {"OK", "DELAYED"}:
            return []
        rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for item in payload.get("results", []) or []:
            trade_date = parse_date(item.get("t") and date.fromtimestamp(int(item["t"]) / 1000).isoformat())
            if trade_date is None or trade_date > end:
                continue
            bar = normalized_bar(
                stock_code=stock_code,
                trade_date=trade_date,
                open_price=item.get("o"),
                high=item.get("h"),
                low=item.get("l"),
                close=item.get("c"),
                pre_close=previous_close or item.get("c"),
                volume=item.get("v"),
                amount=(float(item.get("v") or 0) * float(item.get("c") or 0)),
                adj_factor=1.0,
                source=self.source,
            )
            if bar is not None:
                rows.append(bar)
                previous_close = float(bar["close"])
        return rows[-max(1, periods) :]
