# AUDIT FINDINGS (Completo) - 2026-02-28

Formato por hallazgo: Severidad, Impacto, Evidencia, Fix propuesto, Test/Validación.

## F-SEC-001 - Proxy interno sin token (mitigado)
- Severidad: CRITICAL (estado actual: mitigado).
- Impacto: posibilidad de suplantar rol admin vía headers internos.
- Evidencia:
  - control de trust interno: `rtlab_autotrader/rtlab_core/web/app.py:4216`.
  - BFF envía token interno: `rtlab_dashboard/src/app/api/[...path]/route.ts:31`, `rtlab_dashboard/src/lib/events-stream.ts:42`.
- Fix propuesto:
  1. Mantener validación obligatoria de `x-rtlab-proxy-token`.
  2. Rotar `INTERNAL_PROXY_TOKEN` por entorno.
  3. Aplicar allowlist/zero-trust al backend.
- Test/Validación:
  - `rtlab_autotrader/tests/test_web_live_ready.py:177` (`test_internal_headers_require_proxy_token`).
- OWASP: API2 Broken Authentication, API8 Misconfiguration.

## F-SEC-002 - Login sin control de abuso (mitigado parcial)
- Severidad: HIGH (estado actual: mitigado parcial).
- Impacto: fuerza bruta sobre `/api/v1/auth/login`.
- Evidencia:
  - limiter backend: `rtlab_autotrader/rtlab_core/web/app.py:721`.
  - aplicación en login: `rtlab_autotrader/rtlab_core/web/app.py:4700`.
- Fix propuesto:
  1. Mantener limiter actual (10/10min + lockout 30min tras 20 fallos).
  2. Persistir intentos en DB/Redis para escenarios multi-instancia (pendiente).
- Test/Validación:
  - `rtlab_autotrader/tests/test_web_live_ready.py` (`test_auth_login_rate_limit_and_lock_guard`).
- OWASP: API4 Unrestricted Resource Consumption, API2 Broken Authentication.

## F-SEC-003 - Rate limit general API (abierto)
- Severidad: MEDIUM.
- Impacto: endpoints costosos pueden degradar disponibilidad (DoS lógico).
- Evidencia:
  - **NO EVIDENCIA** de limiter global por IP/ruta en backend fuera de login.
- Fix propuesto:
  1. Agregar middleware de rate-limit por IP.
  2. Perfilar rutas costosas (`/api/v1/research/*`, `/api/v1/backtests/*`) con límites dedicados.
- Test/Validación:
  - tests de 429 por endpoint y ventana temporal.
- OWASP: API4 Unrestricted Resource Consumption.

## F-SEC-004 - Security scanning en CI (cerrado)
- Severidad: MEDIUM (estado actual: mitigado).
- Impacto: reduce riesgo de merge con secretos o dependencias vulnerables.
- Evidencia:
  - CI ahora incluye job `security`: `rtlab_autotrader/.github/workflows/ci.yml`.
  - script endurecido y baseline-aware: `scripts/security_scan.sh`.
- Fix propuesto:
  1. Mantener `SECURITY_SCAN_STRICT=1` en CI.
  2. Requerir job `security` como status check en branch protection.
- Test/Validación:
  - `bash scripts/security_scan.sh` en local/CI debe terminar en `OK`.
  - PR con secreto dummy o dependencia vulnerable debe fallar.
- OWASP: API8 Misconfiguration, ASVS V1/V14.

## F-EXEC-001 - Runtime de trading real (abierto)
- Severidad: HIGH.
- Impacto: “LIVE” puede interpretarse como real sin loop OMS/fills/posición.
- Evidencia:
  - start/stop solo cambia estado: `rtlab_autotrader/rtlab_core/web/app.py:7396`.
  - close-all no ejecuta cancel/flatten real: `rtlab_autotrader/rtlab_core/web/app.py:7485`.
- Fix propuesto:
  1. Implementar `BrokerAdapter` paper/testnet (place/cancel/reconcile).
  2. Conectar kill-switch a cancel-all + flatten (testnet/paper).
  3. Mantener `G9_RUNTIME_ENGINE_REAL` bloqueante para LIVE.
- Test/Validación:
  - integración con broker simulado: idempotencia, partial fills, cancel/replace.

## F-EXEC-002 - Métricas de ejecución sintéticas (abierto)
- Severidad: MEDIUM.
- Impacto: decisiones operativas sobre datos no reales.
- Evidencia:
  - payload fijo/sintético: `rtlab_autotrader/rtlab_core/web/app.py:4499`.
- Fix propuesto:
  1. Reemplazar por métricas reales de pipeline (latencia, fill ratio, errores/rate limits).
- Test/Validación:
  - smoke de series con valores provenientes de runtime real/sim.

## F-QUANT-001 - Engine ignora estrategia específica (abierto)
- Severidad: CRITICAL.
- Impacto: riesgo de ranking/promoción inválido (todas las estrategias evaluadas con misma lógica).
- Evidencia:
  - lógica única de señal en `StrategyRunner._signal`: `rtlab_autotrader/rtlab_core/src/backtest/engine.py:204`.
  - `strategy_id` se usa para metadata/trade tagging, no para seleccionar implementación: `rtlab_autotrader/rtlab_core/src/backtest/engine.py:1124`.
  - callback de mass backtest delega a `create_event_backtest_run` con el mismo engine base: `rtlab_autotrader/rtlab_core/web/app.py:4127`.
