# NEXT STEPS (Prioridades Reales)

Fecha: 2026-03-20

## RTLOPS-45 - User Data Stream lifecycle live - 2026-03-20
- [x] Extender `binance_live_runtime.yaml` con bloques `user_stream` explicitos por conector/familia.
- [x] Implementar runtime privado dedicado en:
  - `rtlab_autotrader/rtlab_core/execution/live_user_stream_runtime.py`
- [x] Cablear Spot por `websocket_api_spot` con:
  - `userDataStream.subscribe.signature`
  - parsing de `executionReport`
  - parsing de eventos de cuenta
  - manejo de `eventStreamTerminated`
- [x] Cablear `binance_um_futures` por `futures_listenkey` con:
  - `POST /fapi/v1/listenKey`
  - `PUT /fapi/v1/listenKey`
  - `DELETE /fapi/v1/listenKey`
  - parsing de `ORDER_TRADE_UPDATE`
  - parsing de eventos de cuenta relevantes
- [x] Persistir eventos privados en:
  - `execution_user_stream_events`
- [x] Integrar el runtime con:
  - `bootstrap_summary()`
  - `live_safety_summary()`
  - endpoints `/api/v1/execution/user-streams/*`
  - `GET /api/v1/config/policies`
- [x] Endurecer request security del path Spot WebSocket API:
  - firma HMAC con params ordenados alfabeticamente
  - `recvWindow = 5000`
  - sync de hora reutilizado
- [x] Dejar explicita la limitacion transicional:
  - `legacy_listenkey` para Spot no queda fingido como soporte productivo
  - en `live` se refleja como `unsupported_mode + degraded_mode + block_live`
- [x] Revalidar:
  - `test_execution_reality.py`
  - `test_web_execution_reality_api.py`
  - `test_policy_paths.py`
  - `test_web_live_ready.py -k config_policies_endpoint_exposes_numeric_policy_bundle`
- [ ] Limites conscientes fuera de RTLOPS-45:
  - `coinm_futures` no queda operativo en este bloque
  - `RTLOPS-55` sigue abierto para el sweep completo de split canonico backend/frontend/storage y provenance
  - la compatibilidad `order_test` por familia sigue como follow-up aparte en `RTLOPS-56` y no se reabre aqui
  - la compatibilidad de ordenes condicionales `usdm_futures` (`reduceOnly`, `closePosition`, hedge-mode y familia STOP/TAKE_PROFIT) queda trazada en `RTLOPS-57`

## RTLOPS-44 - Market WebSocket Runtime live - 2026-03-20
- [x] Crear policy canonica nueva:
  - `config/policies/binance_live_runtime.yaml`
  - copia nested solo como compatibilidad
- [x] Implementar runtime WS publico por conector/familia:
  - `binance_spot`
  - `binance_um_futures`
- [x] Cablear streams minimos:
  - Spot:
    - `bookTicker`
    - `aggTrade`
  - USDⓈ-M:
    - `bookTicker`
    - `aggTrade`
    - `markPrice@1s`
- [x] Soportar:
  - reconnect con backoff + jitter
  - resuscripcion en modo `raw`
  - stale watchdog
  - recycle 24h-aware
  - resumen operativo auditable
- [x] Integrar el runtime con:
  - `bootstrap_summary()`
  - `live_safety_summary()`
  - `GET /api/v1/config/policies`
  - endpoints `/api/v1/execution/market-streams/*`
- [x] Exponer visibilidad minima en frontend sobre el runtime WS.
- [x] Revalidar:
  - `test_execution_reality.py`
  - `test_web_execution_reality_api.py`
  - `test_policy_paths.py`
  - `test_web_live_ready.py -k config_policies_endpoint_exposes_numeric_policy_bundle`
  - `npx.cmd tsc --noEmit`
  - smoke publico Spot + USDⓈ-M live
- [ ] Limites conscientes fuera de RTLOPS-44:
  - el private user/account/order stream queda para `RTLOPS-45`
  - `RTLOPS-55` sigue abierto para terminar el sweep completo de split canonico backend/frontend/storage sin heuristica ambigua
  - la URL/test contract de testnet USDⓈ-M sigue tratada como detalle operativo configurable, no como verdad universal congelada

## Contexto anterior de transicion (ya resuelto)
- Desde RTLOPS-44, el siguiente issue fue `RTLOPS-45` y ya quedo cerrado.
- alcance historico que ya quedo cubierto:
  - Spot private stream auditando camino legacy/transicional actual y evaluando migracion a WebSocket API donde corresponda
  - USDⓈ-M private stream con lifecycle de listenKey / keepalive y parsing robusto de ordenes/cuenta
  - persistencia de eventos privados sin fingir equivalencia entre Spot y Futures
  - integracion con `ExecutionRealityService`, `reconcile`, `fills` y `live_safety`

## Siguiente issue exacto
- `RTLOPS-46` - Exchange Filters Pre-Validator hardening
- alcance inmediato esperado:
  - endurecer `PRICE_FILTER`, `LOT_SIZE`, `MIN_NOTIONAL` y precision handling contra contratos oficiales del exchange
  - dejar bloqueo fail-closed antes de cualquier submit live si la normalizacion no cierra
  - preparar el terreno para que `RTLOPS-47` cierre el gate final de preflight live con:
    - exchange adapter
    - market streams
    - user streams
    - filtros oficiales

## RTLOPS-49 - Exchange Adapter Live Hardening - 2026-03-19
- [x] Endurecer signed REST live con:
  - firma HMAC real
  - `server time sync`
  - `recvWindow` gobernado por policy
  - reintento unico por `INVALID_TIMESTAMP`
- [x] Cubrir contratos live minimos de adapter:
  - `exchangeInfo`
  - `balances/account`
  - `new order`
  - `query order`
  - `query open orders`
  - `cancel order`
  - `cancel all open orders`
  - `test order` para `spot`
- [x] Mapear errores del exchange a razones internas auditables.
- [x] Exponer metadata operativa del adapter en `bootstrap_summary()`.
- [x] Revalidar:
  - `test_execution_reality.py`
  - `test_web_execution_reality_api.py`
  - `test_policy_paths.py`
  - `test_web_live_ready.py -k config_policies_endpoint_exposes_numeric_policy_bundle`
- [ ] Deuda chica consciente fuera de RTLOPS-49:
  - `test order` no se declara soportado para `margin/usdm/coinm` mientras no quede confirmado por documentacion oficial primaria accesible y versionada en una corrida posterior;
  - migrar `startup` FastAPI a lifespan sigue siendo una deuda transversal.

## RTLOPS-36 - Validacion operativa `paper -> testnet -> canary` antes de live serio - 2026-03-19
- [x] Agregar autoridad canonica nueva:
  - `config/policies/validation_gates.yaml`
- [x] Crear storage auditable para:
  - `validation_runs`
  - `validation_gate_results`
  - `validation_stage_evidence`
- [x] Implementar `ValidationService` para:
  - consolidar metricas desde execution/reporting/registry
  - emitir `PASS / HOLD / BLOCK`
  - persistir evidence y gate results
- [x] Cablear etapas y readiness:
  - `PAPER`
  - `TESTNET`
  - `CANARY`
  - `LIVE_SERIO` como destino no auto-activado
- [x] Exponer API minima:
  - `GET /api/v1/validation/summary`
  - `GET /api/v1/validation/runs`
  - `GET /api/v1/validation/runs/{id}`
  - `POST /api/v1/validation/evaluate`
  - `GET /api/v1/validation/readiness`
- [x] Reutilizar execution/reporting existentes sin crear sistema paralelo.
- [x] Corregir el merge incremental de filas runtime en `reporting/service.py` para preservar evidencia de fills de execution entre upserts sucesivos.
- [x] Revalidar:
  - `test_policy_paths.py`
  - `test_validation_service.py`
  - `test_web_validation_api.py`
  - `test_reporting_bridge.py`
  - `test_execution_reality.py`
  - `test_web_execution_reality_api.py`
  - `test_web_live_ready.py -k config_policies_endpoint_exposes_numeric_policy_bundle`
