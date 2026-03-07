# AP-BOT-1035 - Validacion bibliografica (2026-03-05)

## Objetivo del patch
Mantener checks estrictos en produccion, pero evitar falsos negativos operativos en `staging` no-live cuando:
- `G10_STORAGE_PERSISTENCE` esta en `WARN` por almacenamiento efimero de prueba.
- `breaker_events` devuelve `NO_DATA` por ausencia de eventos en entorno no-live.

## Archivos tocados
- `.github/workflows/remote-protected-checks.yml`
- `scripts/ops_protected_checks_report.py`

## Evidencia operativa
- Run staging:
  - `22741088468` (`success`)
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741088468_20260305.md`

## Coherencia tecnica
- Produccion no se relaja:
  - la excepcion aplica solo si la URL objetivo contiene `staging` y se activa flag explicito en workflow.
- Se conserva trazabilidad:
  - el reporte mantiene `g10_status=WARN` y `breaker_status=NO_DATA`;
  - solo cambia la evaluacion operativa final para no-live staging (`allow_staging_warns_applied=true`).

## Bibliografia/fuentes
- Local repo:
  - `docs/truth/SOURCE_OF_TRUTH.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- Fuentes primarias de control (nivel estandar):
  - OWASP ASVS (principio de fail-safe defaults y separacion por entorno).
  - OWASP API Security Top 10 (hardening de validaciones y control operacional por entorno).
