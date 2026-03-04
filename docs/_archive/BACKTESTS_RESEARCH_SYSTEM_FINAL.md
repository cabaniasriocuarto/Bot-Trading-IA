# Backtests & Research System - Checklist Final (Bloques 1-6)

Idioma: Espanol  
Scope aplicado: sin refactor masivo, sin romper runtime LIVE/OMS, extendiendo APIs existentes.

## Resumen ejecutivo
- Se unifico el concepto de resultado como **Backtest Run** (`BT-xxxxx`) con catalogo SQLite y trazabilidad.
- El **Research Batch** (`BX-xxxxx`) quedo como contenedor de multiples runs hijos (`batch_child`).
- Se agrego comparador profesional por capas (shortlist + tabla amplia + deep compare base).
- Se implemento loop **Research -> Validate -> Promote** (Opcion B) hacia rollout con gates/compare/constraints.
- No hay auto-live: toda promocion real sigue por `Rollout / Gates` + canary + rollback + approve manual.

---

## A) Modelo de datos (RUNS + BATCHES + PROVENANCE)

### DONE
- `backtest_runs` en SQLite con identidad estructurada (`BT-xxxxx`)
- `backtest_batches` en SQLite con identidad estructurada (`BX-xxxxx`)
- `artifacts_index` en SQLite
- `id_sequences` para IDs lexicograficos/human friendly
- Provenance persistente por run (dataset hash, commit, costos, params, seed, HF metadata opcional)
- Titulo estructurado + subtitulo tecnico persistidos por run
- Sync incremental desde `runs.json` al catalogo SQLite (compatibilidad sin romper legacy)

### NO-DONE
- IDs `DS-xxxxx` (DatasetSnapshot) como entidad separada
- IDs `MD-xxxxx` (HF Model snapshot) como entidad separada
- UX dedicada para tags/aliases legacy migrados

---

## B) KPIs completos + expectancy unit + costos netos

### DONE
- KPI summary por run en catalogo (Sharpe, Sortino, Calmar, PF, WinRate, trades, expectancy, etc.)
- `expectancy_unit` explicito (`usd_per_trade`) en runs catalogados
- Costos netos y `costs_ratio` usados en ranking/constraints
- Breakdown por regimen (`trend`, `range`, `high_vol`, `toxic`) persistido por run (JSON)
- Flags de run (`OOS`, `WFA`, `PASO_GATES`, `BASELINE`, `FAVORITO`, `ARCHIVADO`, etc.)

### NO-DONE
- Chip de ROBUSTEZ Alta/Media/Baja con tooltip en la tabla principal de runs
- Tabla dedicada de KPI por regimen en `Backtests / Runs` (hoy se ve en comparador/research)

---

## C) Single vs Batch (confusion de producto)

### DONE
- Renombre UI:
  - `Quick Backtest` (single)
  - `Research Batch` (batch experiment)
- Panel "Que usa este modo?" explicando diferencias y cuando conviene usar cada modo
- Aclaracion de que ambos terminan en **Backtest Runs** comparables

### NO-DONE
- Tooltips contextuales en todos los botones del flujo (extra UX)

---

## D) Comparador profesional (sin limite 5)

### DONE
- **D1 Shortlist** (5-10) con seleccion de runs del catalogo
- **D2 Comparison Table Pro (base)** con 50/100/250/500 filas visibles y columnas configurables
- **D3 Deep Compare (base)** 2-4 runs con:
  - tabla comparativa de KPIs
  - overlays de equity y drawdown si hay detalle legacy
- Rankings con presets compuestos (`conservador`, `balanceado`, `agresivo`, `cost-aware`, `oos-first`)
- Constraints visibles (min trades / max DD / Sharpe + OOS/data_quality en ranking)
- Warning por `dataset_hash` distintos en comparacion

### NO-DONE
- Virtualizacion real de tabla pro (50-500+ sin render completo)
- Deep Compare avanzado:
  - heatmap mensual
  - rolling Sharpe
  - distribucion de retornos
  - lista de trades comparativa
- Export directo desde comparador pro

---

## E) UI Backtests (UX data-heavy)

### DONE
- Pantalla `Backtests` extendida con:
  - Quick Backtest
  - Research Batch
  - Backtests / Runs (catalogo)
  - Comparador profesional base
- Filtros + buscador + sort server-side sobre runs del catalogo
- Acciones por fila implementadas:
  - comparar
  - alias
  - fijar/desfijar
  - archivar/desarchivar
  - validar/promover (bloque 5)

### NO-DONE
- Tabla virtualizada (performance UI)
- Estados visuales avanzados con progreso por etapa (`preparing/running/...`) desde catalogo/runtime unificados
- Acciones completas:
  - `rerun_exact`
  - `clone_edit`
  - `export csv/json/pdf` desde catalogo
  - `tags` UI completa

