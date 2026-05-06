# Runbook: LIVE incident response

Fecha: 2026-05-06

## Objetivo

Establecer una respuesta minima y ordenada ante incidentes de una superficie LIVE-ready, canary, paper/testnet o read-only.

Este runbook no activa LIVE real, no envia ordenes y no modifica datos. Sirve para clasificar, registrar, contener y escalar.

## Cuando abrir incidente

Abrir incidente si aparece cualquiera de estos patrones:

- gate o preflight en `FAIL`, `BLOCKED`, `EXPIRED` o `STALE`;
- live-safety indica bloqueo;
- kill switch o manual lock requiere atencion;
- canary queda en `HOLD` o recomienda rollback;
- account/exchange surface no es tradeable;
- health o alerts muestran degradacion critica;
- se detecta cualquier intento de submit real fuera de contrato.

## Severidad minima

- `CRITICAL`: posible exposicion real, submit no autorizado, safety bloqueante o rollback recomendado.
- `WARN`: degradacion importante sin exposicion real activa.
- `INFO`: observacion, seguimiento o recuperacion contenida.

La severidad ordena la respuesta, pero no reemplaza juicio humano.

## Primeros 10 minutos

1. Abrir working log.
2. Registrar hora UTC, entorno, deployment, operador y scope.
3. Confirmar que LIVE real no fue activado por este bloque.
4. Capturar evidencia read-only: health, gates, preflight, live-safety, alerts y canary/rollout si aplica.
5. Elegir estado inicial: `NO_OPERAR`, `HOLD`, `FREEZE_RECOMMENDED`, `ROLLBACK_RECOMMENDED` o `MANUAL_REVIEW_REQUIRED`.
6. Definir siguiente checkpoint.

## Working log minimo

- Incidente y timestamp.
- Operador y aprobador si aplica.
- Entorno y deployment.
- Modo runtime observado.
- Rutas/endpoints consultados.
- Estados de gates, preflight y live-safety.
- Decision tomada.
- Confirmacion de no mutaciones/no ordenes.
- Proximo checkpoint.

## Comunicacion minima

Usar mensajes concretos:

- que fallo;
- que scope afecta;
- que evidencia lo sostiene;
- que accion se recomienda;
- que no se debe tocar;
- cuando se revisa de nuevo.

## Escalamiento

Escalar sin demora si:

- hay sospecha de orden real;
- hay cambio de datos no esperado;
- un safety blocker no tiene owner;
- se requiere rollback o freeze real;
- falta evidencia para continuar.

## Recuperacion

Antes de cerrar:

- revalidar gates y preflight;
- confirmar que no hay P0/P1 abierto;
- confirmar que submit real sigue bloqueado o fue habilitado por aprobacion explicita;
- registrar run, logs y decision;
- crear issue de seguimiento si queda deuda.

## Relacion con RTLOPS-106

RTLOPS-106 puede dejar Vercel Git Integration en rojo. Ese contexto se clasifica como deuda externa esperada y no debe confundirse con incidente de runtime, salvo que rompa el workaround prebuilt o el QA protegido.
