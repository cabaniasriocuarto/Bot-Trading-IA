# Stack de Research (offline) - RTLAB

Objetivo: separar **runtime live** (liviano/estable) de **research offline** (optimización, experimentos, explainability) sin tocar el runtime de ejecución.

## Reglas
- `requirements-runtime.txt`: solo lo necesario para correr backend, riesgo, ejecución, backtests y UI API.
- `requirements-research.txt`: agrega librerías de investigación offline; no se requiere en deploy live.
- Opción B: research **recomienda**; promoción a LIVE pasa por gates + canary + aprobación humana.

## Librerías y uso previsto
- `vectorbt`: prototipado/backtests rápidos offline, screening de ideas.
- `optuna`: HPO controlado (con rangos del Knowledge Pack y gates anti-overfitting).
- `quantstats`: reportes y análisis de equity/returns offline.
- `empyrical-reloaded`: métricas financieras (Sharpe/Sortino/Calmar y afines).
- `statsmodels`: ADF, cointegración, regresiones y análisis estadístico.
- `arch`: GARCH / volatilidad condicional offline.
- `riskfolio-lib` + `PyPortfolioOpt` + `cvxpy`: preview de allocation/pesos por portafolio (NO auto-live).
- `mlflow-skinny`: tracking liviano de experimentos offline.
- `ruptures`: detección de change-points offline (quiebres estructurales).
- `scikit-learn`: meta-modelos offline (RF selector, features por régimen).

## Instalación
### Runtime (live/paper/testnet)
- PowerShell: `./scripts/install_runtime.ps1`
- Bash: `./scripts/install_runtime.sh`

### Research (offline)
- PowerShell: `./scripts/install_research.ps1`
- Bash: `./scripts/install_research.sh`

## Nota de estabilidad
- Si alguna librería research trae conflictos nativos (ej. `cvxpy`, `vectorbt`), instalarla solo en entornos de research (local/VPS research) y dejar Railway/Vercel con runtime mínimo.
