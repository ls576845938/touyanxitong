"""Tests for the agent runtime health endpoint vision-related fields.

Verifies that ``GET /api/agent/runtime/health`` returns the correct vision
fields, does not leak the API key, and includes a warning when vision is
unavailable.

The health endpoint does NOT depend on the database, so these tests use
``TestClient(app)`` directly without dependency overrides.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestRuntimeHealthVision:
    """Test vision-related fields in the runtime health endpoint."""

    def test_health_endpoint_returns_vision_fields(self) -> None:
        """runtime/health response includes vision_configured, supports_image_input."""
        client = TestClient(app)
        resp = client.get("/api/agent/runtime/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "vision_configured" in data
        assert "supports_image_input" in data
        assert "vision_provider" in data
        assert "image_input_max_mb" in data
        assert isinstance(data["vision_configured"], bool)
        assert isinstance(data["supports_image_input"], bool)

    def test_vision_unconfigured_without_api_key(self) -> None:
        """When OPENAI_API_KEY is empty, vision_configured=false."""
        from app.config import settings

        expected_vision = bool(settings.openai_api_key)

        client = TestClient(app)
        resp = client.get("/api/agent/runtime/health")
        data = resp.json()
        assert data["vision_configured"] is expected_vision
        assert data["supports_image_input"] is expected_vision
        if not expected_vision:
            assert data["vision_provider"] is None

    def test_no_api_key_in_response(self) -> None:
        """Health response must not contain API key."""
        client = TestClient(app)
        resp = client.get("/api/agent/runtime/health")
        body = resp.text

        assert "sk-" not in body, "API key prefix leaked in health response"
        assert "openai_api_key" not in body, "openai_api_key field name leaked"
        assert "OPENAI_API_KEY" not in body, "OPENAI_API_KEY env var leaked"

    def test_warning_when_vision_unavailable(self) -> None:
        """Warning present when vision is not configured."""
        from app.config import settings

        if settings.openai_api_key:
            pytest.skip("This test requires no OPENAI_API_KEY (CI env)")

        client = TestClient(app)
        resp = client.get("/api/agent/runtime/health")
        data = resp.json()
        warnings = data.get("warnings", [])
        vision_warning = any(
            "未配置多模态" in w or "vision" in w.lower() or "图片识别" in w
            for w in warnings
        )
        assert vision_warning, (
            f"Expected a vision-related warning in health response, "
            f"got warnings={warnings}"
        )
