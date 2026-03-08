# README breve (Cerebro + Knowledge Pack + Backtests UI)

## Alcance implementado

- CEREBRO (agresividad media) con selector configurable:
  - `thompson` (default)
  - `ucb1`
  - `regime_rules`
- Drift detection configurable:
  - `adwin` (default)
  - `page_hinkley`
- Research Loop Opción B:
  - genera recomendaciones Top N
  - **no aplica cambios a LIVE**
  - adopción manual solo `paper` / `testnet`
- Knowledge Pack en `/knowledge` con templates/filtros/rangos/gates/glosario
- Upload de estrategia por `ZIP` y `YAML`
- Backtests:
  - métricas/costos extra en `report.json`
  - celdas coloreadas + leyenda en comparador
  - “Cantidad de entradas” visible
- Settings:
  - toggles/selectores de Cerebro/Aprendizaje
  - tooltips en español

## Endpoints nuevos

- `GET /api/v1/learning/status`
- `POST /api/v1/learning/run-now`
- `GET /api/v1/learning/drift`
- `GET /api/v1/learning/recommendations`
- `GET /api/v1/learning/recommendations/{id}`
- `POST /api/v1/learning/adopt` (`mode`: `paper|testnet`)

## Activar Research (Opción B)

En `Settings -> Cerebro / Aprendizaje`:

1. Activar `Aprendizaje`
2. `Mode = RESEARCH`
3. Elegir `Selector` y `Drift`
4. Guardar
5. Ejecutar `POST /api/v1/learning/run-now`

## Seguridad / restricción LIVE

- `allow_auto_apply=false`
- `allow_live=false`
- `POST /api/v1/learning/adopt` no acepta `live`

## Notas

- El research loop intenta evaluar con datos reales (`DataLoader + BacktestEngine`) cuando hay datasets disponibles.
- Si faltan datasets, usa fallback de corridas existentes para no romper el flujo de recomendaciones (sin tocar LIVE).
