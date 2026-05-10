from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from loguru import logger

from app.config import settings
from app.data_sources.akshare_client import AKShareClient
from app.data_sources.baostock_client import BaoStockClient
from app.data_sources.base import MarketDataClient
from app.data_sources.eodhd_client import EODHDClient
from app.data_sources.market_classifier import normalize_markets
from app.data_sources.mock_data import MockMarketDataClient
from app.data_sources.polygon_client import PolygonClient
from app.data_sources.source_quality import source_confidence, source_kind
from app.data_sources.tencent_client import TencentMarketDataClient
from app.data_sources.tiingo_client import TiingoClient
from app.data_sources.tushare_client import TushareClient
from app.data_sources.yahoo_client import YahooChartClient


DEFAULT_PROVIDER_CHAINS: dict[str, tuple[str, ...]] = {
    "A": ("tencent", "yahoo", "baostock", "akshare"),
    "HK": ("tencent", "yahoo", "akshare"),
    "US": ("yahoo", "akshare"),
}


@dataclass(frozen=True)
class ProviderDefinition:
    name: str
    markets: tuple[str, ...]
    factory: Callable[[], MarketDataClient]


class ProviderRegistry:
    def __init__(self, definitions: dict[str, ProviderDefinition] | None = None) -> None:
        self.definitions = definitions or _default_definitions()
        self._cache: dict[str, MarketDataClient] = {}

    def provider_names_for_market(self, market: str, source: str | None = None) -> tuple[str, ...]:
        normalized_market = market.upper()
        source_key = (source or settings.market_data_source or "auto").lower()
        configured = _configured_chains(settings.market_data_provider_chain)
        if source_key == "mock":
            return ("mock",)
        if source_key == "auto":
            names = configured.get(normalized_market) or DEFAULT_PROVIDER_CHAINS.get(normalized_market, ("akshare",))
        else:
            names = tuple(item.strip().lower() for item in source_key.split(",") if item.strip())
        return tuple(name for name in names if self.supports_market(name, normalized_market))

    def supports_market(self, name: str, market: str) -> bool:
        if name == "mock":
            return True
        definition = self.definitions.get(name)
        return definition is not None and market.upper() in definition.markets

    def create_provider(self, name: str) -> MarketDataClient:
        normalized = name.lower()
        if normalized == "mock":
            return MockMarketDataClient()
        if normalized not in self._cache:
            definition = self.definitions.get(normalized)
            if definition is None:
                raise RuntimeError(f"unknown market data provider: {name}")
            self._cache[normalized] = definition.factory()
        return self._cache[normalized]


