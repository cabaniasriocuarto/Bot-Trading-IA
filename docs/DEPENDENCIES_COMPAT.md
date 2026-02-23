# Compatibilidad de Dependencias (Runtime vs Research)

## Objetivo
Mantener el runtime (paper/testnet/live) **liviano y estable**, y mover librerías pesadas/experimentales al stack de **research offline**.

## 1) Separación actual
### Runtime (`requirements-runtime.txt`)
Uso en backend/API/runtime:
- `fastapi`, `uvicorn`, `pydantic`
- `requests`, `httpx`, `websockets`
- `PyYAML`
- `numpy`, `pandas`, `scipy`
- utilidades CLI (`typer`, `rich`)

### Research (`requirements-research.txt`)
Uso offline / research masivo:
- `pyarrow` (Parquet)
- `duckdb` (ranking/query sobre Parquet)
- `joblib`, `tqdm`
- `optuna`
- `quantstats`, `empyrical-reloaded`
- `statsmodels`, `arch`
- `ruptures`
- `river` (drift offline opcional)
- `pandera[pandas]`
- `mlflow-skinny`
- `vectorbt`, `PyPortfolioOpt`, `riskfolio-lib`, `cvxpy`

## 2) Riesgos de compilación / peso
Dependencias con mayor probabilidad de “hacer ruido” (build/instalación):
- `cvxpy`
- `vectorbt`
- `riskfolio-lib`
- `pyarrow`
- `arch`

Impacto:
- tiempos de instalación altos
- binarios/ruedas según SO/Python
- posibles conflictos de versiones si se mezclan entornos

Mitigación:
- usar `requirements-runtime.txt` en Railway/backend live
- usar `requirements-research.txt` en entorno de research (local/VPS research)
- no instalar research en producción live salvo necesidad real

## 3) Cómo confirmar conflictos (script)
Script agregado:
- `scripts/deps_check.sh`

Qué hace:
- `pip check`
- `pipdeptree --warn fail`

Uso:
```bash
bash scripts/deps_check.sh
```

Interpretación:
- **Exit 0**: no se detectaron conflictos en el entorno actual
- **Exit 2**: falta `pipdeptree` (instalarlo y reintentar)
- **Exit !=0**: hay conflictos o paquetes rotos en el entorno

## 4) Auditoría de vulnerabilidades (script)
Script agregado:
- `scripts/security_audit.sh`

Qué hace:
- `pip-audit` sobre runtime y research
- intenta SBOM CycloneDX si encuentra herramienta compatible

Interpretación:
- vulnerabilities en `runtime` => prioridad alta (bloqueante para LIVE si son críticas)
- vulnerabilities solo en `research` => evaluar impacto según uso (menos crítico que runtime, pero hay que corregir)

## 5) Estado de compatibilidad (actual)
- El código actual mantiene runtime y research **separados**.
- Las nuevas capabilities (`ruptures`, `mlflow`, etc.) se detectan por disponibilidad y hacen fallback seguro si faltan.
- El backend no rompe si faltan librerías de research.

## 6) Recomendación “release candidate”
- Runtime deploy: instalar **solo** `requirements-runtime.txt`
- Research/mass backtests: usar entorno separado con `requirements-research.txt`
- Ejecutar `deps_check` y `security_audit` antes de cada release candidate
