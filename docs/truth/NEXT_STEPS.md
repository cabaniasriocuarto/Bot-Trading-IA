# NEXT STEPS (Prioridades Reales)

Fecha: 2026-03-04

## Tramo vigente (cleanroom + staging online, sin LIVE)
- [x] Documentacion ordenada con indice unico:
  - `docs/START_HERE.md`
  - `docs/audit/INDEX.md`
  - `docs/_archive/README_ARCHIVE.md`
- [x] App online en staging (solo no-live):
  - frontend: `https://bot-trading-ia-staging.vercel.app`
  - backend: `https://bot-trading-ia-staging.up.railway.app`
  - health backend esperado: `ok=true`, `mode=paper`, `runtime_ready_for_live=false`.
- [x] Runbooks de rollback documentados:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- [x] Policy de logging seguro publicada:
  - `docs/security/LOGGING_POLICY.md` (CWE-532).

## Proximo tramo operativo (sin habilitar LIVE)
1. Ejecutar smoke diario en staging (login + `/api/v1/health` + `/api/v1/bots`) y registrar evidencia en `docs/audit/`.
2. Mantener enforcement no-live en entornos de prueba:
   - `LIVE_TRADING_ENABLED=false`
   - `KILL_SWITCH_ENABLED=true`
   - `MODE/TRADING_MODE=paper` (o `testnet` cuando aplique).
3. Cerrar pendientes tecnicos de runtime end-to-end (orden/fill/reconciliacion/costos) antes de cualquier canary LIVE.
4. Revalidar security CI y branch protection en cada release de hardening.
5. Preparar checklist final paper -> testnet -> canary -> live (sin ejecutar live hasta aprobacion explicita).

## Actualizacion tecnica AP-8001 (2026-03-04)
- [x] BFF fail-closed para fallback mock en error de backend:
  - `production/staging` no permiten fallback mock.
  - `USE_MOCK_API=false` bloquea fallback en cualquier entorno.
- [x] Reglas centralizadas reutilizadas por:
  - `src/app/api/[...path]/route.ts`
  - `src/lib/events-stream.ts`
- Evidencia:
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar wiring runtime broker/exchange end-to-end (orden/fill/reconciliacion real) y corrida verde de `Security CI` root.

## Actualizacion tecnica AP-8002 (2026-03-04)
- [x] Workflow `security-ci` endurecido para instalar `gitleaks` desde release oficial versionado (`8.30.0`) con retries.
- [x] Fallback agregado a install script versionado (`v8.30.0`) + check fail-closed de binario instalado.
- [x] Export `PATH` en el mismo step de instalacion para validar `gitleaks version` en esa corrida.
- [x] Baseline canónica versionada para CI:
  - `docs/security/gitleaks-baseline.json`
  - `scripts/security_scan.sh` actualizado para usarla por defecto.
- [x] `setup-python` en Security CI alineado a `3.11`.
- [x] `actions/checkout` actualizado a `fetch-depth: 0` para alinear `gitleaks git` con baseline historica.
- [x] Corrida verde validada en GitHub Actions (`Security CI`) y `FM-SEC-004` cerrado.
- Evidencia local:
  - cambio en `/.github/workflows/security-ci.yml` (checkout + install tooling).
  - reproduccion del fallo en clone shallow (`1 commit scanned`, `leaks found: 1`) y validacion PASS al convertir a historial completo (`88 commits scanned`, `no leaks found`).
  - run GitHub Actions `22697627615` -> `success` (job `security` `65807494809`).

## Actualizacion tecnica AP-8007 (2026-03-04)
- [x] Thresholds de gates unificados a fuente canonica `config/policies/gates.yaml`.
- [x] Eliminado fallback permisivo a `knowledge/policies/gates.yaml` en learning thresholds.
- [x] Fail-closed aplicado cuando falta config (`pbo/dsr` requeridos + defaults estrictos).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).
- Pendiente inmediato:
  - completar runtime real end-to-end (broker/exchange) y confirmar corrida verde del workflow `Security CI` en GitHub.

