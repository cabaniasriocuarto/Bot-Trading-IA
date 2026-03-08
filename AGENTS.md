# Reglas permanentes de trabajo para agentes (Codex / Claude / ChatGPT)

## Objetivo
Mantener cambios limpios, revisables, deployables y sin mezclar ruido historico con producto real.

## Reglas obligatorias
1. Antes de modificar, inspeccionar:
   - rama actual
   - `git status`
   - relacion con `main`
   - objetivo de la tarea
2. Si la tarea es continuacion directa del mismo objetivo y la rama esta limpia y coherente, seguir en la rama actual.
3. Si cambia el objetivo, si hay mezcla de cambios no relacionados o si la rama esta contaminada, crear una rama nueva desde `main`.
4. No crear una rama nueva por cada microcambio o por cada archivo.
5. Crear rama nueva solo por feature, fix o release coherente.
6. Trabajar una sola tarea por rama.
7. No mezclar cambios de producto con:
   - docs
   - auditorias
   - screenshots
   - exports
   - logs
   - workflows
   - archivos archivados
8. Antes de modificar, mostrar:
   - rama actual
   - `git status`
   - lista de archivos a tocar
9. No hacer push ni abrir PR hasta que:
   - el build local pase
   - el diff sea razonable
   - los archivos tocados esten claramente enumerados
10. Si la rama esta contaminada:
   - frenar
   - no seguir parchando
   - proponer una rama nueva desde `main`
   - hacer cherry-pick o copia selectiva
11. Si un archivo no impacta producto real, excluirlo.
12. No abrir PR gigantes.
13. Priorizar producto visible, deploy real y claridad de release.
14. Si algo no tiene backend real, no fingirlo en frontend.

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
