# CHANGELOG (Truth Layer)

## 2026-02-28

### Bloque 2: backtest por strategy_id (sin refactor masivo)
- `BacktestEngine/StrategyRunner` ya no usa una unica senal para todas las estrategias.
- Se agrego dispatcher por familia de `strategy_id`:
  - `trend_pullback_orderflow_v2`
  - `breakout_volatility_v2`
  - `meanreversion_range_v2`
  - `trend_scanning_regime_v2`
  - `defensive_liquidity_v2`
- Fallback conservador:
  - cualquier `strategy_id` no reconocido sigue usando `trend_pullback` para mantener compatibilidad.
- Tests nuevos:
  - `rtlab_autotrader/tests/test_backtest_strategy_dispatch.py`
    - verifica que el mismo contexto produce decisiones distintas segun `strategy_id`.
    - valida ruteo de `trend_scanning` y gate de `obi_topn` en `defensive_liquidity`.
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> `4 passed`
  - `python -m pytest rtlab_autotrader/tests/test_backtest_annualization.py -q` -> `2 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "event_backtest_engine_runs_for_crypto_forex_equities or backtest_orderflow_toggle_metadata_and_gating" -q` -> `1 passed`

### Bloque 3: min_trades_per_symbol real en gates masivos
- `MassBacktestEngine` ahora calcula y persiste en `summary`:
  - `trade_count_by_symbol_oos`
  - `min_trades_per_symbol_oos`
- Gate `min_trade_quality` actualizado:
  - ya no mira solo `trade_count_oos`
  - ahora exige simultaneamente:
    - `trade_count_oos >= min_trades_per_run`
    - `min_trades_per_symbol_oos >= min_trades_per_symbol`
  - expone detalle en `gates_eval.checks.min_trade_quality`:
    - `run_trade_pass`
    - `symbol_trade_pass`
    - `symbols_below_min_trades`
- Compatibilidad hacia atras:
  - si faltan conteos por simbolo en corridas legacy, usa fallback `UNSPECIFIED=trade_count_oos`.
- Tests agregados:
  - `test_advanced_gates_fail_when_min_trades_per_symbol_is_below_threshold`
  - `test_advanced_gates_pass_when_min_trades_per_symbol_meets_threshold`
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `9 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`

### Bloque 4: fuente canonica de gates unificada (config > knowledge)
- `build_learning_config_payload` ahora toma gates desde `config/policies/gates.yaml` como fuente primaria.
- Si `safe_update.gates_file` en knowledge difiere de la canónica, se agrega warning y se fuerza la fuente canónica.
- `gates_summary` en `/api/v1/config/learning` ahora expone:
  - `source` (ruta canónica efectiva)
  - flags `pbo_enabled` / `dsr_enabled` derivados de política canónica.
- `LearningService` para recomendaciones usa thresholds de gates canónicos:
  - `pbo_max` desde `reject_if_gt`
  - `dsr_min` desde `min_dsr`
  - fallback explícito a `knowledge/policies/gates.yaml` solo si no existe config.
- `MassBacktestEngine` añade trazabilidad de política en artefactos:
  - `knowledge_snapshot.gates_canonical`
  - `knowledge_snapshot.gates_source`
- Tests agregados/ajustados:
  - `test_learning_service_uses_canonical_config_gates_thresholds`
  - `test_config_learning_endpoint_reads_yaml_and_exposes_capabilities` (assert de `gates_summary.source` y `safe_update.gates_file`)
