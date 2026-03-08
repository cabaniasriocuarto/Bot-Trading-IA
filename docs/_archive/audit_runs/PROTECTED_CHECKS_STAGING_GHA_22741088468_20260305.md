# Remote Protected Checks Evidence - STAGING Run 22741088468 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22741088468`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Config: `strict=true`, `expect_g9=WARN`, `username=Wadmin`
- Conclusion: `success`

## Campos canonicos
- `overall_pass=true`
- `protected_checks_complete=true`
- `g10_status=WARN`
- `g9_status=WARN` (esperado en no-live)
- `breaker_ok=true`
- `internal_proxy_status_ok=true`

## Detalle relevante
- `allow_staging_warns_applied=true` en reporter de checks:
  - acepta `G10=WARN` en staging no-live;
  - acepta `breaker_status=NO_DATA` en staging no-live.
- Estado de salud:
  - `health_ok=true`
  - `storage_persistent=false` (se mantiene como warning informativo en staging)
- Sin errores de endpoint (`endpoint_errors=none`)

## Artefactos
- `artifacts/protected_checks_gha_22741088468/ops_protected_checks_gha_22741088468_20260305_232057.md`
- `artifacts/protected_checks_gha_22741088468/ops_protected_checks_gha_22741088468_20260305_232057.json`
- `artifacts/protected_checks_gha_22741088468/protected_checks_stdout.log`
- `artifacts/protected_checks_gha_22741088468/protected_checks_summary_22741088468.json`
