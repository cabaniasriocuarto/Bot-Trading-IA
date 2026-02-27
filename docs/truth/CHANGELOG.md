# CHANGELOG (Truth Layer)

## 2026-02-27

### Backtests / Runs (bloque continuo de UX + escala)
- Runs table ahora permite ordenar haciendo click en cabeceras (Run ID, Fecha, Estrategia, Ret%, MaxDD, Sharpe, PF, WinRate, Trades, Expectancy) con toggle asc/desc.
- Se agregó `sort_by=winrate` en backend (`BacktestCatalogDB.query_runs`) para ranking directo por winrate.
- Se eliminó el límite rígido de `5` en selección legacy (`selectedRuns`) para no recortar comparaciones manuales.
- Parser de errores UI reforzado (`uiErrMsg`) para evitar renderizar `[object Object]` y mostrar mensajes útiles (`detail/message/error/cause`).
- Tests actualizados: `test_backtest_catalog_db.py` valida ordenamiento por `winrate`.

### Research Batch (shortlist BX persistente)
- Backend:
  - nuevo `BacktestCatalogDB.patch_batch(...)` para actualizar `best_runs_cache`/summary del batch.
  - nuevo endpoint `POST /api/v1/batches/{batch_id}/shortlist` (admin) para guardar shortlist de variantes/runs.
- Frontend (`Backtests > Research Batch`):
  - botones `Guardar shortlist BX` y `Cargar shortlist BX`.
  - restauración automática de shortlist al seleccionar un batch.
  - en tabla de Batches se muestra columna `Shortlist` (cantidad guardada) y acción `Cargar shortlist`.
- Tests:
  - `test_web_live_ready.py::test_batch_shortlist_save_and_load`
  - `test_backtest_catalog_db.py` cubre patch de batch con `best_runs_cache`.

### Backtests / Strategies (bloque UX escala)
- `Backtests / Runs` D2 (`Comparison Table Pro`) ahora usa virtualizacion por ventana visible:
  - contenedor con scroll vertical fijo
  - render de filas visibles + overscan
  - espaciadores superior/inferior para mantener altura total
  - contador de ventana (`X-Y de N`) para trazabilidad visual.
- `Strategies` compactado para escalar mejor con 50+ estrategias:
  - filas mas bajas (`align-middle`, menor padding)
  - acciones visibles reducidas en fila (selector compacto + menu `Mas`)
  - menor ancho minimo de columna de acciones.

### Operaciones / Trades (Bloque 3)
- Tabla de operaciones ahora tiene orden configurable (`timestamp`, `PnL`, `estrategia`, `simbolo`, `modo`, `fees`, `slippage`, `qty`).
- Seleccion masiva por checkbox:
  - seleccionar/quitar pagina
  - limpiar seleccion
  - borrar operaciones seleccionadas (admin).
- Borrado filtrado con `preview` (`dry_run`) antes de ejecutar borrado real.
- Resumen operacional extendido:
  - panel por `modo + entorno` clickable para aplicar filtros rapidos
  - `Top estrategias` ahora permite aplicar filtro directo por estrategia.
- En tabla de trades, `strategy_id` es clickable para filtrar al instante.

### Ejecucion / Live Admin (Bloque 4)
- Nuevo panel de **estrategias primarias por modo** dentro de `Ejecucion`:
  - selector y guardado rapido de primaria para `PAPER`, `TESTNET` y `LIVE`
  - usa endpoint existente `POST /api/v1/strategies/{id}/primary` (sin API nueva).
- Modo `LIVE` mas seguro y explicito en UI:
  - muestra bloqueos concretos de checklist (`keys`, `connector`, `gates`)
  - boton `Aplicar modo` se bloquea si `LIVE` no esta listo.
- Administracion de operadores mas intuitiva:
  - atajos de seleccion masiva `Seleccionar activos` y `Seleccionar modo runtime`
  - mensaje contextual que separa runtime global vs operadores de aprendizaje.

## 2026-02-26

### RTLAB Strategy Console (Bloque 1 - Policies numericas)
- Agregada carpeta `config/policies/`
- `gates.yaml` con numeros explicitos para `PBO/CSCV`, `DSR`, `walk_forward`, `cost_stress`, calidad minima de trades
- `microstructure.yaml` con Order Flow L1 (`VPIN`, spread_guard, slippage_guard, volatility_guard)
- `risk_policy.yaml` con soft/hard kill por `bot/strategy/symbol`
- `beast_mode.yaml` con limites (`5000 trials`, concurrencia, budget governor)
- `fees.yaml` con TTLs y fallback maker/taker

### RTLAB Strategy Console (Bloques 2-7)
- Backend: `GET /api/v1/config/policies` + resumen numerico de policies
- Backend: `GET /api/v1/config/learning` extendido con `numeric_policies_summary`
- Research Batch: persistencia de `policy_snapshot` / `policy_snapshot_summary`
- Cost model baseline:
  - `FeeProvider`, `FundingProvider`, `SpreadModel`, `SlippageModel`
  - snapshots persistentes en SQLite
  - metadata de costos/snapshots por `BT-*`
- Order Flow L1 (VPIN proxy desde OHLCV) en motor masivo + debug UI + flags `MICRO_SOFT_KILL` / `MICRO_HARD_KILL`
- Gates avanzados en research masivo (PBO/DSR/WF/cost stress/min trade quality) con PASS/FAIL visible y bloqueo fail-closed de `mark-candidate`
- Modo Bestia (fase 1):
  - scheduler local con cola de jobs, concurrencia y budget governor
  - endpoints `/api/v1/research/beast/start|status|jobs|stop-all|resume`
  - panel UI de Modo Bestia en `Backtests`

### UI/UX Research-first (Bloques 1-6)
- Fix del falso `WS timeout` en diagnostico SSE (`/api/events`)
- `Backtests / Runs`: paginacion obligatoria (30/60/100), labels mas claros, empty state con CTA
- `Settings > Rollout / Gates`: empty states accionables en offline gates / compare / fase / telemetria
- `Portfolio`: empty states guiados + historial con timestamp/tipo/detalle
- `Riesgo`: foco en riesgo (sin duplicar gates) + explicacion de correlacion/concentracion
- `Ejecucion`: panel `Trading en Vivo (Paper/Testnet/Live) + Diagnostico` con checklist `Live Ready`, conectores y controles admin
- `Trades` y `Alertas`: filtros con labels en espanol + empty states guiados
- `Backtests`: `Detalle de Corrida` con pestanas estilo Strategy Tester
- `Backtests`: `Quick Backtest Legacy` marcado como deprecado y colapsado

### Documentacion
- `docs/UI_UX_RESEARCH_FIRST_FINAL.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`
