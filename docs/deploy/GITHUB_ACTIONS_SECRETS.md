# GitHub Actions Secrets - Staging y Produccion

Fecha: 2026-03-05

## Objetivo
Configurar secretos por entorno para workflows remotos (`protected checks` y `staging smoke`) sin mezclar credenciales.

## Secrets requeridos
- Produccion/no-live general:
  - `RTLAB_ADMIN_PASSWORD` (obligatorio)
  - `RTLAB_AUTH_TOKEN` (opcional)
- Staging:
  - `RTLAB_STAGING_ADMIN_PASSWORD` (obligatorio si no hay token staging)
  - `RTLAB_STAGING_AUTH_TOKEN` (opcional)

## Regla operativa
- Workflows contra URL `staging` usan solo `RTLAB_STAGING_*`.
- Workflows contra URL de produccion usan solo `RTLAB_*`.

## Comandos (gh CLI)
Ver secretos actuales:
```bash
gh secret list --repo cabaniasriocuarto/Bot-Trading-IA
```

Set de secreto staging por password:
```bash
gh secret set RTLAB_STAGING_ADMIN_PASSWORD --repo cabaniasriocuarto/Bot-Trading-IA
```

Set de secreto staging por token:
```bash
gh secret set RTLAB_STAGING_AUTH_TOKEN --repo cabaniasriocuarto/Bot-Trading-IA
```

Actualizar secreto de produccion:
```bash
gh secret set RTLAB_ADMIN_PASSWORD --repo cabaniasriocuarto/Bot-Trading-IA
```

## Validacion recomendada
1. Ejecutar `Remote Protected Checks (GitHub VM)` con:
   - `base_url=https://bot-trading-ia-staging.up.railway.app`
   - `expect_g9=WARN`
   - `strict=false`
2. Confirmar que no falla en `Validate auth configuration`.
3. Revisar reporte `.md/.json` en artifacts.

## Nota
- El workflow `staging-smoke.yml` requiere existir en default branch para ejecutarse por `workflow_dispatch`.
