# Staging Smoke Evidence - AP-BOT-1023 (2026-03-05)

Fuente: corrida local contra staging con script dedicado de smoke no-live.

- Frontend URL: `https://bot-trading-ia-staging.vercel.app/login`
- Backend URL: `https://bot-trading-ia-staging.up.railway.app`
- Script: `scripts/staging_smoke_report.py`
- Corrida: `python scripts/staging_smoke_report.py --report-prefix artifacts/staging_smoke_ghafree`

## Resultado
- `front_login_status_code=200`
- `health_ok=true`
- `health_mode=paper`
- `runtime_ready_for_live=false`
- `overall_pass=true`

## Observaciones
- `storage_persistent=false` en staging (esperado con `RTLAB_USER_DATA_DIR=/tmp/...`).
- Checks autenticados (`/api/v1/bots`) en esta corrida local: `NO_EVIDENCE_NO_SECRET` (no habia `RTLAB_AUTH_TOKEN` ni `RTLAB_ADMIN_PASSWORD` en entorno local).
- Para validacion autenticada completa de checks protegidos se mantiene evidencia remota:
  - `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.

## Artefactos
- `artifacts/staging_smoke_ghafree_20260305_190031.json`
- `artifacts/staging_smoke_ghafree_20260305_190031.md`
