# AP-BOT-1012 - Revalidacion Bibliografica (order status para ordenes ausentes)

Fecha: 2026-03-04

Objetivo: validar el endurecimiento del runtime que resuelve ordenes ausentes en `openOrders` consultando `order status` antes de cerrar localmente.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf`.

### Fuentes primarias oficiales (web)
- Binance Spot API - Account endpoints (`GET /api/v3/order`, `GET /api/v3/openOrders`):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints
- Binance Spot API - Trading endpoints (estructura de respuesta de orden/fills):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_fetch_exchange_order_status(...)` consulta `GET /api/v3/order` para ordenes ausentes.
  - `_apply_remote_order_status_to_local(...)` mapea `FILLED/CANCELED/EXPIRED/REJECTED/NEW/PARTIALLY_FILLED` a estado local.
  - `_close_absent_local_open_orders(...)` deja de cancelar ciegamente: primero intenta resolver estado remoto.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`.
  - `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1152-1239`
  - semantica de `open orders` y libro de ordenes como estado operativo real para reconciliacion.
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1235-1239`
  - ciclo de order routing y reportes de trade/quote como base de conciliacion de estado.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:4730`
  - recomendacion de escalar y operar con control prudencial/riesgo en runtime.
- `docs/reference/biblio_txt/14_-_api-overview.txt:184-210`
  - necesidad de estado operacional de API para decisiones de ejecucion y continuidad de servicio.

## NO EVIDENCIA LOCAL
- No hay contrato API exchange-especifico en la bibliografia local para semantica exacta de `GET /api/v3/order` (campos/estados concretos).

## Complemento web primario
- Se usa documentacion oficial de Binance para resolver ese gap de contrato API de forma verificable y al mismo nivel tecnico.

## Conclusion
- AP-BOT-1012 queda respaldado por teoria local de reconciliacion microestructural + contrato oficial de exchange para estado final de orden.
- El cambio reduce cierres ciegos y mejora consistencia runtime sin habilitar LIVE.