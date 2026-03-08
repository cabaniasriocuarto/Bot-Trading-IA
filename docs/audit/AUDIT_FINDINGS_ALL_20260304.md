# AUDIT_FINDINGS_ALL_20260304

Convencion de severidad: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW`

## A) SEGURIDAD (AppSec/DevSecOps)

### FM-SEC-001
- Severidad: HIGH
- Impacto: en produccion el BFF puede servir respuestas mock y ocultar una caida/misconfig de backend real.
- Evidencia: `rtlab_dashboard/src/lib/security.ts:5-11` (`shouldUseMockApi` retorna `true` si falta `BACKEND_API_URL`); `rtlab_dashboard/src/app/api/[...path]/route.ts:85-87` usa `handleMockApi` directo.
- Fix propuesto: forzar fail-closed en produccion (`NODE_ENV=production`) cuando falta `BACKEND_API_URL`; permitir mock solo en `development` o con flag explicita de emergencia.
- Test/Validacion: test unitario en `security.test.ts` que exija `shouldUseMockApi=false` en prod sin backend y test de route que devuelva `500/502` en lugar de mock.

### FM-SEC-002
- Severidad: HIGH
- Impacto: exposicion de secretos en lista de procesos y trazas CI por uso de `--password` en linea de comando.
- Evidencia: `scripts/run_protected_ops_checks.ps1:26,37`; `scripts/run_bots_benchmark_remote.ps1:98`; `scripts/run_remote_closeout_bundle.ps1:51,81,92,115,131`; workflows remotos con fallback password (`.github/workflows/remote-benchmark.yml:239`, `.github/workflows/remote-protected-checks.yml:104`).
- Fix propuesto: priorizar siempre `--auth-token`; para password usar solo stdin/env efimera sin argumentos CLI.
- Test/Validacion: grep CI que falle si detecta `--password` en scripts operativos; smoke de auth por token en workflows.

### FM-SEC-003
- Severidad: MEDIUM
- Impacto: tokens de sesion en texto plano en SQLite incrementan impacto ante lectura de DB local.
- Evidencia: esquema `sessions(token TEXT PRIMARY KEY)` en `rtlab_autotrader/rtlab_core/web/app.py:248-253`; insercion token crudo en `create_session` (`4915-4923`).
- Fix propuesto: almacenar hash (`sha256`) del token + comparar hash al autenticar; rotar sesiones existentes.
- Test/Validacion: test de login/me que confirme que DB no guarda token crudo y que invalidacion por expiracion sigue funcionando.

### FM-SEC-004
- Severidad: MEDIUM
- Impacto: hardening HTTP incompleto en backend FastAPI (dependiente de reverse proxy externo).
- Evidencia: en `rtlab_autotrader/rtlab_core/web/app.py` no hay `CORSMiddleware`, `TrustedHostMiddleware` ni `HTTPSRedirectMiddleware` (busqueda sin coincidencias).
- Fix propuesto: agregar middleware minimo (hosts permitidos, HTTPS redirect si aplica, CORS solo al BFF).
- Test/Validacion: tests de integracion para `Origin` no permitido, `Host` invalido y headers de seguridad esperados.

### FM-SEC-005
- Severidad: MEDIUM
- Impacto: cobertura DevSecOps incompleta (solo pip-audit + gitleaks), menor deteccion de bugs de codigo/supply chain.
- Evidencia: `.github/workflows/security-ci.yml` instala `pip-audit` y `gitleaks`; NO EVIDENCIA de `bandit`, `semgrep`, `CodeQL`, `Scorecard` ejecutandose en CI.
- Fix propuesto: agregar jobs incrementales (bandit/semgrep) y habilitar CodeQL + Scorecard en PR a `main`.
- Test/Validacion: PR con findings de prueba y verificacion de required checks en branch protection.

### FM-SEC-006
- Severidad: LOW
- Impacto: reproducibilidad de auditoria debilitada en otro entorno sin ruta externa de libros.
- Evidencia: `docs/reference/biblio_raw/.gitignore` (sin PDFs); `docs/reference/BIBLIO_INDEX.md:11-12` referencia ruta externa `C:\Users\Admin\Desktop\Libros GPT\Bot IA`.
- Fix propuesto: publicar manifiesto reproducible (hash+origen/licencia) y/o empaquetado interno controlado.
- Test/Validacion: pipeline que valide disponibilidad de fuentes en entorno limpio.

### FM-SEC-007
- Severidad: LOW
- Impacto: parte de la bibliografia local no auditable por extraccion vacia.
- Evidencia: `docs/reference/biblio_txt/2_-Maureen_O_Hara_-_Market_Microstructure_Theory_-Wiley_1998.txt` length `0`; `.../5_-_1985_EMA_Kyle.txt` length `0`; `.../13_-_Security-Analysis-en-espanol.txt` length `0`.
- Fix propuesto: regenerar OCR/TXT y actualizar hash en indice.
- Test/Validacion: job que falle si TXT extraido queda en blanco para items `status=extracted`.

## B) EJECUCION REAL / MICROESTRUCTURA

### FM-EXEC-001
- Severidad: CRITICAL
- Impacto: no hay paridad de ejecucion real para LIVE; runtime sigue simulando fills en memoria.
- Evidencia: `RuntimeBridge` usa `OMS` local (`rtlab_autotrader/rtlab_core/web/app.py:4993-4997`), `_ensure_seed_order` (`5126`), y `self._oms.apply_fill(...)` (`5347`) dentro de `sync_runtime_state`.
- Fix propuesto: adapter de broker real para submit/cancel/query fills + reconciliacion activa por `client_order_id`.
- Test/Validacion: testnet integration e2e (`submit -> partial fill -> reconcile -> close`) con asserts de IDs exchange.

### FM-EXEC-002
- Severidad: HIGH
- Impacto: idempotencia de ordenes insuficiente para exchange real (riesgo de duplicados en retries).
- Evidencia: `rtlab_autotrader/rtlab_core/execution/oms.py` define `order_id` local y no maneja `client_order_id`/exchange IDs (`10-31`).
- Fix propuesto: `client_order_id` deterministico por intento/strategy/run + tabla dedup en persistencia.
- Test/Validacion: reintento forzado con timeout debe preservar una sola orden activa en exchange.

### FM-EXEC-003
- Severidad: HIGH
- Impacto: manejo de partial fills/cancel-replace se limita a simulacion local, sin ciclo real contra exchange.
- Evidencia: `OMS.apply_fill` y `cancel_stale` son locales (`33-57` en `oms.py`); no hay capa dedicada de cancel/replace real en runtime.
- Fix propuesto: implementar estado de orden exchange-aware (`NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED`) sincronizado por polling/ws.
- Test/Validacion: escenario con fills parciales en testnet y verificacion de qty remanente/cancel.

### FM-EXEC-004
- Severidad: MEDIUM
- Impacto: reconciliacion base es comparador de diccionarios; sin acciones automaticas de remediacion.
- Evidencia: `rtlab_autotrader/rtlab_core/execution/reconciliation.py:17-38` solo compara `missing_local/missing_exchange/qty_mismatches`.
- Fix propuesto: agregar reconciliacion activa (fetch exchange, patch estado local, alerta/kill si desync sostenido).
- Test/Validacion: test de desync inyectado y recuperacion automatica.

### FM-EXEC-005
- Severidad: MEDIUM
- Impacto: telemetria de ejecucion usa proxies para spread/slippage en runtime, no solo fills observados.
- Evidencia: `web/app.py:5248-5271` calcula `spread_bps/slippage_bps` por proxy segun open orders; `5441-5444` usa esos valores para robustez.
- Fix propuesto: separar metrica `proxy` de `observed` y exigir `observed` para promotion/live.
- Test/Validacion: gate que falle si `source=proxy` para fases live/canary.

### FM-EXEC-006
- Severidad: MEDIUM
- Impacto: el rate limit implementado protege API entrante, no el consumo saliente a exchange.
- Evidencia: middleware `api_rate_limit_middleware` (`web/app.py:6507-6531`) limita requests cliente->API; NO EVIDENCIA de token bucket especifico para outbound exchange en runtime.
- Fix propuesto: outbound limiter por exchange (peso endpoint, ventanas y backoff exponencial).
- Test/Validacion: simulacion de burst outbound con assert de no-429 en exchange.

### FM-EXEC-007
- Severidad: HIGH
- Impacto: p95 de `/api/v1/bots` inestable con cardinalidad/carga y puede degradar experiencia operativa.
- Evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260303_FINAL.md:16` (`p95_ms 467.372`), `..._AFTER_LITE_QUICK.md:16` (`585.648`), aunque hay rerun mejor `..._RERUN.md:16` (`209.118`).
- Fix propuesto: materializar agregados/kpis, aislar costo de logs recientes, ajustar TTL/cache invalidation por evento.
- Test/Validacion: benchmark remoto controlado con matriz 10/30/100 bots y criterio `p95<300ms` estable en 3 corridas.

