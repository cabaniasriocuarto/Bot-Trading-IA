# AP-BOT-1031 - Revalidacion Bibliografica (fail-closed en ordenes locales no verificadas)

Fecha: 2026-03-05

Objetivo: endurecer runtime para evitar submit remoto duplicado cuando `openOrders` queda vacio pero la consulta de `order status` falla.

## Cambios validados
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_close_absent_local_open_orders(...)` ahora conserva la orden local (fail-closed) cuando `GET /api/v3/order` falla.
  - `_maybe_submit_exchange_runtime_order(...)` ahora bloquea submit si existen ordenes locales abiertas (`local_open_orders_present`) aunque `openOrders` remoto venga vacio.
- `rtlab_autotrader/tests/test_web_live_ready.py`
  - `test_runtime_sync_testnet_keeps_absent_local_open_order_when_order_status_fetch_fails`
  - `test_runtime_sync_testnet_skips_submit_when_local_open_orders_remain_unverified`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf`.

## Fuentes primarias externas (mismo nivel)
- Binance Spot API - Account endpoints (`GET /api/v3/openOrders`, `GET /api/v3/order`):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints
- Binance Spot API - Trading endpoints (semantica de orden):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints

## NO EVIDENCIA LOCAL
- No existe en bibliografia local un contrato exchange-especifico que defina la semantica exacta de errores transitorios de `GET /api/v3/order`.

## Veredicto
- El patch queda alineado con microestructura operativa: ante estado remoto incierto, no inventar cierre local ni abrir nueva orden.
- Resultado esperado: menor riesgo de duplicacion de ordenes por desincronizacion transitoria.
