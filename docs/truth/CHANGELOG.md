# CHANGELOG (Truth Layer)

## 2026-02-27

### Opcion B + Opcion C (hotfix calibracion sin refactor masivo)
- `FundamentalsCreditFilter` separado en:
  - `get_fundamentals_snapshot_cached(...)` (snapshot crudo)
  - `evaluate_credit_policy(...)` (decision por modo)
- Fix leakage por modo:
  - mismo snapshot puede dar decision distinta segun `BACKTEST` vs `LIVE/PAPER`.
  - `allow_trade` ya no depende de cache de decision.
- Backtest equities sin fundamentals preexistentes:
  - en `BACKTEST` no aborta por 400; corre con `fundamentals_missing`, `fundamentals_quality=ohlc_only`, `promotion_blocked=true`.
  - en `LIVE/PAPER` se mantiene fail-closed.
- `/api/v1/bots` sin N+1:
  - nuevo batch `get_bots_overview(...)` para KPIs/logs/kills por bot.
  - `list_bot_instances` usa overview batch interno.
- Kills correctamente scopeados por `bot_id + mode`:
  - nueva tabla `breaker_events` ya conectada al flujo runtime (`add_log` con `breaker_triggered`).
  - `mode` faltante pasa a `unknown` (no se imputa a `paper`).
- Tests nuevos/ajustados:
  - `test_fundamentals_mode_leakage.py`
  - `test_fundamentals_credit_filter.py` (policy nueva BACKTEST/LIVE)
  - `test_web_live_ready.py` (equities ohlc_only + kills por bot/mode)
