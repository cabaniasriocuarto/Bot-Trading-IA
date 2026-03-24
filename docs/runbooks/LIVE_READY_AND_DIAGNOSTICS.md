# Runbook: Live readiness y diagnostico

Fecha: 2026-03-24

## Cuando usarlo

- antes de habilitar `LIVE`
- antes de avanzar `CANARY`
- antes de reanudar un canary en `HOLD`
- cuando una surface devuelve `BLOCKED`, `MANUAL_REVIEW_REQUIRED`, `FAIL`, `HOLD` o `ROLLBACK_RECOMMENDED`

## Superficies primarias

- `GET /api/v1/gates`
  - checklist global; mirar especialmente `G9_RUNTIME_ENGINE_REAL`
- `POST /api/v1/gates/reevaluate`
  - refresco manual de gates
- `GET /api/v1/rollout/status`
  - estado de rollout + `readiness_by_stage`
- `GET /api/v1/rollout/shadow/status`
  - readiness operativa de `LIVE_SHADOW`
- `GET /api/v1/execution/health/summary`
  - verdad consolidada de lectura
- `POST /api/v1/execution/health/evaluate`
  - refresco manual del summary
- `GET /api/v1/execution/safety/summary`
- `GET /api/v1/execution/safety/breakers`
- `GET /api/v1/execution/safety/locks`
- `GET /api/v1/execution/safety/events`
- `GET /api/v1/execution/alerts/open`
- `GET /api/v1/execution/alerts/history`
- `POST /api/v1/execution/alerts/evaluate`
  - refresco manual del consumer persistente
- `GET /api/v1/execution/canary/status`
- `GET /api/v1/config/policies`
- `GET /api/v1/diagnostics/breaker-events`

## Diagnostico rapido

1. Mirar `GET /api/v1/gates`.
   - si `G9_RUNTIME_ENGINE_REAL` esta en `FAIL`, no habilitar `LIVE` ni promover stage.
2. Mirar `GET /api/v1/execution/health/summary`.
   - registrar `state`, `blocking_bool`, `top_priority_reason_code`, `hard_blockers`, `component_status`, `scope_status`.
3. Mirar `GET /api/v1/execution/safety/summary`.
   - registrar `blocking_bool`, `global_state`, `manual_lock_count`, breakers y freezes activos.
4. Mirar `GET /api/v1/execution/alerts/open`.
   - confirmar si hay alertas `CRITICAL` abiertas y de que `source_layer` vienen.
5. Mirar el estado de la fase actual.
   - `GET /api/v1/execution/canary/status` si hay canary activo
   - `GET /api/v1/rollout/shadow/status` si se esta trabajando en `LIVE_SHADOW`
   - `GET /api/v1/rollout/status` para `readiness_by_stage`
6. Si hay duda sobre thresholds o soporte real, mirar `GET /api/v1/config/policies`.

## Patrones cubiertos

### 1) Preflight blocking

Usarlo cuando:

- `health_summary` expone `PREFLIGHT_FAIL`, `PREFLIGHT_EXPIRED` o `PREFLIGHT_STALE`
- `alerts/open` muestra `PREFLIGHT_FAIL` o `PREFLIGHT_EXPIRED`
- `canary/status` cae a `HOLD` por `PREFLIGHT`

Que significa:

- el sistema no tiene evidencia fresca/suficiente para arrancar o promover

Que hacer primero:

- reevaluar `gates`, `health` y `alerts`
- revisar `readiness_by_stage`
- no habilitar `LIVE`, no arrancar bot live, no promover canary

Que hacer si se confirma:

- mantener fail-closed
- si hay canary activo, pasar a `HOLD`
- corregir la causa upstream antes de volver a evaluar

Cerrar cuando:

- desaparecen los reason codes de preflight
- `health_summary` deja de estar bloqueado por preflight
- el stage vuelve a quedar `ready_bool=true` cuando corresponda

Evidencia a registrar:

- `snapshot_id` de health
- razones de `readiness_by_stage`
- ids de alertas abiertas relacionadas

### 2) Operational safety blocking

Usarlo cuando:

- `execution/safety/summary.blocking_bool=true`
- hay `MANUAL_LOCK`
- hay breaker `OPEN` o `COOLDOWN` bloqueante
- `bot/mode` o `bot/start` quedan bloqueados por operational safety

Que significa:

- hay una condicion de contencion ya materializada por la capa canonica de safety

Que hacer primero:

- mirar `breakers`, `locks` y `events`
- confirmar si el bloqueo es global, por bot o por simbolo
- si el incidente esta creciendo, congelar explicitamente el scope afectado

Que hacer si se confirma:

- no forzar `LIVE`
- no levantar locks por conveniencia
- si hay riesgo operativo en un simbolo concreto, usar contencion del runbook de rollback/containment

Cerrar cuando:

- el breaker deja de estar bloqueante
- la condicion operativa ya no esta activa
- el `unfreeze` se hace con `audit_note` y verificacion humana

Evidencia a registrar:

- `breaker_code`
- scope afectado
- `manual_action` o `safety_event_id`

### 3) Runtime/G9 fail-closed o account surface no tradeable

Usarlo cuando:

- `G9_RUNTIME_ENGINE_REAL` falla
- `readiness_by_stage` expone razones como `account_surface_ok`, `account_can_trade` o equivalentes de runtime contract
- `TESTNET` o `LIVE_SERIO` quedan `ready_bool=false`

Que significa:

- el runtime no esta listo con evidencia real/fresca para live/testnet-live

Que hacer primero:

