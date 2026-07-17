#!/usr/bin/env bash
# Hourly job on the trading server (cron).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Optional: load env file with OKX_* if present
if [[ -f "$ROOT/.env.server" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.server"
  set +a
fi
exec python -m prod.cli watch-ten-u --iterations 1