- Suite focal corrida:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_mode_leakage.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_web_live_ready.py::test_event_backtest_engine_runs_for_crypto_forex_equities rtlab_autotrader/tests/test_web_live_ready.py::test_bots_multi_instance_endpoints rtlab_autotrader/tests/test_web_live_ready.py::test_bots_overview_scopes_kills_by_bot_and_mode rtlab_autotrader/tests/test_web_live_ready.py::test_bots_live_mode_blocked_by_gates -q`
  - resultado: `11 passed`.

### Calibracion real (fundamentals + costos)
- Nueva policy `config/policies/fundamentals_credit_filter.yaml` con scoring, thresholds, reglas por instrumento y snapshots.
- Nuevo modulo `rtlab_core/fundamentals/credit_filter.py` con evaluacion auditable:
  - `fund_score`, `fund_status`, `allow_trade`, `risk_multiplier`, `explain[]`
  - cache/snapshot con TTL y persistencia en SQLite.
- Catalogo SQLite extendido:
  - nueva tabla `fundamentals_snapshots`
  - columnas en `backtest_runs`: `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`.
- Wiring en backend (`app.py` + `mass_backtest_engine.py`):
  - run metadata/provenance ahora incluye fundamentals
  - bloqueo fail-closed cuando fundamentals enforced retorna `allow_trade=false`.
- Cost model reforzado:
  - `FeeProvider` intenta endpoints Binance reales (`/api/v3/account/commission`, `/sapi/v1/asset/tradeFee`) + fallback seguro
  - `FundingProvider` intenta `/fapi/v1/fundingRate` + fallback seguro
  - `SpreadModel` agrega estimador `roll` cuando no hay BBO ni spread explicito.
- Ajuste de gates default:
  - `dsr_min` en rollout offline pasa a `0.95`.
- Tests corridos:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `7 passed`.

### Calibracion real (bloque siguiente: fundamentals con fuente local)
- `FundamentalsCreditFilter` ahora puede autoleer snapshot local JSON cuando `source` llega en `unknown/auto/local_snapshot`.
- Nueva configuracion en policy:
  - `data_source.mode`
  - `data_source.local_snapshot_dir`
  - `data_source.auto_load_when_source_unknown`
- El filtro rellena `asof_date` y metricas financieras desde snapshot local y agrega traza:
  - `explain.code = DATA_SOURCE_LOCAL_SNAPSHOT`
  - `source_ref.source_path`
- Paths soportados para snapshot:
  - `user_data/fundamentals/{market}/{symbol}.json`
  - y fallback legacy en `user_data/data/fundamentals/{market}/{symbol}.json`
- Test agregado:
  - `test_fundamentals_autoload_local_snapshot_for_equities`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `8 passed`.

### Calibracion real (bloque 2/5: fundamentals remoto + fallback local)
- `FundamentalsCreditFilter` ahora soporta `remote_json` configurable por policy/env:
  - `data_source.remote.enabled`
  - `base_url_env/base_url`
  - `endpoint_template` con placeholders `{market}`, `{symbol}`, `{exchange}`, `{instrument_type}`
  - timeout y header de auth por ENV.
- Flujo de resolucion de fuente:
  - `source=auto|unknown|runtime_policy|research_batch` -> intenta remoto y luego fallback local
  - `source=remote` -> solo remoto (si falla queda evidencia y aplica fail-closed segun policy)
  - `source=local_snapshot` -> solo local.
- En metadata/explain se agrega trazabilidad de origen:
  - `source_ref.source_url`
  - `source_ref.source_http_status`
  - `DATA_SOURCE_REMOTE_SNAPSHOT` / `DATA_SOURCE_REMOTE_ERROR`.
- Wiring actualizado para usar `source=auto` en:
  - `rtlab_core/web/app.py`
  - `rtlab_core/src/research/mass_backtest_engine.py`
- Test nuevo:
  - `test_fundamentals_autoload_remote_snapshot_for_equities`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `9 passed`.

### Calibracion real (bloque 3/5: costos multi-exchange base)
- `FeeProvider` ahora usa fallback por exchange desde policy:
  - `fees.per_exchange_defaults` (binance/bybit/okx)
  - override opcional por ENV (`{EXCHANGE}_MAKER_FEE`, `{EXCHANGE}_TAKER_FEE`).
- `FundingProvider` agrega fetch para Bybit perps:
  - endpoint `/v5/market/funding/history` (publico)
  - parsea `fundingRate` y persiste snapshot.
- Se mantiene fail-safe:
  - si endpoint no responde, guarda snapshot con fallback y trazabilidad en payload.
- Policy actualizada:
  - `config/policies/fees.yaml` incluye `per_exchange_defaults`.
- Tests nuevos:
  - `test_cost_model_uses_exchange_fee_fallback_for_bybit`
  - `test_cost_model_fetches_bybit_funding_when_perp`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Calibracion real (bloque 4/5: promotion fail-closed con trazabilidad)
- `validate_promotion` ahora exige constraints adicionales en corridas de catalogo:
  - `cost_snapshots_present` (`fee_snapshot_id` + `funding_snapshot_id`)
  - `fundamentals_allow_trade` (`fund_allow_trade=true`)
- `_build_rollout_report_from_catalog_row` expone metadata de trazabilidad en report de rollout:
  - `market`, `exchange`
  - `fee_snapshot_id`, `funding_snapshot_id`
  - `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`
- Si el run viene de legado (`legacy_json_id`), se completa metadata faltante desde catalogo para no perder trazabilidad en promotion.
- Tests actualizados:
  - `test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke` ahora verifica presencia de ambos checks nuevos.
- Suites corridas:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke rtlab_autotrader/tests/test_web_live_ready.py::test_runs_batches_catalog_endpoints_smoke -q`
  - resultado: `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Calibracion real (bloque 5/5: admin multi-bot/live + cierre)
- `BotInstance` metrics reforzadas en backend (`_bot_metrics`):
  - agrega breakdown por modo (`shadow/paper/testnet/live`) con `trade_count`, `winrate`, `net_pnl`, `avg_sharpe`, `run_count`.
  - agrega kills reales desde logs `module=risk`, `type=breaker_triggered`:
    - `kills_total` por modo del bot
    - `kills_24h` por modo
    - `kills_global_total`, `kills_global_24h`
    - `kills_by_mode`, `kills_by_mode_24h`, `last_kill_at`.
- `kill switch` ahora guarda `mode` en payload del log para trazabilidad de kills por entorno.
- Endpoints de bots endurecidos para LIVE:
  - `POST /api/v1/bots`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/bulk-patch`
  - todos bloquean `mode=live` si `live_can_be_enabled(evaluate_gates("live"))` no pasa.
