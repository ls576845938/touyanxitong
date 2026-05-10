#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export MOCK_DATA="${MOCK_DATA:-false}"
export MARKET_DATA_SOURCE="${MARKET_DATA_SOURCE:-auto}"
export ALLOW_MOCK_FALLBACK="${ALLOW_MOCK_FALLBACK:-false}"
export ENABLED_MARKETS="${ENABLED_MARKETS:-A,US,HK}"
export NEWS_DATA_SOURCE="${NEWS_DATA_SOURCE:-auto}"

MARKETS="${MARKETS:-A,HK,US}"
PERIODS="${PERIODS:-320}"
BATCH_LIMIT="${BATCH_LIMIT:-8}"
SLEEP_SECONDS="${SLEEP_SECONDS:-4}"
MAX_ATTEMPTS_PER_SYMBOL="${MAX_ATTEMPTS_PER_SYMBOL:-8}"
ROUND_TIMEOUT="${ROUND_TIMEOUT:-6h}"
RESTART_SLEEP_SECONDS="${RESTART_SLEEP_SECONDS:-60}"

echo "continuous free-source backfill started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "markets=$MARKETS periods=$PERIODS batch_limit=$BATCH_LIMIT source=$MARKET_DATA_SOURCE allow_mock_fallback=$ALLOW_MOCK_FALLBACK"

round=0
while true; do
  round=$((round + 1))
  echo "starting backfill round=$round at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set +e
  timeout "$ROUND_TIMEOUT" ionice -c2 -n7 nice -n 15 .venv/bin/python scripts/backfill_all_market_data.py \
    --markets "$MARKETS" \
    --source "$MARKET_DATA_SOURCE" \
    --periods "$PERIODS" \
    --batch-limit "$BATCH_LIMIT" \
    --max-batches 0 \
    --sleep-seconds "$SLEEP_SECONDS" \
    --min-complete-ratio 0.95 \
    --max-attempts-per-symbol "$MAX_ATTEMPTS_PER_SYMBOL" \
    --skip-research
  code=$?
  set -e

  if [[ "$code" == "0" ]]; then
    echo "backfill exhausted available candidates at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    break
  fi

  echo "backfill round=$round exited with code=$code at $(date -u +%Y-%m-%dT%H:%M:%SZ); restarting after ${RESTART_SLEEP_SECONDS}s"
  sleep "$RESTART_SLEEP_SECONDS"
done

echo "refreshing research outputs at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
.venv/bin/python - <<'PY'
from app.db.session import SessionLocal, init_db
from app.pipeline.daily_report_job import run_daily_report_job
from app.pipeline.evidence_chain_job import run_evidence_chain_job
from app.pipeline.industry_heat_job import run_industry_heat_job
from app.pipeline.industry_mapping_job import run_industry_mapping_job
from app.pipeline.news_ingestion_job import run_news_ingestion_job
from app.pipeline.sector_industry_mapping_job import run_sector_industry_mapping_job
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job
from app.pipeline.trend_signal_job import run_trend_signal_job

init_db()
with SessionLocal() as session:
    print("news_ingestion", run_news_ingestion_job(session))
    print("sector_industry_mapping", run_sector_industry_mapping_job(session, markets=("A",)))
    print("industry_mapping", run_industry_mapping_job(session, markets=("A", "HK", "US")))
    print("industry_heat", run_industry_heat_job(session))
    print("trend_signal", run_trend_signal_job(session))
    print("tenbagger_score", run_tenbagger_score_job(session))
    print("evidence_chain", run_evidence_chain_job(session))
    print("daily_report", run_daily_report_job(session))
PY
echo "continuous free-source backfill finished at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
