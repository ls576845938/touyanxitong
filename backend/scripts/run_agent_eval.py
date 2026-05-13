"""Run golden case evaluation including thesis quality checks.

Usage:
    cd backend && python scripts/run_agent_eval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on sys.path so 'import app' works
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.agent.evaluation.replay_runner import run_all_golden_cases_with_thesis_quality
from app.db.session import SessionLocal, init_db


def main() -> None:
    init_db()
    with SessionLocal() as session:
        results = run_all_golden_cases_with_thesis_quality(session)
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        print(f"\n{'=' * 60}")
        print(f"Golden Case Results: {passed}/{total} passed")
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(
                f"  [{status}] Case {r.case_index}: "
                f"task_type_ok={r.task_type_correct}, "
                f"thesis_count={r.thesis_count}, "
                f"thesis_count_ok={r.thesis_count_ok}, "
                f"evidence_ok={r.evidence_ok}, "
                f"invalidation_ok={r.invalidation_ok}, "
                f"horizon_ok={r.horizon_ok}, "
                f"confidence_ok={r.confidence_ok}, "
                f"forbidden_ok={r.forbidden_ok}, "
                f"risk_flags_ok={r.risk_flags_ok}, "
                f"uncertainty_ok={r.uncertainty_ok}"
            )
            if r.failures:
                for f in r.failures:
                    print(f"    - {f}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
