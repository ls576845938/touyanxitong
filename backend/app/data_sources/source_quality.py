from __future__ import annotations


REAL_SOURCES = {
    "akshare",
    "baostock",
    "databento",
    "eodhd",
    "fmp",
    "polygon",
    "tencent",
    "tiingo",
    "tushare",
    "twelvedata",
    "yahoo",
}
MOCK_SOURCES = {"mock"}


def source_kind(source: str | None, *, requested_source: str | None = None) -> str:
    normalized = (source or "").lower()
    requested = (requested_source or "").lower()
    parts = {part.strip() for part in normalized.replace("+", ",").split(",") if part.strip()}
    if "fallback" in normalized:
        return "fallback"
    if parts & MOCK_SOURCES:
        return "fallback" if requested and requested not in MOCK_SOURCES else "mock"
    if parts & REAL_SOURCES:
        return "real"
    return "unknown"


def source_confidence(source: str | None, *, requested_source: str | None = None) -> float:
    kind = source_kind(source, requested_source=requested_source)
    if kind == "real":
        return 1.0
    if kind == "fallback":
        return 0.35
    if kind == "mock":
        return 0.1
    return 0.0


def real_data_only(source: str | None) -> bool:
    return source_kind(source) == "real"
