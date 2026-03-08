# AP-BOT-1020 - Revalidacion Bibliografica (estados remotos avanzados)

Fecha: 2026-03-05

Objetivo: respaldar el ajuste de reconciliacion runtime para estados `PENDING_CANCEL` y `EXPIRED_IN_MATCH` preservando semantica de fill parcial/terminal.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_apply_remote_order_status_to_local(...)` actualizado para `NEW/PENDING_CANCEL`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1152-1239`
  - reconciliacion operativa de estados de orden y manejo consistente del lifecycle.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:272-274`
  - gestion de riesgo/operacion en sistemas automatizados.

## NO EVIDENCIA LOCAL
- No hay tabla exacta en biblio local para codigos API exchange-especificos `PENDING_CANCEL` y `EXPIRED_IN_MATCH`.

## Complemento primario (mismo nivel)
- Binance Spot API - Account endpoints (`GET /api/v3/order`):
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints

## Conclusion
- AP-BOT-1020 mantiene coherencia entre estado remoto y OMS local en escenarios avanzados de lifecycle.
- El cambio reduce desalineaciones de fill parcial en reconciliacion no-live.