- [ ] Deuda chica consciente fuera de RTLOPS-36:
  - migrar `startup` FastAPI a lifespan;
  - si en una iteracion futura hace falta promotion manual con firma/aprobacion, diseniarlo como capa operativa adicional y no como override silencioso del gate engine.

## Correctivo 3A de Execution Reality - 2026-03-19
- [x] Eliminar bundles espejo completos en codigo para:
  - `execution_safety`
  - `execution_router`
- [x] Dejar fallback minimo `fail-closed` explicito en `rtlab_core/execution/reality.py`.
- [x] Separar con claridad:
  - `source_hash` = hash del archivo fuente cargado
  - `policy_hash` = hash del payload efectivo activo
- [x] Exponer trazabilidad corregida de execution en:
  - `bootstrap_summary()`
  - `live_safety_summary()`
  - `GET /api/v1/config/policies`
- [x] Ampliar tests focalizados de execution para:
  - fuente exacta cargada
  - falta de YAML
  - divergencia root/nested
  - hashes correctos
  - no regresion de preflight / router phase 1
- [x] Dejar la base lista para continuar con `3.4` sin arrastrar la deuda de authority/trazabilidad detectada en auditoria.
- [ ] Deuda chica consciente que sigue fuera de 3A:
  - migrar `startup` FastAPI a lifespan;
  - la materializacion `estimated -> realized` y reconcile siguen siendo trabajo propio de `3.4`.

## Correctivo 1A de M2 - 2026-03-19
- [x] Quitar la duplicacion numerica completa de `DEFAULT_RUNTIME_CONTROLS` en `rtlab_core/runtime_controls.py`.
- [x] Mantener solo un fallback `fail-closed` minimo y explicito cuando `runtime_controls.yaml` falta o es invalido.
- [x] Exponer trazabilidad real del bundle en runtime:
  - `source`
  - `source_hash`
  - `policy_hash`
  - `errors`
- [x] Reflejar esa trazabilidad en `GET /api/v1/config/policies`.
- [x] Recortar fallbacks numericos redundantes en consumidores M2 relevantes:
  - `learning/brain.py`
  - `learning/service.py`
  - `risk/circuit_breakers.py`
  - `execution/exec_guard.py`
  - `web/app.py`
- [x] Revalidar tests focalizados del bloque 1 con cobertura adicional de:
  - fuente exacta cargada
  - ausencia de policy
  - divergencia root vs nested
  - consumidores sin defaults numericos redundantes
- [ ] Deuda chica consciente que sigue fuera de 1A:
  - `rtlab_config.yaml.example` y `ModeLiteral` de `rtlab_core/config.py` siguen cubriendo runtime config mas amplia (`backtest/dryrun/capture_only`);
  - no redefinen la taxonomia canonica del runtime global, pero tampoco se tocaron en este correctivo.

## Cierre del bloque RTLOPS-2 / RTLOPS-1 / RTLOPS-7 - 2026-03-18
- [x] Fijar `config/policies/` de la raiz del monorepo como fuente operativa canonica.
- [x] Dejar `rtlab_autotrader/config/policies/` solo como compatibilidad/fallback y no como autoridad equivalente.
- [x] Exponer por API la metadata de autoridad (`authority`) y la taxonomia canonica (`mode_taxonomy`).
- [x] Cerrar el micro-hardening final del frontend de authority/runtime:
  - `lint` deja de escanear `rtlab_dashboard/.pytest_cache` por ignores explicitos en flat config.
  - `auth-backend.test.ts` usa un helper de env de test valido con `NODE_ENV=test` y `BACKEND_API_URL=https://api.example.com`.
  - validacion local final ejecutada:
    - `npm.cmd run lint`
    - `npm.cmd run build`
    - `npx.cmd tsc --noEmit`
- [x] Documentar jerarquia de autoridad tecnica en:
  - `docs/truth/SOURCE_OF_TRUTH.md`
  - `docs/plan/AUTHORITY_HIERARCHY.md`
- [x] Normalizar semanticamente la taxonomia visible:
  - runtime global `PAPER / TESTNET / LIVE`
  - bots `shadow / paper / testnet / live`
  - evidence `backtest / shadow / paper / testnet`
  - `MOCK` como alias legado local, no como runtime real

## Cierre M2 de `Nucleo Arquitectonico y Policies` - 2026-03-18
- [x] Centralizar en `config/policies/runtime_controls.yaml` los grupos:
  - `execution_modes`
  - `observability`
  - `drift`
  - `health_scoring`
  - `alert_thresholds`
- [x] Hacer que el backend lea estos grupos desde YAML canonico en:
  - `mode_taxonomy`
  - drift/learning
  - circuit breakers / exec guard
  - alertas operativas e integridad de breaker
- [x] Exponer en `GET /api/v1/config/policies` un resumen visible de M2:
  - runtime modes canonicos
  - defaults de drift
  - thresholds de health
  - thresholds de alertas operativas
- [x] Mantener compatibilidad acotada:
  - `rtlab_autotrader/config/policies/runtime_controls.yaml` solo como fallback de empaquetado
  - ENV vars existentes solo como override tecnico de YAML, no como fuente paralela
- [ ] Deuda chica consciente:
  - `rtlab_config.yaml.example` y `ModeLiteral` de `rtlab_core/config.py` siguen cubriendo runtime config mas amplia (`backtest/dryrun/capture_only`);
  - no pasan a redefinir la taxonomia canonica del runtime global de este bloque.

## Cierre del bloque `Binance Catalog + Universes + Live Parity Base` - 2026-03-18
- [x] Crear instrument registry persistente y auditable para:
  - `spot`
  - `margin`
  - `usdm_futures`
  - `coinm_futures`
- [x] Registrar snapshots por family/environment con:
  - diff contra snapshot previo
  - provenance minima
  - resumen de severidad
- [x] Derivar `margin` desde Spot + permissions/capability de forma explicita.
- [x] Crear universos canonicos desde `config/policies/universes.yaml`.
- [x] Exponer summary de registry, snapshots, sync, universes y account capabilities por API.
- [x] Calcular `live_parity_base_ready` de forma fail-closed y visible.
- [x] Actualizar `docs/truth` y dejar traza minima en Linear (`RTLOPS-4`).
- [ ] Deuda consciente ya fuera de este bloque:
  - routing live multi-family real
  - order placement real
  - private websockets completos
  - pre-flight/live safety de execution real

## Correctivo 2A del bloque `Binance Catalog + Universes + Live Parity Base` - 2026-03-19
- [x] Eliminar bundles espejo completos en codigo para:
  - `instrument_registry`
  - `universes`
- [x] Dejar fallback minimo `fail-closed` explicito en lugar de defaults espejo completos.
- [x] Separar con claridad:
  - `source_hash` = hash del archivo fuente cargado
  - `policy_hash` = hash del payload efectivo activo
- [x] Exponer trazabilidad corregida en:
  - `registry summary`
  - `snapshots`
  - `universes`
  - `account capabilities` (via `policy_source`)
- [x] Ampliar tests focalizados para:
  - fuente exacta cargada
  - divergencia root/nested
  - falta de YAML
  - hashes y trazabilidad real
- [ ] Deuda chica restante:
  - si en una iteracion futura se quiere una autoridad todavia mas estricta, puede evaluarse validacion estructural mas fina por family/universe especifico;
  - no hace falta un `2B` inmediato para seguir con el programa.

## Cierre del bloque puente `Cost Stack + Reporting / Export Contracts` - 2026-03-18
- [x] Crear autoridad canonica nueva en:
  - `config/policies/cost_stack.yaml`
  - `config/policies/reporting_exports.yaml`
- [x] Backfillear storage auditable para:
  - `performance_cost_snapshots`
  - `trade_cost_ledger`
  - `export_manifest`
  - `cost_source_snapshots`
- [x] Exponer contratos backend minimos de reporting:
  - summary
  - daily
  - monthly
  - costs breakdown
  - trades
  - exports `xlsx/pdf`
