"""Shared test fixtures for Alpha Radar backend tests."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create a fresh in-memory SQLite database for each test.

    All tables defined on ``Base.metadata`` are created before the test
    and torn down implicitly when the engine is garbage-collected.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session
