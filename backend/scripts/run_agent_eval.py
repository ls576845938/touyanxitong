from __future__ import annotations

from app.agent.evaluation.replay_runner import replay_golden_cases
from app.db.session import SessionLocal, init_db

def main():
    # Use a separate test DB for evaluation to avoid polluting production
    init_db()
    with SessionLocal() as session:
        results = replay_golden_cases(session)
        all_passed = True
        for res in results:
            print(f"Prompt: {res['prompt']}")
            print(f"Task Type: {res['selected_task_type']}")
            print(f"Passed: {res['passed']}")
            if not res['passed']:
                print(f"Reasons: {res['reasons']}")
                all_passed = False
            print("-" * 20)
        
        if all_passed:
            print("All golden cases passed!")
        else:
            print("Some golden cases failed.")
            exit(1)

if __name__ == "__main__":
    main()
