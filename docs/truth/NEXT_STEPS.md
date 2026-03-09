# NEXT STEPS (Plan vivo del proyecto)

Fecha: 2026-03-09

## Hecho hasta ahora
- Fuente de verdad de configuracion confirmada:
  - `config/policies/*.yaml`
- Cerebro backend ya cableado con:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
  - `run_bot_link`
  - `execution_reality`
- `live` ya es fuente real de evidencia en:
  - schema
  - store
  - engine
  - service
  - endpoints
- Blend bot-first con prior global ya operativo en backend.
- Endpoints del cerebro ya expuestos:
  - `GET /api/v1/bots/{bot_id}/brain`
  - `POST /api/v1/bots/{bot_id}/recompute-brain`
  - `GET /api/v1/bots/{bot_id}/decision-log`
  - `GET /api/v1/strategies/{strategy_id}/truth`
  - `GET /api/v1/strategies/{strategy_id}/evidence`
  - `GET /api/v1/execution/reality`
- Bloque 1 cerrado:
  - nuevas policies base para catalogo / market data / live parity / observabilidad
  - tablas base de catalogo de instrumentos y snapshots
  - wrapper `InstrumentCatalogStore`
- Bloque 2 cerrado:
  - adapter Binance multi-family
  - sync manual / startup / scheduler
  - snapshotting y diffing por market family
  - endpoints `/api/v1/instruments*`
- Bloque 3 cerrado:
  - `DataCatalog` sincroniza manifests al `dataset_registry`
  - `DatasetModeDataProvider` registra manifests estandarizados al resolver datasets legacy
  - `ConsoleStore.record_run(...)` persiste `run_dataset_link`
  - `live_parity_state` queda disponible y se refresca junto al sync de instrumentos
  - endpoints:
    - `GET /api/v1/datasets`
    - `GET /api/v1/datasets/{run_id}/links`
    - `GET /api/v1/live-parity`

## Nuevo plan consolidado
- Unificar el proyecto sobre una arquitectura auditable y escalable:
  1. catalogo de instrumentos / Binance multi-family
  2. datasets historicos + live parity
  3. research funnel / Beast / trial ledger
  4. strategy truth + evidence fail-closed
  5. bot brain + bot policy + decision log
  6. taxonomia de modos operativos y matriz de elegibilidad por modo
  7. execution reality + live validation + routing
  8. monitoring / observability / drift / alertas / kill switches
  9. frontend integral, serio y trazable por dominios

## Bloques reordenados
1. Consolidacion docs/truth
2. Instrument registry + snapshots de catalogo + policies base
3. Adapters Binance Spot / Margin / USD?-M / COIN-M
4. Market data / datasets / derivative state / live parity
5. Universos + snapshot exacto por run
6. Research funnel / Beast / PBO-DSR-PSR
7. Strategy truth + evidence + quarantine / stale
8. Bot brain + bot policy + decision log + OPE minima
 9. Modos operativos + eligibility matrix (`backtest/mock/paper/testnet/demo/live`)
 10. Execution reality + live eligibility + preflight validation + routing
 11. Monitoring / observability / drift / kill switches / health score
 12. Frontend integral por dominios
 13. Tests, builds, limpieza conservadora y cierre

## Bloque actual
- Bloque 4 en progreso:
  - universos reproducibles por provider/family/filtros
  - snapshot exacto de instrumentos por run
  - enlace fuerte run -> dataset -> universe/instruments
  - base para taxonomia de modos sin hardcodes dispersos

## Pendiente del siguiente bloque
- Bloque 5:
  - research funnel / Beast con universe snapshot y rechazo explicable
  - wiring PBO / DSR / PSR sobre trial ledger
  - preparar entrada de modos operativos al producto visible

## Bloqueado / no implementado
- Aun no implementado integralmente:
  - universos versionados por run
  - derivative state real poblado desde ingesta
  - live parity state cache completa
  - dataset registry visible en frontend
  - taxonomia visible de modos `mock/paper/testnet/live` en frontend
  - frontend del cerebro
  - monitoring / health dashboard
  - kill switches y drift visibles
  - Beast/Batch visible y consistente end-to-end en deploy

## Riesgos abiertos
- Hay capas legacy de catalogo/datasets simples que pueden superponerse con el nuevo instrument registry si no se consolidan con cuidado.
- Binance multi-family agrega complejidad de metadata, filtros y elegibilidad live; debe hacerse sin romper backtests existentes.
- `gates.yaml` ya concentra secciones nuevas de catalogo/live parity; si luego aparecen consumidores especializados, habra que decidir si conviene separar archivos sin romper `policy_paths.py`.
- Margin en este bloque se deriva de metadata Spot publica; la validacion de capacidad real de cuenta queda para el bloque de live eligibility.
- La taxonomia operativa nueva no debe introducir UI engañosa: si algo no tiene backend real, no debe parecer soportado.
- El bloque actual debe evitar crear una segunda fuente de verdad de datasets distinta a `user_data/data/**/manifests` mientras se migra a storage trazable.

## Decisiones asumidas
- Se sigue en `feature/brain-policy-ledgers-v1` porque el objetivo es continuidad directa del mismo programa tecnico.
- No se abre rama nueva mientras la rama siga limpia y el objetivo no cambie.
- Toda evidencia vieja o incompleta sigue tratandose fail-closed.
- No se habilita live automatico aunque `live` ya entre como fuente valida del cerebro.
- Los nuevos umbrales deben vivir en YAML, no hardcodeados.
- La base del catalogo se deja en `RegistryDB` para evitar abrir otra SQLite paralela ahora.
- El dataset registry nuevo se montara sobre la misma SQLite principal y se alimentara desde `DataCatalog`/`DataProvider` para mantener compatibilidad.
- La taxonomia canonica de modos queda fijada como:
  - `backtest`
  - `mock`
  - `paper`
  - `testnet`
  - `demo`
  - `live`
- `mock` queda separado de `testnet`, y `paper` separado de ambos.

## Archivos tocados
- `config/policies/gates.yaml`
- `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- `rtlab_autotrader/rtlab_core/instruments/__init__.py`
- `rtlab_autotrader/rtlab_core/instruments/registry.py`
- `rtlab_autotrader/rtlab_core/brokers/__init__.py`
- `rtlab_autotrader/rtlab_core/brokers/binance/__init__.py`
- `rtlab_autotrader/rtlab_core/brokers/binance/catalog.py`
- `rtlab_autotrader/rtlab_core/src/data/catalog.py`
- `rtlab_autotrader/rtlab_core/src/research/data_provider.py`
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/tests/test_brain_policy_yaml.py`
- `rtlab_autotrader/tests/test_instrument_registry_store.py`
- `rtlab_autotrader/tests/test_binance_catalog_sync.py`
- `rtlab_autotrader/tests/test_dataset_registry.py`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
- `python -m py_compile rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/instruments/registry.py` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/brokers/binance/catalog.py rtlab_autotrader/rtlab_core/web/app.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_yaml.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_instrument_registry_store.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_binance_catalog_sync.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_service.py -q` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/src/data/catalog.py rtlab_autotrader/rtlab_core/src/research/data_provider.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_dataset_registry.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_dataset_registry.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS

## Build status
- No aplica build de frontend en este bloque backend/config.
