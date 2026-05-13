from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.db.models import EvidenceEvent, NewsArticle
from app.engines.alternative_signals_engine import (
    AlternativeSignal,
    _dt_begin,
    _dt_end,
    _json_str_list,
    compute_evidence_momentum_signal,
    compute_news_sentiment_signal,
)


def _mock_session(rows: list) -> SimpleNamespace:
    """Return a minimal session-like object that mimics scalar(select(...)).all()."""
    stored = list(rows)

    def scalars(query) -> SimpleNamespace:
        class FakeScalarResult:
            def all(self):
                return stored
        return FakeScalarResult()

    return SimpleNamespace(scalars=scalars)


def _utc_dt(days_ago: int) -> datetime:
    """Return a UTC datetime N days ago at noon."""
    return datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


def _utc_dt_iso(days_ago: int) -> str:
    return _utc_dt(days_ago).isoformat()


def test_json_str_list_parses_array() -> None:
    assert _json_str_list('["300308", "688235"]') == ["300308", "688235"]
    assert _json_str_list("[]") == []
    assert _json_str_list("") == []
    assert _json_str_list("not json") == []


def test_dt_begin_end_round_trip() -> None:
    d = date(2026, 5, 13)
    begin = _dt_begin(d)
    end = _dt_end(d)
    assert begin.hour == 0 and begin.minute == 0
    assert end.hour == 23 and end.minute == 59
    assert begin.date() == d
    assert end.date() == d


# ---------------------------------------------------------------------------
# compute_evidence_momentum_signal
# ---------------------------------------------------------------------------


def test_evidence_momentum_no_events_returns_zero() -> None:
    session = _mock_session([])
    result = compute_evidence_momentum_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=date(2026, 5, 13),
    )
    assert result.value == 0.0
    assert result.confidence == 0.0
    assert result.coverage_status == "available"
    assert result.source == "internal_evidence"
    assert "无证据事件记录" in result.metadata_json.get("explanation", "")


def test_evidence_momentum_positive_momentum() -> None:
    today = date(2026, 5, 13)
    # 4 events in recent 7d, 1 event in prior 7d -> ratio 4.0 -> strong positive
    events = [
        SimpleNamespace(
            affected_security_ids=json.dumps(["300308"]),
            event_time=_utc_dt(1),
            impact_direction="positive",
            confidence=0.9,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["300308"]),
            event_time=_utc_dt(2),
            impact_direction="positive",
            confidence=0.8,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["300308"]),
            event_time=_utc_dt(3),
            impact_direction="neutral",
            confidence=0.7,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["300308"]),
            event_time=_utc_dt(4),
            impact_direction="positive",
            confidence=0.85,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["300308"]),
            event_time=_utc_dt(10),  # prior period
            impact_direction="positive",
            confidence=0.6,
        ),
    ]
    session = _mock_session(events)
    result = compute_evidence_momentum_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=today,
    )
    assert result.value > 50.0
    assert result.coverage_status == "available"
    assert "加速" in result.metadata_json.get("explanation", "")
    assert result.metadata_json.get("direction") == "positive"


def test_evidence_momentum_negative_momentum() -> None:
    today = date(2026, 5, 13)
    # 1 event in recent 7d, 4 in prior 7d -> ratio 0.25 -> negative
    events = [
        SimpleNamespace(
            affected_security_ids=json.dumps(["688235"]),
            event_time=_utc_dt(2),
            impact_direction="negative",
            confidence=0.7,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["688235"]),
            event_time=_utc_dt(10),
            impact_direction="negative",
            confidence=0.6,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["688235"]),
            event_time=_utc_dt(11),
            impact_direction="negative",
            confidence=0.6,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["688235"]),
            event_time=_utc_dt(12),
            impact_direction="positive",
            confidence=0.6,
        ),
        SimpleNamespace(
            affected_security_ids=json.dumps(["688235"]),
            event_time=_utc_dt(13),
            impact_direction="neutral",
            confidence=0.5,
        ),
    ]
    session = _mock_session(events)
    result = compute_evidence_momentum_signal(
        session,
        subject_type="stock",
        subject_id="688235",
        subject_name="样本",
        trade_date=today,
    )
    assert result.value < 50.0
    assert "下降" in result.metadata_json.get("explanation", "")
    assert result.metadata_json.get("direction") == "negative"


