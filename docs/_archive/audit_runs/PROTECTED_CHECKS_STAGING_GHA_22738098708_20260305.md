# Remote Protected Checks Evidence - STAGING Run 22738098708 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22738098708`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Config: `strict=true`, `expect_g9=WARN`, `username=Wadmin`
- Conclusion: `failure`

## Resultado
- El workflow falla en `Run protected checks` con:
  - `ERROR: Login fallo: 401 {"detail":"Invalid credentials"}`
- No se genero JSON del reporte (`ops_protected_checks_gha_*.json`) por fallo temprano de autenticacion.

## Campos canonicos
- `overall_pass=NO_EVIDENCE`
- `protected_checks_complete=NO_EVIDENCE`
- `g10_status=NO_EVIDENCE`
- `g9_status=NO_EVIDENCE`
- `breaker_ok=NO_EVIDENCE`
- `internal_proxy_status_ok=NO_EVIDENCE`

## Artefactos
- `artifacts/protected_checks_gha_22738098708/protected_checks_stdout.log` (vacio)
- `artifacts/protected_checks_gha_22738098708/protected_checks_summary_22738098708.json`

## Accion requerida
1. Verificar en Railway staging los valores activos:
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
2. Alinear GitHub secret:
   - `RTLAB_STAGING_ADMIN_PASSWORD` debe ser exactamente `ADMIN_PASSWORD` de staging.
3. Re-ejecutar workflow remoto con `username` igual a `ADMIN_USERNAME` real de staging.
