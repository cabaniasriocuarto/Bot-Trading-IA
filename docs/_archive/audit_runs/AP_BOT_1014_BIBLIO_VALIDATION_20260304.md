# AP-BOT-1014 - Revalidacion Bibliografica (reuso de account snapshot en runtime)

Fecha: 2026-03-04

Objetivo: validar la optimizacion del loop runtime que evita doble consulta de cuenta en el mismo ciclo de decision/submit.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Fuentes primarias oficiales (web)
- Binance Spot API - Account endpoints:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` admite `account_positions`/`account_positions_ok` del ciclo actual.
  - `sync_runtime_state(...)` pasa snapshot ya obtenido al submit remoto.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell` valida `account_get == 1`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1235-1239`
  - reconciliacion y estado operativo dependen de fuentes de mercado/ordenes consistentes en tiempo.
- `docs/reference/biblio_txt/14_-_api-overview.txt:184-210`
  - uso disciplinado del estado API antes de ejecutar acciones, evitando consultas redundantes no necesarias.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:359-415`
  - control operativo y de riesgo como prioridad sobre ejecucion agresiva.

## NO EVIDENCIA LOCAL
- No hay regla textual exacta en la biblio local para "cantidad de llamadas API por loop".

## Decision de ingenieria aplicada
- Se adopta criterio de eficiencia segura: reutilizar snapshot de cuenta del mismo ciclo para mantener coherencia y bajar overhead.
- No cambia la semantica de riesgo/submit, solo elimina fetch redundante.

## Conclusion
- AP-BOT-1014 queda respaldado por principios locales de operacion coherente + contrato API oficial.
- Mejora eficiencia del runtime no-live sin alterar controles de seguridad/riesgo.