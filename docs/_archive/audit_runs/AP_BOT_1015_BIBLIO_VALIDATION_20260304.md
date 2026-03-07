# AP-BOT-1015 - Revalidacion Bibliografica (estados PARTIALLY_FILLED/REJECTED)

Fecha: 2026-03-04

Objetivo: respaldar la cobertura de regresion agregada para estados de orden remota `PARTIALLY_FILLED` y `REJECTED` en runtime no-live.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Fuentes primarias oficiales (web)
- Binance Spot API - Account endpoints (`GET /api/v3/order`):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints

### Evidencia tecnica del repo
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status`.
  - `test_runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status`.
- Runtime cubierto en `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_apply_remote_order_status_to_local(...)`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1152-1239`
  - estados de orden abierta y reconciliacion de libro como base operacional.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:359-415`
  - control de riesgo/estado operativo antes de ejecutar y escalar.

## NO EVIDENCIA LOCAL
- No hay tabla de mapeo exacta local para codigos de estado API exchange-especificos.

## Complemento web primario
- Se usa contrato oficial de Binance para semantica de estado de orden individual.

## Conclusion
- AP-BOT-1015 queda respaldado por teoria local de reconciliacion + fuente oficial de estado de orden.
- El cambio reduce riesgo de regresion en lifecycle runtime no-live.