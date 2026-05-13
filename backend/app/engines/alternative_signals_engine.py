from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceEvent, NewsArticle


@dataclass
class AlternativeSignal:
    signal_name: str
    subject_type: str  # stock / industry
    subject_id: str
    subject_name: str
    value: float  # normalized 0-100
    value_type: str  # score / count / ratio
    source: str  # "internal_evidence" / "news_aggregation" / "deterministic_proxy"
    observed_at: str  # ISO date
    confidence: float  # 0-1
    freshness: str  # "realtime" / "daily" / "weekly"
    coverage_status: str  # "available" / "unavailable" / "pending_connector"
    metadata_json: dict = field(default_factory=dict)


def compute_evidence_momentum_signal(
    session: Session,
    *,
    subject_type: str,
    subject_id: str,
    subject_name: str,
    trade_date: date | None = None,
) -> AlternativeSignal:
    """Compute evidence event momentum for a stock.

    Counts EvidenceEvent rows whose affected_security_ids contain subject_id.
    Compares recent 7d count to prior 7d count.  If recent > prior * 1.3
    the signal is positive.  Normalized to 0-100.
    """
    observed_at = trade_date or date.today()
    period_14d_ago = _dt_begin(observed_at - timedelta(days=14))
    period_7d_ago = _dt_begin(observed_at - timedelta(days=7))
    period_end = _dt_end(observed_at)

    rows = session.scalars(
        select(EvidenceEvent).where(
            EvidenceEvent.event_time >= period_14d_ago,
            EvidenceEvent.event_time <= period_end,
        )
    ).all()

    recent_count = 0
    prior_count = 0
    recent_positive = 0
    recent_negative = 0

    for row in rows:
        ids = _json_str_list(row.affected_security_ids)
        if subject_id not in ids:
            continue
        et = row.event_time
        if et.tzinfo is None:
            et = et.replace(tzinfo=timezone.utc)
        if period_7d_ago <= et <= period_end:
            recent_count += 1
            direction = str(row.impact_direction or "").lower()
            if direction == "positive":
                recent_positive += 1
            elif direction == "negative":
                recent_negative += 1
        elif period_14d_ago <= et < period_7d_ago:
            prior_count += 1

    if recent_count == 0 and prior_count == 0:
        return AlternativeSignal(
            signal_name="evidence_momentum",
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            value=0.0,
            value_type="score",
            source="internal_evidence",
            observed_at=observed_at.isoformat(),
            confidence=0.0,
            freshness="daily",
            coverage_status="available",
            metadata_json={
                "recent_count": 0,
                "prior_count": 0,
                "direction": "neutral",
                "explanation": "近期无证据事件记录。",
            },
        )

    ratio = recent_count / max(prior_count, 1)
    if ratio >= 1.3:
        score = min(100.0, 50.0 + ratio * 20.0 + (recent_positive / max(recent_count, 1)) * 30.0)
        direction = "positive"
    elif ratio <= 0.7:
        score = max(0.0, 50.0 - (1.0 / max(ratio, 0.01)) * 12.0)
        direction = "negative"
    else:
        score = 50.0
        direction = "neutral"

    sent_ratio = recent_positive / max(recent_count, 1)
    avg_conf = _signal_confidence(recent_count, recent_positive, recent_negative)

    return AlternativeSignal(
        signal_name="evidence_momentum",
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name=subject_name,
        value=round(max(0.0, min(100.0, score)), 2),
        value_type="score",
        source="internal_evidence",
        observed_at=observed_at.isoformat(),
        confidence=round(avg_conf, 4),
        freshness="daily",
        coverage_status="available",
        metadata_json={
            "recent_count": recent_count,
            "prior_count": prior_count,
            "ratio": round(ratio, 4),
            "direction": direction,
            "positive_ratio": round(sent_ratio, 4),
            "explanation": _evidence_explanation(direction, recent_count, prior_count, ratio),
        },
    )


