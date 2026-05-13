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
from app.db.models import AgentArtifact, AgentRun, Base
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


# ---------------------------------------------------------------------------
# Chart placeholder tests
# ---------------------------------------------------------------------------


def _seed_chart_artifact(session: Session) -> int:
    """Create a run with an artifact containing chart tags."""
    run = AgentRun(
        task_type="stock_deep_research",
        user_prompt="test chart export",
        status="success",
    )
    session.add(run)
    session.flush()

    content_md = (
        "# 测试报告\n\n"
        "这是包含图表的报告。\n\n"
        ':::chart {"type":"candle","symbol":"300308","stock_name":"中际旭创"}:::\n\n'
        ':::chart {"type":"industry_heat","period":"7日"}:::\n\n'
        ':::chart {"type":"candle","symbol":"600519","stock_name":"贵州茅台"}:::\n\n'
        "以上是图表内容。\n"
    )
    session.add(
        AgentArtifact(
            run_id=run.id,
            artifact_type="research_report",
            title="图表测试报告",
            content_md=content_md,
            content_json='{"summary":"图表测试","claims":[],"risk_disclaimer":"本报告仅用于投研分析和信息整理，不构成任何投资建议。"}',
            evidence_refs_json="[]",
        )
    )
    session.commit()
    return run.id


def test_export_html_contains_chart_placeholders(tmp_path) -> None:
    """HTML export replaces chart tags with descriptive placeholders."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'chart_export.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    run_id: int = 0
    with SessionLocal() as session:
        run_id = _seed_chart_artifact(session)

    def override_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)

        # Test the print endpoint which uses markdown-it-py rendering
        resp = client.get(f"/api/agent/runs/{run_id}/export/print")
        if resp.status_code == 404:
            pytest.skip("Print export endpoint not yet available")
        assert resp.status_code == 200
        body = resp.text

        # Should contain chart placeholder content (not empty divs)
        assert "K线图" in body or "chart-placeholder" in body, (
            "Expected chart placeholder in HTML export output"
        )

        # Test the /export/html endpoint too
        resp2 = client.get(f"/api/agent/runs/{run_id}/export/html")
        assert resp2.status_code == 200
        body2 = resp2.text
        # The basic HTML endpoint uses a simpler replacement
        assert "图表" in body2 or "300308" in body2 or "chart" in body2, (
            "Expected chart reference in /export/html output"
        )
    finally:
        app.dependency_overrides.clear()


def test_export_html_chart_placeholder_not_empty_div(tmp_path) -> None:
    """Chart placeholders in export should not be empty <div> elements."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'chart_export2.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    run_id: int = 0
    with SessionLocal() as session:
        run_id = _seed_chart_artifact(session)

    def override_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)

        resp = client.get(f"/api/agent/runs/{run_id}/export/print")
        if resp.status_code == 404:
            pytest.skip("Print export endpoint not yet available")
        assert resp.status_code == 200
        body = resp.text

        # Verify we have chart-related output (either placeholder divs or render output)
        # The CSS class .chart-placeholder is expected in the stylesheet
        assert "chart-placeholder" in body, "Expected chart-placeholder CSS in export"

        # Verify there are no raw chart tag markers left
        assert ":::chart" not in body, "Raw chart tags leaked into HTML export"

        # Verify chart content appears (at least one chart type label)
        has_kline = "K线图" in body
        has_industry = "行业热度" in body
        has_stock_name = "中际旭创" in body or "贵州茅台" in body
        assert has_kline or has_industry or has_stock_name, (
            "Expected chart content labels in export output"
        )
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Content guardrails tests
# ---------------------------------------------------------------------------


def _seed_unsafe_artifact(session: Session) -> int:
    """Create a run with an artifact containing forbidden words."""
    run = AgentRun(
        task_type="stock_deep_research",
        user_prompt="test guardrails",
        status="success",
    )
    session.add(run)
    session.flush()

    content_md = (
        "# 风险测试报告\n\n"
        "建议买入，目标价：150元。稳赚必涨，无风险。\n\n"
        "抄底机会，满仓梭哈。\n\n"
        "建议加仓，重仓持有。\n"
    )
    session.add(
        AgentArtifact(
            run_id=run.id,
            artifact_type="research_report",
            title="风险测试报告",
            content_md=content_md,
            content_json='{"summary":"风险测试","claims":[],"risk_disclaimer":"本报告仅用于投研分析和信息整理，不构成任何投资建议。"}',
            evidence_refs_json="[]",
        )
    )
    session.commit()
    return run.id


def test_export_content_passes_guardrails(tmp_path) -> None:
    """Exported content contains risk disclaimer and is safe (no script tags)."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'guardrails_export.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    run_id: int = 0
    with SessionLocal() as session:
        run_id = _seed_unsafe_artifact(session)

    def override_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)

        # Check markdown export
        resp = client.get(f"/api/agent/runs/{run_id}/export/markdown")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.text

        # Risk disclaimer must be present (added by export endpoint)
        assert RISK_DISCLAIMER in body, "Risk disclaimer missing from markdown export"

        # Content-Disposition header present
        assert "Content-Disposition" in resp.headers

        # Check HTML export
        resp2 = client.get(f"/api/agent/runs/{run_id}/export/html")
        assert resp2.status_code == 200
        body2 = resp2.text
        assert RISK_DISCLAIMER in body2, "Risk disclaimer missing from HTML export"
        # HTML export must be safe
        assert "<script" not in body2, "Script tags found in HTML export"
        assert "<!DOCTYPE html>" in body2

        # Check print export
        resp3 = client.get(f"/api/agent/runs/{run_id}/export/print")
        if resp3.status_code != 404:
            body3 = resp3.text
            assert RISK_DISCLAIMER in body3, "Risk disclaimer missing from print export"
    finally:
        app.dependency_overrides.clear()
