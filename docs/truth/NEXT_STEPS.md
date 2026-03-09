# NEXT STEPS (Plan vivo del proyecto)

Fecha: 2026-03-09

## Hecho hasta ahora
- `live` ya entra como fuente real de evidencia del cerebro.
- El backend ya expone `POST /api/v1/bots/{bot_id}/ope-evaluate` con OPE `Doubly Robust` conservadora sobre policies del bot.
- El backend ya expone:
  - `GET /api/v1/bots/{bot_id}/brain`
  - `GET /api/v1/bots/{bot_id}/decision-log`
  - `GET /api/v1/bots/{bot_id}/experience`
  - `GET /api/v1/execution/reality`
  - `GET /api/v1/strategies/{strategy_id}/truth`
  - `GET /api/v1/strategies/{strategy_id}/evidence`
- `Bots` ya muestra:
  - brain del bot
  - resumen de `decision log`
  - resumen de `execution reality`
  - experiencia atribuida al bot
  - drilldown de episodios atribuidos por `run_id`, fuente, `dataset_source`, `dataset_hash`, atribucion, confianza, peso y flags
- `Execution` ya muestra por bot:
  - elegibilidad live
  - preflight
  - realidad operativa reciente
  - reconciliacion, slippage, spread, impacto, latencia y maker/taker
- La atribucion historica del bot ahora usa:
  - `experience_episode.bot_id` cuando existe atribucion exacta/fuerte
  - `run_bot_link` y `related_bot_ids` cuando el episodio es ambiguo
- La experiencia por bot resume:
  - `direct_attribution_count`
  - `linked_only_count`
  - `ambiguous_link_count`
- Beast/Batch ya separa:
  - policy/runtime real de `config/policies`
  - disponibilidad de dataset real del formulario
  - estado historico del `BX` seleccionado

## Nuevo plan consolidado
- Endurecer ahora el cerebro con OPE conservadora y luego pasar a visibilidad final en frontend.
- Despues cerrar observabilidad avanzada / alerts / drift / kill switches.
- Luego volver al tramo deploy-visible de Beast/Batch si sigue habiendo divergencia entre preview y backend.

## Bloques reordenados
1. Brain backend + ledgers + live source
2. Frontend minimo del cerebro (`Bots`)
3. Execution reality y live eligibility visibles
4. Trazabilidad fuerte `run/episode -> bot`
5. Beast/Batch deploy-visible y sin estados engañosos
6. OPE conservadora / safe policy improvement del bot
7. Observabilidad avanzada / alerts / drift / kill switches
8. Surface final de frontend para cerebro / truth / reality

## Bloque actual
- OPE conservadora del policy layer cerrada en backend. Siguiente foco: observabilidad avanzada / alerts / drift / kill switches.

## Pendiente del siguiente bloque
- observabilidad avanzada / alertas / drift / kill switches
- endpoints y surface minima adicional para brain/truth/reality si hace falta despues del endurecimiento backend
- frontend especifico del cerebro si el backend nuevo ya queda estable

## Bloqueado / no implementado
- `execution_reality` aun no refleja fills reales end-to-end del runtime productivo
- `decision log` visual aun no tiene timeline rica ni filtros avanzados
- Beast/Batch aun puede verse inconsistente si el deploy backend/frontend no esta en la misma version
- la OPE actual aun no usa propensity logging real ni reward realizado por decision exacta; usa reward proxy conservador

## Riesgos abiertos
- Si el backend desplegado no esta en la misma version que frontend, la pagina `Bots` puede verse parcial.
- Si el backend desplegado no esta en la misma version que frontend, `Execution` puede no recibir `execution_reality` real por bot.
- La atribucion `episode -> bot_id` sigue fail-closed si el run historico trae multiples bots posibles; eso es intencional.
- El warning de Recharts en prerender sigue siendo no bloqueante.
- Si el backend desplegado no incorpora este bloque, `Backtests` todavia puede mostrar Beast como si estuviera bloqueado por policy cuando en realidad falta dataset o faltan policies en runtime.
- La OPE es conservadora y util para governance, pero aun no reemplaza una validacion OPE mas rica con behavior policy logueada desde runtime.

## Decisiones asumidas
- Se mantiene la rama `feature/brain-policy-ledgers-v1` porque sigue siendo el mismo objetivo coherente.
- Se empujan commits por bloque estable para no mezclar trabajo sano con cambios intermedios.
- La atribucion automatica sigue fail-closed cuando un `run_id` tiene mas de un bot posible.
- Beast debe fallar de forma explicable: dataset y policy se diagnostican por separado.
- La promotion de una policy del bot sigue fail-closed si OPE no tiene muestra minima, soporte exacto suficiente o lower bound superior al baseline.

## Archivos tocados
- `rtlab_autotrader/rtlab_core/learning/brain.py`
- `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- `rtlab_autotrader/rtlab_core/learning/service.py`
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/tests/test_learning_experience_option_b.py`
- `rtlab_autotrader/tests/test_brain_policy_service.py`
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`
- `rtlab_autotrader/tests/test_web_live_ready.py`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/lib/types.ts`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
- `python -m py_compile rtlab_autotrader/rtlab_core/learning/brain.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/rtlab_core/web/app.py`
- `python -m py_compile rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/learning/service.py`
- `python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q`
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_service.py -q`
- `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q`
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k beast -q`
- `npm run lint -- "src/app/(app)/backtests/page.tsx" "src/lib/types.ts"`
- `npm run build`

## Build status
- bloque backend atribucion fuerte -> PASS
- bloque Beast/Batch frontend+backend local -> PASS
