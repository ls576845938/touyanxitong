from __future__ import annotations

import json
from collections.abc import Callable

from loguru import logger

from app.llm.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Provider using Google Gemini models via the google-generativeai SDK."""

    provider_name = "gemini"

    def __init__(self, api_key: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.model_name = "gemini-2.5-flash"

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _build_model(self, system_prompt: str, *, json_mode: bool = False):
        import google.generativeai as genai

        kwargs: dict = {
            "model_name": self.model_name,
            "system_instruction": system_prompt,
        }
        if json_mode:
            kwargs["generation_config"] = {"response_mime_type": "application/json"}
        return genai.GenerativeModel(**kwargs)

    # ------------------------------------------------------------------
    # public interface
    # ------------------------------------------------------------------
    def generate_research_report(self, system_prompt: str, user_message: str) -> dict:
        """Generate a structured research report as JSON."""
        try:
            model = self._build_model(system_prompt, json_mode=True)
            response = model.generate_content(user_message)
            return json.loads(response.text)
        except Exception as exc:
            logger.error(f"Gemini research report failed: {exc}")
            raise

    async def generate_research_report_stream(
        self, system_prompt: str, user_message: str, on_token: Callable[[str], None]
    ) -> dict:
        """Stream a structured research report, collecting JSON at the end."""
        try:
            model = self._build_model(system_prompt, json_mode=True)
            response = await model.generate_content_async(user_message, stream=True)
            full_text = ""
            async for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    on_token(chunk.text)
            return json.loads(full_text)
        except Exception as exc:
            logger.error(f"Gemini streaming research report failed: {exc}")
            raise

    def generate_followup_answer(
        self,
        system_prompt: str,
        user_message: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Generate a free-text follow-up answer (not JSON)."""
        try:
            model = self._build_model(system_prompt, json_mode=False)
            if on_token is not None:
                response = model.generate_content(user_message, stream=True)
                full_text = ""
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text
                        on_token(chunk.text)
                return full_text
            else:
                response = model.generate_content(user_message)
                return response.text
        except Exception as exc:
            logger.error(f"Gemini follow-up answer failed: {exc}")
            raise

    @classmethod
    def supports_vision(cls) -> bool:
        return True
