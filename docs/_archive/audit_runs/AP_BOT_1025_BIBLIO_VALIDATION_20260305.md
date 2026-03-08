# AP-BOT-1025 - Bibliographic Validation (2026-03-05)

Objetivo del patch: endurecer `remote-protected-checks.yml` para evitar password CLI y respetar `strict=false`.

## Cambios validados
- `/.github/workflows/remote-protected-checks.yml`
- `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732410544_20260305.md`

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` sobre sintaxis/controles de GitHub Actions.
  - Bibliografia local orientada a trading/microestructura, no a CI workflow semantics.

## Fuentes primarias externas (mismo nivel)
- GitHub Docs - Workflow syntax:
  - https://docs.github.com/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub Docs - Input handling / workflow_dispatch:
  - https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch
- GitHub Docs - Secrets in Actions:
  - https://docs.github.com/actions/security-guides/using-secrets-in-github-actions

## Veredicto
- Patch alineado a hardening:
  - `strict=false` ahora se traduce a `--no-strict` de forma explicita.
  - se elimina ruta insegura de password por CLI en workflow remoto.
