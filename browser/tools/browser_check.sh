#!/usr/bin/env bash
# Sobe um servidor estático para browser/public e roda a verificação no Chromium (Playwright).
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT=${PORT:-8090}
python3 -m http.server "$PORT" --directory browser/public >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV' EXIT
sleep 1
docker run --rm --network host -v "$PWD":/work -w /work -u "$(id -u):$(id -g)" -e HOME=/tmp \
  mcr.microsoft.com/playwright/python:v1.55.0-noble \
  bash -c "pip install -q --user playwright==1.55.0 >/dev/null 2>&1; python browser/tools/browser_check.py http://localhost:${PORT} out/browser"
