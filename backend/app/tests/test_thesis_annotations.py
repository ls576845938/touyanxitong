"""Tests for thesis annotation feedback.

Annotations are HUMAN feedback only -- they do NOT modify
``ResearchThesisReview.review_status`` or ``ResearchThesis.status``.  They
are stored separately in ``ResearchThesisAnnotation`` for analytics and
review purposes.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.api.routes_annotations import VALID_LABELS
from app.db.models import ResearchThesis, ResearchThesisAnnotation, ResearchThesisReview


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thesis(db_session, **kw) -> ResearchThesis:
    """Create and return a minimal ResearchThesis."""
    thesis = ResearchThesis(
        source_type="daily_report",
        source_id="1",
        subject_type="stock",
        subject_id="300308",
        subject_name="中际旭创",
        thesis_title="趋势确认测试",
        thesis_body="该标的趋势偏强，需关注持续性。",
        direction="up",
        horizon_days=20,
        confidence=70.0,
        **kw,
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_annotation(
    db_session,
    thesis: ResearchThesis,
    *,
    label: str = "useful",
    user_id: str = "test_user",
    rating: int = 4,
    note: str = "测试标注",
) -> ResearchThesisAnnotation:
    """Create an annotation for *thesis*."""
    annotation = ResearchThesisAnnotation(
        thesis_id=thesis.id,
        user_id=user_id,
        label=label,
        rating=rating,
        note=note,
    )
    db_session.add(annotation)
    db_session.flush()
    return annotation


# =============================================================================
# Tests
# =============================================================================


class TestThesisAnnotation:
    """Test thesis annotation model and behavior."""

    def test_create_annotation(self, db_session) -> None:
        """Should create annotation with valid label."""
        thesis = _make_thesis(db_session)
        annotation = _make_annotation(db_session, thesis)

        assert annotation.id is not None
        assert annotation.thesis_id == thesis.id
        assert annotation.label == "useful"
        assert annotation.user_id == "test_user"
        assert annotation.rating == 4
        assert annotation.note == "测试标注"
        assert annotation.created_at is not None

    def test_annotation_does_not_change_review_status(self, db_session) -> None:
        """Creating annotation must NOT modify thesis review_status."""
        thesis = _make_thesis(db_session)

        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 20),
            review_status="pending",
        )
        db_session.add(review)
        db_session.flush()

        review_status_before = review.review_status

        # Create annotation
        _make_annotation(db_session, thesis)
        db_session.commit()

        # Verify review status unchanged
        db_session.refresh(review)
        assert review.review_status == review_status_before

    def test_annotation_does_not_change_thesis_status(self, db_session) -> None:
        """Creating annotation must NOT modify thesis status."""
        thesis = _make_thesis(db_session)
        thesis_status_before = thesis.status

        _make_annotation(db_session, thesis)
        db_session.commit()
        db_session.refresh(thesis)

        assert thesis.status == thesis_status_before

    def test_annotation_labels_are_valid(self, db_session) -> None:
        """All standard labels should be storable."""
        thesis = _make_thesis(db_session)
        db_session.commit()

        for label in sorted(VALID_LABELS):
            annotation = _make_annotation(db_session, thesis, label=label)
            db_session.commit()
            assert annotation.label == label

        # Verify all annotations exist
        total = db_session.scalar(select(func.count(ResearchThesisAnnotation.id)))
        assert total == len(VALID_LABELS)

    def test_annotation_summary_stats(self, db_session) -> None:
        """Summary should aggregate annotations correctly."""
        thesis = _make_thesis(db_session)
        db_session.commit()

        # Create multiple annotations with different labels
        _make_annotation(db_session, thesis, label="useful")
        _make_annotation(db_session, thesis, label="useful")
        _make_annotation(db_session, thesis, label="too_vague")
        db_session.commit()

        # Count by label
        counts = db_session.execute(
            select(
                ResearchThesisAnnotation.label,
                func.count(ResearchThesisAnnotation.id),
            ).group_by(ResearchThesisAnnotation.label)
        ).all()

        label_counts = {label: cnt for label, cnt in counts}
        assert label_counts.get("useful", 0) == 2
        assert label_counts.get("too_vague", 0) == 1

        # Total count
        total = db_session.scalar(select(func.count(ResearchThesisAnnotation.id)))
        assert total == 3
