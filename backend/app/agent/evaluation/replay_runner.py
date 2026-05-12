from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.evaluation.golden_cases import GOLDEN_CASES
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import AgentRunRequest
from app.db.models import AgentArtifact


def replay_golden_cases(session: Session) -> list[dict[str, object]]:
    orchestrator = AgentOrchestrator(session)
    results = []
    for case in GOLDEN_CASES:
        response = orchestrator.run(AgentRunRequest(user_prompt=str(case["prompt"])))
        artifact = session.get(AgentArtifact, response.artifact_id) if response.artifact_id else None
        content = artifact.content_md if artifact else ""
        results.append(
            {
                "prompt": case["prompt"],
                "status": response.status,
                "selected_task_type": response.selected_task_type,
                "passed": response.selected_task_type == case["expected_task_type"]
                and all(phrase in content for phrase in case["required_phrases"]),
            }
        )
    return results
