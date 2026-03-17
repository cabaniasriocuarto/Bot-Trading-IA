# Wrapper canonico para correr test_web_live_ready.py desde la raiz del repo.
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 --durations=20 -q
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 -m web_smoke -q
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 -m web_integration -q
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-web-live-ready.ps1 -m web_slow -q

$ErrorActionPreference = "Stop"

uv --directory rtlab_autotrader run python -m pytest tests/test_web_live_ready.py @args
