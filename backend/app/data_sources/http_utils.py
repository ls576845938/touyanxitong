from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any


def fetch_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "AlphaRadar/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def urlencode(params: dict[str, Any]) -> str:
    return urllib.parse.urlencode({key: value for key, value in params.items() if value is not None and value != ""})


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value) in {"", "nan", "NaN", "None"}:
            return default
        return float(value)
    except Exception:
        return default


def normalized_bar(
    *,
    stock_code: str,
    trade_date: date,
    open_price: Any,
    high: Any,
    low: Any,
    close: Any,
    volume: Any,
    source: str,
    pre_close: Any | None = None,
    amount: Any | None = None,
    adj_factor: Any | None = 1.0,
) -> dict[str, Any] | None:
    close_value = number(close)
    open_value = number(open_price, close_value)
    high_value = number(high, max(open_value, close_value))
    low_value = number(low, min(open_value, close_value))
    volume_value = number(volume)
    if min(open_value, high_value, low_value, close_value) <= 0:
        return None
    pre_close_value = number(pre_close, close_value)
    amount_value = number(amount, volume_value * close_value)
    pct_chg = (close_value / pre_close_value - 1) * 100 if pre_close_value else 0.0
    return {
        "stock_code": stock_code,
        "trade_date": trade_date,
        "open": round(open_value, 4),
        "high": round(high_value, 4),
        "low": round(low_value, 4),
        "close": round(close_value, 4),
        "pre_close": round(pre_close_value, 4),
        "volume": round(volume_value, 2),
        "amount": round(amount_value, 2),
        "pct_chg": round(pct_chg, 4),
        "adj_factor": number(adj_factor, 1.0),
        "source": source,
    }
