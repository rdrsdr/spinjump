#!/usr/bin/env bash
# Verificação de layout com Chromium (Playwright) contra um servidor em execução.
# Uso: tools/ui_layout.sh <container-do-servidor> [porta]
set -euo pipefail
SRV=${1:-spinjump-ui}; PORT=${2:-8000}
docker run --rm --network "container:${SRV}" -v "$PWD":/work -w /work -u "$(id -u):$(id -g)" -e HOME=/tmp \
  mcr.microsoft.com/playwright/python:v1.55.0-noble \
  bash -c "pip install -q --user playwright==1.55.0 >/dev/null 2>&1; python tools/ui_layout.py http://localhost:${PORT} out/ui_check"
