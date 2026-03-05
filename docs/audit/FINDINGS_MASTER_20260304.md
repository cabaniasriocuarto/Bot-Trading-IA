# FINDINGS MASTER (Programa Integral + Bot) - 2026-03-04

Objetivo: consolidar TODOS los problemas detectados durante la auditoria integral y la auditoria del cerebro del bot, con estado actual para evitar retrabajo.

Leyenda de estado:
- `ABIERTO`: pendiente de correccion.
- `MITIGADO`: mejorado, pero quedan brechas o deuda tecnica.
- `CERRADO`: resuelto con evidencia en repo.

## Seguridad y gobierno

### FM-SEC-001 - Headers internos sin token proxy (spoof)
- Severidad: CRITICAL
- Estado: CERRADO
- Impacto: escalamiento de privilegios por headers internos falsos.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:4950`
  - `rtlab_autotrader/rtlab_core/web/app.py:5011`
  - `rtlab_autotrader/tests/test_web_live_ready.py:177`
- Fix aplicado:
  - validacion de `x-rtlab-proxy-token` y alerta de intentos de spoof.

### FM-SEC-002 - Fuerza bruta en login
- Severidad: HIGH
- Estado: CERRADO
- Impacto: abuso de `/api/v1/auth/login`.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py` (`LoginRateLimiter` con `backend=sqlite|memory` y tabla `auth_login_rate_limit`).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_auth_login_rate_limit_shared_sqlite_backend_across_instances`).
- Fix aplicado:
  - backend compartido por SQLite para lockout/rate-limit cross-instance (con fallback `memory`).

### FM-SEC-003 - Rate limit general de API
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: riesgo de abuso de endpoints costosos.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:972`
  - `rtlab_autotrader/rtlab_core/web/app.py:5437`

### FM-SEC-004 - Security CI en repo root y branch protection
- Severidad: HIGH
- Estado: CERRADO
- Impacto: gate bloqueante de seguridad activo y estable en branch protegida.
- Evidencia:
  - `/.github/workflows/security-ci.yml` versionado en repo.
  - Branch protection API: `required_status_checks.strict=true`, `contexts=["security"]`.
  - Run `Security CI` verde post-fix: `22697627615` (`success`, job `security` id `65807494809`).

## Ejecucion y runtime operativo

### FM-EXEC-001 - Runtime real no acoplado end-to-end
- Severidad: CRITICAL
- Estado: MITIGADO
- Impacto: no hay garantia de loop OMS/risk/reconciliacion real en runtime web operativo.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py` (`RuntimeBridge._runtime_order_intent` + `_maybe_submit_exchange_runtime_order` con decision por estrategia principal y guardas fail-closed).
  - `rtlab_autotrader/rtlab_core/web/app.py` (`_fetch_exchange_order_status` + `_apply_remote_order_status_to_local` para resolver orden ausente por estado remoto).
  - `rtlab_autotrader/rtlab_core/web/app.py` (estado runtime con `runtime_last_signal_*` para trazabilidad de decision/accion).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`, `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`, `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`, `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`93 passed`).
- Brecha abierta:
  - falta cierre end-to-end del lifecycle de orden real (partial fills/cancel-replace/final states) para declarar runtime totalmente acoplado.

### FM-EXEC-002 - Gate G9 depende de estado/env y no de heartbeat real
- Severidad: CRITICAL
- Estado: CERRADO
- Impacto: posible PASS de G9 sin motor real comprobable.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py` (`evaluate_gates` sincroniza runtime state cuando no recibe snapshot).
  - `rtlab_autotrader/rtlab_core/web/app.py` (`_runtime_contract_snapshot` agrega checks `exchange_*` + freshness).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_g9_live_passes_only_when_runtime_contract_is_fully_ready`).
- Fix aplicado:
  - `G9` ahora se evalua sobre estado runtime actualizado y requiere evidencia exchange + freshness (fail-closed si falta).

### FM-EXEC-003 - `breaker_events` con `NO_DATA` devuelve `ok=true`
- Severidad: HIGH
- Estado: CERRADO
- Impacto: checks protegidos ahora fallan cerrado por defecto cuando `breaker_events` no tiene evidencia.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py` (`breaker_events_integrity(..., strict=True)` y endpoint `/api/v1/diagnostics/breaker-events` con `strict=true` por default).
  - `scripts/ops_protected_checks_report.py` (`--strict` default `true`; override explicito `--no-strict`).
  - `rtlab_autotrader/tests/test_web_live_ready.py`:
    - `test_breaker_events_integrity_endpoint_no_data_strict_fail_closed_by_default`
    - `test_breaker_events_integrity_endpoint_no_data_non_strict_ok`.

