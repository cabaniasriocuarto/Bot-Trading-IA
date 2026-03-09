# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-03-09

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

### Bloque actual en progreso

- Bloque 6:
  - taxonomia operativa y eligibility matrix por modo
  - visibilidad minima de modos en backend/API
  - preparar el puente hacia execution reality y frontend por dominios

### Bibliografia base efectiva para este roadmap

- Base local prioritaria:
  - 32 PDF + 1 TXT fuera del repo, en directorios locales del usuario
- Uso permitido de web:
  - solo fuentes del mismo nivel academico/profesional y preferentemente de los mismos autores o documentacion oficial
- Regla aplicada:
  - si una decision tecnica critica no queda respaldada por bibliografia local, se busca soporte equivalente externo y se documenta.
