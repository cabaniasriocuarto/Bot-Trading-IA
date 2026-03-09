# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-03-09

## Actualizacion de bloque 9 parcial - experiencia atribuida al bot visible

- El backend ya expone `GET /api/v1/bots/{bot_id}/experience`.
- Ese contrato devuelve experiencia atribuida al bot sobre `experience_episode` con backfill previo desde `run_bot_link`.
- La salida ya diferencia:
  - episodios elegibles
  - episodios excluidos
  - episodios `legacy_untrusted`
  - episodios `stale`
  - atribucion `exact` / `strong` / `approx` / `unknown`
  - fuentes por bot (`live`, `shadow`, `paper`, `testnet`, `backtest`)
  - top estrategias por evidencia atribuida
- Frontend `Bots` ya consume ese contrato y muestra una tarjeta dedicada para:
  - ver si el cerebro del bot se apoya en evidencia exacta o solo contextual
  - distinguir experiencia util de experiencia excluida
  - inspeccionar cuales estrategias dominan la evidencia del bot
  - inspeccionar episodios individuales con `run_id`, fuente, `dataset_source`, `dataset_hash`, atribucion, `attribution_confidence`, peso efectivo y flags operativas
- Estado real:
  - `run -> bot` ya queda visible de forma operativa en UI
  - la trazabilidad `episode -> bot` ya es visible a nivel de episodio reciente desde la pantalla `Bots`
  - sigue faltando trazabilidad exacta nativa para todos los historicos viejos que nunca tuvieron `bot_id` ni `run_bot_link`

## Actualizacion de bloque 9 parcial - resumenes explotables de decision log + execution reality

- `LearningService.get_bot_decision_log_payload(...)` ahora devuelve un `summary` agregado con:
  - cantidad total de decisiones
  - decisiones con seleccion efectiva
  - `hold/skip`
  - candidatas totales
  - rechazadas totales
  - ultima decision
  - breakdown por regimen
  - breakdown por estrategia seleccionada
- `LearningService.get_execution_reality_payload(...)` ahora devuelve un `summary` agregado con:
  - cantidad total de ejecuciones
  - slippage medio
  - latencia media
  - spread medio
  - impacto medio estimado
  - partial fill medio
  - maker ratio / taker ratio
  - cantidad de simbolos activos
  - ultima ejecucion
  - breakdown por estado de reconciliacion
- Frontend `Bots` ya explota esos contratos sin inventar datos:
  - tarjeta de resumen del `decision log`
  - desglose por regimen y por estrategia elegida
  - tarjeta de `execution reality` con maker/taker, impacto, partial fills y reconciliacion
- Estado real:
  - el cerebro ya es mas visible y auditable desde `Bots`
  - sigue faltando timeline avanzada y filtros ricos del `decision log`
  - sigue faltando un `reality panel` mas profundo en `Execution`

## Actualizacion de bloque 9 parcial - backfill conservador de atribucion + resumen por fuente enriquecido

- `RegistryDB.backfill_bot_attribution_from_run_links()` ya consolida atribucion historica desde `run_bot_link` cuando existe una unica relacion `run_id -> bot_id`.
- El backfill:
  - completa `experience_episode.bot_id` si estaba vacio
  - completa `experience_episode.attribution_type` / `attribution_confidence` si estaban en `unknown` o `0`
  - completa `strategy_evidence.bot_id` si estaba vacio
  - no sobreescribe filas ya atribuidas ni inventa joins ambiguos
- `LearningService` ejecuta este backfill antes de construir:
  - `bot brain`
  - `strategy evidence payload`
- El resumen por fuente del cerebro ahora expone por fuente:
  - `count`
  - `weight_sum`
  - `trades`
  - `exact_bot_count`
  - `pool_context_count`
  - `exact_bot_trades`
  - `pool_context_trades`
- Frontend `Bots` ya muestra ese detalle por fuente, por lo que `live` deja de verse solo como badge abstracto y pasa a verse con trades y scope de atribucion.
- Regla vigente:
  - si un `run_id` aparece asociado a mas de un bot, no se hace backfill automatico
  - la atribucion queda fail-closed hasta aclarar la relacion
## Actualizacion de bloque 9 parcial - Atribucion `run -> bot` reforzada + taxonomia visible de modos

