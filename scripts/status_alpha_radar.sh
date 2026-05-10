#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "Ports:"
ss -ltnp | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})" || true

echo
echo "FastAPI health:"
curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" || true

echo
echo
echo "Frontend API proxy:"
curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/market/summary" | head -c 500 || true
echo

echo
echo "Market data status:"
curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/market/data-status" | head -c 1200 || true
echo

echo
echo "Data quality:"
curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/market/data-quality" | head -c 1200 || true
echo

echo
echo "Ingestion tasks:"
curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/market/ingestion-tasks" | head -c 1200 || true
echo
