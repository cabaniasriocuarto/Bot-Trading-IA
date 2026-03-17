#!/usr/bin/env bash
set -euo pipefail

# Wrapper canonico para correr test_web_live_ready.py desde la raiz del repo.
# Uso:
#   ./scripts/test-web-live-ready.sh --durations=20 -q
#   ./scripts/test-web-live-ready.sh -m web_smoke -q
#   ./scripts/test-web-live-ready.sh -m web_integration -q
#   ./scripts/test-web-live-ready.sh -m web_slow -q

uv --directory rtlab_autotrader run python -m pytest tests/test_web_live_ready.py "$@"