def test_evidence_momentum_filters_other_stocks() -> None:
    today = date(2026, 5, 13)
    events = [
        SimpleNamespace(
            affected_security_ids=json.dumps(["999999"]),
            event_time=_utc_dt(1),
            impact_direction="positive",
            confidence=0.9,
        ),
    ]
    session = _mock_session(events)
    result = compute_evidence_momentum_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=today,
    )
    # No events for 300308 -> zero
    assert result.value == 0.0
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# compute_news_sentiment_signal
# ---------------------------------------------------------------------------


def test_news_sentiment_no_articles_returns_zero() -> None:
    session = _mock_session([])
    result = compute_news_sentiment_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=date(2026, 5, 13),
    )
    assert result.value == 0.0
    assert result.confidence == 0.0
    assert result.coverage_status == "available"
    assert "无相关新闻文章" in result.metadata_json.get("explanation", "")


def test_news_sentiment_positive_momentum() -> None:
    today = date(2026, 5, 13)
    articles = [
        SimpleNamespace(
            related_stocks=json.dumps(["000001"]),
            published_at=_utc_dt(1),
            source_confidence=0.9,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000001"]),
            published_at=_utc_dt(2),
            source_confidence=0.8,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000001"]),
            published_at=_utc_dt(3),
            source_confidence=0.7,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000001"]),
            published_at=_utc_dt(10),
            source_confidence=0.6,
        ),
    ]
    session = _mock_session(articles)
    result = compute_news_sentiment_signal(
        session,
        subject_type="stock",
        subject_id="000001",
        subject_name="样本",
        trade_date=today,
    )
    assert result.value > 50.0
    assert "加速" in result.metadata_json.get("explanation", "")


def test_news_sentiment_decelerating() -> None:
    today = date(2026, 5, 13)
    articles = [
        SimpleNamespace(
            related_stocks=json.dumps(["000002"]),
            published_at=_utc_dt(10),
            source_confidence=0.8,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000002"]),
            published_at=_utc_dt(11),
            source_confidence=0.8,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000002"]),
            published_at=_utc_dt(12),
            source_confidence=0.7,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000002"]),
            published_at=_utc_dt(13),
            source_confidence=0.6,
        ),
    ]
    session = _mock_session(articles)
    result = compute_news_sentiment_signal(
        session,
        subject_type="stock",
        subject_id="000002",
        subject_name="样本",
        trade_date=today,
    )
    assert result.value < 50.0
    assert "减弱" in result.metadata_json.get("explanation", "")


def test_news_sentiment_confidence_reflects_source_quality() -> None:
    today = date(2026, 5, 13)
    articles = [
        SimpleNamespace(
            related_stocks=json.dumps(["000003"]),
            published_at=_utc_dt(1),
            source_confidence=1.0,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000003"]),
            published_at=_utc_dt(2),
            source_confidence=0.9,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000003"]),
            published_at=_utc_dt(3),
            source_confidence=0.8,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000003"]),
            published_at=_utc_dt(4),
            source_confidence=0.7,
        ),
        SimpleNamespace(
            related_stocks=json.dumps(["000003"]),
            published_at=_utc_dt(10),
            source_confidence=0.5,
        ),
    ]
    session = _mock_session(articles)
    result = compute_news_sentiment_signal(
        session,
        subject_type="stock",
        subject_id="000003",
        subject_name="样本",
        trade_date=today,
    )
    assert 0.4 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Integration-style: dataclass fields
