"""Tests for report export endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.guardrails import RISK_DISCLAIMER
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import AgentRunRequest
from app.db.models import Base
from app.db.session import get_session
from app.main import app


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    """TestClient with isolated SQLite and seeded test data."""
    from app.tests.test_agent import _seed_agent_data

    engine = create_engine(
        f"sqlite:///{tmp_path / 'export_test.sqlite'}",
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


@contextmanager
def _session(tmp_path) -> Iterator[Session]:
    """Isolated DB session for manual orchestration."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'export_test.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        from app.tests.test_agent import _seed_agent_data
        _seed_agent_data(session)
        yield session


def _execute_run(tmp_path, client, prompt: str = "帮我分析中际旭创是不是还在主升趋势") -> int:
    """Create and execute a run, return run_id."""
    response = client.post("/api/agent/runs", json={"user_prompt": prompt})
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    with _session(tmp_path) as session:
        orchestrator = AgentOrchestrator(
            session, session_factory=lambda: _session(tmp_path)
        )
        orchestrator.execute_async(run_id, AgentRunRequest(user_prompt=prompt))

    return run_id


# ---------------------------------------------------------------------------
# Markdown export tests
# ---------------------------------------------------------------------------


def test_export_markdown_endpoint(tmp_path) -> None:
    """GET /export/markdown returns content with Content-Disposition."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        resp = client.get(f"/api/agent/runs/{run_id}/export/markdown")
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert resp.headers["content-type"].startswith("text/markdown")


def test_export_markdown_nonexistent_run(tmp_path) -> None:
    """Export for missing run returns 404."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runs/999999/export/markdown")
        assert resp.status_code == 404


def test_export_markdown_no_artifact(tmp_path) -> None:
    """Export for run with no artifact returns 404."""
    with _client(tmp_path) as client:
        resp = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创"})
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        # Do NOT execute the run — no artifact will exist

        resp = client.get(f"/api/agent/runs/{run_id}/export/markdown")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HTML export tests
# ---------------------------------------------------------------------------


def test_export_html_endpoint(tmp_path) -> None:
    """GET /export/html returns HTML content."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        resp = client.get(f"/api/agent/runs/{run_id}/export/html")
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert resp.headers["content-type"].startswith("text/html")

        body = resp.text
        assert "<!DOCTYPE html>" in body
        assert "</html>" in body


def test_export_html_nonexistent_run(tmp_path) -> None:
    """HTML export for missing run returns 404."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runs/999999/export/html")
        assert resp.status_code == 404


def test_export_html_no_script_tags(tmp_path) -> None:
    """HTML export is safe: no <script> tags, no event handlers."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        resp = client.get(f"/api/agent/runs/{run_id}/export/html")
        assert resp.status_code == 200
        body = resp.text
        assert "<script" not in body
        assert "onload=" not in body
        assert "onerror=" not in body
        assert "onclick=" not in body


# ---------------------------------------------------------------------------
# Content verification tests
# ---------------------------------------------------------------------------


def test_export_content_has_disclaimer(tmp_path) -> None:
    """Exported content contains risk disclaimer."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        resp = client.get(f"/api/agent/runs/{run_id}/export/markdown")
        assert resp.status_code == 200
        assert RISK_DISCLAIMER in resp.text


def test_export_html_has_disclaimer(tmp_path) -> None:
    """HTML export also contains risk disclaimer."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        resp = client.get(f"/api/agent/runs/{run_id}/export/html")
        assert resp.status_code == 200
        assert RISK_DISCLAIMER in resp.text


def test_export_filename_in_content_disposition(tmp_path) -> None:
    """Content-Disposition header includes a meaningful filename."""
    with _client(tmp_path) as client:
        run_id = _execute_run(tmp_path, client)

        for fmt in ("markdown", "html"):
            resp = client.get(f"/api/agent/runs/{run_id}/export/{fmt}")
            assert resp.status_code == 200
            disposition = resp.headers["Content-Disposition"]
            assert "filename=" in disposition
            assert f"alpha-radar-report-{run_id}" in disposition