- [x] Distinguir `estimated_only / mixed / realized` con fail-closed en `live` cuando falten fuentes reales criticas.
- [x] Dejar contracts TS minimos en dashboard para conectar la UI despues sin rehacer frontend.
- [ ] Deuda consciente ya fuera de este bloque:
  - realizacion fina de `spread/slippage` en runtime real
  - download endpoint dedicado para artefactos si la UI lo necesita
  - migrar `startup` FastAPI a lifespan para quitar warning deprecado

## Ejecucion incremental del bloque `Execution Reality + Live Safety` - 2026-03-19
- [x] Parte 3.1:
  - policies canonicas `execution_safety` / `execution_router`
  - storage base auditable
  - servicio base instanciable
  - wiring minimo en backend
  - tests focalizados de storage/policies/wiring
- [x] Parte 3.2:
  - preflight serio y cost-aware
  - fail-closed en `live`
  - endpoint `POST /api/v1/execution/preflight`
  - summary minimo `GET /api/v1/execution/live-safety/summary`
- [x] Parte 3.3:
  - submit/query/cancel/cancel-all fase 1
  - router limitado explicitamente a `MARKET/LIMIT`
  - intents persistidos antes del submit
  - estados locales auditables
  - endpoints `/api/v1/execution/orders*`
- [x] Parte 3.4:
  - reconcile basico real
  - ingestión base de `executionReport` / `ORDER_TRADE_UPDATE`
  - fallback REST controlado con `degraded_mode` explicito
  - fills -> reporting bridge / `trade_cost_ledger`
  - estimated vs realized por orden/fill
  - `GET /api/v1/execution/reconcile/summary`
- [x] Parte 3.5:
  - kill switch operativo
  - live safety final

## Siguiente bloque logico real
- [x] Ejecutar `RTLOPS-36` sobre la base ya cerrada hasta `3.5`.
- [x] Ejecutar `RTLOPS-49` para endurecer el adapter live y dejar contratos REST reales del exchange sobre la base de execution ya cerrada.
- [ ] Siguiente bloque logico real despues de RTLOPS-49:
  - `RTLOPS-44` = `Market WebSocket Runtime live`.
  - sigue el `LIVE-B1` con streams de market data, reconnect, watchdog de stale data y heartbeat, ahora sobre una base REST ya endurecida.
- [ ] Orden operativo LIVE reconciliado:
  - `LIVE-B1`: `RTLOPS-44`, `RTLOPS-45`, `RTLOPS-46`, `RTLOPS-47` con `RTLOPS-49` ya cerrado como base de contratos REST
  - `LIVE-B2`: `RTLOPS-48`, `RTLOPS-50`, `RTLOPS-23`, `RTLOPS-29` y `RTLOPS-22` ya cerrado como base de costos
  - `LIVE-B3`: `RTLOPS-51`, `RTLOPS-52`, `RTLOPS-54`, `RTLOPS-25`, `RTLOPS-26`, `RTLOPS-27`, `RTLOPS-30`, `RTLOPS-37`, `RTLOPS-53`
  - `LIVE-B4`: `RTLOPS-24`, `RTLOPS-31`, `RTLOPS-32`, `RTLOPS-33`, `RTLOPS-34`, `RTLOPS-35`, `RTLOPS-38`

## Seguimiento RTLRESE backend domains/contracts - 2026-03-16
- [x] RTLRESE-13:
  - persistencia backend separada por dominio (`truth/evidence/policy_state/decision_log`).
- [x] RTLRESE-14:
  - contratos FastAPI separados por dominio:
    - `GET /api/v1/strategies/{strategy_id}/truth`
    - `GET /api/v1/strategies/{strategy_id}/evidence`
    - `GET /api/v1/bots/{bot_id}/policy-state`
    - `PATCH /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/decision-log`
- [ ] Seguimiento chico posterior a RTLRESE-14:
  - migrar consumidores hacia estos contratos de dominio y reducir dependencia de endpoints legacy mezclados (`GET /api/v1/strategies/{id}`, `PATCH /api/v1/bots/{id}`, `GET /api/v1/logs`);
  - agregar smoke HTTP de estos endpoints cuando la venv tenga `httpx` y pueda correr `starlette.testclient`.
- [ ] Pendiente chico posterior a RTLRESE-13:
  - partir `RegistryDB` en repos internos por subdominio;
  - sacar helpers residuales de bot refs / breaker mode del `ConsoleStore`;
  - evaluar si `strategy_policy_guidance` debe quedar en `truth/` o migrar a un subdominio de policy mas especifico.

## Cierre inmediato post RTLRESE-16
- [x] Frontera documental canonica consolidada en `docs/truth`:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- [x] Separacion visual frontend entre:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- [x] Compatibilidad razonable mantenida mientras RTLRESE-14 no este integrado en `main`.
- [ ] Cuando RTLRESE-14 quede integrado en la base real:
  - retirar fallbacks legacy de `strategies/[id]`, `strategies/page` y `execution/page`;
  - dejar solo contratos de dominio.
- [ ] Reejecutar validacion frontend real cuando el entorno tenga Node:
  - `next lint`
  - `tsc --noEmit`
  - `next build`
- [ ] Si aparece una pagina dedicada de bots en RTLRESE-16:
  - conservar la misma separacion semantica ya aplicada en `Execution`;
  - no volver a mezclar runtime global con `policy_state` del bot.
- [x] Queda explicitado que RTLRESE-13/14/15 se cerraron en ramas dedicadas, pero no aparecen integradas en esta base activa.
- [ ] Siguiente paso chico 1:
  - mergear o recrear sobre la base actual el split backend de RTLRESE-13 y verificar que `rtlab_autotrader/rtlab_core/domains/*.py` quede trackeado.
- [ ] Siguiente paso chico 2:
  - mergear o recrear sobre la base actual el split API de RTLRESE-14 y verificar presencia real de:
    - `GET /api/v1/strategies/{id}/truth`
    - `GET /api/v1/strategies/{id}/evidence`
    - `GET /api/v1/bots/{id}/policy-state`
    - `PATCH /api/v1/bots/{id}/policy-state`
    - `GET /api/v1/bots/{id}/decision-log`
- [ ] Siguiente paso chico 3:
  - mergear o recrear sobre la base actual el split frontend de RTLRESE-15 y verificar que:
    - `rtlab_dashboard/src/lib/types.ts` ya no use `last_oos` como eje principal de lectura;
    - `strategies/[id]` separe `truth` de `evidence`;
    - `execution` separe `policy_state` de `decision_log`.
- [ ] Siguiente paso chico 4:
  - retirar etiquetas o contratos legacy solo despues de que 13/14/15 esten efectivamente integradas y validadas en la base real.

## Siguiente bloque chico tras RTLRESE-7
- [x] Clasificacion minima `trusted/legacy/quarantine` en `strategy_evidence`.
- [x] Exclusión de `quarantine` de aprendizaje, guidance y rankings de Option B.
- [x] `legacy` conservado con `needs_validation` explicito y penalizacion de confianza.
- [ ] Exponer `evidence_status/evidence_flags` en endpoints o UI solo donde haga falta auditoria operativa, sin volver a mezclar truth con evidence.
- [ ] Extender esta misma frontera a rankings/catalogos fuera de Option B solo cuando exista un consumidor real y justificado.
- [ ] Revisar si conviene un backfill chico para episodios legacy historicos que hoy no traen metadata suficiente para clasificacion fina.
- [ ] Mantener RTLRESE-10 separado: no mezclar esta cuarentena de evidencia con cambios nuevos de producto, frontend o refactors masivos.
## RTLRESE-10 · research funnel / trial ledger
- [x] Exponer `GET /api/v1/research/funnel`.
- [x] Exponer `GET /api/v1/research/trial-ledger`.
- [x] Mostrar `Research Funnel y Trial Ledger` en `Backtests`.
- [x] Marcar visualmente `trusted/legacy/quarantine` sin vender evidence degradada como confiable.
- [ ] Repetir smoke HTTP de `test_web_live_ready.py` cuando la venv tenga `httpx`.
- [ ] Correr `lint` / `tsc --noEmit` / `build` del dashboard en una maquina con `node`/`npm` disponibles en PATH.
- [ ] Cuando exista estado canonico persistido de evidence en esta linea de codigo, hacer que funnel/ledger lo lean directamente y dejar de derivarlo on-the-fly.

