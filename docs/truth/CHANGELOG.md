# CHANGELOG (Truth Layer)

## 2026-03-05

### Remote protected checks (rerun estricto)
- Workflow `Remote Protected Checks (GitHub VM)` re-ejecutado con defaults y `strict=true`:
  - run `22704105623` -> `success`.
- Resultado canonico del reporte remoto:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- Impacto operativo:
  - se confirma continuidad del cierre no-live en verde;
  - LIVE permanece en `NO GO` hasta cierre de runtime real end-to-end y activacion final de APIs live.

### AP-BOT-1016 (guard fail-closed para submit en `live`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nueva variable `LIVE_TRADING_ENABLED` (default `false`);
  - `RuntimeBridge._maybe_submit_exchange_runtime_order(...)` bloquea submit remoto en `mode=live` cuando `LIVE_TRADING_ENABLED=false`;
  - retorna `reason=live_trading_disabled` + `error=LIVE_TRADING_ENABLED=false` para trazabilidad operativa.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_flat_skips_remote_submit or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle or live_skips_submit_when_live_trading_disabled" -q` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`6 passed`).
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1016_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1017 (telemetria de `submit_reason` en runtime)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo estado `runtime_last_remote_submit_reason` persistido por ciclo;
  - `_maybe_submit_exchange_runtime_order(...)` retorna `reason=submitted` cuando el envio remoto fue exitoso.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - assertions nuevas para `runtime_last_remote_submit_reason` en casos:
    - submit exitoso testnet (`submitted`);
    - bloqueo live por flag (`live_trading_disabled`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_meanreversion_submits_sell or live_skips_submit_when_live_trading_disabled or strategy_signal_flat_skips_remote_submit or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1017_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1018 (revalidacion benchmark remoto + fix summary workflow)
- Operativo:
  - ejecutado `Remote Bots Benchmark (GitHub VM)` con defaults:
    - run `22706414197` -> `success`.
  - evidencia registrada en:
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_GHA_22706414197_20260305.md`.
  - metricas clave:
    - `p95_ms=184.546`
    - `server_p95_ms=0.07`
    - `rate_limit_retries=0`
    - objetivo `p95<300ms`: `PASS`.
- CI workflow:
  - `/.github/workflows/remote-benchmark.yml`:
    - `Build summary` pasa regex de `grep -E` a comillas simples para evitar evaluacion de backticks como comandos shell.

### AP-BOT-1019 (limpieza de `runtime_last_remote_submit_reason`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - limpia `runtime_last_remote_submit_reason` al salir de runtime real y cuando `exchange_ready` falla.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "live_skips_submit_when_live_trading_disabled or clears_submit_reason_when_runtime_exits_real_mode or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1019_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1020 (reconciliacion avanzada `PENDING_CANCEL` / `EXPIRED_IN_MATCH`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `NEW/PENDING_CANCEL` ya no pisa `PARTIALLY_FILLED` cuando existe fill parcial;
  - si `filled_qty>=qty`, cierra terminal en `FILLED`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - nuevo `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "keeps_absent_open_order_open_when_order_status_is_new or keeps_partial_state_when_order_status_is_pending_cancel or updates_absent_open_order_partial_fill_from_order_status or marks_absent_open_order_expired_in_match_terminal or marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`5 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1020_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1021 (revalidacion remota protected checks post runtime)
- Operativo:
  - ejecutado `Remote Protected Checks (GitHub VM)` con defaults y `strict=true`:
    - run `22731722376` -> `success`.
  - evidencia registrada en:
    - `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.
- Campos de cierre:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`

### AP-BOT-1022 (refresh de closeout no-live)
- `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`:
  - agregado refresh de evidencia del dia (`2026-03-05`) con runs:
    - benchmark `22706414197` (`PASS`),
    - protected checks `22731722376` (`PASS`).
- Estado operativo consolidado:
  - no-live/testnet se mantiene `GO`;
  - LIVE permanece `NO GO` por decision operativa (fase final).

## 2026-03-04

### AP-8001 (BFF fail-closed de mock fallback)
- `rtlab_dashboard/src/lib/security.ts`:
  - agregado `isProtectedRuntimeEnv` (`NODE_ENV=production` o `APP_ENV in {staging, production, prod}`).
  - agregado `shouldFallbackToMockOnBackendError` con politica fail-closed:
    - en entornos protegidos siempre `false`;
    - con `USE_MOCK_API=false`, siempre `false`;
    - solo permite fallback en no-protegido + flag `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=true`.
- `rtlab_dashboard/src/app/api/[...path]/route.ts`:
  - elimina helper local y usa regla centralizada.
- `rtlab_dashboard/src/lib/events-stream.ts`:
  - fallback a stream mock en error de backend ahora usa regla centralizada.
- `rtlab_dashboard/src/lib/security.test.ts`:
  - nuevos tests para bloqueo en `production`/`staging` y comportamiento en `local`.
- Evidencia:
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).

### AP-8002 (security CI: instalacion robusta de gitleaks)
- `.github/workflows/security-ci.yml`:
  - `actions/checkout@v4` pasa a `fetch-depth: 0` para evitar falsos positivos de `gitleaks` al usar baseline historica sobre clones shallow.
  - `setup-python` alineado a `3.11` (coherente con workflows operativos remotos).
  - reemplazada instalacion via script `master/install.sh` por descarga de release oficial:
    - `gitleaks_8.30.0_linux_x64.tar.gz`
  - agregado `curl` con retries y timeout para runners GitHub.
  - agregado fallback a install script versionado (`v8.30.0`) si la descarga tarball falla.
  - agregado check explicito de binario ejecutable (`$RUNNER_TEMP/bin/gitleaks`) con error claro si no queda instalado.
  - export `PATH` en el mismo step antes de `gitleaks version` (evita falso fail por `GITHUB_PATH` no aplicado aun).
  - extraccion directa a `RUNNER_TEMP/bin` y validacion de `gitleaks version`.
  - `scripts/security_scan.sh` ahora toma baseline canónica en `docs/security/gitleaks-baseline.json` (o `GITLEAKS_BASELINE_PATH`), evitando depender de archivos `artifacts/` no versionados en CI.
- Nuevo archivo versionado:
  - `docs/security/gitleaks-baseline.json` (redactado).
- Resultado esperado:
  - reducir fallos espurios en `Install security tooling` y en `Run security scan (strict)` por baseline/history mismatch, facilitando cierre de `FM-SEC-004` al rerun del workflow.
- Evidencia de cierre:
  - GitHub Actions `Security CI` run `22697627615` en `success` (job `security` id `65807494809`).
  - `FM-SEC-004` actualizado a `CERRADO` en `docs/audit/FINDINGS_MASTER_20260304.md`.

### AP-8007 (unificacion de thresholds de gates)
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - eliminado fallback de thresholds a `knowledge/policies/gates.yaml`;
  - si no hay config valida, se usa `default_fail_closed` (`pbo_max=0.05`, `dsr_min=0.95`).
- `rtlab_autotrader/rtlab_core/rollout/gates.py`:
  - `GateEvaluator` usa `config/policies/gates.yaml` como fuente canonica;
  - en ausencia/error de config, marca `source_mode=default_fail_closed` y exige `pbo/dsr`.
- Test agregado:
  - `rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).

### AP-8011 (optimizacion incremental de `/api/v1/bots`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - evita `learning_service.load_all_recommendations()` en cada request cuando hay cache hit;
  - filtra indexado de `runs` por `strategy_ids` presentes en pools de bots;
  - limita runs indexados por `(strategy_id, mode)` con `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE` (default `250`);
  - expone nuevos campos de perfilado interno en debug: `runs_indexed`, `runs_skipped_outside_pool`, `max_runs_per_strategy_mode`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Nota:
  - requiere rerun remoto de benchmark para verificar impacto final de `p95` en entorno productivo.

### AP-8003 (runtime reconcile: open orders + cierre de ausentes)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_reconcile` usa `OMS.open_orders()` como espejo local para comparar contra `GET /api/v3/openOrders`.
  - agregado cierre local de ordenes abiertas ausentes en exchange luego de `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`).
  - evita desync falso por ordenes locales ya cerradas (`FILLED`/terminal) fuera de `openOrders`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`.
  - nuevo `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).

