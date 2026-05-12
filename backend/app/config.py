from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env from backend directory or parent directory
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AlphaRadar")
    env: str = os.getenv("ENV", "local")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./alpha_radar.db")
    database_pool_pre_ping: bool = _bool_env("DATABASE_POOL_PRE_PING", True)
    mock_data: bool = _bool_env("MOCK_DATA", True)
    market_data_source: str = os.getenv("MARKET_DATA_SOURCE", "mock")
    market_data_provider_chain: str = os.getenv("MARKET_DATA_PROVIDER_CHAIN", "")
    allow_mock_fallback: bool = _bool_env("ALLOW_MOCK_FALLBACK", True)
    enabled_markets: tuple[str, ...] = tuple(
        item.strip().upper() for item in os.getenv("ENABLED_MARKETS", "A,US,HK").split(",") if item.strip()
    )
    max_stocks_per_market: int = _int_env("MAX_STOCKS_PER_MARKET", 50)
    market_data_periods: int = _int_env("MARKET_DATA_PERIODS", 320)
    news_data_source: str = os.getenv("NEWS_DATA_SOURCE", "mock")
    news_rss_feeds: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("NEWS_RSS_FEEDS", "").split(",") if item.strip()
    )
    auto_run_pipeline_on_startup: bool = _bool_env("AUTO_RUN_PIPELINE_ON_STARTUP", False)
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    tushare_token: str | None = os.getenv("TUSHARE_TOKEN") or None
    polygon_api_key: str | None = os.getenv("POLYGON_API_KEY") or None
    tiingo_api_key: str | None = os.getenv("TIINGO_API_KEY") or None
    eodhd_api_key: str | None = os.getenv("EODHD_API_KEY") or None

    # Hermes sidecar
    hermes_endpoint: str = os.getenv("HERMES_ENDPOINT", "")
    hermes_enabled: bool = _bool_env("HERMES_ENABLED", False)


settings = Settings()
