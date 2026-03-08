# AUDIT_REPORT_20260304

Fecha de auditoria: 2026-03-04
Alcance: backend (`rtlab_autotrader`), frontend/BFF (`rtlab_dashboard`), research/backtests, riesgo, ejecucion, ops y seguridad.

## 0) QUE LEI

### Repo (principal)
- `docs/reference/HANDOFF.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`
- `docs/SECURITY.md`
- `config/policies/gates.yaml`
- `knowledge/policies/gates.yaml`
- `config/policies/risk_policy.yaml`
- `config/policies/fees.yaml`
- `config/policies/microstructure.yaml`
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/rtlab_core/execution/oms.py`
- `rtlab_autotrader/rtlab_core/execution/reconciliation.py`
- `rtlab_autotrader/rtlab_core/risk/risk_engine.py`
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
- `rtlab_autotrader/rtlab_core/src/data/loader.py`
- `rtlab_autotrader/rtlab_core/data/quality.py`
- `rtlab_autotrader/rtlab_core/learning/brain.py`
- `rtlab_autotrader/rtlab_core/learning/service.py`
- `rtlab_autotrader/rtlab_core/rollout/compare.py`
- `rtlab_dashboard/src/app/api/[...path]/route.ts`
- `rtlab_dashboard/src/lib/security.ts`
- `rtlab_dashboard/src/lib/security.test.ts`
- `rtlab_dashboard/middleware.ts`
- `rtlab_dashboard/src/app/(app)/execution/page.tsx`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_dashboard/src/app/(app)/settings/page.tsx`
- `scripts/security_scan.ps1`
- `scripts/security_scan.sh`
- `scripts/ops_protected_checks_report.py`
- `scripts/run_protected_ops_checks.ps1`
- `scripts/run_bots_benchmark_remote.ps1`
- `scripts/run_remote_closeout_bundle.ps1`
- `.github/workflows/security-ci.yml`
- `.github/workflows/remote-benchmark.yml`
- `.github/workflows/remote-protected-checks.yml`

