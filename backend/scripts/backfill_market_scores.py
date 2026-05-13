"""Controlled market-wide trend + score backfill for the latest date only.

Usage:
    # Dry-run first
    python scripts/backfill_market_scores.py --dry-run --limit 100

    # Limited real run
    python scripts/backfill_market_scores.py --limit 1000

    # Full run with resume
    python scripts/backfill_market_scores.py --resume

    # Specific market only
    python scripts/backfill_market_scores.py --market A --limit 500
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from sqlalchemy import func, select, text

from app.db.models import (
    DailyBar,
    Industry,
    IndustryHeat,
    NewsArticle,
    Stock,
    StockScore,
    TrendSignal,
)
from app.db.session import SessionLocal, init_db
from app.engines.tenbagger_score_engine import calculate_stock_scores
from app.engines.trend_engine import calculate_trend_metrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIN_BARS_DEFAULT = 120
LOOKBACK_DAYS_DEFAULT = 250
BATCH_SIZE_DEFAULT = 300


def _eligible_stocks(
    session,
    *,
    market: str | None = None,
    as_of_date: date | None = None,
    min_bars: int = MIN_BARS_DEFAULT,
    lookback_days: int = LOOKBACK_DAYS_DEFAULT,
    limit: int | None = None,
) -> list[Stock]:
    """Return active stocks with >= min_bars DailyBar rows in the lookback window."""
    today = as_of_date or date.today()
    window_start = today - timedelta(days=lookback_days)

    # Subquery: count bars per stock in window
    bar_counts = (
        select(
            DailyBar.stock_code,
            func.count(DailyBar.id).label("bar_count"),
            func.max(DailyBar.trade_date).label("last_date"),
        )
        .where(
            DailyBar.trade_date >= window_start,
            DailyBar.trade_date <= today,
        )
        .group_by(DailyBar.stock_code)
        .having(func.count(DailyBar.id) >= min_bars)
        .subquery()
    )

    q = select(Stock).join(bar_counts, Stock.code == bar_counts.c.stock_code)
    q = q.where(Stock.is_active == True)

    if market and market.upper() != "ALL":
        q = q.where(Stock.market == market.upper())

    q = q.order_by(bar_counts.c.bar_count.desc())

    if limit:
        q = q.limit(limit)

    return list(session.scalars(q).all())


def _load_bars(
    session,
    stock_codes: list[str],
    as_of_date: date,
    lookback_days: int = LOOKBACK_DAYS_DEFAULT,
) -> dict[str, list[Any]]:
    """Load DailyBar rows for the given stocks, grouped by stock_code."""
    window_start = as_of_date - timedelta(days=lookback_days)
    rows = (
        session.scalars(
            select(DailyBar)
            .where(
                DailyBar.stock_code.in_(stock_codes),
                DailyBar.trade_date >= window_start,
                DailyBar.trade_date <= as_of_date,
            )
            .order_by(DailyBar.stock_code, DailyBar.trade_date)
        )
        .all()
    )
    bars_by_stock: dict[str, list[Any]] = {}
    for bar in rows:
        bars_by_stock.setdefault(bar.stock_code, []).append(bar)
    return bars_by_stock


def _upsert_trend_signals(
    session, metrics_list: list[Any], trade_date: date
) -> int:
    """Upsert TrendSignal rows. Returns count created/updated."""
    if not metrics_list:
        return 0

    count = 0
    for m in metrics_list:
        existing = session.scalar(
            select(TrendSignal).where(
                TrendSignal.stock_code == m.stock_code,
                TrendSignal.trade_date == trade_date,
            )
        )
        if existing:
            existing.relative_strength_score = m.relative_strength_score
            existing.relative_strength_rank = m.relative_strength_rank
            existing.is_ma_bullish = int(m.is_ma_bullish)
            existing.is_breakout_120d = int(m.is_breakout_120d)
            existing.is_breakout_250d = int(m.is_breakout_250d)
            existing.volume_expansion_ratio = m.volume_expansion_ratio
            existing.max_drawdown_60d = m.max_drawdown_60d
            existing.trend_score = m.trend_score
            existing.explanation = m.explanation
            existing.ma20 = m.ma20
            existing.ma60 = m.ma60
            existing.ma120 = m.ma120
            existing.ma250 = m.ma250
            existing.return_20d = getattr(m, "return_20d", 0.0)
            existing.return_60d = getattr(m, "return_60d", 0.0)
            existing.return_120d = getattr(m, "return_120d", 0.0)
        else:
            ts = TrendSignal(
                stock_code=m.stock_code,
                trade_date=trade_date,
                relative_strength_score=m.relative_strength_score,
                relative_strength_rank=m.relative_strength_rank,
                is_ma_bullish=int(m.is_ma_bullish),
                is_breakout_120d=int(m.is_breakout_120d),
                is_breakout_250d=int(m.is_breakout_250d),
                volume_expansion_ratio=m.volume_expansion_ratio,
                max_drawdown_60d=m.max_drawdown_60d,
                trend_score=m.trend_score,
                explanation=m.explanation,
                ma20=m.ma20,
                ma60=m.ma60,
                ma120=m.ma120,
                ma250=m.ma250,
                return_20d=getattr(m, "return_20d", 0.0),
                return_60d=getattr(m, "return_60d", 0.0),
                return_120d=getattr(m, "return_120d", 0.0),
            )
            session.add(ts)
        count += 1
    return count


def _upsert_stock_scores(
    session, score_list: list[Any], trade_date: date
) -> int:
    """Upsert StockScore rows. Returns count created/updated."""
    if not score_list:
        return 0

    count = 0
    for s in score_list:
        existing = session.scalar(
            select(StockScore).where(
                StockScore.stock_code == s.stock_code,
                StockScore.trade_date == trade_date,
            )
        )
        if existing:
            existing.industry_score = s.industry_score
            existing.company_score = s.company_score
            existing.trend_score = s.trend_score
            existing.catalyst_score = s.catalyst_score
            existing.risk_penalty = s.risk_penalty
            existing.raw_score = s.raw_score
            existing.source_confidence = s.source_confidence
            existing.data_confidence = s.data_confidence
            existing.fundamental_confidence = s.fundamental_confidence
            existing.news_confidence = s.news_confidence
            existing.evidence_confidence = s.evidence_confidence
            existing.confidence_level = s.confidence_level
            existing.confidence_reasons = str(s.confidence_reasons)
            existing.final_score = s.final_score
            existing.rating = s.rating
            existing.explanation = s.explanation
        else:
            ss = StockScore(
                stock_code=s.stock_code,
                trade_date=trade_date,
                industry_score=s.industry_score,
                company_score=s.company_score,
                trend_score=s.trend_score,
                catalyst_score=s.catalyst_score,
                risk_penalty=s.risk_penalty,
                raw_score=s.raw_score,
                source_confidence=s.source_confidence,
                data_confidence=s.data_confidence,
                fundamental_confidence=s.fundamental_confidence,
                news_confidence=s.news_confidence,
                evidence_confidence=s.evidence_confidence,
                confidence_level=s.confidence_level,
                confidence_reasons=str(s.confidence_reasons),
                final_score=s.final_score,
                rating=s.rating,
                explanation=s.explanation,
            )
            session.add(ss)
        count += 1
    return count


def _load_context(
    session, stock_codes: list[str], trade_date: date
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[Any]]]:
    """Load industry heat, fundamentals, and news for scoring context."""
    # Industry heat for the target date
    heats = session.scalars(
        select(IndustryHeat).where(IndustryHeat.trade_date == trade_date)
    ).all()
    heat_by_industry_name: dict[str, Any] = {}
    for h in heats:
        industry = session.get(Industry, h.industry_id)
        if industry:
            heat_by_industry_name[industry.name] = h

    # Latest fundamental per stock
    from app.db.models import FundamentalMetric

    fundamentals: dict[str, Any] = {}
    for code in stock_codes:
        fm = session.scalars(
            select(FundamentalMetric)
            .where(
                FundamentalMetric.stock_code == code,
                FundamentalMetric.report_date <= trade_date,
            )
            .order_by(FundamentalMetric.report_date.desc())
            .limit(1)
        ).first()
        if fm:
            fundamentals[code] = fm

    # News articles grouped by stock
    from datetime import datetime, timezone

    news_cutoff = trade_date - timedelta(days=30)
    articles = session.scalars(
        select(NewsArticle)
        .where(NewsArticle.published_at >= datetime(news_cutoff.year, news_cutoff.month, news_cutoff.day, tzinfo=timezone.utc))
        .order_by(NewsArticle.published_at.desc())
        .limit(2000)
    ).all()

    articles_by_stock: dict[str, list[Any]] = {}
    for a in articles:
        try:
            codes_json = a.related_stocks or "[]"
            import json
            related = json.loads(codes_json) if isinstance(codes_json, str) else codes_json
            for code in related:
                articles_by_stock.setdefault(code, []).append(a)
        except (json.JSONDecodeError, TypeError):
            pass

    return heat_by_industry_name, fundamentals, articles_by_stock


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled market-wide trend + score backfill")
    parser.add_argument("--universe", default="all_recent", choices=["all_recent"],
                        help="Stock universe selection mode")
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS_DEFAULT)
    parser.add_argument("--min-bars", type=int, default=MIN_BARS_DEFAULT)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="Skip stocks that already have TrendSignal + StockScore on as-of-date")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--market", default=None, choices=["A", "US", "HK", "ALL", None])
    parser.add_argument("--as-of-date", default=None,
                        help="Target date YYYY-MM-DD (default: latest DailyBar date)")

    args = parser.parse_args()
    init_db()

    session = SessionLocal()
    try:
        # Determine as_of_date
        if args.as_of_date:
            as_of_date = date.fromisoformat(args.as_of_date)
        else:
            as_of_date = session.scalar(select(func.max(DailyBar.trade_date)))
            if not as_of_date:
                print("ERROR: No DailyBar data found.")
                sys.exit(1)
            print(f"Using latest DailyBar date: {as_of_date}")

        # Get eligible stocks
        eligible = _eligible_stocks(
            session,
            market=args.market,
            as_of_date=as_of_date,
            min_bars=args.min_bars,
            lookback_days=args.lookback_days,
            limit=args.limit,
        )

        print(f"\nEligible stocks: {len(eligible)}")
        print(f"  min_bars: {args.min_bars}")
        print(f"  lookback_days: {args.lookback_days}")
        print(f"  as_of_date: {as_of_date}")
        print(f"  batch_size: {args.batch_size}")
        print(f"  dry_run: {args.dry_run}")
        print()

        if args.dry_run:
            print("[DRY RUN] Would process these stocks (sample):")
            for s in eligible[:10]:
                print(f"  {s.code} {s.name} ({s.market})")
            if len(eligible) > 10:
                print(f"  ... and {len(eligible) - 10} more")
            print(f"\n[DRY RUN] dry-run complete. No data written.")
            session.close()
            return

        # Resume filter: skip stocks that already have both trend + score
        if args.resume:
            existing_trend = session.scalars(
                select(TrendSignal.stock_code).where(
                    TrendSignal.trade_date == as_of_date
                )
            ).all()
            existing_score = session.scalars(
                select(StockScore.stock_code).where(
                    StockScore.trade_date == as_of_date
                )
            ).all()
            completed = set(existing_trend) & set(existing_score)
            before = len(eligible)
            eligible = [s for s in eligible if s.code not in completed]
            print(f"Resume: skipped {before - len(eligible)} already-completed stocks")
            print(f"Remaining: {len(eligible)}")

        if not eligible:
            print("No stocks to process.")
            session.close()
            return

        # Load scoring context (industry heat, fundamentals, news)
        all_codes = [s.code for s in eligible]
        heat_by_industry, fundamentals, articles_by_stock = _load_context(
            session, all_codes, as_of_date
        )

        # Batch processing
        total_batches = (len(eligible) + args.batch_size - 1) // args.batch_size
        batch_num = 0
        stats = Counter(
            trend_created=0, score_created=0, trend_failed=0, score_failed=0,
            skipped_insufficient_bars=0, batches_ok=0, batches_failed=0,
        )
        failure_reasons: Counter = Counter()
        t0 = time.monotonic()

        for i in range(0, len(eligible), args.batch_size):
            batch_num += 1
            batch_stocks = eligible[i : i + args.batch_size]
            batch_codes = [s.code for s in batch_stocks]
            print(
                f"[{batch_num}/{total_batches}] "
                f"Processing {len(batch_stocks)} stocks "
                f"({batch_stocks[0].code} ... {batch_stocks[-1].code}) ...",
                end=" ", flush=True,
            )

            try:
                # --- Step 1: Trend Signals ---
                bars_by_stock = _load_bars(session, batch_codes, as_of_date, args.lookback_days)

                # Filter stocks with insufficient bars
                valid_bars: dict[str, list[Any]] = {}
                for code, bars in bars_by_stock.items():
                    if len(bars) >= args.min_bars:
                        valid_bars[code] = bars
                    else:
                        stats["skipped_insufficient_bars"] += 1

                if valid_bars:
                    trend_metrics = calculate_trend_metrics(valid_bars)
                    if not args.dry_run:
                        trend_count = _upsert_trend_signals(session, trend_metrics, as_of_date)
                        stats["trend_created"] += trend_count
                        session.flush()
                else:
                    trend_metrics = []

                # --- Step 2: Stock Scores ---
                if trend_metrics:
                    # Load trend signals we just created
                    trend_by_code: dict[str, Any] = {}
                    for m in trend_metrics:
                        ts = TrendSignal(
                            stock_code=m.stock_code,
                            trade_date=as_of_date,
                            relative_strength_score=m.relative_strength_score,
                            relative_strength_rank=m.relative_strength_rank,
                            is_ma_bullish=int(m.is_ma_bullish),
                            is_breakout_120d=int(m.is_breakout_120d),
                            is_breakout_250d=int(m.is_breakout_250d),
                            volume_expansion_ratio=m.volume_expansion_ratio,
                            max_drawdown_60d=m.max_drawdown_60d,
                            trend_score=m.trend_score,
                            explanation=m.explanation,
                            ma20=m.ma20, ma60=m.ma60, ma120=m.ma120, ma250=m.ma250,
                            return_20d=getattr(m, "return_20d", 0.0),
                            return_60d=getattr(m, "return_60d", 0.0),
                            return_120d=getattr(m, "return_120d", 0.0),
                        )
                        trend_by_code[m.stock_code] = ts

                    # Filter stocks that match trend codes
                    trend_codes_set = {m.stock_code for m in trend_metrics}
                    stocks_for_score = [s for s in batch_stocks if s.code in trend_codes_set]
                    stocks_for_score = [s for s in batch_stocks if s.code in trend_codes_set]

                    score_metrics = calculate_stock_scores(
                        stocks=stocks_for_score,
                        latest_trend_by_code=trend_by_code,
                        latest_heat_by_industry_name=heat_by_industry,
                        articles_by_stock=articles_by_stock,
                        trade_date=as_of_date,
                        latest_fundamental_by_code=fundamentals,
                    )
                    if not args.dry_run:
                        score_count = _upsert_stock_scores(session, score_metrics, as_of_date)
                        stats["score_created"] += score_count
                else:
                    score_metrics = []

                # Commit batch
                if not args.dry_run:
                    session.commit()
                stats["batches_ok"] += 1
                print(
                    f"OK (trend={len(trend_metrics)}, score={len(score_metrics) if trend_metrics else 0})"
                )

            except Exception as exc:
                stats["batches_failed"] += 1
                failure_reasons[type(exc).__name__] += 1
                print(f"FAILED: {exc}")
                if not args.dry_run:
                    session.rollback()
                # Continue to next batch

        elapsed = time.monotonic() - t0

        # Final summary
        print()
        print("=" * 60)
        print("Backfill Summary")
        print("=" * 60)
        print(f"  Eligible stocks:          {len(eligible)}")
        print(f"  Batches:                  {stats['batches_ok']} OK / {stats['batches_failed']} FAILED")
        print(f"  Trend signals created:    {stats['trend_created']}")
        print(f"  Scores created:           {stats['score_created']}")
        print(f"  Skipped (insufficient bars): {stats['skipped_insufficient_bars']}")
        print(f"  Elapsed:                  {elapsed:.1f}s")
        if failure_reasons:
            print(f"  Failure reasons:")
            for reason, count in failure_reasons.most_common():
                print(f"    {reason}: {count}")

        # Verify
        if not args.dry_run:
            final_trend = session.scalar(
                select(func.count()).select_from(TrendSignal).where(
                    TrendSignal.trade_date == as_of_date
                )
            )
            final_score = session.scalar(
                select(func.count()).select_from(StockScore).where(
                    StockScore.trade_date == as_of_date
                )
            )
            print(f"\nVerification on {as_of_date}:")
            print(f"  TrendSignal count: {final_trend}")
            print(f"  StockScore count:  {final_score}")

            # Top 20 by score
            top20 = session.scalars(
                select(StockScore).where(StockScore.trade_date == as_of_date)
                .order_by(StockScore.final_score.desc()).limit(20)
            ).all()
            print(f"\nTop 20 scored stocks:")
            for s in top20:
                print(f"  {s.stock_code}: score={s.final_score:.1f} rating={s.rating}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
