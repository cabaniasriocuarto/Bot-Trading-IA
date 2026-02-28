# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-02-28

## Actualizacion auditoria comite (2026-02-28)

- Se generaron artefactos de auditoria completos en `docs/audit/`:
  - `AUDIT_REPORT_20260228.md`
  - `AUDIT_FINDINGS_20260228.md`
  - `AUDIT_BACKLOG_20260228.md`
- Seguridad endurecida adicional:
  - backend ahora rechaza headers internos (`x-rtlab-role/x-rtlab-user`) si falta `INTERNAL_PROXY_TOKEN` (fail-closed).
  - login backend con rate-limit + lockout (`10 intentos/10min`, lockout `30min` tras `20` fallos por `IP+user`).
  - BFF falla cerrado si falta `INTERNAL_PROXY_TOKEN`.
- Bibliografia:
  - nuevo extractor incremental `scripts/biblio_extract.py`.
  - `docs/reference/BIBLIO_INDEX.md` regenerado con SHA256 por fuente.
  - `docs/reference/biblio_txt/.gitignore` agregado para salida local de texto.
- Hallazgos abiertos bloqueantes para LIVE:
  - runtime real OMS/broker (hoy simulado).
- Estado `/api/v1/bots` (performance):
  - cache TTL in-memory activado en endpoint `GET /api/v1/bots` (`10s` default).
  - invalidacion explicita en create/patch/bulk de bots y en logs `breaker_triggered`.
  - benchmark local actualizado: `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260228_AFTER_CACHE.md` con `p95=35.524ms` (PASS `<300ms`).
  - benchmark remoto post-deploy:
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY.md` -> `p95=1032.039ms` (FAIL) + `NO EVIDENCIA` por cardinalidad (`1` bot).
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY_100BOTS.md` -> `p95=1458.513ms` con `100` bots (FAIL).
  - estado actual: objetivo `p95 < 300ms` en Railway sigue abierto; requiere optimizacion adicional.
- Estado backtest por strategy_id:
  - `StrategyRunner` ahora despacha senales por familia de estrategia (`trend`, `breakout`, `meanreversion`, `trend_scanning`, `defensive`).
  - el sesgo de logica unica en `BacktestEngine` quedo resuelto en modo incremental (sin refactor masivo).
- Estado gate de calidad por simbolo:
  - `MassBacktestEngine` ya aplica `min_trades_per_symbol` real en `min_trade_quality`.
  - cada variante publica `trade_count_by_symbol_oos` y `min_trades_per_symbol_oos` en `summary`.
  - UI `Backtests > Research Batch` ya expone esos campos en leaderboard y drilldown.
- Estado fuente canónica de gates:
  - learning/research/runtime consumen `config/policies/gates.yaml` como fuente primaria.
  - `knowledge/policies/gates.yaml` queda como fallback/soporte documental cuando falta config.
- Estado surrogate adjustments (research):
  - `enable_surrogate_adjustments` ya no se evalua directo desde request/config.
  - se resuelve por policy canónica (`gates.surrogate_adjustments`) con `allowed_execution_modes`.
  - default actual: solo `demo`, sin override por request y con bloqueo de promotion (`promotable=false`, `recommendable_option_b=false`).
  - trazabilidad visible en `summary/manifest/artifacts` bajo `surrogate_adjustments`.

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
- `Backtests / Runs` con orden por click en columnas clave (incluye `WinRate`) y sin recorte artificial de seleccion legacy
- Parser de errores de Backtests endurecido para evitar `[object Object]` en UI y mostrar `detail/message/cause` real
- `Research Batch` con shortlist persistente por `BX`:
  - guardado de variantes/runs en `best_runs_cache`
  - restauraciÃ³n de shortlist al reabrir batch
  - sincronizaciÃ³n opcional con Comparador de Runs
- Backtests / Runs D2 (Comparison Table Pro) ahora renderiza por ventana visible (virtualizacion + overscan + espaciadores).
- Strategies compactado para escalar con 50+ filas (menos altura por fila y acciones principales mas compactas).
- `Detalle de Corrida` con estructura tipo Strategy Tester por pestanas
- `Quick Backtest Legacy` marcado como deprecado y colapsado
- `Settings` con diagnostico WS/SSE corregido (sin falso timeout)
- `Rollout / Gates` con empty states accionables
- `Ejecucion` convertida en `Trading en Vivo (Paper/Testnet/Live) + Diagnostico`
- `Ejecucion` reforzada (Bloque 4):
  - gestion de estrategias primarias por modo (`paper/testnet/live`) desde la misma pantalla
  - bloqueo explicito de cambio a `LIVE` si checklist critico no esta en PASS
  - atajos de seleccion masiva de operadores por estado/modo runtime
