# FINDINGS DECISION MATRIX - 2026-03-04

Matriz de decision final por hallazgo del tramo no-live.

| Finding | Estado | Decision de tramo |
|---|---|---|
| FM-SEC-001 | CERRADO | Mantener validacion estricta de `x-rtlab-proxy-token` y logging de spoof. |
| FM-SEC-002 | CERRADO | Lockout/rate-limit migrado a backend compartido (`sqlite`) con fallback `memory`. |
| FM-SEC-003 | CERRADO | Rate limit general/expensive operativo con cobertura de tests. |
| FM-SEC-004 | MITIGADO | Workflow `security` + branch protection aplicados; pendiente corrida verde inicial post-fix. |
| FM-EXEC-001 | MITIGADO | Runtime fail-closed + evidencia exchange aplicada; falta loop broker/exchange full end-to-end. |
| FM-EXEC-002 | CERRADO | `G9` ahora sincroniza runtime y exige evidencia exchange + freshness checks. |
| FM-EXEC-003 | MITIGADO | `breaker_events` en `strict=true` fail-closed; riesgo residual en consumidores legacy `strict=false`. |
| FM-EXEC-004 | MITIGADO | `evaluate-phase` bloquea telemetry sintetica; cierre total depende de runtime real. |
| FM-EXEC-005 | MITIGADO | Wiring reforzado con reconciliacion `openOrders`; pendiente submit/fills reales del broker. |
| FM-QUANT-001 | MITIGADO | Dispatch robusto con fallback controlado; residual en modo no estricto. |
| FM-QUANT-002 | MITIGADO | `strict_strategy_id` reforzado en promotion/research no-demo; mantener vigilancia de defaults heredados. |
| FM-QUANT-003 | CERRADO | `min_trades_per_symbol` enforce activo en gates de research. |
| FM-QUANT-004 | CERRADO | Purged CV + CPCV implementados y validados. |
| FM-QUANT-005 | CERRADO | Eliminado fallback silencioso en evaluator (fail-closed). |
| FM-QUANT-006 | CERRADO | Separacion `anti_proxy` vs `anti_advanced` con alias legacy. |
| FM-QUANT-007 | CERRADO | Compare fail-closed con `orderflow_feature_set` unknown. |
| FM-QUANT-008 | ABIERTO | Pipeline ML formal de entrenamiento sigue pendiente (fase 2+). |
| FM-RISK-001 | CERRADO | Opcion B sin auto-live mantenida fail-closed. |
| FM-RISK-002 | MITIGADO | Runtime ya aplica policy canonica (`risk_policy.yaml`) en limites/hard-kill; falta broker loop real completo. |
| FM-RISK-003 | CERRADO | Risk profile default de learning ahora se deriva desde `config/policies/risk_policy.yaml`. |
| FM-RISK-004 | MITIGADO | Fuente canonica `config/policies`; fallback `knowledge` sigue como compatibilidad controlada. |
| FM-SRE-001 | CERRADO | Backup/restore drill validado con hash y runbook. |
| FM-SRE-002 | MITIGADO | Alertas operativas minimas agregadas en `/api/v1/alerts`; falta monitoreo externo para canary/live. |
| FM-QA-001 | CERRADO | Suite E2E critica backend incorporada. |
| FM-QA-002 | CERRADO | Tests de chaos/recovery runtime incorporados. |
| FM-DOC-001 | MITIGADO | Politica formal de `biblio_raw` y metadatos definida; raw local sigue no versionado por policy. |
