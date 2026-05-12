from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.agent.runtime.base import AgentRuntimeResult, RuntimeAdapter
from app.config import settings
from app.llm.prompts import RESEARCH_REPORT_PROMPT
from app.llm.provider import OpenAIProvider


class RealRuntimeAdapter(RuntimeAdapter):
    provider_name = "llm"

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        if not settings.openai_api_key:
             from app.agent.runtime.mock_adapter import MockRuntimeAdapter
             return MockRuntimeAdapter().run(prompt, context, tools, skill_template)

        tool_results_summary = self._summarize_tool_results(context.get("tool_results", {}))
        
        system_prompt = RESEARCH_REPORT_PROMPT
        user_message = (
            f"用户问题: {prompt}\n\n"
            f"工具数据摘要:\n{tool_results_summary}\n\n"
            f"报告模板/Skill:\n{skill_template}\n\n"
            "请生成报告。ContentJSON 部分必须严格符合 JSON 格式，包含 claims (list) 和 evidence_refs (list)。"
        )

        try:
            provider = OpenAIProvider(api_key=settings.openai_api_key)
            data = provider.generate_research_report(system_prompt, user_message)
            
            return AgentRuntimeResult(
                title=str(data.get("title") or "AI 投研报告"),
                summary=str(data.get("summary") or "已生成深度投研分析。"),
                content_md=str(data.get("content_markdown") or data.get("content_md") or ""),
                content_json=data.get("content_json") or {},
                evidence_refs=data.get("evidence_refs") or data.get("content_json", {}).get("evidence_refs") or [],
                warnings=[],
            )
        except Exception as exc:
            from app.agent.runtime.mock_adapter import MockRuntimeAdapter
            result = MockRuntimeAdapter().run(prompt, context, tools, skill_template)
            result.warnings.append(f"LLM 运行失败，已回退到确定性模板。错误: {str(exc)}")
            return result

    async def stream_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AgentRuntimeResult:
        if not settings.openai_api_key:
            from app.agent.runtime.mock_adapter import MockRuntimeAdapter
            return await MockRuntimeAdapter().stream_run(prompt, context, tools, skill_template, on_event=on_event)

        tool_results_summary = self._summarize_tool_results(context.get("tool_results", {}))

        from app.llm.prompts import RESEARCH_REPORT_PROMPT
        system_prompt = RESEARCH_REPORT_PROMPT
        user_message = (
            f"用户问题: {prompt}\n\n"
            f"工具数据摘要:\n{tool_results_summary}\n\n"
            f"报告模板/Skill:\n{skill_template}\n\n"
            "请生成报告。ContentJSON 部分必须严格符合 JSON 格式，包含 claims (list) 和 evidence_refs (list)。"
        )

        try:
            provider = OpenAIProvider(api_key=settings.openai_api_key)

            def on_token(token: str) -> None:
                if on_event:
                    on_event("token_delta", {"delta": token})

            data = await provider.generate_research_report_stream(system_prompt, user_message, on_token=on_token)

            return AgentRuntimeResult(
                title=str(data.get("title") or "AI 投研报告"),
                summary=str(data.get("summary") or "已生成深度投研分析。"),
                content_md=str(data.get("content_markdown") or data.get("content_md") or ""),
                content_json=data.get("content_json") or {},
                evidence_refs=data.get("evidence_refs") or data.get("content_json", {}).get("evidence_refs") or [],
                warnings=[],
            )
        except Exception as exc:
            from app.agent.runtime.mock_adapter import MockRuntimeAdapter
            result = MockRuntimeAdapter().run(prompt, context, tools, skill_template)
            result.warnings.append(f"LLM streaming failed, fell back to deterministic template. Error: {str(exc)}")

            content = result.content_md
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                stripped = para.strip()
                if not stripped:
                    continue
                if on_event:
                    on_event("token_delta", {"delta": stripped + "\n\n"})

            return result

    def _summarize_tool_results(self, results: dict[str, Any]) -> str:
        summary = []
        for name, data in results.items():
            summary.append(f"--- Tool: {name} ---\n{json.dumps(data, ensure_ascii=False, indent=2)}")
        return "\n".join(summary)
