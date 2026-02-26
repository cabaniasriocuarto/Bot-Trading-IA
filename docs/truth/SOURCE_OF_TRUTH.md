# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-02-26

## Estado actual (resumen ejecutivo)

El proyecto tiene:
- `Learning` Opcion B (recomienda, no auto-live)
- `Safe Update with Gates + Canary + Rollback`
- `Strategy Registry` persistente
- `Backtests & Research System` con runs/batches/catalogo/comparador/promocion controlada
- `Mass Backtests` (research offline) con ranking robusto
- UI `Research-first` con Backtests/Runs unificados y panel operativo de `Ejecucion`

## Cambios recientes (UI/UX Research-first)

- `Backtests / Runs` con paginacion, filtros, metadata minima visible y empty states guiados
- `Detalle de Corrida` con estructura tipo Strategy Tester por pestanas
- `Quick Backtest Legacy` marcado como deprecado y colapsado
- `Settings` con diagnostico WS/SSE corregido (sin falso timeout)
- `Rollout / Gates` con empty states accionables
- `Ejecucion` convertida en `Trading en Vivo (Paper/Testnet/Live) + Diagnostico`
- `Portfolio`, `Riesgo`, `Operaciones` y `Alertas` con labels/empty states mas claros

## Lo que sigue faltando (verdad actual)

- Virtualizacion real de tablas grandes en `Backtests / Runs` / comparador
- Smoke/E2E frontend automatizados
- UI de experimentos MLflow (si se habilita capability)
- Reportes avanzados en detalle de corrida (heatmap mensual, rolling Sharpe, distribuciones)
- Endpoints catalogo para `rerun_exact`, `clone_edit`, `export` unificado por `run_id`

## Restricciones vigentes (no negociables)

- Opcion B: no auto-live
- Promocion real siempre via gates + canary + rollback + approve humano
- Secrets solo por ENV/Secrets
- Runtime y Research separados

