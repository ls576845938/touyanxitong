from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any
from loguru import logger

from app.data_sources.market_classifier import (
    infer_a_board,
    infer_a_exchange,
    infer_us_board,
    normalize_hk_code,
    normalize_markets,
    normalize_us_code,
)


class AKShareClient:
    """AKShare adapter with conservative schema normalization.

    AKShare endpoint schemas can change, so this adapter keeps parsing defensive
    and callers should keep MockMarketDataClient fallback enabled for local MVP
    reproducibility.
    """

    source = "akshare"

    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional provider
            raise RuntimeError("AKShare is not installed or unavailable") from exc
        self.ak = ak

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = set(normalize_markets(markets))
        rows: list[dict[str, Any]] = []
        if "A" in requested:
            rows.extend(self._safe_fetch_list("A", self._fetch_a_stock_list))
        if "HK" in requested:
            rows.extend(self._safe_fetch_list("HK", self._fetch_hk_stock_list))
        if "US" in requested:
            rows.extend(self._safe_fetch_list("US", self._fetch_us_stock_list))
        return rows

    def _safe_fetch_list(self, market: str, fetcher: Any) -> list[dict[str, Any]]:
        try:
            return list(fetcher())
        except Exception as exc:  # pragma: no cover - depends on external provider/network
            logger.warning("AKShare stock list failed for {}: {}", market, exc)
            return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        market_key = (market or _infer_market_from_code(stock_code)).upper()
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")
        if market_key == "A":
            frame = self.ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_text, end_date=end_text, adjust="qfq")
            if (frame is None or len(frame) == 0) and infer_a_board(stock_code) == "bse":
                frame = self.ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_text, end_date=end_text, adjust="")
        elif market_key == "HK":
            symbol = stock_code.upper().replace(".HK", "").zfill(5)
            frame = self.ak.stock_hk_hist(symbol=symbol, period="daily", start_date=start_text, end_date=end_text, adjust="qfq")
        elif market_key == "US":
            frame = self._fetch_us_daily_frame(stock_code, start_text, end_text)
        else:
            return []
        return self._normalize_daily_frame(frame, stock_code, periods)

    def _fetch_a_stock_list(self) -> list[dict[str, Any]]:
        frame = self.ak.stock_zh_a_spot_em()
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            code = str(_pick(item, "代码", "code")).strip().zfill(6)
            name = str(_pick(item, "名称", "name")).strip()
            if not code or not name:
                continue
            asset_type = _infer_a_asset_type(code, name)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": "A",
                    "board": infer_a_board(code),
                    "exchange": infer_a_exchange(code),
                    "industry_level1": "未分类",
                    "industry_level2": "",
                    "concepts": json.dumps([], ensure_ascii=False),
                    "asset_type": asset_type,
                    "currency": "CNY",
                    "listing_status": "listed",
                    "market_cap": _market_cap_yi(_pick(item, "总市值", "market_cap")),
                    "float_market_cap": _market_cap_yi(_pick(item, "流通市值", "float_market_cap")),
                    "listing_date": None,
                    "delisting_date": None,
                    "is_st": "ST" in name.upper(),
                    "is_etf": asset_type == "etf",
                    "is_adr": False,
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "stock_zh_a_spot_em"}, ensure_ascii=False),
                }
            )
        return rows

    def _fetch_hk_stock_list(self) -> list[dict[str, Any]]:
        frame = self.ak.stock_hk_spot_em()
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            code = normalize_hk_code(_pick(item, "代码", "code"))
            name = str(_pick(item, "名称", "name")).strip()
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
                    "market_cap": _market_cap_yi(_pick(item, "总市值", "市值", "market_cap")),
                    "float_market_cap": 0.0,
                    "listing_date": None,
                    "delisting_date": None,
                    "is_st": False,
                    "is_etf": False,
                    "is_adr": False,
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "stock_hk_spot_em"}, ensure_ascii=False),
                }
            )
        return rows

    def _fetch_us_stock_list(self) -> list[dict[str, Any]]:
        frame = self.ak.stock_us_spot_em()
        rows: list[dict[str, Any]] = []
        for _, item in frame.iterrows():
            raw_code = _pick(item, "代码", "symbol", "code")
            code = normalize_us_code(raw_code)
            name = str(_pick(item, "名称", "name")).strip()
            if not code or not name:
                continue
            asset_type = _infer_us_asset_type(str(raw_code), code, name)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": "US",
                    "board": infer_us_board(str(raw_code)),
                    "exchange": "US",
                    "industry_level1": "未分类",
                    "industry_level2": "",
                    "concepts": json.dumps([], ensure_ascii=False),
                    "asset_type": asset_type,
                    "currency": "USD",
                    "listing_status": "listed",
                    "market_cap": _market_cap_yi(_pick(item, "总市值", "市值", "market_cap")),
                    "float_market_cap": 0.0,
                    "listing_date": None,
                    "delisting_date": None,
                    "is_st": False,
                    "is_etf": asset_type == "etf",
                    "is_adr": "ADR" in name.upper(),
                    "is_active": True,
                    "data_vendor": self.source,
                    "metadata_json": json.dumps({"provider": self.source, "raw_market": "stock_us_spot_em"}, ensure_ascii=False),
                }
            )
        return rows

    def _fetch_us_daily_frame(self, stock_code: str, start_text: str, end_text: str) -> Any:
        symbol = normalize_us_code(stock_code).replace("_", ".")
        if hasattr(self.ak, "stock_us_hist"):
            try:
                frame = self.ak.stock_us_hist(symbol=symbol, period="daily", start_date=start_text, end_date=end_text, adjust="")
                if frame is not None and len(frame) > 0:
                    return frame
            except Exception as exc:
                logger.debug("AKShare stock_us_hist failed for {}; trying stock_us_daily: {}", symbol, exc)
        if hasattr(self.ak, "stock_us_daily"):
            frame = self.ak.stock_us_daily(symbol=symbol, adjust="")
            if "date" in frame.columns:
                date_text = frame["date"].astype(str).str.slice(0, 10).str.replace("-", "", regex=False)
                return frame[(date_text >= start_text) & (date_text <= end_text)]
            return frame
        raise RuntimeError("AKShare US daily endpoint is unavailable")

    def _normalize_daily_frame(self, frame: Any, stock_code: str, periods: int) -> list[dict[str, Any]]:
        if frame is None or len(frame) == 0:
            return []
        rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for _, item in frame.tail(periods).iterrows():
            trade_date = _parse_date(_pick(item, "日期", "date", "trade_date"))
            close = _number(_pick(item, "收盘", "close"))
            if trade_date is None or close <= 0:
                continue
            open_price = _number(_pick(item, "开盘", "open"), close)
            high = _number(_pick(item, "最高", "high"), max(open_price, close))
            low = _number(_pick(item, "最低", "low"), min(open_price, close))
            volume = _number(_pick(item, "成交量", "volume"))
            amount = _number(_pick(item, "成交额", "amount"), volume * close)
            pre_close = previous_close or _number(_pick(item, "昨收", "pre_close"), close)
            pct_chg = _number(_pick(item, "涨跌幅", "pct_chg"), (close / pre_close - 1) * 100 if pre_close else 0)
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
                    "amount": round(amount, 2),
                    "pct_chg": round(pct_chg, 4),
                    "adj_factor": 1.0,
                    "source": self.source,
                }
            )
            previous_close = close
        return rows


