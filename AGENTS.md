# Reglas permanentes de trabajo para agentes (Codex / Claude / ChatGPT)

## Objetivo
Mantener cambios limpios, revisables, deployables y sin mezclar ruido historico con producto real.

## Reglas obligatorias
1. Crear siempre una rama nueva desde `main`.
2. Trabajar una sola tarea por rama.
3. No mezclar cambios de producto con:
   - docs
   - auditorias
   - screenshots
   - exports
   - logs
   - workflows
   - archivos archivados
4. Antes de modificar, mostrar:
   - rama actual
   - `git status`
   - lista de archivos a tocar
5. No hacer push ni abrir PR hasta que:
   - el build local pase
   - el diff sea razonable
   - los archivos tocados esten claramente enumerados
6. Si la rama esta contaminada:
   - frenar
   - no seguir parchando
   - proponer una rama nueva desde `main`
   - hacer cherry-pick o copia selectiva
7. Si un archivo no impacta producto real, excluirlo.
8. No abrir PR gigantes.
9. Priorizar producto visible, deploy real y claridad de release.
10. Si algo no tiene backend real, no fingirlo en frontend.

## Validacion minima antes de push
- `git diff --stat`
- `npm run build`
- tests minimos necesarios segun el cambio

## Criterio de release
- PR chico
- diff limpio
- sin archivos de `docs/_archive/**`
- sin archivos de `docs/audit/**`
- sin archivos de `docs/audit_runs/**`
- sin ruido historico
- deployable en preview

## Regla de limpieza
Cuando exista ruido historico, el agente debe:
1. identificar
2. clasificar
3. proponer limpieza
4. borrar o mover solo lo claramente obsoleto, redundante o enganoso

## Regla de exclusion por defecto
Excluir, salvo justificacion tecnica explicita:
- `docs/_archive/**`
- `docs/audit/**`
- `docs/audit_runs/**`
- reportes markdown viejos
- screenshots
- exportaciones de conversaciones
- logs
- sqlite
- artefactos generados
- workflows no indispensables
