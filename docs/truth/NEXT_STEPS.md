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
- Bloque 7 parcial cerrado:
  - `LearningService` ya calcula elegibilidad live por bot usando:
    - `bot_policy_state`
    - `instrument_registry`
    - `live_parity_state`
    - estado/modo del bot
    - estado del runtime
  - endpoint nuevo:
    - `GET /api/v1/bots/{bot_id}/live-eligibility`
  - endpoint nuevo:
    - `POST /api/v1/execution/live/validate-order`
  - `Execution` ya muestra:
    - resumen de elegibilidad live del bot seleccionado
    - razones de bloqueo y warnings
    - estrategias del pool con pesos/confidence
    - tabla corta de instrumentos elegibles
    - resultado del preflight live
  - tests backend nuevos para:
    - elegibilidad live positiva
    - bloqueo live cuando `LIVE_TRADING_ENABLED=false`
- Bloque 9 parcial cerrado:
  - `ExperienceStore` ya infiere `bot_id` desde metadata y tags del run.
  - `run_bot_link` queda como fuente fuerte de atribucion historica.
  - `RegistryDB` rehidrata `bot_id` / `attribution_type` / `attribution_confidence` al listar:
    - episodios
    - evidencia por estrategia
  - `Bots` ya muestra taxonomia operativa visible.
  - `Execution` ya muestra taxonomia operativa visible.
- Bloque 9 parcial adicional cerrado:
  - `RegistryDB.backfill_bot_attribution_from_run_links()` consolida atribucion historica solo si el `run_id` tiene un unico bot.
  - `LearningService` ejecuta ese backfill antes de construir cerebro/evidence.
  - `Bots` ya muestra por fuente:
    - episodios
    - peso efectivo
    - trades
    - split exacto del bot vs contexto pool/global

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

## Hecho hasta ahora
- Bloque 8 backend/frontend minimo cerrado:
  - endpoints `monitoring/*`
  - pagina `Monitoring / Salud`
  - score compuesto de salud
  - feed de alertas
  - resumen de drift
  - eventos recientes de breaker/kill switch
  - degradacion fail-soft si drift rompe

## Nuevo plan consolidado
- 1. Policies YAML y source of truth
- 2. Ledgers/migraciones/strategy truth/evidence
- 3. Brain bot-first + attribution + live source
- 4. Research funnel / Beast / PBO-DSR-PSR
- 5. Execution reality / live eligibility / preflight
- 6. Monitoring / observability / alerts / drift / kill switches
- 7. Frontend integral por dominios:
  - dashboard
  - instrumentos
  - datasets
  - research
  - estrategias
  - bots
  - ejecucion
  - monitoring
  - configuracion
- 8. Tests / builds / cierre documental

## Bloques reordenados
- Bloque 7:
  - execution reality + live eligibility + preflight validation + routing
- Bloque 8:
  - monitoring / observability / drift / alertas / kill switches / health score
- Bloque 9:
  - frontend integral por dominios y taxonomia visible de modos
  - trazabilidad fuerte `run -> bot`
- Bloque 10:
  - tests finales, build completo, cierre documental

## Bloque actual
- Bloque 9 en progreso:
  - frontend serio por dominios
  - decision log visual y realidad de ejecucion mas explotable
  - consistencia visible Beast/Batch en deploy

## Pendiente del siguiente bloque
- consolidar paneles visibles del cerebro:
  - decision log
  - execution reality
  - resumen por fuente con `live` ya mas explotable
- reforzar `episode -> bot_id` directo para tablas/pantallas que aun dependan de episodios legacy sin backfill previo
- resolver mensajes/estado visible de Beast/Batch en deploy

## Bloqueado / no implementado
- Aun no implementado integralmente:
  - derivative state real poblado desde ingesta
  - live parity state cache completa
  - dataset/universe registry visible en frontend
  - taxonomia visible de modos `mock/paper/testnet/live` en todas las pantallas del frontend
  - frontend del cerebro completo
  - frontend del research funnel
  - Beast/Batch visible y consistente end-to-end en deploy
  - routing live final por family
  - `execution_reality` alimentado por fills/ordenes del runtime real
  - linkage `episode -> bot_id` historico directo para toda la data legacy

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
- El bloque 7 ahora ya valida elegibilidad/preflight, pero todavia no reemplaza un router live completo; no debe confundirse con ejecucion real end-to-end.
- Monitoring / Salud ya esta visible, pero no reemplaza aun una pila completa de observabilidad externa (Prometheus/Grafana/Otel).
- La trazabilidad `run -> bot` ya es fuerte si el run trae metadata/tags utiles; la analitica legacy por episodio sigue siendo parcialmente dependiente de esa relacion.
- El backfill de atribucion ahora es persistente pero deliberadamente conservador: no resuelve automaticamente casos donde un mismo `run_id` aparece ligado a mas de un bot.

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
- `rtlab_autotrader/rtlab_core/learning/service.py`
- `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/app/(app)/monitoring/page.tsx`
- `rtlab_dashboard/src/components/layout/app-shell.tsx`
- `rtlab_dashboard/src/lib/types.ts`
- `rtlab_autotrader/tests/test_web_live_ready.py`
- `rtlab_autotrader/tests/test_brain_policy_yaml.py`
- `rtlab_autotrader/tests/test_instrument_registry_store.py`
- `rtlab_autotrader/tests/test_binance_catalog_sync.py`
- `rtlab_autotrader/tests/test_dataset_registry.py`
- `rtlab_autotrader/tests/test_universe_registry.py`
- `rtlab_autotrader/tests/test_backtest_catalog_db.py`
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`
- `rtlab_autotrader/tests/test_research_funnel_api.py`
- `rtlab_autotrader/tests/test_brain_policy_service.py`
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
- `python -m py_compile rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/rtlab_core/web/app.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_service.py -q` -> PASS
- `npm run lint -- "src/app/(app)/strategies/page.tsx" "src/app/(app)/execution/page.tsx" "src/app/(app)/backtests/page.tsx" "src/lib/types.ts"` -> PASS
- `npm run lint -- "src/app/(app)/monitoring/page.tsx" "src/components/layout/app-shell.tsx" "src/lib/types.ts"` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "test_monitoring_health_endpoint_returns_scores or test_monitoring_kill_switches_endpoint_exposes_recent_breakers or test_monitoring_endpoints_degrade_cleanly_when_drift_fails" -q` -> PASS
- `npm run build` (`rtlab_dashboard`) -> PASS

