from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.data_sources.http_utils import normalized_bar, number, parse_date
from app.data_sources.market_classifier import infer_a_board, infer_a_exchange, normalize_hk_code, normalize_markets, normalize_us_code


class TushareClient:
    """Tushare Pro adapter for stock master and daily bars.

    Tushare endpoint access depends on account points/permissions. Each method
    is defensive and returns an empty list when a market endpoint is unavailable
    so the provider registry can continue to the next source.
    """

    source = "tushare"

    def __init__(self, token: str | None) -> None:
        if not token:
            raise RuntimeError("Tushare token is missing")
        try:
            import tushare as ts  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional provider
            raise RuntimeError("Tushare is not installed or unavailable") from exc
        self.ts = ts
        self.pro = ts.pro_api(token)

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = set(normalize_markets(markets))
        rows: list[dict[str, Any]] = []
        if "A" in requested:
            rows.extend(self._fetch_a_stock_list())
        if "HK" in requested:
            rows.extend(self._fetch_hk_stock_list())
        if "US" in requested:
            rows.extend(self._fetch_us_stock_list())
        return rows

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        market_key = (market or _infer_market(stock_code)).upper()
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")
        if market_key == "A":
            ts_code = _to_tushare_a_code(stock_code)
            frame = self.pro.daily(ts_code=ts_code, start_date=start_text, end_date=end_text)
        elif market_key == "HK":
            ts_code = _to_tushare_hk_code(stock_code)
            frame = _safe_query(self.pro, "hk_daily_adj", ts_code=ts_code, start_date=start_text, end_date=end_text)
            if frame is None or len(frame) == 0:
                frame = _safe_query(self.pro, "hk_daily", ts_code=ts_code, start_date=start_text, end_date=end_text)
        elif market_key == "US":
            ts_code = normalize_us_code(stock_code).replace("_", ".")
            frame = _safe_query(self.pro, "us_daily", ts_code=ts_code, start_date=start_text, end_date=end_text)
        else:
            return []
        return _normalize_tushare_daily_frame(frame, stock_code, periods, self.source)

    def _fetch_a_stock_list(self) -> list[dict[str, Any]]:
        frame = _safe_query(
            self.pro,
            "stock_basic",
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,industry,market,list_date",
        )
        if frame is None:
            return []
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            code = str(_pick(item, "symbol", "ts_code")).split(".")[0].zfill(6)
            name = str(_pick(item, "name")).strip()
            if not code or not name:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": "A",
                    "board": infer_a_board(code),
                    "exchange": infer_a_exchange(code),
                    "industry_level1": str(_pick(item, "industry")) or "未分类",
                    "industry_level2": "",
                    "concepts": json.dumps([], ensure_ascii=False),
                    "asset_type": "equity",
                    "currency": "CNY",
                    "listing_status": "listed",
                    "market_cap": 0.0,
                    "float_market_cap": 0.0,
                    "listing_date": parse_date(_pick(item, "list_date")),
                    "delisting_date": None,
                    "is_st": "ST" in name.upper(),
                    "is_etf": False,
                    "is_adr": False,
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "stock_basic"}, ensure_ascii=False),
                }
            )
        return rows

    def _fetch_hk_stock_list(self) -> list[dict[str, Any]]:
        frame = _safe_query(self.pro, "hk_basic")
        if frame is None:
            return []
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            ts_code = str(_pick(item, "ts_code", "symbol")).strip()
            code = normalize_hk_code(ts_code.split(".")[0])
            name = str(_pick(item, "name", "fullname", "enname")).strip()
            if not code or not name:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": "HK",
                    "board": "hk_main",
                    "exchange": "HKEX",
                    "industry_level1": "未分类",
                    "industry_level2": "",
                    "concepts": json.dumps([], ensure_ascii=False),
                    "asset_type": "equity",
                    "currency": "HKD",
                    "listing_status": "listed",
                    "market_cap": 0.0,
                    "float_market_cap": 0.0,
                    "listing_date": parse_date(_pick(item, "list_date")),
                    "delisting_date": None,
                    "is_st": False,
                    "is_etf": False,
                    "is_adr": False,
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "hk_basic"}, ensure_ascii=False),
                }
            )
        return rows

    def _fetch_us_stock_list(self) -> list[dict[str, Any]]:
        frame = _safe_query(self.pro, "us_basic")
        if frame is None:
            return []
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            code = normalize_us_code(_pick(item, "ts_code", "symbol"))
            name = str(_pick(item, "name", "fullname")).strip()
            if not code or not name:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": "US",
                    "board": "us_common",
                    "exchange": str(_pick(item, "exchange") or "US"),
                    "industry_level1": "未分类",
                    "industry_level2": "",
                    "concepts": json.dumps([], ensure_ascii=False),
                    "asset_type": "equity",
                    "currency": "USD",
                    "listing_status": "listed",
                    "market_cap": 0.0,
                    "float_market_cap": 0.0,
                    "listing_date": parse_date(_pick(item, "list_date")),
                    "delisting_date": None,
                    "is_st": False,
                    "is_etf": False,
                    "is_adr": False,
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "us_basic"}, ensure_ascii=False),
                }
            )
        return rows


def _normalize_tushare_daily_frame(frame: Any, stock_code: str, periods: int, source: str) -> list[dict[str, Any]]:
    if frame is None or len(frame) == 0:
        return []
    rows: list[dict[str, Any]] = []
    previous_close: float | None = None
    try:
        frame = frame.sort_values("trade_date")
    except Exception:
        pass
    for _, item in frame.tail(periods).iterrows():
        trade_date = parse_date(_pick(item, "trade_date", "date"))
        if trade_date is None:
            continue
        close = _pick(item, "close", "adj_close")
        bar = normalized_bar(
            stock_code=stock_code,
            trade_date=trade_date,
            open_price=_pick(item, "open"),
            high=_pick(item, "high"),
            low=_pick(item, "low"),
            close=close,
            pre_close=_pick(item, "pre_close") or previous_close or close,
            volume=_pick(item, "vol", "volume"),
            amount=_pick(item, "amount"),
            adj_factor=_pick(item, "adj_factor") or 1.0,
            source=source,
        )
        if bar is not None:
            rows.append(bar)
            previous_close = float(bar["close"])
    return rows[-max(1, periods) :]


def _safe_query(pro: Any, name: str, **kwargs: Any) -> Any:
    try:
        method = getattr(pro, name)
    except Exception:
        return None
    try:
        return method(**kwargs)
    except Exception:
        return None


def _to_tushare_a_code(stock_code: str) -> str:
    code = stock_code.strip().split(".")[0].zfill(6)
    exchange = infer_a_exchange(code)
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def _to_tushare_hk_code(stock_code: str) -> str:
    code = normalize_hk_code(stock_code).replace(".HK", "").zfill(5)
    return f"{code}.HK"


def _infer_market(stock_code: str) -> str:
    if stock_code.upper().endswith(".HK"):
        return "HK"
    if stock_code.isdigit():
        return "A"
    return "US"


def _pick(item: Any, *keys: str) -> Any:
    for key in keys:
        try:
            value = item[key]
        except Exception:
            continue
        if value is not None and str(value) not in {"", "nan", "NaN", "None"}:
            return value
    return ""
