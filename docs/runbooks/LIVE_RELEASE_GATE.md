# Runbook: Final live release gate

Fecha: 2026-03-25

## Objetivo

Dejar un gate final auditable para decidir `GO`, `GO con restricciones` o `NO-GO` sin inventar readiness ni ocultar evidencia faltante.

## Alcance real de esta decision

- aplica al estado actual del repo y a la evidencia operativa/documental disponible;
- no reemplaza la revalidacion humana en el entorno objetivo inmediatamente antes de habilitar `LIVE_SERIO`;
- usa como evidencia fuerte:
  - QA backend/live de `RTLOPS-53`
  - Playwright smoke minima de `RTLOPS-35`
  - runbooks/rollback de `RTLOPS-37`
  - contracts y gates reales ya cerrados en `RTLOPS-47`, `RTLOPS-23`, `RTLOPS-29`, `RTLOPS-30`, `RTLOPS-54`, `RTLOPS-51`, `RTLOPS-52`

## Decision actual

- decision: `GO con restricciones`
- aplica a:
  - repo actual
  - local deterministico
  - continuacion del release path hasta la decision operatoria final
- no equivale a:
  - `GO` limpio para habilitar `LIVE_SERIO` sin una reevaluacion fresca en el entorno objetivo

## Matriz de evidencia

### 1) Preflight

- estado actual: `PASS` como contrato y gate fail-closed; sin snapshot fresco de entorno objetivo en este bloque
- evidencia verificada ahora:
  - `execution_canary_start_holds_when_preflight_is_expired` -> PASS
- lectura operativa:
  - no hay evidencia nueva de `preflight PASS` en staging/testnet/live serio hoy;
  - si el preflight real falla o esta expirado, la promocion queda bloqueada

### 2) Runtime / G9

- estado actual: contrato real presente y validado en pass/fail segun evidencia
- evidencia verificada ahora:
  - `test_backend_qa_live.py` -> PASS
  - `g9_live_passes_only_when_runtime_contract_is_fully_ready` -> PASS
- lectura operativa:
  - el gate de runtime existe y falla cerrado;
  - sigue faltando una reevaluacion fresca del entorno objetivo antes de declarar `LIVE_SERIO` listo

### 3) Account surface

- estado actual: surface canonica persistida y exigida por `G9_RUNTIME_ENGINE_REAL`
- evidencia verificada ahora:
  - `g9_live_fails_when_account_surface_is_not_tradeable` -> PASS
- lectura operativa:
  - la regla esta cerrada;
  - no existe en este bloque una lectura fresca de cuenta real/testnet-live del entorno objetivo

### 4) Reconciliation

- estado actual: bloquea o exige manual review cuando falta evidencia remota suficiente
- evidencia verificada ahora:
  - `g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers` -> PASS
  - `execution_canary_recommends_rollback_when_reconciliation_turns_blocking` -> PASS
- lectura operativa:
  - la reconciliacion ya pesa como blocker real;
  - sigue faltando revalidacion fresca con estado remoto real al momento de operar

### 5) Health / alerts / safety

- estado actual: surfaces canonicas presentes, con bloqueo fail-closed y resumen explicable
- evidencia verificada ahora:
  - `live_mode_fails_when_operational_safety_gate_blocks` -> PASS
  - `live_start_fails_when_operational_safety_gate_blocks` -> PASS
  - `execution_health_summary_and_evaluate_endpoints_return_and_persist_contract` -> PASS
  - `execution_alert_endpoints_expose_catalog_history_and_lifecycle` -> PASS
  - `test_backend_qa_live.py` -> PASS
- lectura operativa:
  - el sistema ya tiene lectura consolidada y bloqueos reales;
  - no hay snapshot fresco del entorno objetivo que permita declarar ausencia actual de blockers criticos

### 6) Canary / rollback

- estado actual:
  - canary controller existe y responde fail-closed
  - rollback real soportado por rollout manager
  - rollback del canary controller sigue siendo recomendacion humana mientras `rollback_execution_supported = false`
- evidencia verificada ahora:
  - `execution_canary_status_and_endpoints_expose_contract` -> PASS
  - `execution_canary_recommends_rollback_when_reconciliation_turns_blocking` -> PASS
- lectura operativa:
  - existe ruta real de retirada a baseline;
  - no debe sobredeclararse rollback canonico automatico del canary controller

### 7) Shadow

- estado actual: `LIVE_SHADOW` operativo y fail-closed cuando falta wiring critico
- evidencia verificada ahora:
  - `rollout_shadow_status_and_signal_are_fail_closed_until_runtime_live_is_ready` -> PASS
  - `rollout_api_blending_preview_records_telemetry` -> PASS
  - `rollout_api_evaluate_phase_fail_closed_when_runtime_telemetry_synthetic` -> PASS
