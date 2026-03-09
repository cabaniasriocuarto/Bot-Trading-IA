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

## Nuevo plan consolidado
- Cerrar primero la visibilidad util del cerebro y la atribucion historica fuerte.
- Luego reforzar la atribucion directa `episode -> bot`.
- Despues cerrar Beast/Batch visible y coherente en deploy.
- Por ultimo endurecer OPE / observabilidad avanzada / surface final de monitoring.

## Bloques reordenados
1. Brain backend + ledgers + live source
2. Frontend minimo del cerebro (`Bots`)
3. Execution reality y live eligibility visibles
4. Trazabilidad fuerte `run/episode -> bot`
5. Beast/Batch deploy-visible y sin estados engañosos
6. OPE / observabilidad avanzada / endurecimiento final

## Bloque actual
- `Execution` ya consolidado con realidad operativa por bot. Siguiente foco: atribucion historica fuerte `episode -> bot`.

## Pendiente del siguiente bloque
- reforzar `episode -> bot_id` directo en analitica historica, no solo por backfill conservador
- Beast/Batch deploy-visible y sin estados engañosos

## Bloqueado / no implementado
- `execution_reality` aun no refleja fills reales end-to-end del runtime productivo
- `decision log` visual aun no tiene timeline rica ni filtros avanzados
- Beast/Batch aun puede verse inconsistente si el deploy backend/frontend no esta en la misma version

## Riesgos abiertos
- Si el backend desplegado no esta en la misma version que frontend, la pagina `Bots` puede verse parcial.
- Si el backend desplegado no esta en la misma version que frontend, `Execution` puede no recibir `execution_reality` real por bot.
- El warning de Recharts en prerender sigue siendo no bloqueante.

## Decisiones asumidas
- Se mantiene la rama `feature/brain-policy-ledgers-v1` porque sigue siendo el mismo objetivo coherente.
- Se empujan commits por bloque estable para no mezclar trabajo sano con cambios intermedios.
- La atribucion automatica sigue fail-closed cuando un `run_id` tiene mas de un bot posible.

## Archivos tocados
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
- `npm run lint -- "src/app/(app)/execution/page.tsx"`
- `npm run build`

## Build status
- `rtlab_dashboard` -> PASS
- warning conocido de Recharts en prerender -> no bloqueante