### FM-EXEC-004 - Evaluacion de rollout consume payloads sinteticos
- Severidad: HIGH
- Estado: MITIGADO
- Impacto: decisiones de advance/rollback pueden tomar metricas no reales.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:7159`
  - `rtlab_autotrader/rtlab_core/web/app.py:7180`
- Brecha abierta:
  - el bloqueo fail-closed ya aplica a `evaluate-phase`, pero el cierre total depende todavia del runtime real end-to-end (FM-EXEC-001/FM-EXEC-005).

### FM-EXEC-005 - Modulos OMS/reconciliation/risk existen pero no wiring operativo completo en web runtime
- Severidad: HIGH
- Estado: MITIGADO
- Impacto: gap directo para cierre no-live real y paso posterior a live.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/execution/oms.py:21`
  - `rtlab_autotrader/rtlab_core/execution/reconciliation.py:17`
  - `rtlab_autotrader/rtlab_core/risk/risk_engine.py:19`
  - `rtlab_autotrader/rtlab_core/risk/kill_switch.py:15`
  - `rtlab_autotrader/rtlab_core/web/app.py` (`_reconcile` usa `open_orders` locales y cierra ausentes tras grace `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC`).
  - `rtlab_autotrader/rtlab_core/web/app.py` (submit runtime cableado por estrategia/risk/account/open-orders/cooldown antes de `POST /api/v3/order`).
  - `rtlab_autotrader/rtlab_core/web/app.py` (orden ausente en `openOrders` se resuelve via `GET /api/v3/order` antes de cierre local).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`, `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`, `test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`, `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`, `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`, `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`).
- Brecha abierta:
  - runtime ya decide por senal y consulta `order status` para ausentes, pero todavia falta cierre completo de cancel-replace/fills parciales avanzados + wiring de riesgo en el mismo ciclo para declarar wiring operativo total.

## Quant, research y cerebro del bot

### FM-QUANT-001 - Dispatch por `strategy_id` implementado por familias, pero cobertura parcial
- Severidad: MEDIUM
- Estado: MITIGADO
- Impacto: estrategias fuera de familias soportadas pueden caer en fallback.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py:204`
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py:296`
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py:216`
  - `rtlab_autotrader/tests/test_backtest_strategy_dispatch.py:1`
- Brecha abierta:
  - fallback a `trend_pullback` cuando `strict_strategy_id=false`.

### FM-QUANT-002 - `strict_strategy_id` es opt-in
- Severidad: MEDIUM
- Estado: MITIGADO
- Impacto: se puede enmascarar `strategy_id` no soportado si no se activa estricto.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py:192`
  - `rtlab_autotrader/rtlab_core/web/app.py:5318`
  - `rtlab_autotrader/rtlab_core/web/app.py:7970`
  - `rtlab_autotrader/tests/test_web_live_ready.py:2561`
- Brecha abierta:
  - en `POST /api/v1/backtests/run` el flag sigue opt-in por compatibilidad legacy; el enforcement total queda pendiente de migracion global.

### FM-QUANT-003 - `min_trades_per_symbol` en gates de research
- Severidad: HIGH
- Estado: CERRADO
- Impacto: evita promover variantes con muestra debil por simbolo.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1097`
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1127`

### FM-QUANT-004 - Purged CV + CPCV implementados en learning rapido
- Severidad: HIGH
- Estado: CERRADO
- Impacto: anti-leakage cerrado en camino rapido (purged + cpcv ejecutables).
- Evidencia:
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py:659`
  - `rtlab_autotrader/rtlab_core/web/app.py:5261`
  - `rtlab_autotrader/rtlab_core/learning/service.py:440`
  - `rtlab_autotrader/tests/test_web_live_ready.py:1153`
- Fix aplicado:
  - `purged-cv` ejecuta split OOS real con `purge_bars + embargo_bars` en `BacktestEngine`.
  - `cpcv` ejecuta paths combinatoriales reales (`n_splits`, `k_test_groups`, `max_paths`) con trimming por `purge+embargo`.
  - `learning_eval_candidate` propaga `validation_mode` y parametros `cpcv_*` desde settings.
  - `learning/service` deja de marcar `purged_cv/cpcv` como hook-only.

### FM-QUANT-005 - Fallback silencioso en evaluacion de candidato
- Severidad: HIGH
- Estado: CERRADO
- Impacto: puede ocultar errores reales de datos/engine.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:5247`
  - `rtlab_autotrader/rtlab_core/web/app.py:5269`
  - `rtlab_autotrader/tests/test_web_live_ready.py:894`
- Fix aplicado:
  - `_learning_eval_candidate` ahora falla explicito (`ValueError`) ante ausencia de dataset real o `dataset_source` sintetico.

### FM-QUANT-006 - Doble semantica anti-overfitting (proxy + advanced overwrite)
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: trazabilidad de auditoria mas dificil en promotion.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1815`
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1166`
  - `rtlab_autotrader/tests/test_mass_backtest_engine.py:429`
- Fix aplicado:
  - salida separada en `anti_proxy` y `anti_advanced`, manteniendo `anti_overfitting` como alias legacy de compatibilidad.

### FM-QUANT-007 - CompareEngine asume `orderflow_on` por compatibilidad
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: puede esconder mismatch de feature set.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/rollout/compare.py:67`
  - `rtlab_autotrader/rtlab_core/rollout/compare.py:88`
  - `rtlab_autotrader/tests/test_rollout_safe_update.py:130`
