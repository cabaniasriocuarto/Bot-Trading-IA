# AP-BOT-1032 - Revalidacion Bibliografica (fail-closed por account snapshot)

Fecha: 2026-03-05

Objetivo: bloquear submit remoto cuando falla la verificacion de posiciones de cuenta (`/api/v3/account`) en runtime `testnet/live`.

## Cambios validados
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_maybe_submit_exchange_runtime_order(...)` ahora retorna `account_positions_fetch_failed` cuando no hay snapshot de cuenta valido.
  - `sync_runtime_state(...)` pasa `account_positions_reason` al submitter para trazabilidad de error.
- `rtlab_autotrader/tests/test_web_live_ready.py`
  - `test_runtime_sync_testnet_skips_submit_when_account_positions_fetch_fails`
  - ajuste de `test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency` para mockear `GET /api/v3/account`.

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf`.

## Fuentes primarias externas (mismo nivel)
- Binance Spot API - Account endpoints:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints
- Binance Spot API - Trading endpoints:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints

## NO EVIDENCIA LOCAL
- No existe especificacion local exchange-especifica que obligue semantica exacta frente a timeout/errores de `GET /api/v3/account`.

## Veredicto
- El patch queda alineado con criterio risk-first: sin snapshot de cuenta confiable, no abrir nueva posicion remota.
- Resultado esperado: menor riesgo de sobreexposicion por submit sin estado de cuenta verificado.
