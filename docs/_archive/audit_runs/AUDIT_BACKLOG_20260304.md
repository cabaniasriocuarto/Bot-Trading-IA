# AUDIT_BACKLOG_20260304

Fecha: 2026-03-04
Criterio de priorizacion: Seguridad -> Ejecucion real/costos -> Anti-overfitting -> Riesgo -> Ops -> UX.

## Backlog Top-15 (accionable)

| Ticket | Area | Severidad | Que cambia | Archivos tocados | Riesgo de cambio | Tests/Validacion | Esfuerzo | Ventana |
|---|---|---|---|---|---|---|---|---|
| AP-8001 | BFF/Auth | HIGH | Fail-closed de mock en prod (sin `BACKEND_API_URL`) | `rtlab_dashboard/src/lib/security.ts`, `rtlab_dashboard/src/app/api/[...path]/route.ts`, tests | Bajo | unit tests `shouldUseMockApi` + route tests | S | Quick win (1-2 dias) |
| AP-8002 | Secrets/Ops | HIGH | Eliminar `--password` en scripts/workflows y pasar a token-first | `scripts/run_*`, `.github/workflows/remote-*.yml` | Bajo | grep guard + run remota con token | S | Quick win |
| AP-8003 | Runtime Exec | CRITICAL | Adapter de orden real (submit/cancel/status/fills) con idempotencia | `rtlab_autotrader/rtlab_core/web/app.py`, `execution/*`, store | Alto | integration testnet e2e | L | Grande (1+ mes) |
| AP-8004 | Exec Idempotency | HIGH | `client_order_id` deterministico + dedup persistente | `execution/oms.py` + capa exchange adapter + DB | Medio | retries sin duplicados | M | 1-2 semanas |
| AP-8005 | Reconciliation | HIGH | Reconciliacion activa con correccion automatica de desync | `execution/reconciliation.py`, `web/app.py` | Medio | desync inject/recover tests | M | 1-2 semanas |
| AP-8006 | Strategy Runtime | HIGH | Mapeo estricto `strategy_id -> executor`, fail-closed si falta | `src/backtest/engine.py`, `knowledge/strategies/strategies_v2.yaml`, tests | Medio | parametrized strategy tests | M | 1-2 semanas |
| AP-8007 | Policy Cohesion | HIGH | Unificar thresholds de gates (`config` vs `knowledge`) y check drift en CI | `config/policies/gates.yaml`, `knowledge/policies/gates.yaml`, script CI | Bajo | test comparador YAML | S | Quick win |
| AP-8008 | Data Quality | MEDIUM | Integrar `check_ohlcv_quality` en loader con modo estricto | `src/data/loader.py`, `data/quality.py`, tests | Medio | fixtures con gaps/duplicados | M | 1-2 semanas |
| AP-8009 | Security Hardening | MEDIUM | Middleware de seguridad backend (trusted hosts/CORS/HTTPS segun entorno) | `web/app.py`, docs deploy | Medio | integration tests headers/origin/host | S | Quick win |
| AP-8010 | Session Security | MEDIUM | Hash de token de sesion en DB + migracion ligera | `web/app.py` (sessions) + tests auth | Medio | login/me/logout regression | M | 1-2 semanas |
| AP-8011 | Performance Bots | HIGH | Materializar/agregar cache de agregados para `/api/v1/bots` | `web/app.py`, SQL indices/materialized views | Medio | benchmark remoto 10/30/100 bots | M | 1-2 semanas |
| AP-8012 | Observability | MEDIUM | Instrumentar traces (OpenTelemetry) en rutas criticas | backend + deploy config | Medio | traces visibles + latency spans | M | 1-2 semanas |
| AP-8013 | SAST CI | MEDIUM | Agregar `bandit`, `semgrep`, `CodeQL`, `Scorecard` a CI | `.github/workflows/security-ci.yml` (+ codeql workflow) | Bajo | pipelines verdes con baseline | M | 1-2 semanas |
| AP-8014 | Frontend Safety | MEDIUM | Confirmacion explicita al cambiar bots a LIVE en `Strategies` | `rtlab_dashboard/src/app/(app)/strategies/page.tsx` + tests | Bajo | UI test confirm live | S | Quick win |
| AP-8015 | Charts UX | LOW | Eliminar warnings Recharts (`minHeight/aspect`) | `rtlab_dashboard/src/app/(app)/backtests/page.tsx` | Bajo | build sin warnings + smoke visual | S | Quick win |

## Plan temporal

### Quick wins (1-2 dias)
1. AP-8001
2. AP-8002
3. AP-8007
4. AP-8009
5. AP-8014
6. AP-8015

### Mediano (1-2 semanas)
1. AP-8004
2. AP-8005
3. AP-8006
4. AP-8008
5. AP-8011
6. AP-8012
7. AP-8013
8. AP-8010

### Grande (1+ mes)
1. AP-8003

## Dependencias y orden recomendado
1. Cerrar secretos y fail-closed BFF (`AP-8001`, `AP-8002`).
2. Congelar policy unica (`AP-8007`) antes de tocar riesgo/learning.
3. Arreglar coherencia de estrategia y calidad de datos (`AP-8006`, `AP-8008`).
4. Atacar runtime real e idempotencia/reconcile (`AP-8003`, `AP-8004`, `AP-8005`).
5. Estabilizar performance/observabilidad (`AP-8011`, `AP-8012`).
6. Expandir seguridad CI y UX safety (`AP-8013`, `AP-8014`, `AP-8015`).

## Proximo paso inmediato
- Ejecutar AP-8001 + AP-8002 en una rama tecnica corta, con commit por AP y evidencia de tests por commit.