## Actualizacion tecnica AP-8011 (2026-03-04)
- [x] Optimizacion incremental aplicada en `/api/v1/bots`:
  - carga lazy de recomendaciones en `cache miss`;
  - indexado de runs limitado a estrategias de pools activos;
  - cap por `(strategy_id, mode)` con `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE`.
- [x] Regresion funcional del endpoint:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- [ ] Pendiente de cierre:
  - rerun benchmark remoto para confirmar `p95` estable en entorno productivo (objetivo `< 300ms` sostenido).

## Actualizacion tecnica AP-8003 (2026-03-04)
- [x] Reconciliacion runtime alineada a semantica real de `openOrders`:
  - compara exchange vs `OMS.open_orders()` (no incluye ordenes locales cerradas).
- [x] Cierre de ordenes locales abiertas ausentes en exchange con grace:
  - `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`).
- [x] Tests nuevos de regresion runtime en verde:
  - `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`
  - `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).
- Pendiente inmediato:
  - completar wiring de ejecucion real por señales (no solo seed/diagnose/reconcile), y rerun de checks protegidos + benchmark remoto.


## Actualizacion tecnica AP-8012 (2026-03-04)
- [x] `breaker_events` en modo fail-closed por defecto:
  - `store.breaker_events_integrity(..., strict=True)` default estricto.
  - endpoint `/api/v1/diagnostics/breaker-events` con `strict=true` default.
- [x] `ops_protected_checks_report.py` endurecido:
  - `--strict` default `true`.
  - `--no-strict` agregado como override explicito.
- [x] `FM-EXEC-003` cerrado.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.
## Actualizacion tecnica AP-BOT-1001/AP-BOT-1002 (2026-03-04)
- [x] AP-BOT-1001: coherencia de ejecucion por estrategia/familia en BacktestEngine.
- [x] AP-BOT-1002: inferencia `orderflow_feature_set` fail-closed + check `known_feature_set` en promotion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.

## Actualizacion tecnica AP-BOT-1003 (2026-03-04)
- [x] Estabilizacion de `/api/v1/bots` para cardinalidad alta:
  - auto-disable de logs recientes en polling default con muchos bots (`BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT`, default `40`);
  - override explicito `recent_logs=true` preservado;
  - cache key separa `source=default|explicit`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Siguiente AP recomendado:
  - cerrar runtime real end-to-end (idempotencia submit/cancel/fill + reconciliacion de posiciones/ordenes externas).

## Actualizacion tecnica AP-BOT-1004 (2026-03-04)
- [x] Runtime `testnet/live` sin avance de fills simulados en loop local.
- [x] OMS local sincronizado desde `openOrders` para mejorar coherencia de reconciliacion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`9 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato:
  - wiring de submit/cancel/fill real con `client_order_id` idempotente y reconciliacion de posiciones (no solo open orders).

## Actualizacion tecnica AP-BOT-1005 (2026-03-04)
- [x] Cancel remoto idempotente por `client_order_id/order_id` en runtime `testnet/live` para `stop/kill/mode_change`.
- [x] Parser comun de `openOrders` reutilizado en reconciliacion + cancel.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`10 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato de runtime real:
  - submit real idempotente (`newClientOrderId`) con pipeline de señales/ejecución, y reconciliacion de posiciones (no solo órdenes abiertas).

## Actualizacion tecnica AP-BOT-1006 (2026-03-04)
- [x] Submit remoto idempotente agregado en runtime `testnet/live` con `newClientOrderId` y ventana configurable.
- [x] Feature flag segura por defecto (`RUNTIME_REMOTE_ORDERS_ENABLED=false`) para no alterar operacion no-live actual.
- [x] Trazabilidad runtime agregada (`runtime_last_remote_submit_at`, `runtime_last_remote_client_order_id`, `runtime_last_remote_submit_error`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.
- Pendiente inmediato:
  - cerrar `AP-BOT-1007`: reconciliacion de posiciones reales (`/api/v3/account`) y wiring de costos/fills finales end-to-end.

## Actualizacion tecnica AP-BOT-1007 (2026-03-04)
- [x] Reconciliacion de posiciones runtime `testnet/live` contra account snapshot real (`/api/v3/account`).
- [x] Posiciones runtime/risk priorizan balances reconciliados cuando estan disponibles.
- [x] Fallback seguro a posiciones derivadas de `openOrders` cuando account snapshot falla.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`7 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1008`: wiring final de costos/fills netos por ejecucion real (fees/slippage/funding por run/runtime) para cierre no-live.

## Actualizacion tecnica AP-BOT-1008 (2026-03-04)
- [x] Costos runtime por fill-delta integrados en `execution metrics` (fees/spread/slippage/funding/total).
- [x] Reset por sesion runtime (`start`/`mode_change`) para evitar mezcla de acumulados.
- [x] Fail-closed de costos runtime en telemetry sintetica.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1009`: hardening de seguridad operativa restante (`--password` en workflows/scripts remotos y validacion CI security root).

