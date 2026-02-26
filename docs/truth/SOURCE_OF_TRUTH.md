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

## Cambios recientes (RTLAB Strategy Console - Bloque 1)

- Nuevas policies numericas en `config/policies/` para:
  - gates (`PBO/CSCV`, `DSR`, `walk_forward`, `cost_stress`, calidad minima de trades)
  - microestructura L1 (`VPIN`, spread/slippage/vol guards)
  - risk policy con soft/hard kill por bot/estrategia/simbolo
  - beast mode (limites y budget governor)
  - fees/funding snapshots (TTL y fallback)
- Base de configuracion fija para pasar de defaults ambiguos a criterios auditables con numeros.

## Cambios recientes (RTLAB Strategy Console - Bloques 2-7)

- `config/policies/*` cargado desde backend via `GET /api/v1/config/policies`
- `GET /api/v1/config/learning` extendido con `numeric_policies_summary`
- `Research Batch` guarda `policy_snapshot` y `policy_snapshot_summary` por batch (audit trail)
- Cost model real baseline implementado:
  - `FeeProvider`, `FundingProvider`, `SpreadModel`, `SlippageModel`
  - snapshots persistentes en SQLite (`fee_snapshots`, `funding_snapshots`)
  - runs `BT-*` guardan `fee_snapshot_id`, `funding_snapshot_id`, `spread/slippage_model_params`
- Microestructura L1 (VPIN proxy desde OHLCV) integrada al motor masivo:
  - `VPIN`, `CDF(VPIN)`, spread/slippage/vol guards
  - flags `MICRO_SOFT_KILL` / `MICRO_HARD_KILL`
  - debug visible en drilldown de `Research Batch`
- Gates avanzados en research masivo:
  - `PBO/CSCV`, `DSR`, `walk-forward`, `cost stress`, `min_trade_quality`
  - PASS/FAIL por variante visible en leaderboards
  - `mark-candidate` fail-closed si no pasa gates
- Modo Bestia (fase 1, scheduler local):
  - endpoints `/api/v1/research/beast/*`
  - cola de jobs + budget governor + concurrencia
  - UI en `Backtests` con panel de estado/jobs/stop-all/resume
  - sin Celery/Redis todavia (pendiente fase 2)

## Lo que sigue faltando (verdad actual)

- Virtualizacion real de tablas grandes en `Backtests / Runs` / comparador
- Smoke/E2E frontend automatizados
- UI de experimentos MLflow (si se habilita capability)
- Reportes avanzados en detalle de corrida (heatmap mensual, rolling Sharpe, distribuciones)
- Endpoints catalogo para `rerun_exact`, `clone_edit`, `export` unificado por `run_id`
- Fee/Funding provider con endpoints reales por exchange (hoy baseline con fallback+snapshot, sin fetch live por simbolo)
- VPIN L1 con trade tape real (hoy proxy desde OHLCV; falta tape de trades y BBO real)
- Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)

## Restricciones vigentes (no negociables)

- Opcion B: no auto-live
- Promocion real siempre via gates + canary + rollback + approve humano
- Secrets solo por ENV/Secrets
- Runtime y Research separados

## Parametros y criterios exactos (RTLAB Strategy Console)

### Gates avanzados (research masivo)
- `PBO/CSCV`: reject si `PBO > 0.05` (policy)
- `DSR`: `min_dsr = 0.95` (proxy deflactado por batch/trials en esta fase)
- `Walk-forward`: `folds = 5`, deben ser positivos al menos `4`, degradacion IS->OOS <= `30%`
- `Cost stress`: reevaluacion con `x1.5` y `x2.0`; a `x1.5` debe seguir rentable, a `x2.0` no debe caer mas de `50%` del score
- `Min trade quality`: `min_trades_per_run = 150`, `min_trades_per_symbol = 30`

### Microestructura L1 (VPIN proxy actual)
- **Nivel actual**: proxy desde OHLCV (no tape tick-by-tick todavia)
- Bucketing:
  - `target_draws_per_day = 9`
  - `V = ADV / target_draws_per_day` (fallback fijo si falta ADV)
- Bulk classification:
  - cambio de precio estandarizado
  - probabilidad de compra/venta via `CDF Normal`
- `OI_tau = |V_B - V_S|`
- `VPIN = rolling_mean(OI_tau) / (n * V)` con `n = 50`
- `CDF(VPIN)` via distribucion rolling empirica (proxy)
- Kills por simbolo:
  - `SOFT`: `CDF(VPIN) >= 0.90` (o guards spread/slippage/vol)
  - `HARD`: `CDF(VPIN) >= 0.97`

### Modo Bestia (estado actual)
- **Fase 1 implementada**: scheduler local con cola + concurrencia + budget governor + stop/resume
- **Fase 2 pendiente**: Celery + Redis + workers distribuidos + rate limit real por exchange

#### Como habilitar Modo Bestia
1. Ajustar `config/policies/beast_mode.yaml`:
   - `beast_mode.enabled: true`
2. Deploy backend
3. Usar `Backtests -> Research Batch -> Ejecutar en Modo Bestia`
4. Monitorear panel `Modo Bestia` (cola/jobs/budget/stop-all)
