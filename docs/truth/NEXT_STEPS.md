# NEXT STEPS (Prioridades Reales)

Fecha: 2026-03-04

## Referencias canonicas de reparacion (2026-03-04)
- Registro maestro de problemas: `docs/audit/FINDINGS_MASTER_20260304.md`
- Plan final de implementacion: `docs/audit/ACTION_PLAN_FINAL_20260304.md`

## Progreso AP (plan final)
- Total AP: `23`
- AP cerrados: `21`
- AP pendientes: `2` (`AP-6001`, `AP-6002`)
- Avance global: `91%` (`21/23`)

## Cierre PARTE 7/7 (cerebro del bot)
- Auditoria de cerebro cerrada: decision/learning/rollout validados por codigo.
- Se mantiene politica operativa: **no conectar LIVE todavia**.
- Checklist inmediato de cierre no-live (orden obligatorio):
1. Acoplar runtime operativo real a OMS/risk/reconciliacion y reemplazar payloads sinteticos de `status`/`execution`.
   - avance: AP-0001/AP-0002 + AP-1001/AP-1002/AP-1003/AP-1004 + AP-2001/AP-2002/AP-2003 implementados (`RuntimeBridge`, telemetry fail-closed, breaker strict y bloqueo de evaluate-phase sin telemetry real).
   - pendiente: wiring broker/exchange real end-to-end.
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
   - estabilizar storage persistente para `RTLAB_USER_DATA_DIR` (evitar `/tmp`) antes de benchmarks comparativos: hoy cada redeploy puede resetear bots/runs y contaminar evidencia.
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