## Build status
- Backend bloque 6 parcial: PASS
- Frontend bloque 6 parcial: PASS
- Backend bloque 8 minimo: PASS
- Frontend bloque 8 minimo: PASS
- `npm run build` verde; warnings de Recharts no bloqueantes


## Hecho en este bloque
- Frontend del cerebro visible y separado por dominio:
  - nueva pantalla `Bots`
  - `Execution` deriva acciones de bot a `Bots`
  - `Strategies/[id]` muestra `truth` y `evidence`
- Charts compartidos con ejes nombrados:
  - equity/drawdown
  - returns histogram
  - stacked cost chart
- Contratos tipados frontend agregados para:
  - bot brain
  - bot decision log
  - strategy truth/evidence
- Atribucion `run -> bot` reforzada en backend:
  - `ExperienceStore` infiere `bot_id` desde metadata y tags
  - `run_bot_link` se usa como fuente fuerte de atribucion
  - `RegistryDB` rehidrata atribucion al leer episodios/evidencia
- Taxonomia operativa visible agregada en frontend:
  - `Bots` muestra `Mock / Shadow`, `Paper`, `Testnet`, `Live`
  - `Execution` muestra `Modos operativos y alcance`
  - execution reality

## Bloque actual
- Bloque 9 cerrado parcialmente:
  - brain panel visible
  - decision log visible
  - truth/evidence visible
  - execution reality resumida visible

## Pendiente del siguiente bloque
- Fortalecer atribucion exacta `episode -> bot_id`
- Consolidar taxonomia visible de modos en todas las pantallas
- Research funnel visible en frontend
- Beast/Batch coherente y verificable en deploy

## Bloqueado / no implementado
- `execution_reality` aun no refleja fills reales end-to-end del runtime productivo
- `decision log` visual aun no tiene timeline avanzada ni filtros ricos
- `Strategies/[id]` muestra truth/evidence, pero no todo el passport cientifico completo

## Riesgos abiertos
- La pagina `Bots` depende de endpoints backend ya existentes; si el backend desplegado no esta actualizado, la UI puede verse parcial en preview.
- El warning de Recharts en prerender sigue siendo no bloqueante pero conviene resolverlo en otro bloque para limpiar CI.

## Decisiones asumidas
- Se mantiene la rama `feature/brain-policy-ledgers-v1` porque sigue siendo el mismo objetivo coherente.
- Se cierra este bloque con visibilidad minima real en frontend, sin redise?o gigante ni humo de capacidades no soportadas.
- La atribucion historica fuerte del cerebro usa primero `run_bot_link`; no se inventa `bot_id` de episodio si la evidencia no permite inferencia suficiente.

## Archivos tocados
- `rtlab_autotrader/rtlab_core/learning/experience_store.py`
- `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- `rtlab_autotrader/tests/test_learning_experience_option_b.py`
- `rtlab_dashboard/src/app/(app)/bots/page.tsx`
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `rtlab_dashboard/src/app/(app)/strategies/[id]/page.tsx`
- `rtlab_dashboard/src/components/charts/equity-drawdown-chart.tsx`
- `rtlab_dashboard/src/components/charts/returns-histogram.tsx`
- `rtlab_dashboard/src/components/charts/stacked-cost-chart.tsx`
- `rtlab_dashboard/src/components/layout/app-shell.tsx`
- `rtlab_dashboard/src/lib/types.ts`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
- `npm run lint -- "src/app/(app)/bots/page.tsx" "src/app/(app)/execution/page.tsx" "src/app/(app)/strategies/[id]/page.tsx" "src/components/charts/equity-drawdown-chart.tsx" "src/components/charts/returns-histogram.tsx" "src/components/charts/stacked-cost-chart.tsx" "src/components/layout/app-shell.tsx" "src/lib/types.ts"` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_service.py -q` -> PASS
- `npm run lint -- "src/app/(app)/bots/page.tsx" "src/app/(app)/execution/page.tsx"` -> PASS

## Build status
- `npm run build` en `rtlab_dashboard` -> PASS
