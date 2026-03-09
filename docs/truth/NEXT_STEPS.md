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

## Nuevo plan consolidado
- Unificar el proyecto sobre una arquitectura auditable y escalable:
  1. catalogo de instrumentos / Binance multi-family
  2. datasets historicos + live parity
  3. research funnel / Beast / trial ledger
  4. strategy truth + evidence fail-closed
  5. bot brain + bot policy + decision log
  6. execution reality + live validation + routing
  7. monitoring / observability / drift / alertas / kill switches
  8. frontend integral y trazable

## Bloques reordenados
1. Consolidacion docs/truth
2. Instrument registry + snapshots de catalogo + policies base
3. Adapters Binance Spot / Margin / USD?-M / COIN-M
4. Market data / datasets / derivative state / live parity
5. Universos + snapshot exacto por run
6. Research funnel / Beast / PBO-DSR-PSR
7. Strategy truth + evidence + quarantine / stale
8. Bot brain + bot policy + decision log + OPE minima
9. Execution reality + live eligibility + preflight validation + routing
10. Monitoring / observability / drift / kill switches / health score
11. Frontend integral de catalogo, passport, brain, execution reality y monitoring
12. Tests, builds, limpieza conservadora y cierre

## Bloque actual
- Bloque 1 cerrado:
  - policies base para catalogo/live parity/observabilidad
  - base persistente del instrument registry
  - snapshots versionados del catalogo

## Pendiente del siguiente bloque
- Bloque 2:
  - crear adapter Binance para Spot / Margin / USD?-M / COIN-M
  - sync manual / startup / programado
  - diffing de snapshots
  - poblar `instrument_registry` desde metadata real del exchange

## Bloqueado / no implementado
- Aun no implementado integralmente:
  - adapter Binance multi-market con sync real
  - universos versionados por run
  - live parity state cache
  - frontend del cerebro
  - monitoring / health dashboard
  - kill switches y drift visibles
  - Beast/Batch visible y consistente end-to-end en deploy

## Riesgos abiertos
- Hay capas legacy de catalogo/datasets simples que pueden superponerse con el nuevo instrument registry si no se consolidan con cuidado.
- Binance multi-family agrega complejidad de metadata, filtros y elegibilidad live; debe hacerse sin romper backtests existentes.
- `gates.yaml` ya concentra secciones nuevas de catalogo/live parity; si luego aparecen consumidores especializados, habra que decidir si conviene separar archivos sin romper `policy_paths.py`.

## Decisiones asumidas
- Se sigue en `feature/brain-policy-ledgers-v1` porque el objetivo es continuidad directa del mismo programa tecnico.
- No se abre rama nueva mientras la rama siga limpia y el objetivo no cambie.
- Toda evidencia vieja o incompleta sigue tratandose fail-closed.
- No se habilita live automatico aunque `live` ya entre como fuente valida del cerebro.
- Los nuevos umbrales deben vivir en YAML, no hardcodeados.
- La base del catalogo se deja en `RegistryDB` para evitar abrir otra SQLite paralela ahora.

## Archivos tocados
- `config/policies/gates.yaml`
- `rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py`
- `rtlab_autotrader/rtlab_core/instruments/__init__.py`
- `rtlab_autotrader/rtlab_core/instruments/registry.py`
- `rtlab_autotrader/tests/test_brain_policy_yaml.py`
- `rtlab_autotrader/tests/test_instrument_registry_store.py`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`

## Tests ejecutados
- `python -m py_compile rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/rtlab_core/instruments/registry.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_yaml.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_instrument_registry_store.py -q` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_brain_policy_service.py -q` -> PASS

## Build status
- No aplica build de frontend en este bloque backend/config.