- Validación ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "config_learning_endpoint_reads_yaml_and_exposes_capabilities or config_policies_endpoint_exposes_numeric_policy_bundle" -q` -> `2 passed`
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `10 passed`

### Bloque 5: UI Research Batch con calidad por simbolo visible
- `Backtests > Research Batch` ahora muestra en leaderboard:
  - columna `Mín trades/símbolo`
  - badge de mínimo requerido cuando existe en `gates_eval.min_trade_quality`.
- Drilldown de variante agrega:
  - `Mín trades/símbolo` con umbral requerido
  - detalle `Trades OOS por símbolo` (mapa agregado).
- Tipado frontend actualizado:
  - `MassBacktestResultRow.summary.trade_count_by_symbol_oos`
  - `MassBacktestResultRow.summary.min_trades_per_symbol_oos`
- Validación ejecutada:
  - `npm --prefix rtlab_dashboard run test -- src/lib/auth.test.ts src/lib/security.test.ts` -> `11 passed`
  - `npm --prefix rtlab_dashboard run lint` -> `0 errores` (warnings existentes no bloqueantes)

### Bloque 6: politica canonica para `enable_surrogate_adjustments` (fail-closed)
- `MassBacktestEngine` ahora resuelve surrogate por policy con trazabilidad:
  - nuevo resolver `_resolve_surrogate_adjustments(cfg)` con:
    - `enabled_effective`
    - `allowed_execution_modes`
    - `reason`
    - `promotion_blocked_effective`
    - `evaluation_mode`
- Policy canónica agregada en `config/policies/gates.yaml`:
  - `gates.surrogate_adjustments.enabled=false`
  - `allow_request_override=false`
  - `allowed_execution_modes=["demo"]`
  - `promotion_blocked=true`
- El motor ya no usa `cfg.enable_surrogate_adjustments` de forma directa.
- Si surrogate queda activo (solo `demo` por policy), la variante:
  - se etiqueta `evaluation_mode=engine_surrogate_adjusted`
  - falla `gates_eval.checks.surrogate_adjustments`
  - queda `promotable=false` y `recommendable_option_b=false` (fail-closed para promotion).
- Trazabilidad agregada en artifacts/manifest/summary:
  - `summary.surrogate_adjustments`
  - `manifest.surrogate_adjustments`
  - flags de catalogo `SURROGATE_ADJUSTMENTS` y `EVALUATION_MODE`.
- Tests agregados:
  - `test_surrogate_adjustments_policy_requires_allowed_execution_mode`
  - `test_surrogate_adjustments_request_override_rejected_by_default`
  - `test_advanced_gates_block_promotion_when_surrogate_adjustments_enabled`
  - `test_run_job_applies_surrogate_only_in_demo_mode_and_blocks_promotion`
- Validación ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `13 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`

### Bloque 7: benchmark reproducible de `/api/v1/bots` (100 bots)
- Script nuevo: `scripts/benchmark_bots_overview.py`
  - seed controlado de bots/logs/breakers.
  - benchmark con `FastAPI TestClient` sobre endpoint real `/api/v1/bots`.
  - reporte markdown automatico en `docs/audit/`.
- Evidencia generada:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_20260228.md`
  - resultado: `p95=280.875ms` con `100 bots` y `200 requests` (objetivo `< 300ms`: PASS).
- Smoke adicional:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_SMOKE_20260228.md`.

### Bloque 8: benchmark remoto de `/api/v1/bots` (entorno desplegado)
- `scripts/benchmark_bots_overview.py` extendido con modo remoto:
  - `--base-url`, `--auth-token` (o login con `--username/--password`).
  - `--timeout-sec`.
  - `--min-bots-required` (default `100`).
- Criterio estricto de evidencia:
  - si `/api/v1/bots` devuelve menos bots que el minimo requerido, el reporte marca:
    - estado `NO_EVIDENCIA`
    - `target_pass=false`
    - motivo explicito en `no_evidencia_reason`.
- Smoke local de regresion del script actualizado:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_SMOKE2_20260228.md`.

### Bloque 9: ejecucion real benchmark remoto `/api/v1/bots` (Railway)
- Corrida remota ejecutada contra:
  - `https://bot-trading-ia-production.up.railway.app`
