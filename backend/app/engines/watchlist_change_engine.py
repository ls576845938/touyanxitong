from __future__ import annotations

from datetime import date
from typing import Any


WATCH_RATINGS = {"强观察", "观察"}
RATING_RANK = {"排除": 0, "仅记录": 1, "弱观察": 2, "观察": 3, "强观察": 4}


def build_watchlist_changes(
    *,
    latest_date: date | None,
    previous_date: date | None,
    latest_scores: list[Any],
    previous_scores: list[Any],
    stocks_by_code: dict[str, Any],
) -> dict[str, Any]:
    latest_by_code = {str(_value(row, "stock_code")): row for row in latest_scores}
    previous_by_code = {str(_value(row, "stock_code")): row for row in previous_scores}
    latest_watch = {code for code, row in latest_by_code.items() if _is_watch(row)}
    previous_watch = {code for code, row in previous_by_code.items() if _is_watch(row)}

    if previous_date is None:
        new_codes = latest_watch
        removed_codes: set[str] = set()
    else:
        new_codes = latest_watch - previous_watch
        removed_codes = previous_watch - latest_watch

    common_codes = set(latest_by_code) & set(previous_by_code)
    upgraded = []
    downgraded = []
    score_gainers = []
    score_losers = []
    for code in common_codes:
        latest = latest_by_code[code]
        previous = previous_by_code[code]
        rating_delta = _rating_rank(latest) - _rating_rank(previous)
        score_delta = _score(latest) - _score(previous)
        if rating_delta > 0 and code in latest_watch:
            upgraded.append(_change_row(code, latest, previous, stocks_by_code, "rating_upgraded"))
        if rating_delta < 0 and (code in latest_watch or code in previous_watch):
            downgraded.append(_change_row(code, latest, previous, stocks_by_code, "rating_downgraded"))
        if score_delta >= 2:
            score_gainers.append(_change_row(code, latest, previous, stocks_by_code, "score_up"))
        if score_delta <= -2:
            score_losers.append(_change_row(code, latest, previous, stocks_by_code, "score_down"))

    payload = {
        "latest_date": latest_date.isoformat() if latest_date else None,
        "previous_date": previous_date.isoformat() if previous_date else None,
        "summary": {
            "latest_watch_count": len(latest_watch),
            "previous_watch_count": len(previous_watch),
            "new_count": len(new_codes),
            "removed_count": len(removed_codes),
            "upgraded_count": len(upgraded),
            "downgraded_count": len(downgraded),
            "score_gainer_count": len(score_gainers),
            "score_loser_count": len(score_losers),
        },
        "new_entries": sorted(
            [_change_row(code, latest_by_code[code], None, stocks_by_code, "first_snapshot" if previous_date is None else "new_watch") for code in new_codes],
            key=lambda row: row["final_score"],
            reverse=True,
        ),
        "removed_entries": sorted(
            [_change_row(code, None, previous_by_code[code], stocks_by_code, "removed_watch") for code in removed_codes],
            key=lambda row: row["previous_score"] or 0,
            reverse=True,
        ),
        "upgraded": sorted(upgraded, key=lambda row: row["score_delta"], reverse=True),
        "downgraded": sorted(downgraded, key=lambda row: row["score_delta"]),
        "score_gainers": sorted(score_gainers, key=lambda row: row["score_delta"], reverse=True)[:20],
        "score_losers": sorted(score_losers, key=lambda row: row["score_delta"])[:20],
    }
    return payload


def _change_row(code: str, latest: Any | None, previous: Any | None, stocks_by_code: dict[str, Any], change_type: str) -> dict[str, Any]:
    stock = stocks_by_code.get(code)
    latest_score = _score(latest) if latest is not None else None
    previous_score = _score(previous) if previous is not None else None
    return {
        "code": code,
        "name": _value(stock, "name", code),
        "market": _value(stock, "market", ""),
        "board": _value(stock, "board", ""),
        "industry": _value(stock, "industry_level1", ""),
        "change_type": change_type,
        "rating": _value(latest, "rating", None) if latest is not None else None,
        "previous_rating": _value(previous, "rating", None) if previous is not None else None,
        "final_score": round(latest_score, 2) if latest_score is not None else None,
        "previous_score": round(previous_score, 2) if previous_score is not None else None,
        "score_delta": round((latest_score or 0) - (previous_score or 0), 2) if latest_score is not None and previous_score is not None else None,
    }


def _is_watch(row: Any) -> bool:
    return str(_value(row, "rating", "")) in WATCH_RATINGS


def _rating_rank(row: Any) -> int:
    return RATING_RANK.get(str(_value(row, "rating", "")), 0)


def _score(row: Any) -> float:
    return float(_value(row, "final_score", 0) or 0)


def _value(row: Any, field: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)