- UI:
  - `strategies/page.tsx`: tabla de bots ahora muestra `runs` debajo de `trades` y `kills 24h`.
  - `execution/page.tsx`:
    - botón masivo `Modo LIVE` bloqueado cuando checklist LIVE no está en PASS
    - tabla de operadores agrega columnas `Sharpe` y `Kills (total/24h)`.
- Tipos frontend actualizados en `src/lib/types.ts` para nuevos campos de métricas de bot.
- Tests:
  - nuevo `test_bots_live_mode_blocked_by_gates`
  - se mantiene `test_bots_multi_instance_endpoints`.
- Suites corridas:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py::test_bots_multi_instance_endpoints rtlab_autotrader/tests/test_web_live_ready.py::test_bots_live_mode_blocked_by_gates rtlab_autotrader/tests/test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke -q`
  - resultado: `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Backtests / Runs (bloque continuo de UX + escala)
- Runs table ahora permite ordenar haciendo click en cabeceras (Run ID, Fecha, Estrategia, Ret%, MaxDD, Sharpe, PF, WinRate, Trades, Expectancy) con toggle asc/desc.
- Se agregó `sort_by=winrate` en backend (`BacktestCatalogDB.query_runs`) para ranking directo por winrate.
- Se eliminó el límite rígido de `5` en selección legacy (`selectedRuns`) para no recortar comparaciones manuales.
- Parser de errores UI reforzado (`uiErrMsg`) para evitar renderizar `[object Object]` y mostrar mensajes útiles (`detail/message/error/cause`).
- Tests actualizados: `test_backtest_catalog_db.py` valida ordenamiento por `winrate`.

### Research Batch (shortlist BX persistente)
- Backend:
  - nuevo `BacktestCatalogDB.patch_batch(...)` para actualizar `best_runs_cache`/summary del batch.
  - nuevo endpoint `POST /api/v1/batches/{batch_id}/shortlist` (admin) para guardar shortlist de variantes/runs.
- Frontend (`Backtests > Research Batch`):
  - botones `Guardar shortlist BX` y `Cargar shortlist BX`.
  - restauración automática de shortlist al seleccionar un batch.
  - en tabla de Batches se muestra columna `Shortlist` (cantidad guardada) y acción `Cargar shortlist`.
- Tests:
  - `test_web_live_ready.py::test_batch_shortlist_save_and_load`
  - `test_backtest_catalog_db.py` cubre patch de batch con `best_runs_cache`.

### Backtests / Strategies (bloque UX escala)
- `Backtests / Runs` D2 (`Comparison Table Pro`) ahora usa virtualizacion por ventana visible:
  - contenedor con scroll vertical fijo
  - render de filas visibles + overscan
  - espaciadores superior/inferior para mantener altura total
  - contador de ventana (`X-Y de N`) para trazabilidad visual.
- `Strategies` compactado para escalar mejor con 50+ estrategias:
  - filas mas bajas (`align-middle`, menor padding)
  - acciones visibles reducidas en fila (selector compacto + menu `Mas`)
  - menor ancho minimo de columna de acciones.

### Operaciones / Trades (Bloque 3)
- Tabla de operaciones ahora tiene orden configurable (`timestamp`, `PnL`, `estrategia`, `simbolo`, `modo`, `fees`, `slippage`, `qty`).
- Seleccion masiva por checkbox:
  - seleccionar/quitar pagina
  - limpiar seleccion
  - borrar operaciones seleccionadas (admin).