## Tramo vigente (experience learning + shadow + no-live)
- [x] Experience store persistente integrado al registry SQLite.
- [x] Opcion B con proposals, rationale y gating conservador.
- [x] Shadow/mock en vivo sin ordenes, con experiencia `source=shadow`.
- [x] UI de estrategias ampliada con:
  - propuestas
  - guidance
  - estado shadow
  - experiencia por fuente por bot
- [x] UI de backtests ampliada con:
  - selector de bot
  - `Usar pool del bot`
  - fix del `422` en `Backtests / Runs`
- [x] Documentacion base creada:
  - `docs/research/EXPERIENCE_LEARNING.md`
  - `docs/research/BRAIN_OF_BOTS.md`
  - `docs/runbooks/SHADOW_MODE.md`
- [x] Evidencia local escrita del tramo:
  - `docs/audit/LEARNING_EXPERIENCE_VALIDATION_20260306.md`
  - bestia real `BX-000001` completado
  - shadow/mock con default corregido persistiendo experiencia real
- [x] Root de `config/policies` resuelto por YAML reales en backend:
  - evita elegir `/app/config/policies` vacio en deploy
  - habilita que `Modo Bestia` refleje la policy publicada correcta

## Proximo tramo tecnico real
1. Revalidar backend publicado despues del deploy de este fix:
   - `GET /api/v1/research/beast/status` debe dejar de reportar snapshot vacio si el runtime tiene los YAML nested
   - la UI no debe mostrar `Modo Bestia deshabilitado` salvo que la policy real este en `enabled: false`
2. Validar en deploy publicado que `Research Batch` / `Modo Bestia` devuelven `400` fail-closed cuando falta dataset real:
   - no debe crearse un batch nuevo en estado `FAILED` solo por dataset ausente
   - el detalle debe exponer `market/symbol/timeframe` y la accion recomendada
3. Persistir atribucion historica exacta `run_id -> bot_id` / `episode_id -> bot_id`:
   - hoy la vista bot-centrica de runs usa el pool actual del bot
   - falta guardar la relacion historica explicita para no depender de cambios futuros del pool
4. Agregar evidencia visual/operativa de la pestana de aprendizaje en `docs/audit/`.
5. Mantener `LIVE_TRADING_ENABLED=false` y cerrar runtime real solo al final del programa.

## Riesgos abiertos del tramo
- NO EVIDENCIA de OPE conservador (`IPS/DR/SWITCH`) cableado al motor de promotion.
- NO EVIDENCIA de RL offline serio en produccion.
- Shadow sigue siendo simulacion de ejecucion, no orden real.
- Parte de la bibliografia TXT local sigue vacia/danada y reduce trazabilidad automatica.

## Tramo vigente (cleanroom + staging online, sin LIVE)
- [x] Documentacion ordenada con indice unico:
  - `docs/START_HERE.md`
  - `docs/audit/INDEX.md`
  - `docs/_archive/README_ARCHIVE.md`
- [x] App online en staging (solo no-live):
  - frontend: `https://bot-trading-ia-staging.vercel.app`
  - backend: `https://bot-trading-ia-staging.up.railway.app`
  - health backend esperado: `ok=true`, `mode=paper`, `runtime_ready_for_live=false`.
- [x] Runbooks de rollback documentados:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- [x] Policy de logging seguro publicada:
  - `docs/security/LOGGING_POLICY.md` (CWE-532).

## Proximo tramo operativo (sin habilitar LIVE)
1. [x] Ejecutado smoke de staging del dia y evidencia registrada:
   - `docs/audit/STAGING_SMOKE_20260305.md`
   - comando: `python scripts/staging_smoke_report.py --report-prefix artifacts/staging_smoke_ghafree`
2. Mantener smoke diario en staging (login + `/api/v1/health` + `/api/v1/bots`) y registrar evidencia en `docs/audit/`.
   - Nota: si faltan secretos locales, el script marca `NO_EVIDENCE_NO_SECRET` para checks autenticados.
   - workflow automatizado: `Staging Smoke (GitHub VM)` (`/.github/workflows/staging-smoke.yml`).
3. Mantener enforcement no-live en entornos de prueba:
   - `LIVE_TRADING_ENABLED=false`
   - `KILL_SWITCH_ENABLED=true`
   - `MODE/TRADING_MODE=paper` (o `testnet` cuando aplique).
4. Cerrar pendientes tecnicos de runtime end-to-end (orden/fill/reconciliacion/costos) antes de cualquier canary LIVE.
5. Revalidar security CI y branch protection en cada release de hardening.
6. Preparar checklist final paper -> testnet -> canary -> live (sin ejecutar live hasta aprobacion explicita).

## Actualizacion tecnica AP-BOT-1024 (2026-03-05)
- [x] Workflow diario de smoke staging agregado:
  - `/.github/workflows/staging-smoke.yml`
- [x] Validacion bibliografica del patch:
  - `docs/audit/AP_BOT_1024_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - correr al menos 1 run remoto del workflow y registrar artefacto en `docs/audit/`.
  - nota: hoy el workflow todavia no existe en `main`; `gh workflow run staging-smoke.yml` devuelve `404` hasta merge a branch por defecto.

## Actualizacion tecnica AP-BOT-1025 (2026-03-05)
- [x] Fix workflow `remote-protected-checks` en rama tecnica:
  - `strict=false` ahora usa `--no-strict`.
  - eliminado fallback insecure `--password` por CLI.
- [x] Evidencia del hallazgo previo en `main`:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732410544_20260305.md`
- [x] Validacion del fix en corrida real (rama tecnica):
  - `docs/audit/PROTECTED_CHECKS_GHA_22732584979_NON_STRICT_20260305.md`
- [ ] Pendiente operativo:
  - re-run remoto del workflow ya corregido (tras merge) para validar staging con flujo actualizado.

## Actualizacion tecnica AP-BOT-1026 (2026-03-05)
- [x] Workflows remotos con seleccion de secretos por entorno:
  - `remote-protected-checks.yml` y `staging-smoke.yml` priorizan `RTLAB_STAGING_*` en staging.
- [x] No-regresion validada en produccion:
  - `docs/audit/PROTECTED_CHECKS_GHA_22732769817_20260305.md` (`success`).
- [ ] Pendiente operativo:
  - cargar/validar `RTLAB_STAGING_AUTH_TOKEN` o `RTLAB_STAGING_ADMIN_PASSWORD` para runs autenticados de staging.
  - evidencia actual del faltante: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732896736_20260305.md`.

## Actualizacion tecnica AP-BOT-1027 (2026-03-05)
- [x] Hardening de workflows para separar secretos por entorno sin fallback cruzado:
  - `remote-protected-checks.yml`
  - `staging-smoke.yml`
- [x] Runs remotos post-push registrados:
  - produccion `strict=true` sin regresion:
    - `docs/audit/PROTECTED_CHECKS_GHA_22733438064_20260305.md`
  - staging fail-fast con mensaje explicito de secreto faltante:
    - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22733461982_20260305.md`
- [ ] Pendiente operativo:
  - cargar `RTLAB_STAGING_AUTH_TOKEN` o `RTLAB_STAGING_ADMIN_PASSWORD` y re-ejecutar check staging.

## Actualizacion tecnica AP-BOT-1028 (2026-03-05)
- [x] Runbook de secrets publicado:
  - `docs/deploy/GITHUB_ACTIONS_SECRETS.md`
- [ ] Pendiente operativo:
  - aplicar `gh secret set RTLAB_STAGING_ADMIN_PASSWORD` (o token staging) y repetir run staging.

## Actualizacion tecnica AP-BOT-1029 (2026-03-05)
- [x] Runtime readiness con refresh inmediato tras cache negativo:
  - `RuntimeBridge._runtime_exchange_ready(...)`
- [x] Tests runtime agregados y en PASS:
  - `docs/audit/AP_BOT_1029_BIBLIO_VALIDATION_20260305.md`
- [x] Revalidacion remota post-patch:
  - `docs/audit/PROTECTED_CHECKS_GHA_22733869311_20260305.md`
