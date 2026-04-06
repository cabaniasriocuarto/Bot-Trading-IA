# UI / Trades Console / Exportes

Fecha: 2026-04-05
Estado del documento: canonico de input de producto
Dominio: UI operativa / revision de trades / charting / exportes

## Proposito del dominio

Definir la capa de visualizacion y operacion de revision para trades, runs y artifacts sin mezclarla con riesgo, capital o incident response. Este dominio debe servir para:

- leer evidencia operativa
- revisar trades y runs con contexto suficiente
- exportar evidencia auditable
- sostener QA visual y Playwright

## Fuentes de input usadas

- `docs/_archive/CONVERSACION_SCREENSHOTS_REFERENCIA_UNIVERSOS_COSTOS_GATES_EXCHANGES.txt`
- `docs/_archive/UI_UX_RESEARCH_FIRST_FINAL.md`
- `rtlab_dashboard/README.md`
- `docs/runbooks/LIVE_RELEASE_GATE.md`
- `rtlab_dashboard/src/app/(app)/trades/page.tsx`
- `rtlab_dashboard/src/app/(app)/trades/[id]/page.tsx`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_autotrader/rtlab_core/reporting/service.py`
- `rtlab_autotrader/rtlab_core/web/app.py`

## Contenido trasladado desde el material mezclado

- consola operativa de trades
- charting y overlays para revision de entradas/salidas
- tabla auditable de trades
- filtros, ordenamiento y foco tabla -> chart
- exportes CSV / XLSX / PDF
- smoke / Playwright / QA visual-operativa
- review de runs y artifacts

## Alcance

Incluye:

- pantallas `Trades`, `Trades Detail`, `Backtests / Runs`, exports de reporting
- flujo de revision operador -> filtro -> drilldown -> export
- overlays y charts que ayuden a interpretar decisiones o resultados
- controles QA para evitar regresiones visuales y de wiring

Excluye:

- calculo de sizing y capital allocation
- incident taxonomy y response operativa
- cambios de estrategia o promotion logic

## Estado actual en repo

Evidencia ya existente:

- `Trades` ya consume `GET /api/v1/trades` y `GET /api/v1/trades/summary`
- `Trades` ya tiene filtros por `strategy_id`, `symbol`, `side`, `mode`, `environment`, `reason_code`, `exit_reason`, `result`, rango temporal
- `Backtests` ya expone comparador, overlays y tabs de analisis
- reporting ya exporta `xlsx` y `pdf`
- `Alerts & Logs` ya exporta `csv/json`
- hay Playwright smoke en `rtlab_dashboard/tests/playwright/live-smoke.spec.ts`

Brechas abiertas de producto:

- no existe un documento canonico del dominio UI/Trade Review separado del resto
- charting de trade review y overlays operativos siguen repartidos entre `backtests`, `trades` y detalle de trade
- no hay bloque propio de exportes auditable como dominio separado del reporting engine

## Objetivos funcionales

- Unificar la consola operativa de revision de trades como superficie primaria para:
  - leer estado y resultado de trades
  - navegar por estrategia, simbolo, ambiente y motivo
  - abrir detalle de trade con chart y contexto
- Hacer visibles overlays de:
  - entry
  - exit
  - stop
  - target
  - fees / slippage / net vs gross cuando existan
- Mantener exportes auditables con manifest y retention conocida
- Mantener QA visual minima pero util, no cosmetica

## Backend requerido

Contratos actuales base:

- `GET /api/v1/trades`
- `GET /api/v1/trades/summary`
- `GET /api/v1/trades/{trade_id}`
- `GET /api/v1/reporting/trades`
- `GET /api/v1/reporting/performance/summary`
- `GET /api/v1/reporting/performance/daily`
- `GET /api/v1/reporting/performance/monthly`
- `GET /api/v1/reporting/costs/breakdown`
- `POST /api/v1/reporting/exports/xlsx`
- `POST /api/v1/reporting/exports/pdf`
- `GET /api/v1/reporting/exports`

Contratos esperados a consolidar en este dominio:

- payload de trade detail con contexto de chart / fills / costs / source strategy
- export manifest consistente entre CSV/XLSX/PDF
- linking claro run <-> trade <-> artifact

## Frontend requerido

- tabla de trades auditable
- filtros y ordenamiento visibles
- focus row -> chart / detail
- detalle de trade con chart y contexto operativo
- accesos a exportes
- QA Playwright para:
  - carga
  - filtros
  - drilldown
  - export trigger visible

## Persistencia requerida

- ledger de trades cerrado y consistente
- cost/reporting rows persistidos
- export manifests con retention
- metadata de dataset / commit / strategy / environment cuando aplique

## Endpoints o contratos esperados

Minimo esperable para declarar el dominio consistente:

- trade list filtrable
- trade detail con fills/costos asociados
- summary por strategy / environment / day
- artifacts exportables con nombres y retention claras
- links consistentes desde UI hacia runs / strategies / trade detail

## Integraciones necesarias

- BFF Next.js con backend `/api/v1/*`
- `reporting/service.py`
- `execution` ledger para origen de trades
- componentes de charts (`recharts`, `lightweight-charts`)
- Playwright smoke

## Performance / restricciones

- no cargar tablas gigantes sin paginacion o limite visible
- no renderizar charts sinteticos que mezclen narrativa con evidencia
- exports respetan `max_rows_per_export`
- cualquier vista sin data debe quedar fail-closed con empty state accionable, no con inventos

## Tests esperados

- Playwright smoke de carga y navegacion
- contrato de filtros y summary
- export trigger visible y respuesta no vacia
- regression test para focus row -> detail

## Riesgos / fail-closed / limites

- no inventar overlays si el backend no provee la data
- si falta artifact o cost breakdown, la UI debe mostrar ausencia explicita
- no mezclar visualizaciones de backtest con evidencia de execution real sin marcar la fuente

## Relacion con otros dominios

- depende de `Capital & Allocation Control` para exponer sizing / budget / exposure con semantica correcta
- depende de `Runtime Incidents / Logs / Alerts / Ops` para cruzar trades con alertas o incidentes

## Sugerencia de issues/sub-issues en Linear

Padre sugerido:

- `UI / Trades Console / Exportes / Trade Review`

Sub-issues sugeridas:

- `grafico operativo multi-par / estrategia`
- `overlays de entradas salidas stop target`
- `tabla de trades auditable`
- `filtros ordenamiento y foco chart`
- `exportes CSV XLSX PDF`
- `Playwright / smoke / QA visual-operativa`

## Bloques ejecutables recomendados

1. consolidar contrato `trade detail + fills + costs + chart payload`
2. unificar `trades` y `trade detail` como review surface auditable
3. cerrar QA Playwright de filtro -> detalle -> export

## Siguiente bloque recomendado

No abrir implementacion grande de UI hasta que:

- el modelado de capital / allocation quede separado
- el dominio de incidentes tenga taxonomy canonica

El siguiente bloque sano para este dominio es:

- inventario de contratos actuales y huecos reales de `trade detail` / export manifest / QA smoke