- `ExperienceStore.record_run(...)` ya no depende solo de un `bot_id` explicito para atribuir experiencia a un bot.
- La inferencia fuerte actual de `bot_id` se resuelve en este orden:
  - argumento explicito `bot_id`
  - `run.bot_id`
  - metadata embebida en:
    - `summary`
    - `meta`
    - `provenance`
    - `params`
    - `params_json`
  - tags con prefijos:
    - `bot:<id>`
    - `bot_id:<id>`
- Tipos de atribucion efectivos vigentes:
  - `exact` con confianza `1.0`
  - `strong` con confianza `0.75`
  - `unknown` con confianza `0.0`
- La trazabilidad fuerte hoy queda persistida en:
  - `run_bot_link`
  - `experience_episode.bot_id` cuando la atribucion se puede resolver al grabar
- `RegistryDB` ahora rehidrata atribucion de bot al leer:
  - `list_experience_episodes(...)`
  - `list_strategy_evidence(...)`
  usando `run_bot_link` cuando la fila historica no trae `bot_id` directo.
- Estado real:
  - `run -> bot` queda bastante mas fuerte y util para cerebro, evidencia y UI.
  - `episode -> bot` sigue sin backfill historico total en todas las filas legacy; la fuente mas fuerte sigue siendo `run_bot_link`.
- Frontend visible alineado:
  - `Bots` ahora muestra una tarjeta explicita `Taxonomia de modos` con diferencias entre:
    - `Mock / Shadow`
    - `Paper`
    - `Testnet`
    - `Live`
  - `Execution` ahora muestra una tarjeta explicita `Modos operativos y alcance` con el mismo criterio de producto.
- Regla de UX vigente:
  - `mock` se presenta como simulacion propia del sistema.
  - `paper` se presenta como mercado real con fills simulados.
  - `testnet` se presenta como entorno oficial del exchange.
  - `live` se presenta como operacion real con controles reforzados.

## Actualizacion de bloque 7 parcial - Elegibilidad live por bot + preflight visible en Ejecucion

- `LearningService` ahora expone una capa operativa minima para `live` sobre el cerebro del bot:
  - `get_bot_live_eligibility_payload(...)`
  - `validate_execution_preflight(...)`
- La elegibilidad live ya no depende solo de labels o del modo visible del bot. Ahora combina:
  - `bot_policy_state` persistido
  - `instrument_registry`
  - `live_parity_state`
  - modo del bot
  - estado del bot
  - runtime mode
  - `LIVE_TRADING_ENABLED`
- La validacion usa checks explicitos y auditables:
  - bot encontrado
  - pool no vacio
  - bot no archivado
  - modo del bot compatible
  - instrumento resuelto
  - instrumento tradable
  - instrumento habilitado para el modo
  - runtime live habilitado
  - referencia de mercado disponible
  - estado de mercado reciente
  - `mark_price` reciente si el market es derivado
  - cantidad valida
  - lado declarado
- `web/app.py` ya publica endpoints reales para esta capa:
  - `GET /api/v1/bots/{bot_id}/live-eligibility`
  - `POST /api/v1/execution/live/validate-order`
- Frontend `Execution` ya muestra:
  - resumen de elegibilidad live del bot seleccionado
  - estrategias del pool con score/weights/confidence
  - instrumentos live elegibles
  - motivos de bloqueo
  - warnings
  - resultado del preflight live
- Estado real del bloque:
  - la visibilidad minima backend/frontend ya existe
  - todavia no hay routing live final ni `execution_reality` conectado a fills reales
  - la trazabilidad `episode -> bot_id` directa sigue pendiente; la trazabilidad fuerte hoy es `run -> bot`

## Actualizacion de bloque 6 parcial - Modos operativos y capacidades por instrumento

- Taxonomia operativa canonica vigente:
  - `backtest`
  - `mock`
  - `paper`
  - `testnet`
  - `demo`
  - `live`
- Regla canonica de implementacion:
  - `mock` es el modo operativo visible del bot en UI y store.
  - `shadow` se mantiene como fuente interna/canonica de experiencia y como compatibilidad de endpoints legacy.
  - `mock` no reemplaza `paper`.
  - `mock` no reemplaza `testnet`.
