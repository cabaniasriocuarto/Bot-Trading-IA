# START HERE

Este archivo centraliza la documentacion vigente del proyecto.

## Fuente de verdad (usar primero)
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`
- `docs/truth/CHANGELOG.md`

## Auditoría vigente (docs sustantivos)
- `docs/audit/ACTION_PLAN_FINAL_20260304.md`
- `docs/audit/AP0001_AP0002_RUNTIME_CONTRACT_V1.md`
- `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
- `docs/audit/AUDIT_REPORT_20260304.md`
- `docs/audit/BOT_LINK_BEAST_CLEANUP_20260307.md`
- `docs/audit/FINDINGS_DECISION_MATRIX_20260304.md`
- `docs/audit/FINDINGS_MASTER_20260304.md`
- `docs/audit/LEARNING_EXPERIENCE_VALIDATION_20260306.md`
- `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`
- `docs/audit/INDEX.md`

## Investigación y aprendizaje
- `docs/research/BRAIN_OF_BOTS.md`
- `docs/research/EXPERIENCE_LEARNING.md`

## Estado operativo actual
- `NO-LIVE`: GO (staging/testnet/paper).
- `LIVE`: NO GO.
- Condicion para LIVE:
  - primero recuperar/reconciliar en esta base los cierres core live con drift confirmado (`RTLOPS-23/44/46/47/48/49/50`);
  - despues sync y validacion local de `RTLOPS-35`;
  - luego gate final `RTLOPS-38`;
  - y recien despues aprobacion humana sobre el entorno objetivo.

## Ambientes online de prueba (staging)
- Frontend (Vercel staging): `https://bot-trading-ia-staging.vercel.app`
- Backend (Railway staging): `https://bot-trading-ia-staging.up.railway.app`

## Runbooks operativos y de despliegue
- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- `docs/deploy/VERCEL_STAGING.md`
- `docs/deploy/RAILWAY_STAGING.md`
- `docs/deploy/GITHUB_ACTIONS_SECRETS.md`

## Seguridad operacional
- `docs/SECURITY.md`
- `docs/security/LOGGING_POLICY.md`

## Historico (no vigente)
- `docs/_archive/README_ARCHIVE.md`
- `docs/audit/INDEX.md` (seccion historica)
