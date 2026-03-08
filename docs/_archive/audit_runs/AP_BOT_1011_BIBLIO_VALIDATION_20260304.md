# AP-BOT-1011 - Revalidacion Bibliografica (runtime por senal de estrategia)

Fecha: 2026-03-04

Objetivo: validar que el cambio de runtime (decision por estrategia principal + guardas fail-closed antes de submit remoto) mantiene coherencia tecnica y metodologica.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:24` -> `16 - Backtesting-and-its-Pitfalls.pdf`.
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._runtime_order_intent(...)` deriva `action/side/symbol/notional` desde estrategia principal por modo.
  - `RuntimeBridge._maybe_submit_exchange_runtime_order(...)` aplica guardas previas (`risk`, account snapshot, open orders, cooldown).
  - nuevo estado de trazabilidad runtime: `runtime_last_signal_*`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`.
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:4494-4519`
  - distingue utilidad de reglas segun regimen (momentum vs mean-reversion) y advierte que la accion depende del contexto/regimen.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:4781-4823`
  - refuerza separacion de estrategias por comportamiento (mean reverting/trending/momentum) y necesidad de decision consistente con ese tipo.
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1152-1239`
  - define semantica operativa de `open orders` y libro de ordenes como estado real para reconciliacion/decision.
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:2225-2230`
  - describe comportamiento de participantes tipo momentum como soporte conceptual de sesgo direccional por familia.

## NO EVIDENCIA LOCAL
- No hay una regla universal en la bibliografia local que imponga un mapping exacto `tag -> side` (por ejemplo, `mean_reversion -> SELL`) para este runtime especifico.

## Decision de ingenieria aplicada
- El mapping implementado es deliberadamente conservador y fail-closed:
  - sin estrategia principal valida o con tags defensivos -> `action=flat` (no orden);
  - solo opera cuando pasan guardas de riesgo y estado operativo (`risk.allow_new_positions`, account/open orders, cooldown).
- Esto reduce el riesgo de ordenes no justificadas en no-live y mejora trazabilidad de decision (`runtime_last_signal_*`).

## Conclusion
- AP-BOT-1011 queda bibliograficamente sustentado en principios locales de regimen/estrategia y microestructura de estado de ordenes.
- Donde no existe regla teorica exacta para mapping por tags, se declara `NO EVIDENCIA LOCAL` y se justifica como decision de seguridad operativa fail-closed.