### FM-EXEC-008
- Severidad: LOW
- Impacto: no se observa path explicito de funding real-time de exchange en runtime operativo (si en backtest/modelado).
- Evidencia: NO EVIDENCIA de ingesta funding live en loop runtime; funding aparece en pipelines de costos/backtest.
- Fix propuesto: endpoint provider funding + cache TTL + trazabilidad por run/decision.
- Test/Validacion: test de integracion con snapshot funding y efecto en `costs_ratio`.

## C) INVESTIGACION + BACKTESTS (QUANT)

### FM-QUANT-001
- Severidad: HIGH
- Impacto: divergencia entre estrategia declarada y logica ejecutada puede invalidar conclusiones de research.
- Evidencia: dispatch por familia en `rtlab_autotrader/rtlab_core/src/backtest/engine.py:210-310`; estrategias declarativas ricas en `knowledge/strategies/strategies_v2.yaml` no se reflejan 1:1.
- Fix propuesto: executor dedicado por `strategy_id` o bloqueo fail-closed cuando no exista implementacion exacta.
- Test/Validacion: test parametrico `strategy_id -> expected signals/rules` para todas las estrategias activas.

### FM-QUANT-002
- Severidad: MEDIUM
- Impacto: regla temporal fija puede no respetar definiciones por estrategia/timeframe.
- Evidencia: `engine.py` usa `if bars_held >= 12` para `time_stop` (`linea 391 aprox en runner`), sin lectura explicita de YAML por estrategia.
- Fix propuesto: `time_stop` parametrico por strategy config con defaults conservadores.
- Test/Validacion: caso por estrategia donde cambia `time_stop` y se valida salida esperada.