### Bibliografia local usada (indice + txt)
- `docs/reference/BIBLIO_INDEX.md`
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt`
- `docs/reference/biblio_txt/4_-_Price_Impact.txt`
- `docs/reference/biblio_txt/6_-_Flow_Toxicity_and_Liquidity_in_a_High_Frequency_World_Easley_L_pez_de_Prado_y_O_Hara_2012.txt`
- `docs/reference/biblio_txt/11_-_Advances_in_Financial_Machine_Learning_Marcos_L_pez_de_Prado_2018.txt`
- `docs/reference/biblio_txt/16_-_Backtesting-and-its-Pitfalls.txt`
- `docs/reference/biblio_txt/17_-_backtest-prob.txt`
- `docs/reference/biblio_txt/18_-_advances-in-financial-machine-learning-1nbsped-9781119482086-9781119482116-9781119482109_compress.txt`

### Fuentes web primarias consultadas
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
- OWASP API Security Top 10 2023: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- Binance Spot Trading Endpoints: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints
- Binance Spot Limits: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/limits
- OpenSSF Scorecard: https://github.com/ossf/scorecard

### FALTA
- `docs/reference/biblio_raw/` en repo no contiene PDFs versionados (solo `.gitignore`).
- En `docs/reference/biblio_txt/` hay extracciones vacias para parte de la biblio (`2`, `5`, `13`).

## 1) RESUMEN EJECUTIVO

- Listo para LIVE: NO.
- Estado no-live/testnet: funcional y testeado, con gates y checks protegidos implementados.
- Bloqueante #1 (CRITICAL): runtime de ejecucion en `testnet/live` sigue simulando ciclo de orden/fill interno en `RuntimeBridge`.
- Bloqueante #2 (HIGH): BFF puede caer a mock API por misconfig en produccion (`BACKEND_API_URL` ausente).
- Bloqueante #3 (HIGH): persisten rutas operativas que pasan password por CLI (`--password`), riesgo de exposicion en procesos/logs.
- Bloqueante #4 (HIGH): divergencia entre estrategias declaradas (YAML) y comportamiento ejecutado real (dispatch por familia + reglas comunes).
- Bloqueante #5 (HIGH): latencia de `/api/v1/bots` no estable en todas las corridas productivas (hay reportes sobre objetivo p95).

## 2) MATRIZ DE RIESGOS (TOP-10)

| Riesgo | Severidad | Evidencia | Impacto | Fix corto | Esfuerzo |
|---|---|---|---|---|---|
| Runtime real aun simulado para fills/order loop | CRITICAL | `web/app.py` RuntimeBridge (`_oms.apply_fill`) | No paridad LIVE real | Broker adapter + submit/cancel/reconcile reales | L |
| Estrategia declarada vs ejecutada diverge | HIGH | `knowledge/strategies/strategies_v2.yaml` vs `src/backtest/engine.py` | Riesgo de creer que se ejecuta logica no implementada | Mapa estricto `strategy_id -> executor` fail-closed | M |
| Mock API en produccion por falta de backend URL | HIGH | `security.ts`, `api/[...path]/route.ts` | Datos no reales en UI/BFF | Fail-closed en prod, mock solo dev | S |
| Password en CLI/workflows | HIGH | scripts remotos y workflows | Exposicion de secretos | Token-first + stdin/env efimero | S |
| Inconsistencia de gates policy (config vs knowledge) | HIGH | `config/policies/gates.yaml` vs `knowledge/policies/gates.yaml` | Decisiones incoherentes | Canon unico + test de drift de policy | S |
| P95 `/api/v1/bots` no estable | HIGH | reportes `docs/audit/BOTS_OVERVIEW_*` | UX/ops degradada con cardinalidad alta | materializacion/agregados + tuning cache/query | M |
| Hardening HTTP backend incompleto | MEDIUM | sin `CORSMiddleware/TrustedHost` en FastAPI | Superficie expuesta por config debil | middleware + allowlist origen/host | S |
| Data quality no cableada al loader | MEDIUM | `data/quality.py` sin uso desde loader | leakage/ruido en research | gate de calidad obligatorio pre-backtest | M |
| Telemetria de ejecucion parcialmente proxy en runtime | MEDIUM | `web/app.py` (spread/slippage proxies) | KPI operativos pueden no reflejar fills reales | ingest de fills/orderbook reales | M |
| Cobertura frontend limitada (11 tests) | MEDIUM | `npm test` (2 files / 11 tests) | regresiones UI/BFF mas probables | ampliar tests smoke/e2e criticos | M |

> Lista completa y detallada por hallazgo: `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`

## 3) AUDITORIA POR DOMINIO (A-H)

- A Seguridad/AppSec: riesgo principal en secretos, fallback mock y hardening HTTP.
- B Ejecucion/Microestructura: costos y checks existen, pero runtime LIVE aun no ejecuta orden real end-to-end.
- C Research/Backtests: purged CV/CPCV/PBO/DSR implementados, pero hay caminos proxy y gap de coherencia declarativo-vs-runtime.
- D Riesgo: kill-switch y limites base operativos; falta mayor cohesion policy y controles avanzados (concentracion/correlacion).
- E Operacion/SRE: runbooks y checks protegidos presentes; faltan trazas/alertas externas completas y estabilizacion latencia bots.
- F QA: backend fuerte, frontend bajo, faltan escenarios e2e multicomponente.
- G UX/UI: buenas protecciones en acciones peligrosas; warning de layout charts pendiente.
- H Cerebro del bot: pipeline de decision existe (features -> signal -> risk -> rollout option B), pero aprendizaje ML productivo (fit/predict con drift end-to-end) queda incompleto.

## 4) PLAN DE MEJORAS

- Ver backlog completo priorizado (Top-15 + quick wins/mediano/grande): `docs/audit/AUDIT_BACKLOG_20260304.md`

## 5) VALIDACION FINAL (Go/No-Go)

- Paper -> Testnet: GO (con los gates actuales y sin habilitar LIVE).
- Testnet -> Live: NO-GO hasta cerrar must-fix de ejecucion real, secretos en pipelines y coherencia estrategia/runtime.
- Decision operativa alineada al proyecto: terminar todo no-live/testnet primero y conectar APIs LIVE al final.

## Evidencia de ejecucion en esta corrida

- `./scripts/security_scan.ps1 -Strict` -> PASS.
- `python -m pytest -q rtlab_autotrader/tests` -> PASS.
- `npm test -- --run` -> PASS (11 tests).
- `npm run lint` -> PASS.
- `npm run build` -> PASS (con warning de layout Recharts).