- Evidencia:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md`
- Resultado:
  - `p50=977.579ms`
  - `p95=1663.014ms`
  - `p99=1923.523ms`
  - objetivo `p95 < 300ms`: **FAIL**
- Estado de evidencia:
  - **NO EVIDENCIA** para benchmark objetivo de 100 bots, porque `/api/v1/bots` devolvio `1` bot (minimo requerido `100`).

### Bloque 10: cache TTL en `/api/v1/bots` + invalidacion explicita
- Backend:
  - `GET /api/v1/bots` ahora usa cache in-memory con TTL (`BOTS_OVERVIEW_CACHE_TTL_SEC`, default `10s`).
  - invalidacion explicita del cache en:
    - `POST /api/v1/bots`
    - `PATCH /api/v1/bots/{bot_id}`
    - `POST /api/v1/bots/bulk-patch`
  - `add_log(event_type=\"breaker_triggered\")` invalida cache para reflejar kills por bot/mode sin esperar TTL.
- Test de regresion agregado:
  - `test_bots_overview_cache_hit_and_invalidation_on_create`
  - verifica cache hit en GET consecutivos e invalidacion al crear bot.
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_multi_instance_endpoints or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_scopes_kills_by_bot_and_mode or bots_live_mode_blocked_by_gates" -q` -> `4 passed`.
- Benchmark local posterior al cambio:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260228_AFTER_CACHE.md`
  - resultado: `p50=31.453ms`, `p95=35.524ms`, `p99=37.875ms` (objetivo `<300ms`: PASS).
- Pendiente:
  - deploy del backend en Railway y rerun remoto para medir impacto real en prod.

### Bloque 11: validacion remota post-deploy `/api/v1/bots` (Railway)
- Push realizado a `main` con commit:
  - `11544ae`
- Benchmark remoto post-deploy (sin reseed) ejecutado:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY.md`
  - resultado: `p50=881.590ms`, `p95=1032.039ms`, `p99=1236.711ms` (FAIL `<300ms`)
  - estado evidencia: `NO EVIDENCIA` (la instancia devolvio `1` bot, minimo requerido `100`).
- Seeding remoto aplicado de nuevo a `100` bots:
  - script: `scripts/seed_bots_remote.py`
  - resultado: `bots finales=100`.
- Benchmark remoto post-deploy con 100 bots:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY_100BOTS.md`
  - resultado: `p50=1265.135ms`, `p95=1458.513ms`, `p99=1519.641ms` (FAIL `<300ms`).
- Conclusion del bloque:
  - el cache TTL local mejora benchmark local pero no alcanza objetivo p95 en Railway con 100 bots;
  - se requiere siguiente ronda de optimizacion estructural en backend/storage para overview batch.

### Auditoria comité + hardening adicional
- Seguridad:
  - `current_user` ahora ignora headers internos si no existe `INTERNAL_PROXY_TOKEN` válido (fail-closed en todos los entornos).
  - login backend con rate-limit/lockout por `IP+user`:
    - `10` intentos en `10` min -> `429`
    - lockout `30` min tras `20` fallos.
  - BFF (`[...path]` y `events-stream`) ahora falla con `500` explícito si falta `INTERNAL_PROXY_TOKEN`.
- Config:
  - `.env.example` backend y frontend actualizados con `INTERNAL_PROXY_TOKEN`.
- Auditoría:
  - nuevos artefactos `docs/audit/AUDIT_REPORT_20260228.md`, `docs/audit/AUDIT_FINDINGS_20260228.md`, `docs/audit/AUDIT_BACKLOG_20260228.md`.
- Bibliografía:
  - nuevo `scripts/biblio_extract.py` (indexación SHA256 + extracción incremental a txt).
  - nuevo `docs/reference/biblio_txt/.gitignore`.
  - `docs/reference/BIBLIO_INDEX.md` regenerado con hashes.
- Seguridad documental:
  - `docs/SECURITY.md` reescrito con threat model mínimo, checklist y comandos de auditoría.
- Test agregado:
  - `test_auth_login_rate_limit_and_lock_guard`.

### Seguridad + Runtime + CI (T1 + T2 + T4 + T6 + T9)
- T1 auth bypass mitigado:
  - backend ya no confia ciegamente en `x-rtlab-role/x-rtlab-user`.
  - ahora exige `x-rtlab-proxy-token` valido contra `INTERNAL_PROXY_TOKEN`.
  - BFF (`[...path]` + `events-stream`) envia el token interno desde ENV.
- T2 defaults peligrosos endurecidos:
  - fail-fast en boot cuando `NODE_ENV=production` y hay defaults en admin/viewer o `AUTH_SECRET` corto.
  - `G2_AUTH_READY` actualizado con `no_default_credentials`.
- T4 runtime simulado explicitado:
  - estado del bot persistido con `runtime_engine`.
  - nuevo gate `G9_RUNTIME_ENGINE_REAL`.
  - `POST /api/v1/bot/mode` bloquea `LIVE` si `runtime_engine != real`.
  - `/api/v1/status` y `/api/v1/health` exponen `runtime_engine/runtime_mode`.
- T6 annualizacion por timeframe:
  - `ReportEngine.build_metrics` ya no usa constante fija 5m para Sharpe/Sortino.
  - factor anual se calcula por timeframe real (`1m/5m/10m/15m/1h/1d` + parse generico).
- T9 CI frontend agregado:
  - nuevo job `frontend` en GitHub Actions con `npm ci`, typecheck, vitest y build.
- Tests agregados/ajustados:
  - `test_web_live_ready.py`:
    - `test_internal_headers_require_proxy_token`
    - `test_auth_validation_fails_in_production_with_default_credentials`
    - `test_live_mode_blocked_when_runtime_engine_is_simulated`
  - `test_backtest_annualization.py` (factor y scaling de Sharpe por timeframe).

### Ajustes auditoria comite (quick wins adicionales)
- `GET /api/v1/gates` ahora requiere auth (`current_user`) para evitar exposicion publica del checklist.
- `BacktestEngine` bloquea `validation_mode=purged-cv|cpcv` en Quick Backtest con error explicito (fail-closed; sin `hook_only` silencioso).
- `MassBacktestEngine` desactiva surrogate adjustments por defecto:
  - nuevo comportamiento default `evaluation_mode=engine_raw`.
  - surrogate solo segun policy canónica (`gates.surrogate_adjustments`) y modo permitido.
- `GateEvaluator` migra fuente primaria de thresholds a `config/policies/gates.yaml` (fallback `knowledge/policies/gates.yaml`).
- `GateEvaluator` pasa a fail-closed para PBO/DSR cuando policy los marca como habilitados y faltan en el reporte.

### Bibliografia
- Nuevo `docs/reference/BIBLIO_INDEX.md` con las 20 fuentes externas informadas.
- Nuevo `docs/reference/biblio_raw/.gitignore` para trabajo local sin subir PDFs/TXT al repo.

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
