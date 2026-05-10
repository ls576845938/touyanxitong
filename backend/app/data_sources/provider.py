from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from loguru import logger

from app.config import settings
from app.data_sources.akshare_client import AKShareClient
from app.data_sources.base import MarketDataClient
from app.data_sources.market_classifier import normalize_markets
from app.data_sources.mock_data import MockMarketDataClient
from app.data_sources.registry import RegistryMarketDataClient
from app.data_sources.source_quality import source_confidence, source_kind
from app.data_sources.tencent_client import TencentMarketDataClient


class FallbackMarketDataClient:
    """Use a real provider first and keep the MVP pipeline runnable with mock fallback."""

    def __init__(self, primary: MarketDataClient, fallback: MarketDataClient) -> None:
        self.primary = primary
        self.fallback = fallback
        self.source = f"{primary.source}+{fallback.source}_fallback"
        self.last_effective_source = primary.source

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = normalize_markets(markets, settings.enabled_markets)
        try:
            rows = self.primary.fetch_stock_list(markets=requested)
            if rows:
                self.last_effective_source = self.primary.source
                return rows
            logger.warning("primary market data provider returned empty stock list; falling back to mock")
        except Exception as exc:  # pragma: no cover - depends on external provider/network
            logger.warning("primary market data provider failed for stock list: {}", exc)
        self.last_effective_source = getattr(self.fallback, "last_effective_source", self.fallback.source)
        return self.fallback.fetch_stock_list(markets=requested)

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        try:
            rows = self.primary.fetch_daily_bars(stock_code, market=market, end_date=end_date, periods=periods)
            if rows:
                self.last_effective_source = self.primary.source
                return rows
            logger.debug("primary provider returned no bars for {}; trying mock fallback", stock_code)
        except Exception as exc:  # pragma: no cover - depends on external provider/network
            logger.warning("primary market data provider failed for {}: {}", stock_code, exc)
        self.last_effective_source = getattr(self.fallback, "last_effective_source", self.fallback.source)
        rows = self.fallback.fetch_daily_bars(stock_code, market=market, end_date=end_date, periods=periods)
        for row in rows:
            row_source = str(row.get("source") or self.last_effective_source)
            kind = source_kind(row_source, requested_source=self.primary.source)
            row["source_kind"] = "fallback" if kind == "mock" else kind
            row["source_confidence"] = source_confidence(row_source, requested_source=self.primary.source)
        return rows


def get_market_data_client(source: str | None = None) -> MarketDataClient:
    source = (source or settings.market_data_source).lower()
    fallback = MockMarketDataClient()
    if settings.mock_data or source == "mock":
        return fallback
    if source in {"auto", "akshare", "baostock", "eodhd", "polygon", "tencent", "tiingo", "tushare", "yahoo"} or "," in source:
        return RegistryMarketDataClient(source=source)
    logger.warning("unknown MARKET_DATA_SOURCE='{}'; using registry auto chain", source)
    return RegistryMarketDataClient(source="auto")
