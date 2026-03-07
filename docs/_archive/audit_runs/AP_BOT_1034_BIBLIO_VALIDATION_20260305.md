# AP-BOT-1034 - Bibliographic Validation (runner robusto ante fallo temprano)

Objetivo del patch: mejorar `scripts/run_protected_checks_github_vm.ps1` para generar resumen diagnostico incluso cuando el workflow falla antes de emitir JSON de checks.

## Cambios validados
- `scripts/run_protected_checks_github_vm.ps1`
  - cuando no existe `ops_protected_checks_gha_*.json`, el script ahora:
    - genera `protected_checks_summary_<run_id>.json` con `NO_EVIDENCE`;
    - conserva `run_url`, `workflow_conclusion` y metadatos del run;
    - evita salida muda ante fallo temprano de auth.

## Bibliografia local (repo)
- `docs/reference/BIBLIO_INDEX.md`:
  - `NO EVIDENCIA` para operacion GitHub CLI/workflow artifacts.

## Fuentes primarias externas (mismo nivel)
- GitHub CLI manual:
  - https://cli.github.com/manual/gh_run_download
  - https://cli.github.com/manual/gh_run_view
  - https://cli.github.com/manual/gh_run_list
- GitHub Actions artifacts:
  - https://docs.github.com/actions/using-workflows/storing-workflow-data-as-artifacts

## Veredicto
- El runner queda mas robusto y trazable para diagnosticar fallos de login/secrets en staging sin perder evidencia operativa.