- `config/policies/gates.yaml` ya expone `execution_modes.mock` y conserva `paper/testnet/live`.
- `experience_store.py` normaliza aliases operativos:
  - `mock -> shadow`
  - `test -> testnet`
- `instrument_registry` y `instrument_catalog_snapshot_item` ya persisten `mock_enabled`.
- La API de instrumentos ya devuelve `mode_capabilities` por instrumento/snapshot con:
  - `allowed_in_backtest`
  - `allowed_in_mock`
  - `allowed_in_paper`
  - `allowed_in_testnet`
  - `allowed_in_demo`
  - `allowed_in_live`
- `web/app.py` ya normaliza `shadow -> mock` para modos de bot visibles, sin romper la fuente de experiencia `shadow`.
- Frontend visible ya alineado en:
  - `Strategies`
  - `Execution`
  - `Backtests`
  mostrando `mock` como modo operativo y `live` como fuente de experiencia cuando existe.
- Pendiente real luego de este bloque:
  - consolidar la taxonomia de modos en el resto del frontend
  - conectar `execution_reality` con preflight/live eligibility/routing real
  - evitar que referencias internas `shadow` se filtren a la UX primaria fuera de contextos tecnicos
## Plan maestro consolidado - 2026-03-09

- Rama tecnica activa:
  - `feature/brain-policy-ledgers-v1`
- Estado git al iniciar el bloque:
  - cambios locales acotados a:
    - `registry_db.py`
    - `app.py`
    - `rtlab_core/universe/*`
  - continuidad directa contra `origin/main` (`0/5`)
- Decision de rama:
  - se mantiene la rama actual porque este trabajo sigue el mismo objetivo coherente:
    - cerebro del programa
    - strategy truth
    - bot policy
    - execution reality
    - catalogo de instrumentos / Binance
    - datasets / live parity
    - observabilidad
    - frontend de trazabilidad

### Fuente de verdad vigente

- Configuracion operativa:
  - `config/policies/*.yaml`
- Verdad tecnica viva:
  - `docs/truth/SOURCE_OF_TRUTH.md`
  - `docs/truth/CHANGELOG.md`
  - `docs/truth/NEXT_STEPS.md`
- Persistencia principal:
  - SQLite via `registry_db.py` y stores asociados
- Politica de evidencia:
  - fail-closed para legacy/stale/incompleto
  - no mezclar evidencia vieja o ruidosa en calculos principales

### Capas objetivo del sistema

1. Instrument Registry + Provider Adapters
2. Market Data / Historical Snapshots / Live Parity
3. Research Funnel / Beast Mode / Trial Ledger
4. Strategy Truth Layer
5. Bot Brain / Bot Policy Layer
6. Execution Reality Layer
7. Modos Operativos / Eligibility Matrix
8. Live Trading Layer
9. Governance / Model Risk Layer
10. Monitoring / Observability / Alerts / Drift / Kill Switches
11. Frontend de trazabilidad, control y salud operativa por dominios

### Taxonomia operativa canonica

- `backtest`:
  - simulacion historica reproducible
  - datasets versionados
  - fills simulados
  - sin APIs reales de trading
- `mock`:
  - simulacion propia del sistema
  - puede usar market data real-time o replay
  - exchange/cuenta/fills/errores simulados por RTLAB
  - independiente de testnet
- `paper`:
  - market data real-time
  - decisiones reales del bot
  - capital ficticio
  - fills simulados con execution model interno
- `testnet`:
  - entorno oficial de prueba del exchange
  - credenciales y fondos virtuales de prueba
  - valida auth, payloads, filtros y errores reales de API
- `demo`:
  - reservado para brokers que expongan sandbox/demo propio distinto de testnet
- `live`:
  - cuenta y endpoints reales
  - requiere elegibilidad fuerte, preflight, monitoreo y kill switches

Regla de verdad:
- `mock` != `testnet`
- `paper` != `mock`
- `live` nunca se habilita por defecto

### Estado real consolidado despues del bloque 3

