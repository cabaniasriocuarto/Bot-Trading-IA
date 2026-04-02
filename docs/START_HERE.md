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
- Estado del core live en esta rama:
  - `Carril 1` ya recupero materialmente la cohorte tecnica acoplada `RTLOPS-44/45/46/47/48/49/50/23`;
  - el blocker principal ya no es ausencia de `execution/reality` ni de sus runtimes/modulos satelite.
- Condicion para LIVE en esta base:
  - revalidar la capa release/UI (`RTLOPS-35` / `RTLOPS-38`) sobre esta misma rama;
  - ejecutar `docs/runbooks/LIVE_RELEASE_GATE.md` en el entorno objetivo con snapshots frescos;
  - y recien despues aprobacion humana sobre el entorno objetivo.

## Ambientes online de prueba (staging)
- Frontend (Vercel staging): `https://bot-trading-ia-staging.vercel.app`
- Backend (Railway staging): `https://bot-trading-ia-staging.up.railway.app`

## Runbooks operativos y de despliegue
- `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`
- `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`
- `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`
- `docs/runbooks/LIVE_RELEASE_GATE.md`
- `docs/deploy/VERCEL_STAGING.md`
- `docs/deploy/RAILWAY_STAGING.md`
- `docs/deploy/GITHUB_ACTIONS_SECRETS.md`

## Seguridad operacional
- `docs/SECURITY.md`
- `docs/security/LOGGING_POLICY.md`

## Historico (no vigente)
- `docs/_archive/README_ARCHIVE.md`
- `docs/audit/INDEX.md` (seccion historica)
