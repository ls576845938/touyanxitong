from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.data_sources.http_utils import normalized_bar, parse_date
from app.data_sources.market_classifier import infer_a_exchange


class BaoStockClient:
    """BaoStock adapter for A-share daily bars.

    BaoStock is a practical free fallback for A-share historical daily data. It
    is optional and only used when the package is installed in the environment.
    """

    source = "baostock"

    def __init__(self) -> None:
        try:
            import baostock as bs  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("BaoStock is not installed or unavailable") from exc
        self.bs = bs
        login = self.bs.login()
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock login failed: {getattr(login, 'error_msg', '')}")

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        if (market or "A").upper() != "A":
            return []
        symbol = _to_baostock_symbol(stock_code)
        if not symbol:
            return []
        end = end_date or date.today()
        start = end - timedelta(days=max(periods * 3, 420))
        fields = "date,code,open,high,low,close,preclose,volume,amount,pctChg"
        result = self.bs.query_history_k_data_plus(
            symbol,
            fields,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            frequency="d",
            adjustflag="2",
        )
        rows: list[dict[str, Any]] = []
        while getattr(result, "error_code", "0") == "0" and result.next():
            item = dict(zip(result.fields, result.get_row_data(), strict=False))
            trade_date = parse_date(item.get("date"))
            if trade_date is None or trade_date > end:
                continue
            bar = normalized_bar(
                stock_code=stock_code,
                trade_date=trade_date,
                open_price=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                pre_close=item.get("preclose"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                adj_factor=1.0,
                source=self.source,
            )
            if bar is not None:
                rows.append(bar)
        return rows[-max(1, periods) :]


def _to_baostock_symbol(stock_code: str) -> str:
    code = stock_code.strip().zfill(6)
    exchange = infer_a_exchange(code)
    if exchange == "SSE":
        return f"sh.{code}"
    if exchange in {"SZSE", "BSE"}:
        return f"sz.{code}"
    return ""
