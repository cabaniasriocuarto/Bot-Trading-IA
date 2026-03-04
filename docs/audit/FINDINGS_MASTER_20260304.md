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
- Estado: MITIGADO
- Impacto: gate bloqueante de seguridad ya aplicado en `main`; resta estabilizar corrida verde inicial del workflow.
- Evidencia:
  - `/.github/workflows/security-ci.yml` versionado en repo.
  - Branch protection API: `required_status_checks.strict=true`, `contexts=["security"]`.
  - Run inicial `Security CI`: `22674323602` (`failure` en paso `Install security tooling`).
- Brecha abierta:
  - falta una corrida verde post-fix del workflow (`gitleaks` en `RUNNER_TEMP/bin`).

## Ejecucion y runtime operativo

### FM-EXEC-001 - Runtime real no acoplado end-to-end
- Severidad: CRITICAL
- Estado: ABIERTO
- Impacto: no hay garantia de loop OMS/risk/reconciliacion real en runtime web operativo.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:8339`
  - `rtlab_autotrader/rtlab_core/web/app.py:8360`
  - `rtlab_autotrader/rtlab_core/web/app.py:5262`
  - `rtlab_autotrader/rtlab_core/web/app.py:5320`

### FM-EXEC-002 - Gate G9 depende de estado/env y no de heartbeat real
- Severidad: CRITICAL
- Estado: ABIERTO
- Impacto: posible PASS de G9 sin motor real comprobable.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:900`
  - `rtlab_autotrader/rtlab_core/web/app.py:4943`
  - `rtlab_autotrader/rtlab_core/web/app.py:5185`

### FM-EXEC-003 - `breaker_events` con `NO_DATA` devuelve `ok=true`
- Severidad: HIGH
- Estado: MITIGADO
- Impacto: checks protegidos pueden pasar sin evidencia real de eventos.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:1806`
  - `rtlab_autotrader/rtlab_core/web/app.py:8850`
  - `scripts/ops_protected_checks_report.py:166`
- Brecha abierta:
  - el endpoint mantiene `strict=false` por default para compatibilidad; si un consumidor externo no usa `strict=true`, `NO_DATA` puede seguir no-bloqueante.

### FM-EXEC-004 - Evaluacion de rollout consume payloads sinteticos
- Severidad: HIGH
- Estado: MITIGADO
- Impacto: decisiones de advance/rollback pueden tomar metricas no reales.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/web/app.py:7159`
  - `rtlab_autotrader/rtlab_core/web/app.py:7180`
- Brecha abierta:
  - el bloqueo fail-closed ya aplica a `evaluate-phase`, pero el cierre total depende todavia del runtime real end-to-end (FM-EXEC-001/FM-EXEC-002).

### FM-EXEC-005 - Modulos OMS/reconciliation/risk existen pero no wiring operativo completo en web runtime
- Severidad: HIGH
- Estado: ABIERTO
- Impacto: gap directo para cierre no-live real y paso posterior a live.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/execution/oms.py:21`
  - `rtlab_autotrader/rtlab_core/execution/reconciliation.py:17`
  - `rtlab_autotrader/rtlab_core/risk/risk_engine.py:19`
  - `rtlab_autotrader/rtlab_core/risk/kill_switch.py:15`

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
- Estado: ABIERTO
- Impacto: politicas de riesgo pueden quedar declarativas si no hay wiring runtime real.
- Evidencia:
  - `config/policies/risk_policy.yaml`
  - `rtlab_autotrader/rtlab_core/risk/risk_engine.py:45`
  - `rtlab_autotrader/rtlab_core/web/app.py:5262`

### FM-RISK-003 - Perfil de riesgo base hardcodeado en learning
- Severidad: LOW
- Estado: ABIERTO
- Impacto: posible drift respecto de policy canonica.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/learning/brain.py:10`

### FM-RISK-004 - Fuente canonica de gates (`config/policies`) con fallback permisivo en `knowledge`
- Severidad: MEDIUM
- Estado: MITIGADO
- Impacto: riesgo de divergencia si faltan archivos de `config`.
- Evidencia:
  - `rtlab_autotrader/rtlab_core/learning/service.py:121`
  - `rtlab_autotrader/rtlab_core/learning/service.py:137`
  - `rtlab_autotrader/rtlab_core/rollout/gates.py:45`

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
- Estado: ABIERTO
- Impacto: observabilidad incompleta para canary/live.
- Evidencia:
  - `docs/truth/NEXT_STEPS.md:96`

### FM-QA-001 - E2E de flujo critico integral
- Severidad: MEDIUM
- Estado: CERRADO
- Impacto: riesgo de regresion cross-layer (BFF + backend + UI).
- Evidencia:
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_e2e_critical_flow_login_backtest_validate_promote_rollout`).
  - Flujo cubierto: `login -> backtests/run -> runs/validate_promotion -> runs/promote -> rollout/advance`.

### FM-QA-002 - Chaos/recovery tests de runtime
- Severidad: MEDIUM
- Estado: ABIERTO
- Impacto: baja certeza ante fallas de exchange o storage.
- Evidencia:
  - NO EVIDENCIA de suite chaos para runtime operativo real.

### FM-DOC-001 - Bibliografia raw no versionada en repo
- Severidad: MEDIUM
- Estado: ABIERTO
- Impacto: reproducibilidad local parcial de auditoria bibliografica.
- Evidencia:
  - `docs/reference/BIBLIO_INDEX.md`
  - `docs/reference/biblio_raw/.gitignore`
  - `docs/truth/SOURCE_OF_TRUTH.md:27`

## Resumen ejecutivo de abiertos reales (must-fix no-live)

1. FM-EXEC-001
2. FM-EXEC-002
3. FM-EXEC-003
4. FM-EXEC-004
5. FM-EXEC-005
6. FM-QA-001
7. FM-RISK-002