- [ ] Pendiente operativo:
  - seguir cerrando tramo runtime real para `G9_RUNTIME_ENGINE_REAL=PASS` en fase final.

## Actualizacion tecnica AP-BOT-1030 (2026-03-05)
- [x] Script de automatizacion GitHub VM agregado:
  - `scripts/run_protected_checks_github_vm.ps1`
- [x] Revalidacion remota automatizada en `success`:
  - `docs/audit/PROTECTED_CHECKS_GHA_22734260830_20260305.md`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
- [x] Validacion bibliografica del patch:
  - `docs/audit/AP_BOT_1030_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - mantener este script como runner canonico de checks protegidos en releases no-live.

## Actualizacion tecnica AP-BOT-1031 (2026-03-05)
- [x] Runtime fail-closed ante orden local no verificada:
  - no cerrar localmente cuando `order status` falla;
  - bloquear submit remoto si hay orden local abierta no verificada.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1031_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - completar tramo runtime real restante para llevar `G9_RUNTIME_ENGINE_REAL` a `PASS` al final del programa.

## Actualizacion tecnica AP-BOT-1032 (2026-03-05)
- [x] Submit runtime bloqueado sin snapshot de cuenta valido:
  - `reason=account_positions_fetch_failed` en `testnet/live`.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1032_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - cerrar wiring runtime real restante y revalidar remoto post-deploy para mover `G9_RUNTIME_ENGINE_REAL` a `PASS`.

## Actualizacion tecnica AP-BOT-1033 (2026-03-05)
- [x] Submit runtime bloqueado con reconciliacion no valida:
  - `reason=reconciliation_not_ok` cuando `runtime_reconciliation_ok=false`.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1033_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - desplegar rama tecnica y confirmar en entorno remoto que el guard mantiene `no-live` estable sin falsos positivos de submit.

## Actualizacion tecnica AP-BOT-1034 (2026-03-05)
- [x] Runner de checks protegidos robustecido para fallo temprano sin JSON:
  - `scripts/run_protected_checks_github_vm.ps1` ahora emite resumen diagnostico `NO_EVIDENCE`.
- [x] Evidencia de bloqueo staging registrada:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22738098708_20260305.md`
  - causa: `401 Invalid credentials`.
- [x] Sanity run produccion post-patch en verde:
  - `docs/audit/PROTECTED_CHECKS_GHA_22738228159_20260305.md`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1034_BIBLIO_VALIDATION_20260305.md`
- [x] Revalidacion de credenciales staging completada:
  - re-run `22740010128` confirma auth staging OK con `username=Wadmin`;
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22740010128_20260305.md`.
- [x] Pendiente operativo cerrado por AP-BOT-1035:
  - criterio no-live de staging aplicado y revalidado en run `22741088468` (`success`).

## Actualizacion tecnica AP-BOT-1035 (2026-03-05)
- [x] Reporter de checks con criterio no-live exclusivo para staging:
  - `scripts/ops_protected_checks_report.py` agrega `--allow-staging-warns`;
  - en staging permite `G10=WARN` y `breaker=NO_DATA` sin relajar produccion.
- [x] Workflow remoto actualizado:
  - `/.github/workflows/remote-protected-checks.yml` aplica `--allow-staging-warns` cuando `base_url` contiene `staging`.
- [x] Revalidacion remota staging en verde:
  - run `22741088468` -> `success`
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741088468_20260305.md`.
- [x] Persistencia staging corregida sin crash:
  - volumen operativo en `/app/user_data`;
  - `RTLAB_USER_DATA_DIR=/app/user_data`;
  - run `22741651051` en `success` con `g10_status=PASS`.
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1035_BIBLIO_VALIDATION_20260305.md`.
- [x] Pendiente operativo cerrado:
  - staging ya no usa `/tmp` para user data.

## Actualizacion operativa (2026-03-05)
- [x] Re-run `Remote Protected Checks (GitHub VM)` en `success` (run `22704105623`) con `strict=true`.
- [x] Campos de cierre verificados:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- [ ] Pendiente mantenido: `G9_RUNTIME_ENGINE_REAL=PASS` para habilitacion LIVE al final del programa.

## Actualizacion tecnica AP-8001 (2026-03-04)
- [x] BFF fail-closed para fallback mock en error de backend:
  - `production/staging` no permiten fallback mock.
  - `USE_MOCK_API=false` bloquea fallback en cualquier entorno.
- [x] Reglas centralizadas reutilizadas por:
  - `src/app/api/[...path]/route.ts`
  - `src/lib/events-stream.ts`
- Evidencia:
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar wiring runtime broker/exchange end-to-end (orden/fill/reconciliacion real) y corrida verde de `Security CI` root.

## Actualizacion tecnica AP-8002 (2026-03-04)
- [x] Workflow `security-ci` endurecido para instalar `gitleaks` desde release oficial versionado (`8.30.0`) con retries.
- [x] Fallback agregado a install script versionado (`v8.30.0`) + check fail-closed de binario instalado.
- [x] Export `PATH` en el mismo step de instalacion para validar `gitleaks version` en esa corrida.
- [x] Baseline canónica versionada para CI:
  - `docs/security/gitleaks-baseline.json`
  - `scripts/security_scan.sh` actualizado para usarla por defecto.
- [x] `setup-python` en Security CI alineado a `3.11`.
- [x] `actions/checkout` actualizado a `fetch-depth: 0` para alinear `gitleaks git` con baseline historica.
- [x] Corrida verde validada en GitHub Actions (`Security CI`) y `FM-SEC-004` cerrado.
- Evidencia local:
  - cambio en `/.github/workflows/security-ci.yml` (checkout + install tooling).
  - reproduccion del fallo en clone shallow (`1 commit scanned`, `leaks found: 1`) y validacion PASS al convertir a historial completo (`88 commits scanned`, `no leaks found`).
  - run GitHub Actions `22697627615` -> `success` (job `security` `65807494809`).

## Actualizacion tecnica AP-8007 (2026-03-04)
- [x] Thresholds de gates unificados a fuente canonica `config/policies/gates.yaml`.
- [x] Eliminado fallback permisivo a `knowledge/policies/gates.yaml` en learning thresholds.
- [x] Fail-closed aplicado cuando falta config (`pbo/dsr` requeridos + defaults estrictos).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).
- Pendiente inmediato:
  - completar runtime real end-to-end (broker/exchange) y confirmar corrida verde del workflow `Security CI` en GitHub.

## Actualizacion tecnica AP-8011 (2026-03-04)
- [x] Optimizacion incremental aplicada en `/api/v1/bots`:
  - carga lazy de recomendaciones en `cache miss`;
  - indexado de runs limitado a estrategias de pools activos;
  - cap por `(strategy_id, mode)` con `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE`.
- [x] Regresion funcional del endpoint:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- [ ] Pendiente de cierre:
  - rerun benchmark remoto para confirmar `p95` estable en entorno productivo (objetivo `< 300ms` sostenido).

## Actualizacion tecnica AP-8003 (2026-03-04)
- [x] Reconciliacion runtime alineada a semantica real de `openOrders`:
  - compara exchange vs `OMS.open_orders()` (no incluye ordenes locales cerradas).
- [x] Cierre de ordenes locales abiertas ausentes en exchange con grace:
  - `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`).
