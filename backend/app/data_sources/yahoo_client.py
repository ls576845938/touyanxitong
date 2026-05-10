from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.data_sources.http_utils import fetch_json, normalized_bar, urlencode
from app.data_sources.market_classifier import infer_a_exchange, normalize_hk_code, normalize_us_code


class YahooChartClient:
    """No-key Yahoo Finance chart adapter for A/HK/US daily bars.

    This is a free fallback source, not a formal exchange or vendor feed. The
    research gate still records it as a distinct source so results remain
    auditable and can be replaced later without changing the pipeline contract.
    """

    source = "yahoo"

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        symbol = _to_yahoo_symbol(stock_code, market)
        if not symbol:
            return []
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
        params = urlencode({"period1": period1, "period2": period2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
        payload = fetch_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        adjclose = (((result.get("indicators") or {}).get("adjclose") or [None])[0]) or {}
        rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for idx, raw_ts in enumerate(timestamps):
            trade_date = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).date()
            if trade_date > end:
                continue
            close = _at(adjclose.get("adjclose"), idx) or _at(quote.get("close"), idx)
            bar = normalized_bar(
                stock_code=stock_code,
                trade_date=trade_date,
                open_price=_at(quote.get("open"), idx),
                high=_at(quote.get("high"), idx),
                low=_at(quote.get("low"), idx),
                close=close,
                pre_close=previous_close or close,
                volume=_at(quote.get("volume"), idx),
                amount=None,
                adj_factor=1.0,
                source=self.source,
            )
            if bar is not None:
                rows.append(bar)
                previous_close = float(bar["close"])
        return rows[-max(1, periods) :]


def _to_yahoo_symbol(stock_code: str, market: str | None = None) -> str:
    market_key = (market or "").upper()
    code = stock_code.strip().upper()
    if market_key == "US" or (not market_key and not code.isdigit() and not code.endswith(".HK")):
        return normalize_us_code(code).replace("_", ".")
    if market_key == "HK" or code.endswith(".HK"):
        clean = normalize_hk_code(code).replace(".HK", "")
        try:
            return f"{int(clean):04d}.HK"
        except ValueError:
            return ""
    if market_key == "A" or code.isdigit():
        clean = code.split(".")[0].zfill(6)
        exchange = infer_a_exchange(clean)
        if exchange == "SSE":
            return f"{clean}.SS"
        if exchange == "SZSE":
            return f"{clean}.SZ"
    return ""


def _at(values: Any, idx: int) -> Any:
    if not isinstance(values, list) or idx >= len(values):
        return None
    return values[idx]
