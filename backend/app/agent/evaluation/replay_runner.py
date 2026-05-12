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
        
        reasons = []
        if response.selected_task_type != case["expected_task_type"]:
            reasons.append(f"Expected task type {case['expected_task_type']}, got {response.selected_task_type}")
        
        for phrase in case.get("required_phrases", []):
            if phrase not in content:
                reasons.append(f"Missing required phrase: {phrase}")
                
        for phrase in case.get("forbidden_phrases", []):
            if phrase in content:
                reasons.append(f"Found forbidden phrase: {phrase}")
                
        results.append(
            {
                "prompt": case["prompt"],
                "status": response.status,
                "selected_task_type": response.selected_task_type,
                "passed": len(reasons) == 0,
                "reasons": reasons,
            }
        )
    return results
