# Shadow Mode

## Que es

`shadow` es mock en vivo.

Usa market data real.
No envia ordenes.
Simula fills/costos con el mismo motor del backtest.
Guarda experiencia persistente como `source=shadow`.

## Que NO es

- no es `paper`
- no es `testnet`
- no es `live`

## Componentes reales

- runner:
  - `rtlab_autotrader/rtlab_core/learning/shadow_runner.py`
- coordinador:
  - `ShadowRunCoordinator` en `rtlab_autotrader/rtlab_core/web/app.py`
- persistencia:
  - `ExperienceStore`
  - `RegistryDB`

## Endpoints

- `GET /api/v1/learning/shadow/status`
- `POST /api/v1/learning/shadow/start`
- `POST /api/v1/learning/shadow/stop`

## Requisitos operativos

Para que un bot entre a shadow:

- `status = active`
- `mode = shadow`
- estrategia valida en registry
- la estrategia debe tener `allow_learning = true`
- login admin para `start/stop`

## Timeframes soportados hoy

Implementacion actual:

- `5m`
- `10m`
- `15m`

No hay evidencia en esta version de soporte por tick ni de timeframes arbitrarios.

## Fuente de market data

Implementacion actual:

- klines publicos de Binance Spot
- `bookTicker` publico para spread observado

Base operativa:

- `https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints`

## Parametros utiles

Defaults actuales del runner:

- `lookback_bars = 300`
- `validation_mode = shadow_live`
- `use_orderflow_data = true`
- costos base:
  - `fees_bps = 5.5`
  - `spread_bps = 4.0`
  - `slippage_bps = 3.0`
  - `funding_bps = 1.0`
  - `rollover_bps = 0.0`

Si el spread observado en `bookTicker` existe, reemplaza el spread base.

Nota operativa:

- con ventanas cortas (ej. `120`) puede fallar el primer ciclo si la estrategia necesita warmup real de ~250 velas;
- el default se deja en `300` para que el modo mock funcione sin ajuste manual en esta version.

## Que guarda

Cada ciclo cerrado persiste:

- episodio `source=shadow`
- eventos `enter/exit/skip/...`
- `latency_ms`
- `spread_bps`
- `vpin_value` si existe
- costos desglosados
- `dataset_source = binance_public_klines`
- `dataset_hash`
- `feature_set`

## Como verlo en UI

En `Strategies`:

- resumen de experiencia
- estado de shadow
- iniciar/detener shadow
- experiencia por fuente por bot
- propuestas Opcion B

## Kill switch operativo

`shadow` tambien tiene stop explicito:

- `POST /api/v1/learning/shadow/stop`

Y el coordinador corta el loop si:

- se desactiva el runner
- el bot deja de estar en `mode=shadow`
- el bot ya no esta activo

## Limites conocidos

- NO EVIDENCIA de ordenes reales en shadow: por diseno no envia.
- NO EVIDENCIA de simulacion por tick: la frecuencia operativa es por vela cerrada.
- NO EVIDENCIA de promotion automatica desde shadow a runtime.

## Base bibliografica utilizada

Fuentes locales:

- `16 - Backtesting-and-its-Pitfalls.pdf`
- `6 - Flow Toxicity and Liquidity in a High-Frequency World — Easley, Lopez de Prado y O'Hara (2012).pdf`
- `1 - Hasbrouck's book.pdf`

Fuente oficial web:

- Binance Spot API Docs:
  - `https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints`

## Que decision de diseno respalda cada fuente

- Backtesting and its Pitfalls:
  - separar shadow de backtest y explicitar que shadow no equivale a fill real.
- Flow Toxicity:
  - registrar `VPIN` y regimen `toxic` cuando existe feature.
- Hasbrouck:
  - observar spread y penalizar costos reales de microestructura.
- Binance docs:
  - justificar el origen del market data publico usado por el runner.