def compute_news_sentiment_signal(
    session: Session,
    *,
    subject_type: str,
    subject_id: str,
    subject_name: str,
    trade_date: date | None = None,
) -> AlternativeSignal:
    """Compute news article momentum for a stock.

    Counts NewsArticle rows whose related_stocks contain subject_id.
    Compares recent 7d count to prior 7d count and normalizes to 0-100.
    """
    observed_at = trade_date or date.today()
    period_14d_ago = _dt_begin(observed_at - timedelta(days=14))
    period_7d_ago = _dt_begin(observed_at - timedelta(days=7))
    period_end = _dt_end(observed_at)

    rows = session.scalars(
        select(NewsArticle).where(
            NewsArticle.published_at >= period_14d_ago,
            NewsArticle.published_at <= period_end,
        )
    ).all()

    recent_count = 0
    prior_count = 0

    for row in rows:
        ids = _json_str_list(row.related_stocks)
        if subject_id not in ids:
            continue
        pt = row.published_at
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)
        if period_7d_ago <= pt <= period_end:
            recent_count += 1
        elif period_14d_ago <= pt < period_7d_ago:
            prior_count += 1

    if recent_count == 0 and prior_count == 0:
        return AlternativeSignal(
            signal_name="news_sentiment",
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            value=0.0,
            value_type="score",
            source="internal_evidence",
            observed_at=observed_at.isoformat(),
            confidence=0.0,
            freshness="daily",
            coverage_status="available",
            metadata_json={
                "recent_count": 0,
                "prior_count": 0,
                "momentum": 0.0,
                "explanation": "近期无相关新闻文章。",
            },
        )

    momentum = recent_count / max(prior_count, 1)
    if momentum >= 1.3:
        score = min(100.0, 50.0 + momentum * 18.0)
    elif momentum <= 0.7:
        score = max(0.0, 50.0 - (1.0 / max(momentum, 0.01)) * 10.0)
    else:
        score = 50.0 + (momentum - 1.0) * 30.0

    avg_conf = _article_confidence(rows, subject_id)
    return AlternativeSignal(
        signal_name="news_sentiment",
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name=subject_name,
        value=round(max(0.0, min(100.0, score)), 2),
        value_type="score",
        source="internal_evidence",
        observed_at=observed_at.isoformat(),
        confidence=round(avg_conf, 4),
        freshness="daily",
        coverage_status="available",
        metadata_json={
            "recent_count": recent_count,
            "prior_count": prior_count,
            "momentum": round(momentum, 4),
            "explanation": _news_explanation(recent_count, prior_count, momentum),
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dt_begin(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _dt_end(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=timezone.utc)


def _json_str_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item).strip() for item in parsed if item]


def _signal_confidence(recent_count: int, positive_count: int, negative_count: int) -> float:
    if recent_count == 0:
        return 0.0
    base = min(1.0, recent_count / 10.0)
    balance = 1.0 - abs(positive_count - negative_count) / max(recent_count, 1) * 0.5
    return base * max(0.3, balance)


def _article_confidence(articles: list[NewsArticle], subject_id: str) -> float:
    matched = [
        a for a in articles
        if subject_id in _json_str_list(a.related_stocks)
    ]
    if not matched:
        return 0.0
    confs = [max(0.0, min(1.0, float(a.source_confidence or 0.3))) for a in matched]
    avg = sum(confs) / len(confs)
    volume_bonus = min(0.2, len(matched) * 0.02)
    return min(1.0, avg + volume_bonus)


def _evidence_explanation(
    direction: str,
    recent_count: int,
    prior_count: int,
    ratio: float,
) -> str:
    if direction == "positive":
        return (
            f"证据事件数量上升：近7日{recent_count}件 vs 前7日{prior_count}件 "
            f"（{ratio:.1f}倍），表明关注度或验证事件加速。"
        )
    if direction == "negative":
        return (
            f"证据事件数量下降：近7日{recent_count}件 vs 前7日{prior_count}件 "
            f"（{ratio:.1f}倍），近期验证密度降低。"
        )
    return (
        f"证据事件数量平稳：近7日{recent_count}件 vs 前7日{prior_count}件 "
        f"（{ratio:.1f}倍）。"
    )


def _news_explanation(recent_count: int, prior_count: int, momentum: float) -> str:
    if momentum >= 1.3:
        return (
            f"新闻覆盖加速：近7日{recent_count}篇 vs 前7日{prior_count}篇 "
            f"（{momentum:.1f}倍），市场关注度提升。"
        )
    if momentum <= 0.7:
        return (
            f"新闻覆盖减弱：近7日{recent_count}篇 vs 前7日{prior_count}篇 "
            f"（{momentum:.1f}倍），话题热度降温。"
        )
    return (
        f"新闻覆盖平稳：近7日{recent_count}篇 vs 前7日{prior_count}篇 "
        f"（{momentum:.1f}倍）。"
    )
