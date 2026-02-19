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
- API versionada `/api/v1/*` con proxy al backend y fallback mock.
- Estrategias:
  - Registro, habilitar/deshabilitar, primaria, duplicar, editor YAML, subir Strategy Pack ZIP.
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
- `USE_MOCK_API=true|false`
- `BACKEND_API_URL=https://<servicio>.up.railway.app`
- `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=true|false`

## Modo MOCK (demo inmediata)

```env
USE_MOCK_API=true
```

La app queda funcional sin backend real y muestra datos coherentes.

## Modo REAL (Vercel -> Railway)

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

- admin: `admin` / `admin123!`
- viewer: `viewer` / `viewer123!`

## Contrato de API usado por el front

Minimo esperado:

- `GET /api/v1/health`
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
- `POST /api/v1/control/pause`
- `POST /api/v1/control/resume`
- `POST /api/v1/control/safe-mode`
- `POST /api/v1/control/kill`
- stream: `/api/events` y `/ws/v1/events`

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
