# AP-BOT-1030 - Bibliographic Validation (2026-03-05)

Objetivo del patch: automatizar ejecucion de `Remote Protected Checks (GitHub VM)` desde PowerShell y extraer automaticamente los 6 campos canonicos de cierre.

## Cambios validados
- `scripts/run_protected_checks_github_vm.ps1` (nuevo).

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` especifica para automatizacion GitHub CLI/Actions.
- `docs/deploy/GITHUB_ACTIONS_SECRETS.md`:
  - lineamientos operativos de secretos y ejecucion remota de workflows.

## Fuentes primarias externas (mismo nivel)
- GitHub CLI manual:
  - https://cli.github.com/manual/gh_workflow_run
  - https://cli.github.com/manual/gh_run_list
  - https://cli.github.com/manual/gh_run_view
  - https://cli.github.com/manual/gh_run_download
- GitHub Docs (`workflow_dispatch`):
  - https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch

## Veredicto
- El script queda alineado con fuentes oficiales para:
  - dispatch reproducible del workflow remoto;
  - polling de estado de run;
  - descarga de artifacts y parseo de reporte JSON;
  - extraccion deterministica de `overall_pass`, `protected_checks_complete`, `g10_status`, `g9_status`, `breaker_ok`, `internal_proxy_status_ok`.