### FM-QUANT-003
- Severidad: MEDIUM
- Impacto: anti-overfitting avanzado coexiste con bloque proxy, riesgo de sobreinterpretar robustez si no se etiqueta bien.
- Evidencia: `mass_backtest_engine.py:804-814` (`method: proxy_fail_closed_for_promotion`) y capa avanzada en `956-1170`.
- Fix propuesto: exigir `anti_advanced.available=true` para promotion no-demo y marcar proxy solo como pre-screen.
- Test/Validacion: test que bloquee promotion cuando solo hay proxy sin evidencia avanzada.

### FM-QUANT-004
- Severidad: MEDIUM
- Impacto: controles de calidad OHLCV no aplicados antes del backtest pueden introducir ruido/sesgo.
- Evidencia: funciones en `rtlab_autotrader/rtlab_core/data/quality.py:9-34` sin uso desde `src/data/loader.py` (busqueda sin referencias).
- Fix propuesto: gate de calidad obligatorio en loader (`missing/duplicates/outliers`) con fail-closed configurable.
- Test/Validacion: dataset con duplicados/gaps debe fallar carga en modo estricto.

### FM-QUANT-005
- Severidad: MEDIUM
- Impacto: en algunos caminos de `web/app.py` hay metricas sinteticas de run que no equivalen al motor completo de backtest.
- Evidencia: calculo simplificado de sharpe/sortino/calmar en `web/app.py:4272-4373`.
- Fix propuesto: unificar fuente de metricas al output canonico de `BacktestEngine` o etiquetar claramente `synthetic_estimate`.
- Test/Validacion: test de consistencia entre endpoint y engine para mismo dataset/params.

### FM-QUANT-006
- Severidad: MEDIUM
- Impacto: controles explicitos de survivorship bias para equities no quedan demostrados.
- Evidencia: NO EVIDENCIA de pipeline de universos con delistings/survivorship handling en loader/provider.
- Fix propuesto: metadata de universo con fecha efectiva + delistings + validacion en backtest.
- Test/Validacion: fixture con activo delistado que no debe aparecer fuera de su ventana historica.