- mirar `GET /api/v1/gates`
- mirar `GET /api/v1/rollout/status`
- confirmar `account_surface_ok`, `account_can_trade`, frescura y modo

Que hacer si se confirma:

- no habilitar `LIVE`
- no promover canary
- si ya existe exposicion live gestionada por rollout, pasar al runbook de contencion/rollback

Cerrar cuando:

- `G9_RUNTIME_ENGINE_REAL` vuelve a `PASS` en el contexto correcto
- la account surface vuelve a estar fresca y tradeable

Evidencia a registrar:

- gate `G9_RUNTIME_ENGINE_REAL`
- razones de `readiness_by_stage`
- flags de account surface

### 4) Reconciliation stale o blocking

Usarlo cuando:

- `health_summary` expone `RECONCILIATION_DESYNC` o `MANUAL_REVIEW_REQUIRED`
- `canary/status.current_evaluation.blocking_sources` incluye `RECONCILIATION`
- `alerts/open` muestra `RECONCILIATION_DESYNC_OPEN` o `RECONCILIATION_MANUAL_REVIEW_OPEN`

Que significa:

- no hay consistencia suficiente entre estado local y evidencia canonica remota

Que hacer primero:

- detener avance de fase
- poner canary en `HOLD` si aplica
- no cerrar nada "por conveniencia local"

Que hacer si se confirma:

- exigir verificacion remota/canonica antes de retomar
- si la exposicion candidata ya esta activa y el problema persiste, evaluar rollback manual de rollout

Cerrar cuando:

- `health_summary` deja `BLOCKED` o `MANUAL_REVIEW_REQUIRED`
- los alerts de reconciliacion quedan resueltos

Evidencia a registrar:

- `hard_blockers`
- `blocking_sources`
- ids de alertas de reconciliacion

### 5) Health degraded o blockers activos

Usarlo cuando:

- `execution/health/summary.state` es `DEGRADED`, `BLOCKED` o `MANUAL_REVIEW_REQUIRED`

Que significa:

- la verdad consolidada ya detecto degradacion o bloqueo a partir de surfaces upstream

Que hacer primero:

- mirar `top_priority_reason_code`
- mirar `hard_blockers`
- revisar `component_status` y `scope_status`

Que hacer si se confirma:

- si esta `DEGRADED`, no promover por "mejoro un poco"
- si esta `BLOCKED` o `MANUAL_REVIEW_REQUIRED`, tratarlo como incidente y contener

Cerrar cuando:

- el summary vuelve al estado esperado para el stage actual
- desaparecen blockers duros

Evidencia a registrar:

- `state`
- `score`
- `top_priority_reason_code`
- `component_status`

### 6) Canary hold o rollback recomendado

Usarlo cuando:

- `current_evaluation.hold_required_bool=true`
- `current_evaluation.rollback_recommended_bool=true`

Que significa:

- el canary esta consumiendo una surface canonica bloqueante y respondio fail-closed

Que hacer primero:

- registrar `blocking_sources` y `gating_reasons`
- distinguir si el caso pide solo `HOLD` o si ya amerita contencion mas fuerte

Que hacer si se confirma:

- `HOLD` si la pausa es reversible y el problema aun se esta diagnosticando
- pasar al runbook de contencion/rollback si la recomendacion de rollback persiste o la exposicion ya es riesgosa

Cerrar cuando:

- la reevaluacion vuelve a permitir continuar
- si se reanuda, recordar que `resume` no equivale a `promote`

Evidencia a registrar:

- `run_id`
- `blocking_sources`
- `gating_reasons`
- `latest_evaluation`

### 7) Shadow no ready / runtime live no ready

Usarlo cuando:

- `rollout/shadow/status.active=false`
- `rollout/shadow/status.operational=false`
- aparecen razones como `rollout_not_in_live_shadow` o `runtime_contract_not_ready`

Que significa:

- `LIVE_SHADOW` no esta operativo todavia

Que hacer primero:

- no enviar `POST /api/v1/rollout/shadow/signal`
- revisar `routing.shadow_only`, `runtime_contract`, `telemetry_guard`

Cerrar cuando:

- `active=true`
- `operational=true`
- `routing.shadow_only=true`

Evidencia a registrar:

- razones de `shadow/status`
- `runtime_contract.mode`
- `telemetry_guard.ok`

### 8) Config/policies para diagnostico

Usarlo cuando:

- hay duda sobre thresholds
- hay discusiones sobre si algo deberia bloquear o no

Mirar en `GET /api/v1/config/policies`:

- thresholds de preflight fresco/vencido
- policy de canary
- soporte real de rollback
- policy de alerts
- thresholds de operational safety

Regla operativa:

- diagnosticar desde la policy publicada, no desde memoria ni desde comentarios viejos

## Criterio de escalamiento

Escalar sin esperar otro ciclo si aparece cualquiera de estos:

- `G9_RUNTIME_ENGINE_REAL=FAIL` en ruta live/canary
- `health_summary.state in {BLOCKED, MANUAL_REVIEW_REQUIRED}`
- `execution/safety/summary.blocking_bool=true` por lock global o breaker duro
- `current_evaluation.rollback_recommended_bool=true`
- `account_surface` no tradeable sin explicacion esperada

## Evidencia minima a guardar

- hora UTC de deteccion
- operador responsable
- scope (`GLOBAL`, `BOT`, `SYMBOL`, `BOT_SYMBOL`)
- snapshots/responses clave consultadas
- run/alert ids asociados
- decision tomada (`no_operar`, `hold`, `freeze`, `rollback`, `escalar`)
