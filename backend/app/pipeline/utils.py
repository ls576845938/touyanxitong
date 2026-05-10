from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyBar


def latest_trade_date(session: Session) -> date:
    value = session.scalars(select(DailyBar.trade_date).order_by(DailyBar.trade_date.desc()).limit(1)).first()
    return value or date.today()


def json_list(value: str | list[Any] | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
