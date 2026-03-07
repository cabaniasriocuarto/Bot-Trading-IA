# AP-BOT-1026 - Bibliographic Validation (2026-03-05)

Objetivo del patch: seleccionar secretos por entorno (staging/prod) en workflows remotos sin usar password por CLI.

## Cambios validados
- `/.github/workflows/remote-protected-checks.yml`
- `/.github/workflows/staging-smoke.yml`
- `docs/audit/PROTECTED_CHECKS_GHA_22732769817_20260305.md`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` especifica para CI workflows y manejo de secrets de GitHub Actions.

## Fuentes primarias externas (mismo nivel)
- GitHub Docs - Workflow syntax:
  - https://docs.github.com/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub Docs - Secrets in Actions:
  - https://docs.github.com/actions/security-guides/using-secrets-in-github-actions
- GitHub Docs - workflow_dispatch inputs:
  - https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch

## Veredicto
- El patch mantiene fail-closed de auth y agrega resolucion por entorno:
  - staging usa `RTLAB_STAGING_AUTH_TOKEN`/`RTLAB_STAGING_ADMIN_PASSWORD` cuando existen.
  - fallback seguro a secretos globales cuando no existen secretos de staging.
- Sin regression en flujo productivo:
  - protected checks en `strict=true` continua en PASS (`run 22732769817`).
