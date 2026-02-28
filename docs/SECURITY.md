# Seguridad Operativa (RTLAB Bot-Trading-IA)

Fecha de actualización: 2026-02-28

## Alcance y objetivo
- Alcance: `rtlab_autotrader` (backend FastAPI), `rtlab_dashboard` (BFF Next.js) y sus integraciones.
- Objetivo: proteger autenticación/autorización, secretos, superficie API y operación paper/testnet.
- Restricción explícita: este repo **no** habilita trading LIVE real sin gates y aprobación humana.

## Threat model mínimo
- Actores:
  - Operador legítimo (admin/viewer).
  - Usuario no autenticado en internet.
  - Atacante con acceso parcial a frontend/BFF.
- Activos críticos:
  - Credenciales (`AUTH_SECRET`, exchange keys, `INTERNAL_PROXY_TOKEN`).
  - Endpoints admin (`/api/v1/bot/*`, `/api/v1/bots/*`, rollout/promotion).
  - Integridad de gates y reportes de riesgo.
- Fronteras de confianza:
  - Navegador → BFF (`rtlab_dashboard`).
  - BFF → Backend (`rtlab_autotrader`).
  - Backend → exchange/API externas.

## Controles vigentes
- Credenciales default bloqueadas en producción:
  - backend falla en boot si `NODE_ENV=production` y hay defaults o `AUTH_SECRET` débil.
- Proxy interno endurecido:
  - backend solo acepta `x-rtlab-role/x-rtlab-user` si llega `x-rtlab-proxy-token` válido.
- Rate-limit login backend:
  - `10` intentos / `10` min por `IP+user`.
  - lockout `30` min al superar `20` fallos acumulados.
- Sesiones backend con expiración (tabla `sessions`).
- Eventos de breaker persistidos por `bot_id + mode` en `breaker_events`.

## Configuración obligatoria
- Backend (`rtlab_autotrader/.env` o secrets manager):
  - `AUTH_SECRET` (>=32 chars)
  - `ADMIN_USERNAME`, `ADMIN_PASSWORD`
  - `VIEWER_USERNAME`, `VIEWER_PASSWORD`
  - `INTERNAL_PROXY_TOKEN` (>=32 chars, compartido con BFF)
- BFF (`rtlab_dashboard/.env`):
  - `INTERNAL_PROXY_TOKEN` (mismo valor que backend)
  - `BACKEND_API_URL`

## Checklist pre-deploy
- [ ] `AUTH_SECRET` robusto y rotado.
- [ ] Credenciales default reemplazadas.
- [ ] `INTERNAL_PROXY_TOKEN` configurado en backend y BFF.
- [ ] Exchange keys con mínimo privilegio (`Read + Trade`, nunca `Withdraw`).
- [ ] IP allowlist/Zero Trust aplicado al backend si está público.
- [ ] `scripts/security_audit.sh` ejecutado y revisado.
- [ ] Gates LIVE en PASS antes de cualquier canary.

## OWASP (mapa rápido)
- API2 Broken Authentication: protegido con credenciales fuertes + token interno BFF→backend.
- API5 Broken Function Level Authorization: endpoints críticos usan `require_admin`.
- API8 Security Misconfiguration: validaciones de `AUTH_SECRET`/defaults y checklist de despliegue.
- API4 Unrestricted Resource Consumption: rate-limit login implementado (faltan límites generales en toda API).

## Auditoría de dependencias y secretos
Comandos recomendados:
```bash
bash scripts/security_audit.sh
python -m pip_audit -r requirements-runtime.txt
python -m pip_audit -r requirements-research.txt
gitleaks detect --source . --verbose
```

Si no hay tooling instalado:
- `pip-audit`: `python -m pip install pip-audit`
- `gitleaks`: instalar binario oficial en CI/runner

## Notas operativas
- Si `INTERNAL_PROXY_TOKEN` no está configurado, el BFF falla cerrado hacia backend.
- El modo LIVE sigue bloqueado por `G9_RUNTIME_ENGINE_REAL` y gates de rollout.