### AP-8012 (`breaker_events` strict por defecto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `breaker_events_integrity(..., strict=True)` cambia a fail-closed por defecto.
  - endpoint `GET /api/v1/diagnostics/breaker-events` ahora usa `strict=true` por defecto.
- `scripts/ops_protected_checks_report.py`:
  - `--strict` pasa a default `true`.
  - nuevo flag `--no-strict` para override explícito.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - ajuste de pruebas para default estricto + override no estricto.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.

### Cleanroom docs + staging no-live (docops/devops)
- Limpieza de documentacion vigente/historica:
  - movidos a `docs/_archive/*`: `BACKTESTS_RESEARCH_SYSTEM_FINAL.md`, `MASS_BACKTEST_DATA.md`, `research_mass_backtests.md`, `research_stack.md`, `FINAL_RELEASE_REPORT.md`, `DEPENDENCIES_COMPAT.md`, `UI_UX_RESEARCH_FIRST_FINAL.md`, `CONVERSACION_SCREENSHOTS_REFERENCIA_UNIVERSOS_COSTOS_GATES_EXCHANGES.txt`.
  - agregado `docs/_archive/README_ARCHIVE.md` con disclaimer de no vigencia.
- Indices nuevos para lectura canonica:
  - `docs/START_HERE.md`
  - `docs/audit/INDEX.md`
- Seguridad documental:
  - `docs/security/LOGGING_POLICY.md` (alineado a CWE-532).
  - `docs/SECURITY.md` actualizado con referencia obligatoria a policy de logging seguro.
- Runbooks de staging y rollback:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- Verificacion operativa no-live (staging):
  - backend `https://bot-trading-ia-staging.up.railway.app` en `mode=paper`, `runtime_ready_for_live=false`.
  - frontend `https://bot-trading-ia-staging.vercel.app` accesible (`/login` OK).
- Hardening complementario de docs/runbooks:
  - `docs/runbooks/RAILWAY_STORAGE_PERSISTENCE.md` elimina ejemplo con `--password` en CLI y usa env var.

### AP-BOT-1001/AP-BOT-1002 (coherencia estrategia + fail-closed feature-set)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`
  - agregado `ExecutionProfile` por familia (`trend_pullback`, `breakout`, `meanreversion`, `defensive`, `trend_scanning`);
  - `StrategyRunner.run(...)` deja de usar hardcodes globales (`2.0/3.0/12`) y aplica stop/take/trailing/time-stop por perfil;
  - `trend_scanning` ahora devuelve familia efectiva del sub-regimen para usar perfil correcto;
  - `reason_code` de trades pasa a reflejar familia real ejecutada.
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_infer_orderflow_feature_set(...)` cambia fallback a `orderflow_unknown` (`missing_fail_closed`);
  - `validate_promotion` agrega check `known_feature_set`;
  - baseline picker no bloquea por feature-set cuando candidato esta en `orderflow_unknown` (evita falsos `No baseline`).
- Tests agregados:
  - `rtlab_autotrader/tests/test_backtest_execution_profiles.py`
  - `rtlab_autotrader/tests/test_web_feature_set_fail_closed.py`
- Evidencia de validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_backtest_execution_profiles.py rtlab_autotrader/tests/test_web_feature_set_fail_closed.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.

### AP-BOT-1003 (estabilizacion de latencia en `/api/v1/bots`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado `BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT` (default `40`);
  - en polling default (`recent_logs` sin explicitar), se auto-desactiva carga de logs recientes con muchos bots;
  - `recent_logs=true` explicito mantiene logs habilitados;
  - cache key de overview distingue `source=default|explicit`;
  - debug perf expone `logs_auto_disabled`, threshold y `bots_count`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_supports_recent_logs_query_overrides_and_cache_key or bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override or bots_overview_perf_headers_and_debug_payload" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).

### AP-BOT-1004 (runtime testnet sin fill sintético)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._reconcile(...)` ahora parsea `openOrders` con `qty/symbol/side` y sincroniza OMS local;
  - `RuntimeBridge.sync_runtime_state(...)` deja progresion de fill incremental solo para `paper` (en `testnet/live` no simula fills);
  - reconciliacion se calcula sobre snapshot OMS ya sincronizado con exchange.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.

### AP-BOT-1005 (cancel remoto idempotente por `client_order_id`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado parser comun de `openOrders` con `client_order_id/order_id`;
  - agregado cancel remoto en runtime para `testnet/live` (`DELETE /api/v3/order`) durante `stop/kill/mode_change`;
  - idempotencia temporal de cancel con:
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC=30` (default),
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS=2000` (default);
  - si exchange responde `unknown order`, se toma como cancel idempotente exitoso.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_stop_testnet_cancels_remote_open_orders_idempotently`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.

### AP-BOT-1006 (submit remoto idempotente, default-off)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado submit remoto opcional para runtime `real` en `testnet/live` (`POST /api/v3/order`) con `newClientOrderId` estable por ventana;
  - nuevo control idempotente local:
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC` (default `60`),
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS` (default `2000`);
  - manejo idempotente de duplicate submit Binance (`code=-2010`, `duplicate order`);
  - feature flag segura por defecto:
    - `RUNTIME_REMOTE_ORDERS_ENABLED=false`,
    - parametros de semilla `RUNTIME_REMOTE_ORDER_NOTIONAL_USD`, `RUNTIME_REMOTE_ORDER_SYMBOL`, `RUNTIME_REMOTE_ORDER_SIDE`;
  - estado runtime ahora incluye:
    - `runtime_last_remote_submit_at`,
    - `runtime_last_remote_client_order_id`,
    - `runtime_last_remote_submit_error`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default`;
  - nuevo `test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1007 (reconciliacion de posiciones por account snapshot)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado fetch firmado de `/api/v3/account` para runtime `testnet/live` y parser de balances spot a posiciones;
  - `RuntimeBridge` expone posiciones reconciliadas por account snapshot cuando la fuente remota responde OK;
  - fallback: si account falla, se mantiene snapshot derivado de `openOrders` (sin frenar loop);
  - nuevo estado runtime:
    - `runtime_account_positions_ok`,
    - `runtime_account_positions_verified_at`,
    - `runtime_account_positions_reason`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot`;
  - nuevo `test_runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1008 (costos runtime por fill-delta)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado acumulador de costos runtime en `RuntimeBridge` con deltas de fill (`OMS`) para fees/spread/slippage/funding;
  - nuevos campos en `execution_metrics_snapshot`:
    - `fills_count_runtime`,
    - `fills_notional_runtime_usd`,
    - `fees_total_runtime_usd`,
    - `spread_total_runtime_usd`,
    - `slippage_total_runtime_usd`,
    - `funding_total_runtime_usd`,
    - `total_cost_runtime_usd`,
    - `runtime_costs`.
  - reset de acumuladores al evento `start`/`mode_change` en runtime real.
  - `build_execution_metrics_payload` fail-closed fuerza costos runtime a cero cuando telemetry es sintetica.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_execution_metrics_accumulate_costs_from_fill_deltas`;
  - `test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic` ahora valida `runtime_costs` en cero.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1009 (hardening `--password` + guard CI)
- `.github/workflows`:
  - `security-ci.yml` agrega guard fail-closed para detectar `--password` en workflows/`scripts/*.ps1`.
