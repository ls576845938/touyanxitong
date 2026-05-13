"""Run due thesis reviews for a given date (default: today).

Usage:
    python -m backend.scripts.run_thesis_review [YYYY-MM-DD]
"""

from __future__ import annotations

import sys
from datetime import date

from app.db.session import SessionLocal, init_db
from app.engines.thesis_review_engine import run_due_reviews


def main() -> None:
    init_db()
    as_of_date = date.today()
    if len(sys.argv) > 1:
        as_of_date = date.fromisoformat(sys.argv[1])

    db = SessionLocal()
    try:
        results = run_due_reviews(as_of_date, db)
        db.commit()
        print(f"Reviewed {len(results)} theses:")
        for r in results:
            print(f"  Thesis #{r.thesis_id}: {r.review_status} (horizon={r.review_horizon_days}d)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
