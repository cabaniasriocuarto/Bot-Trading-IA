# RTLab Dashboard (Next.js + Vercel)

Front-end dashboard + strategy lab para `rtlab_autotrader`.

Incluye:
- Next.js App Router + TypeScript
- Tailwind + componentes estilo shadcn
- Charts: TradingView Lightweight Charts + Recharts
- Auth con roles (`admin`, `viewer`)
- RBAC en API (viewer solo `GET`, admin `POST`)
- Integracion mock local y proxy al backend VPS

## 1) Ejecutar local

```bash
npm install
cp .env.example .env.local
npm run dev
```

Abrir: `http://localhost:3000`

## 2) Credenciales de login

Define credenciales propias en `.env.local` (no usar valores de ejemplo en produccion):

```env
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
VIEWER_USERNAME=...
VIEWER_PASSWORD=...
AUTH_SECRET=...
```

## 3) Modos de datos

### Modo mock (solo desarrollo)

```env
USE_MOCK_API=true
```

Toda la UI funciona con datos simulados para demo/desarrollo.
En produccion deja `USE_MOCK_API=false`.

### Modo real (backend VPS)

```env
USE_MOCK_API=false
BACKEND_API_URL=https://tu-backend-vps.com
```

La API de Next actua como proxy autenticado hacia tu backend.

## 4) API contract implementado (front <-> backend)

Endpoints soportados por la UI:

- `GET /api/status`
- `GET /api/portfolio`
- `GET /api/positions`
- `GET /api/trades?filters...`
- `GET /api/trades/:id`
- `GET /api/strategies`
- `GET /api/strategies/:id`
- `POST /api/strategies/:id/enable`
- `POST /api/strategies/:id/disable`
- `POST /api/strategies/:id/set-primary`
- `POST /api/strategies/:id/duplicate`
- `POST /api/strategies/:id/params`
- `GET /api/backtests`
- `POST /api/backtests/run`
- `GET /api/backtests/:id/report`
- `POST /api/control/pause`
- `POST /api/control/resume`
- `POST /api/control/safe-mode`
- `POST /api/control/kill`
- `POST /api/control/close-all`
- `GET /api/logs?since=...`
- `GET /api/alerts?since=...`
- `GET /api/events` (SSE)

Auth:
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

## 5) Paginas incluidas

- Overview (Home)
- Strategies (Registry)
- Strategy Detail
- Backtests (Strategy Lab)
- Trades + Trade Detail
- Positions / Portfolio
- Risk & Limits
- Execution / Microstructure
- Alerts & Logs
- Settings (Admin)

## 6) Deploy en Vercel

1. Importar repo en Vercel.
2. Seleccionar `Root Directory = rtlab_dashboard`.
3. Variables recomendadas:
   - `AUTH_SECRET`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
   - `VIEWER_USERNAME`
   - `VIEWER_PASSWORD`
   - `USE_MOCK_API` (recomendado: `false` en produccion)
   - `BACKEND_API_URL` (si `USE_MOCK_API=false`)
4. Deploy.

## 7) Seguridad

- No guardar API keys de exchange en el front.
- Toda accion sensible va por backend autenticado.
- Mantener `USE_MOCK_API=false` en produccion.
- Mantener RBAC activo tambien del lado backend.
- Configurar `AUTH_SECRET` fuerte (minimo 32 caracteres) y credenciales no triviales.

