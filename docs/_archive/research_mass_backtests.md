# Motor de Backtests Masivos (Research Offline)

Objetivo: ejecutar backtests masivos con evidencia robusta y **sin performance-chasing**, alimentando Opción B (recomendaciones) sin tocar LIVE automáticamente.

## Reglas de seguridad
- Opción B: **NO auto-live**
- Promoción real: `gates + canary + rollback + approve`
- Anti-performance-chasing:
  - ventanas mínimas (paper/testnet >= 7 días, live >= 14 días)
  - límites de cambios por ventana
  - validación walk-forward + costos + robustez

## Endpoints
- `POST /api/v1/research/mass-backtest/start`
- `GET /api/v1/research/mass-backtest/status?run_id=...`
- `GET /api/v1/research/mass-backtest/results?run_id=...`
- `GET /api/v1/research/mass-backtest/artifacts?run_id=...`
- `POST /api/v1/research/mass-backtest/mark-candidate`

## Persistencia
- Carpeta por corrida: `user_data/research/mass_backtests/{run_id}/`
- Archivos:
  - `status.json`
  - `results.json`
  - `results.parquet` (si `pyarrow`/`pandas` está disponible)
  - `manifest.json`
  - `artifacts/index.html`
- Metadata SQLite: `user_data/research/mass_backtests/metadata.sqlite3`

## Ranking robusto
No se ordena por PnL bruto. Se usa score compuesto (Sharpe/Calmar/Expectancy/Stability/Costs/DD) + filtros duros.

## Nota de implementación actual
- Reutiliza el backtest del bot (modo synthetic o event-driven si hay dataset).
- En research offline se aplica ajuste reproducible por variante/fold para simular sensibilidad paramétrica mientras se mantiene el runtime intacto.
- PBO/DSR están en modo proxy/fail-closed para promoción (sirve para evidencia y bloqueo, no para auto-promover).

## Instalación
- Runtime: `./scripts/install_runtime.ps1` o `./scripts/install_runtime.sh`
- Research: `./scripts/install_research.ps1` o `./scripts/install_research.sh`
