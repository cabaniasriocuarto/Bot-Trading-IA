# Vercel Staging Runbook (Frontend)

Fecha de validacion: 2026-03-04

## Objetivo
Publicar frontend online para pruebas, conectado al backend staging de Railway y con NO-LIVE forzado.

## Estado actual validado
- Project (staging): `bot-trading-ia-staging`
- URL publica: `https://bot-trading-ia-staging.vercel.app`
- Login route: `GET /login` -> `200`

## Variables usadas en deploy staging
- `USE_MOCK_API=false`
- `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=false`
- `BACKEND_API_URL=https://bot-trading-ia-staging.up.railway.app`
- `NEXT_PUBLIC_BACKEND_URL=https://bot-trading-ia-staging.up.railway.app`
- `APP_ENV=staging`
- `LIVE_TRADING_ENABLED=false`
- `AUTH_SECRET=<secret>`
- `ADMIN_USERNAME=<user>`
- `ADMIN_PASSWORD=<secret>`
- `VIEWER_USERNAME=<user>`
- `VIEWER_PASSWORD=<secret>`

## Deploy CLI (ejemplo)
Desde repo raiz:
```bash
vercel deploy --yes --logs \
  -e USE_MOCK_API=false \
  -e ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=false \
  -e BACKEND_API_URL=https://bot-trading-ia-staging.up.railway.app \
  -e NEXT_PUBLIC_BACKEND_URL=https://bot-trading-ia-staging.up.railway.app \
  -e APP_ENV=staging \
  -e LIVE_TRADING_ENABLED=false
```

## Verificacion
```bash
curl -I https://bot-trading-ia-staging.vercel.app/login
```

## Rollback (Vercel)
1. Listar deployments del proyecto:
```bash
vercel ls bot-trading-ia-staging
```
2. Rollback a deployment anterior:
```bash
vercel rollback <deployment-url-o-id> --yes
```
3. Confirmar endpoint `/login` y flujo de auth.

## Restriccion
- El frontend staging no debe activar LIVE.
- Si backend no-live cambia a `runtime_ready_for_live=true` por error, detener promotion y revalidar gates.
