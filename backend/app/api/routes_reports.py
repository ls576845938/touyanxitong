from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyReport
from app.db.session import get_session
from app.engines.report_context import build_report_context

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/latest")
def latest_report(session: Session = Depends(get_session)) -> dict[str, object]:
    report = session.scalars(select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)).first()
    if report is None:
        raise HTTPException(status_code=404, detail="daily report not found; run daily pipeline first")
    return _report_payload(session, report)


@router.get("")
def list_reports(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    reports = session.scalars(select(DailyReport).order_by(DailyReport.report_date.desc()).limit(60)).all()
    return [_report_summary(row) for row in reports]


@router.get("/{report_date}")
def report_by_date(report_date: date, session: Session = Depends(get_session)) -> dict[str, object]:
    report = session.scalar(select(DailyReport).where(DailyReport.report_date == report_date))
    if report is None:
        raise HTTPException(status_code=404, detail="daily report not found for date")
    return _report_payload(session, report)


def _report_payload(session: Session, report: DailyReport) -> dict[str, object]:
    context = build_report_context(session, report.report_date)
    top_trend_stocks = [_normalize_report_stock(row) for row in json.loads(report.top_trend_stocks)]
    new_watchlist_stocks = [_normalize_report_stock(row) for row in json.loads(report.new_watchlist_stocks)]
    return {
        "report_date": report.report_date.isoformat(),
        "title": report.title,
        "market_summary": report.market_summary,
        "top_industries": json.loads(report.top_industries),
        "top_trend_stocks": top_trend_stocks,
        "new_watchlist_stocks": new_watchlist_stocks,
        "risk_alerts": json.loads(report.risk_alerts),
        "data_quality": context["data_quality"],
        "research_universe": context["research_universe"],
        "watchlist_changes": context["watchlist_changes"],
        "full_markdown": report.full_markdown,
    }


def _report_summary(report: DailyReport) -> dict[str, object]:
    watchlist = json.loads(report.new_watchlist_stocks)
    risks = json.loads(report.risk_alerts)
    return {
        "report_date": report.report_date.isoformat(),
        "title": report.title,
        "market_summary": report.market_summary,
        "watch_count": len(watchlist),
        "risk_count": len(risks),
        "created_at": report.created_at.isoformat(),
    }


def _normalize_report_stock(row: dict[str, object]) -> dict[str, object]:
    confidence = row.get("confidence")
    if not isinstance(confidence, dict):
        confidence = {}
    data_confidence = _number_or_none(confidence.get("data_confidence"))
    evidence_confidence = _number_or_none(confidence.get("evidence_confidence"))
    source_confidence = _number_or_none(confidence.get("source_confidence"))
    fundamental_confidence = _number_or_none(confidence.get("fundamental_confidence"))
    news_confidence = _number_or_none(confidence.get("news_confidence"))
    combined_confidence = _number_or_none(confidence.get("combined_confidence"))
    if source_confidence is None:
        source_confidence = data_confidence
    if fundamental_confidence is None:
        fundamental_confidence = data_confidence
    if news_confidence is None:
        news_confidence = evidence_confidence
    if combined_confidence is None and data_confidence is not None and evidence_confidence is not None:
        combined_confidence = round(data_confidence * 0.55 + evidence_confidence * 0.45, 2)
    normalized = dict(row)
    normalized["confidence"] = {
        "source_confidence": source_confidence,
        "data_confidence": data_confidence,
        "fundamental_confidence": fundamental_confidence,
        "news_confidence": news_confidence,
        "evidence_confidence": evidence_confidence,
        "combined_confidence": combined_confidence,
        "level": confidence.get("level", "unknown"),
        "reasons": confidence.get("reasons", []),
    }
    normalized.setdefault("research_gate", {"passed": combined_confidence is not None and combined_confidence >= 0.6, "status": "review", "reasons": []})
    normalized.setdefault("fundamental_summary", {"status": "unknown", "confidence": fundamental_confidence, "missing_items": []})
    normalized.setdefault("news_evidence_status", "active" if news_confidence is not None and news_confidence >= 0.66 else "partial" if news_confidence else "missing")
    return normalized


def _number_or_none(value: object) -> float | None:
    return round(float(value), 2) if isinstance(value, int | float) else None
