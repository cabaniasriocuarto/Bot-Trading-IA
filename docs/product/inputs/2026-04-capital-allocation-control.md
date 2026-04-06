# Capital & Allocation Control

Fecha: 2026-04-05
Estado del documento: canonico de input de producto
Dominio: capital / allocation / sizing / pre-trade fail-closed

## Proposito del dominio

Definir una capa canonica para capital, sizing y asignacion que hoy esta repartida entre `portfolio`, `risk`, preflight y policies. Este dominio debe ordenar lo que existe y dejar clara la brecha hacia:

- treasury snapshot
- budget engine
- reservation ledger
- position sizing
- exchange rule validation

## Fuentes de input usadas

- `docs/_archive/CONVERSACION_SCREENSHOTS_REFERENCIA_UNIVERSOS_COSTOS_GATES_EXCHANGES.txt`
- `docs/_archive/research_stack.md`
- `docs/audit/ACTION_PLAN_FINAL_20260304.md`
- `docs/audit/FINDINGS_MASTER_20260304.md`
- `rtlab_dashboard/src/app/(app)/portfolio/page.tsx`
- `rtlab_dashboard/src/app/(app)/risk/page.tsx`
- `rtlab_autotrader/config/policies/risk_policy.yaml`
- `rtlab_autotrader/config/policies/execution_safety.yaml`
- `rtlab_autotrader/rtlab_core/risk/risk_engine.py`
- `rtlab_autotrader/rtlab_core/execution/filter_prevalidator.py`
- `rtlab_autotrader/rtlab_core/web/app.py`

## Contenido trasladado desde el material mezclado

- capital manager
- treasury snapshot
- portfolio budget engine
- reservation ledger
- exchange rule validator
- position sizing
- validacion pre-trade
- vista operativa de capital / allocation / exposure
- reglas numericas explicitas

## Alcance

Incluye:

- sizing y guardas pre-trade
- exposure y concentration
- limites por orden, simbolo, cartera y ambiente
- semantica de capital disponible vs reservado
- vistas operativas de portfolio / risk / capital

Excluye:

- decision alpha / signal generation
- incident response y alert lifecycle
- promotion de rollout

## Estado actual en repo

Evidencia ya existente:

- `RiskEngine.position_size(...)` usa equity, stop distance y `risk_per_trade`
- `Portfolio` ya muestra equity, pnl diario, exposure total y exposure por simbolo
- `Risk` ya muestra limites, circuit breakers y stress tests
- `filter_prevalidator` ya bloquea por filtros exchange y alineacion de precio / qty / notional
- `execution_safety.yaml` ya define:
  - `max_notional_per_order_usd`
  - `max_open_orders_per_symbol`
  - `max_open_orders_total`
  - `min_notional_buffer_pct_above_exchange_min`
  - reglas margin / slippage / reconciliation / persistence
- `rollout.manager` ya usa `capital_pct` por fase canary/stable

Brechas abiertas de producto:

- no existe dominio canonico `capital/allocation` separado
- no existe treasury snapshot consolidado como contrato propio
- no existe reservation ledger explicitamente modelado como producto
- no existe budget engine operativo separado del rollout/canary

## Objetivos funcionales

- Definir capital disponible, capital reservado y exposure efectiva sin ambiguedad
- Validar pre-trade con fail-closed antes de submit
- Explicitar sizing por:
  - equity
  - risk per trade
  - stop distance
  - exchange filters
  - exposure restante
- Hacer visible la diferencia entre:
  - snapshot de portfolio
  - reglas de riesgo
  - reserva pre-trade
  - allocation por fase/entorno

## Backend requerido

Contratos actuales base:

- `GET /api/v1/portfolio`
- `GET /api/v1/risk`
- `POST /api/v1/execution/preflight`
- `GET /api/v1/execution/filter-rules`
- `GET /api/v1/execution/live-safety/summary`

Contratos esperados si el dominio se separa correctamente:

- `capital snapshot` consolidado
- `allocation budget` por bot / estrategia / simbolo / entorno
- `reservation ledger` para intents y ordenes abiertas
- validacion pre-trade numerica reutilizable desde UI y backend

## Frontend requerido

- vista operativa de capital / exposure / concentration
- lectura clara de limites disponibles vs consumidos
- explicacion de rechazos pre-trade y budget remaining
- acciones admin sensibles solo con guardas y confirmacion

## Persistencia requerida

- snapshot de portfolio y exposure
- ledger de ordenes y fills
- reservation ledger auditable
- evidencia de preflight y rechazos
- metadata de origen para sizing y allocation decision

## Endpoints o contratos esperados

Minimo esperable para declarar el dominio consistente:

- capital disponible / reservado / consumido
- exposure por simbolo, bot y estrategia
- sizing sugerido y sizing aplicado
- regla exchange que bloquea cuando un submit no puede pasar
- razon canonica de rechazo pre-trade

## Integraciones necesarias

- `risk_policy.yaml`
- `execution_safety.yaml`
- `filter_prevalidator.py`
- `risk_engine.py`
- instrument registry y exchange filters
- reporting/trades para reconciliar capital consumido vs realizado
- research stack offline solo como preview, nunca auto-live

## Performance / restricciones

- todo submit live-like debe quedar fail-closed si falta policy, filters o snapshot fresco
- no mezclar preview de allocation offline con execution live
- no permitir allocation cosmetico sin reservation ledger auditable

## Tests esperados

- tests de `RiskEngine`
- tests de `filter_prevalidator`
- tests de source fail-closed en policies
- tests de exposure / reservation / budget drift cuando el dominio exista

## Riesgos / fail-closed / limites

- cualquier gap entre budget visible y budget ejecutable es riesgo directo de operacion
- no introducir allocation UI accionable antes de tener semantica de reserva y rechazo consistente
- previews offline de `riskfolio-lib` / `PyPortfolioOpt` no deben tocar runtime live

## Relacion con otros dominios

- alimenta `UI / Trades Console / Exportes` con exposure, sizing y cost context
- alimenta `Runtime Incidents / Logs / Alerts / Ops` con rechazos pre-trade, breakers y safeties

## Sugerencia de issues/sub-issues en Linear

Padre sugerido:

- `Capital & Allocation Control`

Sub-issues sugeridas:

- `treasury snapshot consolidado`
- `budget engine`
- `position sizer`
- `exchange rule validator`
- `reservation ledger`
- `frontend operativo de capital`
- `QA / docs / validacion del bloque`

## Bloques ejecutables recomendados

1. canonizar `capital snapshot` y `budget / reservation` como contrato
2. cerrar semantica de `preflight reject` reusable por UI y backend
3. recien despues abrir implementacion de reservation ledger o budget engine

## Siguiente bloque recomendado

Inventariar contratos actuales de:

- `portfolio`
- `risk`
- `execution/preflight`
- `execution/filter-rules`

y separar lo que ya existe de lo que todavia es solo hueco de producto.
