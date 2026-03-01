# Runbook: Backup / Restore de `user_data`

Fecha: 2026-02-28

## Objetivo
Tener backup reproducible de estado operativo (`bots`, `runs`, `settings`, `registry`, research) y restore seguro.

## Alcance
- Incluye archivos bajo `user_data`.
- No incluye secretos de entorno (`.env`, variables Railway/Vercel).

## Scripts
- Backup: `scripts/backup_user_data.py`
- Restore: `scripts/restore_user_data.py`

## 1) Crear backup

```bash
python scripts/backup_user_data.py
```

Salida esperada:
- JSON con ruta de zip y hash SHA256.
- Archivo en `backups/user_data_backup_YYYYMMDD_HHMMSS.zip`.

Opcional (ruta explícita):
```bash
python scripts/backup_user_data.py --source-dir /data/rtlab_user_data --output-dir backups
```

## 2) Restore

### Caso A: destino vacío
```bash
python scripts/restore_user_data.py --archive backups/user_data_backup_YYYYMMDD_HHMMSS.zip --target-dir /data/rtlab_user_data
```

### Caso B: reemplazar destino existente
```bash
python scripts/restore_user_data.py --archive backups/user_data_backup_YYYYMMDD_HHMMSS.zip --target-dir /data/rtlab_user_data --force
```

## Validaciones de seguridad del restore
- Rechaza entradas ZIP con rutas absolutas.
- Rechaza entradas ZIP con `..` (path traversal).

## Checklist operativo recomendado
1. Crear backup antes de cambios de variables/redeploy.
2. Guardar hash SHA256 del zip en ticket o changelog operativo.
3. Ejecutar restore en entorno de prueba al menos 1 vez por trimestre (drill).
4. Verificar post-restore:
   - `GET /api/v1/health` = `ok`
   - `GET /api/v1/bots` retorna cardinalidad esperada
   - `GET /api/v1/gates` sin regresiones inesperadas.
