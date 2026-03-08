# Validacion local experience learning + shadow + beast

Fecha: 2026-03-06 (ART) / 2026-03-07 (UTC)
Branch: `feature/learning-experience-v1`
Commit validado local: `ffabe9e`

## Objetivo

Confirmar el estado real del bloque `experience learning + shadow/mock + modo bestia` con evidencia ejecutable, sin asumir que la UI publicada ya refleja la rama tecnica.

## Cambios tecnicos validados

- `ShadowRunConfig` ahora usa `default_factory` para `costs`, evitando el crash de import en Python 3.13 por default mutable.
- `lookback_bars` default de shadow/mock sube de `240` a `300` en:
  - runtime interno del runner
  - default de API (`ShadowStartBody`)
  - default de entorno (`SHADOW_DEFAULT_LOOKBACK_BARS`)
- `MassBacktestCoordinator._default_beast_policy_cfg()` ya resuelve la policy real desde `self.engine.repo_root`, evitando fallo cuando la cola de Beast esta vacia.

## Evidencia 1: Modo Bestia con dataset real

Fuente de datos:

- dataset real `BTCUSDT 5m`
- guardado bajo `tmp/learning_experience_validation_20260306/user_data/data/crypto/processed/BTCUSDT_5m.csv`

Estado previo (`/api/v1/research/beast/status`):

- `enabled=true`
- `requires_postgres=true`
- `mode=local_scheduler_phase1`
- `queue_depth=0`

Ejecucion:

- `POST /api/v1/research/beast/start` -> `200`
- `run_id=BX-000001`
- `state=QUEUED`
- `estimated_trial_units=12`

Resultado final:

- job `BX-000001` -> `COMPLETED`
- `strategy_count=6`
- `market=crypto`
- `symbol=BTCUSDT`
- `timeframe=5m`

Conclusion:

- hoy el codigo NO deja `Modo Bestia` deshabilitado por policy del repo;
- si la UI publicada muestra `deshabilitado`, el problema es de deploy/snapshot serializado o frontend viejo, no del YAML actual.

## Evidencia 2: Shadow/mock con default corto (falla reproducible)

Corrida controlada con `lookback_bars=120`:

- `POST /api/v1/learning/shadow/start` -> `200`
- el runner inicia, pero el primer ciclo falla con:
  - `Dataset demasiado corto para backtest (min ~250 velas)`
- `episodes_written=0`

Conclusion:

- el modo shadow estaba conceptualmente integrado, pero el default corto lo hacia fallar en la practica para estrategias con warmup real mas largo.

## Evidencia 3: Shadow/mock con default corregido

Corrida controlada con el default corregido (`lookback_bars=300`):

- `POST /api/v1/learning/shadow/start` -> `200`
- `runs_created=1`
- `episodes_written=1`
- `last_run_ids=["SH-000001"]`
- `last_error=""`

Ultimo episodio persistido:

- `source=shadow`
- `source_weight=1.0`
- `validation_quality=shadow_live_market_data`
- `cost_fidelity_level=runtime_simulated_live_data`
- `dataset_source=binance_public_klines`
- `feature_set=orderflow_on`
- `trade_count=5`
- `mode=shadow`

Conclusion:

- hoy el shadow/mock SI genera experiencia persistente util cuando se le da una ventana de datos consistente con el motor de backtest.

## Evidencia 4: Experience store y Opcion B

Sobre la validacion local del bloque:

- `experience_episodes=8` (backtest/batch) en la corrida de beast
- `experience_events=508`
- `contexts=3`
- `proposals_needs_validation=3`

Interpretacion:

- la capa de aprendizaje no auto-activa nada;
- genera propuestas conservadoras y las deja en estado de validacion pendiente cuando falta evidencia suficiente.

## Validaciones ejecutadas

- `python -m py_compile rtlab_autotrader/rtlab_core/learning/shadow_runner.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_learning_experience_option_b.py`
- `python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q`
- `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q`

Resultado:

- PASS

## Estado del preview remoto de esta rama

Commit `ffabe9e`:

- `Vercel – bot-trading-ia` -> `failure`
- `Vercel – bot-trading-ia-csud` -> `failure`

Conclusion:

- la rama tecnica esta validada localmente para este bloque;
- el preview web de Vercel sigue abierto como problema separado de deploy.

## Riesgos abiertos

- preview Vercel de la rama tecnica sigue fallando;
- shadow sigue siendo simulacion con market data real, no fill real;
- `Modo Bestia` sigue en `local_scheduler_phase1`, no en arquitectura distribuida final;
- LIVE sigue `NO GO`.