- lectura operativa:
  - shadow aporta evidencia complementaria y observabilidad;
  - no sustituye readiness de `LIVE_SERIO`

### 8) QA backend

- estado actual: quality gates backend/live existentes y revalidados
- evidencia verificada ahora:
  - `.\\rtlab_autotrader\\.venv\\Scripts\\pytest.exe rtlab_autotrader/tests/test_backend_qa_live.py --maxfail=1 --basetemp .\\rtlab_autotrader\\.tmp\\pytest-backend-qa-live-final -q` -> PASS (`3 passed`)
  - `.\\rtlab_autotrader\\.venv\\Scripts\\pytest.exe rtlab_autotrader/tests/test_web_live_ready.py -k "execution_canary_start_holds_when_preflight_is_expired or live_mode_fails_when_operational_safety_gate_blocks or live_start_fails_when_operational_safety_gate_blocks or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_account_surface_is_not_tradeable or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers or execution_health_summary_and_evaluate_endpoints_return_and_persist_contract or execution_alert_endpoints_expose_catalog_history_and_lifecycle or execution_canary_recommends_rollback_when_reconciliation_turns_blocking or execution_canary_status_and_endpoints_expose_contract or config_policies_endpoint_exposes_numeric_policy_bundle" --maxfail=1 --basetemp .\\rtlab_autotrader\\.tmp\\pytest-qa-live-ready-final -q` -> PASS (`11 passed`)
- lectura operativa:
  - evidencia fuerte y fresca para contrato backend/local;
  - no reemplaza verificacion del entorno operativo real

### 9) Playwright smoke

- estado actual: smoke minima/operatoria presente y revalidada
- evidencia verificada ahora:
  - `npm.cmd --prefix rtlab_dashboard run test:playwright` -> PASS (`3 passed`)
- lectura operativa:
  - evidencia complementaria de flujo operador visible;
  - no sustituye QA backend ni readiness live

### 10) Runbooks / incidentes

- estado actual: runbooks reales presentes
- evidencia heredada vigente:
  - `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
  - `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
  - `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- lectura operativa:
  - existe camino real de diagnostico, contencion y rollback;
  - no se reejecutan en este bloque porque son evidencia documental/operativa

## Blockers duros de release

- ninguno confirmado hoy en repo/docs/tests para cerrar el gate como decision auditable del programa

## Blockers duros de promocion de stage

- ausencia de evidencia fresca del entorno objetivo para todos estos puntos al momento de activar `LIVE_SERIO`:
  - `preflight PASS`
  - `G9_RUNTIME_ENGINE_REAL = PASS`
  - `account surface` fresca y tradeable
  - reconciliacion sin `BLOCKED` ni `MANUAL_REVIEW_REQUIRED`
  - `health_summary` sin blockers duros
  - `safety_summary.blocking_bool = false`
  - ausencia de alertas `CRITICAL` impeditivas en `SAFETY` o `HEALTH`
  - canary sin `HOLD` ni `ROLLBACK_RECOMMENDED` para el tramo a promover

## Riesgos aceptables solo con restricciones

- la mayor parte de la evidencia live seria sigue siendo contractual/local o heredada de bloques previos y no una lectura fresca del entorno objetivo
- la smoke Playwright fue revalidada localmente, no contra staging/real con credenciales operativas
- el canary controller sigue recomendando rollback humano cuando `rollback_execution_supported = false`

## Observaciones no bloqueantes

- el sync administrativo `RTLOPS-51 / RTLOPS-54` sigue pendiente en Linear UI
- las notas antiguas de `NO GO` mas profundas en `docs/truth` y `CHANGELOG` son snapshots historicos; la decision vigente es la de este gate fechado 2026-03-25

## Que falta para subir a GO limpio

- reevaluacion en el entorno objetivo inmediatamente antes de operar:
  - `POST /api/v1/gates/reevaluate`
  - `POST /api/v1/execution/health/evaluate`
  - `POST /api/v1/execution/alerts/evaluate`
- snapshot fresco y archivado de:
  - `GET /api/v1/gates`
  - `GET /api/v1/rollout/status`
  - `GET /api/v1/execution/health/summary`
  - `GET /api/v1/execution/safety/summary`
  - `GET /api/v1/execution/alerts/open`
  - `GET /api/v1/execution/canary/status`
- aprobacion humana explicita para:
  - activar `LIVE_SERIO`
  - cualquier `unfreeze`
  - cualquier `POST /api/v1/rollout/rollback`

## Proximo paso operativo exacto

- ejecutar este gate en el entorno objetivo inmediatamente antes de habilitar `LIVE_SERIO`
- si cualquiera de las surfaces anteriores falla o queda stale:
  - no habilitar live
  - pasar a `HOLD`, `freeze` o `rollout/rollback` segun corresponda

## Referencias relacionadas

- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