- Fix propuesto:
  1. Resolver `strategy_id` contra un registro de implementación.
  2. Fallar cerrado cuando `strategy_id` no tenga implementación ejecutable.
  3. Mantener fallback solo en DEMO y sin promoción.
- Test/Validación:
  - test de diferenciación de PnL/señales entre 2 strategy_id distintos sobre mismo dataset.

## F-QUANT-002 - `min_trades_per_symbol` no aplicado (abierto)
- Severidad: HIGH.
- Impacto: pasa variantes con baja muestra por símbolo (sobreajuste).
- Evidencia:
  - policy define `min_trades_per_symbol`: `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:345`.
  - check implementado solo en `trade_count_oos` global: `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1009`.
- Fix propuesto:
  1. Calcular `min_trades_per_symbol_oos`.
  2. Agregar check explícito y bloquear promoción cuando no cumpla.
- Test/Validación:
  - unit con 2 símbolos: uno <30 trades => FAIL.

## F-QUANT-003 - Purged/CPCV quick backtest (mitigado)
- Severidad: MEDIUM (estado actual: mitigado).
- Impacto: validación inexistente podía inducir falsa robustez.
- Evidencia:
  - fail-closed en engine: `rtlab_autotrader/rtlab_core/src/backtest/engine.py:1234`.
- Fix propuesto:
  1. Mantener bloqueo hasta implementación real.
  2. Exponer mensaje claro en UI.
- Test/Validación:
  - `test_backtests_run_rejects_purged_cv_and_cpcv_until_implemented`.

## F-CONF-001 - Conflicto de fuentes de gates (abierto)
- Severidad: HIGH.
- Impacto: decisiones inconsistentes entre learning/UI/runtime.
- Evidencia:
  - `knowledge/policies/gates.yaml` vs `config/policies/gates.yaml`.
  - `safe_update.gates_file` en learning embebido apunta a knowledge: `rtlab_autotrader/rtlab_core/learning/knowledge.py:143`.
  - endpoint learning expone ese path por defecto: `rtlab_autotrader/rtlab_core/web/app.py:668`.
- Fix propuesto:
  1. Declarar `config/policies/gates.yaml` como canónica transversal.
  2. Dejar `knowledge` solo como referencia documental.
  3. Test de consistencia entre summary/gates runtime/learning.
- Test/Validación:
  - test que compare thresholds pbo/dsr desde endpoints y GateEvaluator.

## F-RISK-001 - Risk policy sin enforcement en runtime real (abierto)
- Severidad: HIGH.
- Impacto: límites de pérdida/exposición pueden quedar declarativos.
- Evidencia:
  - policy numérica existe: `config/policies/risk_policy.yaml`.
  - runtime real **NO EVIDENCIA** (ver F-EXEC-001).
- Fix propuesto:
  1. Aplicar límites pre-trade y post-fill en broker adapter.
  2. Integrar kill-switch por capas (soft/hard).
- Test/Validación:
  - integración: breach de daily loss -> soft kill; breach DD -> hard kill.

## F-SRE-001 - Backup/restore operativo (abierto)
- Severidad: MEDIUM.
- Impacto: pérdida de datos operativos ante corrupción/disco.
- Evidencia:
  - **NO EVIDENCIA** de runbook formal `backup/restore` en `docs/runbooks`.
- Fix propuesto:
  1. scripts `backup_user_data` y `restore_user_data`.
  2. runbook con drill trimestral.
- Test/Validación:
  - restaurar en entorno limpio y validar integridad de DB.

## F-QA-001 - E2E de flujo crítico (abierto)
- Severidad: MEDIUM.
- Impacto: regresiones UI/proxy pueden pasar a release.
- Evidencia:
  - hay tests backend y unit frontend; **NO EVIDENCIA** de E2E end-to-end productivo.
- Fix propuesto:
  1. añadir Playwright/Cypress para flujo login→batch→compare→validate→promote.
- Test/Validación:
  - pipeline verde con spec E2E mínimo.

## F-BIBLIO-001 - Verificación bibliográfica automática (abierto parcial)
- Severidad: MEDIUM.
- Impacto: fórmulas/gates pueden no validarse automáticamente contra PDFs.
- Evidencia:
  - índice SHA generado: `docs/reference/BIBLIO_INDEX.md`.
  - extractor incremental: `scripts/biblio_extract.py`.
  - `txt_status=no_pdf_parser` en índice actual.
- Fix propuesto:
  1. instalar parser PDF (`pypdf`) en entorno de auditoría offline.
  2. ejecutar extractor y registrar hashes de TXT.
- Test/Validación:
  - `python scripts/biblio_extract.py --input-dir "<ruta_biblio_local>"`.

## F-POS-001 - Bots overview sin N+1 (positivo)
- Severidad: LOW (mejora aplicada).
- Impacto: reduce latencia y carga DB.
- Evidencia:
  - batch queries (máx. 3 lecturas): `rtlab_autotrader/rtlab_core/web/app.py:2496`.
  - endpoint reusa overview batch: `rtlab_autotrader/rtlab_core/web/app.py:4807`.
- Fix propuesto: mantener.
- Test/Validación:
  - `test_bots_overview_scopes_kills_by_bot_and_mode`.
