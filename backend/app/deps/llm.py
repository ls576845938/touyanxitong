from __future__ import annotations

from fastapi import Request


def get_llm_config(request: Request) -> dict:
    """Return ``{api_key, provider}`` preferring user headers over server defaults.

    Priority:
    1. ``X-LLM-API-Key`` header → user-supplied key
    2. Server-side env-var key matching the provider
    3. ``openai_api_key`` as the ultimate fallback

    The provider defaults to ``X-LLM-Provider`` header and falls back to
    ``settings.llm_provider`` (itself defaulting to ``"openai"``).
    """
    from app.config import settings

    provider = getattr(request.state, "llm_provider", None) or settings.llm_provider
    api_key = getattr(request.state, "llm_api_key", None)

    # Fall back to server-side key based on provider
    if not api_key:
        if provider == "gemini":
            api_key = settings.gemini_api_key
        elif provider == "deepseek":
            api_key = settings.deepseek_api_key
        else:
            api_key = settings.openai_api_key

    return {"api_key": api_key, "provider": provider}