class RegistryMarketDataClient:
    """Market-aware provider chain with optional mock fallback.

    It keeps the old MVP behavior available while making the production path
    explicit: each market has an ordered chain and token-gated providers are
    skipped when not configured.
    """

    def __init__(
        self,
        *,
        source: str | None = None,
        registry: ProviderRegistry | None = None,
        fallback: MarketDataClient | None = None,
        allow_mock_fallback: bool | None = None,
    ) -> None:
        self.requested_source = (source or settings.market_data_source or "auto").lower()
        self.registry = registry or ProviderRegistry()
        self.fallback = fallback or MockMarketDataClient()
        self.allow_mock_fallback = settings.allow_mock_fallback if allow_mock_fallback is None else allow_mock_fallback
        self.source = f"registry:{self.requested_source}"
        self.last_effective_source = self.source

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = normalize_markets(markets, settings.enabled_markets)
        rows: list[dict[str, Any]] = []
        effective_sources: list[str] = []
        for market in requested:
            market_rows = self._fetch_stock_list_for_market(market)
            if not market_rows and self.allow_mock_fallback:
                market_rows = self.fallback.fetch_stock_list(markets=(market,))
            if market_rows:
                rows.extend(market_rows)
                effective_sources.append(str(market_rows[0].get("data_vendor") or market_rows[0].get("source") or "unknown"))
        if rows:
            self.last_effective_source = ",".join(sorted(set(effective_sources))) if effective_sources else self.source
            return rows
        return []

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        market_key = (market or _infer_market(stock_code)).upper()
        for name in self.registry.provider_names_for_market(market_key, self.requested_source):
            try:
                provider = self.registry.create_provider(name)
                rows = provider.fetch_daily_bars(stock_code, market=market_key, end_date=end_date, periods=periods)
            except Exception as exc:  # pragma: no cover - external provider/network
                logger.debug("market data provider {} failed for {}: {}", name, stock_code, exc)
                continue
            if rows:
                self.last_effective_source = getattr(provider, "source", name)
                return _annotate_rows(rows, self.last_effective_source, requested_source=name)
            logger.debug("market data provider {} returned no bars for {}", name, stock_code)
        if not self.allow_mock_fallback:
            self.last_effective_source = "none"
            return []
        self.last_effective_source = self.fallback.source
        rows = self.fallback.fetch_daily_bars(stock_code, market=market_key, end_date=end_date, periods=periods)
        return _annotate_rows(rows, self.fallback.source, requested_source=self.requested_source, force_fallback=self.requested_source != "mock")

    def _fetch_stock_list_for_market(self, market: str) -> list[dict[str, Any]]:
        for name in self.registry.provider_names_for_market(market, self.requested_source):
            try:
                provider = self.registry.create_provider(name)
                rows = provider.fetch_stock_list(markets=(market,))
            except Exception as exc:  # pragma: no cover - external provider/network
                logger.debug("stock list provider {} failed for {}: {}", name, market, exc)
                continue
            if rows:
                return rows
        return []


def _default_definitions() -> dict[str, ProviderDefinition]:
    return {
        "akshare": ProviderDefinition("akshare", ("A", "HK", "US"), lambda: AKShareClient()),
        "baostock": ProviderDefinition("baostock", ("A",), lambda: BaoStockClient()),
        "eodhd": ProviderDefinition("eodhd", ("A", "HK", "US"), lambda: EODHDClient(settings.eodhd_api_key)),
        "polygon": ProviderDefinition("polygon", ("US",), lambda: PolygonClient(settings.polygon_api_key)),
        "tencent": ProviderDefinition("tencent", ("A", "HK"), lambda: TencentMarketDataClient()),
        "tiingo": ProviderDefinition("tiingo", ("US",), lambda: TiingoClient(settings.tiingo_api_key)),
        "tushare": ProviderDefinition("tushare", ("A", "HK", "US"), lambda: TushareClient(settings.tushare_token)),
        "yahoo": ProviderDefinition("yahoo", ("A", "HK", "US"), lambda: YahooChartClient()),
    }


def _configured_chains(value: str) -> dict[str, tuple[str, ...]]:
    chains: dict[str, tuple[str, ...]] = {}
    for segment in (value or "").split(";"):
        if "=" not in segment:
            continue
        market, raw_names = segment.split("=", 1)
        market_key = market.strip().upper()
        names = tuple(item.strip().lower() for item in raw_names.split(",") if item.strip())
        if market_key in {"A", "HK", "US"} and names:
            chains[market_key] = names
    return chains


def _annotate_rows(
    rows: list[dict[str, Any]],
    effective_source: str,
    *,
    requested_source: str | None,
    force_fallback: bool = False,
) -> list[dict[str, Any]]:
    for row in rows:
        row_source = str(row.get("source") or effective_source)
        row["source"] = row_source
        kind = source_kind(row_source, requested_source=requested_source)
        row["source_kind"] = "fallback" if force_fallback or kind == "mock" and requested_source not in {None, "", "mock"} else kind
        row["source_confidence"] = source_confidence(row_source, requested_source=requested_source)
        if force_fallback:
            row["source_confidence"] = min(float(row["source_confidence"]), 0.35)
    return rows


def _infer_market(stock_code: str) -> str:
    code = stock_code.strip().upper()
    if code.endswith(".HK"):
        return "HK"
    if code.isdigit():
        return "A"
    return "US"
