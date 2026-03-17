# Wrapper canonico para correr test_web_live_ready.py desde la raiz del repo.
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 --durations=20 -q
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 -k "mass_backtest or rate_limiter" -q

$ErrorActionPreference = "Stop"

uv --directory rtlab_autotrader run python -m pytest tests/test_web_live_ready.py @args
