# Runbook: LIVE containment and rollback

Fecha: 2026-05-06

## Objetivo

Definir como contener una situacion live-ready sin activar LIVE real ni ejecutar ordenes desde el runbook.

Este documento es operativo y fail-closed:

- documenta decisiones humanas;
- separa `hold`, `freeze`, `abort` y `rollback`;
- exige evidencia fresca antes de cualquier reanudacion;
- no reemplaza gates, preflight, permisos, canary, rollback ni aprobacion humana.

## Regla principal

- Si falta evidencia, el submit real queda bloqueado.
- Si hay duda, mantener `paper/testnet/read-only` y escalar.
- No usar rollback por reflejo.
- No ejecutar ordenes, cancelaciones ni cambios de estado desde este runbook.
- Cualquier accion mutante futura requiere bloque autorizado, audit log y aprobacion explicita.

## Estados seguros

- `NO_OPERAR`: no avanzar runtime ni submit real.
- `HOLD`: pausar canary o evaluacion hasta nueva evidencia.
- `FREEZE_RECOMMENDED`: recomendar congelar scope, simbolo o bot, sin ejecutarlo desde este documento.
- `ROLLBACK_RECOMMENDED`: recomendar retirada controlada, sin ejecutarla desde este documento.
- `MANUAL_REVIEW_REQUIRED`: requiere aprobador humano antes de reanudar.

## Decision path

### Caso A: no hay exposicion real activa

1. Mantener submit real bloqueado.
2. Registrar evidencia: health, gates, live-safety, preflight y canary si existe.
3. No promover stage.
4. Abrir seguimiento si el bloqueo persiste.

### Caso B: hay canary o habilitacion candidata en riesgo

1. Marcar `HOLD` o `ROLLBACK_RECOMMENDED` segun evidencia.
2. Registrar reason codes.
3. Exigir aprobacion humana para cualquier reanudacion.
4. No convertir una recomendacion del sistema en accion automatica.

### Caso C: hay exposicion real confirmada

1. Frenar automatismos y escalar a responsable humano.
2. Registrar scope, simbolo, bot, run id y estado de safety.
3. Usar solo procedimientos autorizados fuera de este runbook.
4. Cerrar el incidente solo con evidencia de contencion y reconciliacion.

## Evidencia minima

- Timestamp UTC.
- Entorno y deployment observado.
- Modo runtime: paper, testnet, canary o live.
- Estado de gates y preflight.
- Estado de live-safety, kill switch y freshness.
- Estado de canary/rollout si aplica.
- Decision humana: hold, freeze recomendado, rollback recomendado o no operar.
- Confirmacion de que no se ejecutaron ordenes desde el runbook.

## Relacion con RTLOPS-106 y RTLOPS-107

- RTLOPS-106 sigue abierto como deuda externa de Vercel Git Integration.
- RTLOPS-107/prebuilt sigue siendo workaround temporal para previews.
- Ninguna decision de containment debe depender de corregir RTLOPS-106.

## Criterio de salida

El incidente o bloqueo puede cerrarse cuando:

- submit real sigue bloqueado o fue reanudado por aprobacion explicita;
- los hard blockers tienen owner;
- la evidencia queda registrada;
- no hay ordenes o mutaciones no autorizadas;
- el proximo paso esta definido.
