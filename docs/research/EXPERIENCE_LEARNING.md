# Experience Learning

## Objetivo

Esta capa convierte resultados de `backtest`, `shadow`, `paper` y `testnet` en experiencia persistente y trazable para Opcion B.

No activa estrategias sola.
No habilita live.
No reemplaza validacion humana.

## Definiciones operativas

- `backtest`: corrida historica reproducible. Aporta experiencia con menor peso que runtime.
- `shadow`: mock en vivo. Usa market data real, no envia ordenes y simula fills/costos con el motor de backtest.
- `paper`: runtime con fondos virtuales.
- `testnet`: runtime sobre sandbox del exchange.

## Donde vive

- DB principal de registry:
  - `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- Store/hook de experiencia:
  - `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- Motor Opcion B:
  - `rtlab_autotrader/rtlab_core/learning/option_b_engine.py`
- Shadow runner:
  - `rtlab_autotrader/rtlab_core/learning/shadow_runner.py`

## Schema real implementado

### experience_episode

Persistencia por episodio de experiencia.

Campos principales:

- `id`
- `run_id`
- `source`
- `source_weight`
- `strategy_id`
- `asset`
- `timeframe`
- `start_ts`
- `end_ts`
- `dataset_source`
- `dataset_hash`
- `commit_hash`
- `costs_profile_id`
- `validation_quality`
- `cost_fidelity_level`
- `feature_set`
- `notes`
- `summary_json`

Restricciones reales:

- `PRIMARY KEY (id)`
- `UNIQUE(run_id, source, strategy_id, asset, timeframe, dataset_hash)`

Idempotencia real:

- el `episode_id` es deterministico y deriva de:
  - `run_id`
  - `source`
  - `strategy_id`
  - `asset`
  - `timeframe`
  - `dataset_hash`
  - `feature_set`
- ademas existe `UNIQUE` por run/contexto/dataset.

### experience_event

Persistencia granular por decision/trade.

Campos principales:

- `id`
- `episode_id`
- `ts`
- `regime_label`
- `features_json`
- `action`
- `side`
- `predicted_edge`
- `realized_pnl_gross`
- `realized_pnl_net`
- `fee`
- `spread_cost`
- `slippage_cost`
- `funding_cost`
- `latency_ms`
- `spread_bps`
- `vpin_value`
- `notes`

Eventos realmente generados hoy:

- `enter`
- `exit`
- `skip`
- `hold/reduce/add` si el run trae `decision_events`

### regime_kpi

Agregado por estrategia, activo, timeframe y regimen.

Campos reales:

- `strategy_id`
- `asset`
- `timeframe`
- `regime_label`
- `period_start`
- `period_end`
- `n_trades`
- `n_days`
- `expectancy_net`
- `expectancy_gross`
- `profit_factor`
- `sharpe`
- `sortino`
- `max_dd`
- `hit_rate`
- `turnover`
- `avg_trade_duration`
- `cost_ratio`
- `pbo`
- `dsr`
- `psr`
- `last_updated`

### learning_proposal

Propuesta explicable de Opcion B.

Campos reales:

- `id`
- `asset`
- `timeframe`
- `regime_label`
- `proposed_strategy_id`
- `replaces_strategy_id`
- `confidence`
- `rationale`
- `required_gates_json`
- `score_json`
- `metrics_json`
- `source_summary_json`
- `needs_validation`
- `status`
- `created_at`
- `reviewed_at`

Estados observables en el motor:

- `pending`
- `needs_validation`
- `approved`
- `rejected`

### strategy_policy_guidance

Guiado operativo derivado de experiencia.

Campos reales:

- `strategy_id`
- `preferred_regimes_json`
- `avoid_regimes_json`
- `min_confidence_to_recommend`
- `max_risk_multiplier`
- `max_spread_bps_allowed`
- `max_vpin_allowed`
- `cost_stress_result`
- `notes`
- `updated_at`

## Pesos por fuente

Implementados en `ExperienceStore.SOURCE_WEIGHTS`:

