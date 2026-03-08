# BIBLIO ACCESS POLICY

Fecha: 2026-03-04

## Objetivo
- Definir una politica reproducible para gestionar bibliografia local sin exponer archivos con posible restriccion de licencia en el repo.

## Alcance
- Aplica a:
  - `docs/reference/biblio_raw/` (insumos locales, no versionados).
  - `docs/reference/biblio_txt/` (texto extraido/copiado, no versionado).
  - `docs/reference/BIBLIO_INDEX.md` (metadatos versionados).

## Reglas canonicas
1. `biblio_raw` y `biblio_txt` no se suben al repositorio.
2. Todo insumo bibliografico usado en auditoria/investigacion debe quedar registrado en `BIBLIO_INDEX.md`.
3. El indice debe incluir como minimo:
   - nombre de archivo fuente;
   - `Source SHA256`;
   - estado de extraccion/copia (`TXT status`).
4. Los cambios de bibliografia deben mantener trazabilidad hash-a-hash (misma fuente => mismo SHA256).
5. Si no existe parser PDF, el estado debe quedar explicitado (`no_pdf_parser` o `extract_error:*`), no se asume contenido.

## Flujo operativo
1. Colocar fuentes localmente (fuera de git o en `docs/reference/biblio_raw/` ignorado por git).
2. Regenerar indice:
   - `python scripts/biblio_extract.py --input-dir "C:\\ruta\\a\\fuentes" --input-dir "docs/reference/biblio_raw" --index-out "docs/reference/BIBLIO_INDEX.md" --txt-out-dir "docs/reference/biblio_txt"`
3. Verificar que `BIBLIO_INDEX.md` incluya hashes y estado de extraccion para cada fuente.
4. Versionar en git solo:
   - `docs/reference/BIBLIO_INDEX.md`
   - esta politica (`docs/reference/BIBLIO_ACCESS_POLICY.md`)

## Validacion minima (PowerShell)
1. Hash puntual:
   - `Get-FileHash "C:\\ruta\\archivo.pdf" -Algorithm SHA256`
2. Re-ejecucion de indice y diff:
   - `python scripts/biblio_extract.py ...`
   - `git diff docs/reference/BIBLIO_INDEX.md`

## Criterio de cumplimiento
- Cumple: `BIBLIO_INDEX.md` actualizado + hashes presentes + raw/txt fuera de git.
- No cumple: fuente usada sin hash en indice o archivos raw/txt versionados por error.
