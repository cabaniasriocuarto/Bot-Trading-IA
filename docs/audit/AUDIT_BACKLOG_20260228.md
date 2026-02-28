# AUDIT BACKLOG (Tickets) - 2026-02-28

## Criterio
- Prioridad de ejecución: Seguridad -> Ejecución/costos -> Anti-overfitting -> Riesgo -> Operación -> UX/QA.
- Tamaño: S (1-2 días), M (3-5 días), L (>1 semana).

| Ticket | Prioridad | Severidad | Objetivo | Archivos clave | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| T-SEC-001 | P0 | CRITICAL | Mantener trust interno solo con `INTERNAL_PROXY_TOKEN` y runbook de rotación | `rtlab_autotrader/rtlab_core/web/app.py`, `rtlab_dashboard/src/app/api/[...path]/route.ts`, `rtlab_dashboard/src/lib/events-stream.ts`, `docs/SECURITY.md` | S | DONE |
| T-SEC-002 | P0 | HIGH | Rate-limit login backend + lockout por IP+user | `rtlab_autotrader/rtlab_core/web/app.py`, `rtlab_autotrader/tests/test_web_live_ready.py` | S | DONE |
| T-SEC-003 | P1 | MEDIUM | Rate-limit general API (incl. endpoints costosos) | `rtlab_autotrader/rtlab_core/web/app.py` | M | TODO |
| T-SEC-004 | P1 | MEDIUM | Integrar gitleaks/pip-audit en CI bloqueante | `scripts/security_scan.sh`, `rtlab_autotrader/.github/workflows/ci.yml` | S | TODO |
| T-EXEC-001 | P0 | HIGH | Implementar runtime paper/testnet real (BrokerAdapter) | `rtlab_autotrader/rtlab_core/web/app.py`, módulo runtime nuevo | L | TODO |
| T-EXEC-002 | P1 | MEDIUM | Reemplazar métricas de ejecución sintéticas por reales | `rtlab_autotrader/rtlab_core/web/app.py` | M | TODO |
| T-QUANT-001 | P0 | CRITICAL | Ejecutar lógica por `strategy_id` (sin engine único) | `rtlab_autotrader/rtlab_core/src/backtest/engine.py`, wiring en `web/app.py` | L | TODO |
| T-QUANT-002 | P0 | HIGH | Aplicar gate `min_trades_per_symbol` real | `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py` | S | TODO |
| T-CONF-001 | P0 | HIGH | Unificar canonicidad de gates (`config` sobre `knowledge`) en learning/runtime/UI | `rtlab_autotrader/rtlab_core/learning/knowledge.py`, `rtlab_autotrader/rtlab_core/web/app.py`, docs truth | S | TODO |
| T-RISK-001 | P1 | HIGH | Cablear `risk_policy.yaml` a runtime real pre/post trade | `config/policies/risk_policy.yaml`, runtime broker | M | TODO |
| T-SRE-001 | P1 | MEDIUM | Scripts + runbook de backup/restore | `scripts/*`, `docs/runbooks/*` | M | TODO |
| T-QA-001 | P2 | MEDIUM | E2E frontend flujo crítico | `rtlab_dashboard` + workflow CI | M | TODO |
| T-BIB-001 | P2 | MEDIUM | Habilitar extracción PDF->TXT para verificación bibliográfica automática | `scripts/biblio_extract.py`, entorno local con `pypdf` | S | TODO |

## Definition of Done por ticket crítico

### T-EXEC-001
- Broker adapter paper/testnet operativo.
- Órdenes/fills/posiciones persistidas y reconciliables.
- `kill-switch` ejecuta cancel/flatten en sim/testnet.

### T-QUANT-001
- Diferentes `strategy_id` producen señales distintas en dataset idéntico.
- Si `strategy_id` no tiene implementación: fail-closed.

### T-QUANT-002
- Gate falla cuando cualquier símbolo OOS está bajo el mínimo.
- Bloqueo de promoción cuando no cumple.

### T-CONF-001
- `SOURCE_OF_TRUTH` define canónica única.
- Endpoints `config/learning`, `config/policies` y GateEvaluator devuelven thresholds consistentes.