- `shadow = 1.00`
- `testnet = 0.90`
- `paper = 0.80`
- `backtest = 0.60`

Estos pesos alimentan:

- `source_weight` por episodio
- `source_quality_factor` en Opcion B
- score/confidence ponderados

## Como se genera experiencia hoy

### Backtest puntual

`ConsoleStore.create_event_backtest_run(...)` termina llamando:

- `record_experience_run(..., source_override="backtest")`

Cada corrida persiste:

- 1 episodio por `run_id + strategy + asset + timeframe + dataset`
- eventos de `enter/exit`
- eventos `skip` si el trade trae eventos rechazados
- costos desglosados
- `dataset_source`
- `dataset_hash`
- `commit_hash`
- `feature_set`

### Backtest masivo / batch

El batch usa callback por fold:

- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_mass_backtest_eval_fold(...)`
  - llama a `store.create_event_backtest_run(...)`

Por lo tanto, cada sub-run del batch genera experiencia real de backtest y queda trazado como `batch_child` en catalogo.

### Shadow / mock

`ShadowRunner`:

- consume market data vivo desde Binance public
- construye dataset OHLCV
- ajusta spread observado via `bookTicker`
- corre `BacktestEngine`
- no envia ordenes

El coordinador HTTP expone:

- `GET /api/v1/learning/shadow/status`
- `POST /api/v1/learning/shadow/start`
- `POST /api/v1/learning/shadow/stop`

Cada iteracion cerrada termina en:

- `create_shadow_live_run(...)`
- `record_experience_run(..., source_override="shadow", bot_id=...)`

## Costos y metricas usadas

### PnL neto

Definicion usada por experiencia:

`pnl_net = pnl_gross - fee - spread_cost - slippage_cost - funding_cost`

### Expectancy neta

El store usa `realized_pnl_net` por salida y agrega `expectancy_net` por promedio en `regime_kpi`.

### Profit Factor

Se calcula sobre `pnl_net` agregado por regimen.

### Sharpe / Sortino / Max DD

Se recalculan sobre la serie neta por regimen dentro de `ExperienceStore`.

### Cost ratio

Implementacion real:

`cost_ratio = total_costs / abs(sum(gross_pnls))`

### Cost stress 1.5x

Opcion B recalcula expectativa estresada por trade:

- `fee * 1.5`
- `spread_cost * 1.5`
- `slippage_cost * 1.5`
- `funding_cost * 1.5`

Si `cost_stress_expectancy < 0`, la propuesta queda bloqueada.

## Score y confidence reales

Implementacion actual en `OptionBLearningEngine.recalculate(...)`:

`score_raw =`

- `0.45 * expectancy_net_z`
- `+ 0.20 * profit_factor_z`
- `+ 0.10 * sharpe_z`
- `+ 0.10 * psr_z`
- `+ 0.05 * dsr_z`
- `- 0.10 * max_dd_z`
- `- 0.05 * turnover_cost_z`

Confidence actual:

- `trade_factor = min(1, log(1+n_trades_regime)/log(201))`
- `confidence = trade_factor * stability_factor * validation_factor * source_quality_factor * pbo_factor`

Donde:

- `stability_factor` usa dispersion de ventanas de `episode_net_pnls`
- `validation_factor` cae si hay synthetic, falta `pbo`, falta `dsr/psr` o mezcla de feature sets
- `source_quality_factor` resume la calidad ponderada por fuente
- `pbo_factor = 0.75` si no hay PBO, si no `1 - pbo`

## Criterios de elegibilidad reales

Una estrategia queda bloqueada si ocurre cualquiera de estos casos:

- `n_trades_total < 120`
- `n_days_total < 90`
- `n_trades_regime < 30`
- `expectancy_net <= 0`
- `cost_stress_1_5x < 0`
- `pbo > pbo_max` cuando hay `pbo`
- `dsr < dsr_min` cuando hay `dsr`
- mezcla de feature sets
- feature set distinto al baseline del contexto

Si faltan validaciones:

- el motor marca `needs_validation`
- no promociona nada solo

## Que aprende hoy

Aprende:

- ranking por `asset/timeframe/regime`
- guidance por estrategia:
  - regimenes preferidos
  - regimenes a evitar
  - `min_confidence_to_recommend`
  - `max_risk_multiplier`
  - `max_spread_bps_allowed`
  - `max_vpin_allowed`
  - `cost_stress_result`

No aprende hoy:

- activacion autonoma a live
- RL offline como motor core
- OPE robusto tipo IPS/DR/SWITCH en produccion

## Relacion con Strategy Registry

Solo se consideran estrategias con:

- `allow_learning = true`

Compatibilidad preservada:

- `enabled_for_trading`
- `allow_learning`
- `is_primary`

`is_primary` se usa como baseline preferido de comparacion cuando aplica.

## Order flow / feature set

La experiencia guarda:

- `feature_set`
- `use_orderflow_data`
- tags de provenance ya existentes en el repo

Opcion B castiga:

- mezcla de `feature_set`
- diferencia contra baseline del contexto

Esto preserva la regla de `same_feature_set` ya existente en el proyecto.

## NO EVIDENCIA / limites actuales

- NO EVIDENCIA de RL offline serio integrado como motor de produccion.
- NO EVIDENCIA de OPE conservador completo (`IPS`, `DR`, `SWITCH`) cableado al ranking final.
- NO EVIDENCIA de envio automatico de propuestas a canary runtime; hoy la aprobacion queda en capa humana/UI.
- NO EVIDENCIA de uso del shadow runner por tick; hoy el modelo operativo es por vela cerrada.

## Base bibliografica utilizada

Fuentes locales del proyecto:

- `11 - Advances in Financial Machine Learning — Marcos Lopez de Prado (2018).pdf`
  - soporte para DSR, PSR, meta-labeling, validacion robusta y sesgo por sobreoptimizacion.
- `16 - Backtesting-and-its-Pitfalls.pdf`
  - soporte para separar backtest de runtime, costos, leakage y necesidad de OOS.
- `17 - backtest-prob.pdf`
  - soporte para `PBO` y bloqueo conservador de estrategias sobreajustadas.
- `6 - Flow Toxicity and Liquidity in a High-Frequency World — Easley, Lopez de Prado y O'Hara (2012).pdf`
  - soporte para `VPIN` y etiqueta de regimen `toxic`.
