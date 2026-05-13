from __future__ import annotations

from importlib import import_module

from app.llm.base import BaseLLMProvider

PROVIDERS: dict[str, str] = {
    "openai": "app.llm.openai_provider.OpenAIProvider",
    "gemini": "app.llm.gemini_provider.GeminiProvider",
    "deepseek": "app.llm.deepseek_provider.DeepSeekProvider",
}


def create_provider(provider_name: str, api_key: str, **kwargs: str) -> BaseLLMProvider:
    """Create an LLM provider by name.

    Args:
        provider_name: One of ``"openai"``, ``"gemini"``, ``"deepseek"``.
        api_key: API key for the provider.
        **kwargs: Additional keyword arguments forwarded to the provider
            constructor (e.g. ``base_url``).

    Returns:
        An instantiated :class:`BaseLLMProvider` subclass.

    Raises:
        ValueError: If *provider_name* is not recognised.
    """
    dotted_path = PROVIDERS.get(provider_name)
    if dotted_path is None:
        raise ValueError(
            f"Unknown LLM provider {provider_name!r}. "
            f"Available: {', '.join(sorted(PROVIDERS))}"
        )

    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    provider_cls = getattr(module, class_name)
    return provider_cls(api_key, **kwargs)
