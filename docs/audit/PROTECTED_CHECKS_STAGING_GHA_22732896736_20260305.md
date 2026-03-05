# Remote Protected Checks (Staging) - Run 22732896736 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22732896736`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Config: `strict=false`, `expect_g9=WARN`
- Conclusion: `failure`

## Diagnostico confirmado
- El workflow ya no usa `--password` por CLI (fix AP-BOT-1025/1026 aplicado).
- Secrets presentes en run:
  - `RTLAB_ADMIN_PASSWORD`: configurado
  - `RTLAB_AUTH_TOKEN`: vacio
  - `RTLAB_STAGING_ADMIN_PASSWORD`: vacio
  - `RTLAB_STAGING_AUTH_TOKEN`: vacio
- Resultado:
  - el workflow hizo fallback a `RTLAB_ADMIN_PASSWORD` (global) y login staging devolvio `401 Invalid credentials`.

## Accion requerida para staging
- Definir al menos uno:
  - `RTLAB_STAGING_AUTH_TOKEN`, o
  - `RTLAB_STAGING_ADMIN_PASSWORD`
- Luego rerun del workflow para validar checks protegidos en staging con credenciales correctas.
