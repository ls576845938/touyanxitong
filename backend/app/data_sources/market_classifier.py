from __future__ import annotations


def normalize_markets(markets: object | None, default: tuple[str, ...] = ("A", "US", "HK")) -> tuple[str, ...]:
    if markets is None:
        return default
    if isinstance(markets, str):
        raw_items = markets.split(",")
    else:
        raw_items = list(markets)  # type: ignore[arg-type]
    items = tuple(str(item).strip().upper() for item in raw_items if str(item).strip())
    return items or default


def infer_a_exchange(code: str) -> str:
    clean = code.strip()
    if clean.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"
    if clean.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"
    if clean.startswith(("4", "8", "9")):
        return "BSE"
    return "CN"


def infer_a_board(code: str) -> str:
    clean = code.strip()
    if clean.startswith(("300", "301")):
        return "chinext"
    if clean.startswith(("688", "689")):
        return "star"
    if clean.startswith(("4", "8", "9")):
        return "bse"
    return "main"


def normalize_hk_code(code: object) -> str:
    clean = str(code).strip().upper().replace(".HK", "")
    return f"{clean.zfill(5)}.HK"


def normalize_us_code(code: object) -> str:
    clean = str(code).strip().upper()
    if "." in clean and clean.split(".")[-1].isalpha():
        return clean.split(".")[-1]
    return clean


def infer_us_board(code: str) -> str:
    clean = code.upper()
    if clean.startswith(("N.", "NASDAQ.")):
        return "nasdaq"
    if clean.startswith(("NYSE.", "Y.")):
        return "nyse"
    return "us"
