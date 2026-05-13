from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from loguru import logger

from app.llm.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """Provider calling the DeepSeek API (OpenAI-compatible)."""

    provider_name = "deepseek"

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com") -> None:
        self.api_key = api_key
        self.base_url = base_url

    def generate_research_report(self, system_prompt: str, user_message: str) -> dict:
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as exc:
            logger.error(f"DeepSeek call failed: {exc}")
            raise

    async def generate_research_report_stream(
        self, system_prompt: str, user_message: str, on_token: Callable[[str], None]
    ) -> dict:
        """Streaming version using httpx async with stream=True."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "stream": True,
                        "response_format": {"type": "json_object"},
                    },
                ) as response:
                    response.raise_for_status()
                    content = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta:
                                    content += delta
                                    on_token(delta)
                            except json.JSONDecodeError:
                                continue
                    return json.loads(content)
        except Exception as exc:
            logger.error(f"DeepSeek streaming call failed: {exc}")
            raise

    def generate_followup_answer(
        self,
        system_prompt: str,
        user_message: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Generate a follow-up answer — free-text (not JSON), optional token streaming."""
        try:
            if on_token is not None:
                with httpx.Client(timeout=60.0) as client:
                    with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message},
                            ],
                            "stream": True,
                        },
                    ) as response:
                        response.raise_for_status()
                        full_content: list[str] = []
                        for line in response.iter_lines():
                            if not line:
                                continue
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_content.append(delta)
                                    on_token(delta)
                            except json.JSONDecodeError:
                                continue
                        return "".join(full_content)
            else:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message},
                            ],
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error(f"DeepSeek follow-up call failed: {exc}")
            raise

    @classmethod
    def supports_vision(cls) -> bool:
        return False
