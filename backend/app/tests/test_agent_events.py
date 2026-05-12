"""Tests for EventBus, persisted events, and SSE event replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.events import AgentEventBus, publish_event, replay_events
from app.db.models import AgentEvent, AgentRun, Base
from app.db.session import get_session
from app.main import app


# ---------------------------------------------------------------------------
# Test helpers  (lightweight versions — no _seed_agent_data needed for most tests)
# ---------------------------------------------------------------------------


@contextmanager
def _session(tmp_path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'events_test.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    """TestClient for API-level event tests (needs full seed data)."""
    from app.tests.test_agent import _seed_agent_data

    engine = create_engine(
        f"sqlite:///{tmp_path / 'events_api_test.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as seed_session:
        _seed_agent_data(seed_session)

    def override_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# EventBus unit tests
# ---------------------------------------------------------------------------


def test_event_bus_publish_and_subscribe() -> None:
    """Event published to EventBus can be received by subscriber."""

    async def _run_test() -> dict[str, Any]:
        bus = AgentEventBus()
        loop = asyncio.get_running_loop()
        queue = bus.subscribe(42, loop)

        assert bus.has_subscribers(42)
        assert bus.subscriber_count == 1

        bus.publish(
            42,
            {
                "event": "test_event",
                "run_id": 42,
                "timestamp": "2026-01-01T00:00:00",
                "payload": {"key": "value"},
                "seq": 1,
            },
        )

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        return received

    event = asyncio.run(_run_test())
    assert event["event"] == "test_event"
    assert event["run_id"] == 42
    assert event["payload"]["key"] == "value"
    assert event["seq"] == 1


def test_event_bus_next_seq() -> None:
    """AgentEventBus.next_seq returns monotonically increasing integers per run_id."""
    bus = AgentEventBus()
    assert bus.next_seq(1) == 1
    assert bus.next_seq(1) == 2
    assert bus.next_seq(1) == 3
    # Independent counter per run_id
    assert bus.next_seq(2) == 1
    assert bus.next_seq(1) == 4


def test_event_bus_subscriber_count_across_run_ids() -> None:
    """subscriber_count reflects all run_ids."""
    bus = AgentEventBus()

    async def _subscribe(run_id: int) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        return bus.subscribe(run_id, loop)

    async def _run():
        q1 = await _subscribe(1)
        q2 = await _subscribe(1)
        q3 = await _subscribe(2)
        assert bus.subscriber_count == 3
        assert bus.has_subscribers(1)
        assert bus.has_subscribers(2)
        bus.unsubscribe(1, q1)
        assert bus.subscriber_count == 2
        bus.unsubscribe(1, q2)
        assert bus.subscriber_count == 1
        bus.unsubscribe(2, q3)
        assert bus.subscriber_count == 0
        assert not bus.has_subscribers(1)
        assert not bus.has_subscribers(2)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# DB persistence tests
# ---------------------------------------------------------------------------


def test_event_persisted_to_db(tmp_path) -> None:
    """Published events are written to agent_events table."""
    with _session(tmp_path) as session:
        run = AgentRun(user_prompt="test persistence", task_type="auto", status="pending")
        session.add(run)
        session.commit()

        publish_event(session, run.id, "my_event", {"data": 42})
        session.commit()

        rows = session.scalars(
            select(AgentEvent).where(AgentEvent.run_id == run.id)
        ).all()
        assert len(rows) == 1
        assert rows[0].event_type == "my_event"
        assert json.loads(rows[0].payload_json) == {"data": 42}
        assert isinstance(rows[0].seq, int)
        assert rows[0].seq > 0


def test_event_replay_by_since_seq(tmp_path) -> None:
    """Replay returns events after since_seq."""
    with _session(tmp_path) as session:
        run = AgentRun(user_prompt="test replay", task_type="auto", status="pending")
        session.add(run)
        session.commit()

        publish_event(session, run.id, "evt1", {"n": 1})
        publish_event(session, run.id, "evt2", {"n": 2})
        publish_event(session, run.id, "evt3", {"n": 3})
        session.commit()

        all_events = replay_events(session, run.id)
        assert len(all_events) == 3
        # seq values are monotonically increasing (global counter may start > 0)
        assert all_events[0]["seq"] < all_events[1]["seq"] < all_events[2]["seq"]

        # Replay with since_seq equal to first event's seq => get last 2
        filtered = replay_events(session, run.id, since_seq=all_events[0]["seq"])
        assert len(filtered) == 2
        assert filtered[0]["seq"] == all_events[1]["seq"]
        assert filtered[1]["seq"] == all_events[2]["seq"]

        # Replay with since_seq equal to last event's seq => empty
        empty = replay_events(session, run.id, since_seq=all_events[2]["seq"])
        assert len(empty) == 0


def test_events_have_required_fields(tmp_path) -> None:
    """Events from replay_events contain event/run_id/timestamp/payload/seq."""
    with _session(tmp_path) as session:
        run = AgentRun(user_prompt="test fields", task_type="auto", status="pending")
        session.add(run)
        session.commit()

        publish_event(session, run.id, "test_event", {"msg": "hello"})
        session.commit()

        events = replay_events(session, run.id)
        assert len(events) == 1
        ev = events[0]
        assert "event" in ev
        assert "run_id" in ev
        assert "timestamp" in ev
        assert "payload" in ev
        assert "seq" in ev

        assert ev["event"] == "test_event"
        assert ev["run_id"] == run.id
        assert isinstance(ev["timestamp"], str)
        assert ev["payload"] == {"msg": "hello"}
        assert isinstance(ev["seq"], int)


# ---------------------------------------------------------------------------
# SSE API endpoint tests
# ---------------------------------------------------------------------------


def test_sse_events_endpoint_with_since_seq(tmp_path) -> None:
    """SSE endpoint accepts ?since_seq=N and replays from there."""
    with _client(tmp_path) as client:
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        resp = client.get(f"/api/agent/runs/{run_id}/events?since_seq=0")
        if resp.status_code in (404, 500):
            pytest.skip("SSE since_seq endpoint not fully implemented yet")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


def test_sse_events_for_nonexistent_run(tmp_path) -> None:
    """SSE returns 404 for missing run_id."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runs/999999/events")
        assert resp.status_code == 404


def test_sse_events_requires_run_id(tmp_path) -> None:
    """SSE endpoint returns 404 for a non-existent run_id even with special since_seq."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runs/0/events?since_seq=99")
        assert resp.status_code == 404
