# Runbook: Live incident response

Fecha: 2026-03-24

## Objetivo

No improvisar cuando una surface live/canary/shadow falla. Este runbook deja un marco minimo-profesional para:

- deteccion
- working log
- contencion
- recuperacion
- cierre

## Cuando abrir incidente

Abrir incidente si aparece cualquiera de estos:

- `G9_RUNTIME_ENGINE_REAL=FAIL` en ruta live/canary
- `health_summary.state in {BLOCKED, MANUAL_REVIEW_REQUIRED}`
- `execution/safety/summary.blocking_bool=true`
- `current_evaluation.hold_required_bool=true`
- `current_evaluation.rollback_recommended_bool=true`
- `account surface` no tradeable sin motivo esperado
- `shadow/status.operational=false` durante trabajo activo de `LIVE_SHADOW`

## Clasificacion minima

Usar severidad operativa minima alineada con alerting:

- `CRITICAL`
  - live/canary bloqueado, rollback considerado, freeze global, emergency cancel, manual review blocking
- `WARN`
  - degradacion importante sin retirada inmediata
- `INFO`
  - observacion, seguimiento o recuperacion ya contenida

Esta clasificacion ayuda a ordenar la respuesta, pero no reemplaza juicio humano.

## Roles minimos

- operador responsable
  - ejecuta diagnostico y contencion
- aprobador humano
  - valida `unfreeze`, rollback manual y reanudacion sensible
- registro
  - si no hay equipo separado, lo lleva el mismo operador

## Primeros 10 minutos

1. Abrir working log.
2. Registrar hora UTC, scope, stage actual y operador.
3. Capturar outputs de:
   - `gates`
   - `health_summary`
   - `safety_summary`
   - `alerts/open`
   - `canary/status` o `shadow/status` segun corresponda
4. Elegir una accion inicial:
   - `no_operar`
   - `hold`
   - `freeze`
   - `emergency-cancel`
   - `rollback manual`
5. Definir proximo checkpoint y criterio de escalamiento.

## Working log minimo

Registrar como minimo:

- `incident_started_at`
- operador
- severidad inicial
- scope afectado
- stage actual (`TESTNET`, `CANARY`, `LIVE_SERIO`, `LIVE_SHADOW`)
- outputs clave consultados
- ids de run, alertas, breakers o events relevantes
- accion tomada
- aprobaciones humanas recibidas
- hora del siguiente chequeo

## Comunicacion minima

Cada actualizacion debe decir:

- que se detecto
- que surfaces lo confirman
- que accion se tomo
- que sigue faltando validar

Ejemplo corto:

`CRITICAL - canary en HOLD por RECONCILIATION. Safety sin freeze global. Se congela simbolo BTCUSDT y se pausa avance. Proxima reevaluacion en 10 min tras validacion remota.`

## Ramas operativas

### Si el incidente es de readiness/diagnostico

- usar `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`

### Si el incidente requiere contencion o retirada

- usar `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`

## Escalar sin demora

Escalar de inmediato si aparece cualquiera de estos:

- `rollback_recommended_bool=true`
- `health_summary.hard_blockers` contiene reconciliacion, preflight expirada o manual lock
- `execution/safety/summary.global_state=MANUAL_LOCK`
- `alerts/open` contiene alerta `CRITICAL` persistente en `SAFETY` o `HEALTH`
- `diagnostics/breaker-events` falla cerrado en un entorno donde deberia haber evidencia

## Recuperacion

No declarar recuperado solo porque una pantalla "se ve mejor".

Confirmar siempre:

- `gates` consistentes
- `health_summary` sin blockers duros
- `safety_summary.blocking_bool=false` en el scope relevante
- alertas criticas ya no activas
- si habia canary en `HOLD`, reevaluacion canonica antes de `resume`

## Cierre

Cerrar incidente cuando:

- la condicion base dejo de estar activa
- la contencion ya no es necesaria
- el operador dejo evidencia suficiente del diagnostico y de la accion tomada

Registrar al cierre:

- hora de cierre
- causa confirmada o mejor explicacion disponible
- acciones ejecutadas
- riesgos residuales
- follow-up si hace falta

## Post-incident minimo

Si el incidente revela un gap real del sistema:

- actualizar `docs/truth`
- dejar comentario o follow-up en la issue correcta

Si no revela gap de producto:

- no abrir bloque tecnico por inercia
- alcanza con dejar evidencia y aprendizaje operativo
