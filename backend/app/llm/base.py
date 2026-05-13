from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def generate_research_report(self, system_prompt: str, user_message: str) -> dict:
        ...

    @abstractmethod
    def generate_research_report_stream(
        self, system_prompt: str, user_message: str, on_token: Callable[[str], None]
    ) -> dict:
        ...

    @abstractmethod
    def generate_followup_answer(
        self,
        system_prompt: str,
        user_message: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        ...

    @classmethod
    @abstractmethod
    def supports_vision(cls) -> bool:
        ...
