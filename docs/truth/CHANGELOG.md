# CHANGELOG (Truth Layer)

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