- `scripts`:
  - `seed_bots_remote.py` y `check_storage_persistence.py`:
    - `--password` pasa a deprecado/inseguro;
    - uso por CLI queda bloqueado por defecto (solo se habilita con `ALLOW_INSECURE_PASSWORD_CLI=1`);
    - fallback de password remoto prioriza `RTLAB_ADMIN_PASSWORD`.
  - `run_bots_benchmark_sweep_remote.ps1` elimina `--password` en comandos python y usa env temporal.
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\\Program Files\\Git\\bin\\bash.exe scripts/security_scan.sh` -> PASS.
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.

### AP-BOT-1010 (cierre no-live formal)
- Nuevo artefacto:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- Resultado consolidado:
  - no-live/testnet: GO.
  - LIVE: NO GO (postergado por decision operativa, pendiente tramo final con APIs reales/canary).

### AP-BOT-1011 (submit runtime por intencion de estrategia, fail-closed)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo `RuntimeBridge._runtime_order_intent(...)` para derivar `action/side/symbol/notional` desde estrategia principal por modo;
  - fail-closed cuando no hay estrategia principal valida o esta deshabilitada (`action=flat`);
  - nuevo control de enfriamiento de submit:
    - `RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC` (default `120`);
  - nuevo flujo `RuntimeBridge._maybe_submit_exchange_runtime_order(...)`:
    - bloquea submit si `risk.allow_new_positions=false`;
    - bloquea submit si ya hay posiciones abiertas por account snapshot;
    - bloquea submit si hay `openOrders` o cooldown activo;
    - conserva idempotencia de `client_order_id` ya implementada en AP previos.
  - estado runtime ampliado con trazabilidad de senal:
    - `runtime_last_signal_action`,
    - `runtime_last_signal_reason`,
    - `runtime_last_signal_strategy_id`,
    - `runtime_last_signal_symbol`,
    - `runtime_last_signal_side`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`;
  - agregado `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Nota de estado:
  - reduce brecha de `FM-EXEC-001/FM-EXEC-005` en no-live;
  - LIVE permanece `NO GO` hasta cerrar lifecycle real completo (fills/partial fills/cancel-replace/reconciliacion final).

### Revalidacion bibliografica AP-BOT-1011
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) y declaracion explicita de `NO EVIDENCIA LOCAL` cuando corresponde.

### AP-BOT-1012 (finalizacion de ordenes ausentes con `order status` remoto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._parse_exchange_open_orders_payload(...)` incorpora `status` remoto cuando existe;
  - nuevo `RuntimeBridge._fetch_exchange_order_status(...)` con `GET /api/v3/order` para resolver estado final de orden ausente en `openOrders`;
  - nuevo `RuntimeBridge._apply_remote_order_status_to_local(...)`:
    - `FILLED` -> cierra en `OrderStatus.FILLED` y ajusta `filled_qty`;
    - `CANCELED/EXPIRED/EXPIRED_IN_MATCH` -> terminal `CANCELED` (o `FILLED` si ya completo);
    - `REJECTED` -> terminal `REJECTED`;
    - `NEW/PARTIALLY_FILLED/PENDING_CANCEL` -> mantiene orden abierta.
  - `_close_absent_local_open_orders(...)` ahora:
    - consulta `order status` antes de cancelar localmente;
    - si orden sigue abierta, la reinyecta en snapshot de reconciliacion para evitar desync falso;
    - si no hay evidencia remota, mantiene fallback conservador a cancel local.
  - `_reconcile(...)` pasa `mode` al cierre de ausentes para habilitar esta resolucion en `testnet/live`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`;
  - agregado `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`;
  - ajuste de regresion en `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace` para cubrir ruta real de grace sin chocar con `cancel_stale`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Nota de estado:
  - mejora cierre de lifecycle de orden en no-live y reduce desync por ausencias transitorias en `openOrders`;
  - LIVE permanece `NO GO` (todavia falta cierre global de runtime end-to-end + riesgos abiertos no-runtime).

### Revalidacion bibliografica AP-BOT-1012
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) y fuentes primarias oficiales cuando falta contrato API especifico.

### AP-BOT-1013 (riesgo del mismo ciclo antes de submit remoto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge.sync_runtime_state(...)` reordena el flujo: el submit remoto en `testnet/live` ahora corre despues de recalcular riesgo del ciclo actual;
  - el gate de submit usa `self._last_risk` ya actualizado del mismo ciclo (no snapshot atrasado);
  - condicion de submit endurecida:
    - solo si `decision.kill=false`,
    - `running=true`,
    - `killed=false`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Nota de estado:
  - reduce la brecha de `FM-RISK-002` en no-live al evitar submits con riesgo bloqueado en el mismo loop;
  - LIVE sigue `NO GO` por pendientes globales de cierre end-to-end.

### Revalidacion bibliografica AP-BOT-1013
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) para principios de risk management y gates fail-closed.

### AP-BOT-1014 (reuso de account snapshot en submit runtime)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` acepta snapshot de cuenta ya resuelto en el ciclo (`account_positions`, `account_positions_ok`);
  - `sync_runtime_state(...)` pasa ese snapshot al submit remoto para evitar segunda llamada a `/api/v3/account` en el mismo loop;
  - mantiene mismo comportamiento funcional (bloqueo si hay posiciones abiertas) con menos llamadas remotas.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell` ahora verifica `account_get == 1` (sin doble fetch de cuenta).
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Nota de estado:
  - reduce overhead de API por ciclo en runtime real no-live;
  - LIVE sigue `NO GO`.

### Revalidacion bibliografica AP-BOT-1014
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first en principios de eficiencia operativa + contrato API oficial para account/order endpoints.

### AP-BOT-1015 (cobertura de estados remotos PARTIALLY_FILLED/REJECTED)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status`;
  - agregado `test_runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status`.
