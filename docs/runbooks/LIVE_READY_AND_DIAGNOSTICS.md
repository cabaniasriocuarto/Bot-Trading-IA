# Runbook: LIVE readiness and diagnostics

Fecha: 2026-05-06

## Cuando usarlo

Usar este runbook antes de cualquier decision de habilitacion real, canary amplio o reanudacion sensible.

Tambien aplica cuando la UI o el backend muestran:

- submit real bloqueado;
- preflight pendiente, vencido o fallido;
- readiness live incompleta;
- live-safety en bloqueo;
- canary en hold;
- rollback recomendado.

## Principio operativo

El sistema es LIVE-ready por arquitectura, pero el submit real permanece bloqueado hasta completar:

- gates;
- preflight;
- permisos exchange/account;
- market data y orderbook freshness;
- risk gates;
- kill switch sano;
- canary;
- rollback plan;
- approval humano;
- audit log.

## Superficies read-only recomendadas

Consultar solo lecturas seguras y ya existentes cuando esten disponibles:

- `/api/v1/health`
- `/api/v1/gates`
- `/api/v1/rollout/status`
- `/api/v1/exchange/diagnose`
- `/api/v1/exchange/live-preflight`
- `/api/v1/execution/kill-switch/status`
- `/api/v1/execution/live-safety/summary`
- `/api/v1/execution/canary/status`

No usar este runbook para enviar `POST`, `PUT`, `PATCH` o `DELETE`.

## Diagnostico rapido

1. Confirmar entorno, deployment y commit.
2. Confirmar modo runtime visible.
3. Confirmar `LIVE enabled` y `submit real`.
4. Revisar gates y preflight.
5. Revisar live-safety, kill switch y freshness.
6. Revisar canary/rollout si aplica.
7. Registrar blockers y owners.

## Patrones comunes

### Preflight fail, stale o pendiente

- Mantener submit bloqueado.
- Registrar reason code y timestamp.
- No promover stage ni activar live.
- Reintentar solo con autorizacion explicita y evidencia fresca.

### Kill switch o safety blocker

- Mantener fail-closed.
- Identificar scope: global, bot o simbolo.
- Escalar si existe exposicion real.
- No reanudar sin aprobador humano.

### Canary hold o rollback recomendado

- Tratarlo como recomendacion operacional, no como accion automatica.
- Registrar run id, blocker y decision.
- Usar el runbook de containment si hay riesgo activo.

### Vercel Git Integration rojo

- Si corresponde a RTLOPS-106, clasificar como deuda externa esperada.
- No mezclarlo con readiness runtime.
- Validar por prebuilt/QA protegido cuando el workaround RTLOPS-107 siga vigente.

## Evidencia a guardar

- Run de QA o fuente read-only.
- Deployment/commit.
- Resultado de `/reporting` si el frente Cost Stack participa.
- Estado de gates/preflight/live-safety.
- Decision: no operar, mantener bloqueado, avanzar canary o escalar.
- Confirmacion de cero ordenes/mutaciones.

## Criterio de salida

El diagnostico queda cerrado si:

- hay decision explicita;
- los blockers tienen owner;
- no hay P0/P1 sin clasificar;
- RTLOPS-106 queda separado como deuda externa;
- el siguiente microbloque esta definido.
