# AP-BOT-1027 - Bibliographic Validation (2026-03-05)

Objetivo del patch: endurecer workflows remotos para evitar fallback de credenciales entre entornos.

## Cambios validados
- `/.github/workflows/remote-protected-checks.yml`
- `/.github/workflows/staging-smoke.yml`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` para semantica de secretos por entorno en GitHub Actions.

## Fuentes primarias externas (mismo nivel)
- GitHub Docs - Secrets in Actions:
  - https://docs.github.com/actions/security-guides/using-secrets-in-github-actions
- GitHub Docs - Workflow syntax:
  - https://docs.github.com/actions/writing-workflows/workflow-syntax-for-github-actions

## Veredicto
- El patch reduce riesgo operacional:
  - staging usa exclusivamente `RTLAB_STAGING_*`;
  - produccion usa exclusivamente `RTLAB_*`;
  - se elimina fallback cruzado de credenciales entre entornos.
