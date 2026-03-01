# Runbook: Storage Persistente en Railway (RTLAB)

Fecha: 2026-02-28

## Objetivo
Evitar que un redeploy resetee estado runtime (bots/runs/logs) por usar `/tmp`.

## Resultado esperado
- `/api/v1/health` devuelve `storage.persistent_storage=true`.
- `/api/v1/gates` devuelve `G10_STORAGE_PERSISTENCE=PASS`.
- LIVE no queda bloqueado por storage efimero.

## Paso a paso

1. Crear o validar volumen persistente en Railway
- Railway `Project -> Service -> Volumes`.
- Crear volume y montarlo en ruta persistente (recomendado: `/data`).

2. Configurar variable de entorno en backend
- Railway `Project -> Service -> Variables`.
- Definir:
  - `RTLAB_USER_DATA_DIR=/data/rtlab_user_data`

3. Aplicar cambios y redeploy
- Click en `Apply` o `Deploy` para que el contenedor tome la nueva variable.

4. Verificar desde API
- Login admin y consultar:
  - `GET /api/v1/health`
  - `GET /api/v1/gates`
- Confirmar:
  - `storage.persistent_storage=true`
  - `G10_STORAGE_PERSISTENCE.status=PASS`

5. Verificar con script local (opcional recomendado)
```bash
python scripts/check_storage_persistence.py \
  --base-url https://bot-trading-ia-production.up.railway.app \
  --username Wadmin \
  --password "<PASSWORD_ADMIN>" \
  --require-persistent
```

## Diagnostico rapido de fallas

- Si `storage_ephemeral=true`:
  - `RTLAB_USER_DATA_DIR` sigue en `/tmp` o no tomo el redeploy.
- Si `G10_STORAGE_PERSISTENCE=FAIL`:
  - modo LIVE queda bloqueado hasta corregir path persistente.

## Notas operativas
- En Railway, cualquier cambio de variables dispara redeploy.
- Si el backend sigue con storage efimero, los benchmarks y cardinalidad de bots no son estables entre deploys.
