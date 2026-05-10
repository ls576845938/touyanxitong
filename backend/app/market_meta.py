from __future__ import annotations


MARKET_LABELS: dict[str, str] = {
    "ALL": "全市场",
    "A": "A股",
    "US": "美股",
    "HK": "港股",
}

BOARD_LABELS: dict[str, str] = {
    "all": "全部",
    "main": "主板",
    "chinext": "创业板",
    "star": "科创板",
    "bse": "北交所",
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
    "amex": "AMEX",
    "us": "美股",
    "hk_main": "港股主板",
    "hk_gem": "港股 GEM",
    "etf": "ETF",
    "adr": "ADR",
}

MARKET_ORDER = ["A", "US", "HK"]
A_BOARD_ORDER = ["main", "chinext", "star", "bse", "nasdaq", "nyse", "amex", "us", "hk_main", "hk_gem", "etf", "adr"]


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, market)


def board_label(board: str) -> str:
    return BOARD_LABELS.get(board, board)
