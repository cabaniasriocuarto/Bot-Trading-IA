# Runtime Incidents / Logs / Alerts / Ops

Fecha: 2026-04-05
Estado del documento: canonico de input de producto
Dominio: incidentes runtime / alerting / logs / respuesta operativa

## Proposito del dominio

Separar el dominio operativo de incidentes del resto del backlog. Este dominio cubre la superficie necesaria para detectar, clasificar, persistir y operar incidentes sin confundirlo con UI de review ni con capital/sizing.

## Fuentes de input usadas

- `docs/_archive/CONVERSACION_SCREENSHOTS_REFERENCIA_UNIVERSOS_COSTOS_GATES_EXCHANGES.txt`
- `rtlab_dashboard/README.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/audit/ACTION_PLAN_FINAL_20260304.md`
- `docs/audit/FINDINGS_MASTER_20260304.md`
- `rtlab_dashboard/src/app/(app)/alerts/page.tsx`
- `rtlab_autotrader/rtlab_core/execution/alerts.py`
- `rtlab_autotrader/rtlab_core/web/app.py`

## Contenido trasladado desde el material mezclado

- incident model
- problem details
- taxonomy / internal codes
- mapeo Binance y errores operativos
- persistencia auditable
- dedup / correlation / trace
- integracion con safety / breakers / reconciliation
- pantalla de Logs y Alertas
- auditoria y operaciones relacionadas
- Playwright / smoke / tests operativos

## Alcance

Incluye:

- alert catalog y lifecycle
- logs y alertas exportables
- incident response y containment runbooks
- breakers, reconciliation, safety y canary como fuentes operativas
- taxonomy y codigos internos

Excluye:

- sizing / allocation
- charting de review de trades
- promotion logic de research

## Estado actual en repo

Evidencia ya existente:

- `Alerts & Logs` ya consume `GET /api/v1/alerts` y `GET /api/v1/logs`
- `Alerts & Logs` ya exporta `CSV` y `JSON`
- `execution/alerts.py` ya tiene:
  - catalogo de triggers
  - severidades
  - estados
  - source layers
  - `dedup_strategy = trigger_scope_active`
- existen runbooks operativos para:
  - incident response
  - containment y rollback
  - live ready y diagnostics
- backend ya expone surfaces operativas relacionadas:
  - `execution/live-safety/summary`
  - `execution/reconciliation/*`
  - `execution/reconcile/summary`
  - `diagnostics/breaker-events` segun runbooks y truth

Brechas abiertas de producto:

- no existe documento canonico del dominio de incidentes
- no hay un modelado de `problem details` y taxonomy consolidado como input de producto
- no hay una traduccion formal a parent/sub-issues de Linear para este dominio

## Objetivos funcionales

- Tener un modelo canonico de incidente que no dependa solo de logs sueltos
- Unificar alertas runtime, breakers, reconciliation y gates en lenguaje operativo consistente
- Hacer trazable:
  - que paso
  - en que scope
  - con que severidad
  - con que codigo
  - que accion se tomo
  - que evidencia la respalda
- Mantener fail-closed para todo lo live-like

## Backend requerido

Contratos actuales base:

- `GET /api/v1/alerts`
- `GET /api/v1/logs`
- `GET /api/v1/execution/live-safety/summary`
- `GET /api/v1/execution/reconciliation/summary`
- `GET /api/v1/execution/reconciliation/cases`
- `POST /api/v1/execution/reconciliation/run`
- endpoints de freeze / hold / abort / rollback descritos en runbooks

Contratos esperados a consolidar:

- incident payload canonico
- taxonomy / internal code / provider code map
- problem details reutilizable por UI y API
- correlation / trace id / related ids
- auditoria de acciones operativas

## Frontend requerido

- pantalla `Alerts & Logs` con filtros, drilldown y export
- lectura clara de severidad, modulo, relacionado, payload
- vista preparada para incidentes, no solo logs planos

## Persistencia requerida

- alert store auditable
- log store auditable
- timeline de incidentes / working log cuando el dominio se formalice
- referencias a:
  - alert ids
  - breaker events
  - reconciliation cases
  - action audit notes

## Endpoints o contratos esperados

Minimo esperable para declarar el dominio consistente:

- incident severity / state / source layer
- trigger code / problem code / provider code
- scope (`GLOBAL`, `BOT`, `SYMBOL`, `BOT_SYMBOL`)
- dedup y estado activo/resuelto
- acciones operativas con audit note

## Integraciones necesarias

- `execution/alerts.py`
- reconciliation engine
- live safety summary
- canary / rollout containment
- runbooks operativos
- mapeos Binance desde adapter y surfaces firmadas cuando aplique

## Performance / restricciones

- no suprimir incidentes criticos por comodidad
- no marcar recuperado solo porque una pantalla mejoro; siempre con evidencia
- toda accion sensible debe quedar auditada
- cualquier ausencia de evidencia relevante en live-like debe caer fail-closed

## Tests esperados

- tests de catalogo y dedup de alertas
- tests de API `alerts/logs`
- smoke de filtros y exportes de `Alerts & Logs`
- pruebas operativas de runbooks y containment endpoints

## Riesgos / fail-closed / limites

- taxonomy inconsistente vuelve imposible operar o auditar incidentes grandes
- sin `problem details` canonico la UI tiende a mostrar payloads crudos poco accionables
- sin correlation/trace se dificulta unir alertas, logs, breakers y reconcile cases

## Relacion con otros dominios

- alimenta `UI / Trades Console / Exportes` cuando un trade o run necesita contexto de incidente
- alimenta `Capital & Allocation Control` cuando un rechazo pre-trade o freeze nace de limites o safeties

## Sugerencia de issues/sub-issues en Linear

Padre sugerido:

- `Runtime Incidents / Logs / Alerts / Ops`

Sub-issues sugeridas:

- `modelo canonico de incidentes`
- `problem details / handlers`
- `mapeo Binance / taxonomy`
- `persistencia auditable`
- `integracion con safety / breakers / reconciliation`
- `UI Logs y Alertas`
- `tests / Playwright / docs del dominio`

## Bloques ejecutables recomendados

1. canonizar `incident payload` y taxonomy interna
2. cerrar dedup / correlation / trace
3. luego abrir la evolucion de `Alerts & Logs` desde log viewer a incident console

## Siguiente bloque recomendado

Levantar inventario de:

- trigger codes actuales
- severidades
- states
- source layers
- endpoints de contencion soportados hoy

y traducir eso a un contrato canonico de incidente sin tocar todavia la implementacion grande.