- Fix aplicado:
  - `CompareEngine` ahora falla cerrado (`known_feature_set`) cuando el feature set queda `orderflow_unknown`.

### FM-QUANT-008 - Pipeline ML formal de entrenamiento
- Severidad: LOW
- Estado: ABIERTO
- Impacto: el cerebro actual es rule/bandit/research driven, sin pipeline ML productivo formal.
- Evidencia:
  - NO EVIDENCIA de pipeline `fit/predict` en `rtlab_autotrader/rtlab_core/learning` y `rtlab_autotrader/rtlab_core/src/research`.

## Riesgo y politicas

### FM-RISK-001 - Opcion B (no auto-live) forzada fail-closed
- Severidad: HIGH
- Estado: CERRADO
- Impacto positivo: evita cambios live automaticos.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/learning/service.py:91`
  - `rtlab_autotrader/rtlab_core/learning/service.py:660`

### FM-RISK-002 - Enforcement de riesgo real depende de runtime real
- Severidad: HIGH
- Estado: MITIGADO
- Impacto: politicas de riesgo pueden quedar declarativas si no hay wiring runtime real.
- Evidencia:
  - `config/policies/risk_policy.yaml`
  - `rtlab_autotrader/rtlab_core/risk/risk_engine.py:45`
  - `rtlab_autotrader/rtlab_core/web/app.py` (`_load_runtime_risk_policy_thresholds`, hard-kill policy-driven en `RuntimeBridge.sync_runtime_state`).
  - `rtlab_autotrader/rtlab_core/web/app.py` (submit remoto en `testnet/live` se ejecuta despues del calculo de riesgo del mismo ciclo).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle`).
- Brecha abierta:
  - conector de ordenes/fills reales del broker todavia pendiente para enforcement completo sobre fills reales de mercado y escenarios avanzados de cancel-replace.

### FM-RISK-003 - Perfil de riesgo base hardcodeado en learning
- Severidad: LOW
- Estado: CERRADO
- Impacto: posible drift respecto de policy canonica.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/learning/service.py` (`_default_learning_risk_profile` deriva defaults desde `config/policies/risk_policy.yaml`).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_learning_default_risk_profile_prefers_policy_yaml`).

### FM-RISK-004 - Fuente canonica de gates (`config/policies`) con fallback permisivo en `knowledge`
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: riesgo de divergencia si faltan archivos de `config`.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/learning/service.py` (`_canonical_gates_thresholds` usa `config/policies/gates.yaml` y `default_fail_closed` sin fallback a knowledge).
  - `rtlab_autotrader/rtlab_core/rollout/gates.py` (`source_path` canonico `config/policies/gates.yaml`, `source_mode=default_fail_closed` si falta config).
  - `rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py`.
  - `rtlab_autotrader/tests/test_learning_service_gates_source.py`.

## SRE, QA, UX y documentacion

### FM-SRE-001 - Backup/restore y drill operativo
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto positivo: recuperacion validada con hash.
- Evidencia:
  - `scripts/backup_restore_drill.py`
  - `docs/runbooks/BACKUP_RESTORE_USER_DATA.md`
  - `docs/truth/SOURCE_OF_TRUTH.md:80`

### FM-SRE-002 - Alertas operativas avanzadas de drift/costos/slippage en CI/monitoring externo
- Severidad: MEDIUM
- Estado: MITIGADO
- Impacto: observabilidad incompleta para canary/live.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py` (`build_operational_alerts_payload`, `GET /api/v1/alerts` con `include_operational`).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_alerts_include_operational_alerts_for_drift_slippage_api_and_breaker`, `test_alerts_operational_alerts_clear_when_runtime_recovers`).
- Brecha abierta:
  - faltan integraciones de monitoreo externo (dashboards/alert routing) para canary/live.

### FM-QA-001 - E2E de flujo critico integral
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: riesgo de regresion cross-layer (BFF + backend + UI).
- Evidencia:
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_e2e_critical_flow_login_backtest_validate_promote_rollout`).
  - Flujo cubierto: `login -> backtests/run -> runs/validate_promotion -> runs/promote -> rollout/advance`.

### FM-QA-002 - Chaos/recovery tests de runtime
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: baja certeza ante fallas de exchange o storage.
- Evidencia:
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect`).
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers`).

### FM-DOC-001 - Bibliografia raw no versionada en repo
- Severidad: MEDIUM
- Estado: MITIGADO
- Impacto: reproducibilidad local parcial de auditoria bibliografica.
- Evidencia:
  - `docs/reference/BIBLIO_INDEX.md`
  - `docs/reference/biblio_raw/.gitignore`
  - `docs/reference/BIBLIO_ACCESS_POLICY.md`

## Resumen ejecutivo de abiertos reales (must-fix no-live)

1. FM-EXEC-001
2. FM-EXEC-005
3. FM-RISK-002
4. FM-QUANT-008

