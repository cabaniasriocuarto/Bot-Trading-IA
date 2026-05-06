# Runbook: LIVE release gate

Fecha: 2026-05-06

## Objetivo

Definir el gate documental para decidir si una release puede avanzar hacia canary o LIVE real.

Este runbook no habilita LIVE. La decision final requiere evidencia fresca, aprobacion humana y un bloque operativo autorizado.

## Decision por defecto

La decision por defecto es `NO GO` hasta probar lo contrario.

Para pasar a `GO` o `GO con restricciones`, deben cumplirse todos los puntos:

- main limpio y alineado;
- Security CI y QA protegido relevantes en PASS;
- backend production sano;
- preflight vigente;
- gates en PASS o bloqueo explicado;
- live-safety sin hard blockers;
- kill switch validado;
- canary y rollback documentados;
- approval humano registrado;
- RTLOPS-106 clasificado si afecta Vercel Git Integration.

## Matriz de evidencia

| Area | Evidencia minima | Resultado |
| --- | --- | --- |
| Repo | commit, PRs, status limpio | PASS/BLOCK |
| CI | Security CI, workflows criticos | PASS/BLOCK |
| Preview | prebuilt READY si RTLOPS-107 aplica | PASS/BLOCK |
| QA | RTLOPS-109A o equivalente | PASS/BLOCK |
| Backend | health, OpenAPI, endpoints criticos | PASS/BLOCK |
| Execution | LIVE-ready visible, submit real bloqueado/habilitable | PASS/BLOCK |
| Gates | gates/preflight/live-safety | PASS/BLOCK |
| Canary | scope, fase, hold/rollback plan | PASS/BLOCK |
| Approval | aprobador, fecha, limite | PASS/BLOCK |

## Blockers duros

- LIVE real activado sin aprobacion.
- Orden o mutacion real no autorizada.
- Secrets expuestos.
- DB productiva modificada sin bloque aprobado.
- Preflight vencido o ausente.
- Kill switch desconocido.
- RTLOPS-106 confundido con readiness runtime.
- QA protegido fallando sin clasificacion.

## Resultado permitido

- `NO GO`: falta evidencia o hay blocker.
- `GO con restricciones`: solo canary/paper/testnet/read-only con limites claros.
- `GO`: requiere aprobacion humana y evidencia fresca de todos los gates.

## Relacion con Cost Stack

El frente Cost Stack ya tiene UI read-only `/reporting` y QA protegido cubriendo `Costos`, `Reporting`, `taxCommission` y `specialCommission` como pendientes/no soportados.

La ausencia de soporte backend completo para `taxCommission` y `specialCommission` no bloquea un canary read-only, pero debe quedar documentada antes de cualquier decision live real.

## Relacion con RTLOPS-106

RTLOPS-106 sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`.

Mientras RTLOPS-107/prebuilt siga vigente:

- Vercel Git Integration rojo se clasifica como esperado si coincide con RTLOPS-106;
- el gate debe usar prebuilt READY y QA protegido como evidencia operativa;
- el workaround no debe convertirse en solucion definitiva sin decision explicita.

## Criterio de cierre del gate

El gate queda cerrado solo si:

- la decision queda escrita;
- se registran links a runs/deployments;
- se confirma cero ordenes/mutaciones no autorizadas;
- se lista que queda pendiente;
- se define el siguiente bloque.