- `1 - Hasbrouck's book.pdf`
  - soporte para costos de microestructura, spread, liquidez e impacto operativo.
- `7 - New Concepts in Technical Trading Systems — J. Welles Wilder Jr. (1978).pdf`
  - soporte para indicadores clasicos que aparecen en `features_json` como RSI/ADX/ATR.

Fuente oficial web usada para shadow market data:

- Binance Spot API Docs:
  - `https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints`

## Que decision de diseno respalda cada fuente

- Lopez de Prado / AFML:
  - usar `DSR`, `PSR`, gating por validacion y no confiar en PnL bruto.
- Backtesting and its Pitfalls:
  - exigir datos reales para batch/bestia y explicitar `NO EVIDENCIA` cuando faltan validaciones.
- backtest-prob:
  - usar `PBO` como bloqueo conservador cuando esta disponible.
- Easley / Lopez de Prado / O'Hara:
  - tratar `VPIN` y toxicidad como senales de regimen, no como adorno de UI.
- Hasbrouck:
  - desglosar `fee`, `spread`, `slippage`, `funding` y no mezclar costo bruto con edge real.
- Wilder:
  - mantener RSI/ADX/ATR como features explicables y no como cajas negras.
- Binance official docs:
  - justificar el origen de market data publico del `ShadowRunner`.

## Nota de calidad bibliografica

- `docs/reference/BIBLIO_INDEX.md` muestra extracciones vacias para algunas fuentes locales, por ejemplo el TXT asociado a O'Hara/Kyle.
- Donde el TXT local no ayudo, se privilegio:
  - otra fuente local util del mismo repositorio
  - documentacion oficial del exchange para la parte operativa de shadow
