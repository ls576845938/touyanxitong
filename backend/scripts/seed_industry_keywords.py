from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.stock_universe_job import run_stock_universe_job  # noqa: E402


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        result = run_stock_universe_job(session)
    print(result)
