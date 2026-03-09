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
- Bloque 4 cerrado:
  - `universe_registry`, `universe_snapshot`, `universe_snapshot_item` y `run_universe_link` ya viven en la SQLite principal
  - `UniverseService` ya genera universos reproducibles por provider/family/symbols
  - `ConsoleStore.record_run(...)` ya persiste `run -> universe`
  - endpoints:
    - `GET /api/v1/universes`
    - `POST /api/v1/universes`
    - `GET /api/v1/universes/runs/{run_id}`
  - los simbolos ausentes en un snapshot quedan fail-closed con `snapshot_gap`
- Bloque 5 cerrado:
  - `BacktestCatalogDB` ya persiste `research_trial_ledger`
  - `MassBacktestEngine` ya registra un trial del funnel por cada sub-run del batch
  - endpoint nuevo:
    - `GET /api/v1/research/funnel`
  - el ledger guarda:
    - `promotion_stage`
    - `rejection_reason_json`
    - `dataset_hash`
    - `universe_json`
    - `PBO/DSR/PSR`
  - `delete_runs()` del catalogo limpia tambien trials asociados
  - fallback seguro de timeframe soportado evita que provenance legacy rompa `run_dataset_link` y `run_universe_link`

- Bloque 6 parcial cerrado:
  - `mock` queda como modo operativo visible del bot.
  - `shadow` queda interno como fuente de experiencia/compatibilidad.
  - `experience_store` ya normaliza aliases `mock -> shadow`.
  - `instrument_registry` y snapshots ya persisten `mock_enabled`.
  - la API ya expone `mode_capabilities` por instrumento.
  - frontend visible actualizado en:
    - `Strategies`
    - `Execution`
    - `Backtests`
  - `live` ya aparece como fuente de experiencia en resumenes donde corresponde.

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
5. Research funnel / Beast / PBO-DSR-PSR
6. Modos operativos + eligibility matrix (`backtest/mock/paper/testnet/demo/live`)
7. Execution reality + live eligibility + preflight validation + routing
8. Monitoring / observability / drift / kill switches / health score
9. Frontend integral por dominios
10. Tests, builds, limpieza conservadora y cierre

## Bloque actual
- Bloque 7 en progreso:
  - execution reality + live eligibility + preflight validation + routing
  - apoyar la taxonomia operativa ya consolidada sobre validacion/ruteo real

## Pendiente del siguiente bloque
- Bloque 8:
  - monitoring / observability / drift / alertas / kill switches / health score
  - surface minima en backend antes del frontend integral por dominios

## Bloqueado / no implementado
- Aun no implementado integralmente:
  - derivative state real poblado desde ingesta
  - live parity state cache completa
  - dataset/universe registry visible en frontend
  - taxonomia visible de modos `mock/paper/testnet/live` en todas las pantallas del frontend
  - frontend del cerebro
  - frontend del research funnel
  - monitoring / health dashboard
  - kill switches y drift visibles
  - Beast/Batch visible y consistente end-to-end en deploy

## Riesgos abiertos
- Hay capas legacy de catalogo/datasets simples que pueden superponerse con el nuevo instrument registry si no se consolidan con cuidado.
- Binance multi-family agrega complejidad de metadata, filtros y elegibilidad live; debe hacerse sin romper backtests existentes.
- Los universos ya quedan versionados, pero todavia no alimentan un funnel visual de research ni el frontend de datasets/universes.
- `gates.yaml` ya concentra secciones nuevas de catalogo/live parity; si luego aparecen consumidores especializados, habra que decidir si conviene separar archivos sin romper `policy_paths.py`.
- Margin en este bloque se deriva de metadata Spot publica; la validacion de capacidad real de cuenta queda para el bloque de live eligibility.
- La taxonomia operativa nueva no debe introducir UI enganosa: si algo no tiene backend real, no debe parecer soportado.
- El research funnel ya persiste trials, pero todavia no tiene explotacion visual en frontend ni integracion completa con promotion UI.
- El bloque actual debe evitar crear una segunda fuente de verdad de modos operativos fuera de YAML y store principal.
- Todavia quedan referencias tecnicas internas `shadow` que deben seguir internas y no filtrarse como UX primaria.

## Decisiones asumidas
- Se sigue en `feature/brain-policy-ledgers-v1` porque el objetivo es continuidad directa del mismo programa tecnico.
- No se abre rama nueva mientras la rama siga limpia y el objetivo no cambie.
- Toda evidencia vieja o incompleta sigue tratandose fail-closed.
- No se habilita live automatico aunque `live` ya entre como fuente valida del cerebro.
- Los nuevos umbrales deben vivir en YAML, no hardcodeados.
- La base del catalogo se deja en `RegistryDB` para evitar abrir otra SQLite paralela ahora.
- El dataset registry nuevo se montara sobre la misma SQLite principal y se alimentara desde `DataCatalog`/`DataProvider` para mantener compatibilidad.
- Los universos generados desde runs usan snapshot del catalogo vigente; si no existe snapshot de la family, se persisten igual pero con gaps fail-closed.
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
- `rtlab_autotrader/rtlab_core/backtest/catalog_db.py`
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
- `rtlab_autotrader/rtlab_core/universe/__init__.py`
- `rtlab_autotrader/rtlab_core/universe/service.py`
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/lib/types.ts`
- `rtlab_autotrader/tests/test_brain_policy_yaml.py`
- `rtlab_autotrader/tests/test_instrument_registry_store.py`
- `rtlab_autotrader/tests/test_binance_catalog_sync.py`
- `rtlab_autotrader/tests/test_dataset_registry.py`
- `rtlab_autotrader/tests/test_universe_registry.py`
- `rtlab_autotrader/tests/test_backtest_catalog_db.py`
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`
- `rtlab_autotrader/tests/test_research_funnel_api.py`
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
- `python -m py_compile rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/universe/service.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_universe_registry.py -q` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/backtest/catalog_db.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/web/app.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_backtest_catalog_db.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_research_funnel_api.py -q` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/brokers/binance/catalog.py rtlab_autotrader/rtlab_core/instruments/registry.py rtlab_autotrader/rtlab_core/universe/service.py rtlab_autotrader/rtlab_core/web/app.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_instrument_registry_store.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_binance_catalog_sync.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS
- `npm run lint -- "src/app/(app)/strategies/page.tsx" "src/app/(app)/execution/page.tsx" "src/app/(app)/backtests/page.tsx" "src/lib/types.ts"` -> PASS
- `npm run build` (`rtlab_dashboard`) -> PASS

## Build status
- Backend bloque 6 parcial: PASS
- Frontend bloque 6 parcial: PASS
- `npm run build` verde; warnings de Recharts no bloqueantes
