# AP-BOT-1033 - Revalidacion Bibliografica (submit bloqueado con reconciliacion no valida)

Fecha: 2026-03-05

Objetivo: impedir submit remoto cuando `runtime_reconciliation_ok=false` en runtime `testnet/live`.

## Cambios validados
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_maybe_submit_exchange_runtime_order(...)` agrega guard fail-closed `reason=reconciliation_not_ok`.
- `rtlab_autotrader/tests/test_web_live_ready.py`
  - `test_runtime_sync_testnet_skips_submit_when_reconciliation_not_ok`
  - ajuste de `test_runtime_sync_testnet_skips_submit_when_local_open_orders_remain_unverified` para reflejar guard nuevo.

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf`.

## Fuentes primarias externas (mismo nivel)
- Binance Spot API - Account endpoints:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints

## NO EVIDENCIA LOCAL
- No hay regla formal local que cuantifique tolerancia exacta de submit con `desync_count>0`; se aplica criterio conservador fail-closed.

## Veredicto
- El patch refuerza coherencia de estado antes de ejecutar ordenes: sin reconciliacion valida, no hay submit.
- Resultado esperado: menor riesgo de operacion sobre snapshot inconsistente.
