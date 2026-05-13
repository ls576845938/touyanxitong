from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.agent.schemas import AgentTaskType


SKILL_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SKILL_DIR / "templates"


@dataclass(frozen=True)
class SystemSkill:
    id: str
    name: str
    description: str
    skill_type: str
    template_file: str


SYSTEM_SKILLS: tuple[SystemSkill, ...] = (
    SystemSkill("system:stock_deep_research", "个股深度投研", "围绕单只股票生成趋势、评分、产业链和证据链报告。", AgentTaskType.STOCK_DEEP_RESEARCH, "stock_deep_research.md"),
    SystemSkill("system:industry_chain_radar", "产业链雷达", "分析产业链热度、节点、核心股票和催化证据。", AgentTaskType.INDUSTRY_CHAIN_RADAR, "industry_chain_radar.md"),
    SystemSkill("system:trend_pool_scan", "趋势股票池扫描", "按评分、动量和风险筛出观察池。", AgentTaskType.TREND_POOL_SCAN, "trend_pool_scan.md"),
    SystemSkill("system:tenbagger_candidate", "十倍股早期特征候选", "整理具备早期成长特征的候选清单和证据缺口。", AgentTaskType.TENBAGGER_CANDIDATE, "tenbagger_candidate.md"),
    SystemSkill("system:daily_market_brief", "每日市场简报", "生成强产业链、高动量股票、催化事件和风险预警。", AgentTaskType.DAILY_MARKET_BRIEF, "daily_market_brief.md"),
    SystemSkill("system:risk_budget", "风险预算与仓位管理", "分析风险预算、计算仓位上限、检查组合暴露和生成仓位计划。", AgentTaskType.RISK_BUDGET, "risk_budget.md"),
)


def system_skill_by_type(skill_type: str | AgentTaskType) -> SystemSkill:
    value = str(skill_type)
    for skill in SYSTEM_SKILLS:
        if skill.skill_type == value:
            return skill
    return SYSTEM_SKILLS[0]


def system_skill_by_id(skill_id: str) -> SystemSkill | None:
    for skill in SYSTEM_SKILLS:
        if skill.id == skill_id:
            return skill
    return None


def load_skill_template(skill_type: str | AgentTaskType) -> str:
    skill = system_skill_by_type(skill_type)
    return (TEMPLATE_DIR / skill.template_file).read_text(encoding="utf-8")


def system_skill_payloads() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for skill in SYSTEM_SKILLS:
        payloads.append(
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "skill_type": skill.skill_type,
                "skill_md": (TEMPLATE_DIR / skill.template_file).read_text(encoding="utf-8"),
                "skill_config": {"template_file": skill.template_file},
                "owner_user_id": None,
                "is_system": True,
                "created_at": None,
                "updated_at": None,
            }
        )
    return payloads
