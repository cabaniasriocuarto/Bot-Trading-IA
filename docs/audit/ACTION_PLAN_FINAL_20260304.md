# ACTION PLAN FINAL - Programa Integral + Bot - 2026-03-04

Este plan consolida la reparacion de hallazgos del programa integral y del cerebro del bot, con orden de implementacion para evitar retrabajo.

Referencia de hallazgos: `docs/audit/FINDINGS_MASTER_20260304.md`.

## Principio anti-retrabajo

No modificar capas aguas arriba hasta cerrar contratos base:
1. Contrato de runtime real (`status`, `execution metrics`, `risk snapshot`) primero.
2. Gating runtime (G9 y rollout phase-eval) despues.
3. UI/E2E al final de estabilizar contratos.

## Orden final de ejecucion (bloques)

### BLOQUE 0 - Congelamiento de contratos (1-2 dias)
- Objetivo: definir interfaces estables para evitar reescribir backend/frontend dos veces.
- Tickets:
  - AP-0001: Especificar `RuntimeSnapshot` canonico (`status`, `execution`, `risk`, `telemetry_source`).
  - AP-0002: Especificar criterio exacto de `G9_RUNTIME_ENGINE_REAL=PASS`.
- Hallazgos cubiertos:
  - FM-EXEC-001, FM-EXEC-002, FM-EXEC-005.
- Entregables:
  - doc tecnico corto en `docs/runbooks/` o `docs/audit/`.

### BLOQUE 1 - Runtime real no-live (prioridad maxima) (1-2 semanas)
- Objetivo: cerrar la mayor deuda tecnica que hoy bloquea no-live robusto y live futuro.
- Tickets:
  - AP-1001: Cablear `OMS + Reconciliation + RiskEngine + KillSwitch` al runtime web.
  - AP-1002: Reemplazar payload sintetico de `build_status_payload`.
  - AP-1003: Reemplazar payload sintetico de `build_execution_metrics_payload`.
  - AP-1004: Exponer `telemetry_source` y fail-closed si es sintetico.
- Hallazgos cubiertos:
  - FM-EXEC-001, FM-EXEC-002, FM-EXEC-005, FM-RISK-002.
- Dependencias:
  - BLOQUE 0 cerrado.
- Validacion minima:
  - integration tests de ciclo `start -> submit -> partial fill -> reconcile -> stop`.

### BLOQUE 2 - Gates y rollout sobre datos reales (3-5 dias)
- Objetivo: que la toma de decisiones de rollout dependa solo de evidencia real.
- Tickets:
  - AP-2001: Cambiar `G9` para exigir heartbeat runtime real + reconciliacion reciente.
  - AP-2002: `breaker_events`: `NO_DATA` => `ok=false` en modo estricto.
  - AP-2003: bloquear `evaluate_*_soak`/`evaluate_live_phase` si `telemetry_source != real`.
- Hallazgos cubiertos:
  - FM-EXEC-002, FM-EXEC-003, FM-EXEC-004.
- Dependencias:
  - BLOQUE 1 cerrado.

### BLOQUE 3 - Hardening quant/learning (5-10 dias)
- Objetivo: subir robustez anti-overfitting y trazabilidad de recomendacion.
- Tickets:
  - AP-3001: implementar Purged CV + embargo en camino learning/research rapido.
  - AP-3002: implementar CPCV real en camino learning/research.
  - AP-3003: eliminar fallback silencioso de `_learning_eval_candidate` (fail explicito).
  - AP-3004: separar `anti_proxy` y `anti_advanced` en salida de research.
  - AP-3005: compare fail-closed cuando feature set sea `orderflow_unknown`.
  - AP-3006: exigir `strict_strategy_id=true` en research/promotion no-demo.
- Hallazgos cubiertos:
  - FM-QUANT-002, FM-QUANT-004, FM-QUANT-005, FM-QUANT-006, FM-QUANT-007.
- Dependencias:
  - BLOQUE 0 cerrado.
  - BLOQUE 1 recomendado (para coherencia de pipeline end-to-end).

### BLOQUE 4 - Seguridad CI y gobierno (2-4 dias)
- Objetivo: hacer bloqueante la seguridad de forma reproducible.
- Tickets:
  - AP-4001: versionar/pushear `/.github/workflows/security-ci.yml`.
  - AP-4002: configurar branch protection con required checks de seguridad.
  - AP-4003: migrar lockout/rate-limit de login a backend compartido multi-instancia.
- Hallazgos cubiertos:
  - FM-SEC-002, FM-SEC-004.
- Dependencias:
  - ninguna tecnica fuerte, se puede ejecutar en paralelo con BLOQUE 3.

### BLOQUE 5 - QA/SRE de cierre no-live (3-7 dias)
- Objetivo: cerrar riesgo operacional antes de tocar LIVE.
- Tickets:
  - AP-5001: suite E2E critica (`login -> backtest -> validate -> promote -> rollout`).
  - AP-5002: tests de caos/recovery de runtime (exchange down, reconnect, desync).
  - AP-5003: alertas operativas minimas (drift, slippage anomalo, api errors, breaker integrity).
- Hallazgos cubiertos:
  - FM-QA-001, FM-QA-002, FM-SRE-002.
- Dependencias:
  - BLOQUE 1 y BLOQUE 2 cerrados.

### BLOQUE 6 - Trazabilidad documental y bibliografia (1-2 dias)
- Objetivo: reproducibilidad final de auditoria y operacion.
- Tickets:
  - AP-6001: registrar decision final de cada hallazgo en `docs/truth/*`.
  - AP-6002: definir politica formal de acceso a `biblio_raw` local y versionado de metadatos.
- Hallazgos cubiertos:
  - FM-DOC-001.
- Dependencias:
  - ninguna tecnica fuerte.

## Matriz de dependencias (resumen)

1. BLOQUE 0 -> BLOQUE 1 -> BLOQUE 2 -> BLOQUE 5.
2. BLOQUE 3 puede correr en paralelo parcial con BLOQUE 4, pero se valida junto a BLOQUE 5.
3. BLOQUE 6 al final de cada sprint y cierre final.

## Riesgos de retrabajo a evitar

1. No tocar UI de ejecucion/rollout antes de cerrar BLOQUE 1 y 2.
2. No ajustar thresholds de gates en frontend si no se fijo source canonico runtime.
3. No habilitar LIVE ni canary real antes de cerrar BLOQUE 1, 2, 4 y 5.

## Criterio de salida (NO-LIVE listo)

Se considera "no-live listo para conectar APIs live al final" cuando:
1. FM-EXEC-001/002/003/004/005 en `CERRADO`.
2. FM-QUANT-004/005/007 en `CERRADO` o `MITIGADO` con fail-closed documentado.
3. FM-SEC-004 en `CERRADO`.
4. FM-QA-001 en `CERRADO`.
5. `docs/truth/SOURCE_OF_TRUTH.md`, `CHANGELOG.md`, `NEXT_STEPS.md` actualizados con evidencia de cada bloque.

## Proximo paso inmediato recomendado

1. Ejecutar BLOQUE 0 en una rama tecnica (`feature/runtime-contract-v1`) y cerrar AP-0001/AP-0002 antes de tocar mas codigo operativo.
