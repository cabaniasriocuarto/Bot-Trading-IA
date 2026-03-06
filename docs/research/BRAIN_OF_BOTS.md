# Brain Of Bots

## Que es

El cerebro del bot es una capa conservadora de seleccion y recomendacion.

No es un motor live autonomo.
No promociona estrategias solo.
No reemplaza Risk ni gates.

## Pipeline real

1. Strategy Registry define:
   - activa para trading
   - incluida en aprendizaje
   - principal/baseline
2. Experience Store acumula evidencia por:
   - backtest
   - shadow
   - paper
   - testnet
3. `regime_kpi` resume rendimiento neto por:
   - estrategia
   - activo
   - timeframe
   - regimen
4. `OptionBLearningEngine` calcula:
   - score
   - confidence
   - bloqueos
   - rationale
5. Se crea `learning_proposal`
6. El humano aprueba o rechaza

## Que decide

Decide recomendaciones del tipo:

- mejor estrategia por contexto
- top 3 por `asset/timeframe/regime`
- guia de uso por estrategia

No decide:

- live automatico
- promotion sin aprobacion
- cambio silencioso de baseline

## Contexto que usa

El motor agrupa por:

- `strategy_id`
- `asset`
- `timeframe`
- `regime_label`

Y conserva:

- `feature_set`
- `source_weight`
- `validation_quality`
- `cost_fidelity_level`

## Regimenes

Regimenes soportados hoy:

- `trend`
- `range`
- `high_vol`
- `toxic`
- `unknown`

La capa `unknown` no se usa como excusa para inventar edge; se usa como fallback cuando:

- no hay trades suficientes por regimen
- no hay etiqueta robusta
- la evidencia es insuficiente

## Como selecciona

La seleccion no se apoya en PnL bruto.

Prioriza:

- expectativa neta
- profit factor neto
- Sharpe / PSR / DSR
- drawdown
- costo y turnover
- estabilidad por ventanas
- calidad de fuente
- coherencia de feature set

Castiga:

- synthetic o validacion pobre
- mezcla de feature sets
- costo estresado negativo
- falta de evidencia por regimen

## Que aprende de cada fuente

### backtest

Sirve para:

- descubrir candidatos
- comparar variantes
- estudiar sensibilidad por activo/timeframe

Pesa menos que runtime.

### shadow

Sirve para:

- medir como se comporta la estrategia con market data real
- medir spread observado y latencia
- validar si el edge sobrevive fuera del historico puro

Es la fuente mas valiosa hoy dentro de no-live.

### paper / testnet

Sirven para:

- validar operacion runtime sin live
- contrastar con shadow y backtest

## Opcion B

La salida final no es "activar".

La salida final es:

- `proposal`
- `rationale`
- `required_gates`
- `status`

Estados practicos:

- `pending`
- `needs_validation`
- `approved`
- `rejected`

## Relation con baseline

El cerebro compara candidatos contra baseline cuando existe una estrategia principal.

Guardas vigentes:

- `same_feature_set`
- chequeo contra `baseline_feature_set`
- bloqueo si hay mezcla o incoherencia

## Que NO hace hoy

- NO EVIDENCIA de RL offline serio en produccion.
- NO EVIDENCIA de OPE robusto tipo IPS/DR/SWITCH en el path de promotion.
- NO EVIDENCIA de canary runtime automatizado por propuesta.
- NO EVIDENCIA de activacion live automatica.

## Shadow / mock dentro del cerebro

`shadow` no es paper ni testnet.

`shadow`:

- usa datos vivos
- no manda ordenes
- simula fills con el mismo motor de costos
- deja experiencia persistente

Esto es importante porque el cerebro necesita separar:

- "le hubiera ido bien en historico"
de
- "se mantiene consistente en flujo de mercado vivo sin ejecutar"

## Frontend asociado

La UI ya muestra:

- experiencia resumida
- propuestas Opcion B
- guidance por estrategia
- estado de shadow
- experiencia por fuente por bot

Y en backtests:

- selector de bot
- `Usar pool del bot`
- research batch / bestia

## Base bibliografica utilizada

Fuentes locales:

- `11 - Advances in Financial Machine Learning — Marcos Lopez de Prado (2018).pdf`
- `16 - Backtesting-and-its-Pitfalls.pdf`
- `17 - backtest-prob.pdf`
- `6 - Flow Toxicity and Liquidity in a High-Frequency World — Easley, Lopez de Prado y O'Hara (2012).pdf`
- `1 - Hasbrouck's book.pdf`
- `7 - New Concepts in Technical Trading Systems — J. Welles Wilder Jr. (1978).pdf`

Fuentes internas del repo:

- `README_CEREBRO_OPCION_B_ES.md`
- `CODEX_BACKTEST_LEARNING_TASK.md`

Fuente oficial web usada solo para la parte operativa de shadow:

- Binance Spot API Docs:
  - `https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints`

## Que decision de diseno respalda cada fuente

- AFML:
  - selector conservador, DSR/PSR, validacion antes de recomendar.
- Backtesting and its Pitfalls:
  - no confiar en una sola corrida y no mezclar dataset pobre con runtime.
- backtest-prob:
  - `PBO` como freno a promociones fragiles.
- Flow Toxicity:
  - usar `toxic` y `VPIN` como restriccion operativa.
- Hasbrouck:
  - desglosar costos de microestructura y penalizar estrategias que solo sobreviven con costos irreales.
- Wilder:
  - conservar indicadores clasicos como features legibles.
- README_CEREBRO_OPCION_B_ES.md / CODEX_BACKTEST_LEARNING_TASK.md:
  - Opcion B, aprobacion humana y no-live por defecto.

## Riesgos abiertos

- El cerebro actual depende de la calidad de los runs persistidos; si faltan datasets reales, la calidad cae.
- Shadow depende de market data publico y no reemplaza un runtime real de orden/fill.
- Algunas extracciones TXT locales estan vacias; cuando eso ocurre se usa otra fuente local valida u oficial.