---

## F) Research -> Validate -> Promote (loop profesional)

### DONE
- `validate_promotion` por run del catalogo:
  - constraints
  - offline gates
  - compare vs baseline
- `promote` por run del catalogo:
  - inicia rollout offline (Opcion B)
  - sin auto-live
  - actualiza flags de catalogo (`PASO_GATES`, `BASELINE`, `FAVORITO`)
- Integracion con `Rollout / Gates` existente (sin duplicar pantalla)

### NO-DONE
- Botones de promocion por target (`paper` / `testnet`) diferenciados en UI
- Wizard guiado de promocion con confirmaciones paso a paso

---

## G) Endpoints API (minimos)

### DONE
- `GET /api/v1/runs?filters...`
- `GET /api/v1/runs/{run_id}`
- `PATCH /api/v1/runs/{run_id}` (alias/tags/pin/archive)
- `GET /api/v1/batches`
- `POST /api/v1/batches`
- `GET /api/v1/batches/{batch_id}`
- `GET /api/v1/compare?r=...`
- `GET /api/v1/rankings?preset=...&constraints...`
- `POST /api/v1/runs/{run_id}/validate_promotion`
- `POST /api/v1/runs/{run_id}/promote`

### NO-DONE
- `POST /api/v1/runs/{run_id}/rerun_exact`
- `POST /api/v1/runs/{run_id}/clone_edit`
- `GET /api/v1/export/run/{run_id}?format=csv|json|pdf` (catalogo unificado)

Nota: existe export legacy via `/api/v1/backtests/runs/{legacy_id}?format=...`

---

## H) Tests (minimos serios)

### DONE
Backend
- Unit: catalogo IDs/run record + fingerprint/provenance persistente
- Unit: query/sort + patch metadata + patch flags + rankings compuestos
- Unit: mass backtest persiste resultados + batch children en catalogo + `expectancy_unit`
- Smoke: endpoints `runs/batches/compare/rankings`
- Smoke: `validate_promotion` / `promote` (success o fail-closed valido)

Frontend
- Type-check (`tsc`) de `Backtests` y tipos nuevos

### NO-DONE
Frontend tests automaticos
- Smoke UI de runs table + filtros
- E2E crear batch -> runs -> comparar -> ranking

---

## Checklist global (DONE / NO-DONE)

- [x] Single vs Batch claro en UI
- [x] Runs con identidad estructurada + alias opcional
- [x] Comparacion >5 (tabla amplia base)
- [x] Ranking con constraints (evita ganadores truchos)
- [x] Reproducibilidad visible (dataset hash, commit hash, costos, params, seed)
- [x] Loop Research -> Validate -> Promote (Opcion B, sin auto-live)
- [ ] Tabla Pro virtualizada (50+ sin render full)
- [ ] Deep Compare avanzado (heatmaps/rolling metrics/trades)
- [ ] Endpoints `rerun_exact`, `clone_edit`, export unificado por catalogo
- [ ] Frontend smoke/E2E tests automatizados

---

## Como probar manualmente (5 pasos)

1. **Crear Quick Backtest**
   - Ir a `Backtests`
   - Ejecutar `Quick Backtest`
   - Verificar que aparece en `Backtests / Runs` con ID `BT-xxxxx`, dataset hash y commit hash

2. **Crear Research Batch**
   - En `Research Batch`, elegir estrategias + parametros basicos
   - Click en `Ejecutar Backtests Masivos`
   - Verificar que aparece un `BX-xxxxx` en batches y que se generan `batch_child` (`BT-xxxxx`)

3. **Comparar y rankear**
   - En `Backtests / Runs`, seleccionar 2-4 runs con "Comparar"
   - Revisar `Comparador Profesional` (shortlist + table + deep compare)
   - Probar constraints (`min_trades`, `max_dd`, `Sharpe`) y ranking presets

4. **Validar promocion (Opcion B)**
   - En una fila de run, click `Validar`
   - Verificar panel `Research -> Validate -> Promote`:
     - constraints
     - offline gates
     - compare vs baseline
     - `rollout_ready`

5. **Promover a rollout (sin LIVE automatico)**
   - Click `Promover` en un run validado
   - Confirmar mensaje de exito y luego ir a `Settings -> Rollout / Gates`
   - Continuar con paper/testnet soak / canary / rollback / approve (manual)

---

## Confirmaciones clave (Backtests & Research System)

- No se rompio runtime LIVE/OMS: SI
- No se auto-promueve a LIVE: SI (Opcion B)
- APIs existentes se extendieron sin romper compatibilidad: SI
- Cambios organizados por bloques, sin refactor masivo: SI
