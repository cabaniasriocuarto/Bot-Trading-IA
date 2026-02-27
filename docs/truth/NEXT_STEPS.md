# NEXT STEPS (Prioridades Reales)

Fecha: 2026-02-26

## Prioridad 1 (RC operativo)
1. Deploy frontend/backend y validacion visual completa de UI `Research-first`
2. Validar `Settings -> Diagnostico` (WS/Exchange)
3. Validar `Backtests / Runs -> Validate -> Promote -> Rollout / Gates`
4. Resolver infraestructura testnet/live (si reaparece bloqueo de red/egress)
5. Validar Modo Bestia fase 1 en produccion (cola, budget governor, stop-all, resume)

## Prioridad 2 (UX / producto)
1. Virtualizacion adicional en tablas grandes restantes (D2 comparador ya virtualizado)
2. Deep Compare avanzado (heatmap mensual, rolling Sharpe, distribucion retornos)
3. Componente reutilizable unico para empty states / CTA
4. Tooltips consistentes en acciones de runs (rerun/clone/export cuando existan)

## Prioridad 3 (robustez / automatizacion)
1. Smoke/E2E frontend automatizados (runs table, paginacion, filtros, empty states)
2. Integrar `deps_check` + `security_audit` a CI
3. PBO/DSR completos (no solo proxy/fail-closed) en research masivo
4. Fee/Funding providers reales con snapshots persistentes y fetch live por simbolo/exchange
5. Order Flow L1 full (trade tape/BBO real) sobre VPIN proxy actual

## Prioridad 4 (nice-to-have)
1. UI de experimentos MLflow (capability)
2. SBOM firmado por release
3. Dashboards externos para canary live (Prometheus/Grafana)
4. Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)
