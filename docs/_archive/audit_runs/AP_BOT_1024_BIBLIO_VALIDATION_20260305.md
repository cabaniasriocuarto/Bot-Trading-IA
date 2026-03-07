# AP-BOT-1024 - Bibliographic Validation (2026-03-05)

Objetivo del patch: automatizar smoke diario de staging (NO-LIVE) en GitHub VM.

## Cambios validados
- `/.github/workflows/staging-smoke.yml`
- `scripts/staging_smoke_report.py` (reutilizado como executor del workflow)

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` especifica para sintaxis/seguridad de GitHub Actions.
  - La bibliografia local del proyecto cubre trading/quant/microestructura; no cubre detalle de CI workflows.

## Fuentes primarias externas (mismo nivel)
- GitHub Docs - Workflow syntax:
  - https://docs.github.com/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub Docs - Scheduled workflows:
  - https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#schedule
- GitHub Docs - Secrets in Actions:
  - https://docs.github.com/actions/security-guides/using-secrets-in-github-actions
- Official action `upload-artifact`:
  - https://github.com/actions/upload-artifact

## Veredicto
- Diseño del workflow alineado a fuentes oficiales:
  - `workflow_dispatch` + `schedule` soportados.
  - Manejo de secretos via `secrets.*` y validacion fail-closed cuando `require_auth_checks=true`.
  - Publicacion de artefactos de evidencia por corrida.
