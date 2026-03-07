# Remote Protected Checks Evidence - STAGING Run 22739570506 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22739570506`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Config: `strict=true`, `expect_g9=WARN`, `username=Wadmin`
- Conclusion: `failure` (por checks operativos, no por auth)

## Campos canonicos
- `overall_pass=false`
- `protected_checks_complete=true`
- `g10_status=WARN`
- `g9_status=WARN` (esperado en no-live)
- `breaker_ok=false`
- `internal_proxy_status_ok=true`

## Causa observada
- `health_ok=true` (backend responde bien)
- `storage_persistent=false` -> `g10_status=WARN`
- `breaker_status=NO_DATA` con `strict_mode=true` -> `breaker_ok=false`
- Sin errores de endpoint (`endpoint_errors=none`)

## Artefactos
- `artifacts/protected_checks_gha_22739570506/ops_protected_checks_gha_22739570506_20260305_222216.md`
- `artifacts/protected_checks_gha_22739570506/ops_protected_checks_gha_22739570506_20260305_222216.json`
- `artifacts/protected_checks_gha_22739570506/protected_checks_stdout.log`
- `artifacts/protected_checks_gha_22739570506/protected_checks_summary_22739570506.json`
