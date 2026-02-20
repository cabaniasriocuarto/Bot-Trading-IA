# RTLAB Strategy Console (Front-End)

Dashboard web en Next.js para operar y observar `Bot-Trading-IA`.

## Stack

- Next.js (App Router) + TypeScript
- Tailwind + componentes UI
- Recharts + Lightweight Charts
- Auth con roles (`admin`, `viewer`)
- BFF `/api/*` en misma origin

## Funcionalidades implementadas

- UI en espanol:
  - Resumen, Estrategias, Backtests, Operaciones, Portafolio, Riesgo, Ejecucion, Alertas y Logs, Configuracion.
- API versionada `/api/v1/*` por BFF (mismo origin), sin llamadas directas browser->Railway.
- Estrategias:
  - Registro, habilitar/deshabilitar, primaria por modo (paper/testnet/live), duplicar, editor YAML, subir Strategy Pack ZIP.
  - Estrategia default `trend_pullback_orderflow` cargada por defecto en mock.
- Backtests:
  - Correr run, listar runs, comparar 2-5 corridas, overlays equity/drawdown, export artefactos.
- Execution / Microstructure:
  - KPIs + series + notas operativas.
- Alerts & Logs:
  - filtros por fechas/severidad/modulo, drill-down payload, export CSV/JSON.
- Settings:
  - GET/PUT funcional, diagnostico backend/WS/exchange, test alerta Telegram.
- Stream:
  - `/api/events` y `/ws/v1/events` (SSE compatible).

## Variables de entorno

Copiar `.env.example` a `.env.local`.

Variables clave:

- `AUTH_SECRET`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `VIEWER_USERNAME`
- `VIEWER_PASSWORD`
- `USE_MOCK_API=false`
- `BACKEND_API_URL=https://<servicio>.up.railway.app`
- `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=false` (recomendado)

## MOCK vs REAL

```env
USE_MOCK_API=true
```

La app queda funcional sin backend real y muestra datos coherentes.

Para backend real:

```env
USE_MOCK_API=false
BACKEND_API_URL=https://<servicio>.up.railway.app
```

Requisitos backend:

- Exponer dominio publico `*.up.railway.app`.
- Escuchar en `0.0.0.0:$PORT`.
- Implementar contrato `/api/v1/*` + stream (`/ws/v1/events` o `/api/v1/events`).

## Correr local

```bash
npm install
npm run dev
```

Login por defecto (si no lo cambiaste):

- admin: `Wadmin` / `moroco123`
- viewer: `viewer` / `viewer123!`

## Contrato de API usado por el front

Minimo esperado:

- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `GET /api/v1/gates`
- `GET /api/v1/bot/status`
- `GET /api/v1/strategies`
- `POST /api/v1/strategies/upload`
- `POST /api/v1/strategies/:id/enable`
- `POST /api/v1/strategies/:id/disable`
- `POST /api/v1/strategies/:id/primary`
- `GET /api/v1/strategies/:id`
- `PUT /api/v1/strategies/:id/params`
- `POST /api/v1/backtests/run`
- `GET /api/v1/backtests/runs`
- `GET /api/v1/backtests/runs/:id`
- `GET /api/v1/trades`
- `GET /api/v1/portfolio`
- `GET /api/v1/risk`
- `GET /api/v1/execution/metrics`
- `GET /api/v1/logs`
- `GET /api/v1/alerts`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `POST /api/v1/gates/reevaluate`
- `POST /api/v1/bot/mode`
- `POST /api/v1/bot/start`
- `POST /api/v1/bot/stop`
- `POST /api/v1/bot/killswitch`
- `POST /api/v1/control/pause`
- `POST /api/v1/control/resume`
- `POST /api/v1/control/safe-mode`
- `POST /api/v1/control/kill`
- stream: `/api/v1/stream` (SSE), proxied por `/api/events` y `/ws/v1/events`

## Deploy en Vercel (importante para evitar 404)

1. Importa el repo.
2. En el proyecto de Vercel configura `Root Directory = rtlab_dashboard`.
3. Define variables de entorno del bloque anterior.
4. Deploy.

Si el `Root Directory` apunta al repo raiz, Vercel puede mostrar `404: NOT_FOUND`.

## Railway (backend real)

1. Servicio conectado al mismo repo.
2. Configurar el servicio backend (no el front) para iniciar API.
3. Confirmar que responda:
   - `/api/v1/health`
   - `/api/v1/settings`
   - stream `/ws/v1/events` (o `/api/v1/events`)
4. Copiar esa URL en `BACKEND_API_URL` del front (Vercel).

## Pasos MOCK -> BACKEND REAL (checklist rapido)

1. Railway (backend): cargar envs server-side:
   - `AUTH_SECRET`
   - `ADMIN_USERNAME=Wadmin`
   - `ADMIN_PASSWORD=moroco123`
   - `VIEWER_USERNAME`, `VIEWER_PASSWORD`
   - `MODE=paper`
   - `EXCHANGE_NAME=binance|bybit`
   - `API_KEY/API_SECRET` y/o `TESTNET_API_KEY/TESTNET_API_SECRET` segun modo.
2. Deploy backend y verificar:
   - `GET https://<railway>.up.railway.app/api/v1/health`
   - `GET https://<railway>.up.railway.app/api/v1/gates` (con auth)
3. Vercel (frontend): cargar envs:
   - `USE_MOCK_API=false`
   - `BACKEND_API_URL=https://<railway>.up.railway.app`
   - `AUTH_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `VIEWER_USERNAME`, `VIEWER_PASSWORD`
4. Ingresar al dashboard, ir a Estrategias y definir primaria por modo si hace falta.
5. Revisar gates en Configuracion y usar "Reevaluar gates".
6. Operar primero en `PAPER`/`TESTNET`. Habilitar `LIVE` solo cuando gates requeridos esten en PASS.