- [x] Tests nuevos de regresion runtime en verde:
  - `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`
  - `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).
- Pendiente inmediato:
  - completar wiring de ejecucion real por señales (no solo seed/diagnose/reconcile), y rerun de checks protegidos + benchmark remoto.


## Actualizacion tecnica AP-8012 (2026-03-04)
- [x] `breaker_events` en modo fail-closed por defecto:
  - `store.breaker_events_integrity(..., strict=True)` default estricto.
  - endpoint `/api/v1/diagnostics/breaker-events` con `strict=true` default.
- [x] `ops_protected_checks_report.py` endurecido:
  - `--strict` default `true`.
  - `--no-strict` agregado como override explicito.
- [x] `FM-EXEC-003` cerrado.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.
## Actualizacion tecnica AP-BOT-1001/AP-BOT-1002 (2026-03-04)
- [x] AP-BOT-1001: coherencia de ejecucion por estrategia/familia en BacktestEngine.
- [x] AP-BOT-1002: inferencia `orderflow_feature_set` fail-closed + check `known_feature_set` en promotion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.

## Actualizacion tecnica AP-BOT-1003 (2026-03-04)
- [x] Estabilizacion de `/api/v1/bots` para cardinalidad alta:
  - auto-disable de logs recientes en polling default con muchos bots (`BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT`, default `40`);
  - override explicito `recent_logs=true` preservado;
  - cache key separa `source=default|explicit`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Siguiente AP recomendado:
  - cerrar runtime real end-to-end (idempotencia submit/cancel/fill + reconciliacion de posiciones/ordenes externas).

## Actualizacion tecnica AP-BOT-1004 (2026-03-04)
- [x] Runtime `testnet/live` sin avance de fills simulados en loop local.
- [x] OMS local sincronizado desde `openOrders` para mejorar coherencia de reconciliacion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`9 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato:
  - wiring de submit/cancel/fill real con `client_order_id` idempotente y reconciliacion de posiciones (no solo open orders).

## Actualizacion tecnica AP-BOT-1005 (2026-03-04)
- [x] Cancel remoto idempotente por `client_order_id/order_id` en runtime `testnet/live` para `stop/kill/mode_change`.
- [x] Parser comun de `openOrders` reutilizado en reconciliacion + cancel.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`10 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato de runtime real:
  - submit real idempotente (`newClientOrderId`) con pipeline de señales/ejecución, y reconciliacion de posiciones (no solo órdenes abiertas).

## Actualizacion tecnica AP-BOT-1006 (2026-03-04)
- [x] Submit remoto idempotente agregado en runtime `testnet/live` con `newClientOrderId` y ventana configurable.
- [x] Feature flag segura por defecto (`RUNTIME_REMOTE_ORDERS_ENABLED=false`) para no alterar operacion no-live actual.
- [x] Trazabilidad runtime agregada (`runtime_last_remote_submit_at`, `runtime_last_remote_client_order_id`, `runtime_last_remote_submit_error`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.
- Pendiente inmediato:
  - cerrar `AP-BOT-1007`: reconciliacion de posiciones reales (`/api/v3/account`) y wiring de costos/fills finales end-to-end.

## Actualizacion tecnica AP-BOT-1007 (2026-03-04)
- [x] Reconciliacion de posiciones runtime `testnet/live` contra account snapshot real (`/api/v3/account`).
- [x] Posiciones runtime/risk priorizan balances reconciliados cuando estan disponibles.
- [x] Fallback seguro a posiciones derivadas de `openOrders` cuando account snapshot falla.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`7 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1008`: wiring final de costos/fills netos por ejecucion real (fees/slippage/funding por run/runtime) para cierre no-live.

## Actualizacion tecnica AP-BOT-1008 (2026-03-04)
- [x] Costos runtime por fill-delta integrados en `execution metrics` (fees/spread/slippage/funding/total).
- [x] Reset por sesion runtime (`start`/`mode_change`) para evitar mezcla de acumulados.
- [x] Fail-closed de costos runtime en telemetry sintetica.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1009`: hardening de seguridad operativa restante (`--password` en workflows/scripts remotos y validacion CI security root).

## Actualizacion tecnica AP-BOT-1009 (2026-03-04)
- [x] Eliminado uso de `--password` en automatizacion remota (workflows + `scripts/*.ps1`).
- [x] Scripts remotos endurecidos (`seed_bots_remote.py`, `check_storage_persistence.py`): `--password` queda deprecado y bloqueado por defecto (requiere `ALLOW_INSECURE_PASSWORD_CLI=1`).
- [x] Security CI reforzado con guard fail-closed para detectar regresiones de `--password`.
- [x] Revalidacion local de seguridad ejecutada en PASS (`pip-audit` + `gitleaks`).
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\Program Files\Git\bin\bash.exe scripts/security_scan.sh` -> PASS.
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.
- Pendiente inmediato:
  - cerrar `AP-BOT-1010`: estabilizacion final operativa (latencia/soak/checklist no-live de cierre).

## Actualizacion tecnica AP-BOT-1010 (2026-03-04)
- [x] Checklist formal de cierre no-live generado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- [x] Tramo no-live/testnet consolidado en estado GO.
- [ ] LIVE postergado hasta fase final (configuracion APIs/canary/rollback).
- Pendiente inmediato:
  - avanzar con runtime orientado por senales de estrategia para reducir brecha FM-EXEC-001/FM-EXEC-005.

## Actualizacion tecnica AP-BOT-1011 (2026-03-04)
- [x] Runtime remoto ahora decide submit desde estrategia principal (no semilla ciega).
- [x] Guardas fail-closed previas al submit:
  - estrategia principal valida y habilitada;
  - `risk.allow_new_positions=true`;
  - sin posiciones abiertas reconciliadas;
  - sin cooldown activo ni open orders pendientes.
- [x] Trazabilidad de senal runtime agregada:
  - `runtime_last_signal_action`,
  - `runtime_last_signal_reason`,
  - `runtime_last_signal_strategy_id`,
  - `runtime_last_signal_symbol`,
  - `runtime_last_signal_side`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Pendiente inmediato:
  - cerrar lifecycle final de ejecucion real (partial fills/cancel-replace/estado final de orden) para pasar FM-EXEC-001/FM-EXEC-005 a CERRADO.

## Actualizacion tecnica AP-BOT-1012 (2026-03-04)
- [x] Runtime ahora resuelve orden ausente via `order status` remoto antes de cerrar localmente.
- [x] Cierre por estado remoto implementado:
  - `FILLED`/`CANCELED`/`EXPIRED`/`REJECTED` con mapeo de estado local consistente.
- [x] Si orden sigue `NEW/PARTIALLY_FILLED/PENDING_CANCEL`, se mantiene abierta y se reinyecta al snapshot de reconciliacion.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Pendiente inmediato:
  - cerrar parte final de runtime end-to-end (cancel-replace/partial fills avanzados + wiring de riesgo en el mismo ciclo de decision).

## Actualizacion tecnica AP-BOT-1013 (2026-03-04)
- [x] Submit remoto movido despues del calculo de riesgo del mismo ciclo.
- [x] Submit bloqueado cuando el decisionado de riesgo del ciclo actual no permite nuevas posiciones.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - cerrar tramo restante de runtime real (cancel-replace/fills parciales avanzados) y revalidar checks protegidos + benchmark remoto.

## Actualizacion tecnica AP-BOT-1014 (2026-03-04)
- [x] Submit runtime reutiliza snapshot de cuenta del ciclo y evita doble `GET /api/v3/account`.
- [x] Se mantiene gate funcional de posiciones abiertas con menor overhead de API.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - completar cierre de runtime end-to-end restante (cancel-replace/fills parciales avanzados) y ejecutar checks protegidos remotos.

## Actualizacion tecnica AP-BOT-1015 (2026-03-04)
- [x] Cobertura de regresion agregada para estados remotos:
  - `PARTIALLY_FILLED`,
  - `REJECTED`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Pendiente inmediato:
  - completar bloque de runtime real restante (cancel-replace avanzado + revalidacion remota protegida).

## Actualizacion tecnica AP-BOT-1016 (2026-03-05)
- [x] Guard fail-closed agregado para submit remoto en `mode=live`:
  - `LIVE_TRADING_ENABLED=false` bloquea ordenes nuevas en runtime;
  - se registra `runtime_last_remote_submit_error=LIVE_TRADING_ENABLED=false`.
- [x] Test de regresion agregado:
  - `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1016_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_flat_skips_remote_submit or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle or live_skips_submit_when_live_trading_disabled" -q` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`6 passed`).
- Pendiente inmediato:
  - cerrar tramo runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE ahora).

## Actualizacion tecnica AP-BOT-1017 (2026-03-05)
- [x] Telemetria de motivo de submit agregada al runtime:
  - nuevo campo `runtime_last_remote_submit_reason`.