- `Portfolio`, `Riesgo`, `Operaciones` y `Alertas` con labels/empty states mas claros
- `Operaciones` reforzado (Bloque 3):
  - orden configurable de tabla
  - seleccion masiva + borrado por IDs
  - preview de borrado filtrado (`dry_run`)
  - filtros rapidos por modo/entorno/estrategia desde paneles resumen

## Bibliografia y trazabilidad externa

- Se agrego `docs/reference/BIBLIO_INDEX.md` con el listado consolidado de fuentes externas (1-20).
- Se agrego `docs/reference/biblio_raw/.gitignore` para permitir trabajo local con PDFs sin versionarlos.
- Politica vigente: bibliografia raw fuera de git; solo se versiona indice y metadatos de trazabilidad.

## Actualizacion 2026-02-28 (seguridad runtime + annualizacion + CI frontend)

- Auth interna backend endurecida:
  - `current_user` ahora acepta `x-rtlab-role/x-rtlab-user` solo si `x-rtlab-proxy-token` coincide con `INTERNAL_PROXY_TOKEN`.
  - sin token valido, los headers internos se ignoran y se requiere `Bearer` de sesion.
- BFF actualizado para proxy seguro:
  - `rtlab_dashboard/src/app/api/[...path]/route.ts` y `rtlab_dashboard/src/lib/events-stream.ts` ahora reenvian `x-rtlab-proxy-token` desde ENV.
- Credenciales por defecto en produccion:
  - fail-fast al boot si `NODE_ENV=production` y quedan credenciales default (`admin/admin123!`, `viewer/viewer123!`) o `AUTH_SECRET` debil.
  - `G2_AUTH_READY` ahora reporta `no_default_credentials` y falla si hay defaults.
- Runtime de ejecucion real:
  - estado del bot incorpora `runtime_engine` (`simulated|real`).
  - nuevo gate `G9_RUNTIME_ENGINE_REAL`.
  - `LIVE` queda bloqueado si runtime sigue simulado.
  - `status/health` exponen `runtime_engine/runtime_mode`.
- Backtest:
  - Sharpe/Sortino anualizados por timeframe real (`1m`, `5m`, `10m`, `15m`, `1h`, `1d` + parse generico `Nm/Nh/Nd`).
- CI:
  - workflow agrega job frontend (`npm ci`, `tsc --noEmit`, `vitest`, `next build`).

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

## Cambios recientes (Calibracion real - fundamentals + costos)

- Nueva policy `config/policies/fundamentals_credit_filter.yaml`:
  - `enabled`, `fail_closed`, `apply_markets`, `freshness_max_days`
  - scoring y thresholds auditables
  - reglas por `common/preferred/bond/fund_bond`
  - snapshots con TTL
- Nuevo modulo `rtlab_core/fundamentals/credit_filter.py`:
  - calcula `fund_score`, `fund_status`, `allow_trade`, `risk_multiplier`, `explain[]`
  - aplica fail-closed cuando faltan datos y el mercado esta en scope
  - reutiliza snapshot vigente y persiste snapshot nuevo en DB
  - autoload opcional de snapshot local JSON para equities cuando source esta en `unknown/auto/local_snapshot`
  - traza de origen en `source_ref.source_path` + `DATA_SOURCE_LOCAL_SNAPSHOT`
  - soporte `remote_json` configurable por policy/env con `endpoint_template` y auth header por ENV
  - `source=auto` intenta remoto y luego fallback local (enforced/fail-closed se mantiene)
  - traza remota en `source_ref.source_url` + `DATA_SOURCE_REMOTE_SNAPSHOT|DATA_SOURCE_REMOTE_ERROR`
- Catalogo SQLite extendido:
  - nueva tabla `fundamentals_snapshots`
  - `backtest_runs` guarda `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`
- Wiring backend:
  - `app.py` y `mass_backtest_engine.py` ahora resuelven y guardan metadata fundamentals por run
  - ambos usan `source=auto` para habilitar remoto+fallback sin hardcode de proveedor
  - si `fundamentals_credit_filter` esta enforced y `allow_trade=false`, bloquea corrida (fail-closed)
- Cost model endurecido:
  - `FeeProvider` intenta endpoints reales Binance (`/api/v3/account/commission`, `/sapi/v1/asset/tradeFee`) y fallback seguro
  - `FeeProvider` soporta fallback por exchange (`per_exchange_defaults`) + override por ENV
  - `FundingProvider` intenta `/fapi/v1/fundingRate` (Binance) y `/v5/market/funding/history` (Bybit) para perps
  - `SpreadModel` agrega estimador `roll` cuando no hay BBO ni spread explicito
- Promotion/rollout endurecido (bloque 4/5):
  - `validate_promotion` agrega constraints fail-closed para corridas de catalogo:
    - `cost_snapshots_present`
    - `fundamentals_allow_trade`
  - `_build_rollout_report_from_catalog_row` ahora preserva trazabilidad de costos/fundamentals en el reporte de validacion y promocion.
