# AP-BOT-1028 - Bibliographic Validation (2026-03-05)

Objetivo del patch: documentar configuracion de secretos por entorno para workflows remotos.

## Cambios validados
- `docs/deploy/GITHUB_ACTIONS_SECRETS.md`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` para gestion de GitHub Actions secrets.

## Fuentes primarias externas (mismo nivel)
- GitHub Docs - Secrets in Actions:
  - https://docs.github.com/actions/security-guides/using-secrets-in-github-actions
- GitHub Docs - GH CLI secret commands:
  - https://cli.github.com/manual/gh_secret_set
  - https://cli.github.com/manual/gh_secret_list
- GitHub Docs - workflow_dispatch:
  - https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch

## Veredicto
- Runbook alineado a fuentes oficiales y al hardening AP-BOT-1027:
  - separacion de secretos por entorno;
  - pasos de carga/validacion reproducibles.
