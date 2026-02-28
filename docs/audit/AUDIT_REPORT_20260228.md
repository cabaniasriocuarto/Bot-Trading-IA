# AUDIT REPORT (Comité) - 2026-02-28

## Resumen ejecutivo
- Estado para LIVE: **NO-GO**.
- Motivos bloqueantes actuales:
  - Runtime de ejecución real **NO EVIDENCIA** (el ciclo `start/stop` es de estado, no OMS/broker real).
  - Backtest engine usa señal única y no ejecuta lógica específica por `strategy_id` (riesgo de validez de research).
  - Persisten inconsistencias de fuente de políticas (`knowledge` vs `config`) en superficies de aprendizaje/UI.
- Estado para Research/Backtests: **usable**, con mejoras recientes:
  - fail-closed en `purged-cv/cpcv` para Quick Backtest.
  - anti-overfitting y gates avanzados en mass backtests.
  - orderflow toggle y trazabilidad de feature set.
- Seguridad:
  - mitigado bypass de headers internos sin token confiable.
  - agregado rate-limit/lockout de login backend.
  - falta rate-limit general para endpoints costosos y hardening en CI (gitleaks/semgrep/codeql).

## Alcance auditado
- Backend: `rtlab_autotrader/rtlab_core/web/app.py`, `rtlab_autotrader/rtlab_core/rollout/gates.py`, `rtlab_autotrader/rtlab_core/src/backtest/engine.py`, `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`, `rtlab_autotrader/rtlab_core/fundamentals/credit_filter.py`.
- Frontend/BFF: `rtlab_dashboard/src/app/api/[...path]/route.ts`, `rtlab_dashboard/src/lib/events-stream.ts`, `rtlab_dashboard/middleware.ts`, `rtlab_dashboard/src/lib/auth.ts`.
- Policies/docs: `docs/truth/*`, `docs/SECURITY.md`, `knowledge/**`, `config/policies/**`, `docs/BACKTESTS_RESEARCH_SYSTEM_FINAL.md`, `docs/MASS_BACKTEST_DATA.md`.
- Seguridad/deps: `scripts/security_audit.sh`, `scripts/security_scan.sh`, `requirements-runtime.txt`, `requirements-research.txt`.
- Bibliografía local: indexada en `docs/reference/BIBLIO_INDEX.md` con SHA256.

## Fase 0 - Inventario (sin cambios funcionales)
- Entrypoint backend: `create_app()` en `rtlab_autotrader/rtlab_core/web/app.py:4621`.
- Entrypoint frontend BFF: proxy en `rtlab_dashboard/src/app/api/[...path]/route.ts`.
- Persistencia principal:
  - backend: `user_data/console_api.sqlite3`, `user_data/backtests/catalog.sqlite3`, `user_data/backtests/runs.json`.
  - mass backtests: `user_data/research/mass_backtests/*`.
- Jobs research:
  - mass backtest coordinator/scheduler en `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`.
- Fuentes de policy:
  - numéricas canónicas (runtime): `config/policies/*`.
  - knowledge pack: `knowledge/policies/*`, `knowledge/strategies/strategies_v2.yaml`.

## Fuente canónica y conflictos
- Canónica propuesta para runtime/gates/risk/costos: `config/policies/*`.
- Conflicto detectado:
  - `knowledge/policies/gates.yaml` (PBO 0.30 / DSR 1.20) vs `config/policies/gates.yaml` (PBO 0.05 / DSR 0.95).
  - evidencia: `knowledge/policies/gates.yaml`, `config/policies/gates.yaml`, `rtlab_autotrader/rtlab_core/learning/knowledge.py:143`.
- Resolución parcial ya aplicada:
  - GateEvaluator prioriza `config/policies/gates.yaml` y fallback a `knowledge`.
  - evidencia: `rtlab_autotrader/rtlab_core/rollout/gates.py:45`.

## Hallazgos críticos/prioritarios (top)
1. **HIGH** - Runtime real no implementado (solo estado simulado): `rtlab_autotrader/rtlab_core/web/app.py:7396`, `rtlab_autotrader/rtlab_core/web/app.py:7485`.
2. **CRITICAL** - Validez de research: `BacktestEngine` usa lógica única y no ejecuta estrategias por `strategy_id`: `rtlab_autotrader/rtlab_core/src/backtest/engine.py:204`, `rtlab_autotrader/rtlab_core/src/backtest/engine.py:1124`.
3. **HIGH** - `min_trades_per_symbol` definido pero no aplicado en gate: `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:345`, `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py:1009`.
4. **HIGH** - conflicto `knowledge` vs `config` sigue visible en payload de learning: `rtlab_autotrader/rtlab_core/web/app.py:668`.
5. **HIGH** - hard limits de `risk_policy.yaml` no demostrados en ejecución real (depende de OMS no implementado): `config/policies/risk_policy.yaml`, `rtlab_autotrader/rtlab_core/web/app.py:7396`.
6. **MEDIUM** - métricas de ejecución sintéticas en endpoint: `rtlab_autotrader/rtlab_core/web/app.py:4499`.
7. **MEDIUM** - rate limit general API (no login) **NO EVIDENCIA**.
8. **MEDIUM** - backup/restore operativo de DB **NO EVIDENCIA** en scripts/runbooks.
9. **MEDIUM** - E2E frontend de flujo crítico **NO EVIDENCIA**.
10. **MEDIUM** - validación bibliográfica automática de fórmulas **NO EVIDENCIA** (hash/index sí; parser PDF no disponible en entorno actual).

## Cambios incrementales aplicados en esta auditoría
- Seguridad backend:
  - se bloqueó trust de headers internos sin token: `rtlab_autotrader/rtlab_core/web/app.py:4220`.
  - se agregó limiter de login con lockout: `rtlab_autotrader/rtlab_core/web/app.py:732`, `rtlab_autotrader/rtlab_core/web/app.py:4700`.
- Seguridad BFF:
  - fail-closed si falta `INTERNAL_PROXY_TOKEN` en proxy HTTP/SSE:
    - `rtlab_dashboard/src/app/api/[...path]/route.ts`
    - `rtlab_dashboard/src/lib/events-stream.ts`
- Configuración:
  - `INTERNAL_PROXY_TOKEN` agregado en `.env.example` backend/frontend.
- Bibliografía:
  - script incremental `scripts/biblio_extract.py`.
  - índice SHA256 regenerado: `docs/reference/BIBLIO_INDEX.md`.
  - salida de txt no versionada: `docs/reference/biblio_txt/.gitignore`.
- Seguridad operativa:
  - `docs/SECURITY.md` actualizado con threat model mínimo, checklist y comandos.

## Validación y tests ejecutados
- Ejecutado (focal):
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token or auth_login_rate_limit_and_lock_guard or gates_requires_auth or live_mode_blocked_when_runtime_engine_is_simulated" -q`
  - Resultado esperado: PASS de pruebas focales de auth/gates/runtime.
- Si no corre en tu entorno, ejecutar:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token or auth_login_rate_limit_and_lock_guard" -q`

## Go/No-Go
- Paper: **GO condicional** (seguridad básica + research).
- Testnet: **GO condicional** (tras cerrar hallazgos HIGH de runtime/validación estrategia).
- LIVE: **NO-GO** hasta cerrar bloqueantes:
  1. Runtime OMS/Broker real mínimo + reconciliación.
  2. Corrección de validez de estrategia por `strategy_id`.
  3. Enforcement `min_trades_per_symbol`.
  4. Unificación final de source-of-truth de gates (UI/runtime/learning).
