from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.data_sources.source_quality import source_confidence, source_kind
from app.db.models import DataSourceRun


def record_data_run(
    session: Session,
    *,
    job_name: str,
    effective_source: str,
    markets: Sequence[str],
    status: str,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_total: int = 0,
    error: str = "",
    started_at: datetime | None = None,
) -> None:
    started = started_at or datetime.now(timezone.utc)
    run = DataSourceRun(
        job_name=job_name,
        requested_source=settings.market_data_source,
        effective_source=effective_source,
        source_kind=source_kind(effective_source, requested_source=settings.market_data_source),
        source_confidence=source_confidence(effective_source, requested_source=settings.market_data_source),
        markets=json.dumps(list(markets), ensure_ascii=False),
        status=status,
        rows_inserted=rows_inserted,
        rows_updated=rows_updated,
        rows_total=rows_total,
        error=error,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
