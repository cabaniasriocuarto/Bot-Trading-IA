# Runbook: Live containment y rollback

Fecha: 2026-03-24

## Objetivo

Contener incidentes live sin inventar capacidades. Este runbook distingue entre:

- contencion reversible
- rollback soportado hoy
- recomendacion de rollback con intervencion humana
- cosas que todavia no estan soportadas

## Regla principal

- si falta evidencia suficiente, el sistema queda fail-closed
- no forzar `LIVE`
- no tratar `hold`, `freeze` y `rollback` como sinonimos

## Soporte real hoy

### 1) Contencion soportada hoy

- `POST /api/v1/execution/safety/freeze/symbol/{symbol}`
- `POST /api/v1/execution/safety/freeze/bot/{bot_id}`
- `POST /api/v1/execution/safety/freeze/global`
- `POST /api/v1/execution/safety/unfreeze`
- `POST /api/v1/execution/safety/emergency-cancel/{symbol}`
- `POST /api/v1/execution/canary/{run_id}/hold`
- `POST /api/v1/execution/canary/{run_id}/resume`
- `POST /api/v1/execution/canary/{run_id}/abort`

Lectura correcta:

- `freeze` y `emergency-cancel` son contencion operativa
- `HOLD` es pausa reversible
- `ABORTED` cierra el run actual y no debe reanudarse sin accion explicita nueva

### 2) Rollback soportado hoy

- `POST /api/v1/rollout/rollback`

Semantica soportada:

- si hay rollout activo, el manager puede volver a:
  - `baseline_pct = 100`
  - `candidate_pct = 0`
  - `state = ROLLED_BACK`
- el manager persiste `rollback_snapshot`
- en live phases tambien existe auto rollback del rollout manager si se disparan hard fails configurados

### 3) Rollback recomendado hoy, pero no confirmado como ejecucion canonica

- `POST /api/v1/execution/canary/{run_id}/rollback`

Lectura correcta:

- el canary controller hoy no confirma rollback real por si mismo
- la policy actual deja `rollback_execution_supported = false`
- sin confirmacion canonica, la salida valida sigue siendo `ROLLBACK_RECOMMENDED`
- no vender este endpoint como "rollback real ya ejecutado"

### 4) No soportado hoy

- rollback canonico confirmado del canary controller sin evidencia persistida adicional
- rollback global de exchange fuera del rollout manager
- rollback que reescriba fills, reconciliacion o history
- rollback de shadow hacia ejecucion real

## Decision path corto

### Caso A: no hay exposicion nueva que retirar

Usar:

- `no_operar`
- `HOLD`
- `freeze`

No usar rollback por reflejo.

### Caso B: hay riesgo operativo en un scope concreto

Usar primero:

- `freeze/symbol`
- `freeze/bot`
- `freeze/global` si el problema ya no es local

Agregar:

- `emergency-cancel/{symbol}` si el riesgo esta en ordenes activas del simbolo

### Caso C: hay canary bloqueado o rollback recomendado

Usar primero:

- `hold`

Pasar a rollback manual de rollout solo si:

- el problema persiste
- ya hay exposicion candidata activa
- un operador humano decide volver a baseline

### Caso D: hay rollout live activo y la retirada a baseline es la accion correcta

Usar:

- `POST /api/v1/rollout/rollback`

Esperar:

- `state = ROLLED_BACK`
- `weights.baseline_pct = 100`
- `weights.candidate_pct = 0`

## Payloads minimos utiles

### Freeze global

```json
{
  "audit_note": "incident_2026-03-24 contain global risk"
}
```

### Unfreeze

```json
{
  "scope_type": "GLOBAL",
  "audit_note": "clear after verification"
}
```

Para `BOT`, `SYMBOL` o `BOT_SYMBOL` agregar `bot_id` y/o `symbol` segun corresponda.

### Emergency cancel por simbolo

```json
{
  "audit_note": "cancel live symbol during incident"
}
```

### Canary hold

```json
{
  "reason": "reconciliation blocking",
  "audit_note": "hold pending remote verification"
}
```

### Canary resume

```json
{
  "reason": "surfaces healthy again",
  "audit_note": "resume after reevaluation"
}
```

### Canary abort

```json
{
  "reason": "incident closed, new run required",
  "audit_note": "abort current run"
}
```

### Rollout rollback manual

```json
{
  "reason": "candidate retreat after live incident"
}
```

## Reglas humanas obligatorias

- `unfreeze` requiere verificacion humana y `audit_note`
- `rollout/rollback` requiere decision humana explicita
- `ROLLBACK_RECOMMENDED` del canary no se interpreta como ejecucion real sin confirmacion canonica
- `resume` no equivale a `promote`

## Que hacer por patron

### Preflight expirado o fail

- no operar
- si hay canary, `hold`
- no hacer rollback salvo que ya exista rollout activo y la retirada sea una decision humana separada

### Safety breaker / manual lock / freeze activo

- mantener contencion
- no levantar lock por conveniencia
- si hay riesgo de ordenes abiertas, `emergency-cancel` por simbolo

### Reconciliation blocking / manual review

- `hold`
- no cerrar localmente sin evidencia remota
- si la exposicion candidata activa vuelve inseguro seguir, evaluar `rollout/rollback`

### G9 fail / account surface no tradeable

- no habilitar live
- `hold` si hay canary
- `rollout/rollback` solo si ya hay exposicion activa y el operador decide retirada

### Canary rollback recomendado

- tratarlo como decision humana obligatoria
- mirar `blocking_sources` y `gating_reasons`
- decidir entre:
  - `hold`
  - `abort`
  - `rollout/rollback`

## Criterio de salida

Salir de contencion solo cuando:

- `gates` y `health` vuelven a estar consistentes con el stage
- no quedan breakers/manual locks bloqueantes en el scope
- las alertas criticas asociadas ya no estan activas
- si se hace `resume`, la reevaluacion vuelve a permitir continuar

## Evidencia a registrar

- operador
- motivo exacto
- endpoint usado
- payload enviado
- respuesta recibida
- ids de run/event/alert/breaker involucrados

## Referencias relacionadas

- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- `docs/runbooks/RAILWAY_STORAGE_PERSISTENCE.md`
- `docs/runbooks/BACKUP_RESTORE_USER_DATA.md`
