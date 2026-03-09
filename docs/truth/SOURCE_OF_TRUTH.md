# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-03-09

## Plan maestro consolidado - 2026-03-09

- Rama tecnica activa:
  - `feature/brain-policy-ledgers-v1`
- Estado git al iniciar el bloque:
  - `git status` limpio
  - continuidad directa contra `origin/main` (`0/2`)
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
7. Live Trading Layer
8. Governance / Model Risk Layer
9. Monitoring / Observability / Alerts / Drift / Kill Switches
10. Frontend de trazabilidad, control y salud operativa

### Estado real consolidado despues del bloque 2

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
  - universos reproducibles por run
  - live parity state cache
  - research funnel visible de punta a punta
  - monitoring / observability / drift / kill switches completos
  - frontend integral del cerebro, truth, execution reality y health

### Orden tecnico definitivo de bloques

1. Consolidar docs/truth y congelar roadmap maestro
2. Instrument registry + snapshots de catalogo + policies base
3. Adapters Binance Spot / Margin / USD?-M / COIN-M + sync manual/startup/programado
4. Market data / datasets / derivative state / live parity
5. Universos + dataset builder + linkage exacto de snapshots por run
6. Research funnel / Beast / trial ledger / PBO-DSR-PSR wiring
7. Strategy truth + evidence + legacy quarantine / stale handling
8. Bot brain + bot policy + decision log + OPE minima
9. Execution reality + live eligibility + preflight validation + routing
10. Monitoring / observability / alerts / drift / kill switches / health score
11. Frontend integral de catalogo, passport, brain, execution reality y monitoring
12. Tests, builds, limpieza conservadora y cierre documental

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

### Bibliografia base efectiva para este roadmap

- Base local prioritaria:
  - 32 PDF + 1 TXT fuera del repo, en directorios locales del usuario
- Uso permitido de web:
  - solo fuentes del mismo nivel academico/profesional y preferentemente de los mismos autores o documentacion oficial
- Regla aplicada:
  - si una decision tecnica critica no queda respaldada por bibliografia local, se busca soporte equivalente externo y se documenta.
