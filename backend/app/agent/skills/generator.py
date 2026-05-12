from __future__ import annotations

import json
from typing import Any

from app.agent.schemas import AgentRunRequest, AgentTaskType


def generate_skill_from_run(request: AgentRunRequest, task_type: AgentTaskType, report_title: str, context: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    name = f"{report_title} 工作流"
    description = f"由自然语言请求生成的 Alpha Radar 可复用投研 Skill：{request.user_prompt[:80]}"
    config = {
        "task_type": str(task_type),
        "symbols": request.symbols or context.get("selected_symbols", []),
        "industry_keywords": request.industry_keywords or context.get("selected_industries", []),
        "risk_preference": request.risk_preference,
        "time_window": request.time_window,
        "tool_plan": sorted(context.get("tool_results", {}).keys()),
    }
    skill_md = "\n".join(
        [
            f"# {name}",
            "",
            "## 触发语义",
            request.user_prompt,
            "",
            "## 工作流",
            f"- task_type: {task_type}",
            "- 只读读取平台股票、产业链、评分、证据和报告工具。",
            "- 输出投研分析、观察清单、风险提示、证据链和不确定性说明。",
            "",
            "## 配置",
            "```json",
            json.dumps(config, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    return name, skill_md, config
