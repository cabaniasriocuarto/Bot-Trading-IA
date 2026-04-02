# Runbook: Final live release gate

Fecha: 2026-04-02

## Contexto de este gate

- este artefacto hoy se usa sobre `feature/live-core-coupled-recovery`;
- `Carril 1` ya recupero materialmente la cohorte tecnica acoplada `RTLOPS-44/45/46/47/48/49/50/23`;
- este bloque no reabre esa cohorte: la toma como base tecnica ya recuperada en esta rama;
- este gate no convierte por si mismo al repo en `LIVE: GO`;
- el uso correcto es decidir `GO`, `GO con restricciones` o `NO GO` con evidencia fresca y humana sobre el entorno objetivo.

## Decision vigente en esta base

- decision actual: `NO GO`
- motivo:
  - la rama ya quedo validada localmente para release path con:
    - `npm run lint` -> PASS
    - `npm run build` -> PASS
    - `npm run test:playwright` -> PASS (`3 passed`)
  - el core live acoplado ya no es el blocker principal en esta rama;
  - habilitar `LIVE_SERIO` sigue requiriendo snapshots frescos del entorno objetivo y aprobacion humana explicita.

## Alcance real de la decision

- aplica al estado actual del repo y a la evidencia documental disponible;
- no reemplaza una revalidacion humana del entorno objetivo inmediatamente antes de operar;
- usa como referencias fuertes:
  - QA backend/live de `RTLOPS-53`
  - smoke UI integrada de `RTLOPS-35`
  - runbooks/rollback de `RTLOPS-37`
  - gates y contratos backend ya presentes en `RTLOPS-51/52/54/29/30`
- mantiene como limitacion explicita:
  - aun falta gate final contra el entorno objetivo;
  - `LIVE` sigue fail-closed hasta reevaluacion fresca y aprobacion humana.

## Matriz de evidencia util

### 1) Preflight

- estado actual en repo: gate fail-closed presente
- evidencia fuerte disponible:
  - contratos y tests backend de `RTLOPS-53`
- evidencia faltante para `GO`:
  - reevaluacion fresca del entorno objetivo
  - snapshot real de `preflight PASS`

### 2) Runtime / G9

- estado actual en repo: contrato real presente y bloqueante
- evidencia fuerte disponible:
  - QA backend/live de `RTLOPS-53`
- limitacion vigente:
  - la base sigue con drift documentado en parte del core live; no debe venderse como reconciliacion completa

### 3) Account surface

- estado actual en repo: surface canonica persistida y exigida por `G9_RUNTIME_ENGINE_REAL`
- evidencia faltante para `GO`:
  - lectura fresca y tradeable del entorno objetivo

### 4) Reconciliation

- estado actual en repo:
  - existe reconciliacion operativa y engine formal recuperado en esta rama
- lectura correcta:
  - usarlo como gate real;
  - no declararlo `PASS` hasta snapshot fresco del entorno objetivo.

### 5) Health / alerts / safety

- estado actual en repo:
  - surfaces canonicas presentes
  - bloqueo fail-closed presente
- evidencia fuerte disponible:
  - QA backend/live de `RTLOPS-53`

### 6) Canary / rollback

- estado actual en repo:
  - canary controller presente
  - rollback del rollout manager documentado y utilizable
  - el canary controller sigue recomendando rollback humano donde corresponde

### 7) Shadow

- estado actual en repo:
  - `LIVE_SHADOW` presente como surface operativa
  - no sustituye readiness de `LIVE_SERIO`

### 8) QA backend

- estado actual en repo:
  - suite `test_backend_qa_live.py` integrada y ya documentada como evidence layer fuerte
- lectura correcta:
  - evidencia backend suficiente para release path serio;
  - no sustituye smoke UI ni reevaluacion del entorno objetivo.

### 9) Playwright smoke

- estado actual en repo:
  - script `test:playwright`
  - `playwright.config.ts`
  - `tests/playwright/live-smoke.spec.ts`
- cobertura integrada:
  - login -> `Ejecucion`
  - visibilidad de `Checklist Live Ready`, `Preflight LIVE Final`, `Reconciliation`
  - visibilidad de `Refrescar panel`, `Modo seguro ON`, `Cerrar posiciones`, `Kill switch`
  - navegacion a `Alertas y Logs`
- validacion local fresca:
  - `npm run test:playwright` -> PASS (`3 passed`)
  - cuenta como evidencia local de release path en esta rama

### 10) Runbooks / incidentes

- estado actual en repo:
  - `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
  - `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
  - `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- lectura correcta:
  - el camino de diagnostico, contencion y rollback existe;
  - este gate los centraliza como criterio de decision final.

## Blockers duros para pasar a LIVE

- no hay reevaluacion fresca del entorno objetivo para:
  - `preflight`
  - `G9_RUNTIME_ENGINE_REAL`
  - `account surface`
  - `reconciliation`
  - `validation/readiness`
  - `live-safety`
  - `market-streams`
- no hay aprobacion humana explicita posterior a esa reevaluacion.

## Que habilitaria pasar de `NO GO` a decision operable

- usar la branch ya pusheada y el Draft PR existente para refrescar el entorno de preview/staging que corresponda;
- ejecutar este gate en el entorno objetivo con snapshots frescos de:
  - `GET /api/v1/gates`
  - `GET /api/v1/rollout/status`
  - `GET /api/v1/validation/readiness`
  - `GET /api/v1/execution/live-safety/summary`
  - `GET /api/v1/execution/reconcile/summary`
  - `GET /api/v1/execution/market-streams/summary`
- si el entorno objetivo sigue mostrando `401/403/404` en alguna de esas surfaces:
  - registrar la evidencia como pendiente por auth/acceso o drift de deployment;
  - no levantar `NO GO` con snapshots incompletos o inventados.
- obtener aprobacion humana explicita antes de habilitar `LIVE_SERIO`.

## Proximo paso operativo exacto

- conservar `feature/live-core-coupled-recovery` y el Draft PR `#13` contra `rtlops-sync-release-live-unification`;
- dejar que preview/staging refresque sobre esta rama;
- ejecutar este gate en el entorno objetivo inmediatamente antes de cualquier promocion live;
- si alguna surface falla o queda stale:
  - no habilitar live
  - pasar a `HOLD`, `freeze` o `rollout/rollback` segun corresponda.

## Referencias relacionadas

- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`
- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