- Admin multi-bot/live endurecido (bloque 5/5):
  - metricas de `BotInstance` ahora incluyen desglose por modo (`shadow/paper/testnet/live`) para `trades/winrate/net_pnl/sharpe/run_count`.
  - metricas de kills reales derivadas de logs (`breaker_triggered`) con `kills_total`, `kills_24h`, `kills_by_mode` y timestamp del ultimo kill.
  - transicion de bots a `mode=live` bloqueada por gates en backend (`create/patch/bulk-patch`) si LIVE no esta listo.
  - UI de `Ejecucion` bloquea el boton masivo `Modo LIVE` con motivo explicito cuando faltan checks.
- Gates default ajustado:
  - `dsr_min` default en rollout offline ahora `0.95`
- Tests ejecutados:
  - `test_backtest_catalog_db.py`
  - `test_fundamentals_credit_filter.py`
  - `test_cost_providers.py`
  - resultado: `11 passed`

## Actualizacion Opcion B + Opcion C (sin refactor masivo)

### Fundamentals gating por modo (policy explicita)

- Orden de severidad aplicado:
  - `UNKNOWN < WEAK < BASIC < STRONG`
- Reglas por modo:
  - `LIVE`: minimo `STRONG`, fail-closed si faltan requeridos (`allow_trade=false`)
  - `PAPER`: minimo `STRONG`, fail-closed si faltan requeridos (`allow_trade=false`)
  - `BACKTEST`: minimo `BASIC`; si faltan requeridos permite corrida con:
    - `fund_status=UNKNOWN`
    - `warnings` incluye `fundamentals_missing`
    - `promotion_blocked=true`
    - `fundamentals_quality=ohlc_only`
- Separacion Snapshot vs Decision:
  - `get_fundamentals_snapshot_cached(...)` cachea solo snapshot crudo
  - `evaluate_credit_policy(...)` calcula decision final por modo
  - `allow_trade` no se cachea
- Backtest equities sin snapshot fundamentals:
  - ya no aborta por defecto en BACKTEST
  - el run se crea con metadata/warnings y bloqueado para promocion
  - en PAPER/LIVE se mantiene fail-closed

### Bots overview performance (/api/v1/bots)

- Se elimino el patron N+1 por bot.
- Nuevo agregado batch en backend:
  - `ConsoleStore.get_bots_overview(...)`
- Carga en lote:
  - KPIs por modo y por pool de estrategias
  - logs recientes por bot (max 20 por bot; limite total 2000)
  - kills por bot y por modo
- Endpoint `GET /api/v1/bots` mantiene contrato actual y ahora consume overview batch interno.
- Benchmark reproducible local agregado:
  - script: `scripts/benchmark_bots_overview.py`
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_20260228.md`
  - resultado local (100 bots, 200 requests, warmup 30): `p95=280.875ms` (objetivo `<300ms` => PASS).
  - el mismo script ya soporta benchmark remoto (`--base-url`) con validacion de evidencia minima (`--min-bots-required`, default `100`).
- Benchmark remoto ejecutado (Railway):
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md`
  - resultado actual: `p95=1663.014ms` (FAIL vs `<300ms`)
  - `NO EVIDENCIA` de carga objetivo por cardinalidad: `/api/v1/bots` retorna `1` bot (se exigen `>=100` para este test).

### Breaker events schema (fuente canonica para kills)

- Tabla SQLite:
  - `breaker_events`
- Campos:
  - `bot_id` (obligatorio; faltante -> `unknown_bot`)
  - `mode` (obligatorio; faltante/invalid -> `unknown`)
  - `ts`
  - `reason`
  - `run_id` (nullable)
  - `symbol` (nullable)
  - `source_log_id` (unique cuando viene de logs)
- `add_log(..., event_type=\"breaker_triggered\")` inserta/actualiza `breaker_events` en tiempo real.
- Backfill legacy desde `logs` disponible en init (`_backfill_breaker_events_from_logs`).

## Lo que sigue faltando (verdad actual)

- Virtualizacion adicional en otras tablas grandes (D2 de comparador ya virtualizado)
- Orden server-side multi-columna (hoy sigue siendo 1 clave por request, aunque ya se puede ordenar por click en UI)
- Endpoints de shortlist por batch (CRUD completo; hoy hay guardado + lectura en detalle de batch)
- Smoke/E2E frontend automatizados
- UI de experimentos MLflow (si se habilita capability)
- Reportes avanzados en detalle de corrida (heatmap mensual, rolling Sharpe, distribuciones)
- Endpoints catalogo para `rerun_exact`, `clone_edit`, `export` unificado por `run_id`
- Adaptador remoto especifico de proveedor financiero pendiente (el motor remoto generico ya esta implementado)
- Fee/Funding provider multi-exchange avanzado pendiente (hoy Binance + Bybit base + fallback con snapshots)
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

