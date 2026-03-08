# AP-BOT-1029 - Bibliographic Validation (2026-03-05)

Objetivo del patch: reducir efecto de cache negativo en readiness de exchange dentro del runtime loop.

## Cambios validados
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `RuntimeBridge._runtime_exchange_ready(...)` ahora fuerza `diagnose_exchange(..., force_refresh=True)` cuando el resultado cacheado viene en fail.
- `rtlab_autotrader/tests/test_web_live_ready.py`
  - `test_runtime_exchange_ready_forces_refresh_after_cached_failure`
  - `test_runtime_exchange_ready_uses_cached_success_without_forced_refresh`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` especifica para politicas de cache de readiness en runtime loop.

## Fuentes externas
- `NO EVIDENCIA WEB` requerida para este patch:
  - cambio de control-flow interno (fail-cache refresh) sin formula cuantitativa ni dependencia de estandar externo.

## Validacion ejecutada
- `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_exchange_ready_forces_refresh_after_cached_failure or runtime_exchange_ready_uses_cached_success_without_forced_refresh or runtime_sync_clears_submit_reason_when_runtime_exits_real_mode or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot" -q` -> PASS (`4 passed`)