- Borrado filtrado con `preview` (`dry_run`) antes de ejecutar borrado real.
- Resumen operacional extendido:
  - panel por `modo + entorno` clickable para aplicar filtros rapidos
  - `Top estrategias` ahora permite aplicar filtro directo por estrategia.
- En tabla de trades, `strategy_id` es clickable para filtrar al instante.

### Ejecucion / Live Admin (Bloque 4)
- Nuevo panel de **estrategias primarias por modo** dentro de `Ejecucion`:
  - selector y guardado rapido de primaria para `PAPER`, `TESTNET` y `LIVE`
  - usa endpoint existente `POST /api/v1/strategies/{id}/primary` (sin API nueva).
- Modo `LIVE` mas seguro y explicito en UI:
  - muestra bloqueos concretos de checklist (`keys`, `connector`, `gates`)
  - boton `Aplicar modo` se bloquea si `LIVE` no esta listo.
- Administracion de operadores mas intuitiva:
  - atajos de seleccion masiva `Seleccionar activos` y `Seleccionar modo runtime`
  - mensaje contextual que separa runtime global vs operadores de aprendizaje.

## 2026-02-26

### RTLAB Strategy Console (Bloque 1 - Policies numericas)
- Agregada carpeta `config/policies/`
- `gates.yaml` con numeros explicitos para `PBO/CSCV`, `DSR`, `walk_forward`, `cost_stress`, calidad minima de trades
- `microstructure.yaml` con Order Flow L1 (`VPIN`, spread_guard, slippage_guard, volatility_guard)
- `risk_policy.yaml` con soft/hard kill por `bot/strategy/symbol`
- `beast_mode.yaml` con limites (`5000 trials`, concurrencia, budget governor)
- `fees.yaml` con TTLs y fallback maker/taker

### RTLAB Strategy Console (Bloques 2-7)
- Backend: `GET /api/v1/config/policies` + resumen numerico de policies
- Backend: `GET /api/v1/config/learning` extendido con `numeric_policies_summary`
- Research Batch: persistencia de `policy_snapshot` / `policy_snapshot_summary`
- Cost model baseline:
  - `FeeProvider`, `FundingProvider`, `SpreadModel`, `SlippageModel`
  - snapshots persistentes en SQLite
  - metadata de costos/snapshots por `BT-*`
- Order Flow L1 (VPIN proxy desde OHLCV) en motor masivo + debug UI + flags `MICRO_SOFT_KILL` / `MICRO_HARD_KILL`
- Gates avanzados en research masivo (PBO/DSR/WF/cost stress/min trade quality) con PASS/FAIL visible y bloqueo fail-closed de `mark-candidate`
- Modo Bestia (fase 1):
  - scheduler local con cola de jobs, concurrencia y budget governor
  - endpoints `/api/v1/research/beast/start|status|jobs|stop-all|resume`
  - panel UI de Modo Bestia en `Backtests`

### UI/UX Research-first (Bloques 1-6)
- Fix del falso `WS timeout` en diagnostico SSE (`/api/events`)
- `Backtests / Runs`: paginacion obligatoria (30/60/100), labels mas claros, empty state con CTA
- `Settings > Rollout / Gates`: empty states accionables en offline gates / compare / fase / telemetria
- `Portfolio`: empty states guiados + historial con timestamp/tipo/detalle
- `Riesgo`: foco en riesgo (sin duplicar gates) + explicacion de correlacion/concentracion
- `Ejecucion`: panel `Trading en Vivo (Paper/Testnet/Live) + Diagnostico` con checklist `Live Ready`, conectores y controles admin
- `Trades` y `Alertas`: filtros con labels en espanol + empty states guiados
- `Backtests`: `Detalle de Corrida` con pestanas estilo Strategy Tester
- `Backtests`: `Quick Backtest Legacy` marcado como deprecado y colapsado

### Documentacion
- `docs/UI_UX_RESEARCH_FIRST_FINAL.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`
