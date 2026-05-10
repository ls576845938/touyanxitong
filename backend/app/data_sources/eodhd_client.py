from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.data_sources.http_utils import fetch_json, normalized_bar, parse_date, urlencode
from app.data_sources.market_classifier import infer_a_exchange, normalize_hk_code, normalize_us_code


class EODHDClient:
    """EODHD daily-bar adapter for US/HK and optional A-share symbols."""

    source = "eodhd"

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise RuntimeError("EODHD API key is missing")
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
        symbol = _to_eodhd_symbol(stock_code, market)
        if not symbol:
            return []
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        params = urlencode({"api_token": self.api_key, "fmt": "json", "from": start.isoformat(), "to": end.isoformat(), "period": "d"})
        payload = fetch_json(f"https://eodhd.com/api/eod/{symbol}?{params}", timeout=20)
        rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for item in payload if isinstance(payload, list) else []:
            trade_date = parse_date(item.get("date"))
            if trade_date is None or trade_date > end:
                continue
            close = item.get("adjusted_close") or item.get("close")
            bar = normalized_bar(
                stock_code=stock_code,
                trade_date=trade_date,
                open_price=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=close,
                pre_close=previous_close or close,
                volume=item.get("volume"),
                amount=None,
                adj_factor=1.0,
                source=self.source,
            )
            if bar is not None:
                rows.append(bar)
                previous_close = float(bar["close"])
        return rows[-max(1, periods) :]


def _to_eodhd_symbol(stock_code: str, market: str | None = None) -> str:
    market_key = (market or "").upper()
    code = stock_code.strip().upper()
    if market_key == "US" or (not market_key and not code.isdigit() and not code.endswith(".HK")):
        return f"{normalize_us_code(code).replace('_', '.')}.US"
    if market_key == "HK" or code.endswith(".HK"):
        return f"{normalize_hk_code(code).replace('.HK', '').zfill(4)}.HK"
    if market_key == "A" or code.isdigit():
        exchange = infer_a_exchange(code)
        if exchange == "SSE":
            return f"{code.zfill(6)}.SHG"
        if exchange == "SZSE":
            return f"{code.zfill(6)}.SHE"
    return ""