def _infer_market_from_code(stock_code: str) -> str:
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


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value) in {"", "nan", "NaN", "None"}:
            return default
        return float(value)
    except Exception:
        return default


def _market_cap_yi(value: Any) -> float:
    raw = _number(value)
    if raw > 1_000_000:
        return round(raw / 100_000_000, 4)
    return raw


def _looks_like_etf(name: str, code: str) -> bool:
    upper = f"{name} {code}".upper()
    return any(token in upper for token in (" ETF", " ETN", " TRUST", " FUND"))


def _infer_a_asset_type(code: str, name: str) -> str:
    upper = f"{name} {code}".upper()
    if "ETF" in upper or "LOF" in upper or "基金" in name:
        return "etf"
    unsupported_tokens = ("定转", "转债", "债", "优先", "权证", "退市整理")
    if any(token in name for token in unsupported_tokens):
        return "other"
    if code.startswith("81"):
        return "other"
    return "equity"


def _infer_us_asset_type(raw_code: str, code: str, name: str) -> str:
    """Keep odd AKShare US rows out of the ordinary stock ingestion queue.

    AKShare's US spot endpoint can include derivative-like rows such as
    ``105.AAPL22`` and class/warrant encodings that do not map cleanly to the
    daily endpoints. They remain in the security master as ``other`` so the
    universe is auditable, but the default full-market scanner focuses on
    common-stock-style symbols first.
    """
    if _looks_like_etf(name, code):
        return "etf"
    normalized = code.upper()
    raw = raw_code.upper()
    if any(char.isdigit() for char in normalized):
        return "other"
    if "." in normalized or "_" in normalized or "." in raw or "_" in raw:
        return "other"
    unsupported_tokens = (" WARRANT", " WTS", " UNIT", " RIGHT", " PREFERRED", " NOTE", " BOND")
    upper = f"{name} {raw} {normalized}".upper()
    if any(token in upper for token in unsupported_tokens):
        return "other"
    return "equity"


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None
