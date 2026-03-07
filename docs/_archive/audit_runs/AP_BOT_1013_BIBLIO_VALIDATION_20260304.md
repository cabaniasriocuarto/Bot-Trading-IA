# AP-BOT-1013 - Revalidacion Bibliografica (riesgo del mismo ciclo antes de submit)

Fecha: 2026-03-04

Objetivo: validar el cambio de runtime que evita submit remoto cuando el risk gate del ciclo actual bloquea nuevas posiciones.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:8` -> `11 - Advances in Financial Machine Learning (2018).pdf`.
- `docs/reference/BIBLIO_INDEX.md:24` -> `16 - Backtesting-and-its-Pitfalls.pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - reorden de `sync_runtime_state(...)` para ejecutar submit remoto despues de calcular `RiskDecision` del mismo ciclo.
  - submit condicionado a `decision.kill=false` y estado `running` valido.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:359-415`
  - enfatiza que la gestion de riesgo es requisito central previo a escalar ejecucion.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:4658-4730`
  - reglas de control de riesgo/position sizing como primera barrera operativa del sistema.
- `docs/reference/biblio_txt/16_-_Backtesting-and-its-Pitfalls.txt:1-40`
  - valida que decisiones operativas deben respetar restricciones de riesgo y no depender de supuestos optimistas.

## NO EVIDENCIA LOCAL
- No hay una prescripcion textual exacta en la bibliografia local sobre "orden exacto de funciones dentro del loop runtime".

## Decision de ingenieria aplicada
- Se aplica criterio fail-closed: primero riesgo del ciclo actual, despues intento de submit.
- Esto evita enviar ordenes usando un snapshot de riesgo atrasado (`_last_risk` del ciclo previo).

## Conclusion
- AP-BOT-1013 queda alineado con los principios locales de risk-first execution.
- El cambio reduce el gap operativo de enforcement sin habilitar LIVE.