## Actualizacion tecnica AP-BOT-1009 (2026-03-04)
- [x] Eliminado uso de `--password` en automatizacion remota (workflows + `scripts/*.ps1`).
- [x] Scripts remotos endurecidos (`seed_bots_remote.py`, `check_storage_persistence.py`): `--password` queda deprecado y bloqueado por defecto (requiere `ALLOW_INSECURE_PASSWORD_CLI=1`).
- [x] Security CI reforzado con guard fail-closed para detectar regresiones de `--password`.
- [x] Revalidacion local de seguridad ejecutada en PASS (`pip-audit` + `gitleaks`).
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\Program Files\Git\bin\bash.exe scripts/security_scan.sh` -> PASS.
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.
- Pendiente inmediato:
  - cerrar `AP-BOT-1010`: estabilizacion final operativa (latencia/soak/checklist no-live de cierre).

## Actualizacion tecnica AP-BOT-1010 (2026-03-04)
- [x] Checklist formal de cierre no-live generado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- [x] Tramo no-live/testnet consolidado en estado GO.
- [ ] LIVE postergado hasta fase final (configuracion APIs/canary/rollback).
- Pendiente inmediato:
  - avanzar con runtime orientado por senales de estrategia para reducir brecha FM-EXEC-001/FM-EXEC-005.

## Actualizacion tecnica AP-BOT-1011 (2026-03-04)
- [x] Runtime remoto ahora decide submit desde estrategia principal (no semilla ciega).
- [x] Guardas fail-closed previas al submit:
  - estrategia principal valida y habilitada;
  - `risk.allow_new_positions=true`;
  - sin posiciones abiertas reconciliadas;
  - sin cooldown activo ni open orders pendientes.
- [x] Trazabilidad de senal runtime agregada:
  - `runtime_last_signal_action`,
  - `runtime_last_signal_reason`,
  - `runtime_last_signal_strategy_id`,
  - `runtime_last_signal_symbol`,
  - `runtime_last_signal_side`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Pendiente inmediato:
  - cerrar lifecycle final de ejecucion real (partial fills/cancel-replace/estado final de orden) para pasar FM-EXEC-001/FM-EXEC-005 a CERRADO.

## Actualizacion tecnica AP-BOT-1012 (2026-03-04)
- [x] Runtime ahora resuelve orden ausente via `order status` remoto antes de cerrar localmente.
- [x] Cierre por estado remoto implementado:
  - `FILLED`/`CANCELED`/`EXPIRED`/`REJECTED` con mapeo de estado local consistente.
- [x] Si orden sigue `NEW/PARTIALLY_FILLED/PENDING_CANCEL`, se mantiene abierta y se reinyecta al snapshot de reconciliacion.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Pendiente inmediato:
  - cerrar parte final de runtime end-to-end (cancel-replace/partial fills avanzados + wiring de riesgo en el mismo ciclo de decision).

## Actualizacion tecnica AP-BOT-1013 (2026-03-04)
- [x] Submit remoto movido despues del calculo de riesgo del mismo ciclo.
- [x] Submit bloqueado cuando el decisionado de riesgo del ciclo actual no permite nuevas posiciones.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - cerrar tramo restante de runtime real (cancel-replace/fills parciales avanzados) y revalidar checks protegidos + benchmark remoto.

## Actualizacion tecnica AP-BOT-1014 (2026-03-04)
- [x] Submit runtime reutiliza snapshot de cuenta del ciclo y evita doble `GET /api/v3/account`.
- [x] Se mantiene gate funcional de posiciones abiertas con menor overhead de API.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - completar cierre de runtime end-to-end restante (cancel-replace/fills parciales avanzados) y ejecutar checks protegidos remotos.

## Actualizacion tecnica AP-BOT-1015 (2026-03-04)
- [x] Cobertura de regresion agregada para estados remotos:
  - `PARTIALLY_FILLED`,
  - `REJECTED`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Pendiente inmediato:
  - completar bloque de runtime real restante (cancel-replace avanzado + revalidacion remota protegida).

## Revalidacion bibliografica AP-BOT-1006..1010 (2026-03-04)
- [x] Cerrada validacion bibliografica completa por patch:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- [x] En cada AP se declaro `NO EVIDENCIA LOCAL` cuando aplico y se uso solo fuente primaria oficial para cubrir el vacio.
- Pendiente inmediato:
  - mantener este criterio (local-first + fuentes primarias) para AP nuevos.

## Cierre de auditoria integral (2026-03-04)
- Auditoria completa finalizada y documentada en:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Estado:
  - `LIVE`: NO GO (bloqueante tecnico de ejecucion real end-to-end).
  - `No-live/testnet`: GO y estable para continuar hardening antes de conectar APIs LIVE.
- Proximo tramo recomendado (orden):
1. `AP-8001` fail-closed de mock API en BFF.
2. `AP-8002` eliminar `--password` en scripts/workflows remotos.
3. `AP-8007` unificar thresholds de gates (`config` vs `knowledge`) con test de drift.
4. `AP-8011` estabilizar `/api/v1/bots` a `p95 < 300ms` sostenido.
5. `AP-8003` cerrar adapter de ejecucion real con idempotencia/reconciliacion.

## Referencias canonicas de reparacion (2026-03-04)
- Registro maestro de problemas: `docs/audit/FINDINGS_MASTER_20260304.md`
- Plan final de implementacion: `docs/audit/ACTION_PLAN_FINAL_20260304.md`

## Progreso AP (plan final)
- Total AP (plan original): `23`
- AP cerrados (plan original): `23`
- AP adicionales fase 2: `2` (`AP-7001`, `AP-7002`)
- AP cerrados (total extendido): `25`
- AP pendientes (total extendido): `0`
- Avance global extendido: `100%` (`25/25`)

## Estado post-plan AP
- El plan AP original queda ejecutado al `100%`, pero el programa **todavia NO esta listo para LIVE**.
- Hallazgos criticos abiertos para fase siguiente:
  - `FM-EXEC-001`
  - `FM-EXEC-005`
  - `FM-QUANT-008`
  - `FM-RISK-002`
- Hallazgos cerrados en fase 2:
  - `FM-EXEC-002` (G9 reforzado con sync runtime + evidencia exchange + freshness checks).
  - `FM-RISK-003` (learning risk profile por defecto ahora policy-driven).

## Evidencia tecnica fase 2 (2026-03-04)
- Cambios aplicados:
  - `AP-7001`: hardening runtime/gates (`exchange evidence`, `sync runtime`, reconciliacion `openOrders`, fail-closed sintetico).
  - `AP-7002`: risk policy wiring en runtime + default risk profile policy-driven en learning.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.

## Cierre PARTE 7/7 (cerebro del bot)
- Auditoria de cerebro cerrada: decision/learning/rollout validados por codigo.
- Se mantiene politica operativa: **no conectar LIVE todavia**.
- Checklist inmediato de cierre no-live (orden obligatorio):
1. Acoplar runtime operativo real a OMS/risk/reconciliacion y reemplazar payloads sinteticos de `status`/`execution`.
   - avance: AP-0001/AP-0002 + AP-1001/AP-1002/AP-1003/AP-1004 + AP-2001/AP-2002/AP-2003 + AP-7001/AP-7002 implementados (`RuntimeBridge`, telemetry fail-closed, breaker strict, bloqueo de evaluate-phase sin telemetry real, G9 con sync runtime/evidencia exchange y risk policy wiring).
   - pendiente: wiring broker/exchange real end-to-end para ordenes/fills reales (no solo `diagnose` + `openOrders`).
2. Versionar y activar `/.github/workflows/security-ci.yml` en GitHub Actions + branch protection.
   - avance: AP-4001 versionado en branch (`0dbf55d`) + AP-4002 aplicado en GitHub (`main` con required check `security`, `strict=true`) + AP-4003 cerrado (login lockout/rate-limit con backend compartido sqlite).
   - pendiente: corrida verde de `Security CI` tras fix de instalacion de `gitleaks` (run `22674323602` fallo en `Install security tooling`; fix aplicado en workflow, pendiente rerun).
3. Ejecutar hardening final (alertas/recovery/e2e criticos) y volver a correr checks protegidos con evidencia.

## Bloque 3 (quant/learning) - estado actual
- [x] AP-3003: eliminado fallback silencioso de `_learning_eval_candidate` (fail-closed explicito).
- [x] AP-3004: separadas salidas `anti_proxy` y `anti_advanced` en research (con alias legacy).
- [x] AP-3005: `CompareEngine` fail-closed cuando `orderflow_feature_set` queda unknown.
- [x] AP-3006: `strict_strategy_id=true` obligatorio en research/promotion no-demo.
- [x] AP-3001: Purged CV + embargo real en learning/research rapido.
- [x] AP-3002: CPCV real en learning/research.

## Estimacion de bloques restantes (sin LIVE)
- Objetivo declarado: terminar programa en modo no-live/testnet y dejar LIVE para el final.
- Estimacion actual: **faltan 3 bloques tecnicos** para cierre no-live robusto.
1. Bloque A - Runtime de verdad no-live:
   - cerrar reconciliacion/heartbeat sobre broker real (hoy no-live interno).
2. Bloque B - CI/seguridad protegida en root:
   - versionar/activar workflow security root y exigirlo en branch protection.
3. Bloque C - Hardening final de operacion:
   - cerrar gaps de observabilidad/alertas y completar pruebas criticas faltantes (integration/e2e de flujos peligrosos).
- Bloque LIVE real: **postergado por decision operativa** (configuracion de APIs y canary al final).

## Estado de cierre no-live (2026-03-03)
- [x] Benchmark remoto en GitHub VM en PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin retries `429`).
- [x] `Remote Protected Checks (GitHub VM)` en PASS con `strict=true`:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- [x] Revalidacion de seguridad ejecutada en modo estricto (`scripts/security_scan.ps1 -Strict`) sin vulnerabilidades ni leaks.
- [ ] `G9_RUNTIME_ENGINE_REAL` en `PASS` (pendiente runtime real OMS/broker) [POSTERGADO por decision operativa].
- [ ] Habilitacion LIVE real (bloqueada hasta resolver item anterior) [POSTERGADO por decision operativa].
- Criterio actual de tramo: priorizar estabilidad testnet/no-live; LIVE se retoma al final con APIs definitivas configuradas.

## Bloqueantes LIVE (auditoria comite)
1. Completar runtime de ejecucion real contra broker/exchange (paper/testnet/live) con reconciliacion externa y telemetria estricta fail-closed.

## Prioridad 1 (RC operativo)
1. Configurar `INTERNAL_PROXY_TOKEN` en Vercel + Railway y validar que requests directos al backend sin token fallen (hard check de T1 en entorno real).
2. Validar `runtime_engine=real` solo cuando exista loop de ejecucion real y reconciliacion; mantener `simulated` en cualquier otro caso.
3. Confirmar gates LIVE con `G9_RUNTIME_ENGINE_REAL` en PASS antes de habilitar canary.
4. Remediar benchmark remoto de `/api/v1/bots`:
   - ya desplegado cache TTL/invalidacion; evidencia actual sigue en FAIL con 100 bots (`p95=1458.513ms`),
   - mantener `BOTS_MAX_INSTANCES` en rango conservador (recomendado Railway actual: `30`, bajar a `20` si aparece saturacion),
   - probar en Railway `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false` y medir impacto real de latencia,
   - usar headers `X-RTLAB-Bots-Overview-*` y `debug_perf=true` para separar hit/miss y medir efecto de cache,
   - instrumentar timing interno por etapas en `get_bots_overview` (kpis/logs/kills/serialization),
   - agregar indice/materializacion para datos de overview de bots (si el costo principal viene de agregacion en request),
   - rerun remoto con `100` bots y objetivo `p95 < 300ms`.
   - estabilizar storage persistente para `RTLAB_USER_DATA_DIR` (evitar `/tmp`) antes de benchmarks comparativos: hoy cada redeploy puede resetear bots/runs y contaminar evidencia.
5. Validar integridad de `breaker_events` (`bot_id/mode`) y monitorear volumen de `unknown`.
6. Afinar thresholds/parametros por estrategia del dispatcher de `BacktestEngine` y agregar `fail-closed` explicito para strategy_ids no soportados en modo estricto.
7. Validar en entorno desplegado que `surrogate_adjustments` se mantenga apagado fuera de `execution_mode=demo` y que promotion quede bloqueada cuando se active.

## Prioridad 2 (operacion + hardening)
1. Agregar rotacion/expiracion para `INTERNAL_PROXY_TOKEN` y checklist de cambio en runbook.
2. [x] Lockout/rate-limit de login backend con backend compartido sqlite (AP-4003 cerrado).
3. Instrumentar alertas de seguridad para intentos de headers internos sin token valido.
4. Definir policy de despliegue que impida `NODE_ENV=production` con defaults de auth.
5. Asegurar que backend no sea accesible en bypass directo (allowlist/zero-trust) aun con token interno.
6. Branch protection para requerir job `security` antes de merge a `main` (AP-4002 completado).
7. Rotar claves de exchange (testnet/live) y validar que no exista hardcode en archivos locales.

## Prioridad 3 (UX / producto)
1. Deploy frontend/backend y validacion visual completa de UI `Research-first`
2. Validar `Settings -> Diagnostico` (WS/Exchange)
3. Validar `Backtests / Runs -> Validate -> Promote -> Rollout / Gates`
4. Resolver infraestructura testnet/live (si reaparece bloqueo de red/egress)
5. Validar Modo Bestia fase 1 en produccion (cola, budget governor, stop-all, resume)
6. Validar en produccion el bloqueo de `bots mode=live` por gates y revisar mensajes de bloqueo en UI
7. Medir `/api/v1/bots` con 100 bots y verificar objetivo p95 `< 300ms` (tracing real en entorno productivo)
8. Verificar integridad de `breaker_events` (bot_id/mode) en logs reales y alertar filas `unknown_bot`/`unknown` por encima de umbral

## Prioridad 4 (UX / producto)
1. Virtualizacion adicional en tablas grandes restantes (D2 comparador ya virtualizado)
2. Deep Compare avanzado (heatmap mensual, rolling Sharpe, distribucion retornos)
3. Componente reutilizable unico para empty states / CTA
4. Tooltips consistentes en acciones de runs (rerun/clone/export cuando existan)

## Prioridad 5 (robustez / automatizacion)
1. [x] AP-5001: suite E2E critica backend (`login -> backtest -> validate -> promote -> rollout`) cerrada.
2. [x] AP-5002: chaos/recovery runtime (`exchange down -> reconnect`, `desync reconcile -> recover`) cerrado.
3. [x] AP-5003: alertas operativas minimas en `/api/v1/alerts` (drift/slippage/api_errors/breaker_integrity) cerrada.
4. Extender `Fee/Funding` a multi-exchange avanzado (hoy Binance + Bybit base + fallback) con manejo de limites/errores por proveedor
5. Integrar proveedor financiero especifico (mapeos/contratos) sobre el adaptador remoto generico de fundamentals
6. Order Flow L1 full (trade tape/BBO real) sobre VPIN proxy actual
7. Materializar agregados para overview de bots (si sube cardinalidad) e indices adicionales por ventana temporal
8. Revisar y refrescar `gitleaks-baseline.json` cuando se remedien hallazgos historicos.

## Prioridad 6 (nice-to-have)
1. UI de experimentos MLflow (capability)
2. SBOM firmado por release
3. Dashboards externos para canary live (Prometheus/Grafana)
4. Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)
