# AP-0001 / AP-0002 - Runtime Contract v1 + Criterio G9

Fecha: 2026-03-04  
Rama tecnica: `feature/runtime-contract-v1`

## Alcance (estricto)

Este documento congela el contrato base del runtime para evitar retrabajo en las siguientes fases.

- AP-0001: definir `RuntimeSnapshot` canonico.
- AP-0002: definir criterio exacto de `G9_RUNTIME_ENGINE_REAL`.

No incluye implementar el runtime real completo (OMS/reconciliacion/ejecucion real): eso queda para Bloque 1.

## RuntimeSnapshot v1 (canonico)

Version: `runtime_snapshot_v1`

Campos:
1. `contract_version`: string.
2. `runtime_engine`: `real | simulated`.
3. `telemetry_source`: `runtime_loop_v1 | synthetic_v1`.
4. `runtime_loop_alive`: bool.
5. `executor_connected`: bool.
6. `reconciliation_ok`: bool.
7. `runtime_heartbeat_at`: ISO8601 UTC.
8. `runtime_last_reconcile_at`: ISO8601 UTC.
9. `heartbeat_age_sec`: int|null.
10. `heartbeat_max_age_sec`: int.
11. `reconciliation_age_sec`: int|null.
12. `reconciliation_max_age_sec`: int.
13. `checks`: objeto bool por check.
14. `missing_checks`: lista de checks faltantes.
15. `ready_for_live`: bool.
16. `evaluated_at`: ISO8601 UTC.

Checks canonicos (`checks`):
1. `engine_real`
2. `telemetry_real`
3. `runtime_loop_alive`
4. `executor_connected`
5. `reconciliation_ok`
6. `heartbeat_fresh`
7. `reconciliation_fresh`

## Criterio exacto G9 (AP-0002)

`G9_RUNTIME_ENGINE_REAL=PASS` solo si `RuntimeSnapshot.ready_for_live=true`.

Definicion:
- `ready_for_live = all(checks.values())`.

Reglas de status por modo:
1. `mode=live`
   - `PASS` si `ready_for_live=true`.
   - `FAIL` si `ready_for_live=false`.
2. `mode=paper|testnet`
   - `PASS` si `ready_for_live=true`.
   - `WARN` si `ready_for_live=false`.

## Parametros operativos v1

Variables:
1. `RUNTIME_HEARTBEAT_MAX_AGE_SEC` (default `90`)
2. `RUNTIME_RECONCILIATION_MAX_AGE_SEC` (default `120`)

## Implementacion base incluida en esta etapa

1. `RuntimeSnapshot` expuesto en:
   - `/api/v1/status` (`runtime_snapshot` y `runtime.*` extendido)
   - `/api/v1/health` (metadata de contrato)
   - `/api/v1/execution/metrics` (metadata de contrato)
2. G9 ahora evalua el criterio anterior y publica detalles en `details.runtime_contract`.

## Fuera de alcance en AP-0001/AP-0002

1. Adapter de exchange real y wiring OMS/reconciliacion completo.
2. Cambio de decisiones de rollout para bloquear fases por telemetry source (AP-2003).
3. Refactor masivo de endpoints o frontend.
