from __future__ import annotations

import json
from datetime import date

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import AlternativeSignalRecord, Stock
from app.engines.alternative_signals_engine import (
    AlternativeSignal,
    compute_evidence_momentum_signal,
    compute_news_sentiment_signal,
)
from app.pipeline.utils import latest_trade_date


def run_alternative_signals_job(session: Session, trade_date: date | None = None) -> dict[str, int | str]:
    """Compute alternative signals for all active stocks and persist to DB."""
    target_date = trade_date or latest_trade_date(session)
    stocks = session.scalars(
        select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.code)
    ).all()

    if not stocks:
        logger.info("alternative signals computed: 0 (no active stocks)")
        return {"alternative_signals": 0, "effective_date": target_date.isoformat()}

    recorded = 0
    for stock in stocks:
        signals = _compute_signals_for_stock(session, stock, target_date)
        for sig in signals:
            _upsert_signal(session, sig, target_date)
            recorded += 1

    session.commit()
    logger.info(
        "alternative signals computed: {} for {} stocks (date={})",
        recorded,
        len(stocks),
        target_date,
    )
    return {"alternative_signals": recorded, "effective_date": target_date.isoformat()}


def _compute_signals_for_stock(
    session: Session,
    stock: Stock,
    trade_date: date,
) -> list[AlternativeSignal]:
    return [
        compute_evidence_momentum_signal(
            session,
            subject_type="stock",
            subject_id=stock.code,
            subject_name=stock.name,
            trade_date=trade_date,
        ),
        compute_news_sentiment_signal(
            session,
            subject_type="stock",
            subject_id=stock.code,
            subject_name=stock.name,
            trade_date=trade_date,
        ),
    ]


def _upsert_signal(session: Session, signal: AlternativeSignal, trade_date: date) -> None:
    existing = session.scalar(
        select(AlternativeSignalRecord).where(
            AlternativeSignalRecord.signal_name == signal.signal_name,
            AlternativeSignalRecord.subject_id == signal.subject_id,
            AlternativeSignalRecord.observed_at == trade_date,
        )
    )
    payload = {
        "signal_name": signal.signal_name,
        "subject_type": signal.subject_type,
        "subject_id": signal.subject_id,
        "subject_name": signal.subject_name,
        "value": signal.value,
        "value_type": signal.value_type,
        "source": signal.source,
        "observed_at": trade_date,
        "confidence": signal.confidence,
        "freshness": signal.freshness,
        "status": signal.coverage_status,
        "metadata_json": json.dumps(signal.metadata_json, ensure_ascii=False),
    }
    if existing is None:
        session.add(AlternativeSignalRecord(**payload))
    else:
        for key, value in payload.items():
            setattr(existing, key, value)