- [x] Submit exitoso ahora deja `reason=submitted` para trazabilidad.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1017_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_meanreversion_submits_sell or live_skips_submit_when_live_trading_disabled or strategy_signal_flat_skips_remote_submit or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - mantener cierre de runtime real restante (cancel-replace/fills avanzados/reconciliacion final) para `G9_RUNTIME_ENGINE_REAL=PASS`.

## Actualizacion tecnica AP-BOT-1018 (2026-03-05)
- [x] Revalidacion remota de latencia en GitHub VM:
  - workflow `Remote Bots Benchmark (GitHub VM)` run `22706414197` en `success`.
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_GHA_22706414197_20260305.md`.
- [x] Resultado objetivo:
  - `p95_ms=184.546` (`PASS` contra `<300ms`),
  - `server_p95_ms=0.07`,
  - `rate_limit_retries=0`.
- [x] Hardening menor del workflow:
  - fix de quoting en `/.github/workflows/remote-benchmark.yml` (`Build summary`) para evitar ruido no bloqueante por backticks.
- Pendiente inmediato:
  - cerrar tramo runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE en esta fase).

## Actualizacion tecnica AP-BOT-1019 (2026-03-05)
- [x] Higiene de telemetria runtime:
  - `runtime_last_remote_submit_reason` se limpia al salir de runtime real;
  - tambien se limpia cuando `exchange_ready` falla.
- [x] Test de regresion agregado:
  - `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1019_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "live_skips_submit_when_live_trading_disabled or clears_submit_reason_when_runtime_exits_real_mode or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - seguir con cierre runtime real restante (cancel-replace/fills avanzados/reconciliacion final) para `G9_RUNTIME_ENGINE_REAL=PASS`.

## Actualizacion tecnica AP-BOT-1020 (2026-03-05)
- [x] Reconciliacion avanzada de estados remotos:
  - `PENDING_CANCEL` conserva `PARTIALLY_FILLED` cuando hay fill parcial;
  - `EXPIRED_IN_MATCH` queda cubierto con cierre terminal correcto.
- [x] Tests de regresion agregados:
  - `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1020_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "keeps_absent_open_order_open_when_order_status_is_new or keeps_partial_state_when_order_status_is_pending_cancel or updates_absent_open_order_partial_fill_from_order_status or marks_absent_open_order_expired_in_match_terminal or marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`5 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - continuar con cierre de runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE en esta fase).

## Actualizacion tecnica AP-BOT-1021 (2026-03-05)
- [x] Revalidacion remota de checks protegidos post AP-BOT-1020:
  - workflow `Remote Protected Checks (GitHub VM)` run `22731722376` en `success`.
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.
- [x] Campos canonicos confirmados:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- Pendiente inmediato:
  - cierre final de runtime real para mover `G9_RUNTIME_ENGINE_REAL` a `PASS` (sin habilitar LIVE aun).

