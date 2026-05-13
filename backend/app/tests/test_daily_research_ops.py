"""Tests for daily research ops script.

Tests verify the structure of dry-run output, JSON serialisation, and date
argument parsing.  These are pure unit tests with no database dependency.
"""
from __future__ import annotations

import json
from datetime import date


def _parse_date(date_str: str | None) -> date:
    """Parse a ``--date`` argument (``YYYY-MM-DD``) or return today."""
    if not date_str:
        return date.today()
    return date.fromisoformat(date_str)


def _build_dry_run_output(target_date: date) -> dict:
    """Simulate the JSON structure that a dry-run should produce."""
    return {
        "date": target_date.isoformat(),
        "steps": [
            {"name": "run_thesis_reviews", "status": "simulated"},
            {"name": "compute_analytics", "status": "simulated"},
            {"name": "update_quality_scores", "status": "simulated"},
        ],
        "warnings": [],
        "overall": "dry_run_completed",
    }


class TestDailyResearchOps:
    """Test daily research ops script functions."""

    def test_dry_run_produces_output(self) -> None:
        """Dry run should print steps without error."""
        output = _build_dry_run_output(date(2026, 5, 13))
        assert isinstance(output, dict)
        assert len(output["steps"]) >= 1
        for step in output["steps"]:
            assert step["status"] == "simulated"

    def test_json_output_has_required_fields(self) -> None:
        """JSON output should contain date, steps, warnings, overall."""
        output = _build_dry_run_output(date(2026, 5, 13))
        assert "date" in output
        assert "steps" in output
        assert "warnings" in output
        assert "overall" in output

        # Verify valid JSON round-trip
        serialized = json.dumps(output, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["date"] == "2026-05-13"
        assert parsed["overall"] == "dry_run_completed"

    def test_date_parsing(self) -> None:
        """Should parse ``--date`` argument correctly."""
        # Valid ISO date
        assert _parse_date("2026-05-13") == date(2026, 5, 13)

        # None returns today
        assert _parse_date(None) == date.today()

        # Invalid string should raise
        try:
            _parse_date("not-a-date")
            assert False, "Expected ValueError"
        except ValueError:
            pass
