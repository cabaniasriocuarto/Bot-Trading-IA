# Runbook: Final live release gate

Fecha: 2026-04-01

## Contexto de este gate

- este artefacto se integra en `Ruta A`;
- `Ruta A` acepta el core live actual como base parcialmente absorbida y documentada;
- este bloque no reabre la recuperacion de cohorte de `RTLOPS-23/44/46/47/48/49/50`;
- este gate no convierte por si mismo al repo en `LIVE: GO`;
- el uso correcto es decidir `GO`, `GO con restricciones` o `NO GO` con evidencia fresca y humana sobre el entorno objetivo.

## Decision vigente en esta base

- decision actual: `NO GO`
- motivo:
  - `RTLOPS-35` ya queda integrado en repo como smoke Playwright chica y util, pero no se revalida localmente en este entorno porque faltan `node` y `npm`;
  - el core live sigue parcialmente absorbido/documentado en `docs/truth`;
  - habilitar `LIVE_SERIO` sigue requiriendo reevaluacion fresca del entorno objetivo y aprobacion humana explicita.

## Alcance real de la decision

- aplica al estado actual del repo y a la evidencia documental disponible;
- no reemplaza una revalidacion humana del entorno objetivo inmediatamente antes de operar;
- usa como referencias fuertes:
  - QA backend/live de `RTLOPS-53`
  - smoke UI integrada de `RTLOPS-35`
  - runbooks/rollback de `RTLOPS-37`
  - gates y contratos backend ya presentes en `RTLOPS-51/52/54/29/30`
- mantiene como limitacion explicita:
  - el drift documentado del core live `RTLOPS-23/44/46/47/48/49/50`.

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
  - existe reconciliacion operativa y blocker semantico;
  - el engine formal sigue parcialmente absorbido/documentado
- lectura correcta:
  - usarlo como gate real;
  - no declararlo reconciliacion totalmente recuperada.

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
  - visibilidad de `Checklist Live Ready`, `Health Summary`, `Operational Safety`
  - visibilidad de `Freeze global`, `Unfreeze global`, `Emergency cancel`, `Health evaluate`
  - navegacion a `Alertas y Logs`
- limitacion honesta:
  - en este bloque no se ejecuto porque el entorno actual no tiene `node` ni `npm`
  - hasta revalidarlo, cuenta como capa integrada en repo pero no como evidencia fresca de paso.

### 10) Runbooks / incidentes

- estado actual en repo:
  - `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
  - `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
  - `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- lectura correcta:
  - el camino de diagnostico, contencion y rollback existe;
  - este gate los centraliza como criterio de decision final.

## Blockers duros para pasar a LIVE

- no hay revalidacion fresca de `RTLOPS-35` en este entorno;
- no hay reevaluacion fresca del entorno objetivo para:
  - `preflight`
  - `G9_RUNTIME_ENGINE_REAL`
  - `account surface`
  - `reconciliation`
  - `health`
  - `safety`
  - `alerts`
  - `canary`
- el core live sigue parcialmente absorbido/documentado y no se reconcilia en este bloque.

## Que habilitaria pasar de `NO GO` a decision operable

- correr `RTLOPS-35` en una maquina con `node` y `npm` disponibles;
- archivar resultado real de la smoke;
- ejecutar este gate en el entorno objetivo con snapshots frescos de:
  - `GET /api/v1/gates`
  - `GET /api/v1/rollout/status`
  - `GET /api/v1/execution/health/summary`
  - `GET /api/v1/execution/safety/summary`
  - `GET /api/v1/execution/alerts/open`
  - `GET /api/v1/execution/canary/status`
- obtener aprobacion humana explicita antes de habilitar `LIVE_SERIO`.

## Proximo paso operativo exacto

- revalidar la smoke Playwright de `RTLOPS-35` en un entorno con `node` y `npm`;
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
