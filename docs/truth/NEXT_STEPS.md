# NEXT STEPS (Plan vivo del proyecto)

Fecha: 2026-03-09

## Hecho hasta ahora
- `live` ya entra como fuente real de evidencia del cerebro.
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
- Cerrar primero Beast/Batch deploy-visible y sin mensajes engañosos.
- Luego endurecer OPE / observabilidad avanzada / surface final de monitoring.
- Despues cerrar el frontend especifico del cerebro que aun falte para decision log / truth / reality.

## Bloques reordenados
1. Brain backend + ledgers + live source
2. Frontend minimo del cerebro (`Bots`)
3. Execution reality y live eligibility visibles
4. Trazabilidad fuerte `run/episode -> bot`
5. Beast/Batch deploy-visible y sin estados engañosos
6. OPE / observabilidad avanzada / endurecimiento final

## Bloque actual
- Beast/Batch deploy-visible y sin mensajes/estados engañosos cerrado a nivel backend + frontend local. Siguiente foco: OPE / observabilidad avanzada / endurecimiento final.

## Pendiente del siguiente bloque
- OPE / safe policy improvement del policy layer
- observabilidad avanzada / alertas / drift / kill switches
- surface minima adicional para brain/truth/reality si hace falta despues del endurecimiento backend

## Bloqueado / no implementado
- `execution_reality` aun no refleja fills reales end-to-end del runtime productivo
- `decision log` visual aun no tiene timeline rica ni filtros avanzados
- Beast/Batch aun puede verse inconsistente si el deploy backend/frontend no esta en la misma version

## Riesgos abiertos
- Si el backend desplegado no esta en la misma version que frontend, la pagina `Bots` puede verse parcial.
- Si el backend desplegado no esta en la misma version que frontend, `Execution` puede no recibir `execution_reality` real por bot.
- La atribucion `episode -> bot_id` sigue fail-closed si el run historico trae multiples bots posibles; eso es intencional.
- El warning de Recharts en prerender sigue siendo no bloqueante.
- Si el backend desplegado no incorpora este bloque, `Backtests` todavia puede mostrar Beast como si estuviera bloqueado por policy cuando en realidad falta dataset o faltan policies en runtime.

## Decisiones asumidas
- Se mantiene la rama `feature/brain-policy-ledgers-v1` porque sigue siendo el mismo objetivo coherente.
- Se empujan commits por bloque estable para no mezclar trabajo sano con cambios intermedios.
- La atribucion automatica sigue fail-closed cuando un `run_id` tiene mas de un bot posible.
- Beast debe fallar de forma explicable: dataset y policy se diagnostican por separado.

## Archivos tocados
- `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- `rtlab_autotrader/rtlab_core/learning/service.py`
- `rtlab_autotrader/tests/test_learning_experience_option_b.py`
- `rtlab_autotrader/tests/test_brain_policy_service.py`
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`
- `rtlab_autotrader/tests/test_web_live_ready.py`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/lib/types.ts`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
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