### FM-QUANT-007
- Severidad: LOW
- Impacto: referencia bibliografica incompleta para validar ciertas formulas microestructura (por TXT vacios).
- Evidencia: TXT vacios (O'Hara/Kyle) en `docs/reference/biblio_txt`.
- Fix propuesto: reparar extraccion/indice y versionar artefactos de texto auditables.
- Test/Validacion: check CI de tamaño minimo por TXT extraido.

## D) RIESGO (RISK MANAGER)

### FM-RISK-001
- Severidad: HIGH
- Impacto: incoherencia entre policy canonica y knowledge puede generar decisiones distintas segun la ruta de lectura.
- Evidencia: `config/policies/gates.yaml` (`pbo.reject_if_gt=0.05`, `dsr.min_dsr=0.95`) vs `knowledge/policies/gates.yaml` (`pbo.max_allowed=0.30`, `dsr.min_allowed=1.20`).
- Fix propuesto: una sola fuente activa + validacion de drift en CI.
- Test/Validacion: test que compare valores de thresholds y falle ante divergencia.

### FM-RISK-002
- Severidad: MEDIUM
- Impacto: falta limite explicito de `max trades/day` en `RiskEngine`.
- Evidencia: `rtlab_autotrader/rtlab_core/risk/risk_engine.py:52-72` valida drawdown/exposure/positions; NO EVIDENCIA de contador diario de trades.
- Fix propuesto: agregar contador rolling diario por modo/bot y rechazo por umbral.
- Test/Validacion: simulacion de n+1 trades diarios debe devolver `allow=false`.

### FM-RISK-003
- Severidad: MEDIUM
- Impacto: no se evidencia control explicito de concentracion/correlacion de portafolio.
- Evidencia: NO EVIDENCIA de calculo de correlacion cruzada o concentration limits en risk core.
- Fix propuesto: limite por cluster/correlacion y cap por factor/risk bucket.
- Test/Validacion: test con activos altamente correlacionados que active limite.

### FM-RISK-004
- Severidad: LOW
- Impacto: coexisten limites en settings y policy; riesgo de confusion operativa si no se muestra limite efectivo.
- Evidencia: wiring de min(settings, policy) en runtime (`web/app.py:5046-5072`), pero UI no siempre explicita “effective limit” en todas vistas.
- Fix propuesto: exponer `effective_limits` canonico en endpoint de risk y UI.
- Test/Validacion: snapshot API/UI que compare limites configurados vs efectivos.

## E) OPERACION / SRE

### FM-OPS-001
- Severidad: MEDIUM
- Impacto: observabilidad centrada en logs/metrics internas, sin evidencia de tracing distribuido.
- Evidencia: NO EVIDENCIA de OpenTelemetry/traces exportados en backend/frontend.
- Fix propuesto: instrumentar trazas en rutas criticas (`/api/v1/bots`, backtests run, rollout advance).
- Test/Validacion: smoke con collector y trace-id visible en request logs.

### FM-OPS-002
- Severidad: MEDIUM
- Impacto: alertas existen en endpoint API, pero no se evidencia canal externo de notificacion (pager/chatops).
- Evidencia: `web/app.py` expone `api/v1/alerts`; NO EVIDENCIA de integracion a Slack/Email/Pager.
- Fix propuesto: webhook notifier configurable + umbrales por severidad.
- Test/Validacion: test de `settings/test-alert` que confirme entrega en canal externo.

### FM-OPS-003
- Severidad: LOW
- Impacto: benchmark remoto no esta como check bloqueante permanente de PR/main.
- Evidencia: workflows de benchmark/protected checks existen, pero branch protection explicita solo check `security` (ver `docs/truth/CHANGELOG.md` AP-4002).
- Fix propuesto: required check opcional para performance/regresion en rama release.
- Test/Validacion: PR de prueba bloqueada por degradacion p95.

## F) QA / TESTING

### FM-QA-001
- Severidad: MEDIUM
- Impacto: frontend con cobertura acotada incrementa riesgo de regresion UX/BFF.
- Evidencia: `npm test -- --run` -> `2 files`, `11 tests`.
- Fix propuesto: ampliar tests en rutas criticas (mode switch, live blockers, backtest compare, auth flows).
- Test/Validacion: objetivo minimo inicial 40+ tests frontend y smoke e2e Playwright en CI.

### FM-QA-002
- Severidad: LOW
- Impacto: warning de charts detectado solo en build; puede escapar a PRs sin threshold.
- Evidencia: `npm run build` muestra warnings Recharts `width(-1)/height(-1)`.
- Fix propuesto: test visual/smoke de layout para secciones con `ResponsiveContainer`.
- Test/Validacion: snapshot visual o assert de contenedores con `minHeight`.

### FM-QA-003
- Severidad: LOW
- Impacto: faltan pruebas de seguridad SAST automatizadas en CI.
- Evidencia: `security-ci.yml` sin jobs bandit/semgrep/codeql.
- Fix propuesto: incorporar jobs y establecer baseline aceptada.
- Test/Validacion: workflow `security` con 4 etapas (`deps`, `secrets`, `sast`, `scorecard`).

## G) UX/UI (Frontend Safety)

### FM-UX-001
- Severidad: MEDIUM
- Impacto: accion de pasar bot a LIVE desde vista `Strategies` puede ejecutarse sin doble confirmacion local.
- Evidencia: `rtlab_dashboard/src/app/(app)/strategies/page.tsx:437-448` (`patchBot` sin confirm); botones live en `1097` invocan `patchBot(..., { mode: "live" })`.
- Fix propuesto: replicar confirmacion explicita y texto de riesgo como en `execution/page.tsx`.
- Test/Validacion: test UI que exija confirmacion antes de patch LIVE.

### FM-UX-002
- Severidad: LOW
- Impacto: warnings de layout de charts pueden mostrar paneles con altura 0 en ciertos estados SSR.
- Evidencia: `backtests/page.tsx` tiene `ResponsiveContainer` sin `minHeight` en bloques `2588` y `2616`; build arroja warning.
- Fix propuesto: definir `minHeight` o `aspect` para todos los contenedores.
- Test/Validacion: build sin warnings + smoke visual en mobile/desktop.

## H) CEREBRO DEL BOT (Aprendizaje/Decision)

### FM-BRAIN-001
- Severidad: HIGH
- Impacto: el “cerebro” de seleccion combina logica rule-based y scoring, pero sin evidencia de pipeline ML productivo `fit/predict` con versionado de modelo desplegado.
- Evidencia: `learning/service.py` y `learning/brain.py` realizan evaluacion/ranking/weights; NO EVIDENCIA de serving model con artifact registry + inferencia online estable.
- Fix propuesto: definir modo ML explícito (offline training -> registry -> shadow infer -> canary -> approve).
- Test/Validacion: e2e de promotion de modelo con rollback.

### FM-BRAIN-002
- Severidad: MEDIUM
- Impacto: inferencia de `orderflow_feature_set` mantiene fallback backward-compatible que puede ocultar falta de metadata.
- Evidencia: `_infer_orderflow_feature_set` retorna default `orderflow_on` (`web/app.py:8118`) cuando no hay evidencia previa.
- Fix propuesto: en no-demo usar fail-closed (`orderflow_unknown`) salvo metadata explicita.
- Test/Validacion: test de promotion que falle si `feature_set` no esta explicitado.

### FM-BRAIN-003
- Severidad: LOW
- Impacto: opcion B y controles humanos estan correctamente aplicados; riesgo residual bajo.
- Evidencia: `web/app.py` marca `allow_live=false`, `option_b_no_auto_live` en rutas de promotion/rollout (`7445`, `8600`, `8987-8991`).
- Fix propuesto: mantener; agregar auditoria de aprobaciones por usuario/justificacion.
- Test/Validacion: test de auditoria que requiera `approved_by` y `reason`.

### FM-BRAIN-004
- Severidad: LOW
- Impacto: DSR/PBO/CSCV implementados, pero deben mantenerse como gates obligatorios en no-demo para evitar sobreajuste.
- Evidencia: `learning/brain.py` (`pbo_cscv`, `deflated_sharpe_ratio`) y `learning/service.py:461-486`.
- Fix propuesto: bloquear promotion cuando falte evidencia estadistica minima.
- Test/Validacion: test de candidate con `pbo>umbral` o `dsr<umbral` debe fallar.

## Estado de validacion ejecutada en esta auditoria
- `./scripts/security_scan.ps1 -Strict` -> PASS.
- `python -m pytest -q rtlab_autotrader/tests` -> PASS.
- `npm test -- --run` -> PASS.
- `npm run lint` -> PASS.
- `npm run build` -> PASS (warnings Recharts pendientes).