- Objetivo:
  - fijar regresion para mapping de estados remotos ya implementados en runtime (`PARTIALLY_FILLED`, `REJECTED`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Nota de estado:
  - mejora cobertura de lifecycle runtime y reduce riesgo de regresion en reconciliacion no-live.

### Revalidacion bibliografica AP-BOT-1015
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - misma base local-first usada en AP-BOT-1012 (microestructura de open orders + contrato API oficial).

### Revalidacion bibliografica completa AP-BOT-1006..1010
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- Incluye para cada AP:
  - evidencia tecnica exacta en repo;
  - soporte bibliografico local (`BIBLIO_INDEX` + `biblio_txt` con lineas);
  - `NO EVIDENCIA LOCAL` cuando corresponde;
  - complemento exclusivo con fuentes primarias oficiales (Binance, Linux man-pages, Microsoft, MITRE CWE, Kubernetes).

### Auditoria integral de pe a pa (estado actualizado)
- Nuevos artefactos de auditoria:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Consolidacion de estado real:
  - `LIVE`: `NO GO` por runtime de ejecucion real no cerrado end-to-end.
  - `No-live/testnet`: operativo con controles actuales (decision de proyecto: LIVE al final).
- Hallazgos criticos/high registrados en reporte:
  - runtime `testnet/live` aun con loop de fills simulados en `RuntimeBridge`.
  - fallback mock del BFF si falta `BACKEND_API_URL`.
  - scripts/workflows con rutas `--password` (exposicion de secretos en CLI).
  - divergencia de policy `gates` entre `config` y `knowledge`.
  - variabilidad de latencia `/api/v1/bots` en productivo.
- Evidencia de corrida del dia:
  - `./scripts/security_scan.ps1 -Strict` -> PASS.
  - `python -m pytest -q rtlab_autotrader/tests` -> PASS.
  - `npm test -- --run` -> PASS.
  - `npm run lint` -> PASS.
  - `npm run build` -> PASS (warning de charts pendiente).

### AP-7003 hotfix (G9 estricto por modo + evaluate_gates read-only)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeSnapshot.checks` cambia `exchange_mode_known` -> `exchange_mode_match` para exigir `runtime_exchange_mode == mode objetivo`.
  - `evaluate_gates(...)` deja de llamar `_sync_runtime_state(..., persist=True)` cuando no recibe `runtime_state`; queda sin efectos de persistencia sobre `bot_state`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode`.
  - nuevo test `test_evaluate_gates_does_not_persist_runtime_state_side_effects`.
  - ajustes en tests G9 para usar `runtime_exchange_mode=\"live\"` en escenarios PASS para LIVE.
- Evidencia:
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_passes_only_when_runtime_contract_is_fully_ready rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers rtlab_autotrader/tests/test_web_live_ready.py::test_evaluate_gates_does_not_persist_runtime_state_side_effects rtlab_autotrader/tests/test_web_live_ready.py::test_live_mode_blocked_when_runtime_engine_is_simulated` -> PASS.
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py -k "g9 or runtime_contract_snapshot_defaults_are_exposed_in_status or live_blocked_by_gates_when_requirements_fail or storage_gate_blocks_live_when_user_data_is_ephemeral"` -> PASS.

### AP-7001/AP-7002 completados (runtime exchange-evidence + risk policy wiring)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `evaluate_gates(...)` ahora sincroniza runtime state cuando no se pasa `runtime_state` (reduce bypass por estado stale).
  - `RuntimeSnapshot` agrega checks de exchange (`exchange_connector_ok`, `exchange_order_ok`, `exchange_check_fresh`, `exchange_mode_known`).
  - runtime fail-closed: si engine real no valida connector+order en exchange, fuerza `runtime_telemetry_source=synthetic_v1`.
  - reconciliacion no-paper ahora consulta `GET /api/v3/openOrders` firmado y publica `source/source_ok/source_reason`.
  - runtime risk ahora carga `config/policies/risk_policy.yaml` y aplica hard-kill policy-driven (`daily_loss`/`drawdown`).
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `default_learning_settings().risk_profile` pasa a derivarse desde `config/policies/risk_policy.yaml` (fallback: `MEDIUM_RISK_PROFILE`).
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `_mock_exchange_ok` cubre `openOrders`.
  - nuevo test `test_learning_default_risk_profile_prefers_policy_yaml`.
  - ajustes en tests de `G9` y runtime real para contrato actualizado.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.

### Cierre auditoria PARTE 7/7 (cerebro del bot)
- Se cerro la auditoria de aprendizaje/decision/rollout con evidencia de codigo en:
  - `learning/brain.py`, `learning/service.py`,
  - `src/backtest/engine.py`, `src/research/mass_backtest_engine.py`,
  - `rollout/manager.py`, `rollout/compare.py`, `rollout/gates.py`,
  - `web/app.py`.
- Se agregaron artefactos de cierre para no perder contexto y planificar reparacion sin retrabajo:
  - `docs/audit/FINDINGS_MASTER_20260304.md` (registro maestro de problemas con estado).
  - `docs/audit/ACTION_PLAN_FINAL_20260304.md` (plan final por bloques y dependencias).
- Confirmado:
  - Opcion B sigue obligatoria (`allow_auto_apply=false`, `allow_live=false`).
  - `purged_cv` y `cpcv` quedan implementados en quick backtest/learning rapido.
  - runtime web seguia con payloads sinteticos en endpoints operativos clave (`status`/`execution metrics`) al inicio de la auditoria; mitigado parcialmente en Bloque 1.
- Se deja trazado que faltan 3 bloques no-live para cierre final: runtime real no-live, security CI root protegido y hardening final de operacion/pruebas.

### Bloque 0 iniciado (AP-0001/AP-0002)
- Rama tecnica creada: `feature/runtime-contract-v1`.
- Contrato canonico `RuntimeSnapshot v1` y criterio exacto `G9` documentados en:
  - `docs/audit/AP0001_AP0002_RUNTIME_CONTRACT_V1.md`.
- Implementacion base (sin runtime real aun):
  - `web/app.py` ahora expone metadata de contrato runtime en `/health`, `/status`, `/execution/metrics`.
  - `evaluate_gates` usa evaluacion de contrato runtime para `G9_RUNTIME_ENGINE_REAL`.
- Tests focales agregados y en verde:
  - `test_runtime_contract_snapshot_defaults_are_exposed_in_status`
  - `test_g9_live_passes_only_when_runtime_contract_is_fully_ready`
  - `test_live_mode_blocked_when_runtime_engine_is_simulated`

### Bloque 1 en progreso (AP-1001/AP-1002/AP-1003)
- Wiring runtime aplicado en backend web (`rtlab_autotrader/rtlab_core/web/app.py`):
  - nuevo `RuntimeBridge` acoplado a `OMS + Reconciliation + RiskEngine + KillSwitch`;
  - sincronizacion runtime integrada en `/api/v1/status`, `/api/v1/execution/metrics`, `/api/v1/risk` y `/api/v1/health`;
  - endpoints de control (`bot/mode`, `bot/start`, `bot/stop`, `bot/killswitch`, `control/pause`, `control/safe-mode`) ahora actualizan contrato runtime en cada transicion.
- Payloads operativos ya no usan valores hardcodeados:
  - `build_status_payload` usa `positions` y health derivados del runtime bridge.
  - `build_execution_metrics_payload` usa series/ratios calculados por runtime bridge.
  - `/api/v1/risk` usa snapshot de exposicion/riesgo/reconciliacion del runtime bridge.
- Tests agregados en `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk`
  - `test_runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live`
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or health_reports_storage_persistence_status or storage_gate_blocks_live_when_user_data_is_ephemeral or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `8 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.
- Estado: mitigacion fuerte de `FM-EXEC-001/FM-EXEC-005` en no-live; sigue pendiente wiring de broker/exchange real para LIVE y cierre de gates estrictos de runtime (AP-200x).

### AP-1004 completado (telemetry_source + fail-closed sintetico)
- `build_status_payload`, `build_execution_metrics_payload`, `/api/v1/risk` y `/api/v1/health` exponen guard de telemetria runtime:
  - `runtime_telemetry_source`
  - `runtime_telemetry_ok`
  - `runtime_telemetry_fail_closed`
  - `runtime_telemetry_reason`
- Regla fail-closed aplicada cuando `telemetry_source=synthetic_v1`:
  - `execution_metrics` fuerza metricas conservadoras (ej. `fill_ratio=0`, `maker_ratio=0`, `latency_ms_p95>=999`) para no permitir lecturas falsas de salud operativa.
- Tests agregados/ajustados:
  - `test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic`
  - `test_runtime_contract_snapshot_defaults_are_exposed_in_status` (assert de `telemetry_fail_closed`)
  - `test_runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk` (assert de `telemetry_ok`)
  - `test_rollout_safe_update.py` API e2e ajustado para levantar runtime real no-live en setup (`_ensure_runtime_real_for_rollout_api`).
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `6 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.

### AP-2001/AP-2002/AP-2003 completados (gating runtime + breaker strict + bloqueo de evaluacion sintetica)
- AP-2001 (G9 con heartbeat/reconciliacion frescos) reforzado con test especifico:
  - `test_g9_live_fails_when_runtime_heartbeat_is_stale` en `rtlab_autotrader/tests/test_web_live_ready.py`.
- AP-2002 aplicado en diagnostico de `breaker_events`:
  - `GET /api/v1/diagnostics/breaker-events` acepta `strict=true|false`;
  - en modo estricto, `NO_DATA` pasa a fail-closed (`ok=false`);
  - `scripts/ops_protected_checks_report.py` propaga el flag y reporta `breaker_strict_mode`.
  - cobertura nueva:
    - `test_breaker_events_integrity_endpoint_no_data_non_strict_ok`
    - `test_breaker_events_integrity_endpoint_no_data_strict_fail_closed`
- AP-2003 aplicado en `POST /api/v1/rollout/evaluate-phase`:
  - fail-closed explicito cuando `runtime_telemetry_guard.ok=false` (telemetry sintetica);
  - se registra log `rollout_phase_eval_blocked` con fase + fuente de telemetria.
- Cobertura nueva:
  - `test_rollout_api_evaluate_phase_fail_closed_when_runtime_telemetry_synthetic` en `rtlab_autotrader/tests/test_rollout_safe_update.py`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_heartbeat_is_stale or runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `7 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint_pass or breaker_events_integrity_endpoint_no_data_non_strict_ok or breaker_events_integrity_endpoint_no_data_strict_fail_closed or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-3001 completado (Purged CV + embargo real)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`:
  - `validation_mode=purged-cv` deja de ser hook y ejecuta split OOS real con `purge_bars + embargo_bars`;
  - `validation_summary` ahora registra `purge_bars`, `embargo_bars`, `oos_bars`, `is_bars` y rango temporal OOS;
  - base de configuracion (`purge/embargo`) queda lista para CPCV.
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `POST /api/v1/backtests/run` acepta `purge_bars` y `embargo_bars` (opcionales, enteros `>=0`);
  - `_learning_eval_candidate` usa `settings.learning.validation` para resolver modo (`walk-forward`/`purged-cv`/`cpcv`).
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `validation.purged_cv` pasa a `implemented=true`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_backtests_run_supports_purged_cv_and_cpcv`.
  - `test_learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled`.
  - `test_learning_research_loop_and_adopt_option_b` valida estado de `purged_cv/cpcv`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_research_loop_and_adopt_option_b" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

### AP-3002 completado (CPCV real en learning/research rapido)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`:
  - `validation_mode=cpcv` ya no es hook-only y ejecuta paths combinatoriales (`n_splits`, `k_test_groups`, `max_paths`);
  - cada path aplica trimming por `purge_bars + embargo_bars`, se evalua con `StrategyRunner` y se consolida en `validation_summary`.
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `POST /api/v1/backtests/run` acepta `cpcv_n_splits`, `cpcv_k_test_groups`, `cpcv_max_paths` (enteros validados);
  - `_learning_eval_candidate` propaga `cpcv_*` desde `settings.learning.validation`.
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `validation.cpcv` pasa a `implemented=true` con `enforce` atado a `enforce_cpcv`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_backtests_run_supports_purged_cv_and_cpcv` ahora valida `cpcv` en `200` + `paths_evaluated>=1`.
  - nuevo `test_learning_eval_candidate_supports_cpcv_mode_from_settings`.
  - `test_learning_research_loop_and_adopt_option_b` exige `cpcv.implemented=true`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_eval_candidate_supports_cpcv_mode_from_settings or learning_research_loop_and_adopt_option_b" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_rejects_synthetic_source or event_backtest_engine_runs_for_crypto_forex_equities or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

### AP-3003 completado (learning eval fail-closed sin fallback silencioso)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_learning_eval_candidate` deja de usar fallback silencioso a runs cache/dummy;
  - ante falta de dataset real o `dataset_source` sintetico, ahora lanza `ValueError` fail-closed.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_learning_research_loop_and_adopt_option_b` se estabiliza con evaluator stub explicito;
  - nuevo `test_learning_run_now_fails_closed_when_real_dataset_missing`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "learning_research_loop_and_adopt_option_b or learning_run_now_fails_closed_when_real_dataset_missing" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-3004 completado (separar `anti_proxy` y `anti_advanced` en research)
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`:
  - resultados de `run_job` ahora incluyen `anti_proxy`, `anti_advanced` y `anti_overfitting` (alias legacy de `anti_advanced`);
  - `_apply_advanced_gates` deja trazabilidad separada de proxy vs gates avanzados;
  - persistencia de batch (`kpi_summary_json`/`artifacts_json`) prioriza valores de `anti_advanced` y conserva `anti_proxy`.
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`:
  - se amplian asserts en `test_run_job_persists_results_and_duckdb_smoke_fallback`;
  - nuevo `test_advanced_gates_exposes_anti_proxy_and_anti_advanced_separately`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`.

### AP-3005 completado (CompareEngine fail-closed cuando feature_set es unknown)
- `rtlab_autotrader/rtlab_core/rollout/compare.py`:
  - `_extract_orderflow_feature_set` ya no hace fallback silencioso a `orderflow_on`;
  - nuevo check `known_feature_set` bloquea compare cuando baseline/candidato quedan `orderflow_unknown`.
- `rtlab_autotrader/tests/test_rollout_safe_update.py`:
  - `_sample_run` pasa a declarar `orderflow_feature_set` explicito;
  - `test_compare_engine_improvement_rules` agrega caso fail-closed por unknown.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

### AP-3006 completado (strict_strategy_id obligatorio en research/promotion no-demo)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - research mass/beast propaga `execution_mode` y fuerza `strict_strategy_id` en `_mass_backtest_eval_fold` para no-demo;
  - `POST /api/v1/research/mass-backtest/mark-candidate` bloquea candidatos sin `strict_strategy_id=true` en no-demo;
  - `validate_promotion/promote` agregan constraint `strict_strategy_id_non_demo`.
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`:
  - resultados incluyen `strict_strategy_id` + `execution_mode` y se persisten en `params_json/artifacts_json`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo` nuevo;
  - `test_mass_backtest_research_endpoints_and_mark_candidate` y `test_runs_validate_and_promote_endpoints_smoke` actualizados.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-4001 (security CI root) - versionado tecnico
- Se versiona `/.github/workflows/security-ci.yml` en rama tecnica (`feature/runtime-contract-v1`, commit `0dbf55d`).
- Contenido del workflow:
  - instala `pip-audit` + `gitleaks`,
  - ejecuta `scripts/security_scan.sh` en modo estricto,
  - sube artifacts `artifacts/security_audit/`.
- Validacion local de sintaxis:
  - parse YAML de workflow con `python + yaml.safe_load` -> `OK_WORKFLOW`.
- Pendiente para cierre operativo:
  - corrida verde en GitHub Actions.
- Evidencia remota inicial:
  - run `22674323602` (evento `push`) en `failure`;
  - causa: paso `Install security tooling` del job `security`.
- Fix incremental:
  - instalacion de `gitleaks` migrada a `"$RUNNER_TEMP/bin"` + `GITHUB_PATH` para evitar error de permisos.

### AP-4002 completado (branch protection con required check security)
- Proteccion de rama `main` aplicada por API:
  - `required_status_checks.strict=true`
  - `required_status_checks.contexts=["security"]`
- Evidencia de verificacion:
  - `PROTECTION_SET_OK contexts=security`
  - `PROTECTION_VERIFY strict=True contexts=security enforce_admins=False`
- Resultado:
  - merge a `main` queda condicionado al check `security`.

### AP-4003 completado (lockout/rate-limit login backend compartido)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `LoginRateLimiter` ahora soporta backend `sqlite|memory` (default `sqlite`).
  - nuevos envs:
    - `RATE_LIMIT_LOGIN_BACKEND`
    - `RATE_LIMIT_LOGIN_SQLITE_PATH`
  - persistencia de estado de login en tabla `auth_login_rate_limit` para compartir lockout/rate-limit entre instancias.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_auth_login_rate_limit_and_lock_guard` ajustado a `backend="memory"` para estabilidad deterministica.
  - nuevo `test_auth_login_rate_limit_shared_sqlite_backend_across_instances`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_and_lock_guard or auth_login_rate_limit_shared_sqlite_backend_across_instances" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_and_admin_protection or api_general_rate_limit_guard or api_expensive_rate_limit_guard" -q` -> `3 passed`.

### AP-5001 completado (suite E2E critica backend)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_e2e_critical_flow_login_backtest_validate_promote_rollout`.
  - helper `_force_runs_rollout_ready` para datos deterministas en gates/compare durante la suite.
- Flujo cubierto:
  - `login -> backtests/run -> runs/validate_promotion -> runs/promote -> rollout/advance`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "e2e_critical_flow_login_backtest_validate_promote_rollout or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

### AP-5002 completado (chaos/recovery runtime)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - helper nuevo `_mock_exchange_down`.
  - nuevo `test_exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect`.
  - nuevo `test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers`.
- Escenarios cerrados:
  - exchange down/reconnect en testnet (diagnose + gates).
  - desync de reconciliacion runtime (`G9` FAIL -> PASS tras refresh).
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers or g9_live_fails_when_runtime_heartbeat_is_stale or exchange_diagnose_passes_with_env_keys_and_mocked_exchange" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_shared_sqlite_backend_across_instances or e2e_critical_flow_login_backtest_validate_promote_rollout or exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `4 passed`.

### AP-5003 completado (alertas operativas minimas)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo `build_operational_alerts_payload`.
  - `/api/v1/alerts` agrega alertas derivadas (`include_operational=true` por default):
    - `ops_drift`, `ops_slippage_anomaly`, `ops_api_errors`, `ops_breaker_integrity`.
  - nuevos umbrales por ENV: `OPS_ALERT_SLIPPAGE_P95_WARN_BPS`, `OPS_ALERT_API_ERRORS_WARN`, `OPS_ALERT_BREAKER_WINDOW_HOURS`, `OPS_ALERT_DRIFT_ENABLED`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_alerts_include_operational_alerts_for_drift_slippage_api_and_breaker`.
  - nuevo `test_alerts_operational_alerts_clear_when_runtime_recovers`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `2 passed`.

### AP-6001 completado (decision final de hallazgos)
- Se versiona `docs/audit/FINDINGS_DECISION_MATRIX_20260304.md` con decision final por `FM-*`.
- Snapshot de cierre del plan:
  - `CERRADO=12`
  - `MITIGADO=8`
  - `ABIERTO=6`
- Abiertos priorizados para fase siguiente:
  - `FM-EXEC-001`, `FM-EXEC-002`, `FM-EXEC-005`, `FM-QUANT-008`, `FM-RISK-002`, `FM-RISK-003`.

### AP-6002 completado (politica formal de biblio_raw/metadatos)
- Nueva politica: `docs/reference/BIBLIO_ACCESS_POLICY.md`.
- Se formaliza:
  - `biblio_raw`/`biblio_txt` no versionados en git.
  - versionado obligatorio de metadatos/hashes en `docs/reference/BIBLIO_INDEX.md`.
  - flujo canonico de actualizacion con `python scripts/biblio_extract.py`.

### Auditoria integral (comite senior) + evidencia operativa
- Se ejecuto auditoria E2E del sistema (AppSec/DevSecOps, ejecucion, quant/backtests, risk, SRE, QA, UX) con evidencia por rutas y lineas.
- Resultado de go/no-go actualizado: **NO GO para LIVE** por bloqueantes tecnicos de runtime real.
- Evidencia de ejecucion local en esta corrida:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict` -> PASS (`pip-audit` runtime/research sin vulnerabilidades conocidas + `gitleaks` sin leaks).
  - `python -m pytest rtlab_autotrader/tests --collect-only` -> `126 tests collected`.
  - `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - `npm --prefix rtlab_dashboard run lint` -> PASS.
- Hallazgos criticos consolidados:
  - runtime live en backend web todavia desacoplado de OMS/risk/reconciliacion reales;
  - payloads sinteticos en endpoints de estado/ejecucion/riesgo (estado previo, mitigado parcialmente en Bloque 1);
  - `breaker_events` queda fail-closed solo en modo estricto (`strict=true`).
- CI/security:
  - en root siguen activos solo `remote-benchmark.yml` y `remote-protected-checks.yml`;
  - `/.github/workflows/security-ci.yml` ya versionado en rama tecnica (`0dbf55d`); pendiente push + corrida en GitHub Actions.
- Bibliografia:
  - se confirma `BIBLIO_INDEX.md`;
  - `docs/reference/biblio_raw/` en repo continua sin PDFs versionados (solo `.gitignore`), por lo que se registro faltante para trazabilidad local reproducible.

## 2026-03-03

### Remote protected checks + cierre no-live
- Workflow `Remote Protected Checks (GitHub VM)` ejecutado con defaults (`strict=true`):
  - run `22648114549` -> `success`.
  - artifact `protected-checks-22648114549` con:
    - `ops_protected_checks_gha_22648114549_20260303_234740.json`
    - `ops_protected_checks_gha_22648114549_20260303_234740.md`
    - `protected_checks_stdout.log`
- Resultado canonico del reporte remoto:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en etapa no-live)
  - `breaker_ok=true` (`breaker_status=NO_DATA`)
  - `internal_proxy_status_ok=true`
- Revalidacion de seguridad ejecutada en local (equivalente al job security):
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
  - resultado: `pip-audit` runtime/research sin vulnerabilidades conocidas y `gitleaks` baseline-aware sin leaks.
  - nota de CI: en GitHub Actions del repo root solo se observan workflows remotos (`Remote Bots Benchmark` y `Remote Protected Checks`), por lo que este cierre registra la verificacion estricta local como evidencia operativa de seguridad.
  - para cerrar ese gap, se versiona workflow root `/.github/workflows/security-ci.yml` (security CI bloqueante); queda pendiente push + corrida en GitHub Actions.
- Estado no-live consolidado:
  - benchmark remoto GitHub VM previamente en PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin `429` retries).
  - checks protegidos remotos en PASS.
  - LIVE real continua bloqueado por `G9_RUNTIME_ENGINE_REAL` hasta runtime real.

## 2026-03-02

### Cierre final de bloque (6h real + lint limpio)
- Soak extendido `6h` finalizado en segundo plano con evidencia real:
  - `artifacts/soak_6h_bg_status.json` -> `loops=1440`, `ok=1440`, `errors=0`, `g10_pass=1440`.
  - `artifacts/soak_6h_bg_20260302_132230_DONE.txt`.
- Snapshot operativo final (sin supuestos) ejecutado:
  - `python scripts/build_ops_snapshot.py`
  - evidencia: `artifacts/ops_block2_snapshot_20260302_231911.json` + `.md`.
  - resultado: `block2_provisional_ready=true`, `soak_6h_effective_pass=true`.
- Limpieza de warnings frontend completada:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`: deps de hooks corregidas + memoizacion de `focusTrades` + remocion de variable no usada.
  - `rtlab_dashboard/src/app/(app)/settings/page.tsx`: remocion de estado no usado `learningConfigError`.
  - validacion: `npm --prefix rtlab_dashboard run lint` -> `0 errores, 0 warnings`.
  - validacion: `npm --prefix rtlab_dashboard run test` -> `11 passed`.
- Cierre estricto de checks protegidos preparado:
  - `scripts/build_ops_snapshot.py` agrega:
    - `--ask-password` (prompt de `ADMIN_PASSWORD` cuando falta token),
    - `--require-protected` (falla si no valida endpoints protegidos),
    - checks nuevos en reporte: `protected_checks_complete`, `breaker_integrity_ok`, `internal_proxy_status_ok`, `block2_ready_strict`.
  - nuevo launcher `scripts/run_protected_ops_checks.ps1`:
    - pide password una sola vez,
    - ejecuta `check_storage_persistence --require-persistent`,
    - ejecuta `build_ops_snapshot --require-protected --label ops_block2_snapshot_final`.
- Drill de backup/restore ejecutado y documentado:
  - nuevo script `scripts/backup_restore_drill.py` (usa scripts existentes de backup/restore y valida integridad por SHA256).
  - corrida ejecutada:
    - `python scripts/backup_restore_drill.py`
    - evidencia: `artifacts/backup_restore_drill_20260302_234205.json` + `.md`.
    - resultado: `backup_ok=true`, `restore_ok=true`, `manifest_match=true`.
  - runbook actualizado: `docs/runbooks/BACKUP_RESTORE_USER_DATA.md`.
- Bloque seguridad local (Windows) cerrado:
  - nuevo script `scripts/security_scan.ps1` (equivalente del job CI security sin dependencia de bash).
  - corrida estricta ejecutada:
    - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
    - `pip-audit` runtime/research: sin vulnerabilidades conocidas.
    - `gitleaks` baseline-aware: sin leaks.
  - evidencia refrescada:
    - `artifacts/security_audit/pip-audit-runtime.json`
    - `artifacts/security_audit/pip-audit-research.json`
    - `artifacts/security_audit/gitleaks.sarif`
- Bloque benchmark `/api/v1/bots` (regresión local + endurecimiento remoto):
  - `scripts/benchmark_bots_overview.py` agrega:
    - `--ask-password`,
    - `--require-evidence` (exit `2` cuando no hay cardinalidad mínima),
    - `--require-target-pass` (exit `3` cuando no cumple objetivo p95).
  - nuevo launcher `scripts/run_bots_benchmark_remote.ps1` para ejecutar benchmark remoto estricto en Windows con prompt de password.
  - rerun local ejecutado:
    - `python scripts/benchmark_bots_overview.py --bots 100 --requests 200 --warmup 30 --report-path docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260302_RERUN.md`
    - resultado: `p50=36.914ms`, `p95=55.513ms`, `p99=81.628ms` (PASS `<300ms`).
- Bundle remoto de cierre (operación en 1 comando):
  - nuevo script `scripts/run_remote_closeout_bundle.ps1`.
  - ejecuta secuencialmente con una sola captura de `ADMIN_PASSWORD`:
    - `check_storage_persistence.py --require-persistent`,
    - `build_ops_snapshot.py --require-protected --label ops_block2_snapshot_final`,
    - `benchmark_bots_overview.py` remoto con `--require-evidence` (y opcional `-RequireTargetPass`).

### Handoff + soak tests operativos (traspaso corto)
- Se creo `docs/reference/HANDOFF.md` con contexto de traspaso listo para abrir chat nuevo.
- Se actualizo `docs/truth/SOURCE_OF_TRUTH.md` con estado operativo de hoy:
  - persistencia Railway validada (`G10_STORAGE_PERSISTENCE=PASS`),
  - testnet estable con `G1..G8=PASS`,
  - LIVE sigue bloqueado por `G9` (runtime simulado).
- Se agregaron scripts locales para soak:
  - `scripts/soak_testnet.ps1` (parse fix + soporte `SOAK_ADMIN_PASSWORD`),
  - `scripts/start_soak_20m_background.ps1`,
  - `scripts/start_soak_6h_background.ps1`.
- Smoke corto de soak validado con evidencia local:
  - `ok=7`, `errors=0`, `g10_pass=7`.
- Soak operativo de `20m` ejecutado y finalizado en background:
  - `loops=80`, `ok=80`, `errors=0`, `g10_pass=80`.
- Flujo operativo actualizado: se usa solo soak `20m` + `6h` (sin `8h`).
- Adelanto de bloque (sin esperar cierre de soak 6h):
  - `BacktestEngine` incorpora `strict_strategy_id` opt-in para fail-closed de `strategy_id` no soportado.
  - default sigue compatible (`strict_strategy_id=false`) con fallback legacy a `trend_pullback`.
  - `POST /api/v1/backtests/run` propaga `strict_strategy_id`.
  - tests nuevos:
    - `test_unknown_strategy_falls_back_to_trend_pullback_when_not_strict`
    - `test_unknown_strategy_fails_closed_when_strict_mode_enabled`
    - `test_backtests_run_forwards_strict_strategy_id_flag`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py rtlab_autotrader/tests/test_web_live_ready.py -k "strict_strategy_id_flag or unknown_strategy_fails_closed_when_strict_mode_enabled or unknown_strategy_falls_back_to_trend_pullback_when_not_strict" -q` -> `3 passed`.
- Adelanto de bloque performance `/api/v1/bots`:
  - `ConsoleStore.get_bots_overview(...)` ahora registra timings por etapa (inputs/context/pool/runs_index/kpis/db_reads/db_process/assemble/total).
  - cache interna de overview guarda tambien perf y lo devuelve en `debug_perf=true` (tanto `hit` como `miss`).
  - `bots_overview_slow` agrega `overview_perf` al payload de log.
  - tests actualizados:
    - `test_bots_overview_perf_headers_and_debug_payload`
    - `test_bots_overview_cache_hit_and_invalidation_on_create` (wrapper ajustado a nuevo arg `overview_perf`).
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create" -q` -> `2 passed`.
- Adelanto de bloque `breaker_events` (integridad y diagnostico):
  - nuevo endpoint `GET /api/v1/diagnostics/breaker-events` (auth requerido) con ventana configurable (`window_hours`).
  - integra chequeo de integridad de catalogo `breaker_events`:
    - volumen total/ventana,
    - ratios de `unknown_bot`/`unknown_mode`/`unknown_any`,
    - warning por umbral (`BREAKER_EVENTS_UNKNOWN_RATIO_WARN`) con minimo de eventos (`BREAKER_EVENTS_UNKNOWN_MIN_EVENTS`).
  - tests nuevos:
    - `test_breaker_events_integrity_endpoint_pass`
    - `test_breaker_events_integrity_endpoint_warn_when_unknown_ratio_high`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity" -q` -> `2 passed`.
- Adelanto de bloque seguridad auth interna:
  - `current_user` ahora emite log de seguridad cuando detecta `x-rtlab-role/x-rtlab-user` sin proxy token valido.
  - evento generado: `type=security_auth`, `severity=warn`, `module=auth`.
  - payload incluye `reason` (`missing_proxy_token` o `invalid_proxy_token`), `client_ip`, `path`, `method`.
  - anti-ruido: throttle por `SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC` (default `60s`) para no inundar logs.
  - test ajustado:
    - `test_internal_headers_require_proxy_token` ahora valida bloqueo + evidencia de logs `security_auth`.
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token" -q` -> `1 passed`.
- Adelanto de bloque rotacion `INTERNAL_PROXY_TOKEN`:
  - soporte de rotacion con ventana de gracia:
    - `INTERNAL_PROXY_TOKEN` (token activo),
    - `INTERNAL_PROXY_TOKEN_PREVIOUS`,
    - `INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT` (ISO8601).
  - `current_user` ahora acepta token previo solo si no expiro; al expirar se rechaza (`reason=expired_previous_token`).
  - nuevo endpoint admin: `GET /api/v1/auth/internal-proxy/status` para verificar estado de rotacion sin exponer secretos.
  - tests nuevos:
    - `test_internal_proxy_allows_previous_token_with_future_expiry`
    - `test_internal_proxy_rejects_previous_token_when_expired`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_proxy" -q` -> `2 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token or internal_proxy_allows_previous_token_with_future_expiry or internal_proxy_rejects_previous_token_when_expired" -q` -> `3 passed`.
- Adelanto de bloque performance `/api/v1/bots` (scope de KPIs):
  - `ConsoleStore.get_bots_overview(...)` ahora calcula KPIs solo para estrategias presentes en pools de bots (`strategies_in_pool_count`) y no para todo el registry.
  - objetivo: reducir CPU en `stage_kpis_ms` cuando hay muchas estrategias no asignadas.
  - test nuevo:
    - `test_bots_overview_only_computes_kpis_for_strategies_in_pool`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_only_computes_kpis_for_strategies_in_pool" -q` -> `1 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `4 passed`.
- Adelanto de bloque performance `/api/v1/bots` (logs prefiltrados por bot_ref):
  - tabla `logs` incorpora flag materializado `has_bot_ref` (0/1).
  - migracion incremental al boot:
    - agrega columna si falta,
    - crea indice `idx_logs_has_bot_ref_id`,
    - backfill acotado por ventana reciente (`BOTS_LOGS_REF_BACKFILL_MAX_ROWS`, default `50000`).
  - `add_log(...)` ahora persiste `has_bot_ref` en escritura.
  - `get_bots_overview(...)` usa `WHERE has_bot_ref = 1` para cargar logs recientes de bots (fallback legacy si falta columna), reduciendo parseo de logs no relacionados.
  - `debug_perf.overview` agrega:
    - `logs_prefilter_has_bot_ref`
    - `logs_rows_read`
  - test nuevo:
    - `test_logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated" -q` -> `1 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `5 passed`.
- Adelanto de bloque performance `/api/v1/bots` (materializacion `log_bot_refs`):
  - nueva tabla `log_bot_refs(log_id, bot_id)` + indice `idx_log_bot_refs_bot_id_log_id`.
  - `add_log(...)` ahora indexa refs de bots en tiempo de escritura (desde `related_ids`, `payload.bot_id`, `payload.bot_ids[]`).
  - migracion/backfill incremental para DB legacy (`_backfill_log_bot_refs`) con ventana controlada por `BOTS_LOGS_REF_BACKFILL_MAX_ROWS`.
  - `get_bots_overview(...)` pasa a leer logs recientes via join `log_bot_refs -> logs` (prefilter por bots target), con fallback a `has_bot_ref`/legacy.
  - `debug_perf.overview.logs_prefilter_mode` ahora distingue `log_bot_refs`, `has_bot_ref`, `legacy_full_logs`.
  - tests nuevos:
    - `test_log_bot_refs_table_is_populated_and_used_in_overview`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "log_bot_refs_table_is_populated_and_used_in_overview or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated" -q` -> `2 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated or log_bot_refs_table_is_populated_and_used_in_overview or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `6 passed`.
- Adelanto de bloque operativo soak 6h (resume fail-safe):
  - `scripts/soak_testnet.ps1` ahora soporta reanudacion por segmento sin perder acumulados:
    - `StartIter`, `TotalLoops`,
    - offsets `OffsetOk/OffsetErrors/OffsetG10Pass`,
    - override de rutas `StatusPath/LogPath/DonePath`,
    - preservacion de `StartedAt`.
  - nuevo launcher `scripts/resume_soak_6h_background.ps1`:
    - detecta status existente (`soak_6h_bg_status.json`),
    - calcula iteraciones restantes,
    - evita duplicar ejecucion si ya hay proceso activo,
    - relanza en background continuando counters y log principal.
  - validacion de sintaxis PowerShell:
    - parser OK en `scripts/soak_testnet.ps1`.
    - parser OK en `scripts/resume_soak_6h_background.ps1`.
- Adelanto de bloque 2 operativo (cierre provisional mientras corre soak 6h):
  - nuevo script `scripts/build_ops_snapshot.py` para snapshot consolidado de operacion:
    - consume health remoto (sin auth) + artefactos de soak locales,
    - opcion `--assume-soak-6h-from-20m` para cierre temporal solicitado por usuario,
    - opcion `--assume-soak-6h-from-1h` para cierre temporal basado en soak 1h,
    - genera reporte JSON + Markdown en `artifacts/ops_block2_snapshot_<timestamp>.*`.
  - corrida ejecutada (modo provisional):
    - `python scripts/build_ops_snapshot.py --assume-soak-6h-from-20m`
    - resultado: `block2_provisional_ready=true` con nota explicita de suposicion temporal.
  - validacion ejecutada:
    - `python -m py_compile scripts/build_ops_snapshot.py` -> `OK`.
- Adelanto operativo soak abreviado 1h:
  - nuevo launcher `scripts/start_soak_1h_background.ps1` (`240 loops x 15s`) para ejecucion en segundo plano.
  - sintaxis PowerShell validada via parser: `OK`.
- Cierre de tramo con criterio valedero `1h`:
  - soak `1h` ejecutado y completado:
    - `loops=240`, `ok=240`, `errors=0`, `g10_pass=240`, `done=true`.
  - snapshot operativo de cierre generado con:
    - `python scripts/build_ops_snapshot.py --assume-soak-6h-from-1h`
  - evidencia:
    - `artifacts/soak_1h_bg_status.json`
    - `artifacts/soak_1h_bg_*_DONE.txt`
    - `artifacts/ops_block2_snapshot_20260302_211848.json`
    - `artifacts/ops_block2_snapshot_20260302_211848.md`
  - `build_ops_snapshot.py` ahora reporta `g10_effective_pass` y permite inferencia `PASS_INFERRED_FROM_SOAK` cuando `gates` no esta disponible por falta de token.
- Validacion integral no-live (backend + frontend):
  - backend: `python -m pytest rtlab_autotrader/tests -q` -> `124 passed`.
  - frontend: `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - frontend lint: `npm --prefix rtlab_dashboard run lint` -> `0 errores, 0 warnings`.
  - nota operativa: ejecutar pytest desde la raiz del repo para resolver correctamente `config/policies/*`.

## 2026-03-01

### Bloque 15: cierre hardening + limpieza de repo (commit limpio)
- `.gitignore` endurecido:
  - se ignoran `artifacts/`, `backups/`, `__pycache__/`, `*.pyc`.
  - se ignora bibliografia cruda local `docs/reference/biblio_raw/*` (manteniendo `.gitignore` del directorio).
- `scripts/security_scan.sh` corregido:
  - flujo `gitleaks` baseline-aware.
  - usa baseline si existe `artifacts/security_audit/gitleaks-baseline.json`.
  - sin baseline, ejecuta modo estricto con `gitleaks git`.
  - elimina falso warning de “gitleaks no instalado” cuando el binario esta presente.
- CI de seguridad:
  - `rtlab_autotrader/.github/workflows/ci.yml` agrega job `security` bloqueante.
  - ejecuta `pip-audit` + `gitleaks` y sube artefactos de auditoria.
  - ajuste del job Python para correr en `rtlab_autotrader` (coherente con `pyproject.toml`).
- Config local exchange:
  - `rtlab_autotrader/user_data/config/exchange_binance_spot.json` verificado con placeholders de ENV (sin claves reales).
- Requisitos:
  - `requirements-runtime.txt` y `requirements-research.txt` auditados (pip-audit sin vulns reportadas en esta corrida).

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

### Bloque 12: cardinalidad operativa de bots (sin minimos, con maximos)
- Backend:
  - nuevo limite maximo configurable por entorno: `BOTS_MAX_INSTANCES` (default `30`).
  - `POST /api/v1/bots` bloquea altas al alcanzar el tope y devuelve error claro en espanol.
- Script de benchmark:
  - `scripts/benchmark_bots_overview.py` ahora permite `--min-bots-required 0` (sin minimo obligatorio de evidencia).
  - mantiene modo estricto opcional cuando se quiera exigir una cardinalidad minima.
- Script de seed remoto:
  - default de `--target-bots` ajustado a `30` (recomendado para Railway actual).
  - si el backend rechaza por limite maximo, corta seed con mensaje explicito.
- Config:
  - `rtlab_autotrader/.env.example` documenta `BOTS_MAX_INSTANCES=30`.
- Tests:
  - nuevo `test_bots_creation_respects_max_instances_limit`.
  - validacion focal bots: `4 passed`.

### Bloque 13: observabilidad de performance en `/api/v1/bots`
- Endpoint `GET /api/v1/bots` ahora expone telemetria de latencia/cache por request:
  - headers:
    - `X-RTLAB-Bots-Overview-Cache` (`hit|miss`)
    - `X-RTLAB-Bots-Overview-MS`
    - `X-RTLAB-Bots-Count`
    - `X-RTLAB-Bots-Recent-Logs` (`enabled|disabled`)
  - query opcional `debug_perf=true` agrega bloque `perf` en payload (sin romper contrato base).
- Nuevo switch de carga:
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS` (default `true`) para poder desactivar logs recientes en overview cuando Railway este bajo presion.
- Slow-log controlado (throttled):
  - si `/api/v1/bots` supera `BOTS_OVERVIEW_PROFILE_SLOW_MS` (default `500ms`) registra `bots_overview_slow`.
  - throttling de logs con `BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC` (default `30s`) para evitar spam.
- Config documentada en `.env.example`:
  - `BOTS_OVERVIEW_CACHE_TTL_SEC`
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS`
  - `BOTS_OVERVIEW_PROFILE_SLOW_MS`
  - `BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC`
- Test nuevo:
  - `test_bots_overview_perf_headers_and_debug_payload`
- Validacion focal ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_multi_instance_endpoints or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_perf_headers_and_debug_payload or bots_overview_scopes_kills_by_bot_and_mode or bots_live_mode_blocked_by_gates or bots_creation_respects_max_instances_limit" -q` -> `6 passed`.

### Bloque 14: benchmark remoto A/B con `recent_logs` y metrica server-side
- Script `scripts/benchmark_bots_overview.py` extendido:
  - ahora reporta metricas server-side via header `X-RTLAB-Bots-Overview-MS`:
    - `server_p50_ms`, `server_p95_ms`, `server_p99_ms`, `server_avg_ms`
  - agrega trazabilidad de cache:
    - `cache_hits`, `cache_misses`, `cache_hit_ratio`
    - `recent_logs_mode` (enabled/disabled).
- Evidencia remota A/B en Railway:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_ENABLED_30BOTS.md`
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_DISABLED_30BOTS.md`
- Resultado relevante (server-side, 30 bots):
  - `enabled`: `server_p95_ms=74.93`
  - `disabled`: `server_p95_ms=63.034`
  - mejora aproximada: `~15.9%` al desactivar `recent_logs`.
- Observacion operativa critica:
  - cambios de variables en Railway disparan redeploy y en este entorno se observa reset de datos runtime (`/tmp/rtlab_user_data`), con cardinalidad de bots volviendo de `30` a `1`.
  - conclusion: la comparativa robusta exige persistencia de storage o reseed controlado tras cada redeploy.
- Estado final de config en prod:
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false`.

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
- `docs/_archive/UI_UX_RESEARCH_FIRST_FINAL.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`
