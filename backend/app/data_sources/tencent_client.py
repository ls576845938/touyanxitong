from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from app.data_sources.market_classifier import infer_a_exchange


class TencentMarketDataClient:
    """Tencent quote adapter used as a practical daily-bar fallback.

    It is intentionally narrow: the first version only uses Tencent for A-share
    and HK daily bars because those endpoints are available without API keys in
    the current environment. Stock universe discovery stays with AKShare/mock.
    """

    source = "tencent"

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        symbol = _to_tencent_symbol(stock_code, market)
        if not symbol:
            return []
        count = max(1, min(int(periods), 1000))
        query = urllib.parse.urlencode({"param": f"{symbol},day,,,{count},qfq"})
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        if payload.get("code") != 0:
            return []
        data = payload.get("data", {}).get(symbol, {})
        raw_rows = data.get("qfqday") or data.get("day") or []
        return _normalize_tencent_rows(raw_rows, stock_code, end_date=end_date, periods=periods)


def _to_tencent_symbol(stock_code: str, market: str | None = None) -> str:
    market_key = (market or "").upper()
    code = stock_code.strip().upper()
    if market_key == "HK" or code.endswith(".HK"):
        clean = code.replace(".HK", "").zfill(5)
        return f"hk{clean[-5:]}"
    if market_key == "A" or code.isdigit():
        exchange = infer_a_exchange(code)
        if exchange == "SSE":
            return f"sh{code.zfill(6)}"
        if exchange == "SZSE":
            return f"sz{code.zfill(6)}"
        if exchange == "BSE":
            return f"bj{code.zfill(6)}"
    return ""


def _normalize_tencent_rows(
    raw_rows: list[list[Any]],
    stock_code: str,
    *,
    end_date: date | None,
    periods: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_close: float | None = None
    cutoff = end_date or date.today()
    for item in raw_rows:
        if len(item) < 6:
            continue
        trade_date = _parse_date(item[0])
        if trade_date is None or trade_date > cutoff:
            continue
        open_price = _number(item[1])
        close = _number(item[2])
        high = _number(item[3])
        low = _number(item[4])
        volume = _number(item[5])
        if close <= 0 or open_price <= 0 or high <= 0 or low <= 0:
            continue
        pre_close = previous_close or close
        rows.append(
            {
                "stock_code": stock_code,
                "trade_date": trade_date,
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "pre_close": round(pre_close, 4),
                "volume": round(volume, 2),
                "amount": round(volume * close, 2),
                "pct_chg": round((close / pre_close - 1) * 100 if pre_close else 0.0, 4),
                "adj_factor": 1.0,
                "source": "tencent",
            }
        )
        previous_close = close
    return rows[-max(1, min(int(periods), 1000)) :]


def _parse_date(value: Any) -> date | None:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value) in {"", "nan", "NaN", "None"}:
            return default
        return float(value)
    except Exception:
        return default
