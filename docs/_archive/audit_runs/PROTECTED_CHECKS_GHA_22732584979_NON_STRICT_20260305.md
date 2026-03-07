# Remote Protected Checks Evidence - Run 22732584979 (non-strict, 2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22732584979`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Config: `expect_g9=PASS`, `strict=false`
- Conclusion del workflow: `success`

## Evidencia clave del fix
- El workflow termino en `success` aun con `overall_pass=false`, confirmando que `strict=false` ahora aplica `--no-strict`.
- Campos del reporte:
  - `g9_status=WARN`
  - `g9_expected_runtime_guard=false`
  - `overall_pass=false`
  - `protected_checks_complete=true`

## Artefactos descargados
- `artifacts/gha_protected_22732584979/ops_protected_checks_gha_22732584979_20260305_191450.md`
- `artifacts/gha_protected_22732584979/ops_protected_checks_gha_22732584979_20260305_191450.json`
- `artifacts/gha_protected_22732584979/protected_checks_stdout.log`
