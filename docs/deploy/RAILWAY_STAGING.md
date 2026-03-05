# Railway Staging Runbook (Backend)

Fecha de validacion: 2026-03-04

## Objetivo
Levantar backend online en entorno `staging` con guard-rails NO-LIVE.

## Estado actual validado
- Project: `Bot-Trading-IA`
- Environment: `staging`
- Service: `Bot-Trading-IA`
- URL publica staging: `https://bot-trading-ia-staging.up.railway.app`
- Health check:
  - `GET /api/v1/health` -> `ok=true`
  - `mode=paper`
  - `runtime_ready_for_live=false`

## Variables minimas (staging)
- `APP_ENV=staging`
- `MODE=paper` (o `testnet` si se habilita explicitamente)
- `TRADING_MODE=paper`
- `LIVE_TRADING_ENABLED=false`
- `KILL_SWITCH_ENABLED=true`
- `EXCHANGE_NAME=binance`
- `AUTH_SECRET=<secret>`
- `INTERNAL_PROXY_TOKEN=<secret>`
- `ADMIN_USERNAME=<user>`
- `ADMIN_PASSWORD=<secret>`
- `VIEWER_USERNAME=<user>`
- `VIEWER_PASSWORD=<secret>`
- `RTLAB_CONFIG_PATH=/app/rtlab_config.yaml.example`
- `RTLAB_USER_DATA_DIR=/tmp/rtlab_user_data` (staging efimero)
- `RAILWAY_DOCKERFILE_PATH=docker/Dockerfile`

Nota:
- Para persistencia real en staging, montar volumen y usar `/data/rtlab_user_data`.
- Validacion 2026-03-05:
  - en este servicio, rutas con volumen (`/data/...` y `/app/user_data`) provocaron `sqlite3.OperationalError: unable to open database file` por permisos;
  - rollback aplicado a `RTLAB_USER_DATA_DIR=/tmp/rtlab_user_data` para mantener disponibilidad.

## Comandos usados (CLI)
```bash
npx @railway/cli project link -p "Bot-Trading-IA" -e staging -s "Bot-Trading-IA"
npx @railway/cli variable set ... -e staging -s d92fdf65-10e6-4d2c-a303-f778f02ef3e4
npx @railway/cli up rtlab_autotrader --path-as-root -p 22ef7b88-aa38-4d1d-9cfc-f8e6bf03889a -e staging -s d92fdf65-10e6-4d2c-a303-f778f02ef3e4 -d
npx @railway/cli domain -s d92fdf65-10e6-4d2c-a303-f778f02ef3e4 --json
```

## Verificacion operativa
```bash
curl https://bot-trading-ia-staging.up.railway.app/api/v1/health
```

Esperado:
- `ok=true`
- `mode=paper` o `testnet`
- `runtime_ready_for_live=false`

## Rollback (Railway)
1. Listar deployments:
```bash
npx @railway/cli deployment list -e staging -s d92fdf65-10e6-4d2c-a303-f778f02ef3e4 --json
```
2. Revertir ultimo deploy:
```bash
npx @railway/cli down -e staging -s d92fdf65-10e6-4d2c-a303-f778f02ef3e4 -y
```
3. Validar `health` nuevamente.

## Restriccion
- LIVE queda prohibido en staging: `LIVE_TRADING_ENABLED=false` obligatorio.