# ---------------------------------------------------------------------------


def test_alternative_signal_dataclass_defaults() -> None:
    sig = AlternativeSignal(
        signal_name="test_signal",
        subject_type="stock",
        subject_id="T001",
        subject_name="测试",
        value=75.0,
        value_type="score",
        source="internal_evidence",
        observed_at="2026-05-13",
        confidence=0.85,
        freshness="daily",
        coverage_status="available",
    )
    assert sig.signal_name == "test_signal"
    assert sig.value == 75.0
    assert sig.metadata_json == {}  # default empty dict
    assert sig.coverage_status == "available"


# ---------------------------------------------------------------------------
# Additional signal contract tests
# ---------------------------------------------------------------------------


def test_signal_has_source() -> None:
    """Every signal should have a documented source."""
    sig = AlternativeSignal(
        signal_name="evidence_momentum",
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        value=75.0,
        value_type="score",
        source="internal_evidence",
        observed_at="2026-05-13",
        confidence=0.85,
        freshness="daily",
        coverage_status="available",
    )
    assert sig.source is not None
    assert len(sig.source) > 0
    # Source should be a known identifier
    assert sig.source in ("internal_evidence", "news_aggregation", "deterministic_proxy")


def test_signal_has_freshness() -> None:
    """Every signal should indicate freshness."""
    sig = AlternativeSignal(
        signal_name="evidence_momentum",
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        value=75.0,
        value_type="score",
        source="internal_evidence",
        observed_at="2026-05-13",
        confidence=0.85,
        freshness="daily",
        coverage_status="available",
    )
    assert sig.freshness is not None
    assert sig.freshness in ("realtime", "daily", "weekly")


def test_pending_connector_explicit() -> None:
    """Signals with pending_connector status should be explicitly marked."""
    sig = AlternativeSignal(
        signal_name="pending_connector_signal",
        subject_type="stock",
        subject_id="T999",
        subject_name="待接入",
        value=0.0,
        value_type="score",
        source="deterministic_proxy",
        observed_at="2026-05-13",
        confidence=0.0,
        freshness="weekly",
        coverage_status="pending_connector",
    )
    assert sig.coverage_status == "pending_connector"
    # pending_connector is not "available" or "unavailable"
    assert sig.coverage_status != "available"
    assert sig.coverage_status != "unavailable"


def test_no_external_network() -> None:
    """Signal computation should not require external network calls.

    This is a design contract test -- it verifies that the public signal
    computation functions (compute_evidence_momentum_signal,
    compute_news_sentiment_signal) accept a session parameter and do not
    import any HTTP/networking libraries.
    """
    import inspect

    from app.engines.alternative_signals_engine import (
        compute_evidence_momentum_signal as fn1,
        compute_news_sentiment_signal as fn2,
    )

    for fn in (fn1, fn2):
        source = inspect.getsource(fn)
        # Must not contain network calls
        assert "requests." not in source, f"{fn.__name__} should not make HTTP calls"
        assert "urllib" not in source, f"{fn.__name__} should not make HTTP calls"
        assert "httpx" not in source, f"{fn.__name__} should not make HTTP calls"
        assert "aiohttp" not in source, f"{fn.__name__} should not make HTTP calls"
        # Must accept a session parameter (not a connection string or URL)
        sig = inspect.signature(fn)
        assert "session" in sig.parameters, f"{fn.__name__} must accept a session parameter"


def test_signal_value_range() -> None:
    """Signal values should be normalized 0-100."""
    # Test with known data producing a value in range
    today = date(2026, 5, 13)
    session = _mock_session([])

    # No events -> value should be 0 (within range)
    result = compute_evidence_momentum_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=today,
    )
    assert 0.0 <= result.value <= 100.0

    # News signal with no articles
    result2 = compute_news_sentiment_signal(
        session,
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        trade_date=today,
    )
    assert 0.0 <= result2.value <= 100.0
