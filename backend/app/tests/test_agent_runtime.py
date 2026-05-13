from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.orchestrator import AgentOrchestrator
from app.agent.runtime import MockRuntimeAdapter
from app.agent.schemas import AgentRunRequest, AgentTaskType
from app.db.models import Base
from app.db.session import get_session
from app.main import app


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime_test.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    _seed_run_data(SessionLocal)

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


def _seed_run_data(SessionLocal: sessionmaker) -> None:
    """Create a completed run with an artifact so follow-up can be tested."""
    from app.agent.events import publish_event

    with SessionLocal() as session:
        from app.agent.tools.registry import registry
        from app.db.models import AgentArtifact, AgentFollowup, AgentRun, AgentToolCall

        # Create a completed run with artifact
        run = AgentRun(user_prompt="test health agent run", task_type="auto", status="success")
        session.add(run)
        session.flush()

        artifact = AgentArtifact(
            run_id=run.id,
            artifact_type="research_report",
            title="测试报告",
            content_md="# 测试报告\n\n这是测试内容。",
            content_json='{"summary": "测试"}',
            evidence_refs_json='[]',
        )
        session.add(artifact)

        # Add a tool call so context building works
        tc = AgentToolCall(
            run_id=run.id,
            tool_name="test_tool",
            input_json="{}",
            output_json='{"result": "ok"}',
            latency_ms=10,
            success=True,
        )
        session.add(tc)

        session.commit()

        # Publish completed event so follow-up streaming tests pass
        publish_event(session, run.id, "followup_completed", {"mode": "auto"})


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_status(tmp_path) -> None:
    """GET /api/agent/runtime/health returns HTTP 200 with runtime info."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runtime/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "runtime_provider" in data
        assert "llm_configured" in data
        assert "hermes_configured" in data
        assert "streaming_supported" in data
        assert "followup_llm_enabled" in data
        assert "fallback_enabled" in data
        assert "warnings" in data


def test_health_no_api_key_shows_llm_disabled(tmp_path) -> None:
    """Without OPENAI_API_KEY, llm_configured and followup_llm_enabled are False."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runtime/health")
        data = resp.json()

        from app.config import settings
        expected_llm = bool(settings.openai_api_key)
        expected_hermes = bool(settings.hermes_endpoint)

        assert data["llm_configured"] is expected_llm
        assert data["hermes_configured"] is expected_hermes
        assert data["followup_llm_enabled"] is expected_llm

        if not expected_llm and not expected_hermes:
            assert data["runtime_provider"] == "mock"
            assert data["streaming_supported"] is False
        elif expected_llm:
            assert data["runtime_provider"] == "llm"
            assert data["streaming_supported"] is True


def test_health_does_not_leak_key(tmp_path) -> None:
    """Health endpoint never returns the API key or hermes endpoint value."""
    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runtime/health")
        body = resp.text

        # Check no key values appear in the response body
        assert "sk-" not in body, "API key prefix leaked in health response"
        assert "openai_api_key" not in body, "openai_api_key field name leaked"
        assert "hermes_endpoint" not in body, "hermes_endpoint field name leaked"


def test_health_warnings_when_no_llm(tmp_path) -> None:
    """When neither LLM nor Hermes is configured, warnings list is non-empty."""
    from app.config import settings
    if settings.openai_api_key or settings.hermes_endpoint:
        pytest.skip("This test requires no LLM/Hermes config (CI env)")

    with _client(tmp_path) as client:
        resp = client.get("/api/agent/runtime/health")
        data = resp.json()
        assert len(data["warnings"]) > 0
        mock_warning = any("mock" in w.lower() for w in data["warnings"])
        assert mock_warning, "Expected a warning about mock runtime when no LLM configured"


# ---------------------------------------------------------------------------
# Follow-up fallback warning tests
# ---------------------------------------------------------------------------


def test_followup_fallback_warning_when_no_llm(tmp_path) -> None:
    """Follow-up response includes fallback warning when template path is used."""
    from app.config import settings

    if settings.openai_api_key:
        pytest.skip("LLM follow-up would use real LLM; skipping in test env")

    with _client(tmp_path) as client:
        # Create a run & execute
        resp = client.post("/api/agent/runs", json={"user_prompt": "test health"})
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(f"sqlite:///{tmp_path / 'runtime_test.sqlite'}", connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(bind=engine, future=True)
        with SessionLocal() as session:
            def session_factory():
                return SessionLocal()
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="test health"))

        # Followup — should use template fallback
        followup_resp = client.post(
            f"/api/agent/runs/{run_id}/followups",
            json={"message": "解释一下这个结果"},
        )
        assert followup_resp.status_code == 201
        data = followup_resp.json()

        # Verify warnings include the template fallback message
        assert "warnings" in data
        warnings = data["warnings"]
        fallback_found = any(
            "LLM 不可用" in w or "模板回答" in w or "回退" in w or
            "No LLM" in w or "fallback" in w or "template" in w
            for w in warnings
        )
        assert fallback_found, (
            f"Expected a fallback/template warning in follow-up response, "
            f"got warnings={warnings}"
        )