- Ya implementado y usable en backend:
  - `live` como fuente real de evidencia
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
  - `run_bot_link`
  - `execution_reality`
  - servicio bot-first con prior global
  - endpoints del cerebro del bot
  - tablas base de catalogo de instrumentos:
    - `instrument_registry`
    - `instrument_catalog_snapshot`
    - `instrument_catalog_snapshot_item`
  - wrapper de catalogo:
    - `rtlab_core.instruments.registry.InstrumentCatalogStore`
  - adapter Binance multi-family:
    - `rtlab_core.brokers.binance.BinanceCatalogSyncService`
  - sync de catalogo Binance:
    - manual via API
    - on startup
    - programado por scheduler configurable
  - snapshotting y diffing de catalogo para:
    - `spot`
    - `margin`
    - `usdm_futures`
    - `coinm_futures`
  - endpoints de catalogo:
    - `GET /api/v1/instruments`
    - `GET /api/v1/instruments/{instrument_id}`
    - `POST /api/v1/instruments/sync`
  - dataset registry persistente y compatible con el stack actual:
    - `dataset_registry`
    - `run_dataset_link`
  - `DataCatalog` y `DatasetModeDataProvider` ya sincronizan manifests a SQLite sin romper research legacy
  - `ConsoleStore.record_run(...)` ya persiste linkage `run -> dataset`
  - live parity minima persistida:
    - `live_parity_state`
    - estados honestos `reference_only / reference_dataset_ready / live_blocked / not_tradable / missing_*`
  - endpoints nuevos de datos:
    - `GET /api/v1/datasets`
    - `GET /api/v1/datasets/{run_id}/links`
    - `GET /api/v1/live-parity`
- Ya centralizado en YAML:
  - `gates`
  - `microstructure`
  - `risk_policy`
  - `beast_mode`
  - `fees`
  - `fundamentals_credit_filter`
  - y nuevas secciones en `gates.yaml` para:
    - `market_catalog`
    - `market_data`
    - `execution_modes`
    - `execution_symbol_validation`
    - `universe_policy`
    - `observability`
- Aun no implementado de forma integral:
  - frontend de universos reproducibles por run
  - derivative state real poblado desde ingesta de mercado
  - live parity state cache completa con websocket/REST freshness por family
  - research funnel visible de punta a punta en frontend
  - monitoring / observability / drift / kill switches completos
  - frontend integral del cerebro, truth, execution reality y health
  - frontend reorganizado por dominios claros:
    - instrumentos
    - datasets
    - research
    - estrategias
    - bots
    - ejecucion
    - monitoring
    - configuracion

### Orden tecnico definitivo de bloques

1. Consolidar docs/truth y congelar roadmap maestro
2. Instrument registry + snapshots de catalogo + policies base
3. Adapters Binance Spot / Margin / USD?-M / COIN-M + sync manual/startup/programado
4. Market data / datasets / derivative state / live parity
5. Universos + dataset builder + linkage exacto de snapshots por run
6. Research funnel / Beast / trial ledger / PBO-DSR-PSR wiring
7. Strategy truth + evidence + legacy quarantine / stale handling
8. Bot brain + bot policy + decision log + OPE minima
9. Normalizacion de modos operativos + eligibility matrix por modo
10. Execution reality + live eligibility + preflight validation + routing
11. Monitoring / observability / alerts / drift / kill switches / health score
12. Frontend integral por dominios: dashboard, instrumentos, datasets, research, estrategias, bots, ejecucion, monitoring, configuracion
13. Tests, builds, limpieza conservadora y cierre documental

### Bloques cerrados

- Bloque 0:
  - fusion de prompts y roadmap consolidado
  - decision de rama
  - fuente de verdad confirmada
  - docs/truth reordenadas
- Bloque 1:
  - normalizacion inicial de policies para catalogo/live parity/observabilidad
  - schema base del instrument registry y snapshots versionados
  - wrapper fino de catalogo sobre `RegistryDB`
  - tests de sanidad YAML y persistencia del catalogo
- Bloque 2:
  - adapter Binance multi-family con normalizacion de metadata para:
    - Spot
    - Margin derivado de `exchangeInfo`
    - USD?-M Futures
    - COIN-M Futures
  - sync inicial opcional al startup
  - scheduler de resync configurable
  - endpoint admin de sync manual
  - snapshotting y diffing del catalogo por market family
  - tests del adapter y persistencia de snapshots reales
