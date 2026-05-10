from __future__ import annotations

from datetime import date
from typing import Any

from app.data_sources.mock_data import MockMarketDataClient
from app.data_sources.registry import DEFAULT_PROVIDER_CHAINS, ProviderDefinition, ProviderRegistry, RegistryMarketDataClient
from app.data_sources.source_quality import source_kind
from app.data_sources.yahoo_client import _to_yahoo_symbol


class EmptyClient:
    source = "empty"

    def fetch_stock_list(self, markets=None):
        return []

    def fetch_daily_bars(self, stock_code: str, market: str | None = None, end_date: date | None = None, periods: int = 320):
        return []


class RealClient:
    def __init__(self, source: str, markets: tuple[str, ...] = ("US",), stock_rows: list[dict[str, Any]] | None = None) -> None:
        self.source = source
        self.markets = markets
        self.stock_rows = stock_rows or []

    def fetch_stock_list(self, markets=None):
        requested = set(markets or self.markets)
        return [row for row in self.stock_rows if row["market"] in requested]

    def fetch_daily_bars(self, stock_code: str, market: str | None = None, end_date: date | None = None, periods: int = 320):
        return [
            {
                "stock_code": stock_code,
                "trade_date": date(2026, 5, 8),
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "pre_close": 10,
                "volume": 1_000_000,
                "amount": 10_500_000,
                "pct_chg": 5,
                "adj_factor": 1,
                "source": self.source,
            }
        ]


def test_registry_client_uses_provider_chain_before_fallback() -> None:
    registry = ProviderRegistry(
        {
            "tiingo": ProviderDefinition("tiingo", ("US",), lambda: EmptyClient()),
            "polygon": ProviderDefinition("polygon", ("US",), lambda: RealClient("polygon")),
        }
    )
    client = RegistryMarketDataClient(source="tiingo,polygon", registry=registry, allow_mock_fallback=False)

    rows = client.fetch_daily_bars("NVDA", market="US", periods=1)

    assert rows[0]["source"] == "polygon"
    assert rows[0]["source_kind"] == "real"
    assert rows[0]["source_confidence"] == 1.0
    assert client.last_effective_source == "polygon"


def test_registry_client_marks_mock_as_fallback_when_real_chain_has_no_bars() -> None:
    registry = ProviderRegistry({"akshare": ProviderDefinition("akshare", ("A",), lambda: EmptyClient())})
    client = RegistryMarketDataClient(source="auto", registry=registry, fallback=MockMarketDataClient(), allow_mock_fallback=True)

    rows = client.fetch_daily_bars("300308", market="A", periods=3)

    assert rows
    assert {row["source"] for row in rows} == {"mock"}
    assert {row["source_kind"] for row in rows} == {"fallback"}
    assert max(row["source_confidence"] for row in rows) <= 0.35


def test_registry_client_can_merge_market_specific_stock_lists() -> None:
    registry = ProviderRegistry(
        {
            "tencent": ProviderDefinition(
                "tencent",
                ("A", "HK"),
                lambda: RealClient(
                    "tencent",
                    ("A", "HK"),
                    [
                        {"code": "300308", "name": "中际旭创", "market": "A", "data_vendor": "tencent"},
                        {"code": "00700.HK", "name": "腾讯控股", "market": "HK", "data_vendor": "tencent"},
                    ],
                ),
            ),
            "yahoo": ProviderDefinition("yahoo", ("A", "HK", "US"), lambda: RealClient("yahoo", ("US",), [{"code": "NVDA", "name": "NVIDIA", "market": "US", "data_vendor": "yahoo"}])),
        }
    )
    client = RegistryMarketDataClient(source="auto", registry=registry, allow_mock_fallback=False)

    rows = client.fetch_stock_list(markets=("A", "HK", "US"))

    assert {row["code"] for row in rows} == {"300308", "00700.HK", "NVDA"}
    assert client.last_effective_source == "tencent,yahoo"


def test_configured_real_provider_sources_are_research_grade() -> None:
    for source in ("yahoo", "baostock", "polygon", "tiingo", "eodhd"):
        assert source_kind(source) == "real"


def test_default_provider_chains_are_free_only() -> None:
    assert DEFAULT_PROVIDER_CHAINS == {
        "A": ("tencent", "yahoo", "baostock", "akshare"),
        "HK": ("tencent", "yahoo", "akshare"),
        "US": ("yahoo", "akshare"),
    }


def test_yahoo_symbol_mapping_covers_a_hk_us() -> None:
    assert _to_yahoo_symbol("600519", "A") == "600519.SS"
    assert _to_yahoo_symbol("300308", "A") == "300308.SZ"
    assert _to_yahoo_symbol("00700.HK", "HK") == "0700.HK"
    assert _to_yahoo_symbol("NVDA", "US") == "NVDA"
