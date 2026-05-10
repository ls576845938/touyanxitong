#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/.runtime"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MARKETS="${MARKETS:-A,US,HK}"
PERIODS="${PERIODS:-320}"
SEED_STOCK_CODES="${SEED_STOCK_CODES:-300750,300308,300502,601138,688256,002050,002085,688235,835185,AAPL,NVDA,MSFT,TSLA,00700.HK,09988.HK,03690.HK,09868.HK}"

mkdir -p "$RUNTIME_DIR"

is_listening() {
  local port="$1"
  ss -ltn | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python scripts/run_daily_pipeline.py \
  --markets "$MARKETS" \
  --stock-codes "$SEED_STOCK_CODES" \
  --periods "$PERIODS" \
  > "$RUNTIME_DIR/pipeline.log" 2>&1

if is_listening "$BACKEND_PORT"; then
  echo "FastAPI already listening on :$BACKEND_PORT"
else
  nohup uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    > "$RUNTIME_DIR/backend.log" 2>&1 &
  echo $! > "$RUNTIME_DIR/backend.pid"
  echo "FastAPI started on :$BACKEND_PORT"
fi

cd "$FRONTEND_DIR"
if [ "${SKIP_FRONTEND_BUILD:-false}" != "true" ]; then
  npm run build > "$RUNTIME_DIR/frontend-build.log" 2>&1
fi

if is_listening "$FRONTEND_PORT"; then
  echo "Next.js already listening on :$FRONTEND_PORT"
else
  BACKEND_INTERNAL_URL="${BACKEND_INTERNAL_URL:-http://127.0.0.1:$BACKEND_PORT}" \
    nohup npm run start -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
    > "$RUNTIME_DIR/frontend.log" 2>&1 &
  echo $! > "$RUNTIME_DIR/frontend.pid"
  echo "Next.js started on :$FRONTEND_PORT"
fi

IP_ADDRESS="$(hostname -I | awk '{print $1}')"
echo "AlphaRadar: http://${IP_ADDRESS:-127.0.0.1}:$FRONTEND_PORT"
echo "Backend docs: http://${IP_ADDRESS:-127.0.0.1}:$BACKEND_PORT/docs"