- Bloque 3:
  - `DataCatalog` ya sincroniza manifests al `dataset_registry`
  - `DatasetModeDataProvider` ya registra datasets estandarizados al resolver manifests legacy
  - `ConsoleStore.record_run(...)` ya persiste `run_dataset_link`
  - `live_parity_state` queda disponible con actualizacion en sync de instrumentos
  - endpoints de datasets y live parity ya expuestos
  - tests locales en verde para dataset registry y compatibilidad con mass backtest
- Bloque 4:
  - `universe_registry`, `universe_snapshot`, `universe_snapshot_item` y `run_universe_link` quedan persistidos en la SQLite principal
  - `UniverseService` genera universos reproducibles con snapshot exacto de instrumentos por family/provider
  - `ConsoleStore.record_run(...)` ya persiste `run -> universe` junto al `run -> dataset`
  - endpoints nuevos:
    - `GET /api/v1/universes`
    - `POST /api/v1/universes`
    - `GET /api/v1/universes/runs/{run_id}`
  - si falta un simbolo en el snapshot, queda fail-closed con `snapshot_gap=instrument_missing_from_catalog` en vez de inventar metadata
- Bloque 5:
  - `BacktestCatalogDB` persiste `research_trial_ledger` como ledger reproducible del research funnel
  - cada sub-run de `MassBacktestEngine` escribe trial con:
    - `promotion_stage`
    - `rejection_reason_json`
    - `PBO/DSR/PSR`
    - `dataset_hash`
    - `universe_json`
  - endpoint nuevo:
    - `GET /api/v1/research/funnel`
  - el borrado de runs del catalogo limpia tambien el ledger del funnel
  - fallback seguro de timeframe soportado en enlaces de dataset/universe evita romper provenance legacy durante tests y API
- Bloque 8:
  - dominio `Monitoring / Salud` ya existe como capa visible separada en frontend
  - endpoints nuevos:
    - `GET /api/v1/monitoring/health`
    - `GET /api/v1/monitoring/alerts`
    - `GET /api/v1/monitoring/metrics-summary`
    - `GET /api/v1/monitoring/drift`
    - `GET /api/v1/monitoring/kill-switches`
  - `monitoring/health` expone `health score` compuesto y sub-scores:
    - data
    - research
    - brain
    - execution
    - risk
    - observability
  - `monitoring/kill-switches` expone integridad de `breaker_events` y eventos recientes por bot/modo/razon
  - `monitoring/drift` queda fail-soft:
    - si el calculo de drift falla, la API devuelve `status=DEGRADED` sin romper la pantalla
  - la navegacion ya separa `Monitoring / Salud` del resto de dominios operativos

### Bloque actual en progreso

- Bloque 9:
  - frontend integral por dominios:
    - brain del bot
    - strategy truth / passport
    - execution reality
    - health dashboard completo
  - consolidar taxonomia visible de modos:
    - mock
    - paper
    - testnet
    - demo
    - live

### Estado vigente tras frontend serio del cerebro (2026-03-09)

- El dominio `Bots` ya es pantalla propia del producto y deja de vivir mezclado en `Ejecucion`.
- `Ejecucion` queda orientada a operativa/runtime/preflight.
- `Bots` queda orientada a:
  - brain/policy del bot
  - decision log
  - elegibilidad live
  - execution reality agregada por bot
- `Strategies/[id]` ya muestra la capa `strategy truth` y `strategy evidence` del cerebro backend.
- Los charts compartidos del frontend ahora exponen nombres de ejes y unidades visibles en los componentes principales de comparacion/backtest.
- No existe aun frontend completo para:
  - funnel visual de research
  - datasets/universes
  - decision timeline avanzada
  - panel exhaustivo de execution reality con trazas/fills reales
  - taxonomia completa de modos en todas las pantallas

### Bibliografia base efectiva para este roadmap

- Base local prioritaria:
  - 32 PDF + 1 TXT fuera del repo, en directorios locales del usuario
- Uso permitido de web:
  - solo fuentes del mismo nivel academico/profesional y preferentemente de los mismos autores o documentacion oficial
- Regla aplicada:
  - si una decision tecnica critica no queda respaldada por bibliografia local, se busca soporte equivalente externo y se documenta.

