# Remote Protected Checks (Staging) - Run 22733461982 (2026-03-05)

Fuente: GitHub Actions `Remote Protected Checks (GitHub VM)` sobre rama tecnica `chore/audit-cleanroom-20260304` (post AP-BOT-1027).

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22733461982`
- Base URL: `https://bot-trading-ia-staging.up.railway.app`
- Config: `strict=false`, `expect_g9=WARN`
- Conclusion: `failure`

## Resultado esperado del hardening (PASS de diseño, FAIL operacional)
- Falla en step `Validate auth configuration` con mensaje explicito:
  - `Missing staging secrets: define RTLAB_STAGING_AUTH_TOKEN or RTLAB_STAGING_ADMIN_PASSWORD.`
- Ya no intenta login con credenciales de produccion y evita `401` tardio por fallback cruzado.

## Acción requerida
- Cargar uno de estos secretos en GitHub repo:
  - `RTLAB_STAGING_AUTH_TOKEN`, o
  - `RTLAB_STAGING_ADMIN_PASSWORD`
- Re-ejecutar workflow y registrar evidencia del run exitoso.
