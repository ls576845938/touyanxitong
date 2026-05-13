from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class LLMAuthMiddleware(BaseHTTPMiddleware):
    """Extract LLM API key and provider from request headers.

    Reads ``X-LLM-API-Key`` and ``X-LLM-Provider`` from incoming request
    headers and stores them on ``request.state`` so that downstream
    dependencies (e.g. ``get_llm_config``) can access them.

    When a header is absent the corresponding ``request.state`` attribute
    is set to ``None``, signalling the caller to fall back to server-side
    defaults.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.llm_api_key = request.headers.get("X-LLM-API-Key")
        request.state.llm_provider = request.headers.get("X-LLM-Provider")
        response = await call_next(request)
        return response
