from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print("AlphaRadar database initialized")
