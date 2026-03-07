# Remote Protected Checks (Staging) - Run 22732410544 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre `main`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22732410544`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Inputs: `strict=false`, `expect_g9=WARN`, `window_hours=24`
- Conclusion: `failure`

## Evidencia del fallo
- El run en `main` aun ejecuto fallback legacy con `--password` (CLI) al no tener `RTLAB_AUTH_TOKEN`.
- Login remoto en staging devolvio `401 Invalid credentials`.
- No se genero reporte `.md/.json` de checks; solo `protected_checks_stdout.log`.

## Accion correctiva aplicada en rama tecnica
- `/.github/workflows/remote-protected-checks.yml`:
  - agregado `--no-strict` cuando `strict=false` (antes quedaba en estricto por default del script).
  - eliminado fallback CLI de password (`--password`) para alinear hardening.

## Estado
- Resultado staging remoto autenticado: `NO EVIDENCIA PASS` hasta re-run con workflow corregido y credenciales validas para staging.