## Actualizacion tecnica AP-BOT-1022 (2026-03-05)
- [x] Refresh del closeout no-live completado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md` actualizado con evidencia fresh:
    - benchmark `22706414197` PASS;
    - protected checks `22731722376` PASS.
- [x] Estado no-live/testnet consolidado en `GO` con evidencia actualizada.
- [ ] Pendiente unico de tramo final:
  - mover `G9_RUNTIME_ENGINE_REAL` a `PASS` al final del programa, junto con habilitacion live controlada (APIs + canary + rollback).

## Revalidacion bibliografica AP-BOT-1006..1010 (2026-03-04)
- [x] Cerrada validacion bibliografica completa por patch:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- [x] En cada AP se declaro `NO EVIDENCIA LOCAL` cuando aplico y se uso solo fuente primaria oficial para cubrir el vacio.
- Pendiente inmediato:
  - mantener este criterio (local-first + fuentes primarias) para AP nuevos.

## Cierre de auditoria integral (2026-03-04)
- Auditoria completa finalizada y documentada en:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Estado:
  - `LIVE`: NO GO (bloqueante tecnico de ejecucion real end-to-end).
  - `No-live/testnet`: GO y estable para continuar hardening antes de conectar APIs LIVE.
- Proximo tramo recomendado (orden):
1. `AP-8001` fail-closed de mock API en BFF.
2. `AP-8002` eliminar `--password` en scripts/workflows remotos.
3. `AP-8007` unificar thresholds de gates (`config` vs `knowledge`) con test de drift.
4. `AP-8011` estabilizar `/api/v1/bots` a `p95 < 300ms` sostenido.
5. `AP-8003` cerrar adapter de ejecucion real con idempotencia/reconciliacion.

## Referencias canonicas de reparacion (2026-03-04)
- Registro maestro de problemas: `docs/audit/FINDINGS_MASTER_20260304.md`
- Plan final de implementacion: `docs/audit/ACTION_PLAN_FINAL_20260304.md`

## Progreso AP (plan final)
- Total AP (plan original): `23`
- AP cerrados (plan original): `23`
- AP adicionales fase 2: `2` (`AP-7001`, `AP-7002`)
- AP cerrados (total extendido): `25`
- AP pendientes (total extendido): `0`
- Avance global extendido: `100%` (`25/25`)

## Estado post-plan AP
- El plan AP original queda ejecutado al `100%`, pero el programa **todavia NO esta listo para LIVE**.
- Hallazgos criticos abiertos para fase siguiente:
  - `FM-EXEC-001`
  - `FM-EXEC-005`
  - `FM-QUANT-008`
  - `FM-RISK-002`
- Hallazgos cerrados en fase 2:
  - `FM-EXEC-002` (G9 reforzado con sync runtime + evidencia exchange + freshness checks).
  - `FM-RISK-003` (learning risk profile por defecto ahora policy-driven).

## Evidencia tecnica fase 2 (2026-03-04)
- Cambios aplicados:
  - `AP-7001`: hardening runtime/gates (`exchange evidence`, `sync runtime`, reconciliacion `openOrders`, fail-closed sintetico).
  - `AP-7002`: risk policy wiring en runtime + default risk profile policy-driven en learning.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.

## Cierre PARTE 7/7 (cerebro del bot)
- Auditoria de cerebro cerrada: decision/learning/rollout validados por codigo.
- Se mantiene politica operativa: **no conectar LIVE todavia**.
- Checklist inmediato de cierre no-live (orden obligatorio):
1. Acoplar runtime operativo real a OMS/risk/reconciliacion y reemplazar payloads sinteticos de `status`/`execution`.
   - avance: AP-0001/AP-0002 + AP-1001/AP-1002/AP-1003/AP-1004 + AP-2001/AP-2002/AP-2003 + AP-7001/AP-7002 implementados (`RuntimeBridge`, telemetry fail-closed, breaker strict, bloqueo de evaluate-phase sin telemetry real, G9 con sync runtime/evidencia exchange y risk policy wiring).
   - pendiente: wiring broker/exchange real end-to-end para ordenes/fills reales (no solo `diagnose` + `openOrders`).
2. Versionar y activar `/.github/workflows/security-ci.yml` en GitHub Actions + branch protection.
   - avance: AP-4001 versionado en branch (`0dbf55d`) + AP-4002 aplicado en GitHub (`main` con required check `security`, `strict=true`) + AP-4003 cerrado (login lockout/rate-limit con backend compartido sqlite).
   - pendiente: corrida verde de `Security CI` tras fix de instalacion de `gitleaks` (run `22674323602` fallo en `Install security tooling`; fix aplicado en workflow, pendiente rerun).
3. Ejecutar hardening final (alertas/recovery/e2e criticos) y volver a correr checks protegidos con evidencia.

## Bloque 3 (quant/learning) - estado actual
- [x] AP-3003: eliminado fallback silencioso de `_learning_eval_candidate` (fail-closed explicito).
- [x] AP-3004: separadas salidas `anti_proxy` y `anti_advanced` en research (con alias legacy).
- [x] AP-3005: `CompareEngine` fail-closed cuando `orderflow_feature_set` queda unknown.
- [x] AP-3006: `strict_strategy_id=true` obligatorio en research/promotion no-demo.
- [x] AP-3001: Purged CV + embargo real en learning/research rapido.
- [x] AP-3002: CPCV real en learning/research.

## Estimacion de bloques restantes (sin LIVE)
- Objetivo declarado: terminar programa en modo no-live/testnet y dejar LIVE para el final.
- Estimacion actual: **faltan 3 bloques tecnicos** para cierre no-live robusto.
1. Bloque A - Runtime de verdad no-live:
   - cerrar reconciliacion/heartbeat sobre broker real (hoy no-live interno).
2. Bloque B - CI/seguridad protegida en root:
   - versionar/activar workflow security root y exigirlo en branch protection.
3. Bloque C - Hardening final de operacion:
   - cerrar gaps de observabilidad/alertas y completar pruebas criticas faltantes (integration/e2e de flujos peligrosos).
- Bloque LIVE real: **postergado por decision operativa** (configuracion de APIs y canary al final).

## Estado de cierre no-live (2026-03-03)
- [x] Benchmark remoto en GitHub VM en PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin retries `429`).
- [x] `Remote Protected Checks (GitHub VM)` en PASS con `strict=true`:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- [x] Revalidacion de seguridad ejecutada en modo estricto (`scripts/security_scan.ps1 -Strict`) sin vulnerabilidades ni leaks.
- [ ] `G9_RUNTIME_ENGINE_REAL` en `PASS` (pendiente runtime real OMS/broker) [POSTERGADO por decision operativa].
- [ ] Habilitacion LIVE real (bloqueada hasta resolver item anterior) [POSTERGADO por decision operativa].
- Criterio actual de tramo: priorizar estabilidad testnet/no-live; LIVE se retoma al final con APIs definitivas configuradas.

## Bloqueantes LIVE (auditoria comite)
1. Completar runtime de ejecucion real contra broker/exchange (paper/testnet/live) con reconciliacion externa y telemetria estricta fail-closed.

## Prioridad 1 (RC operativo)
1. Configurar `INTERNAL_PROXY_TOKEN` en Vercel + Railway y validar que requests directos al backend sin token fallen (hard check de T1 en entorno real).
2. Validar `runtime_engine=real` solo cuando exista loop de ejecucion real y reconciliacion; mantener `simulated` en cualquier otro caso.
3. Confirmar gates LIVE con `G9_RUNTIME_ENGINE_REAL` en PASS antes de habilitar canary.
4. Remediar benchmark remoto de `/api/v1/bots`:
   - ya desplegado cache TTL/invalidacion; evidencia actual sigue en FAIL con 100 bots (`p95=1458.513ms`),
   - mantener `BOTS_MAX_INSTANCES` en rango conservador (recomendado Railway actual: `30`, bajar a `20` si aparece saturacion),
   - probar en Railway `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false` y medir impacto real de latencia,
   - usar headers `X-RTLAB-Bots-Overview-*` y `debug_perf=true` para separar hit/miss y medir efecto de cache,
   - instrumentar timing interno por etapas en `get_bots_overview` (kpis/logs/kills/serialization),
   - agregar indice/materializacion para datos de overview de bots (si el costo principal viene de agregacion en request),
   - rerun remoto con `100` bots y objetivo `p95 < 300ms`.
  - [x] storage persistente estabilizado en staging (`RTLAB_USER_DATA_DIR=/app/user_data`).
5. Validar integridad de `breaker_events` (`bot_id/mode`) y monitorear volumen de `unknown`.
6. Afinar thresholds/parametros por estrategia del dispatcher de `BacktestEngine` y agregar `fail-closed` explicito para strategy_ids no soportados en modo estricto.
7. Validar en entorno desplegado que `surrogate_adjustments` se mantenga apagado fuera de `execution_mode=demo` y que promotion quede bloqueada cuando se active.

## Prioridad 2 (operacion + hardening)
1. Agregar rotacion/expiracion para `INTERNAL_PROXY_TOKEN` y checklist de cambio en runbook.
2. [x] Lockout/rate-limit de login backend con backend compartido sqlite (AP-4003 cerrado).
3. Instrumentar alertas de seguridad para intentos de headers internos sin token valido.
4. Definir policy de despliegue que impida `NODE_ENV=production` con defaults de auth.
5. Asegurar que backend no sea accesible en bypass directo (allowlist/zero-trust) aun con token interno.
6. Branch protection para requerir job `security` antes de merge a `main` (AP-4002 completado).
7. Rotar claves de exchange (testnet/live) y validar que no exista hardcode en archivos locales.

## Prioridad 3 (UX / producto)
1. Deploy frontend/backend y validacion visual completa de UI `Research-first`
2. Validar `Settings -> Diagnostico` (WS/Exchange)
3. Validar `Backtests / Runs -> Validate -> Promote -> Rollout / Gates`
4. Resolver infraestructura testnet/live (si reaparece bloqueo de red/egress)
5. Validar Modo Bestia fase 1 en produccion (cola, budget governor, stop-all, resume)
6. Validar en produccion el bloqueo de `bots mode=live` por gates y revisar mensajes de bloqueo en UI
7. Medir `/api/v1/bots` con 100 bots y verificar objetivo p95 `< 300ms` (tracing real en entorno productivo)
8. Verificar integridad de `breaker_events` (bot_id/mode) en logs reales y alertar filas `unknown_bot`/`unknown` por encima de umbral

## Prioridad 4 (UX / producto)
1. Virtualizacion adicional en tablas grandes restantes (D2 comparador ya virtualizado)
2. Deep Compare avanzado (heatmap mensual, rolling Sharpe, distribucion retornos)
3. Componente reutilizable unico para empty states / CTA
4. Tooltips consistentes en acciones de runs (rerun/clone/export cuando existan)

## Prioridad 5 (robustez / automatizacion)
1. [x] AP-5001: suite E2E critica backend (`login -> backtest -> validate -> promote -> rollout`) cerrada.
2. [x] AP-5002: chaos/recovery runtime (`exchange down -> reconnect`, `desync reconcile -> recover`) cerrado.
3. [x] AP-5003: alertas operativas minimas en `/api/v1/alerts` (drift/slippage/api_errors/breaker_integrity) cerrada.
4. Extender `Fee/Funding` a multi-exchange avanzado (hoy Binance + Bybit base + fallback) con manejo de limites/errores por proveedor
5. Integrar proveedor financiero especifico (mapeos/contratos) sobre el adaptador remoto generico de fundamentals
6. Order Flow L1 full (trade tape/BBO real) sobre VPIN proxy actual
7. Materializar agregados para overview de bots (si sube cardinalidad) e indices adicionales por ventana temporal
8. Revisar y refrescar `gitleaks-baseline.json` cuando se remedien hallazgos historicos.

## Prioridad 6 (nice-to-have)
1. UI de experimentos MLflow (capability)
2. SBOM firmado por release
3. Dashboards externos para canary live (Prometheus/Grafana)
4. Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)

## Siguiente bloque tecnico (2026-03-07)
1. Persistir relacion historica exacta `run_id/episode_id -> bot_id` para que `Backtests / Runs` y `Experience` no dependan del pool actual derivado.
2. Validar preview/deploy de `feature/learning-experience-v1` y confirmar en web los fixes de bots/backtests/beast.
3. Verificar en deploy que desaparezca el falso `Modo Bestia deshabilitado` y que los nuevos intents de batch sin dataset respondan `400` sin crear runs `FAILED` historicos.
4. Revisar simplificacion UX adicional en `Strategies` para evitar exceso de botones visibles por fila (mantener acciones masivas arriba y acciones finas en menu contextual).
5. Evaluar export adicional de conocimiento por lote de bots/estrategias (no solo por bot individual) sin tocar LIVE.

- [x] Persistir `run -> bot` exacto para quick/mass/beast y dejar de depender solo del pool actual derivado.
- [ ] Extender la persistencia fuerte a `experience_episode -> bot_id` para analitica historica por bot sin reconstruccion derivada.
- [ ] Validar en deploy visible que la rama con `beast/status` corregido este realmente desplegada y deje de mostrar `Modo Bestia deshabilitado` falso.
- [ ] Completar export consolidado de conocimiento por lote de bots (no solo export JSON por bot individual).
- [ ] Seguir con simplificacion UX: agrupar acciones masivas/edicion de pool para reducir ruido por fila en `Strategies`.
