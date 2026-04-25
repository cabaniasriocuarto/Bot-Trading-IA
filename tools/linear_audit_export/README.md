# Linear Audit Export

Utilidad de snapshot/auditoría para extraer Linear con foco en:

- preservación de texto completo
- trazabilidad entre entidades
- export raw canónico
- export derivado para LLM/humano
- resume/checkpoint
- adjuntos autenticados cuando sea posible
- validación básica del snapshot

El código vive en `rtlab_autotrader/rtlab_core/linear_audit_export/`.

## Por qué existe

Linear es excelente para operación, pero una auditoría profunda necesita:

- JSON raw sin truncado
- relaciones cruzadas conservadas
- comentarios completos
- documents/attachments preservados
- gaps explícitos cuando la API, el plan o los permisos no permiten bajar algo

Este exportador está pensado para producir un snapshot repetible que luego pueda revisar:

- una persona
- ChatGPT / Codex
- otros agentes o pipelines de auditoría

## Alcance real

La utilidad intenta exportar, según schema/permisos/plan:

- viewer / organization
- teams / users / workflow states / labels / custom views / templates
- projects / milestones / updates / statuses / documents
- initiatives / initiative updates
- cycles
- issues base
- issue comments
- issue relations
- issue attachments
- issue documents
- issue customer needs
- issue subscribers / children
- customers / customer requests
- audit log
- adjuntos `uploads.linear.app`

## Prerrequisitos

- Python 3.11+
- dependencias del repo instaladas
- una credencial de Linear:
  - `LINEAR_API_KEY`
  - o `LINEAR_ACCESS_TOKEN`

## Cómo crear API key

En Linear:

1. `Settings > Account > Security & Access`
2. crear una API key personal
3. guardarla en un secreto seguro
4. exportarla como variable de entorno

## Variables de entorno

- `LINEAR_API_KEY`
- `LINEAR_ACCESS_TOKEN`
- `LINEAR_BASE_URL=https://api.linear.app/graphql`
- `LINEAR_OUTPUT_DIR=./artifacts/linear_export`
- `LINEAR_INCLUDE_ATTACHMENTS=true|false`
- `LINEAR_INCLUDE_AUDIT=true|false`
- `LINEAR_INCLUDE_CUSTOMERS=true|false`
- `LINEAR_PAGE_SIZE=50`
- `LINEAR_TIMEOUT_SECONDS=60`
- `LINEAR_RETRY_MAX=5`
- `LINEAR_RESUME=true|false`
- `LINEAR_MAX_ISSUES=0`
- `LINEAR_LOG_LEVEL=INFO`
- `LINEAR_HASH_FILES=false`
- `LINEAR_PUBLIC_FILE_URLS_EXPIRE_IN=<segundos>` opcional

## Comandos

Discovery del schema:

```powershell
linear-export discover
```

Snapshot completo:

```powershell
linear-export snapshot --scope all
```

Snapshot parcial de issues:

```powershell
linear-export snapshot --scope issues --max-issues 100
```

Snapshot solo audit log:

```powershell
linear-export snapshot --scope audit
```

Descarga de adjuntos sobre snapshot existente:

```powershell
linear-export attachments download
```

Render derivado para LLM:

```powershell
linear-export render-llm
```

Validación básica:

```powershell
linear-export validate
```

## Estructura de salida

```text
artifacts/linear_export/
  snapshot_meta/
    manifest.json
    schema_summary.json
    export_log.json
    permissions_and_gaps.json
    checkpoint.json
    validation_report.json
  workspace/
    viewer.json
    organization.json
    teams.json
    users.json
    states.json
    labels.json
    views.json
    templates.json
    project_statuses.json
  delivery/
    projects.json
    project_milestones.json
    project_updates.json
    initiatives.json
    initiative_updates.json
    cycles.json
    documents.json
  customers/
    customers.json
    customer_requests.json
    customer_statuses.json
    customer_tiers.json
  audit/
    audit_entries.json
  issues/
    index.json
    by_identifier/
    comments/
    relations/
  attachments/
    entities.json
    files/
    metadata.json
  llm/
    INDEX.md
    EXPORT_SUMMARY.md
    GAPS_AND_LIMITATIONS.md
    AUDIT_HANDOFF_PROMPT.md
    issues/
    projects/
    initiatives/
    customers/
    audit/
  manual_imports/
    issues_csv/
    projects_csv/
    initiatives_csv/
    members_csv/
    customer_requests_csv/
    markdown_copies/
    pdfs/
    manual_import_manifest.json
```

## Cómo reanudar

El exportador usa `snapshot_meta/checkpoint.json`.

- si `LINEAR_RESUME=true`, reutiliza cursores y marcas por subproceso
- si querés reiniciar una corrida limpia, borrá `artifacts/linear_export/`

## Qué baja seguro

- schema summary
- probes de queries
- raw JSON de lo accesible por API y permisos
- markdown derivado desde el raw
- manifest
- validación básica

## Qué intenta bajar, pero puede depender de permisos/plan

- audit log
- customers y customer requests
- adjuntos autenticados
- vistas/custom views
- templates

## Cómo complementar con exportes manuales de UI

Guardá exports/manuales en:

- `manual_imports/issues_csv/`
- `manual_imports/projects_csv/`
- `manual_imports/initiatives_csv/`
- `manual_imports/members_csv/`
- `manual_imports/customer_requests_csv/`
- `manual_imports/markdown_copies/`
- `manual_imports/pdfs/`

### Sugerencia operativa

- export CSV de workspace/issues/views desde la UI cuando necesites contraste con API
- copiar markdown de issues/documents desde la UI cuando quieras validar fidelidad textual
- exportar PDFs de issues puntuales para auditoría formal con timestamps absolutos

## Cómo mergear material manual con el snapshot

- no sobrescribas raw API
- agregá los archivos manuales en `manual_imports/`
- corré `linear-export validate`
- usá `manual_imports/manual_import_manifest.json` como inventario complementario

## Cómo darle el dump a ChatGPT/Codex

Orden recomendado:

1. `snapshot_meta/manifest.json`
2. `snapshot_meta/schema_summary.json`
3. `snapshot_meta/permissions_and_gaps.json`
4. `llm/EXPORT_SUMMARY.md`
5. `issues/index.json`
6. `llm/issues/*.md`
7. `delivery/projects.json` / `delivery/initiatives.json`
8. `audit/audit_entries.json`

## Troubleshooting

- `Authentication required`
  - falta `LINEAR_API_KEY` o `LINEAR_ACCESS_TOKEN`
- `Query too complex`
  - bajar page size o separar scope
- 429 / rate limited
  - dejar resume activado y reintentar
- adjuntos fallan
  - revisar permisos y que la URL sea `uploads.linear.app`
- audit log vacío
  - puede faltar rol owner o el plan no exponerlo

## Limitaciones honestas

- la utilidad no escribe nada en Linear
- no adivina campos ausentes del schema
- algunas relaciones pueden existir en UI pero no quedar expuestas igual por la API
- algunos adjuntos pueden ser detectados pero no descargables
- el audit log depende de permisos/plan y retención
- la introspección completa de args del tipo `Query` puede ser demasiado costosa; por eso se combina introspección por tipo con probes de queries mínimas
