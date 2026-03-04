# UI/UX FINAL `Research-first` (Entrega por Bloques)

Fecha: 2026-02-26  
Alcance: Frontend UX/UI + wiring minimo (sin refactor masivo, sin tocar core de trading)

## 1) Plan de ataque por pantallas (que se unifico / movio / aclaro)

### Backtests
- Flujo oficial visible:
  - `Quick Backtest` (single)
  - `Research Batch` (batch)
  - ambos producen `Runs`
- `Backtests / Runs` consolidado como lista principal de resultados
- Comparador profesional de runs (shortlist / tabla / deep compare)
- `Detalle de Corrida` reestructurado como `Strategy Tester` por pestanas:
  - Overview
  - Performance
  - Trades analysis
  - Risk / ratios
  - Listado de trades
  - Artifacts
- `Quick Backtest Legacy` marcado como **Deprecado** y colapsado (compatibilidad)

### Settings / Rollout
- Empty states con CTA concretas en lugar de `N/A / SIN_EVAL`
- Diagnostico WS/SSE corregido (evita falso timeout)

### Ejecucion
- Convertida en pantalla clara de:
  - `Trading en Vivo (Paper / Testnet / Live) + Diagnostico`
- Mantiene metricas de ejecucion abajo
- Agrega checklist `Live Ready`, estado de conectores y controles admin

### Riesgo
- Se enfoca en riesgo (limites, exposicion, stress)
- Se evita duplicar `gates` operativos (quedan en `Settings > Rollout / Gates`)
- Explicacion de correlacion / concentracion + CTA

### Portfolio
- Proposito mas claro
- Historial con timestamp, tipo y link de detalle
- Empty states guiados

### Operaciones (Trades) y Alertas
- Filtros con labels claros (`Todos los simbolos`, `Todas las estrategias`, etc.)
- Empty states con CTA
- Mejor contexto en tabla/listados

## 2) Lista de archivos tocados (minimos)

- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/app/(app)/settings/page.tsx`
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `rtlab_dashboard/src/app/(app)/portfolio/page.tsx`
- `rtlab_dashboard/src/app/(app)/risk/page.tsx`
- `rtlab_dashboard/src/app/(app)/trades/page.tsx`
- `rtlab_dashboard/src/app/(app)/alerts/page.tsx`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`
- `docs/UI_UX_RESEARCH_FIRST_FINAL.md`

## 3) Checklist DONE

### A) Unificar conceptos (product model)
- [x] Quick Backtest vs Research Batch en `Backtests`
- [x] Runs como salida unificada visible
- [x] Legacy marcado como deprecado (compatibilidad)

### B) Metadata minima siempre
- [x] Runs muestran ID, tipo, estado, timestamp, estrategia, dataset hash, commit, costos, KPIs
- [x] Historial de Portfolio con timestamp + tipo + detalle
- [x] Operaciones/Trades con timestamp y detalle

### C) Empty states con “Que hacer ahora”
- [x] Settings / Rollout
- [x] Portfolio
- [x] Ejecucion
- [x] Riesgo
- [x] Alertas / Trades

### D) Runs list profesional
- [x] Paginacion (30/60/100)
- [x] Filtros + buscador + sort base
- [x] Acciones basicas por run (alias/pin/archive/compare/validar/promover)
- [ ] Virtualizacion real (queda para siguiente fase)

### E) Backtests estilo Strategy Tester
- [x] Pestanas Overview / Performance / Trades analysis / Ratios / Trades list / Artifacts
- [x] KPI y graficos base reutilizando datos existentes
- [ ] Graficos avanzados (heatmap mensual / rolling Sharpe / distribuciones) en esta fase

### F) Dónde se opera (Paper/Testnet/Live)
- [x] Pantalla `Ejecucion` con panel operativo claro
- [x] Checklist `Live Ready`
- [x] Estado de conectores + diagnostico
- [x] Controles admin con confirmaciones

### G) Consistencia visual
- [x] Labels en espanol y con contexto
- [x] Empty states guiados
- [x] KPIs con grading visual en Backtests
- [ ] Componente unico reutilizable para todos los empty states (posible mejora)

### H) Tests / no romper
- [x] `tsc` frontend en verde
- [ ] Smoke tests frontend automatizados (pendiente)

## 4) Como probar manualmente (5 pasos)

1. **Settings**
   - Abri `Configuracion`
   - Proba `WS` y `Exchange`
   - Verifica que `WS` no marque falso timeout y que los empty states de `Rollout / Gates` muestren CTA

2. **Ejecucion**
   - Abri `Ejecucion`
   - Cambia `Mock/Paper/Testnet` (admin) y verifica `Aplicar modo`
   - Revisa checklist `Live Ready`, conectores y controles (`Pausar/Reanudar/Modo seguro/Kill switch`)

3. **Backtests / Runs**
   - Abri `Backtests`
   - Verifica paginacion, filtros y labels
   - Selecciona runs para shortlist/comparador

4. **Detalle de Corrida (Strategy Tester)**
   - Elige una corrida con trades
   - Navega pestanas `Overview`, `Performance`, `Trades analysis`, `Ratios`, `Listado`, `Artifacts`
   - Confirma metadata (`dataset_hash`, `commit`, costos, expectancy con unidad)

5. **Research → Validate → Promote**
   - En `Backtests / Runs`, usa `Validar` y luego `Promover` en un run apto
   - Ir a `Settings > Rollout / Gates`
   - Confirmar que sigue Opcion B (sin auto-live)

## 5) Notas de alcance (scope lock)

- Sin refactor masivo
- Sin reestructurar carpetas
- Sin cambios de core trading/execution/risk (solo UX + wiring minimo)
- Sin secretos hardcodeados

