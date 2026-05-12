from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

EVENT_RUN_CREATED = "run_created"
EVENT_RUN_STARTED = "run_started"
EVENT_STEP_STARTED = "step_started"
EVENT_STEP_COMPLETED = "step_completed"
EVENT_TOOL_CALL_STARTED = "tool_call_started"
EVENT_TOOL_CALL_COMPLETED = "tool_call_completed"
EVENT_TOKEN_DELTA = "token_delta"
EVENT_ARTIFACT_CREATED = "artifact_created"
EVENT_FOLLOWUP_STARTED = "followup_started"
EVENT_FOLLOWUP_TOKEN_DELTA = "followup_token_delta"
EVENT_FOLLOWUP_COMPLETED = "followup_completed"
EVENT_RUN_COMPLETED = "run_completed"
EVENT_RUN_FAILED = "run_failed"
EVENT_HEARTBEAT = "heartbeat"

TERMINAL_EVENTS = {EVENT_RUN_COMPLETED, EVENT_RUN_FAILED}


# ---------------------------------------------------------------------------
# In-memory subscription
# ---------------------------------------------------------------------------

@dataclass
class _Subscription:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


class AgentEventBus:
    """Lightweight in-process EventBus using per-run_id asyncio.Queue subscribers.

    Thread-safe: publish() can be called from any thread (e.g. the background
    orchestrator thread) and will dispatch events to the asyncio event loop
    that owns each subscriber.
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, list[_Subscription]] = defaultdict(list)
        self._seq_counters: dict[int, int] = defaultdict(int)
        self._lock = Lock()

    # -- thread-safe sequence counter ---------------------------------------

    def next_seq(self, run_id: int) -> int:
        """Return the next monotonically-increasing sequence number for *run_id*."""
        with self._lock:
            self._seq_counters[run_id] += 1
            return self._seq_counters[run_id]

    # -- subscribe / unsubscribe --------------------------------------------

    def subscribe(self, run_id: int, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        """Register a new subscriber *queue* for *run_id*.

        The caller must eventually call ``unsubscribe()`` when it no longer
        needs events (e.g. on client disconnect).
        """
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[run_id].append(_Subscription(queue=queue, loop=loop))
        return queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue) -> None:
        """Remove a previously registered subscriber *queue* for *run_id*."""
        with self._lock:
            subs = self._subscribers.get(run_id, [])
            self._subscribers[run_id] = [s for s in subs if s.queue is not queue]
            if not self._subscribers[run_id]:
                self._subscribers.pop(run_id, None)
                self._seq_counters.pop(run_id, None)

    # -- publish ------------------------------------------------------------

    def publish(self, run_id: int, event: dict[str, Any]) -> None:
        """Deliver an event dict to every subscriber of *run_id*.

        Safe to call from any thread.  If there are no subscribers this is a
        no-op (the event is still expected to have been persisted to the DB by
        the caller).
        """
        with self._lock:
            subs = list(self._subscribers.get(run_id, []))
        for sub in subs:
            try:
                asyncio.run_coroutine_threadsafe(sub.queue.put(event), sub.loop)
            except RuntimeError:
                # Event loop is not running or is closed -- skip this subscriber
                pass
            except Exception:
                logger.warning(
                    "Failed to enqueue event for run %s (type=%s)",
                    run_id,
                    event.get("event"),
                    exc_info=True,
                )

    # -- introspection ------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(subs) for subs in self._subscribers.values())

    def has_subscribers(self, run_id: int) -> bool:
        with self._lock:
            return bool(self._subscribers.get(run_id))


# Singleton bus instance
bus = AgentEventBus()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def publish_event(
    session: Session,
    run_id: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Persist an event to ``agent_events`` and push to in-memory subscribers.

    *session* is the orchestrator's active DB session (events are flushed but
    **not** committed -- the caller owns the transaction).

    This function catches and logs all exceptions so that **event publishing
    never crashes a run**.
    """
    try:
        seq = bus.next_seq(run_id)
        now = datetime.now(timezone.utc)
        event = AgentEvent(
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            created_at=now,
        )
        session.add(event)
        session.flush()

        bus.publish(
            run_id,
            {
                "event": event_type,
                "run_id": run_id,
                "timestamp": now.isoformat(),
                "payload": payload,
                "seq": seq,
            },
        )
    except Exception:
        logger.exception(
            "publish_event failed (run_id=%s, type=%s)",
            run_id,
            event_type,
        )


def subscribe(run_id: int) -> tuple[asyncio.Queue, asyncio.AbstractEventLoop]:
    """Subscribe to live events for *run_id*.

    Returns ``(queue, loop)``.  The caller **must** call ``unsubscribe()``
    when done (e.g. on client disconnect) to avoid a memory leak.
    """
    loop = asyncio.get_running_loop()
    queue = bus.subscribe(run_id, loop)
    return queue, loop


def unsubscribe(run_id: int, queue: asyncio.Queue) -> None:
    """Remove a subscriber queue for *run_id*."""
    bus.unsubscribe(run_id, queue)


def replay_events(
    session: Session,
    run_id: int,
    since_seq: int = 0,
) -> list[dict[str, Any]]:
    """Query persisted events for *run_id* ordered by sequence number.

    Returns events whose ``seq > since_seq``.  This is the same shape as what
    ``subscribe()`` delivers so callers can handle both paths identically.
    """
    rows = (
        session.execute(
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id, AgentEvent.seq > since_seq)
            .order_by(AgentEvent.seq)
        )
        .scalars()
        .all()
    )
    return [
        {
            "event": row.event_type,
            "run_id": row.run_id,
            "timestamp": row.created_at.isoformat(),
            "payload": json.loads(row.payload_json) if row.payload_json else {},
            "seq": row.seq,
        }
        for row in rows
    ]
