# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-05-06

## RTLOPS-62 - Cost Stack operativo en Execution - 2026-05-06

- Estado real:
  - `/reporting` sigue siendo el hub principal contable de Cost Stack;
  - `/trades` y `/portfolio` ya muestran Cost Stack compacto;
  - `/execution` necesitaba una lectura operativa, no contable, para decidir si operar sin duplicar reporting.
- Cambio UI read-only:
  - `Execution` agrega la tarjeta `Costos operativos / Cost Stack`;
  - consume lecturas existentes de `/api/v1/reporting/costs/breakdown` y `/api/v1/reporting/performance/summary`;
  - muestra fees, spread, slippage, costos totales, gross/net PnL, funding, borrow interest, coverage de commission components, source, freshness y status cuando el contrato los expone;
  - conserva missing data como `pendiente` o `no disponible`, sin interpretar ausencia como cero;
  - agrega link visible a `/reporting` para detalle completo.
- Limites:
  - la tarjeta es informativa y read-only;
  - no habilita submit real, no modifica gates, no ejecuta ordenes y no agrega readiness formal de Cost Stack;
  - no toca backend, endpoints nuevos, DB/user_data, Binance privado, secrets, Vercel/Railway settings, preserve/rescue/audit, RTLOPS-106 ni RTLOPS-107.
- Pendiente futuro:
  - freshness por componente;
  - funding/borrow estimated;
  - `cost_stack_readiness_status` formal;
  - Cost Stack por bot/simbolo/estrategia si se decide.

## RTLOPS-62 - QA protegido para Cost Stack compacto en Trades/Portfolio - 2026-05-06

- Estado real:
  - `PR #79` ya mergeo el Cost Stack compacto en `/trades` y el bloque `Costos y PnL neto` en `/portfolio`;
  - el QA protegido/autenticado ya cargaba `/trades=200` y `/portfolio=200`, pero faltaban aserciones textuales dedicadas para esas superficies.
- Cambio QA-only:
  - `RTLOPS-109A Protected Preview QA` valida semantica visible en `/trades`: `Cost Stack`, `Costos`, `PnL bruto`, `PnL neto`, `fees`, `slippage` y link a `/reporting`;
  - valida semantica visible en `/portfolio`: `Costos y PnL neto`, `Gross PnL`, `Net PnL`, `Costos totales`, link a `/reporting` y estados honestos como `pendiente`, `no disponible`, `no aplica`, `no soportado`, `disponible` o `parcial`;
  - mantiene las aserciones existentes de `/reporting`, `taxCommission` y `specialCommission`.
- Limites:
  - no toca producto funcional, backend, endpoints, DB/user_data, Binance privado, secrets, Vercel/Railway settings, preserve/rescue/audit ni branch protection;
  - no activa LIVE real, no ejecuta ordenes y no agrega metodos mutantes;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`.

## Live operations runbooks clean rescue - 2026-05-06

- Estado real:
  - `preserve/remote-account-surface-repo-main` contiene cuatro runbooks live potencialmente utiles, pero la rama esta 157 commits behind / 45 ahead, sucia y mezclada con artifacts;
  - no es fuente de verdad y no debe mergearse ni cherry-pickearse directo.
- Cambio documental:
  - se rehacen limpio desde `main` los runbooks:
    - `docs/runbooks/LIVE_READY_AND_DIAGNOSTICS.md`;
    - `docs/runbooks/LIVE_CONTAINMENT_AND_ROLLBACK.md`;
    - `docs/runbooks/LIVE_INCIDENT_RESPONSE.md`;
    - `docs/runbooks/LIVE_RELEASE_GATE.md`.
- Linea operativa:
  - el producto sigue LIVE-ready por arquitectura, pero el submit real permanece bloqueado por gates, preflight, permisos, kill switch, canary, rollback, approval y audit log;
  - los runbooks no ejecutan ordenes, no activan LIVE real y no modifican datos.
- Limites:
  - no se toca codigo, workflows, Vercel/Railway settings, secrets, DB, preserve ni branch protection;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`;
  - `RTLOPS-107` sigue siendo workaround temporal de previews prebuilt.

## RTLOPS-124 - Execution LIVE-readiness evidence panel - 2026-05-05

- Estado real:
  - `RTLOPS-123` corrigio el framing de `Execution`: el producto es LIVE-ready, no `paper-only`;
  - faltaba ordenar evidencia visible para explicar por que el submit real queda bloqueado o eventualmente habilitable.
- Cambio funcional chico:
  - `Execution` agrega un panel `Evidencia LIVE-readiness`;
  - muestra estado `PASS`, `FAIL`, `PENDIENTE`, `BLOQUEADO` o `NO APLICA` por cada evidencia;
  - usa lecturas read-only existentes de `/api/v1/health`, `/api/v1/gates`, `/api/v1/rollout/status`, `/api/v1/exchange/diagnose`, `/api/v1/exchange/live-preflight`, `/api/v1/execution/kill-switch/status` y `/api/v1/execution/live-safety/summary`;
  - deja claro que `LIVE-ready != orden real` y que el submit real sigue bloqueado hasta readiness, gates, preflight, permisos, kill switch, freshness, canary, aprobacion y auditoria.
- Limites:
  - no activa LIVE real;
  - no envia ordenes reales;
  - no agrega submit real nuevo ni mutaciones;
  - no toca backend, Binance keys, Vercel/Railway settings, variables/secrets, DB, branch protection, package files ni RTLOPS-106;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`.

## RTLOPS-123 - Execution LIVE-ready wording and activation contract - 2026-05-05

- Estado real:
  - `RTLOPS-122` dejo Execution mas segura, pero el framing podia leerse como si el producto fuera `paper-only` o `no-live`;
  - la postura correcta del proyecto es arquitectura LIVE-ready desde el minuto cero, con submit real bloqueado por contrato hasta completar gates, preflight, permisos, aprobacion, canary, rollback y auditoria.
- Cambio funcional chico:
  - `Execution` cambia el framing a `Contrato LIVE-ready con submit real bloqueado`;
  - muestra `LIVE-ready`, `LIVE habilitado`, `Submit real` y `Readiness LIVE`;
  - explica que las rutas/adaptadores/preflight/gates existen como contrato de activacion, pero que no se envian ordenes reales hasta habilitacion controlada;
  - reemplaza copys centrados en `apagado/no-live` por `submit real bloqueado por gates/preflight`;
  - mantiene `Cerrar posiciones`, `Kill switch`, `Guardar LIVE` y `Modo LIVE` bloqueados si no pasan readiness/gates/permisos.
- Limites:
  - no activa LIVE real;
  - no envia ordenes reales;
  - no toca backend, Binance keys, Vercel/Railway settings, variables/secrets, DB, branch protection, package files ni RTLOPS-106;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`.

## RTLOPS-122 - Execution paper/testnet guardrails clarity - 2026-05-05

- Estado real:
  - despues de `RTLOPS-120` y `RTLOPS-121`, el sistema queda en postura segura `paper/testnet/read-only`;
  - `Execution` necesitaba explicitar mejor el estado operativo: modo actual, LIVE real apagado, `runtime_ready_for_live=false` y motivos de bloqueo.
- Cambio funcional chico:
  - `Execution` agrega una banda de `Postura operativa segura`;
  - muestra `LIVE real` y `Readiness LIVE` como metricas visibles;
  - explica por que acciones peligrosas quedan disabled;
  - lista que falta para habilitar LIVE en el futuro;
  - `Cerrar posiciones` y `Kill switch` quedan bloqueados cuando LIVE real no esta activo/listo.
- Limites:
  - no activa LIVE;
  - no envia ordenes reales;
  - no agrega mutaciones peligrosas;
  - no toca Vercel/Railway settings, variables/secrets, DB, branch protection, package files ni RTLOPS-106;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`.

## RTLOPS-121 - GitHub Actions Node24 readiness - 2026-05-05

- Estado real:
  - GitHub Actions empezo a emitir warnings por acciones JavaScript ejecutando Node.js 20;
  - el run canary/protected QA `25373591442` reporto deprecacion Node.js 20 para `actions/checkout@v4` y `actions/upload-artifact@v4`;
  - tambien se auditaron las acciones oficiales usadas por workflows criticos: `actions/setup-node`, `actions/setup-python`, `actions/download-artifact`, `actions/cache` y `actions/github-script`.
- Alcance del bloque:
  - actualizar workflows administrativos/CI a versiones oficiales compatibles con Node 24;
  - mantener triggers, inputs, secrets y logica funcional equivalente;
  - no usar `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION` ni workarounds para permanecer en Node 20.
- Limites:
  - no toca producto, frontend funcional, backend, package files, Vercel settings, Railway settings, variables/secrets, DB, branch protection ni RTLOPS-69 Slice 3;
  - no ejecuta deploy/redeploy, ordenes ni mutaciones;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`;
  - `RTLOPS-107` sigue siendo workaround temporal de previews prebuilt, no fix definitivo de Git Integration.

## RTLOPS-118 - cierre post Railway production fix - 2026-05-05

- Estado real:
  - `RTLOPS-117` corrigio el mismatch operativo de Railway production sin tocar codigo ni Dockerfile;
  - production paso de `rootDirectory=/rtlab_autotrader` a repo root equivalente (`rootDirectory=""`/null);
  - el deployment production nuevo `5a6fb353-cba9-43ab-a8ea-53a8ddb3bbef` corre el commit `764faf646b525e93c44c0d98084d0cf34a1c2156` con status `SUCCESS`;
  - production `/api/v1/health` responde `200`;
  - production `/openapi.json` vuelve a listar `POST /api/v1/research/dataset-preflight`;
  - POST directo sin auth a `/api/v1/research/dataset-preflight` responde `401 Unauthorized` esperado, no `404`.
- Regresion final:
  - workflow `RTLOPS-109A Protected Preview QA` run `25352773864` -> `success`;
  - `access_status=app`;
  - login viewer OK;
  - `/api/auth/me=200`, rol `viewer`;
  - APIs principales autenticadas respondieron `200`;
  - Portfolio mantiene `Cerrar todas` visible y disabled;
  - Execution mantiene `Pausar`, `Reanudar`, `Cerrar posiciones`, `Kill switch`, `Guardar LIVE` y `Modo LIVE` visibles y disabled;
  - no hubo ordenes, mutaciones ni cambios de datos;
  - el residual `dataset-preflight` ya no registra respuestas `404` en el QA; solo quedaron aborts de navegacion rapida (`net::ERR_ABORTED`), no clasificados como bug.
- Causa raiz cerrada:
  - production estaba stale porque el deploy de commit `764faf6...` fallaba al construir con contexto recortado;
  - `docker/Dockerfile` espera contexto repo root y hace `COPY rtlab_autotrader/...`;
  - con `rootDirectory=/rtlab_autotrader`, Docker no podia ver rutas como `/rtlab_autotrader/rtlab_config.yaml.example`.
- Limites:
  - no se tocaron codigo de producto, backend source, Dockerfile, package files, Vercel settings, Railway variables/secrets, DB, branch protection ni RTLOPS-69 Slice 3;
  - `RTLOPS-106` sigue abierto como deuda externa de Vercel Git Integration / `routes-manifest-deterministic`;
  - `RTLOPS-107` sigue siendo workaround temporal de previews prebuilt, no fix definitivo de Git Integration.

## RTLOPS-112 - QA autenticado read-only del preview protegido - 2026-05-04

- Estado real:
  - `RTLOPS-108B` confirmo que el preview protegido carga app real con Vercel Automation Bypass;
  - `RTLOPS-112` retoma el QA autenticado con usuario `viewer` del entorno preview/staging;
  - los secrets esperados viven en GitHub Actions: `VERCEL_AUTOMATION_BYPASS_SECRET`, `RTLAB_TEST_USER_EMAIL`, `RTLAB_TEST_USER_PASSWORD`.
- Alcance:
  - se extiende solo el workflow administrativo `RTLOPS-109A Protected Preview QA`;
  - se agrega un modo manual `run_authenticated_qa` para login viewer read-only;
  - el reporte autenticado valida sesion viewer, rutas UI, APIs read-only y guardrails visibles en Portfolio/Execution;
  - no guarda `storageState` en repo y no imprime credenciales ni cookies.
- Limites:
  - no ejecuta ordenes, no modifica datos y no hace clicks finales en acciones sensibles;
  - no toca producto, backend, package files, Next/PostCSS, Vercel settings, Railway, produccion, branch protection ni RTLOPS-69 Slice 3;
  - `RTLOPS-106` sigue abierto por la deuda externa de Vercel Git Integration.

## RTLOPS-111 - Redirect/cookie en QA protegido de preview - 2026-05-04

- Estado real:
  - se crea `RTLOPS-111` como follow-up de `RTLOPS-110`;
  - el run `RTLOPS-109A Protected Preview QA` `25301512052` encontro el secret de bypass sin exponerlo;
  - todas las rutas devolvieron `307` con `Set-Cookie=true`, `vercel_sso=false` y `access_status=inconclusive`.
- Ajuste:
  - el probe HTTP administrativo ahora mantiene un cookie jar en memoria;
  - captura `Set-Cookie` sin imprimir valores;
  - sigue redirects de Vercel Protection Bypass hasta obtener la respuesta final;
  - clasifica `app` solo si obtiene HTML/app sin SSO.
- Limites:
  - no toca producto, backend, package files, Next/PostCSS, Vercel settings, Railway, produccion, branch protection, secrets ni RTLOPS-69 Slice 3;
  - `RTLOPS-106` sigue abierto por la deuda externa de Vercel Git Integration.

## RTLOPS-109A - QA protegido de preview con Vercel Automation Bypass - 2026-05-04

- Estado real:
  - se crea `RTLOPS-110` para instalar un workflow administrativo manual-only de QA read-only contra previews protegidos;
  - `RTLOPS-108` quedo bloqueado porque el preview READY de `RTLOPS-107` responde `401` por Vercel Deployment Protection / SSO;
  - `VERCEL_AUTOMATION_BYPASS_SECRET` existe como secret de GitHub Actions y solo puede consumirse dentro de un workflow.
- Alcance:
  - workflow `RTLOPS-109A Protected Preview QA`;
  - usa headers oficiales `x-vercel-protection-bypass` y `x-vercel-set-bypass-cookie`;
  - ejecuta probe HTTP read-only y, si la app carga, navegacion Playwright read-only de pantallas principales;
  - sube artifact con resultados sin imprimir secretos.
- Limites:
  - no toca codigo de producto, backend, Vercel settings, Railway, produccion, package files, Next/PostCSS, branch protection ni RTLOPS-69 Slice 3;
  - no cierra `RTLOPS-106`, que sigue abierto por la deuda externa de Vercel Git Integration.

## RTLOPS-107 - Prebuilt Preview Deploy oficial temporal - 2026-05-04

- Estado real:
  - se crea `RTLOPS-107` para formalizar un workflow administrativo de preview prebuilt mientras `RTLOPS-106` sigue abierto;
  - `RTLOPS-106` reproduce el fallo de Vercel Git Integration en proyectos actuales y sandbox con `routes-manifest-deterministic.json`;
  - el workaround temporal aceptado es `vercel build` + `vercel deploy --prebuilt --archive=tgz --target=preview`.
- Alcance:
  - workflow manual-only `RTLOPS-107 Prebuilt Preview Deploy`;
  - acepta `target_ref` configurable y solo permite `vercel_target=preview`;
  - valida `npm ci`, `npm audit --audit-level=moderate`, `npm run lint`, `npm run typecheck`, `npm run build` y `npm run test:smoke:live-console` antes del prebuilt deploy;
  - publica URL/Deployment ID/estado en logs y artifact diagnostico.
- Limites:
  - es workaround operativo temporal, no fix definitivo de Vercel Git Integration;
  - no toca codigo de producto, backend, Vercel settings productivos, Railway, produccion, branch protection, Next/PostCSS, package files ni RTLOPS-69 Slice 3;
  - `RTLOPS-106` sigue abierto esperando respuesta Vercel/Community.

## RTLOPS-105 - QA/UI lint Alerts - 2026-05-02

- Estado real:
  - se crea `RTLOPS-105` para limpiar el error ESLint restante en `Alerts`;
  - se documenta y acota la carga inicial client-side de alertas/logs para cumplir `react-hooks/set-state-in-effect`;
  - `npm run lint` repo-wide queda en PASS.
- Alcance:
  - solo `rtlab_dashboard/src/app/(app)/alerts/page.tsx`;
  - no cambia comportamiento funcional, contratos API, backend, Vercel, Railway, Next/PostCSS, package files ni workflows;
  - no toca PR #51 ni abre RTLOPS-69 Slice 3.
- Validacion:
  - lint focalizado de `Alerts` -> PASS;
  - `npm run lint` -> PASS;
  - `npm run typecheck` -> PASS;
  - `npm run build` -> PASS.

## RTLOPS-104 - QA/UI lint Backtests y Portfolio - 2026-05-01

- Estado real:
  - se crea `RTLOPS-104` para limpiar errores ESLint preexistentes en `Backtests` y `Portfolio`;
  - se corrige el copy JSX con comillas sin escapar en `Backtests`;
  - se evita llamar `Date.now()` durante render en `Portfolio` y se mantiene el cooldown con reloj de cliente acotado.
- Alcance:
  - solo frontend en `rtlab_dashboard`;
  - solo `backtests/page.tsx` y `portfolio/page.tsx`;
  - no cambia contratos API, backend, Vercel, Railway, Next/PostCSS, package files ni workflows;
  - no toca PR #51 ni abre RTLOPS-69 Slice 3.
- Validacion:
  - lint focalizado de `Backtests` y `Portfolio` -> PASS;
  - `npm run typecheck` -> PASS;
  - `npm run build` -> PASS;
  - `npm run lint` repo-wide sigue fallando por `alerts/page.tsx`, deuda fuera de alcance de este bloque.

## RTLOPS-103 - QA/UI layout de charts del dashboard - 2026-05-01

- Estado real:
  - se crea `RTLOPS-103` para corregir warnings visibles de Recharts/layout durante el build del dashboard;
  - se agregan dimensiones iniciales explicitas a `ResponsiveContainer` en charts de `Execution`, `Portfolio`, `Risk` y `Backtests`;
  - el build deja de emitir los warnings `width(-1)` / `height(-1)` de Recharts.
- Alcance:
  - solo layout/SSR sizing de charts;
  - no cambia contratos API, datos, comportamiento funcional ni logica de trading;
  - no toca PR #51, Vercel settings, Railway, backend, Next/PostCSS, package files ni workflows de deploy.
- Validacion:
  - `npm run typecheck` -> PASS;
  - `npm run build` -> PASS sin warnings Recharts;
  - lint focalizado disponible, pero falla por errores preexistentes no relacionados en `backtests` y `portfolio`.

## RTLOPS-101 - parking tecnico controlado - 2026-05-01

- Estado real:
  - PR #51 sigue `OPEN / MERGEABLE / UNSTABLE`;
  - head conocido validado: `81109fce0f4c5885553e761cc0489d0f03ee53f4`;
  - `npm ci`, `npm audit --audit-level=moderate`, `npm run build`, `npm run typecheck` y prebuilt preview deploy pasaron;
  - Vercel Git Integration automatico sigue fallando por un issue externo de finalizacion/path sobre `routes-manifest-deterministic.json`.
- Evidencia temporal:
  - prebuilt preview READY: `https://bot-trading-avvj2m1wc-ranquel-tech-lab.vercel.app`;
  - deployment ID: `dpl_H5FvyppBfXAbZSCQgdgro5PwH8n1`.
- Triggers obligatorios para retomar RTLOPS-101:
  - Vercel Git Integration empieza a pasar;
  - Vercel/Community responde con una solucion concreta;
  - PR #51 bloquea otro bloque real de producto;
  - antes de cualquier release/canary/staging serio/produccion;
  - despues de 5 PRs mergeadas a `main` o 7 dias corridos, lo que ocurra primero;
  - si `npm audit` vuelve a mostrar la vulnerabilidad que PR #51 corregia.

## RTLOPS-101 - PR #51 refreshed con main + prebuilt PASS - 2026-04-30

- Resultado confirmado:
  - se preservo el merge local accidental en una rama backup local no pusheada;
  - se creo una rama limpia desde `origin/feature/rtlops-101-dashboard-npm-audit-fix`;
  - se integro `origin/main` sin conflictos;
  - PR #51 quedo actualizada en `0498db52e54d59381ab14187724407976c42bc49`.
- Validacion local:
  - `npm ci` -> PASS, `found 0 vulnerabilities`;
  - `npm audit --audit-level=moderate` -> PASS, `found 0 vulnerabilities`;
  - `npm run build` -> PASS con warnings Recharts ya conocidos/no fatales.
- Validacion prebuilt:
  - workflow manual `RTLOPS-101 Prebuilt Preview Deploy` run `25149961717` -> `success`;
  - preview generado: `https://bot-trading-f34mynb26-ranquel-tech-lab.vercel.app`;
  - deployment id inspeccionado: `dpl_8oR67BHgi2jZ2LpV6Dxh6ExPLPRK`;
  - estado Vercel prebuilt: `Ready`.
- Estado:
  - Vercel Git Integration automatico de PR #51 sigue fallando en los 4 proyectos y queda clasificado como problema externo/finalization;
  - PR #51 sigue abierta/no mergeada;
  - RTLOPS-101 sigue In Progress hasta decision explicita de merge/cierre.

## RTLOPS-102 - QA/UI mojibake cleanup dashboard - 2026-04-30

- Estado real:
  - se crea `RTLOPS-102` para corregir mojibake visible en el dashboard;
  - se corrigen textos/copy afectados en `Settings` y `Strategies`;
  - se corrigen ocurrencias historicas en docs/truth.
- Alcance:
  - solo copy/labels visibles y texto documental;
  - no cambia comportamiento funcional;
  - no toca backend, Vercel, Railway, Next/PostCSS ni package files;
  - no toca PR #51 ni abre RTLOPS-69 Slice 3.
- Validacion local:
  - `npx next typegen` PASS tras limpiar `.next`;
  - `npm run typecheck` PASS;
  - `npx eslint "src/app/(app)/settings/page.tsx" "src/app/(app)/strategies/page.tsx"` PASS;
  - `npm run build` PASS.

## RTLOPS-101 - prebuilt preview deploy PASS - 2026-04-30

- Resultado confirmado:
  - workflow manual `RTLOPS-101 Prebuilt Preview Deploy` run #1 termino en `success`;
  - `target_ref=feature/rtlops-101-dashboard-npm-audit-fix`;
  - commit diagnosticado: `a2ff740279a8a78f3001c879d9dab64b66a17dfa`;
  - preview generado: `https://bot-trading-8ev1013f3-ranquel-tech-lab.vercel.app`.
- Validacion del workflow:
  - `npm ci` -> PASS;
  - `npm audit --audit-level=moderate` -> PASS;
  - `npm run build` -> PASS;
  - `vercel build` -> PASS;
  - `vercel deploy --prebuilt --archive=tgz --target=preview` -> PASS.
- Conclusion tecnica:
  - el codigo de PR #51 puede desplegarse correctamente como preview cuando se usa el Build Output API generado por GitHub Actions;
  - el fallo restante queda aislado al Vercel Git Integration automatico/finalization;
  - Git Integration sigue fallando con `ENOENT` sobre `/vercel/path0/.next/routes-manifest-deterministic.json`.
- Estado:
  - PR #51 sigue abierta/no mergeada hasta decision final;
  - PR #54 no debe mergearse como fix;
  - PR #55 queda reemplazada operativamente por el workflow instalado en main via PR #56;
  - RTLOPS-101 sigue In Progress hasta decidir camino de merge/cierre.

## RTLOPS-101 - instalacion workflow prebuilt preview en main - 2026-04-30

- Estado real:
  - se abre PR administrativa contra `main` para instalar `.github/workflows/rtlops101-prebuilt-preview-deploy.yml`;
  - el workflow debe existir en la rama default para que `workflow_dispatch` pueda ejecutarse de forma confiable;
  - permite apuntar `target_ref=feature/rtlops-101-dashboard-npm-audit-fix` sin tocar PR #51.
- Objetivo:
  - probar si `vercel deploy --prebuilt --target=preview` evita el fallo de finalizacion de Vercel Git Integration;
  - aislar si el problema esta en el flujo automatico Git Integration o tambien en el deploy del Build Output API generado por Actions.
- Reglas:
  - workflow manual-only (`workflow_dispatch`);
  - usa Node 22;
  - corre `npm ci`, `npm audit --audit-level=moderate`, `npm run build`, `vercel pull`, `vercel build` y opcionalmente `vercel deploy --prebuilt --archive=tgz --target=preview`;
  - no usa `--prod`, no promueve aliases y no cambia settings Vercel.
- Limite honesto:
  - esto no toca producto, dependencias, backend, UI funcional, `.vercelignore`, `.env`, Railway, RTLOPS-69 ni RTLOPS-68;
  - RTLOPS-101 sigue In Progress hasta ejecutar el workflow y clasificar el resultado.

## RTLOPS-101 - workflow diagnostico manual Vercel build Linux - 2026-04-30

- Ajuste diagnostico v2:
  - el primer run Linux confirmo `npm ci`, `npm audit --audit-level=moderate` y `npm run build` en PASS;
  - confirmo `.next/routes-manifest.json` y `.next/required-server-files.json`;
  - confirmo que `.next/routes-manifest-deterministic.json` falta en el output Next puro;
  - con secrets Vercel presentes, `vercel build` fallo prematuramente con `Error: spawn sh ENOENT` durante `npm install`;
  - este ajuste mueve `vercel pull` y `vercel build` a la raiz del repo para respetar la Root Directory remota `rtlab_dashboard`;
  - agrega preflight explicito de shell/PATH y conserva artifacts reducidos de diagnostico.
- Estado real de este bloque administrativo:
  - se agrega `.github/workflows/diagnose-vercel-build-rtlops101.yml`;
  - el workflow es manual-only (`workflow_dispatch`) y debe existir en la rama default para poder ejecutarse de forma confiable desde GitHub Actions;
  - permite diagnosticar `RTLOPS-101` apuntando `target_ref=feature/rtlops-101-dashboard-npm-audit-fix` en `ubuntu-latest`;
  - ejecuta `npm ci`, `npm audit --audit-level=moderate`, `npm run build` e inspecciona manifests `.next`;
  - si existen `VERCEL_TOKEN`, `VERCEL_ORG_ID` y `VERCEL_PROJECT_ID`, puede correr `npx vercel@latest build` sin desplegar.
- Regla de seguridad:
  - no toca producto, backend, UI funcional, dependencias, `next.config`, Vercel settings, Railway, preserve, ramas historicas ni PRs viejas;
  - no ejecuta `vercel deploy` ni `vercel deploy --prebuilt`;
  - no sube `.env`, `.vercel` ni secretos como artefactos.
- Limite honesto:
  - no resuelve todavia el ERROR remoto de Vercel;
  - `RTLOPS-101` sigue parcial/In Progress hasta ejecutar el workflow y clasificar el resultado;
  - `RTLOPS-69` y `RTLOPS-68` no cambian.
- Proximo paso exacto:
  - mergear esta PR administrativa;
  - ejecutar `Actions -> RTLOPS-101 Diagnose Vercel Build` con `target_ref=feature/rtlops-101-dashboard-npm-audit-fix` y `run_vercel_build=true`;
  - clasificar si falla npm/build Linux, falta el manifest deterministic, `vercel build` reproduce ENOENT, genera output correcto o faltan secrets.

## RTLOPS-101 / RTLOPS-69 QA - npm audit dashboard post Playwright - 2026-04-29

- Estado real confirmado en esta rama:
  - se corrige la deuda `npm audit` detectada despues de `RTLOPS-100`;
  - baseline inicial: `npm.cmd audit --audit-level=moderate` -> FAIL con 9 vulnerabilities, 3 moderate y 6 high;
  - baseline final: `npm.cmd audit --audit-level=moderate` -> PASS, `found 0 vulnerabilities`.
- Cambios de dependencias frontend:
  - `next` pasa de `16.1.6` a `16.2.3`;
  - `eslint-config-next` pasa de `16.1.6` a `16.2.3`;
  - `npm audit fix` sin `--force` actualiza transitivas de tooling como `vite`, `rollup`, `picomatch`, `minimatch`, `brace-expansion`, `flatted` y `ajv`;
  - se agrega override acotado `postcss=8.5.12` para evitar el `postcss<8.5.10` anidado bajo `next`.
- Regla de seguridad:
  - no se uso `npm audit fix --force`;
  - no se toco backend, UI funcional, Playwright smoke, Railway/Vercel config, preserve ni ramas historicas.
- Validacion real del slice:
  - `npm.cmd audit --audit-level=moderate` -> PASS;
  - `npm.cmd run typecheck` -> PASS despues de limpiar `.next` regenerable por tipos viejos de Next;
  - `npm.cmd run lint -- playwright.config.ts tests/playwright/live-console-readonly.spec.ts` -> PASS;
  - `npm.cmd run test:smoke:live-console` -> PASS, 1 test;
  - `npm.cmd run build` -> PASS.
- Limite honesto:
  - `next@16.2.4` fue descartado para este PR porque los previews Vercel fallaban en finalizacion/output con `ENOENT` sobre `.next/routes-manifest-deterministic.json`;
  - `next@16.1.6` fue descartado porque reintroduce una vulnerabilidad `high` directa en `next`;
  - `next@16.2.3` queda como version intermedia localmente validada; falta validar previews Vercel despues del push;
  - el smoke/build siguen emitiendo warnings no fatales de Recharts por dimensiones en entorno headless;
  - `RTLOPS-69` y `RTLOPS-68` siguen parciales.

## RTLOPS-100 / RTLOPS-69 Slice 2 - smoke visual Playwright de consola read-only - 2026-04-29

- Estado real confirmado en esta rama:
  - se agrega un smoke Playwright minimo para `Execution`;
  - el smoke verifica que la "Consola Live del Bot - solo lectura" renderiza la surface esencial de `RTLOPS-99`;
  - valida titulo, estado read-only/no crea ordenes, policy Paper `single-intent seguro`, observabilidad multi-symbol, tabla por simbolo y razones de bloqueo;
  - valida que dentro de esa consola no haya botones operativos ni combobox/selector paralelo.
- Contratos usados por el smoke:
  - `rtlops97/v1` como contrato de `order_intents_by_symbol`;
  - `rtlops96/v1` como scope heredado del bot;
  - `rtlops68-slice3/v1` como policy Paper.
- Regla de producto:
  - este slice es QA/observabilidad, no producto nuevo;
  - no crea ordenes, no cancela ordenes, no activa live actions, no agrega drill-down/event feed y no toca backend;
  - las fixtures de red viven solo dentro de Playwright para estabilizar el smoke read-only.
- Limite honesto:
  - no cierra todo `RTLOPS-69`;
  - no cierra todo `RTLOPS-68`;
  - no toca Railway/Vercel config, preserve, ramas historicas, PRs viejas, risk/scorecard/portfolio ni `Strategy Truth/Evidence`.
- Validacion real del slice:
  - `npm.cmd run typecheck` -> PASS;
  - `npm.cmd run lint -- playwright.config.ts tests/playwright/live-console-readonly.spec.ts` -> PASS;
  - `npm.cmd run test:smoke:live-console` -> PASS, 1 test.

## RTLOPS-99 / RTLOPS-69 Slice 1 - Live Console read-only por simbolo - 2026-04-29

- Estado real confirmado en esta rama:
  - `Execution` agrega una primera surface "Consola Live del Bot - solo lectura";
  - consume `GET /api/v1/bots/{bot_id}/order-intents-by-symbol?mode=...`;
  - muestra el contrato `rtlops97/v1`, bot, modo operativo, scope heredado, status agregado, policy Paper e intents por simbolo;
  - expone `selected_strategy_id`, `source`, `action`, `side`, `net_decision_key`, `decision_log_scope`, `blocking_reasons` y `paper_execution_status` por simbolo.
- Resiliencia de UI:
  - si falla solo el endpoint `order-intents-by-symbol`, la consola read-only muestra error propio;
  - policy, scope, lifecycle y decision log del bot seleccionado no se limpian por un fallo aislado del nuevo read model.
- Regla de producto:
  - la consola es observabilidad read-only;
  - no crea ordenes, no cancela ordenes, no modifica lifecycle y no activa live actions;
  - no agrega selector paralelo de simbolos ni edita scope, estrategias o policy Paper.
- Relacion con slices previos:
  - reutiliza RTLOPS-94 para scope heredado del bot;
  - reutiliza RTLOPS-68 Slice 1 para decision neta por simbolo;
  - reutiliza RTLOPS-97 para el read model `order_intents_by_symbol`;
  - reutiliza RTLOPS-98 para mostrar `single_intent_safe` y `multi_symbol_per_cycle_enabled=false`.
- Limite honesto:
  - no cierra todo `RTLOPS-69`;
  - no cierra todo `RTLOPS-68`;
  - no implementa live console con acciones, lifecycle completo, ejecucion multi-order, Railway/Vercel, risk/scorecard/portfolio ni `Strategy Truth/Evidence`.
- Validacion real del slice:
  - `npm.cmd run typecheck` -> PASS;
  - `npm.cmd run lint -- "src/app/(app)/execution/page.tsx" "src/lib/types.ts"` -> PASS.

## RTLOPS-98 / RTLOPS-68 Slice 3 - policy Paper multi-symbol - 2026-04-28

- Estado real confirmado en esta rama:
  - Paper queda formalizado con policy explicita `rtlops68-slice3/v1`;
  - la policy vive en `config/policies/runtime_controls.yaml` bajo `runtime_controls.paper_execution`;
  - `multi_symbol_per_cycle_enabled=false`;
  - `max_symbols_per_cycle=1` y `max_intents_per_cycle=1`;
  - `order_intents_by_symbol` puede observar multiples simbolos, pero eso no habilita ejecucion multi-order por ciclo.
- Decision Paper:
  - se mantiene `single_intent_safe`;
  - si hay multiples intents accionables, solo el primer intent queda `execution_actionable`;
  - los demas quedan como `observability_only` con `paper_multi_symbol_execution_disabled` y caps excedidos auditables.
- Limite honesto:
  - no cierra todo `RTLOPS-68`;
  - no abre `RTLOPS-69`;
  - no activa Paper multi-symbol por ciclo;
  - no implementa multi-order live, live console, lifecycle completo, Railway/Vercel, risk/scorecard/portfolio ni `Strategy Truth/Evidence`.
- Validacion real del slice:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS;
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops68-slice3'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops97 or rtlops68 or rtlops94" -q` -> PASS, 17 tests.

## RTLOPS-97 / RTLOPS-68 Slice 2 - read model order_intents_by_symbol - 2026-04-28

- Estado real confirmado en esta rama:
  - se agrega el contrato read-only `rtlops97/v1` para consultar `order_intents_by_symbol`;
  - endpoint nuevo: `GET /api/v1/bots/{bot_id}/order-intents-by-symbol?mode=paper|shadow|testnet|live`;
  - el read model deriva de `runtime.net_decision_by_symbol`, `runtime.items` y `bot_operation_scope_gate(...)`;
  - el contrato no persiste intents nuevos, no crea ordenes y no activa ejecucion multi-order;
  - cada simbolo tiene como maximo un intent neto auditable con `selected_strategy_id`, `net_decision_key`, `decision_log_scope`, `source=bot_runtime_net_decision`, `status` y `blocking_reasons`.
- Decision Paper:
  - Paper conserva `single_intent_safe`;
  - `multi_symbol_per_cycle_enabled=false`;
  - `order_intents_by_symbol` queda como read model/observabilidad, no como activacion de multi-order por ciclo.
- Fail-closed:
  - bloquea si el scope operativo heredado del bot no sostiene el simbolo;
  - bloquea si falta runtime o `runtime.guardrails.execution_ready=false`;
  - bloquea si falta estrategia seleccionada, side valido o simbolo permitido por guardrails.
  - conserva `404` para `bot_id` inexistente en vez de convertirlo en payload `200 blocked`.
- Limite honesto:
  - no cierra todo `RTLOPS-68`;
  - no abre `RTLOPS-69`;
  - no implementa live console, lifecycle completo, ejecucion multi-order live, risk/scorecard/portfolio ni `Strategy Truth/Evidence`.
- Validacion real del slice:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS;
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops97'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops97 or rtlops68 or rtlops94" -q` -> PASS, 16 tests.

## RTLOPS-68 Slice 1 - decision neta por simbolo como intent operativo - 2026-04-28

- Estado real confirmado en esta rama:
  - `runtime.net_decision_by_symbol` ya no queda solo como surface informativa para bots;
  - cuando hay `active_bot_id`, el submit operativo deriva el intent desde el runtime canonico del bot y su `net_decision_by_symbol`;
  - cuando un start operativo no trae `bot_id`, el runtime limpia cualquier `active_bot_id` previo y vuelve a strategy-only/principal strategy mode;
  - la fuente del intent queda marcada como `source=bot_runtime_net_decision`;
  - el intent incluye `net_decision_key`, `decision_log_scope`, `selected_strategy_id`, `candidate_intents_count` y `suppressed_intents_count`;
  - si el runtime del bot no esta listo, el submit bloquea fail-closed con `blocking_reasons` en vez de volver a una estrategia primaria paralela.
- Regla canonica resultante:
  - un bot multi-symbol produce una decision neta por simbolo;
  - una operacion con bot activo no debe multiplicar ordenes por cada estrategia candidata del pool;
  - la estrategia seleccionada por simbolo es la que alimenta el intent operativo;
  - el camino legacy de estrategia primaria queda solo como fallback cuando no existe contexto de bot activo.
- Limite honesto del slice:
  - no cierra todo `RTLOPS-68`;
  - no abre live console;
  - no implementa ejecucion multi-order nueva;
  - no toca Binance adapters, Railway, Vercel, risk, scorecard, portfolio ni `strategy truth/evidence`.
- Validacion real del slice:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS;
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops68'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops68_runtime_order_intent_uses_net_decision_by_symbol_without_strategy_duplication or rtlops68_runtime_order_intent_fails_closed_when_bot_runtime_is_not_ready or bot_runtime_surface_is_canonical_and_traceable or bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope or rtlops94_operation_modes_inherit_bot_scope or rtlops94_operation_preflight_rejects_parallel_manual_symbol or rtlops94_operation_scope_blocks_empty_or_over_cap_scope or rtlops94_operation_preflight_rejects_invalid_mode_even_with_valid_environment or rtlops94_operation_scope_blocks_unresolved_max_active_symbols_without_typeerror" -q` -> PASS;
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops68'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops68 or rtlops94" -q` -> PASS, 11 tests;
  - `npm.cmd run typecheck` -> PASS.

## RTLOPS-94 - Shadow/Paper/Testnet/Live heredan Trading Universe Scope del bot - 2026-04-26

- Estado real confirmado en esta rama:
  - `RTLOPS-94` usa la fundacion `rtlops96/v1` ya mergeada para resolver el scope operativo del bot;
  - `Shadow`, `Paper`, `Testnet` y `Live` consumen `scope_source=bot_runtime_scope`;
  - `POST /api/v1/execution/preflight`, `POST /api/v1/execution/orders` y `POST /api/v1/bot/start` aplican un gate de scope operativo antes de operar;
  - `Execution` muestra el `Scope operativo heredado del bot` como surface read-only;
  - no se agrega selector manual paralelo en operacion.
- Regla canónica resultante:
  - el bot define y persiste el `Trading Universe Scope`;
  - research mantiene su logica separada (`manual` o `bot_inherited` segun contexto);
  - operacion solo puede usar simbolos dentro del subset elegible heredado del bot;
  - un simbolo manual distinto al scope del bot no se convierte en fuente paralela y bloquea fail-closed.
- Fail-closed operativo:
  - bloquea si falta `bot_id`;
  - bloquea si `payload.mode` fue enviado pero no pertenece a `shadow/paper/testnet/live`;
  - bloquea si el contrato `rtlops96/v1` no puede resolverse;
  - bloquea si el scope esta vacio;
  - bloquea si `max_active_symbols` no puede resolverse a entero positivo;
  - bloquea si `symbols[]` supera `max_active_symbols`;
  - bloquea si `max_active_symbols` excede el cap inicial de `12`;
  - bloquea si falta `market_family` o `quote_asset`;
  - bloquea si hay simbolos inelegibles;
  - expone `blocking_reasons` auditables.
- Validacion real del bloque:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS;
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops94'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope or rtlops94_operation_modes_inherit_bot_scope or rtlops94_operation_preflight_rejects_parallel_manual_symbol or rtlops94_operation_scope_blocks_empty_or_over_cap_scope or rtlops94_operation_preflight_rejects_invalid_mode_even_with_valid_environment or rtlops94_operation_scope_blocks_unresolved_max_active_symbols_without_typeerror" -q` -> PASS;
  - `npm.cmd run typecheck` -> PASS;
  - `npm.cmd run lint -- "src/app/(app)/execution/page.tsx" "src/lib/types.ts"` -> PASS;
  - `npm.cmd run build` -> PASS.
- Limite honesto del bloque:
  - no abre una live console nueva;
  - no rehace `Execution` completa;
  - no mezcla `risk`, `scorecard`, `portfolio` ni `strategy truth/evidence`;
  - no cambia research fuera de reafirmar su separacion conceptual.

## RTLOPS-96 - fundación canónica runtime / universe scope / eligibility en Execution - 2026-04-26

- Estado real confirmado en esta rama:
  - `RTLOPS-92` ya no queda solo como decisión documental: el repo expone un contrato operativo nuevo `rtlops96/v1` en `GET /api/v1/bots/{bot_id}/scope-eligibility`;
  - el carrier nuevo no introduce selector manual nuevo en `Execution`;
  - la fuente canónica del scope operativo sigue siendo el bot:
    - `persisted_scope_owner=bot_registry`
    - `scope_source=bot_runtime_scope`
    - `strategy_role=consumer_only`;
  - research sigue pudiendo consumir:
    - `manual`
    - `bot_inherited`;
  - operación queda explícitamente cerrada sobre:
    - `shadow`
    - `paper`
    - `testnet`
    - `live`;
  - `Execution` agrega una surface mínima read-only de `Runtime scope / eligibility` para mostrar:
    - ownership
    - universe efectivo
    - market family
    - quote asset
    - símbolos configurados
    - elegibles / inelegibles
    - bloqueos por símbolo;
  - no se agrega ningún PATCH nuevo ni selector paralelo escondido en operación.
- Regla canónica resultante:
  - el bot persiste el scope operativo;
  - research puede heredar ese scope o trabajar manual según contexto ya cerrado por `RTLOPS-93`;
  - operación no vuelve a decidir símbolos por fuera del bot;
  - la elegibilidad operativa visible se deriva de:
    - `multi_symbol`
    - `strategy_eligibility`
    - `runtime`
    - `lifecycle_operational`.
- Límite honesto del bloque:
  - no cierra toda `RTLOPS-94`;
  - no rehace `Execution`;
  - no abre console live nueva;
  - no mezcla `risk`, `portfolio` o `strategy truth/evidence`.
- Siguiente paso exacto recomendado:
  - seguir con `RTLOPS-94` ya apoyándose en este carrier canónico;
  - mantener fuera del siguiente bloque:
    - selector manual operativo paralelo
    - rewrite transversal de `Execution`
    - scorecard/risk.

## RTLOPS-93 - selector reusable Bot vs Estrategia + Trading Universe Scope auditable en Batch/Beast - 2026-04-25

- Estado real confirmado en esta rama:
  - `Research Batch` y `Beast` ya no dependen solo de `symbol` puntual para research;
  - el backend ya canoniza un contrato `rtlops93/v1` de scope research via:
    - `entity_type`
    - `entity_id`
    - `scope_source`
    - `strategy_ids`
    - `universe_name`
    - `market_family`
    - `quote_asset`
    - `symbols_requested`
    - `symbols_effective`
    - `eligible_symbols`
    - `ineligible_symbols`
    - `blocking_reasons`;
  - `POST /api/v1/research/dataset-preflight` ya devuelve ese scope auditable dentro de `research_scope`;
  - `POST /api/v1/research/mass-backtest/start` y `POST /api/v1/research/beast/start` ya consumen el mismo carrier canonico:
    - `entity_type=bot|strategy`
    - `entity_id`
    - `strategy_ids`
    - `symbols[]`
    - `universe_name`;
  - cuando `entity_type=bot`:
    - el backend resuelve el scope persistido del bot como fuente principal;
    - valida que `strategy_ids` pertenezcan al pool del bot;
    - bloquea simbolos fuera del scope del bot;
  - cuando `entity_type=strategy`:
    - research acepta scope portable manual;
    - en `crypto` exige `universe_name` para multi-simbolo portable;
    - no finge persistencia operativa nueva fuera del modelo bot-centrico existente;
  - `MassBacktestEngine` ya ejecuta research multi-simbolo real:
    - multiplica tareas por `variantes x folds x simbolos`;
    - ejecuta cada fold por simbolo;
    - agrega resumen canonico por fold sin perder trazabilidad por simbolo;
  - el preflight ya integra readiness real por todo el scope:
    - `dataset_hashes`
    - `dataset_manifest_paths`
    - `bootstrap_commands_by_symbol`
    - `data_providers_by_symbol`;
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx` ya consume esa verdad backend y expone:
    - selector explicito `Correr Bot` / `Correr Estrategias`;
    - `Trading Universe Scope` multi-simbolo reusable para `Batch/Beast`;
    - busqueda
    - chips
    - contador
    - lista seleccionada
    - universe crypto portable
    - elegibles / no elegibles / bloqueos del preflight.
- Regla canonica resultante:
  - `Quick` sigue single-symbol;
  - `Research Batch` y `Beast` ya soportan multi-simbolo real y auditable sobre el mismo contrato research;
  - el cap inicial del scope research reutiliza `BOT_MAX_LIVE_SYMBOLS` via `RESEARCH_SCOPE_MAX_SYMBOLS`;
  - no hay pruning silencioso:
    - si el scope supera limites o mezcla simbolos incompatibles, el backend lo deja visible y lo bloquea fail-closed;
  - `Backtests` no decide reglas de scope:
    - solo envia carrier canonico
    - renderiza el payload auditable;
  - `Shadow / Paper / Testnet / Live` siguen fuera de este bloque.
- Validacion real ejecutada:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "research_mass_backtest_start_rejects_missing_dataset or research_dataset_preflight_ready_payload or research_dataset_preflight_missing_blocks_cleanly or research_dataset_preflight_blocks_synthetic_even_with_real_dataset or research_dataset_preflight_bot_scope_multi_symbol_payload or research_dataset_preflight_strategy_scope_blocks_symbols_outside_universe or research_mass_backtest_start_forwards_bot_id or research_beast_endpoints_smoke or research_beast_start_rejects_missing_dataset or research_beast_start_accepts_orderflow_toggle" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> PASS en la rama limpia de integracion reconstruida desde `main`;
  - el `FAIL` previo no reprodujo como error del slice y quedo acotado a estado local/transitorio de artefactos Next (`.next`) y espacio en disco de la worktree stacked, no al codigo de `RTLOPS-93`.
- Decision de integracion para `44a023e`:
  - entra completo dentro de `RTLOPS-93`;
  - fija el preflight de arquitectura (`RTLOPS-91/92/93/94`) que este slice implementa de forma efectiva;
  - no adelanta producto nuevo de `RTLOPS-94`, solo deja asentada la separacion canonica `Entidad / Trading Universe Scope / Modo`.
- Limite honesto del bloque:
  - no abre `RTLOPS-94`;
  - no implementa `Shadow / Testnet / Live`;
  - no funda un CRUD global de universos;
  - no reescribe `Bot Registry` ni `Strategy Registry`;
  - no cambia `Quick`.
- Siguiente bloque exacto recomendado:
  - abrir `RTLOPS-94` solo para reutilizar el `Trading Universe Scope` del bot en `Shadow / Paper / Testnet / Live`;
  - mantener fuera de ese bloque:
    - refactor transversal
    - nueva UX de research
    - CRUD global de symbol sets salvo evidencia nueva.

## Preflight de arquitectura multi-simbolo - entidad, scope y modos - 2026-04-25

- Estado real confirmado en esta rama:
  - el `Bot Registry` ya persiste la base canonica del scope operativo por bot via:
    - `universe_name`
    - `universe`
    - `max_live_symbols`
    - `pool_strategy_ids`
    - `strategy_eligibility_by_symbol`
    - `strategy_selection_by_symbol`;
  - `Strategies` ya es la surface canonica para editar ese scope del bot;
  - `Execution` ya es la surface canonica para operar el bot y consumir:
    - `policy_state`
    - `runtime`
    - `lifecycle`
    - `lifecycle_operational`;
  - `Backtests` ya quedo ordenada por modos, pero `Research Batch` y `Beast` todavia entran por `symbol` puntual aunque acepten `bot_id` como contexto;
  - `MassBacktestEngine` ya soporta `universe` en config, pero `ResearchMassBacktestStartBody` y `ResearchBeastStartBody` siguen expuestos en API/UI con carrier principal `symbol`;
  - `InstrumentUniverseService` ya resuelve universos/policies validos del catalogo, pero hoy no existe una entidad CRUD separada de `symbol set` reusable del usuario.
- Decision canonica resultante:
  - la separacion correcta del programa queda en tres dimensiones:
    - `Entidad`
      - `Bot`
      - `Estrategia`
    - `Trading Universe Scope`
      - `universe_name`
      - `symbols[]`
      - `market_family`
      - `quote_asset`
      - `max_active_symbols`
      - elegibilidad/preflight
    - `Modo`
      - `Quick`
      - `Research Batch`
      - `Beast`
      - `Shadow`
      - `Paper`
      - `Testnet`
      - `Live`;
  - no corresponde abrir primero una entidad global nueva tipo `symbol set registry`;
  - si corresponde fundar un contrato canonico reusable de `Trading Universe Scope`:
    - persistido dentro del `Bot` para operacion;
    - reusable como scope explicito en research;
  - `Strategy` queda como alpha portable que consume scope, pero no como duena persistente del universe operativo.
- Reglas operativas recomendadas:
  - `Quick`
    - sigue single-symbol;
  - `Research Batch`
    - debe aceptar multi-simbolo real sobre `Trading Universe Scope`;
    - puede correr sobre:
      - scope heredado de `Bot`
      - scope manual de research;
  - `Beast`
    - reutiliza exactamente el mismo scope y el mismo preflight de `Research Batch`;
  - `Shadow / Paper / Testnet / Live`
    - usan el scope persistido del bot;
    - no deben abrir un selector paralelo ad hoc dentro de `Execution`;
  - limites iniciales canonicos:
    - una sola `market_family` por scope;
    - una sola `quote_asset` por scope;
    - cap inicial de hasta `12` simbolos;
    - `Batch/Beast` requieren preflight sobre todo el scope;
    - en v1 no corresponde hacer pruning silencioso de simbolos invalidos.
- Linear alineada para este frente:
  - `RTLOPS-91`
    - `Entidad + Trading Universe Scope multi-símbolo reusable entre Research y Deploy`;
  - `RTLOPS-92`
    - `Definir contrato canónico Trading Universe Scope y reglas de elegibilidad por modo`;
  - `RTLOPS-93`
    - `Research Batch / Beast — selector reusable Bot vs Estrategia + multi-símbolo auditable`;
  - `RTLOPS-94`
    - `Shadow / Paper / Testnet / Live — reutilizar Trading Universe Scope del bot sin mezclar research con operación`.
- Siguiente bloque exacto recomendado:
  - no corresponde saltar directo a refactor masivo ni a live console;
  - corresponde programar primero `RTLOPS-93`, apoyandose en la decision ya cerrada por `RTLOPS-92`;
  - mantener fuera de ese bloque:
    - nueva entidad CRUD global de `symbol set`
    - cambios live pesados
    - refactor transversal de `Backtests`, `Strategies` o `Execution`.

## RTLOPS-90 - reordenamiento UX Backtests sin refactor masivo - 2026-04-25

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx` ya deja de presentar `Backtests` como megapantalla plana sin jerarquia;
  - la surface principal queda reordenada visualmente por modos reales de trabajo:
    - `Quick`
    - `Runs`
    - `Comparador Profesional`
    - `Research Batch`
    - `Beast / Infra`;
  - `Research Batch` y `Beast / Infra` ya no quedan mezclados dentro del mismo bloque principal;
  - el disparador de `Modo Bestia` ya no vive dentro de la operatoria principal de `Research Batch`, sino en su card propio de infra;
  - `Research Funnel y Trial Ledger` baja de jerarquia como auditoria secundaria;
  - `Detalle de Corrida (Strategy Tester)` queda marcado como secundario;
  - `Quick Backtest Legacy (Deprecado)` sigue disponible, pero queda fuera del flujo principal y al final de la pantalla.
- Regla canonica resultante:
  - `Backtests` ya no vende el mismo peso visual para:
    - corrida puntual
    - catalogo/comparacion de runs
    - research masivo
    - scheduler/infra
    - legacy;
  - `Runs` conserva el rol de catalogo operativo principal;
  - `Comparador Profesional` conserva el rol de analisis comparativo principal sobre runs;
  - `Research Batch` conserva:
    - configuracion
    - batches `BX`
    - leaderboard
    - variantes
    - shortlist;
  - `Beast / Infra` conserva:
    - policy/runtime hints
    - scheduler
    - budget governor
    - jobs recientes;
  - `Research Funnel`, `Detalle de Corrida` y `Legacy` quedan como surfaces secundarias/auditables y no como caminos principales.
- Dependencias backend reusadas y no reabiertas:
  - `POST /api/v1/research/dataset-preflight` sigue siendo la verdad canonica de prerequisitos para `Research Batch` y `Beast`;
  - no se reabre:
    - `MassBacktestCoordinator.dataset_preflight(...)`
    - `start_async(...)`
    - `start_beast_async(...)`
    - wiring backend de dataset/prereqs de `RTLOPS-89`;
  - este bloque no agrega contratos backend nuevos ni cambia reglas fail-closed del preflight.
- Surface minima real integrada:
  - `Quick` queda separado del research masivo;
  - `Runs` y `Comparador Profesional` quedan juntos como flujo principal de catalogo + analisis;
  - `Research Batch` y `Beast / Infra` quedan separados como modos distintos;
  - la copy principal queda en espanol y deja explicito que `Legacy`/auditoria no son el flujo oficial.
- Validacion real ejecutada:
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limite honesto del bloque:
  - no cambia contratos backend;
  - no hace refactor masivo;
  - no reescribe `Research Funnel` ni `Strategy Tester` como dominios nuevos;
  - no abre una UI nueva fuera de la pagina `Backtests`.
- Siguiente bloque exacto recomendado:
  - no corresponde abrir otro refactor UX grande a ciegas;
  - la revalidacion con repo + `docs/truth` + Linear ya deja a `RTLOPS-87` absorbida y cerrada administrativamente;
  - no corresponde abrir otro bloque de producto en `Backtests` por defecto;
  - si aparece un gap nuevo real, abrir solo un microbloque chico sobre surfaces secundarias y no reabrir backend/prereqs.

## RTLOPS-89 - preflight canonico de dataset/prerequisitos para Batch/Beast - 2026-04-25

- Estado real confirmado en esta rama:
  - el backend ya expone un endpoint canonico y auditable `POST /api/v1/research/dataset-preflight`;
  - la verdad canonica del preflight vive en `MassBacktestCoordinator.dataset_preflight(...)` dentro de `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`;
  - ese preflight reutiliza logica real ya existente y no abre una segunda verdad:
    - `_preflight_dataset_ready(...)`
    - `build_data_provider(...)`
    - `DataCatalog` / manifests reales del runtime;
  - `start_async(...)` y `start_beast_async(...)` siguen fail-closed sobre la misma evaluacion canonica;
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx` ya consume el preflight canonico y deja de deducir readiness desde heuristicas locales de `data/status`.
- Contrato canonico minimo resultante:
  - `mode`
  - `dataset_ready`
  - `dataset_status`
  - `dataset_source_type`
  - `dataset_root`
  - `bootstrap_required`
  - `bootstrap_command`
  - `market_family`
  - `symbol`
  - `symbols`
  - `timeframe`
  - `date_range`
  - `can_run_batch`
  - `can_run_beast`
  - `blocking_reason`
  - `missing_reasons`
  - `eligible_symbols`
  - `ineligible_symbols`
- Regla canonica resultante:
  - si falta dataset real reproducible:
    - `dataset_ready=false`
    - `dataset_status=missing`
    - `bootstrap_required=true` cuando existe comando canonico de carga
    - `blocking_reason` explicito;
  - si se intenta `dataset_source=synthetic` en Batch/Beast:
    - `dataset_ready=false`
    - `dataset_status=synthetic_blocked`
    - `dataset_source_type=synthetic`
    - fail-closed sin dejar al frontend inferir nada;
  - la elegibilidad minima queda visible y auditable por:
    - `market_family`
    - `symbol` / `symbols`
    - `timeframe`
    - `dataset_source_type`
    - `eligible_symbols`
    - `ineligible_symbols`;
  - para `crypto`, el preflight canoniza `market_family=usdm` por default cuando manifest/cfg no declaran otro valor.
- Surface minima real integrada:
  - `Backtests > Research Batch` ahora muestra de forma honesta:
    - listo
    - bloqueado
    - `synthetic` bloqueado
    - falta bootstrap
    - simbolos elegibles / no elegibles;
  - el boton de refresh del bloque ya consulta el preflight canonico, no `GET /api/v1/data/status` como fuente primaria de decision;
  - el start de Research Batch y el start de Beast ahora cortan por `can_run_batch` / `can_run_beast` y mensajes canonicos del backend.
- Validacion real ejecutada:
  - `uv run --project rtlab_autotrader python -m py_compile rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
  - `uv run --project rtlab_autotrader --extra dev python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "dataset_preflight or research_mass_backtest_start_rejects_missing_dataset or research_beast_start_rejects_missing_dataset or research_beast_endpoints_smoke" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limite honesto del bloque:
  - no abre `RTLOPS-90`;
  - no redisenia toda la pantalla de `Backtests`;
  - no abre una API grande nueva;
  - no toca dominios fuera de Batch/Beast dataset prereqs.
- Siguiente bloque exacto recomendado:
  - `RTLOPS-90 - Reordenamiento UX Backtests sin refactor masivo`.

## RTLOPS-28 - cierre administrativo final sobre alcance ya absorbido - 2026-04-24

- Estado real revalidado con prioridad `repo -> docs/truth -> Linear`:
  - el alcance tecnico real de `RTLOPS-28` ya quedo absorbido en repo/tests sobre `rtlops28/v1`;
  - ese alcance ya incluye:
    - `drift_not_blocking`
    - mapping `allow_review / hold / block`
    - `missingness`
    - `recommended_actions[]`;
  - Linear ya deja `RTLOPS-28` en `Done`;
  - no se abrio split nuevo.
- Regla canonica resultante:
  - hoy no aparece un gap tecnico vivo de `PSI/KS` dentro de `RTLOPS-28`;
  - cualquier `PSI/KS` futuro solo corresponde si vuelve a sostenerse con evidencia nueva en repo + `docs/truth` + Linear;
  - si reaparece, debe abrirse como issue nueva, chica y precisa, y no reabrirse esta issue por memoria historica.
- Siguiente bloque exacto recomendado:
  - `RTLOPS-28` queda cerrada administrativamente y fuera de continuidad tecnica;
  - el siguiente paso correcto pasa a ser un preflight limpio para decidir el dominio siguiente del programa, ya fuera de `RTLOPS-28`;
  - mantener fuera de ese preflight:
    - drift cosmetico nuevo
    - `live console`
    - monitoring completo
    - scorecard de produccion
    - UI nueva

## RTLRESE-32 - validacion independiente real por run - 2026-04-22

- Estado real confirmado en esta rama:
  - el backend ya persiste un contrato canonico `rtlrese32/v1` por run en `backtest_runs.independent_validation_json`;
  - el contrato vive tanto en corridas simples creadas por `POST /api/v1/backtests/run` como en hijos persistidos por `mass_backtest_engine`;
  - `GET /api/v1/runs/{run_id}` ya expone `independent_validation` como evidencia auditable por run;
  - `POST /api/v1/runs/{run_id}/validate_promotion` ya consume esa evidencia con checks explicitos:
    - `independent_validation_reusable`
    - `independent_validation_target_stage`
- Reuso real de backlog previo:
  - `RTLRESE-5` queda absorbida via `PBO/CSCV` trazable por run dentro del contrato;
  - `RTLRESE-6` queda absorbida via `PSR/DSR`, `review_reasons`, `rejection_reasons` y `promotion_stage_eligible`;
  - `RTLRESE-4` no hizo falta en este bloque porque no aparecio un gap nuevo de provenance persistente fuera de lo ya disponible en catalogo/run payload.
- Regla canonica resultante:
  - `PBO`, `DSR` y `PSR` quedan visibles por run dentro del contrato `rtlrese32/v1`;
  - si `DSR/PSR` salen solo de returns derivados y no de evidencia formal del run, quedan como auditoria `REVIEW` y no como evidencia reusable para promocion;
  - un run solo queda reusable para `promotion_stage` cuando la validacion independiente queda en `PASS` y declara elegibilidad explicita por etapa;
  - el bloque sigue fuera de:
    - `live console`
    - scorecard de produccion
    - portfolio risk
    - governance IA como dominio separado
- Siguiente bloque exacto recomendado:
  - `RTLOPS-28` - drift layer minimo y auditable sobre el estado ya cerrado por `RTLRESE-32`.

## Preflight posterior a RTLOPS-84 - cadena minima cerrada - 2026-04-21

- Estado real confirmado en esta rama:
  - `rtlops81/v1` ya tiene tres consumidores reales y auditables de `lifecycle_operational` en:
    - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
  - no aparece una cuarta surface natural comparable en el dashboard para seguir extendiendo la cadena minima
  - por eso, la cadena de consumidores minimos queda cerrada en `RTLOPS-84`
- Estado real del dominio siguiente:
  - Linear expone `RTLOPS-69` (`live console`) como backlog real dentro del mismo proyecto
  - pero repo + `docs/truth` todavia no sostienen con honestidad que `live console` sea la sucesora inmediata del programa
  - tampoco queda canonizado todavia un dominio siguiente alternativo en monitoring / health / alerts, lifecycle operativo mas amplio o lifecycle completo entre entornos
- Regla canonica resultante:
  - no corresponde inventar `RTLOPS-85`
  - la cadena minima queda explicitamente cerrada
  - la decision del dominio siguiente queda fail-closed hasta que repo + `docs/truth` + Linear sostengan una sucesora real

## RTLOPS-84 - tercer consumidor minimo de lifecycle_operational - 2026-04-21

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx` ya consume `selectedMassBot.lifecycle_operational` como tercera surface minima operativa sobre `rtlops81/v1`;
  - el tercer consumidor vive en la vista de `Backtests`, dentro del bloque `Research Batch`, y es distinto de los consumidores ya cerrados en `execution/page.tsx` y `strategies/page.tsx`;
  - la UI deja visible, para el bot seleccionado:
    - status canonico del lifecycle operativo;
    - progreso permitido o bloqueado;
    - conteos de `allowed`, `rejected`, `progressing`, `paused` y simbolos sin dato;
    - trazabilidad minima por simbolo con `runtime_symbol_id`, `selected_strategy_id` e issues canonicos.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - agrega la tercera surface minima operativa de `lifecycle_operational` dentro del panel del bot usado para `Research Batch`;
    - mantiene el consumidor en modo lectura/auditoria y no duplica controles operativos de `Execution`;
  - `rtlab_dashboard/src/lib/lifecycle-operational.ts`
    - agrega `summarizeLifecycleOperationalUniverse` para resumir el subset operativo sobre el universo del bot;
  - `rtlab_dashboard/src/lib/lifecycle-operational.test.ts`
    - cubre el resumen canonico del tercer consumidor minimo en `Backtests`.
- Regla canonica reafirmada:
  - `RTLOPS-84` no abre `live console`;
  - no abre LIVE lateral;
  - no abre lifecycle completo `backtest/shadow/paper/testnet/live`;
  - no cambia el contrato backend: solo agrega un tercer consumidor real y minimo del contrato ya canonico.
- Validacion real ejecutada:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS

## Preflight posterior a RTLOPS-83 - sucesora canonizada - 2026-04-21

- Estado real confirmado en esta rama:
  - `RTLOPS-83` ya deja consumido `lifecycle_operational` en una segunda surface minima operativa sobre `rtlops81/v1`;
  - repo + docs/truth + Linear sostienen el cierre de `RTLOPS-83`, pero no sostenian todavia una hija explicita posterior;
  - para destrabar esa ambiguedad sin abrir un frente mayor, el usuario canoniza explicitamente la sucesora correcta del frente.
- Regla canonica resultante:
  - la sucesora correcta inmediata de `RTLOPS-83` es `RTLOPS-84`:
    - `Bot Multi-Symbol — tercer consumidor mínimo de lifecycle_operational`;
  - ese slice debe resolver solo:
    - tercer consumidor minimo de `lifecycle_operational`;
    - tercera surface minima operativa ubicada en `rtlab_dashboard/src/app/(app)/backtests/page.tsx`;
    - wiring minimo, chico y auditable sobre `rtlops81/v1`;
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`).
- Fuera de alcance mantenido a proposito:
  - `live console`;
  - LIVE lateral;
  - lifecycle completo `backtest/shadow/paper/testnet/live`;
  - refactor transversal.
- Estado administrativo revalidado:
  - `RTLOPS-84` queda creada en `Backlog` como hija explicita de `RTLOPS-68`.

## RTLOPS-83 - segundo consumidor minimo de lifecycle_operational - 2026-04-21

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx` ya consume `bot.lifecycle_operational` como segunda surface minima operativa sobre `rtlops81/v1`;
  - el segundo consumidor vive en la vista de `Strategies`, distinto del primer consumidor ya cerrado en `execution/page.tsx`;
  - la UI deja visible, por bot:
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - `lifecycle_operational_by_symbol`
    - `items[*].runtime_symbol_id`
    - `items[*].selection_key`
    - `items[*].net_decision_key`
    - `base_lifecycle_state`
    - `operational_status`
    - `lifecycle_state`
    - `selected_strategy_id`
    - errores canonicos por simbolo
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - agrega la segunda surface minima operativa de `lifecycle_operational` dentro del detalle de cada bot;
    - deja visible el subset permitido vs rechazado, los overrides pausados y la trazabilidad por simbolo;
    - mantiene el segundo consumidor en modo lectura/auditoria y deriva a `Execution` para overrides puntuales sin duplicar controles;
  - `rtlab_dashboard/src/lib/lifecycle-operational.ts`
    - agrega helpers puros para resumir y ordenar `lifecycle_operational` de forma reusable;
  - `rtlab_dashboard/src/lib/lifecycle-operational.test.ts`
    - cubre el resumen canonico del segundo consumidor minimo.
- Regla canonica reafirmada:
  - `RTLOPS-83` no abre `live console`;
  - no abre LIVE lateral;
  - no abre lifecycle completo `backtest/shadow/paper/testnet/live`;
  - no cambia el contrato de backend: solo agrega un segundo consumidor real y minimo del contrato ya canonico.
- Validacion real ejecutada:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS

## Preflight posterior a RTLOPS-82 - sucesora canonizada - 2026-04-21

- Estado real confirmado en esta rama:
  - `RTLOPS-82` ya deja consumido `lifecycle_operational` en una primera surface minima operativa sobre `rtlops81/v1`;
  - repo + docs/truth + Linear sostienen el cierre de `RTLOPS-82`, pero no sostenian todavia una hija explicita posterior;
  - para destrabar esa ambiguedad sin abrir un frente mayor, el usuario canoniza explicitamente la sucesora correcta del frente.
- Regla canonica resultante:
  - la sucesora correcta inmediata de `RTLOPS-82` es `RTLOPS-83`:
    - `Bot Multi-Symbol — segundo consumidor mínimo de lifecycle_operational`;
  - ese slice debe resolver solo:
    - segundo consumidor minimo de `lifecycle_operational`;
    - segunda surface minima operativa distinta del primer consumidor ya cerrado en `execution/page.tsx`;
    - wiring minimo, chico y auditable sobre `rtlops81/v1`;
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`).
- Fuera de alcance mantenido a proposito:
  - `live console`;
  - LIVE lateral;
  - lifecycle completo `backtest/shadow/paper/testnet/live`;
  - refactor transversal.
- Estado administrativo revalidado:
  - `RTLOPS-83` queda creada en `Backlog` como hija explicita de `RTLOPS-68`.

## RTLOPS-82 - primer consumidor real de lifecycle_operational - 2026-04-21

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx` ya consume de forma real `lifecycle_operational` sobre `rtlops81/v1`;
  - el primer consumidor operativo queda colgado en la surface ya existente de `Execution`, sin abrir `live console`;
  - la UI selecciona un bot del registry, lee `GET /api/v1/bots/{bot_id}/lifecycle-operational` y consume:
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - `blocked_symbols`
    - `lifecycle_operational_by_symbol`
    - `items[*].runtime_symbol_id`
    - `items[*].selection_key`
    - `items[*].net_decision_key`
- Cambio real aplicado en frontend/API:
  - el bloque operativo del bot seleccionado ahora expone una tarjeta canonica de `lifecycle_operational`;
  - esa tarjeta muestra el subset permitido vs rechazado, el estado de progresion y los overrides persistidos;
  - por simbolo permite:
    - pausar cuando el simbolo sigue dentro del subset `allowed_trade_symbols`
    - reanudar quitando el override persistido y volviendo al default implicito `active`
  - el wiring frontend usa `GET/PATCH /api/v1/bots/{bot_id}/lifecycle-operational` sin abrir scheduler, engine nuevo ni ejecucion LIVE lateral.
- Regla canonica reafirmada:
  - `RTLOPS-82` no abre `live console`;
  - no abre LIVE lateral;
  - no abre lifecycle completo `backtest/shadow/paper/testnet/live`;
  - no cambia la verdad de `rtlops81/v1`: solo agrega el primer consumidor real y minimo del contrato ya canonico.
- Validacion real ejecutada:
  - `npm.cmd test -- --run src/lib/execution-bots.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS

## RTLOPS-81 - contratos minimos de lifecycle operativo por simbolo - 2026-04-20

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de `lifecycle_operational` por simbolo sobre la base derivada cerrada por `RTLOPS-80`;
  - el nuevo contrato `rtlops81/v1` consume:
    - `GET /api/v1/bots/{bot_id}/lifecycle`
    - `GET /api/v1/bots/{bot_id}/runtime`
    - `GET /api/v1/bots/{bot_id}/policy-state`
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
  - el storage minimo persistido queda reducido a `lifecycle_operational_by_symbol`;
  - para no abrir una segunda verdad paralela, solo se persisten overrides `paused`; `active` sigue como default implicito.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/lifecycle-operational`
  - `PATCH /api/v1/bots/{bot_id}/lifecycle-operational`
  - `lifecycle_operational` agregado al payload canonico de bots y al `registry-contract`
  - `contract_version` del Bot Registry elevada a `rtlops81/v1`
  - `lifecycle_operational` expone por simbolo:
    - `base_lifecycle_state`
    - `operational_status`
    - `lifecycle_state`
    - `progression_allowed`
  - reason code canonico agregado:
    - `symbol_operational_paused`
- Regla canonica reafirmada:
  - `RTLOPS-81` no abre `live console`;
  - no abre ejecucion LIVE lateral por simbolo;
  - no abre lifecycle completo `backtest/shadow/paper/testnet/live`;
  - no introduce un scheduler/engine nuevo: solo agrega pausa operativa minima sobre el subset ya canonico.
- Validacion real ejecutada:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle_operational or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`

## Preflight posterior a RTLOPS-81 - sucesora canonizada - 2026-04-21

- Estado real confirmado en esta rama:
  - `RTLOPS-81` ya deja `lifecycle_operational` como capa canonica, auditable y consumible sobre `rtlops81/v1`;
  - repo + docs/truth + Linear sostienen el cierre de `RTLOPS-81`, pero no sostenian todavia una hija explicita posterior;
  - para destrabar esa ambiguedad sin abrir un frente mayor, el usuario canoniza explicitamente la sucesora correcta del frente.
- Regla canonica resultante:
  - la sucesora correcta inmediata de `RTLOPS-81` es `RTLOPS-82`:
    - `Bot Multi-Symbol — primer consumidor real de lifecycle_operational`;
  - ese slice debe resolver solo:
    - primer consumidor real de `lifecycle_operational`;
    - surface minima operativa sobre `rtlops81/v1`;
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`);
    - consumo auditable sin abrir un scheduler o engine nuevo.
- Fuera de alcance mantenido a proposito:
  - `live console`;
  - LIVE lateral;
  - lifecycle completo `backtest/shadow/paper/testnet/live`;
  - refactor transversal.
- Estado administrativo revalidado:
  - `RTLOPS-82` queda creada en `Backlog` como hija explicita de `RTLOPS-68`.

## RTLOPS-80 - lifecycle minimo multi-symbol - 2026-04-20

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de `lifecycle` minimo multi-symbol sobre la base cerrada por `RTLOPS-79`;
  - el nuevo contrato `rtlops80/v1` consume:
    - `GET /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/runtime`
    - `runtime.guardrails.execution_ready`
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
  - la progresion minima ocurre solo sobre `allowed_trade_symbols`;
  - los simbolos rechazados por priorizacion quedan fuera de progresion con motivo visible;
  - si `policy_state.status != active` o `runtime.guardrails.execution_ready=false`, el lifecycle no progresa simbolos y queda fail-closed.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/lifecycle`
  - `lifecycle` agregado al payload canonico de bots y al `registry-contract`
  - `contract_version` del Bot Registry elevada a `rtlops80/v1`
  - `runtime` conserva `rtlops77/v1` como contrato base consumido por este slice
  - `lifecycle` expone:
    - `execution_ready`
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - `blocked_symbols`
    - `progression_allowed`
    - `items[*].lifecycle_state`
  - reason codes canonicos:
    - `bot_status_paused`
    - `bot_status_archived`
    - `runtime_execution_not_ready`
    - `trade_decisions_exceed_live_cap`
    - mas los guardrails heredados del runtime
- Regla canonica reafirmada:
  - `RTLOPS-80` no abre live console;
  - no abre ejecucion LIVE lateral por simbolo;
  - no abre lifecycle completo `backtest/shadow/paper/testnet/live`;
  - no introduce un motor nuevo de scheduling: solo progresa o bloquea el subset ya canonico.
- Validacion real ejecutada:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`

## Preflight posterior a RTLOPS-80 - sucesora canonizada - 2026-04-20

- Estado real confirmado en esta rama:
  - `RTLOPS-80` ya deja resuelto quien progresa, quien queda bloqueado y quien queda rechazado dentro del subset multi-symbol;
  - el contrato `rtlops80/v1` ya es consumible, pero `lifecycle` sigue siendo una capa derivada y auditable con `storage_fields=[]`;
  - el siguiente delta minimo del frente ya no es `live console` ni lifecycle completo entre entornos: es explicitar los contratos minimos de lifecycle operativo por simbolo sobre esa base.
- Regla canonica resultante:
  - la sucesora correcta inmediata de `RTLOPS-80` es `RTLOPS-81`:
    - `Bot Multi-Symbol — contratos mínimos de lifecycle operativo por símbolo`;
  - ese slice debe resolver solo:
    - shape minimo de estado operativo por simbolo;
    - storage/API minimo sin crear una segunda verdad paralela;
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols`);
    - exclusion explicita de `rejected_trade_symbols` con motivo visible;
    - reuse de `runtime_symbol_id`, `selection_key`, `net_decision_key` y `decision_log_scope`.
- Fuera de alcance mantenido a proposito:
  - `live console`;
  - ejecucion LIVE lateral por simbolo;
  - lifecycle completo `backtest/shadow/paper/testnet/live`;
  - scheduler/engine nuevo por fuera del contrato actual;
  - refactor transversal.
- Estado administrativo revalidado:
  - `RTLOPS-79` y `RTLOPS-80` siguen en `Done` en Linear;
  - `RTLOPS-81` queda creada en `Backlog` como hija explicita de `RTLOPS-68`.

## Preflight posterior a RTLOPS-79 - lifecycle minimo multi-symbol - 2026-04-20

- Estado real confirmado en esta rama:
  - el contrato actual ya sostiene abrir un `lifecycle minimo multi-symbol` sin reabrir antes subset/priorizacion;
  - la base minima sale de combinar:
    - `GET /api/v1/bots/{bot_id}/runtime`
    - `guardrails.execution_ready`
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
    - `GET /api/v1/bots/{bot_id}/policy-state` para `mode/status` del bot
  - con esa base, el siguiente bloque puede acotarse a progresion minima sobre el subset ejecutable ya canonico y dejar explicitamente afuera los simbolos rechazados por priorizacion.
- Regla canonica resultante:
  - el siguiente slice correcto posterior a `RTLOPS-79` si puede ser `lifecycle minimo multi-symbol`;
  - ese slice no necesita abrir live console;
  - no necesita abrir ejecucion LIVE lateral por simbolo;
  - tampoco necesita reutilizar el issue amplio `RTLRESE-25`, porque ese issue modela lifecycle completo y sobrealcanza este frente.
- Estado administrativo revalidado:
  - `RTLOPS-79` quedo sincronizada a `Done` en Linear con comentario de cierre real repo/docs/tests;
  - no existe todavia una hija explicita para este lifecycle minimo dentro del frente `RTLOPS-68`.

## RTLOPS-79 - subset ejecutable y priorizacion deterministica bajo caps - 2026-04-20

- Estado real confirmado en esta rama:
  - sobre `rtlops77/v1`, el runtime multi-symbol ya no falla cerrado por completo cuando `trade_decisions_count > max_live_symbols` y la configuracion base sigue siendo coherente;
  - en ese escenario ahora canoniza un subset ejecutable deterministico por orden canonico de `symbols` del bot;
  - la incoherencia dura `max_live_symbols > max_positions` se mantiene fail-closed como error y no entra en priorizacion.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/runtime`
    - conserva `net_decision_by_symbol` completo para auditoria;
    - pasa `guardrails.status` a `warning` cuando aplica priorizacion bajo caps sin incoherencia de configuracion;
    - deja `guardrails.execution_ready=true` cuando la consolidacion sigue valida y el subset ejecutable ya cae dentro del cap live;
    - expone `allowed_trade_symbols` y `rejected_trade_symbols` como subset permitido vs rechazado por priorizacion;
    - agrega `guardrails.prioritization_criterion=symbol_order`;
    - marca los simbolos rechazados a nivel `items[*].errors` con `reason_code=trade_decisions_exceed_live_cap` y `priority_rank` auditable en el mensaje.
- Regla canonica reafirmada:
  - `RTLOPS-79` no abre lifecycle;
  - no abre live console;
  - no abre ejecucion remota LIVE lateral por simbolo;
  - no introduce un motor nuevo de scheduling ni cambia la decision neta ya canonica: solo recorta el subset ejecutable bajo caps.
- Validacion real ejecutada:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> PASS despues de regenerar `.next/types` con `build`
- Fuera de alcance mantenido a proposito:
  - lifecycle
  - live console
  - ejecucion remota LIVE lateral por simbolo
  - refactor transversal
  - features sin dependencia directa del contrato `rtlops77/v1`

## RTLOPS-77 - guardrails, caps y rechazos de configuracion - 2026-04-20

- Estado real confirmado en esta rama:
  - el runtime multi-symbol ya no queda solo como surface derivada auditable: ahora expone una capa explicita de **guardrails + caps** para bloquear la ejecucion cuando la configuracion o el neto por simbolo no sostienen una operacion coherente;
  - el contrato del Bot Registry y del runtime queda elevado a `rtlops77/v1`;
  - el slice consume la base ya cerrada por `RTLOPS-72 + RTLOPS-73 + RTLOPS-74 + RTLOPS-75 + RTLOPS-76`, sin abrir lifecycle ni live console.
- Cambio real aplicado en backend/API:
  - `POST/PATCH /api/v1/bots` y `PATCH /api/v1/bots/{bot_id}/multi-symbol`
    - rechazan configuraciones incoherentes cuando `max_live_symbols > max_positions`;
  - `GET /api/v1/bots/{bot_id}/runtime`
    - agrega `caps` con:
      - `configured_symbols_count`
      - `trade_decisions_count`
      - `max_live_symbols`
      - `max_positions`
    - agrega `guardrails` con:
      - `status`
      - `execution_ready`
      - `allowed_trade_symbols`
      - `rejected_trade_symbols`
      - `reason_codes`
      - `errors`
    - agrega reason codes canonicos:
      - `live_cap_exceeds_max_positions`
      - `trade_decisions_exceed_live_cap`
- Regla canonica reafirmada:
  - `RTLOPS-77` no prioriza ni elige un subset de simbolos para ejecutar cuando el neto excede caps;
  - en ese escenario falla cerrado, deja `execution_ready=false` y explicita el rechazo en `guardrails`;
  - la decision neta derivada puede seguir visible para auditoria, pero ya no queda vendida como ejecutable en silencio.
- Conclusion canonica posterior al preflight:
  - la sucesora correcta inmediata de `RTLOPS-77` no es un `lifecycle` minimo;
  - antes corresponde cerrar el bloque chico de subset ejecutable y priorizacion deterministica bajo caps sobre `rtlops77/v1`;
  - abrir `lifecycle` antes de ese cierre mezclaria en el mismo slice dos decisiones distintas:
    - que simbolos quedan habilitados bajo caps
    - como progresa su lifecycle operativo
- Fuera de alcance mantenido a proposito:
  - lifecycle
  - live console
  - ejecucion remota LIVE lateral por simbolo
  - refactor transversal
  - features sin dependencia directa del contrato `rtlops76/v1`

## RTLOPS-76 - contratos minimos de runtime, storage y API - 2026-04-20

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de **runtime multi-symbol** derivada sobre la verdad ya cerrada por `RTLOPS-72 + RTLOPS-73 + RTLOPS-74 + RTLOPS-75`;
  - el nuevo shape `runtime` no introduce una segunda verdad ni inventa persistencia paralela: cuelga de la asignacion multi-symbol, la seleccion por simbolo, la decision neta por simbolo y las referencias de storage ya existentes;
  - el runtime queda listo para que bloques posteriores consuman ids/keys estables por simbolo sin abrir todavia lifecycle ni live console.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/runtime`
  - `runtime` agregado al payload canonico de bots y al `registry-contract`
  - `contract_version` del Bot Registry elevada a `rtlops76/v1`
  - referencias minimas de storage/API expuestas con:
    - registry: `learning/bots.json`
    - runtime state global: `logs/bot_state.json`
    - decision log: `console_api.sqlite3`
    - paths API concretos para `detail`, `runtime`, `signal-consolidation`, `policy-state` y `decision-log`
  - trazabilidad minima por simbolo expuesta con:
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
    - `decision_action`
    - `decision_side`
    - `decision_criterion`
    - `decision_reason`
- Regla canonica reafirmada:
  - `RTLOPS-76` no abre ejecucion remota real ni lifecycle;
  - deja fundado el **contrato de runtime/storage/API** para colgar la decision neta por simbolo ya canonica;
  - si `signal_consolidation` queda invalida, el runtime cae fail-closed con `signal_consolidation_invalid` y no publica una decision neta utilizable en silencio.
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-77`
  - lifecycle
  - live console
  - ejecucion remota real por simbolo
  - features laterales fuera del dominio runtime/storage/API minimo

## RTLOPS-75 - consolidacion de señales y decision neta por simbolo - 2026-04-18

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de **consolidacion / decision neta por simbolo** sobre la base cerrada por `RTLOPS-72 + RTLOPS-73 + RTLOPS-74`;
  - la nueva surface derivada vive en `signal_consolidation` y ya no obliga al frontend a inferir la decision final desde textos sueltos ni a multiplicar caminos por estrategia;
  - la decision final por simbolo queda anclada a la **estrategia seleccionada por simbolo** ya resuelta en `RTLOPS-74`, pero deja visibles los inputs elegibles que participaron en esa consolidacion.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/signal-consolidation`
  - `signal_consolidation` agregado al payload canonico de bots y al `registry-contract`
  - `contract_version` del Bot Registry elevada a `rtlops75/v1`
  - `net_decision_by_symbol` expuesto con:
    - `action`
    - `side`
    - `selected_strategy_id`
    - `criterion`
    - `reason`
    - `agreement_status`
  - criterios explicitados:
    - `selected_strategy`
    - `action_override`
    - `side_override`
    - `defensive_tags_flat`
    - `meanreversion_tags_sell`
    - `trend_tags_buy`
  - reason codes canonicos:
    - `bot_archived`
    - `strategy_selection_invalid`
    - `selected_strategy_missing`
    - `selected_strategy_not_found`
    - `selected_strategy_disabled`
    - `selected_strategy_symbol_mismatch`
    - `selected_strategy_signal_unresolved`
- Regla canonica reafirmada:
  - `RTLOPS-75` no ejecuta ordenes remotas ni enchufa todavia la runtime real a esta decision;
  - deja resuelta la **decision neta canónica por símbolo** para que el runtime posterior no multiplique ordenes por estrategia ni mantenga caminos paralelos opacos;
  - si la seleccion previa, el estado archivado o la metadata de la estrategia no permiten derivar una decision coherente, el sistema queda fail-closed y no inventa una señal.
- Surface minima real integrada:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - ya muestra la decision neta por simbolo
    - ya muestra inputs participantes, acuerdo/conflicto y criterio final
    - sigue operando sobre universe + elegibilidad + seleccion persistidos
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - ejecucion remota real por estrategia
  - subcuentas

## RTLOPS-74 - seleccion de estrategia por simbolo - 2026-04-18

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de **seleccion por simbolo** sobre la elegibilidad fundada por `RTLOPS-73`;
  - la seleccion explicita persistida vive en `strategy_selection_by_symbol`;
  - la seleccion efectiva visible por API/UI vive en `selected_strategy_by_symbol` y ya no depende de texto libre ni de inferencia opaca del frontend.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/strategy-selection`
  - `PATCH /api/v1/bots/{bot_id}/strategy-selection`
  - `contract_version` del Bot Registry elevada a `rtlops74/v1`
  - nueva seccion canonica `strategy_selection` en `/api/v1/bots/registry-contract`
  - criterios de resolucion explicitados:
    - `explicit`
    - `single_eligible`
    - `primary_strategy`
    - `pool_order`
  - reason codes canonicos:
    - `strategy_eligibility_invalid`
    - `selected_strategy_not_eligible`
    - `no_strategy_selected_for_symbol`
- Regla canonica reafirmada:
  - `RTLOPS-74` no ejecuta ni consolida señales;
  - solo deja resuelto **que estrategia queda seleccionada por simbolo** dentro del pool y universe ya persistidos;
  - si un mapping explicito deja de ser elegible, el sistema falla cerrado y no deriva otra estrategia en silencio.
- Surface minima real integrada:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - ya permite ver la seleccion efectiva por simbolo
    - ya permite fijar/limpiar seleccion explicita por simbolo
    - sigue operando sobre universe + pool + elegibilidad persistidos
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-75`
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - net/consolidation execution

## Microbloque tecnico - canonizacion del type-check frio del dashboard - 2026-04-18

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/tsconfig.json` sigue siendo el unico `tsconfig` efectivo del dashboard;
  - `rtlab_dashboard/next.config.ts` NO define `typescript.tsconfigPath`, NO activa `ignoreBuildErrors`, NO usa `typedRoutes`, NO usa `typedEnv` y NO redefine `distDir`;
  - el dashboard ya pasa type-check en frio sin depender de `next build` ni de `next typegen`.
- Definicion operativa de `en frio` usada:
  - `rtlab_dashboard` sin `.next`
  - `rtlab_dashboard` sin `tsconfig.tsbuildinfo`
  - cada comando corrido en una shell nueva
- Matriz real validada:
  - `npm.cmd exec tsc -- --noEmit` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit --incremental false` en frio -> PASS
  - `npm.cmd exec next -- typegen` -> PASS
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
- Verdad tecnica canonica:
  - la opcion correcta para este repo es **type-check directo**, no una dependencia obligatoria de `next typegen`;
  - el comando canonico formalizado en repo pasa a ser:
    - `npm.cmd run typecheck`
    - implementado como `tsc --noEmit --incremental false`
  - `next typegen` queda como paso compatible pero no requerido para validar el proyecto.
- Motivo de canonizacion:
  - `tsc --noEmit` directo ya pasa en frio;
  - `--incremental false` evita dejar `tsconfig.tsbuildinfo` residual y endurece el flujo para uso estable/CI.
- Limite honesto:
  - no quedo reconstruida con certeza la causa historica exacta de los FAIL observados en sesiones anteriores;
  - la mejor inferencia actual es que se trataba de un estado transitorio o de observaciones tomadas mientras `.next/types` estaba siendo mutado por otros comandos.

## RTLOPS-73 - mapping simbolo↔estrategias elegibles del pool - 2026-04-18

- Estado real confirmado en esta rama:
  - el Bot Registry ya expone una capa canonica y auditable de elegibilidad `simbolo -> estrategias elegibles` por bot;
  - la elegibilidad queda persistida en `strategy_eligibility_by_symbol` y ya no depende de texto libre ni de heuristicas por tags;
  - la surface minima del registry en `rtlab_dashboard/src/app/(app)/strategies/page.tsx` ya permite ver y editar esa elegibilidad sobre el universe y pool persistidos.
- Cambio real aplicado en backend/API:
  - `GET /api/v1/bots/{bot_id}/symbol-strategy-eligibility`
  - `PATCH /api/v1/bots/{bot_id}/symbol-strategy-eligibility`
  - `contract_version` del Bot Registry elevada a `rtlops73/v1`
  - reconciliacion fail-closed cuando cambia pool/universe y algun simbolo quedaria sin estrategias elegibles
  - reason codes canonicos:
    - `symbol_assignment_invalid`
    - `strategy_pool_invalid`
    - `symbol_not_in_universe`
    - `strategy_not_in_pool`
    - `strategy_not_effective_in_pool`
    - `no_eligible_strategy_for_symbol`
- Regla canonica reafirmada:
  - el strategy pool del bot sigue definiendo el conjunto maximo de estrategias posibles;
  - `RTLOPS-73` funda el mapping explicito por simbolo dentro de ese pool;
  - si pool o universe invalidan el mapping persistido, el sistema falla cerrado y exige recomputacion coherente.
- Limite honesto del bloque:
  - no se abre todavia:
    - `RTLOPS-74`
    - `RTLOPS-75`
    - `RTLOPS-76`
    - `RTLOPS-77`
    - lifecycle
    - live console
    - net/consolidation execution

## Microbloque tecnico - validacion inicial del caveat de `tsc --noEmit` - 2026-04-18

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/tsconfig.json` sigue siendo el unico `tsconfig` efectivo del dashboard;
  - `rtlab_dashboard/next.config.ts` NO define `typescript.tsconfigPath`, NO activa `ignoreBuildErrors`, NO usa `typedRoutes`, NO usa `typedEnv` y NO redefine `distDir`;
  - no existe un script canonico `typecheck` en `rtlab_dashboard/package.json`, pero el comando real validado `npm.cmd exec tsc -- --noEmit` ya pasa tambien en frio.
- Definicion operativa usada para `en frio`:
  - `rtlab_dashboard` sin `.next`
  - `rtlab_dashboard` sin `tsconfig.tsbuildinfo`
  - cada comando corrido en una invocacion nueva de shell
- Matriz real validada:
  - `npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit --incremental false` en frio -> PASS
- Conclusion tecnica de esa validacion inicial:
  - la narrativa de `FAIL en frio por includes .next/types` no reprodujo de forma estable en esa punta;
  - esa validacion ya fue superada por el microbloque posterior de canonizacion, que formalizo `npm.cmd run typecheck` como comando canónico del repo.
- Limite honesto:
  - no quedo reconstruida con certeza la causa historica exacta de los FAIL reportados en sesiones anteriores; solo quedo confirmado que ya no son el estado real actual de esta linea.
- Observacion superada por validacion posterior del mismo dia:
  - durante el cierre de `RTLOPS-73` reaparecio un `FAIL` inicial de `npm.cmd exec tsc -- --noEmit` antes del `build`, con error por `.next/types/cache-life.d.ts` faltante;
  - despues de `npm.cmd run build`, `npm.cmd exec next -- typegen` y un segundo `npm.cmd exec tsc -- --noEmit`, el type-check volvio a `PASS`;
  - por lo tanto, esta seccion ya no debe leerse como cierre definitivo del caveat, sino como un estado intermedio luego contradicho por evidencia posterior.

## RTLOPS-71 - subbloque 2 de identidad canonica en backtests - 2026-04-18

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx` ya no expone identidad visible del bot apoyada solo en `name` o `id` internos;
  - la surface de backtests muestra identidad canonica por `display_name + bot_id` en los puntos operatorios principales del bloque.
- Cambio real aplicado en frontend:
  - selector de bot para mass backtest
  - mensaje de carga del pool del bot
  - resumen `Bot filtrado`
  - vista centrica por bot
  - badges/lista de related bots
- Regla canonica reafirmada:
  - la identidad visible del bot en surfaces operatorias debe seguir el registry canonico;
  - `name` puede seguir existiendo como dato legacy/compatibilidad, pero no debe seguir siendo la identidad visible primaria donde el registry ya expone `display_name + bot_id`.
- Fuera de alcance mantenido a proposito:
  - comparador legacy
  - `legacy_json_id`
  - evidence `trusted / legacy / quarantine`
  - `RTLOPS-73+`
  - lifecycle
  - live console
- Caveat tecnico reportado en ese momento:
  - durante el cierre del subbloque quedo asentada una hipotesis de `FAIL` en frio para `npm.cmd exec tsc -- --noEmit`;
  - esa hipotesis quedo revalidada y cerrada despues en el microbloque tecnico de 2026-04-18.

## RTLOPS-71 - subbloque 1 de strategy detail canonico - 2026-04-17

- Estado real confirmado en esta rama:
  - `rtlab_dashboard/src/app/(app)/strategies/[id]/page.tsx` ya no reconstruye `truth/evidence` desde contratos legacy del frontend;
  - la vista depende del contrato canonico:
    - `GET /api/v1/strategies/{id}/truth`
    - `GET /api/v1/strategies/{id}/evidence`
- Cambio real aplicado en frontend:
  - se elimina el fallback que armaba `StrategyTruth` desde `/api/v1/strategies`;
  - se elimina el fallback que armaba `StrategyEvidenceResponse` desde `/api/v1/backtests/runs`;
  - si falta el contrato canonico:
    - `truth` falla con error explicito de surface;
    - `evidence` deja aviso explicito y la vista no simula evidence legacy;
  - el texto de detalle deja de presentar `backtests/trades` como fallback legacy de `truth/evidence` y pasa a describirlos como expansion de evidence derivada.
- Regla canonica reafirmada:
  - `truth/evidence` del detail de estrategia ya no deben reconstruirse del lado del frontend;
  - si el backend no expone el contrato canonico, la vista debe fallar de forma honesta y no maquillar el dominio.
- Fuera de alcance mantenido a proposito:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
  - cleanup transversal de naming legacy en otras surfaces
  - `RTLOPS-73+`
  - lifecycle
  - live console
- Conclusion operativa:
  - el nucleo mas confirmado de `RTLOPS-71` ya quedo absorbido en strategy detail;
  - todavia puede quedar un segundo subbloque chico de `RTLOPS-71` para surfaces derivadas si se confirma contra repo/Linear, pero ya no en este bloque.

## Auditoria de deuda real - lote 1 de reparacion RTLOPS-24 + RTLOPS-34 - 2026-04-17

- Estado real confirmado en esta rama:
  - la surface operatoria de `execution` ya no contradice al Bot Registry canonico en dos puntos criticos:
    - deja de ofrecer borrado destructivo de bots;
    - deja de mezclar `status` runtime con `registry_status` como si fueran lo mismo.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - usa identidad canonica del registry (`display_name` + `bot_id`) en selector, tabla y acciones;
    - muestra por separado:
      - `runtime:<status>`
      - `registry:<registry_status>`
    - reemplaza acciones stale de `DELETE /api/v1/bots/{bot_id}` por:
      - `POST /api/v1/bots/{bot_id}/archive`
      - `POST /api/v1/bots/{bot_id}/restore`
    - evita edicion operativa sobre bots archivados desde esta surface.
  - `rtlab_dashboard/src/lib/execution-bots.ts`
    - helper canonico para labels, filtros y badges del frente operatorio
  - `rtlab_dashboard/src/lib/execution-bots.test.ts`
    - cubre identity label, filtro `archived` por registry y badges separados.
- Regla canonica reafirmada:
  - `registry_status=archived` pertenece al gobierno del registry;
  - `status=active|paused|...` sigue siendo estado operativo/runtime;
  - `execution` no debe volver a presentar `DELETE` como camino valido mientras el backend mantenga soft-archive fail-closed.
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-73+`
  - lifecycle
  - live console
  - refactor del core de execution
  - reescritura de surfaces research/backtests
- Conclusion operativa:
  - la consola operatoria principal ya no empuja al usuario a un contrato API invalidado por el backend;
  - el siguiente lote de deuda real conviene ir sobre frontend fino de estrategia/surfaces derivadas, no sobre execution core.

## RTLOPS-72 - Bot Multi-Symbol con modelo canonico de simbolos por bot y limites base - 2026-04-17

- Estado real confirmado en esta rama:
  - el runtime multi-symbol todavia NO esta resuelto;
  - pero el registry del bot ya expone un modelo canonico minimo para representar multi-symbol sin texto libre ni storage paralelo.
- Fuente de verdad real usada por este bloque:
  - la persistencia multi-symbol sigue viviendo en el mismo storage canonico del registry (`learning/bots.json`);
  - este bloque reutiliza exactamente los campos ya persistidos por `RTLRESE-28`:
    - `universe_name`
    - `universe`
    - `max_live_symbols`
  - no se crea una `v2` del registry ni un storage separado para multi-symbol.
- Contratos reales expuestos por API despues de este bloque:
  - sigue vigente `GET /api/v1/bots/registry-contract`, ahora versionado como `rtlops72/v1`;
  - nuevo surface minimo canonico:
    - `GET /api/v1/bots/{bot_id}/multi-symbol`
    - `PATCH /api/v1/bots/{bot_id}/multi-symbol`
  - el contrato del registry ahora deja visible:
    - `storage.multi_symbol_fields`
    - `api.multi_symbol_path`
    - `multi_symbol.contract_version = rtlops72/v1`
    - limites y fields del modelo multi-symbol.
- Reglas canonicas fijadas en este bloque:
  - `symbols` se apoyan en el universo/catalogo real del registry;
  - no se aceptan simbolos duplicados;
  - `configured_symbols_count >= 1`;
  - `configured_symbols_count <= 12`;
  - `max_active_symbols >= 1`;
  - `max_active_symbols <= 12`;
  - `max_active_symbols` no puede superar la cantidad de simbolos configurados;
  - si el catalogo/universe real deja invalida una configuracion persistida, el bot queda fail-closed con:
    - `multi_symbol.status = error`
    - `multi_symbol.errors[]`
  - un bot archivado no admite edicion operativa via `/multi-symbol`.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa el modelo y la respuesta canonica `multi_symbol`
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - valida el cap de simbolos configurados contra el contrato canonico
    - sigue usando el mismo formulario del registry ya existente
  - este bloque NO abre una UI nueva ni una live console para multi-symbol.
- Lo que este bloque NO implementa:
  - `RTLOPS-73`
  - mapping estrategia<->simbolo
  - seleccion de estrategia por simbolo
  - consolidacion de señales
  - net execution
  - lifecycle
  - live console
- Conclusion operativa:
  - desde este bloque, el sistema ya tiene una base canonica y persistida para colgar el runtime multi-symbol;
  - el siguiente bloque ya puede enfocarse en elegibilidad/mapping por simbolo, no en volver a fundar el modelo.

## Auditoria global + cleanup controlado de residuos live/legacy - 2026-04-17

- Estado real revalidado contra repo + docs/truth + Linear:
  - `RTLRESE-13` backend domains y `RTLRESE-14` API contracts ya aparecen absorbidas en esta base real:
    - `rtlab_autotrader/rtlab_core/domains/*.py` esta trackeado
    - `GET /api/v1/strategies/{strategy_id}/truth`
    - `GET /api/v1/strategies/{strategy_id}/evidence`
    - `GET/PATCH /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/decision-log`
  - `RTLRESE-15` frontend domains ya opera sobre esos contratos canonicos; los fallbacks legacy que sobreviven son transicionales y no deben volver a presentarse como si `RTLRESE-14` siguiera sin integrar.
  - `LIVE` global sigue bloqueado por guardrails reales y pendientes operativos de preflight/readiness/credenciales/canary; no se removio ninguna proteccion real.
- Cleanup controlado aplicado en este bloque:
  - la ayuda de `mode=live` en `Strategies` deja de expresarse como `NO GO` global y pasa a describir gating real por readiness/gates;
  - los notices de fallback en `strategies/[id]` y `execution` dejan de decir que `RTLRESE-14` no esta integrada y pasan a describir degradacion transicional por contrato ausente.

## RTLRESE-31 - Bot Registry con contratos minimos de storage, API y frontend - 2026-04-17

- Estado real confirmado en esta rama:
  - el `Bot Registry` ya no depende de defaults/limits hardcodeados en frontend para operar su surface minima;
  - ahora tiene un contrato canonico explicito que alinea storage, API y frontend sobre el mismo shape administrativo del bot.
- Fuente de verdad real consolidada en este bloque:
  - el storage real sigue viviendo en `learning/bots.json`, administrado por `BotPolicyStateRepository` / `ConsoleStore`;
  - no se creo un storage paralelo ni una `v2` del registry;
  - la surface canonica nueva sale por `GET /api/v1/bots/registry-contract`.
- Contratos reales expuestos por API despues de este bloque:
  - siguen vigentes:
    - `GET /api/v1/bots`
    - `POST /api/v1/bots`
    - `GET /api/v1/bots/{bot_id}`
    - `PATCH /api/v1/bots/{bot_id}`
    - `POST /api/v1/bots/{bot_id}/archive`
    - `POST /api/v1/bots/{bot_id}/restore`
    - `GET /api/v1/bots/{bot_id}/policy-state`
    - `PATCH /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/decision-log`
  - nuevo contrato minimo canonico:
    - `GET /api/v1/bots/registry-contract`
      - version de contrato
      - storage real del registry
      - surface API minima
      - defaults canonicos
      - limites canonicos
      - enums canonicos
      - grupos de campos del registry
- Reglas canonicas fijadas en este bloque:
  - frontend deja de definir por su cuenta:
    - cap del pool
    - cap live
    - defaults de capital/risk profile/base config
    - enums base del registry
  - la UI del registry consume el contrato canonico del backend para:
    - crear drafts
    - validar drafts
    - mostrar capacidad/storage/version del registry
  - `bot_id` sigue siendo la identidad estable y el soft-archive sigue siendo la semantica valida del storage.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - helpers del draft consumen `BotRegistryContractResponse`
    - validacion Zod deja de apoyarse en limites hardcodeados
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - carga `GET /api/v1/bots/registry-contract`
    - crea/edita bots usando defaults/limits/enums canónicos
    - muestra version y storage del registry en UI
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa el contrato canonico del registry
- Lo que este bloque NO implementa:
  - runtime multi-symbol (`RTLOPS-72+`)
  - mapping estrategia<->simbolo
  - lifecycle
  - live console
  - nuevas features de negocio del bot
- Conclusion operativa:
  - desde este bloque, el Bot Registry queda cerrado como dominio minimo profesional y util;
  - el siguiente frente ya no necesita consolidar contratos del registry y puede arrancar sobre runtime multi-symbol.

## RTLRESE-30 - Bot Registry con edicion, archivado/reactivacion y gobierno basico con trazabilidad - 2026-04-16

- Estado real confirmado en esta rama:
  - el `Bot Registry` ya no solo persiste identidad/config/pool;
  - ahora endurece el gobierno basico del bot con trazabilidad minima persistida y reglas explicitas de reactivacion.
- Campos nuevos persistidos y expuestos por este bloque:
  - `last_change_type`
    - `created`
    - `updated`
    - `archived`
    - `reactivated`
  - `last_change_summary`
  - `last_changed_by`
  - `last_change_source`
  - `updated_at` y `archived_at` siguen siendo timestamps canonicos del registry.
- Fuente de verdad real usada por este bloque:
  - la persistencia del bot sigue viviendo en `learning/bots.json`, administrada por `BotPolicyStateRepository` / `ConsoleStore`;
  - la trazabilidad minima se persiste en el mismo registro del bot, sin abrir una auditoria enterprise paralela;
  - la auditabilidad historica se apoya en el `decision_log` ya existente (`/api/v1/bots/{bot_id}/decision-log`), no en una segunda fuente de verdad.
- Contratos reales expuestos por API despues de este bloque:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/{bot_id}/archive`
  - `POST /api/v1/bots/{bot_id}/restore`
  - `GET /api/v1/bots/{bot_id}/policy-state`
  - `PATCH /api/v1/bots/{bot_id}/policy-state`
  - `GET /api/v1/bots/{bot_id}/decision-log`
  - los contratos del registry ahora devuelven metadata minima de cambio junto al estado del bot.
- Reglas canonicas fijadas en este bloque:
  - `bot_id` sigue siendo inmutable y no se rompe por rename/display changes;
  - `archive` sigue siendo soft-archive y no borrado destructivo;
  - un bot archivado sigue sin admitir edicion operativa mientras siga archivado;
  - `restore` ahora falla de forma explicita si el bot quedo invalido contra el registry actual:
    - symbols assignment invalido
    - strategy pool invalido
    - `mode=live` no habilitado por gates actuales
  - los cambios relevantes del registry dejan:
    - tipo de cambio
    - resumen
    - actor
    - source
    - timestamp visible via `updated_at`.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - muestra trazabilidad minima por bot
    - muestra `updated_at` / `archived_at`
    - muestra ultimo tipo/resumen de cambio
    - expone errores reales al intentar restaurar un bot invalido
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` y `BotPolicyState` tipados con metadata minima de trazabilidad
- Lo que este bloque NO implementa:
  - lifecycle completo entre entornos
  - runtime multi-symbol
  - elegibilidad estrategia<->simbolo
  - consolidacion de señales
  - live console
  - contratos globales/minimos amplios de `RTLRESE-31`
- Conclusion operativa:
  - desde este bloque, el Bot Registry ya puede editar, archivar y reactivar con trazabilidad minima util y reactivacion fail-closed;
  - el siguiente bloque ya puede enfocarse en contratos/minimos transversales del registry, no en volver a resolver gobierno basico.

## RTLRESE-29 - Bot Registry con strategy pool asignado, persistencia y limites - 2026-04-16

- Estado real confirmado en esta rama:
  - el `Bot Registry` ya no trata `pool_strategy_ids` como lista informal o derivada;
  - ahora el pool asignado es una configuracion canonica del registry con validacion, persistencia y cap explicito por bot.
- Campos nuevos persistidos y expuestos por este bloque:
  - `pool_strategy_ids`
    - lista declarativa de estrategias asignadas al bot
  - `pool_strategies`
    - metadata resuelta contra la fuente real del `strategy registry / truth`
  - `strategy_pool_status`
    - `valid`
    - `error`
  - `strategy_pool_errors`
  - `max_pool_strategies`
    - cap inicial canonico `15`
- Fuente de verdad real usada por este bloque:
  - la persistencia del bot sigue viviendo en `learning/bots.json`, administrada por `BotPolicyStateRepository` / `ConsoleStore`;
  - el pool NO define estrategias por texto libre ni crea una fuente paralela dentro del registry del bot;
  - la validacion reutiliza `store.list_strategies()` como vista canonica del `strategy registry / truth`, incluyendo `status`, `enabled_for_trading` y `allow_learning`.
- Contratos reales expuestos por API despues de este bloque:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `GET /api/v1/bots/{bot_id}/policy-state`
  - `PATCH /api/v1/bots/{bot_id}/policy-state`
  - los contratos del registry ahora devuelven pool asignado, metadata del pool, limite explicito y estado fail-closed del pool.
- Reglas canonicas fijadas en este bloque:
  - `pool_strategy_ids` debe tener al menos `1` estrategia
  - `pool_strategy_ids` no puede superar `15` estrategias
  - no se aceptan duplicados
  - cada `strategy_id` debe existir en la fuente real del `strategy registry / truth`
  - solo se aceptan estrategias:
    - `status=active`
    - `enabled_for_trading=true`
    - `allow_learning=true`
  - si una estrategia previamente persistida deja de ser valida, el bot queda fail-closed con:
    - `strategy_pool_status = error`
    - `strategy_pool_errors[]` visibles por API/UI
  - el sistema ya no borra estrategias invalidas en silencio al normalizar el bot.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - alta con selector real de strategy pool
    - edicion operativa del pool por bot
    - resumen del cap `15`
    - errores reales del pool visibles por bot
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema zod real para `pool_strategy_ids`
    - validaciones de minimo, duplicados y cap `15`
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` y `BotPolicyState` tipados con estado/errores del pool
- Lo que este bloque NO implementa:
  - elegibilidad estrategia<->simbolo
  - seleccion de estrategia por simbolo
  - consolidacion de señales
  - runtime multi-symbol (`RTLOPS-72+`)
  - lifecycle entre entornos
  - live console
- Conclusion operativa:
  - desde este bloque, el lado registry del bot ya puede expresar un pool de estrategias persistente y acotado sin inventar runtime multi-symbol;
  - el siguiente bloque del frente bots ya no necesita abrir persistencia base de pool, sino gobierno/capas siguientes sobre esta base.

## RTLRESE-28 - Bot Registry con asignacion de simbolos, universo valido y cap live - 2026-04-16

- Estado real confirmado en esta rama:
  - el `Bot Registry` ya no conserva solo identidad y config base;
  - ahora tambien persiste la asignacion manual de simbolos por bot, el universo valido desde el que salen esos simbolos y un `cap live` inicial.
- Campos nuevos persistidos y expuestos por este bloque:
  - `universe_name`
  - `universe`
    - lista de simbolos asignados al bot
  - `max_live_symbols`
  - `symbol_assignment_status`
    - `valid`
    - `error`
  - `symbol_assignment_errors`
- Fuente de verdad real usada por este bloque:
  - la persistencia del bot sigue viviendo en la misma capa canonica de `learning/bots.json`, administrada por `BotPolicyStateRepository` / `ConsoleStore`;
  - el universo valido NO se redefine dentro del registry del bot;
  - la validacion reutiliza el catalogo real expuesto por `InstrumentUniverseService` y la policy canonica de universos (`config/policies/universes.yaml`).
- Contratos reales expuestos por API despues de este bloque:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `GET /api/v1/instruments/universes`
  - los endpoints del registry ahora aceptan y devuelven identidad + config base + asignacion de simbolos en un mismo contrato coherente.
- Reglas canonicas fijadas en este bloque:
  - `universe` debe tener al menos `1` simbolo
  - no se aceptan simbolos duplicados
  - todos los simbolos deben existir en un universo real del catalogo
  - `max_live_symbols` debe ser entero en `1..12`
  - `max_live_symbols` no puede exceder la cantidad de simbolos asignados
  - bots `spot` solo aceptan universos `spot`
  - bots `futures` solo aceptan universos `usdm_futures|coinm_futures`
  - si un simbolo previamente asignado deja de existir o deja de ser valido en el catalogo real, el bot queda en estado fail-closed de configuracion:
    - `symbol_assignment_status = error`
    - `symbol_assignment_errors[]` con el detalle
  - un bot archivado no acepta edicion operativa de asignacion/cap/universo.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - selector de universo valido por bot
    - multi-select de simbolos asignados desde ese universo
    - input real de `cap live`
    - badges y mensajes de error cuando la asignacion queda invalida
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema zod real para `universe`, `universe_name` y `max_live_symbols`
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` tipado con estado de asignacion y errores
- Lo que este bloque NO implementa:
  - strategy pool
  - elegibilidad estrategia<->simbolo
  - seleccion de estrategia por simbolo
  - runtime multi-symbol
  - routing / consolidacion / net execution
  - lifecycle entre entornos
  - live console
- Conclusion operativa:
  - desde este bloque, el lado registry del bot ya puede expresar un universo valido, una lista asignada de simbolos y un limite live inicial sin inventar runtime multi-symbol;
  - el siguiente bloque debe apoyarse sobre esta base para abrir `strategy pool`, no volver a redefinir simbolos/universos/cap live.

## RTLRESE-27 - Bot Registry con capital base, risk profile y configuracion operativa minima por bot - 2026-04-16

- Estado real confirmado en esta rama:
  - la entidad `Bot` ya no conserva solo identidad persistente;
  - ahora tambien persiste una configuracion base operativa por bot para capital, riesgo y limites minimos previos a `RTLRESE-28+`.
- Campos nuevos persistidos y expuestos por este bloque:
  - `capital_base_usd`
  - `risk_profile`
    - `conservative`
    - `medium`
    - `aggressive`
  - `max_total_exposure_pct`
  - `max_asset_exposure_pct`
  - `risk_per_trade_pct`
  - `max_daily_loss_pct`
  - `max_drawdown_pct`
  - `max_positions`
- Fuente de persistencia real usada por este bloque:
  - se mantiene la misma capa ya usada por `RTLRESE-26` en `learning/bots.json`, administrada por `BotPolicyStateRepository` / `ConsoleStore`;
  - no se crea storage paralelo ni tablas nuevas para el registry del bot.
- Contratos reales expuestos por API despues de este bloque:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/{bot_id}/archive`
  - `POST /api/v1/bots/{bot_id}/restore`
  - los endpoints del registry ahora aceptan y devuelven identidad + capital/risk/base config minima en un mismo contrato coherente.
- Reglas canonicas fijadas en este bloque:
  - `capital_base_usd > 0`
  - `risk_profile` queda acotado a `conservative|medium|aggressive`
  - `max_total_exposure_pct`, `max_asset_exposure_pct`, `risk_per_trade_pct`, `max_daily_loss_pct` y `max_drawdown_pct` deben quedar en `0 < x <= 100`
  - `max_positions >= 1`
  - `max_asset_exposure_pct` no puede exceder `max_total_exposure_pct`
  - el registry resuelve defaults minimos coherentes con el perfil de riesgo elegido cuando el payload no trae todos los limites explicitos.
- Configuracion base operativa usada en este bloque:
  - `engine`, `mode` y `status` siguen siendo la base operativa ya existente del repo;
  - este bloque no reemplaza esa base: la complementa con presupuesto y limites minimos por bot.
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - formulario de alta con `risk_profile`, capital base y limites minimos
    - listado visible con resumen de capital/riesgo por bot
    - edicion inline de la configuracion base del registry
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema zod real con coercion numerica y validacion cruzada de exposicion
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` tipado con la nueva base canonica de configuracion por bot
- Lo que este bloque NO implementa:
  - symbols assignment
  - strategy pool
  - seleccion por simbolo
  - multi-symbol runtime
  - lifecycle entre entornos
  - live console
  - configuracion avanzada de capital/riesgo por simbolo o por estrategia
- Conclusion operativa:
  - desde este bloque, el bot ya existe como entidad configurable minima mas alla de su identidad;
  - el siguiente bloque debe colgarse de esta base para abrir asignacion de simbolos, no volver a redefinir budget/risk base.

## RTLRESE-26 - Bot Registry canonico con identidad persistente y soft-archive - 2026-04-14

- Estado real confirmado en esta rama:
  - ya existe una entidad `Bot` persistente en registry con identidad separada de su nombre interno legado pobre;
  - el backend conserva `bot_id` estable y expone identidad visible editable sin perder trazabilidad historica.
- Campos canonicos que quedan persistidos y visibles:
  - `bot_id`
  - `display_name`
  - `alias`
  - `description`
  - `domain_type`
    - `spot`
    - `futures`
  - `registry_status`
    - `active`
    - `archived`
  - `created_at`
  - `updated_at`
  - `archived_at`
- Fuente de persistencia real usada por este bloque:
  - la misma capa ya existente de bots en `learning/bots.json`, administrada por `BotPolicyStateRepository` / `ConsoleStore`;
  - no se creo una persistencia paralela ni un storage nuevo fuera del patron actual del repo.
- Contratos reales expuestos por API despues de este bloque:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/{bot_id}/archive`
  - `POST /api/v1/bots/{bot_id}/restore`
  - `DELETE /api/v1/bots/{bot_id}` queda bloqueado en este bloque con `409` para sostener soft-archive y evitar borrado destructivo accidental.
- Reglas canonicas fijadas en este bloque:
  - `display_name` es requerido, editable y visible para el usuario;
  - `bot_id` no se reemplaza por el nombre visible;
  - `domain_type` queda acotado a `spot|futures`;
  - `registry_status` queda acotado a `active|archived`;
  - el archivado es soft-archive y no borrado destructivo.
- Validaciones reales aplicadas server-side y en la UI:
  - `display_name`
    - trim
    - minimo `3`
    - maximo `80`
  - `alias`
    - trim
    - maximo `40`
  - `description`
    - trim
    - maximo `280`
  - `domain_type`
    - enum estricto `spot|futures`
  - `registry_status`
    - enum estricto `active|archived`
- Superficie frontend real integrada en este bloque:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - formulario minimo para crear bots con identidad real
    - listado mostrando `display_name`, `bot_id`, `domain_type` y `registry_status`
    - edicion inline de identidad
    - acciones visibles de archivar / restaurar
  - el panel sigue conviviendo con `policy_state`/evidence existentes, pero este bloque no expande lifecycle, pool ni multi-symbol.
- Lo que este bloque NO implementa:
  - capital/risk profile
  - symbols assignment
  - strategy pool como dominio canonico
  - lifecycle `backtest/shadow/paper/testnet/live`
  - multi-symbol runtime
  - live console
  - metricas avanzadas del bot
- Conclusion operativa:
  - desde este bloque, el registry del bot ya no depende de nombres pobres tipo `AutoBot N` como identidad de producto;
  - la identidad canonica del bot ya existe de forma persistente y auditable;
  - los siguientes bloques deben colgarse de esta base, no volver a inventarla.

## Produccion online, pero la postura canonica de runtime debe quedar en PAPER hasta cerrar LIVE readiness - 2026-04-08

- Estado real confirmado al abrir este bloque:
  - Railway production ya responde `200` en `/api/v1/health`;
  - Backtests y Execution vuelven a cargar;
  - pero el backend seguia exponiendo `mode=live` al mismo tiempo que `runtime_ready_for_live=false`.
- Causa raiz del desalineamiento:
  - habia estado legado persistido en `console_settings.json` / `bot_state.json` con `LIVE`;
  - `bot_mode` ya bloqueaba nuevos cambios a `LIVE` por gates/preflight, pero `settings` y `status` todavia podian reflejar ese estado viejo;
  - ademas la UI de Settings estaba evaluando `/api/v1/gates` del modo actual, no la readiness real de `LIVE`.
- Cambio minimo/profesional aplicado:
  - el backend degrada fail-closed a `PAPER` cualquier estado legado `LIVE` cuando `live_can_be_enabled(...)` sigue en `FAIL`;
  - esa degradacion tambien pausa el bot (`PAUSED`, `running=false`) para evitar acciones reales accidentales;
  - `PUT /api/v1/settings` ahora rechaza `LIVE` si la readiness real sigue pendiente;
  - `GET/POST /api/v1/gates` aceptan `?mode=live` para consultar la readiness de `LIVE` sin depender del modo actual;
  - Settings ahora consulta gates de `LIVE` y muestra que `PAPER` es la postura canonica mientras `LIVE` siga bloqueado.
- Decision canonica de este bloque:
  - runtime global: `PAPER`
  - operador principal efectivo: `PAPER`
  - `SHADOW`: permitido porque no toca exchange real
  - `LIVE`: bloqueado de forma honesta y fail-closed hasta cerrar readiness real
- Lo que este bloque NO cierra:
  - rotacion de API keys Binance
  - IP whitelist
  - permisos minimos de cuenta
  - principal strategy live
  - rollout/canary para promotion a live

## Produccion Railway: el decision log seguia haciendo backfill pesado dentro del startup sincrono - 2026-04-07

- Hallazgo raiz adicional en repo:
  - aun despues de sacar varios bloqueos del boot path, `ConsoleStore.__init__()` seguia llamando `BotDecisionLogRepository.initialize()` de forma sincrona;
  - ese init no solo aseguraba esquema: tambien corria backfills de `logs`, `log_bot_refs` y `breaker_events`.
- Por que esto importa para produccion:
  - staging puede tolerarlo con menos volumen de datos;
  - produccion, con SQLite/volume mas cargado, puede quedar colgada antes de responder `health`.
- Cambio minimo/profesional aplicado:
  - `decision_log.initialize(include_backfill=False)` deja el camino sincrono reducido a esquema y migraciones minimas;
  - el backfill pesado pasa a `startup maintenance` en background;
  - si esa etapa falla, el estado queda registrado como `decision_log_backfill_failed`.
- Lectura operativa correcta:
  - esto sigue siendo un fix repo-side para bajar bloqueo de arranque;
  - el cierre real del incidente solo queda confirmado cuando Railway produccion vuelva a `200`.

## Auditoria implementada: el startup maintenance y varios SQLite wrappers seguian dejando una brecha real en el camino de arranque - 2026-04-07

- Hallazgo real sobre lo implementado:
  - aunque `#28`, `#29` y `#30` ya habian endurecido el startup path, todavia quedaban dos deudas concretas:
    - `_run_startup_maintenance()` podia fallar antes de llegar al `reporting refresh` y dejar `startup_maintenance_status` ambiguo (`running` sin `finished_at`);
    - varios wrappers SQLite construidos en startup seguian haciendo `Path.resolve()` sobre runtime paths del volumen:
      - `ReportingBridgeDB`
      - `ExecutionRealityDB`
      - `ValidationDB`
      - `LivePreflightDB`
      - `BinanceInstrumentRegistryDB`
- Cambio minimo/profesional aplicado:
  - `_run_startup_maintenance()` ahora clasifica fallos por etapa (`seed_backtest_failed`, `backtest_catalog_sync_failed`, `reporting_refresh_failed`) y siempre deja `finished_at`;
  - esos wrappers SQLite pasan a `runtime_path(...)` para no volver a resolver roots runtime del volumen en el camino critico.
- Lectura operativa correcta:
  - este ajuste no “cierra” por si solo el incidente `502`;
  - pero si baja otra capa real de fragilidad del boot path y deja observabilidad honesta cuando el mantenimiento de startup se degrada.

## Produccion Railway: el 502 seguia atado al startup blocking path de auth y ConsoleStore - 2026-04-07

- Hallazgo raiz aislado en repo:
  - aun despues de `#28`, el import de `rtlab_core.web.main` seguia tardando ~33s localmente con la configuracion default;
  - al forzar `RATE_LIMIT_LOGIN_BACKEND=memory`, ese mismo import bajaba a ~4.6s.
- Hallazgo adicional confirmado al seguir auditando el boot:
  - incluso con ese import ya aliviado, `create_app()` seguia registrando hooks `startup` que hacian trabajo potencialmente pesado/bloqueante:
    - `instrument_registry.sync_on_startup()`
    - `execution_reality.recover_live_orders_on_startup()`
  - el segundo es especialmente sensible porque por policy de reconciliacion queda habilitado por default.
- Evidencia tecnica concreta:
  - `LoginRateLimiter()` seguia instanciado globalmente en import-time y por default usando backend `sqlite`;
  - ese camino seguia tocando `RTLAB_USER_DATA_DIR`/`CONSOLE_DB_PATH` antes de servir requests;
  - ademas `ConsoleStore.__init__()` seguia ejecutando:
    - `_ensure_seed_backtest()`
    - `_sync_backtest_runs_catalog()`
    - `reporting_bridge.refresh_materialized_views(...)`
    en el boot blocking path;
  - `/api/v1/health` todavia llamaba `_sync_runtime_state(..., persist=True)`, o sea que el probe escribia estado en vez de limitarse a medir disponibilidad.
- Cambio minimo/profesional aplicado:
  - el login rate limiter pasa a inicializacion lazy y deja de bloquear el import de la app;
  - su sqlite path tambien deja de usar `resolve()` sobre roots runtime;
  - `ConsoleStore` mueve seed/sync/reporting a mantenimiento de startup no bloqueante;
  - los hooks `startup` de instrument registry y live order recovery pasan a background no bloqueante;
  - `/api/v1/health` pasa a `persist=False` para ser una sonda read-only de disponibilidad.
- Lectura operativa correcta:
  - este fix baja de forma fuerte el startup path del backend;
  - el cierre real del incidente solo queda confirmado cuando Railway produccion vuelva a `200` y se pueda leer `health` sobre el deployment activo.

## Produccion Railway: el startup seguia resolviendo `RTLAB_USER_DATA_DIR` en servicios instanciados al importar `app.py` - 2026-04-07

- Hallazgo raiz aislado en repo:
  - aunque `web.app` y el dominio Backtests ya habian dejado de resolver roots runtime en varias rutas criticas,
    el backend seguia instanciando durante import/startup:
    - `ReportingBridgeService`
    - `ExecutionRealityService`
    - `ValidationService`
    - `LearningService`
    - `RolloutManager`
  - esos servicios todavia hacian `Path.resolve()` sobre `user_data_dir` o roots derivados del volumen.
- Evidencia tecnica concreta:
  - `ConsoleStore()` se construye en import-time dentro de `rtlab_core.web.app`;
  - en ese camino se crean `reporting/execution/validation`;
  - ademas `learning_service` y `rollout_manager` se construyen como globals del modulo;
  - por lo tanto, si `resolve()` sobre el root runtime vuelve a tocar un mount problemático en Railway, el proceso puede quedar sin responder antes de servir `/api/v1/health`.
- Cambio minimo/profesional aplicado:
  - esos servicios migran a `runtime_path(...)` para normalizar roots runtime sin `resolve()`;
  - se agregan tests puntuales de constructor para impedir regresion de ese patron.
- Lectura operativa correcta:
  - este cambio apunta directamente al startup path del backend productivo;
  - el cierre real del incidente recien queda confirmado cuando produccion vuelva a `200` en `/api/v1/health`.

## Auditoria Backtests / Beast / Masivo: Beast y Masivo comparten root/catalogo, pero el dominio todavia arrastra deuda runtime - 2026-04-07

- Alcance auditado:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
  - `rtlab_core.web.app`
  - `rtlab_core.src.data.*`
  - `rtlab_core.src.research.*`
  - `rtlab_core.src.reports.reporting`
- Hallazgo estructural confirmado:
  - Beast y Masivo **no** usan roots distintos;
  - ambos dependen del mismo `USER_DATA_DIR`, del mismo `DataCatalog`, del mismo `build_data_provider(...)` y del mismo preflight `_preflight_dataset_ready(...)`;
  - cuando uno ve dataset faltante y el otro tambien, la causa raiz es compartida.
- Hallazgo tecnico importante:
  - despues de `#25` y `#26`, seguian quedando `Path.resolve()` sobre roots runtime dentro del propio dominio Backtests:
    - `DataCatalog`
    - `DataLoader`
    - `DatasetModeDataProvider`
    - `MassBacktestEngine`
    - `ArtifactReportEngine`
    - metadata/reportes del bootstrap Futures
  - eso dejaba una deuda inconsistente:
    - `health/startup` ya no resolvia roots runtime;
    - pero Backtests todavia podia volver a tocar/normalizar esos mismos paths por filesystem dentro del flujo de datasets y artifacts.
- Cambio minimo/profesional aplicado en rama de auditoria:
  - nuevo helper `rtlab_core.src.data.runtime_path` para normalizar paths runtime sin `resolve()`;
  - el dominio Backtests migra a esa normalizacion para dataset roots, manifests y artifacts locales;
  - el panel de Beast en frontend deja de tragarse errores de refresh y ahora muestra cuando no puede leer el estado real del backend;
  - se agregan tests para impedir regresion de `resolve()` sobre `/app/data/rtlab_user_data`.
- Estado operativo honesto al cierre de la auditoria:
  - el frontend de Backtests no esta inventando el problema;
  - `csud` sigue apuntando a produccion;
  - la causa activa visible para el usuario sigue siendo disponibilidad/runtime de produccion (`502`), no divergencia Beast-vs-Masivo ni warning legacy del frontend.

## Produccion Railway: la deteccion de mount no puede tocar el volumen por `exists()/is_mount()` - 2026-04-07

- Hallazgo raiz confirmado tras merge de `#24`:
  - el fix fail-closed anterior era conceptualmente correcto;
  - pero la implementacion apoyada en `Path.exists()` + `Path.is_mount()` sobre roots runtime podia bloquear el proceso en produccion.
- Evidencia real:
  - `main` quedo en `b007abeaa749411f6137845bf28c06373c2c877f`;
  - despues del auto-deploy, `https://bot-trading-ia-production.up.railway.app/api/v1/health` paso a responder `502 Application failed to respond` de forma sostenida;
  - el workflow `Production Storage Durability` (`24063115973`) fallo en el primer chequeo por `Read timed out` contra produccion antes de cualquier bootstrap.
- Diagnostico tecnico mas fuerte:
  - el problema activo ya no es Beast ni el bootstrap;
  - la deteccion de mount debe ser no bloqueante y basada solo en metadata del kernel (`/proc/self/mountinfo`), sin hacer probes filesystem sobre el volume path.
- Cambio minimo/profesional aplicado en repo:
  - `rtlab_core.web.app` deja de usar `exists()/is_mount()` para clasificar mounts runtime;
  - ahora resuelve el mount efectivo por longest-prefix match contra `/proc/self/mountinfo`;
  - tambien deja de hacer `Path.resolve()` sobre `RTLAB_USER_DATA_DIR` y roots runtime en el camino critico de seleccion/health;
  - esto mantiene el fail-closed pero evita tocar el filesystem del volumen durante health/runtime selection.
- Regla operativa correcta desde ahora:
  - para Railway produccion:
    - usar `mountinfo` como fuente de verdad para mount detection;
    - no usar probes filesystem sobre roots de volumen para decidir persistencia durable.

## Produccion Railway: persistencia durable de datasets requiere mount real, no solo path fuera de `/tmp` - 2026-04-07

- Hallazgo raiz confirmado en repo:
  - `storage.persistent_storage` y `G10_STORAGE_PERSISTENCE` se calculaban solo con una heuristica de path:
    - si `RTLAB_USER_DATA_DIR` no estaba bajo `/tmp`, el runtime lo marcaba como persistente;
    - no verificaba si el path estaba realmente respaldado por un volumen montado.
- Consecuencia operativa:
  - produccion podia escribir datasets en `/app/data/rtlab_user_data` dentro del contenedor activo;
  - Beast podia llegar a correr con esos archivos;
  - pero tras restart/redeploy el catalogo podia reaparecer vacio si ese root no estaba sobre un mount real.
- Cambio minimo aplicado en repo:
  - `rtlab_core.web.app` ahora:
    - detecta mount real desde `/proc/self/mountinfo` + `Path.is_mount()`;
    - solo marca `persistent_storage=true` cuando el root efectivo esta sobre un mount no-root;
    - expone en `health.storage`:
      - `configured_user_data_dir`
      - `selection_drift`
      - `mount_detected`
      - `mount_point`
      - `mount_source`
      - `mount_fs_type`
      - `mounted_runtime_candidates`
  - `G10_STORAGE_PERSISTENCE` pasa a fail-closed:
    - `PASS` solo si hay mount real;
    - `FAIL/WARN` si el path es efimero o si no apunta a un volumen montado real.
- Normalizacion de roots soportados para Railway:
  - `/data/rtlab_user_data`
  - `/app/data/rtlab_user_data`
  - `/app/user_data`
- Regla operativa correcta desde ahora:
  - no confiar en `persistent_storage=true` solo por ver un path “no /tmp”;
  - validar siempre el mount real y el `mount_point` expuesto por `/api/v1/health`.
- Validacion canonica agregada:
  - workflow `production-storage-durability.yml`
  - combina:
    - `scripts/check_storage_persistence.py`
    - `scripts/beast_runtime_status_report.py`
    - bootstrap Futures `BTCUSDT` y re-check posterior del dataset exacto `5m`
  - objetivo:
    - confirmar que produccion usa un root montado real antes de vender persistencia durable.

## Produccion Backtests/Beast: dataset faltante por catalogo vacio en volumen runtime - 2026-04-06

- Superficie productiva canonica auditada:
  - `https://bot-trading-ia-csud.vercel.app/backtests`
  - esa URL apunta a `https://bot-trading-ia-production.up.railway.app`
- Estado real confirmado antes del fix de datos:
  - `GET /api/v1/research/beast/status` en produccion:
    - `policy_state=enabled`
    - `policy_source_root=/app/config/policies`
  - `GET /api/v1/data/status` en produccion:
    - `data_root=/app/data/rtlab_user_data/data`
    - `available_count=0`
    - `missing_count=63`
    - faltante explicito para `crypto/BTCUSDT/5m`
- Causa raiz exacta del bloqueo visible:
  - el runtime de Beast ya estaba sano en policies;
  - el bloqueo real paso a ser ausencia de datasets/manifests canónicos en el volumen persistente de produccion;
  - Backtests/Beast decide el faltante desde `DataCatalog.status()` sobre `${RTLAB_USER_DATA_DIR}/data`, no desde frontend ni desde un warning legacy.
- Cambio canonico aplicado en repo:
  - nuevo bootstrap oficial de Binance Futures:
    - `rtlab_autotrader/scripts/bootstrap_binance_futures_public.py`
    - `POST /api/v1/data/bootstrap/binance-futures-public`
  - fuente prioritaria:
    - zips historicos oficiales de Binance Futures + `.CHECKSUM`
  - fallback:
    - REST oficial de klines Futures
  - persistencia:
    - sobre el volumen/runtime real del servicio (`${RTLAB_USER_DATA_DIR}/data`)
  - salida canónica:
    - base `1m`
    - derivados `5m`, `15m`, `1h`, `4h`, `1d`
    - manifests con provenance (`source_type`, `market_family`, `checksum_validation_result`, `archive_paths`, `dataset_file_hash`, etc.)
- Criterio auditable de universo para escalar el pipeline:
  - USD-M:
    - `status=TRADING`
    - `contractType=PERPETUAL`
    - `underlyingType=COIN`
    - ranking por `quoteVolume` 24h descendente
  - COIN-M:
    - `contractStatus=TRADING`
    - `contractType=PERPETUAL`
    - `underlyingType=COIN`
    - ranking por `baseVolume * weightedAvgPrice` 24h descendente
- Regla operativa inmediata:
  - el desbloqueo minimo en produccion/main se hace con:
    - `market_family=usdm`
    - `symbols=[BTCUSDT]`
    - `start_month=2024-01`
    - `end_month=2024-12`
    - `resample_timeframes=[5m,15m,1h,4h,1d]`
- Estado real post-merge/post-bootstrap:
  - `POST /api/v1/data/bootstrap/binance-futures-public` ejecutado en produccion con:
    - `market_family=usdm`
    - `symbols=[BTCUSDT]`
    - `start_month=2024-01`
    - `end_month=2024-12`
    - `resample_timeframes=[5m,15m,1h,4h,1d]`
  - resultado:
    - `available_count=6`
    - `BTCUSDT_1m.parquet` persistido en `/app/data/rtlab_user_data/data/crypto/processed/`
    - derivados persistidos:
      - `5m`
      - `15m`
      - `1h`
      - `4h`
      - `1d`
    - `checksum_validation_result=true` para los `12` zips mensuales oficiales de 2024
  - validacion funcional real posterior:
    - Beast en produccion completo una corrida E2E sobre `BTCUSDT/5m`
    - `run_id=BX-000001`
    - `terminal_state=COMPLETED`
    - `results_count=1`
  - consecuencia operativa:
    - `csud/backtests` ya no deberia marcar faltante para `BTCUSDT/5m`
    - el bloqueo pendiente de Beast deja de ser dataset base para ese caso y pasa a ser cobertura de universo adicional si se quiere escalar

## Produccion Beast/runtime: policies ausentes por empaquetado legacy - 2026-04-06

- Superficie real auditada por el usuario:
  - `https://bot-trading-ia-csud.vercel.app/backtests`
  - ese frontend apunta a `https://bot-trading-ia-production.up.railway.app`
- Contraste real entre staging y produccion:
  - `staging` via `bot-trading-ia-staging-2`:
    - `GET /api/v1/research/beast/status` -> `policy_state=enabled`
    - `GET /api/v1/config/policies` -> `available=true`
    - `authority.candidates[0]` en `/app/config/policies` con `15/15` YAML presentes
  - `produccion` via `bot-trading-ia-csud`:
    - `GET /api/v1/research/beast/status` -> `policy_state=missing`
    - `GET /api/v1/config/policies` -> `available=false`
    - `authority.candidates` reporta ausentes tanto:
      - `/app/config/policies`
      - `/app/rtlab_autotrader/config/policies`
- Causa raiz exacta confirmada en repo:
  - el Dockerfile legacy `rtlab_autotrader/docker/Dockerfile` no copiaba `config/` al contenedor;
  - el Dockerfile root-safe del repo root si copia `config/`, por eso staging ya estaba sano;
  - la compat local `rtlab_autotrader/config/policies/` si existe y contiene los `15` YAML esperados.
- Cambio minimo aplicado:
  - endurecer el Dockerfile legacy de `rtlab_autotrader` para que tambien haga `COPY config /app/config`;
  - asi, si produccion sigue construyendo con `rtlab_autotrader/` como source/root efectivo, Beast deja de quedar sin policies por empaquetado.
- Regla de validacion operativa desde ahora:
  - `staging` se valida en `https://bot-trading-ia-staging-2.vercel.app/backtests`
  - `produccion` se valida en `https://bot-trading-ia-csud.vercel.app/backtests`
  - el chequeo tecnico canonico para distinguir problema de frontend vs runtime es:
    - `GET /api/v1/config/policies`
    - `GET /api/v1/research/beast/status`

## Railway staging: fix de auto-deploy GitHub/root directory ausente - 2026-04-06

- Estado real auditado en Railway `staging`:
  - `serviceManifest.build.builder = DOCKERFILE`
  - `serviceManifest.build.dockerfilePath = docker/Dockerfile`
  - `rootDirectory = null`
  - volumen montado en `/app/user_data`
  - variable activa:
    - `RTLAB_USER_DATA_DIR=/app/user_data`
- Causa raiz exacta del fallo de auto-deploy desde GitHub/main:
  - Railway estaba construyendo desde la raiz del repo;
  - por documentacion oficial, Railway busca `Dockerfile` en la raiz del `source directory` y acepta un path custom con `RAILWAY_DOCKERFILE_PATH` o config-as-code;
  - en este servicio, el path configurado era `docker/Dockerfile`, pero en la raiz del repo ese archivo no existia;
  - por eso el build de GitHub fallaba con `Dockerfile 'docker/Dockerfile' does not exist`.
- Por que el deploy manual por CLI seguia funcionando:
  - los deploys manuales se hacian con `railway up rtlab_autotrader --path-as-root`;
  - eso convertia `rtlab_autotrader/` en `source directory`;
  - dentro de esa raiz si existia `docker/Dockerfile`, por eso el build pasaba.
- Solucion automatica aplicada:
  - se agrega `docker/Dockerfile` en la raiz del repo, compatible con build context repo root;
  - se agrega `railway.json` en la raiz con config-as-code para fijar:
    - `builder=DOCKERFILE`
    - `dockerfilePath=docker/Dockerfile`
    - `watchPatterns` del backend/config
- Resultado esperado:
  - Railway ya no depende del `Root Directory` visible en UI para encontrar el Dockerfile correcto;
  - el proximo merge a `main` deberia poder auto-desplegar desde GitHub con el source directory en repo root.

## PR 2 product inputs + truth structuring preparado para integrar a `main` - 2026-04-05

- Rama limpia de integracion usada para este bloque:
  - `integration/product-inputs-and-truth-main`
- Base real usada:
  - `main` ya actualizado con el merge del PR runtime `#15`
- Alcance intencional de este PR 2:
  - introducir `docs/product/inputs/*` como capa canonica de input de producto
  - dejar trazabilidad minima en `docs/truth/*`
  - dejar la estructura lista para sync administrativo a Linear
- Dominios canonicos incluidos:
  - `docs/product/inputs/2026-04-ui-trades-console.md`
  - `docs/product/inputs/2026-04-capital-allocation-control.md`
  - `docs/product/inputs/2026-04-runtime-incidents-ops.md`
- Queda explicitamente afuera de este PR 2:
  - implementacion grande de `Capital & Allocation Control`
  - implementacion grande de `UI / Trades Console / Exportes`
  - implementacion grande de `Runtime Incidents / Logs / Alerts / Ops`
  - sync real de Linear si la integracion sigue no disponible
- Criterio adoptado:
  - separar backlog/input de producto de la capa de verdad runtime;
  - no mezclar todavia modelado documental con implementacion de dominio.

## PR 1 runtime live/paper hardening preparado para integrar a `main` - 2026-04-05

- Rama limpia de integracion usada para este bloque:
  - `integration/runtime-live-paper-hardening-main`
- Base real usada:
  - `origin/main`
- Alcance intencional de este PR 1:
  - hardening runtime live/paper ya validado
  - fixes operativos de `margin_guard`
  - persistencia paper al ledger operativo
  - correccion contable `gross/net/cost` y backfill via reconcile
  - monitor externo de `PAPER` via GitHub Actions
- Queda explicitamente afuera de este PR 1:
  - `docs/product/inputs/*`
  - sync/modelado administrativo de Linear
  - dominio grande `Capital & Allocation Control`
  - dominio grande `UI / Trades Console / Exportes`
  - dominio grande `Runtime Incidents / Logs / Alerts / Ops`
- Estado runtime real que este PR busca consolidar en `main`:
  - auth Binance saneado en staging
  - `live_safety.overall_status = OK`
  - `margin_guard.level` visible y `margin_level_blocker` resuelto
  - `PAPER` ya no falla por `orders=0`
  - `max_gross_net_inconsistency_rate` resuelto
  - frente restante de `PAPER`:
    - volumen/tiempo operativo (`min_orders`, `min_trading_days`)
- Monitor de `PAPER` incluido en este PR:
  - `.github/workflows/paper-validation-monitor.yml`
  - `scripts/paper_validation_monitor.py`
- Limitacion importante del monitor:
  - el cron del workflow solo quedara realmente activo cuando el archivo exista en la branch por defecto;
  - antes del merge a `main`, esa automatizacion sigue siendo validable solo por dispatch/manual o desde ramas que ya lo contengan.
- Criterio de integracion adoptado:
  - priorizar un PR coherente de runtime validado;
  - no mezclar todavia estructuracion de producto/backlog/documentacion grande.

## RTLOPS-2 / RTLOPS-1 / RTLOPS-7: autoridad de policies + taxonomia de modos + jerarquia documental - 2026-03-18

- Fuente operativa unica de verdad para policies numericas y gates:
  - `config/policies/` en la raiz del monorepo.
- Compatibilidad permitida, pero no equivalente en autoridad:
  - `rtlab_autotrader/config/policies/`
  - solo se usa como fallback de empaquetado/deploy cuando la raiz canonica no esta disponible o esta incompleta.
- Cambio real aplicado:
  - el backend ahora expone en `GET /api/v1/config/policies`:
    - `authority`
    - `mode_taxonomy`
  - eso deja visible:
    - cual es la raiz runtime seleccionada
    - cual es la raiz canonica esperada
    - si el runtime cayo en compatibilidad
    - si existen YAML duplicados y divergentes entre la raiz canonica y la nested
- Criterio de autoridad tecnica documentado tambien en:
  - `docs/plan/AUTHORITY_HIERARCHY.md`

### Taxonomia canonica de modos

- Runtime global del backend / settings API:
  - `PAPER`
  - `TESTNET`
  - `LIVE`
- Modo operativo por bot:
  - `shadow`
  - `paper`
  - `testnet`
  - `live`
- Fuentes de evidence / learning:
  - `backtest`
  - `shadow`
  - `paper`
  - `testnet`

### Alias legacy explicitados

- `MOCK`:
  - queda tratado como alias legado del mock local de frontend;
  - no es modo canonico del runtime real del backend.
- `demo`:
  - queda tratado como contexto legacy de research/promocion;
  - no es modo operativo canonico.

### Ajuste real en frontend

- `Settings` y `Execution` ya no presentan `MOCK` como si fuera equivalente a runtime real.
- La UI lo rotula como:
  - alias legado local
  - separado de `SHADOW`
  - separado del runtime global `PAPER / TESTNET / LIVE`

### Regla de decision operativa

Cuando codigo, docs y configuracion discrepan:

1. manda el runtime real del backend y los contratos API efectivos
2. despues manda `config/policies/`
3. despues mandan los defaults fail-closed
4. despues `docs/truth`
5. despues `docs/plan`

## RTLRESE-13: separacion backend por dominio operativo y dominio de verdad - 2026-03-16

- Rama de trabajo:
  - `feature/rtlrese-13-backend-domains`
- Se aplico una separacion minima y segura del backend sin cambiar contratos FastAPI ni tocar frontend.
- El backend ahora tiene una frontera explicita en:
  - `rtlab_autotrader/rtlab_core/domains/truth/`
  - `rtlab_autotrader/rtlab_core/domains/evidence/`
  - `rtlab_autotrader/rtlab_core/domains/policy_state/`
  - `rtlab_autotrader/rtlab_core/domains/decision_log/`

### Mapeo real de dominios

- `strategy_truth`
  - persistencia de metadata de estrategias (`strategy_meta.json`)
  - repositorio: `StrategyTruthRepository`
- `strategy_evidence`
  - runs persistidos (`runs.json`)
  - cableado a `ExperienceStore` para evidencia/episodios
  - repositorio: `StrategyEvidenceRepository`
- `bot_policy_state`
  - `console_settings.json`
  - `logs/bot_state.json`
  - `learning/bots.json`
  - repositorio: `BotPolicyStateRepository`
- `bot_decision_log`
  - `console_api.sqlite3`
  - tablas/flujo operativo de `logs` y `breaker_events`
  - repositorio: `BotDecisionLogRepository`

### Cambio arquitectonico real

- `ConsoleStore` pasa a ser un orquestador fino que delega persistencia a repositorios por dominio.
- La separacion se hizo sin refactor masivo:
  - se preservan endpoints y payloads actuales
  - se preserva el cableado actual con `ExperienceStore`, `BacktestCatalogDB` y `RegistryDB`
- Esto mantiene la frontera de backend mas clara sin abrir una migracion grande en esta rama.

### Lo que NO se hizo en este tramo

- NO se hizo split profundo de `RegistryDB` tabla por tabla.
- NO se reescribieron servicios de rollout ni learning fuera de lo minimo necesario para la frontera de persistencia.
- NO se tocaron contratos frontend ni UI.
- NO se mezclo esta sub-issue con RTLRESE-14/15/16.

### Pendiente consciente

- `RegistryDB` todavia agrupa tablas de:
  - `strategy_registry`
  - `experience_*`
  - `learning_proposal`
  - `strategy_policy_guidance`
- Si el siguiente paso de RTLRESE-13 requiere profundizar la separacion, conviene partir ese storage interno en repositorios/submodulos por dominio sin romper contratos actuales.

### Validacion local de este tramo

- `uv run python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/domains/common.py rtlab_autotrader/rtlab_core/domains/truth/repository.py rtlab_autotrader/rtlab_core/domains/evidence/repository.py rtlab_autotrader/rtlab_core/domains/policy_state/repository.py rtlab_autotrader/rtlab_core/domains/decision_log/repository.py` -> PASS

## RTLRESE-14 API contracts por dominio - 2026-03-16

- FastAPI ya expone endpoints separados por dominio operativo:
  - `GET /api/v1/strategies/{strategy_id}/truth`
  - `GET /api/v1/strategies/{strategy_id}/evidence`
  - `GET /api/v1/bots/{bot_id}/policy-state`
  - `PATCH /api/v1/bots/{bot_id}/policy-state`
  - `GET /api/v1/bots/{bot_id}/decision-log`
- `GET /api/v1/strategies/{strategy_id}` queda como contrato legado de compatibilidad:
  - sigue devolviendo `last_oos`;
  - internamente se recompone desde `truth + evidence`.
- Frontera semantica vigente en backend:
  - `strategy_truth`: metadata/flags/params/registry de la estrategia.
  - `strategy_evidence`: resumen de runs y evidencia observada (`latest_run`, `last_oos`, `run_count`).
  - `bot_policy_state`: configuracion operativa del bot (`engine`, `mode`, `status`, `pool_strategy_ids`, `universe`, `notes`).
  - `bot_decision_log`: logs y `breaker_events` filtrados por `bot_id`.
- Alcance explicitamente acotado en esta sub-issue:
  - sin cambios de frontend;
  - sin mezclar RTLRESE-15 ni RTLRESE-16;
  - sin refactor masivo de routers.
- Validacion local ejecutada:
  - `uv run --project rtlab_autotrader --extra dev python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
  - smoke funcional directo sobre `ConsoleStore` en `user_data` temporal -> PASS
- Limitacion abierta de entorno:
  - el smoke HTTP de `pytest` para estos endpoints no corrio porque `starlette.testclient` requiere `httpx` instalado en la venv actual.

## RTLRESE-15 - frontend por dominios con compatibilidad legacy controlada - 2026-03-16

- Scope real de este tramo:
  - solo frontend/dashboard + `docs/truth`;
  - sin cambios backend;
  - sin mezcla con RTLRESE-16.
- Pantallas ajustadas:
  - `rtlab_dashboard/src/app/(app)/strategies/[id]/page.tsx`
    - separa visualmente `strategy_truth` y `strategy_evidence`;
    - deja de mostrar KPIs/evidence como si fueran verdad base;
    - elimina charts sinteticos que mezclaban narrativa de truth con evidencia inventada.
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - hoy es la superficie operativa real del bot; no existe una `bots/page.tsx` dedicada en esta rama;
    - toma el rol de vista operativa del bot;
    - separa `bot_policy_state` de `bot_decision_log`;
    - distingue runtime global de estado declarativo del bot.
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - relabela evidencia agregada y columnas de bots para no confundir `policy_state` con `evidence`.
- Tipos frontend nuevos/explicitos en `rtlab_dashboard/src/lib/types.ts`:
  - `StrategyTruth`
  - `StrategyEvidenceResponse`
  - `BotPolicyStateResponse`
  - `BotDecisionLogResponse`
- Estado de contratos en esta rama:
  - el frontend intenta usar endpoints de dominio:
    - `GET /api/v1/strategies/{id}/truth`
    - `GET /api/v1/strategies/{id}/evidence`
    - `GET /api/v1/bots/{id}/policy-state`
    - `GET /api/v1/bots/{id}/decision-log`
    - `PATCH /api/v1/bots/{id}/policy-state`
  - pero mantiene fallback legacy porque en `main` actual todavia se observan contratos legacy:
    - `GET /api/v1/strategies/{id}`
    - `GET /api/v1/backtests/runs`
    - `PATCH /api/v1/bots/{id}`
    - `GET /api/v1/logs`
- Decision arquitectonica de este tramo:
  - priorizar separacion semantica visible y segura en UI sin bloquear la rama por falta de merge previo de RTLRESE-14.
- Limitacion de validacion en este entorno:
  - no se pudo correr `lint`/`build` de Next.js porque el entorno no tiene `node.exe` disponible;
  - la verificacion de este tramo fue por inspeccion de contratos/codigo y consistencia del diff, no por build frontend ejecutado.

## RTLRESE-16 - consolidacion documental de la frontera operativa - 2026-03-16

- Frontera canonica acordada para el dominio operativo:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- Lectura arquitectonica consolidada:
  - `strategy_truth` = definicion declarativa de la estrategia, parametros, version, tags y notas base.
  - `strategy_evidence` = runs, backtests, metricas agregadas y evidencia observada que respalda o cuestiona la estrategia.
  - `bot_policy_state` = modo, engine, status, pool y notas operativas declarativas del bot.
  - `bot_decision_log` = logs, breaker events y trazas de decisiones/alertas del bot.
- Estado de las sub-issues RTLRESE-11 a RTLRESE-15:
  - RTLRESE-11 / RTLRESE-12:
    - dejaron fijada la frontera semantica y el lenguaje canonico de contratos para no mezclar verdad base con evidencia ni estado declarativo con decision log.
  - RTLRESE-13:
    - rama dedicada: `feature/rtlrese-13-backend-domains`
    - commit de cierre: `4497029`
    - resultado documentado: separacion backend de persistencia por dominios `truth/evidence/policy_state/decision_log`.
  - RTLRESE-14:
    - rama dedicada: `feature/rtlrese-14-api-contracts`
    - commit de cierre: `703cea8`
    - resultado documentado: separacion de endpoints FastAPI por dominio operativo.
  - RTLRESE-15:
    - rama dedicada: `feature/rtlrese-15-frontend-domains`
    - commit de cierre: `1443789`
    - resultado documentado: separacion visual y de tipos en frontend con fallback legacy acotado.
- Estado real de integracion en la base activa al 2026-04-17:
  - `rtlab_autotrader/rtlab_core/domains/` ya aparece trackeado como arbol fuente real:
    - `truth/`
    - `evidence/`
    - `policy_state/`
    - `decision_log/`
  - el backend ya expone contratos canonicos visibles:
    - `GET /api/v1/strategies/{id}/truth`
    - `GET /api/v1/strategies/{id}/evidence`
    - `GET/PATCH /api/v1/bots/{id}/policy-state`
    - `GET /api/v1/bots/{id}/decision-log`
  - el frontend base ya consume esos contratos en `strategies/[id]` y `execution`;
  - todavia sobreviven fallbacks transicionales para degradar con honestidad si un backend remoto no expone el contrato esperado, pero eso ya no equivale a decir que `RTLRESE-14` no este integrada.
- Conclusión operativa honesta:
  - la frontera 13/14/15 ya quedo absorbida de forma usable en la base real;
  - cualquier pendiente restante ya no es "mergear RTLRESE-13/14/15", sino seguir achicando compatibilidad transicional sin romper consumidores remotos atrasados;
  - por lo tanto, cualquier lectura de `SOURCE_OF_TRUTH` debe distinguir:
    - cierre historico de frontera
    - estado efectivamente integrado hoy en la base activa
- Criterio documental adoptado desde RTLRESE-16:
  - no volver a describir `Sharpe`, `Max DD`, `WinRate`, `trades` o `confidence` runtime como si fueran parte de `strategy_truth`;
  - no volver a mezclar `policy_state` del bot con `decision_log` en la misma definicion semantica;
  - mantener explicitado cuando algo sea `legacy`, `derivado` o `agregado`.

## Actualizacion tecnica RTLRESE-7 (strategy_evidence legacy/quarantine) - 2026-03-16

- Se consolida una frontera minima y explicita para `strategy_evidence` en:
  - `ExperienceStore`
  - `RegistryDB`
  - `OptionBLearningEngine`
- Estados canonicos de evidencia:
  - `trusted`: metadata critica, costos y trazabilidad suficientes.
  - `legacy`: evidencia usable pero degradada.
  - `quarantine`: evidencia no confiable para aprendizaje/ranking/guidance.
- Reglas minimas implementadas:
  - `quarantine` cuando falta alguno de estos minimos:
    - `asset` o `timeframe`
    - trazabilidad temporal suficiente (`start_ts`, `end_ts` o `created_at`)
    - `dataset_hash` en `source=backtest`
    - costos totales completos (`gross_pnl_total`, `net_pnl_total`, `total_cost`)
  - `legacy` cuando la evidencia sigue siendo usable pero llega degradada:
    - `costs_breakdown` faltante pero reconstruible desde trades
    - `dataset_source` faltante en `backtest`
    - `commit_hash` faltante
    - `validation_mode` faltante en `backtest`
    - `feature_set` faltante o `unknown`
    - componentes de costo faltantes
    - `validation_quality=synthetic_or_bootstrap`
- Efecto operativo real:
  - `quarantine` queda excluida de:
    - `regime_kpi`
    - `strategy_policy_guidance`
    - contexts/rankings/proposals de Option B
  - `legacy` sigue visible, pero:
    - baja `validation_factor`
    - fuerza `needs_validation`
    - agrega `legacy_evidence_present` en razones de proposal
  - guidance deja nota explicita cuando hubo episodios `legacy` o `quarantine`.
- Persistencia/lectura actual:
  - cada `experience_episode.summary` guarda:
    - `evidence_status`
    - `evidence_flags`
    - `learning_excluded`
  - `RegistryDB.list_experience_episodes(...)` materializa esos campos para consumidores internos.
- Alcance deliberadamente acotado:
  - no se tocaron frontend ni endpoints nuevos en esta issue;
  - no se mezclo RTLRESE-7 con RTLRESE-10.
- Validacion local ejecutada:
  - `uv run --project rtlab_autotrader python -m py_compile rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/learning/option_b_engine.py rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/tests/test_learning_experience_option_b.py` -> PASS
  - `uv run --project rtlab_autotrader --extra dev python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS (`8 passed`)
## RTLRESE-10 · Research funnel + trial ledger por API y frontend - 2026-03-16

- API nueva:
  - `GET /api/v1/research/funnel`
  - `GET /api/v1/research/trial-ledger`
- Fuente operativa usada por esta vista:
  - catalogo de backtests (`BacktestCatalogDB`)
  - evidencia persistida `experience_episode` (`source=backtest`)
  - propuestas de aprendizaje (`learning_proposal`)
- Frontera semantica visible:
  - `strategy_truth` no cambia en esta issue
  - `strategy_evidence` se expone como funnel/ledger de research
  - `bot_policy_state` y `bot_decision_log` no se mezclan en esta pantalla
- Clasificacion operativa actual de evidence:
  - `trusted`: metadata, costos y trazabilidad completas
  - `legacy`: evidencia degradada o solo catalogada; visible, pero no debe venderse como evidence fuerte
  - `quarantine`: faltan metadata critica, costos completos o trazabilidad suficiente
  - `learning_excluded` se expone como flag operativo del ledger/funnel para distinguir evidencia no apta
- Compatibilidad legacy mantenida:
  - si un run existe solo en catalogo y no en `experience_episode`, se muestra como `legacy` con flag `catalog_only_no_episode`
  - en esta rama el status de evidence todavia se deriva on-the-fly desde metadata/costos/trazabilidad actuales; no depende aun de una columna canonica persistida
- Frontend:
  - `Backtests` agrega una seccion `Research Funnel y Trial Ledger`
  - la seccion nueva convive con `Backtests / Runs` y `Research Batch`; no reemplaza contratos legacy existentes
  - la UI marca `trusted/legacy/quarantine` y evita presentar evidence degradada como si fuera evidencia confiable
- Validacion ejecutada en esta rama:
  - `py_compile` sobre `app.py` y `test_web_live_ready.py` -> PASS
  - smoke funcional directo sobre los helpers nuevos del modulo (`_research_funnel_payload`, `_collect_research_trial_ledger_items`) con `user_data` temporal -> PASS
  - smoke HTTP con `pytest`/`TestClient` no corrio por limitacion de entorno: falta `httpx` en la venv de `rtlab_autotrader`

## Hotfix shadow/beast + evidencia local controlada - 2026-03-06

- `ShadowRunConfig` ya no rompe import en Python 3.13:
  - `costs` pasa a `default_factory(...)` en vez de usar un default mutable directo.
- Shadow/mock queda alineado a lo que el motor necesita hoy:
  - default real `lookback_bars=300` en runner + API + env default;
  - evidencia local: con `120` el ciclo falla por dataset corto; con `300` crea `1` episodio `source=shadow` y `5` trades persistidos.
- `Modo Bestia`:
  - `_default_beast_policy_cfg()` lee la policy desde `self.engine.repo_root`;
  - evidencia local: `beast/status` responde `enabled=true` y el batch real `BX-000001` termina `COMPLETED` sobre `BTCUSDT 5m`.
- Evidencia escrita de este tramo:
  - `docs/audit/LEARNING_EXPERIENCE_VALIDATION_20260306.md`
- Estado remoto abierto:
  - el preview Vercel del commit `ffabe9e` sigue fallando;
  - por lo tanto, la rama tecnica hoy esta validada localmente para este bloque, pero no tiene preview web sano.

## Actualizacion tecnica experience learning + shadow + backtests UX - 2026-03-06

- Backend de aprendizaje:
  - `RegistryDB` ya persiste:
    - `experience_episode`
    - `experience_event`
    - `regime_kpi`
    - `learning_proposal`
    - `strategy_policy_guidance`
  - `ConsoleStore.record_experience_run(...)` cablea experiencia al cerrar runs de backtest/shadow.
- Generacion de experiencia:
  - backtest puntual:
    - `create_event_backtest_run(...)` -> `record_experience_run(..., source_override="backtest")`
  - batch/bestia:
    - `_mass_backtest_eval_fold(...)` llama a `create_event_backtest_run(...)`
    - cada sub-run de batch genera experiencia y catalogo `batch_child`
    - batch/bestia bloquean sinteticos y exigen datos reales
  - shadow/mock:
    - `ShadowRunner` usa market data publico de Binance Spot
    - no envia ordenes
    - persiste experiencia `source=shadow`
    - endpoints:
      - `GET /api/v1/learning/shadow/status`
      - `POST /api/v1/learning/shadow/start`
      - `POST /api/v1/learning/shadow/stop`
- Opcion B:
  - `OptionBLearningEngine` solo considera estrategias con `allow_learning=true`
  - pesos por fuente implementados:
    - `shadow=1.00`
    - `testnet=0.90`
    - `paper=0.80`
    - `backtest=0.60`
  - score real:
    - `0.45 expectancy_net_z`
    - `0.20 profit_factor_z`
    - `0.10 sharpe_z`
    - `0.10 psr_z`
    - `0.05 dsr_z`
    - `-0.10 max_dd_z`
    - `-0.05 turnover_cost_z`
  - bloqueos reales:
    - `n_trades_total<120`
    - `n_days_total<90`
    - `n_trades_regime<30`
    - `expectancy_net<=0`
    - `cost_stress_1_5x<0`
    - `pbo>threshold`
    - `dsr<threshold`
    - `mixed_feature_set`
    - mismatch contra baseline feature set
  - NO activa estrategias sola; crea propuestas Opcion B.
- Frontend `Strategies`:
  - muestra experiencia resumida
  - muestra propuestas Opcion B
  - muestra guidance por estrategia
  - muestra estado/control de shadow
  - muestra experiencia por fuente por bot (`shadow/backtest/...`)
  - agrega ayuda textual para modos:
    - `shadow`
    - `paper`
    - `testnet`
    - `live` visible como modo gated: si `preflight/readiness/gates` no pasan, queda bloqueado fail-closed
- Frontend `Backtests`:
  - agrega selector de bot para research batch
  - agrega accion `Usar pool del bot`
  - explica diferencia entre batch y shadow/mock
  - muestra estado de scheduler/budget de Modo Bestia
  - `Backtests / Runs` ya soporta vista centrica por bot:
    - filtro `bot_id`
    - chips `related_bot_ids/related_bots` por run
    - historial por fuente (`backtest/shadow/paper/testnet`) usando `bots.metrics.experience_by_source`
    - metricas acumuladas por bot en la misma pantalla
  - fix real:
    - `GET /api/v1/runs` ya no pide `limit=5000`
    - ahora usa `limit=2000`, alineado con el maximo permitido por API y corrige el `422` de la vista `Backtests / Runs`
- Policy `Modo Bestia`:
  - `config/policies/beast_mode.yaml` actual:
    - `enabled: true`
    - `requires_postgres: true`
  - en esta fase el scheduler sigue como `local_scheduler_phase1`; Postgres queda marcado como recomendado, no como requisito duro de ejecucion local.
- Documentacion nueva:
  - `docs/research/EXPERIENCE_LEARNING.md`
  - `docs/research/BRAIN_OF_BOTS.md`
  - `docs/runbooks/SHADOW_MODE.md`
- Validacion local ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/shadow_runner.py rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/learning/option_b_engine.py` -> PASS
  - `python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS
  - `npm run lint -- "src/app/(app)/backtests/page.tsx" "src/app/(app)/strategies/page.tsx" "src/lib/types.ts"` -> PASS
  - `npm run build` (`rtlab_dashboard`) -> PASS
- Riesgos abiertos:
  - LIVE sigue `NO GO`
  - NO EVIDENCIA de RL offline serio como motor core
  - NO EVIDENCIA de OPE robusto (`IPS/DR/SWITCH`) integrado al promotion path
  - la vista bot-centrica de runs hoy relaciona un run con un bot por las estrategias que estan en el pool actual del bot; NO EVIDENCIA de atribucion historica exacta `run_id -> bot_id` persistida en catalogo
  - parte de la bibliografia TXT local esta vacia/danada; cuando eso pasa se usa otra fuente local valida o fuente oficial del mismo nivel
  - preview Vercel de `feature/learning-experience-v1` sigue fallando; la validacion positiva de este bloque es local, no por preview web

## Actualizacion operativa staging persistence + checks (run 22741651051) - 2026-03-05

- Infra staging:
  - volumen adjunto en `/app/user_data`;
  - permisos corregidos para runtime user (`uid=1000`):
    - `chown -R 1000:1000 /app/user_data`
    - `chmod 775 /app/user_data`
  - `RTLAB_USER_DATA_DIR=/app/user_data`.
- Health staging actual:
  - `ok=true`
  - `mode=paper`
  - `runtime_ready_for_live=false`
  - `storage.persistent_storage=true`.
- Revalidacion remota (`strict=true`):
  - run `22741651051` -> `success`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741651051_20260305.md`.

## Actualizacion tecnica AP-BOT-1035 (checks staging no-live con strict=true) - 2026-03-05

- `scripts/ops_protected_checks_report.py`:
  - nuevo flag `--allow-staging-warns`;
  - cuando aplica a URL `staging`, permite aprobacion operativa no-live para:
    - `G10_STORAGE_PERSISTENCE=WARN`;
    - `breaker_status=NO_DATA`.
- `/.github/workflows/remote-protected-checks.yml`:
  - agrega `--allow-staging-warns` automaticamente cuando `base_url` contiene `staging`.
- Revalidacion remota staging:
  - run `22741088468` -> `success`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=WARN`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741088468_20260305.md`.
- Nota operativa:
  - `storage_persistent` sigue en `false` en staging (warning informativo no-live);
  - pruebas de volumen en staging con `/data` y `/app/user_data` provocaron crash por permisos de SQLite y se revertio a `/tmp/rtlab_user_data`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1035_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1034 (runner checks con diagnostico en fallo temprano) - 2026-03-05

- `scripts/run_protected_checks_github_vm.ps1`:
  - ante workflow `failure` sin JSON de checks, ahora emite `protected_checks_summary_<run_id>.json` con `NO_EVIDENCE` en campos canonicos.
- Evidencia staging:
  - run `22738098708` -> `failure` por login:
    - `ERROR: Login fallo: 401 {"detail":"Invalid credentials"}`
  - documento: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22738098708_20260305.md`.
- Sanity run en produccion tras patch del runner:
  - run `22738228159` -> `success`
  - campos canonicos: `overall_pass=true`, `protected_checks_complete=true`, `g10_status=PASS`, `g9_status=WARN`, `breaker_ok=true`, `internal_proxy_status_ok=true`
  - documento: `docs/audit/PROTECTED_CHECKS_GHA_22738228159_20260305.md`.
- Estado:
  - `RTLAB_STAGING_ADMIN_PASSWORD` ya fue alineado con Railway staging;
  - `username=Wadmin` sigue vigente en staging.
- Bloqueante actual de staging:
  - no es auth; es operativo (`G10 WARN` + `breaker NO_DATA` en `strict=true`).
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1034_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion operativa staging checks (run 22739570506) - 2026-03-05

- `Remote Protected Checks (GitHub VM)` contra staging:
  - run `22739570506` completado en `failure`.
- Estado post-ajuste de secreto:
  - autenticacion staging funcional (sin `401 Invalid credentials`);
  - bloqueo actual no-live en staging:
    - `g10_status=WARN` por `storage_persistent=false`;
    - `breaker_ok=false` por `breaker_status=NO_DATA` en modo `strict=true`.
- Campos canonicos:
  - `overall_pass=false`
  - `protected_checks_complete=true`
  - `g10_status=WARN`
  - `g9_status=WARN`
  - `breaker_ok=false`
  - `internal_proxy_status_ok=true`
- Evidencia:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22739570506_20260305.md`.

## Actualizacion operativa staging checks (run 22740010128) - 2026-03-05

- `Remote Protected Checks (GitHub VM)` contra staging:
  - run `22740010128` completado en `failure`.
- Resultado:
  - autenticacion staging confirmada (sin `401`);
  - persisten bloqueos operativos no-live:
    - `g10_status=WARN` por `storage_persistent=false`;
    - `breaker_ok=false` por `breaker_status=NO_DATA` en `strict=true`.
- Campos canonicos:
  - `overall_pass=false`
  - `protected_checks_complete=true`
  - `g10_status=WARN`
  - `g9_status=WARN`
  - `breaker_ok=false`
  - `internal_proxy_status_ok=true`
- Evidencia:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22740010128_20260305.md`.

## Actualizacion tecnica AP-BOT-1033 (submit fail-closed sin reconciliacion valida) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` ahora exige `runtime_reconciliation_ok=true` para submit remoto;
  - cuando falla, retorna `reason=reconciliation_not_ok`.
- Objetivo:
  - impedir operacion remota sobre estado desincronizado.
- Tests de regresion:
  - `test_runtime_sync_testnet_skips_submit_when_reconciliation_not_ok`
  - ajuste de `test_runtime_sync_testnet_skips_submit_when_local_open_orders_remain_unverified`.
- Evidencia de validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1033_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1032 (submit fail-closed sin account snapshot) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` bloquea submit remoto cuando `account_positions_ok=false`;
  - expone `reason=account_positions_fetch_failed` + `error` con motivo operativo;
  - `sync_runtime_state(...)` ahora pasa `account_positions_reason` al submitter.
- Objetivo:
  - evitar apertura de nuevas ordenes remotas sin estado de cuenta verificado.
- Tests de regresion:
  - `test_runtime_sync_testnet_skips_submit_when_account_positions_fetch_fails`
  - ajuste de `test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency`.
- Evidencia de validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1032_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1031 (runtime fail-closed ante orden no verificada) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_close_absent_local_open_orders(...)` ahora preserva orden local cuando falla `GET /api/v3/order` (sin cierre ciego);
  - `_maybe_submit_exchange_runtime_order(...)` agrega guard `local_open_orders_present` para bloquear submit remoto si queda orden local abierta no verificada.
- Objetivo:
  - evitar duplicacion de ordenes por vacio transitorio de `openOrders` + error de `order status`.
- Tests de regresion:
  - `test_runtime_sync_testnet_keeps_absent_local_open_order_when_order_status_fetch_fails`
  - `test_runtime_sync_testnet_skips_submit_when_local_open_orders_remain_unverified`
- Evidencia de validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1031_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1030 (automatizacion checks protegidos GH VM) - 2026-03-05

- Nuevo script:
  - `scripts/run_protected_checks_github_vm.ps1`
- Objetivo:
  - ejecutar `Remote Protected Checks (GitHub VM)` desde PowerShell local sin depender de `gh` en `PATH`;
  - extraer automaticamente los 6 campos de cierre desde artifacts oficiales del run.
- Flujo implementado:
  - dispatch por `workflow_dispatch` (`remote-protected-checks.yml`);
  - polling de estado hasta completion;
  - descarga de artifact `protected-checks-<run_id>`;
  - parseo del JSON `ops_protected_checks_gha_<run_id>_*.json`;
  - emision de resumen `artifacts/protected_checks_gha_<run_id>/protected_checks_summary_<run_id>.json`.
- Revalidacion operativa:
  - run `22734260830` en `success`:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22734260830_20260305.md`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1030_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1023 (smoke staging automatizado) - 2026-03-05

- `scripts/staging_smoke_report.py` (nuevo):
  - smoke no-live para staging con salida `json/md` en `artifacts/`;
  - valida `frontend /login`, `backend /api/v1/health`, modo no-live (`paper/testnet`) y `runtime_ready_for_live=false`;
  - valida `/api/v1/bots` solo cuando hay token/credenciales disponibles.
- Evidencia operativa:
  - `docs/audit/STAGING_SMOKE_20260305.md`
  - corrida: `python scripts/staging_smoke_report.py --report-prefix artifacts/staging_smoke_ghafree`.
- Resultado de la corrida de referencia:
  - `front_login_status_code=200`
  - `health_ok=true`
  - `health_mode=paper`
  - `runtime_ready_for_live=false`
  - `overall_pass=true`
- Trazabilidad de autenticacion:
  - en esta corrida local: `NO_EVIDENCE_NO_SECRET` para checks autenticados (sin `RTLAB_AUTH_TOKEN`/`RTLAB_ADMIN_PASSWORD` locales).
  - cobertura autenticada completa mantenida por reporte remoto:
    - `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.

## Actualizacion tecnica AP-BOT-1024 (workflow diario staging smoke) - 2026-03-05

- `/.github/workflows/staging-smoke.yml` (nuevo):
  - ejecuta smoke en GitHub VM por `schedule` diario y `workflow_dispatch`;
  - usa `scripts/staging_smoke_report.py` para checks de frontend/backend;
  - exige secretos cuando `require_auth_checks=true` (fail-closed);
  - publica artefactos `json/md` + `stdout` por run.
- Cobertura de controles:
  - smoke diario deja evidencia online de NO-LIVE (`mode=paper/testnet`, `runtime_ready_for_live=false`);
  - check autenticado `/api/v1/bots` queda forzado en corridas programadas.
- Trazabilidad de fuentes:
  - `docs/audit/AP_BOT_1024_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1025 (fix workflow protected-checks no-strict/password-cli) - 2026-03-05

- `/.github/workflows/remote-protected-checks.yml`:
  - corrige semantica de `strict=false` agregando `--no-strict` explicito;
  - elimina fallback legacy `--password` por CLI.
- Evidencia operativa del hallazgo:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732410544_20260305.md`
  - run staging en `main` fallo (`401 Invalid credentials`) y mostro uso legacy de `--password`.
- Validacion operativa del fix (rama tecnica):
  - `docs/audit/PROTECTED_CHECKS_GHA_22732584979_NON_STRICT_20260305.md`
  - run `22732584979` en `success` con `strict=false` y `overall_pass=false` (esperado por `expect_g9=PASS`).
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1025_BIBLIO_VALIDATION_20260305.md`.
- Estado:
  - fix versionado en rama tecnica;
  - pendiente re-run remoto tras merge para confirmar flujo corregido en default branch.

## Actualizacion tecnica AP-BOT-1026 (secretos por entorno en workflows remotos) - 2026-03-05

- `/.github/workflows/remote-protected-checks.yml`:
  - selecciona credenciales por entorno segun `base_url`:
    - staging: `RTLAB_STAGING_AUTH_TOKEN` / `RTLAB_STAGING_ADMIN_PASSWORD`;
    - fallback: `RTLAB_AUTH_TOKEN` / `RTLAB_ADMIN_PASSWORD`.
- `/.github/workflows/staging-smoke.yml`:
  - prioriza secretos de staging con fallback seguro a secretos globales.
- Validacion operativa:
  - `docs/audit/PROTECTED_CHECKS_GHA_22732769817_20260305.md`
  - run `22732769817` en `success` (`strict=true`, `expect_g9=WARN`) sin regression.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1026_BIBLIO_VALIDATION_20260305.md`.
- Pendiente:
  - run staging `22732896736` confirma que `RTLAB_STAGING_AUTH_TOKEN` y `RTLAB_STAGING_ADMIN_PASSWORD` estan vacios;
  - se requiere cargar al menos uno para validar checks protegidos autenticados en staging.
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732896736_20260305.md`.

## Actualizacion tecnica AP-BOT-1027 (hardening no-fallback cross-env de credenciales) - 2026-03-05

- `/.github/workflows/remote-protected-checks.yml`:
  - staging consume solo `RTLAB_STAGING_AUTH_TOKEN` / `RTLAB_STAGING_ADMIN_PASSWORD`;
  - produccion consume solo `RTLAB_AUTH_TOKEN` / `RTLAB_ADMIN_PASSWORD`.
- `/.github/workflows/staging-smoke.yml`:
  - smoke de staging con auth requiere secretos `RTLAB_STAGING_*` (sin fallback a secretos globales).
- Objetivo:
  - evitar uso accidental de credenciales de produccion contra staging.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1027_BIBLIO_VALIDATION_20260305.md`.
- Evidencia operativa post-push:
  - produccion: run `22733438064` en `success`
    - `docs/audit/PROTECTED_CHECKS_GHA_22733438064_20260305.md`
  - staging: run `22733461982` en `failure` fail-fast por secreto faltante
    - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22733461982_20260305.md`
- Pendiente:
  - cargar `RTLAB_STAGING_AUTH_TOKEN` o `RTLAB_STAGING_ADMIN_PASSWORD` y repetir run staging.

## Actualizacion tecnica AP-BOT-1028 (runbook de secrets GitHub Actions) - 2026-03-05

- Nuevo runbook:
  - `docs/deploy/GITHUB_ACTIONS_SECRETS.md`
- Contenido:
  - secrets requeridos por entorno (`RTLAB_*` vs `RTLAB_STAGING_*`);
  - comandos `gh secret list/set`;
  - validacion operativa posterior de workflows remotos.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1028_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1029 (runtime exchange readiness refresh) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._runtime_exchange_ready(...)` ahora fuerza refresh de diagnostico si el cache previo da fail.
  - objetivo: reducir latencia de recuperacion cuando exchange vuelve a estar operativo.
- Tests agregados:
  - `test_runtime_exchange_ready_forces_refresh_after_cached_failure`
  - `test_runtime_exchange_ready_uses_cached_success_without_forced_refresh`
- Evidencia:
  - `docs/audit/AP_BOT_1029_BIBLIO_VALIDATION_20260305.md`
- Revalidacion remota:
  - `docs/audit/PROTECTED_CHECKS_GHA_22733869311_20260305.md` (`success`).
- Estado:
  - cambio interno de runtime, sin impacto en contrato API.

## Actualizacion tecnica AP-8001 (BFF mock fallback fail-closed) - 2026-03-04

- `rtlab_dashboard/src/lib/security.ts`:
  - nueva regla centralizada `shouldFallbackToMockOnBackendError(...)`;
  - `staging/production` quedan bloqueados para fallback mock aunque exista `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=true`;
  - si `USE_MOCK_API=false`, el fallback queda bloqueado tambien en desarrollo.
- `rtlab_dashboard/src/app/api/[...path]/route.ts` y `rtlab_dashboard/src/lib/events-stream.ts`:
  - usan la regla centralizada (se elimina evaluacion local permisiva).
- Tests:
  - `rtlab_dashboard/src/lib/security.test.ts` agrega casos de entorno protegido (`NODE_ENV=production`, `APP_ENV=staging`), disable explicito y enable controlado en local.
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).
- Estado:
  - riesgo de fallback mock accidental en staging/prod queda mitigado en BFF;
  - LIVE sigue **NO GO** por pendientes runtime end-to-end fuera de este AP.

## Actualizacion tecnica AP-8002 (security CI tooling estable) - 2026-03-04

- `.github/workflows/security-ci.yml`:
  - `setup-python` unificado en `3.11` para coherencia con workflows remotos existentes;
  - `actions/checkout` ahora usa `fetch-depth: 0` para que `gitleaks git` escanee historial completo y aplique baseline canonica sin falsos positivos por clone shallow;
  - instalacion de `gitleaks` cambia a binario oficial versionado (`8.30.0`) desde release de GitHub;
  - se elimina dependencia del install script remoto `master/install.sh` (mas fragil);
  - descarga con `curl --retry` + `tar` + `chmod` para reducir fallos transitorios en runners;
  - fallback a install script versionado (`v8.30.0`) si el tarball falla;
  - verificacion fail-closed de binario instalado (`$RUNNER_TEMP/bin/gitleaks`);
  - export de `PATH` en el mismo step para validar `gitleaks version` sin depender de step siguiente.
  - `scripts/security_scan.sh` usa baseline canonica versionada en `docs/security/gitleaks-baseline.json` (con override opcional por `GITLEAKS_BASELINE_PATH`).
- Estado:
  - root-cause del fail en `Security CI` identificado: clone shallow (`fetch-depth=1`) + baseline historica de gitleaks;
  - fix aplicado en workflow (`fetch-depth: 0`) y validado en GitHub Actions:
    - run `22697627615`: `success` (job `security` `65807494809`);
  - `FM-SEC-004` queda en `CERRADO`;
  - no se toco runtime ni logica de trading.

## Actualizacion tecnica AP-8007 (gates canonicos sin fallback permisivo) - 2026-03-04

- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `_canonical_gates_thresholds` deja de usar fallback a `knowledge/policies/gates.yaml`;
  - si `config/policies/gates.yaml` falta o falla parseo, aplica default `fail-closed`:
    - `pbo_max=0.05`
    - `dsr_min=0.95`
    - `source=config/policies/gates.yaml:default_fail_closed`.
- `rtlab_autotrader/rtlab_core/rollout/gates.py`:
  - `GateEvaluator` usa fuente canonica `config/policies/gates.yaml` como `source_path`;
  - cuando falta/esta invalido, opera en `source_mode=default_fail_closed` y exige `pbo/dsr` como requeridos.
- Tests nuevos/validacion:
  - `rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py` (nuevo).
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).
- Estado:
  - se reduce la divergencia `config` vs `knowledge` para thresholds de gates;
  - LIVE sigue **NO GO** (pendiente runtime real end-to-end + cierre security CI run green).

## Actualizacion tecnica AP-8012 (breaker-events strict default fail-closed) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `breaker_events_integrity(..., strict=True)` ahora es estricto por default;
  - endpoint `/api/v1/diagnostics/breaker-events` pasa a `strict=true` por default.
- `scripts/ops_protected_checks_report.py`:
  - `--strict` queda habilitado por default;
  - se agrega override explicito `--no-strict` para compatibilidad legacy controlada.
- Tests de regresion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.
- Estado:
  - `FM-EXEC-003` queda en `CERRADO`.

## Actualizacion tecnica AP-8011 (latencia `/api/v1/bots`: optimizacion incremental) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `list_bots` deja de cargar recomendaciones antes del cache-check (se cargan solo en `cache miss`);
  - `get_bots_overview` indexa runs filtrando por estrategias realmente presentes en pools de bots;
  - nuevo cap por estrategia/modo para indexado de runs:
    - `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE` (default `250`);
  - perf debug agrega:
    - `runs_indexed`,
    - `runs_skipped_outside_pool`,
    - `max_runs_per_strategy_mode`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Estado:
  - optimizacion aplicada sin cambio de contrato API;
  - pendiente: rerun remoto de benchmark para confirmar impacto en `p95` productivo de forma estable.

## Actualizacion tecnica AP-8003 (runtime reconcile open-orders fail-closed) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - reconciliacion runtime (`_reconcile`) compara `openOrders` del exchange contra `OMS.open_orders()` (no contra ordenes locales cerradas);
  - nuevo cierre local de ordenes abiertas ausentes en exchange tras grace configurable:
    - `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`);
  - objetivo: evitar desync falso persistente por ordenes ya cerradas/finalizadas.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`.
  - nuevo `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).
- Estado:
  - mitigacion adicional sobre `FM-EXEC-001/FM-EXEC-005/FM-RISK-002`;
  - LIVE permanece **NO GO** hasta cierre completo del loop broker/exchange end-to-end.

## Actualizacion cleanroom docs + staging NO-LIVE (2026-03-04)

- Se aplico limpieza de documentacion para reducir confusion operativa:
  - nuevos indices vigentes:
    - `docs/START_HERE.md`
    - `docs/audit/INDEX.md`
  - historico movido a `docs/_archive/*` con regla explicita `NO USAR PARA DECISIONES` en:
    - `docs/_archive/README_ARCHIVE.md`
- Seguridad DocOps agregada:
  - `docs/security/LOGGING_POLICY.md` (CWE-532: no secretos en logs/CLI, redaccion obligatoria, checklist por release).
  - `docs/SECURITY.md` referencia explicita a la policy de logging seguro.
- Staging online validado (solo no-live):
  - frontend: `https://bot-trading-ia-staging.vercel.app`
  - backend: `https://bot-trading-ia-staging.up.railway.app`
  - health backend esperado y verificado: `ok=true`, `mode=paper`, `runtime_ready_for_live=false`.
- Runbooks de despliegue/rollback agregados:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- Restriccion vigente:
  - `LIVE_TRADING_ENABLED=false` en staging.
  - estado LIVE global permanece **NO GO** por decision operativa y tramo tecnico final pendiente.
- Regla de bibliografia vigente para decisiones tecnicas:
  - primero bibliografia local (`docs/reference/BIBLIO_INDEX.md` + `docs/reference/biblio_raw/*`);
  - si falta cobertura local: solo fuentes primarias oficiales/papers de nivel equivalente (sin blogs como fuente principal).

## Actualizacion tecnica AP-BOT-1001/AP-BOT-1002 (coherencia de cerebro) - 2026-03-04

- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`:
  - se elimino hardcode unico de exits para todas las estrategias;
  - ahora cada familia usa perfil propio (stop/take/trailing/time-stop) alineado con `knowledge/strategies/strategies_v2.yaml`;
  - `trend_scanning` selecciona perfil efectivo segun sub-regimen;
  - `reason_code` del trade refleja la familia real ejecutada (no queda fijo en `trend_pullback`).
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_infer_orderflow_feature_set` pasa a fail-closed: sin evidencia explicita devuelve `orderflow_unknown`;
  - validacion de promotion agrega check `known_feature_set`;
  - busqueda de baseline evita filtro estricto por feature-set cuando el candidato esta en `unknown`.
- Tests nuevos/focales:
  - `rtlab_autotrader/tests/test_backtest_execution_profiles.py`
  - `rtlab_autotrader/tests/test_web_feature_set_fail_closed.py`
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.
- Estado:
  - Coherencia estrategia->ejecucion: reforzada.
  - Promotion sin evidencia de feature-set: fail-closed.
  - LIVE: sigue NO GO hasta cerrar runtime real end-to-end (decision operativa vigente).

## Actualizacion tecnica AP-BOT-1003 (latencia `/api/v1/bots`) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo umbral `BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT` (default `40`) para polling por defecto;
  - cuando `recent_logs` no viene explicito y hay muchos bots, se desactiva carga de logs recientes automaticamente;
  - override explicito `?recent_logs=true` se mantiene disponible;
  - cache key de `/api/v1/bots` ahora distingue `source=default|explicit` para evitar reutilizar payload de una politica en otra;
  - headers/debug perf reflejan el estado efectivo (`X-RTLAB-Bots-Recent-Logs`, `logs_auto_disabled`).
- Tests de regresion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Impacto esperado:
  - menos picos de latencia en cardinalidad alta de bots sin romper el contrato del endpoint.

## Actualizacion tecnica AP-BOT-1004 (runtime testnet mas real) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge` ahora sincroniza OMS local con `openOrders` del exchange (`clientOrderId/orderId`, `origQty`, `executedQty`, `symbol`, `side`);
  - en `testnet/live` se desactiva progresion de fills simulados locales (la simulacion de fill incremental queda solo para `paper`);
  - reconciliacion usa estado OMS ya sincronizado contra exchange antes de evaluar desync.
- Test nuevo de regresion:
  - `test_runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`9 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Estado:
  - runtime no-live se acerca a fuente real de exchange;
  - pendiente para cierre total: submit/cancel/fill real end-to-end con idempotencia de orden y reconciliacion completa de posiciones.

## Actualizacion tecnica AP-BOT-1005 (idempotencia cancel remoto) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - runtime agrega idempotencia de cancel remoto por `client_order_id/order_id` con ventana temporal configurable:
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC` (default `30`);
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS` (default `2000`);
  - en eventos `stop/kill/mode_change` y runtime `real` en `testnet/live`:
    - consulta `openOrders` reales;
    - emite `DELETE /api/v3/order` con `origClientOrderId` (o `orderId`);
    - evita duplicar cancel de la misma orden dentro de TTL;
    - trata `unknown order` como estado ya-cancelado (idempotente).
  - reconciliacion reutiliza parser comun de `openOrders` para coherencia de `client_order_id`/`order_id`.
- Test nuevo:
  - `test_runtime_stop_testnet_cancels_remote_open_orders_idempotently`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`10 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.

## Actualizacion tecnica AP-BOT-1006 (submit remoto idempotente, default off) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - runtime agrega submit remoto opcional (`POST /api/v3/order`) en `testnet/live` con `newClientOrderId` estable por ventana temporal;
  - guardas nuevas de entorno (fail-safe): 
    - `RUNTIME_REMOTE_ORDERS_ENABLED` (default `false`),
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC` (default `60`),
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS` (default `2000`),
    - `RUNTIME_REMOTE_ORDER_NOTIONAL_USD` (default `15`),
    - `RUNTIME_REMOTE_ORDER_SYMBOL` (default `BTCUSDT`),
    - `RUNTIME_REMOTE_ORDER_SIDE` (default `BUY`);
  - si Binance devuelve `duplicate order` (`-2010`) se trata como exito idempotente;
  - `sync_runtime_state` expone trazabilidad:
    - `runtime_last_remote_submit_at`,
    - `runtime_last_remote_client_order_id`,
    - `runtime_last_remote_submit_error`.
- Tests nuevos:
  - `test_runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default`.
  - `test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency`.
- Estado:
  - submit remoto queda integrado pero apagado por defecto (sin impacto en no-live actual);
  - LIVE sigue **NO GO** hasta cerrar pipeline completo de ejecucion/posiciones/fills reales end-to-end.

## Actualizacion tecnica AP-BOT-1007 (reconciliacion de posiciones por account snapshot) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - runtime `testnet/live` consulta `GET /api/v3/account` firmado y deriva posiciones desde balances reales (spot);
  - nuevos campos de trazabilidad en estado:
    - `runtime_account_positions_ok`,
    - `runtime_account_positions_verified_at`,
    - `runtime_account_positions_reason`;
  - `RuntimeBridge.positions()` y `risk_snapshot` priorizan posiciones reconciliadas por account snapshot cuando estan disponibles;
  - fallback seguro: si falla `/api/v3/account`, se conserva posicionamiento derivado de `openOrders` (sin cortar runtime loop).
- Tests nuevos:
  - `test_runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot`.
  - `test_runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`7 passed`).
- Estado:
  - runtime no-live queda mas cercano a estado real de exchange (ordenes + balances);
  - LIVE sigue **NO GO** hasta cierre total de costos/fills finales end-to-end.

## Actualizacion tecnica AP-BOT-1008 (costos runtime por fill-delta) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - runtime agrega contabilidad acumulada de costos por deltas de fills observados en OMS:
    - `fills_count_runtime`,
    - `fills_notional_runtime_usd`,
    - `fees_total_runtime_usd`,
    - `spread_total_runtime_usd`,
    - `slippage_total_runtime_usd`,
    - `funding_total_runtime_usd`,
    - `total_cost_runtime_usd`,
    - `runtime_costs` (breakdown).
  - calculo incremental basado en `execution` settings (`maker/taker fees`, `spread_proxy_bps`, `slippage_base_bps`, `funding_proxy_bps`) y `mark_price` por simbolo.
  - reset de costos al iniciar runtime real o en `mode_change` para evitar mezclar sesiones.
  - `build_execution_metrics_payload` aplica fail-closed tambien a costos cuando telemetry es sintetica.
- Tests nuevos/ajustados:
  - `test_runtime_execution_metrics_accumulate_costs_from_fill_deltas`.
  - `test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic` (ahora valida costos runtime en cero).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`9 passed`).
- Estado:
  - runtime no-live ya refleja ordenes + balances + costos estimados por fill;
  - LIVE sigue **NO GO** (faltan cierre de wiring final de ejecucion y hardening operativo global).

## Actualizacion tecnica AP-BOT-1009 (hardening `--password` + security CI) - 2026-03-04

- `.github/workflows`:
  - `security-ci.yml` agrega guard para bloquear `--password` en workflows/PowerShell de automatizacion.
- `scripts`:
  - `seed_bots_remote.py` y `check_storage_persistence.py`:
    - `--password` pasa a DEPRECATED/inseguro;
    - por defecto se bloquea uso CLI de password (se puede habilitar explicitamente con `ALLOW_INSECURE_PASSWORD_CLI=1`);
    - login password prioriza entorno seguro (`RTLAB_ADMIN_PASSWORD`).
  - `run_bots_benchmark_sweep_remote.ps1`:
    - elimina paso de `--password` por CLI a scripts python;
    - inyecta password temporalmente por variables de entorno y restaura al finalizar.
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\Program Files\Git\bin\bash.exe scripts/security_scan.sh` -> PASS (`pip-audit` sin vulns conocidas + `gitleaks` sin leaks).
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.
- Estado:
  - riesgo de exposicion de secretos por CLI en automatizacion remota queda mitigado;
  - LIVE sigue **NO GO** por pendientes funcionales finales fuera de seguridad (`runtime` end-to-end total + hardening final).

## Actualizacion tecnica AP-BOT-1010 (cierre no-live formal) - 2026-03-04

- Artefacto de cierre agregado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- Consolidado operativo:
  - no-live/testnet queda en **GO** con evidencia de runtime + seguridad + hardening.
  - LIVE queda en **NO GO** por decision operativa (postergado hasta configuracion final de APIs/canary).
- Evidencia de cierre usada:
  - pruebas runtime focales: PASS.
  - `scripts/security_scan.sh`: PASS.
  - guard CI de `--password`: activo.

## Actualizacion tecnica AP-BOT-1011 (runtime por senal de estrategia, fail-closed) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - submit remoto runtime deja de ser semilla ciega y pasa a intencion derivada de estrategia principal (`store.registry.get_principal(mode)` + `strategy_or_404`);
  - nuevo derivador `_runtime_order_intent(...)`:
    - fail-closed si no hay estrategia principal, no existe o esta deshabilitada;
    - usa `tags`/`params` para decidir `action=trade|flat`, `side`, `symbol`, `notional`;
  - nuevo guard temporal de submit:
    - `RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC` (default `120`);
  - submit runtime aplica guardas previas antes de enviar orden:
    - `risk.allow_new_positions` debe estar habilitado;
    - si hay posiciones abiertas en account snapshot, no envia nueva orden;
    - si hay cooldown activo o `openOrders` existentes, no envia nueva orden;
  - trazabilidad runtime ampliada:
    - `runtime_last_signal_action`,
    - `runtime_last_signal_reason`,
    - `runtime_last_signal_strategy_id`,
    - `runtime_last_signal_symbol`,
    - `runtime_last_signal_side`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`;
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Estado:
  - `FM-EXEC-001` y `FM-EXEC-005` quedan mas mitigados en no-live (decision runtime ahora alineada a estrategia+risk);
  - LIVE sigue **NO GO** hasta cierre total del ciclo de ejecucion real (fills/partial fills/cancel-replace/reconciliacion final end-to-end).

## Revalidacion bibliografica AP-BOT-1011 - 2026-03-04

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Criterio aplicado:
  - primero bibliografia local indexada (`docs/reference/BIBLIO_INDEX.md`);
  - cuando no hay regla teorica explicita, se declara `NO EVIDENCIA LOCAL` y se justifica como decision de ingenieria fail-closed de runtime.

## Actualizacion tecnica AP-BOT-1012 (resolver orden ausente por `order status`) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_close_absent_local_open_orders(...)` ahora consulta `GET /api/v3/order` antes de cancelar localmente una orden ausente en `openOrders`;
  - nuevo `_fetch_exchange_order_status(...)` para obtener `status/origQty/executedQty` de la orden;
  - nuevo `_apply_remote_order_status_to_local(...)` para cerrar correctamente segun estado remoto:
    - `FILLED` -> cierre `FILLED` y ajuste de `filled_qty`;
    - `CANCELED/EXPIRED/EXPIRED_IN_MATCH` -> terminal cancelado;
    - `REJECTED` -> terminal rechazado;
    - `NEW/PARTIALLY_FILLED/PENDING_CANCEL` -> mantiene orden abierta;
  - cuando estado remoto confirma que la orden sigue abierta, se reinyecta en snapshot de reconciliacion para evitar desync falso en ese ciclo;
  - parser de `openOrders` guarda tambien `status` remoto si viene en payload.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`;
  - `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`;
  - ajuste de regresion en `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Estado:
  - se reduce el gap de lifecycle de orden en no-live (menos cierres ciegos por ausencia transitoria);
  - LIVE sigue **NO GO** hasta cierre de pendientes globales (`FM-EXEC-001`, `FM-EXEC-005`, `FM-RISK-002`, `FM-QUANT-008`).

## Revalidacion bibliografica AP-BOT-1012 - 2026-03-04

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Criterio aplicado:
  - primero bibliografia local indexada (`docs/reference/BIBLIO_INDEX.md`);
  - para contrato API de `order status`, uso de fuente primaria oficial de exchange.

## Actualizacion tecnica AP-BOT-1013 (riesgo del mismo ciclo antes de submit) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `sync_runtime_state(...)` mueve submit remoto de `testnet/live` para despues del calculo de riesgo del mismo ciclo;
  - submit queda condicionado a estado operativo seguro del mismo loop:
    - `decision.kill=false`,
    - `running=true`,
    - `killed=false`;
  - resultado: no se intenta orden remota cuando `runtime_risk_allow_new_positions=false` en ese mismo ciclo.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Estado:
  - `FM-RISK-002` queda mas mitigado (enforcement de riesgo y submit ya no corren desfasados en el loop);
  - LIVE sigue **NO GO** por brechas abiertas fuera de este AP.

## Revalidacion bibliografica AP-BOT-1013 - 2026-03-04

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Criterio aplicado:
  - principios de risk management y fail-closed tomados de bibliografia local indexada.

## Actualizacion tecnica AP-BOT-1014 (reuso de account snapshot en submit) - 2026-03-04

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - submit runtime ahora puede recibir snapshot de cuenta ya calculado en el ciclo (`account_positions`, `account_positions_ok`);
  - `sync_runtime_state(...)` reutiliza ese snapshot y evita doble consulta a `/api/v3/account` en el mismo loop;
  - decision funcional se mantiene: si hay posiciones abiertas, bloquea submit.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell` valida que `account_get == 1` (sin doble fetch).
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Estado:
  - mejora eficiencia de loop runtime no-live y reduce llamadas remotas redundantes;
  - LIVE sigue **NO GO** hasta cierre global de hallazgos abiertos.

## Revalidacion bibliografica AP-BOT-1014 - 2026-03-04

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Criterio aplicado:
  - principios de eficiencia operativa local + contrato API oficial para endpoints de cuenta/orden.

## Actualizacion tecnica AP-BOT-1015 (cobertura de estados remotos) - 2026-03-04

- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status`;
  - `test_runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status`.
- Alcance:
  - valida explicitamente que los estados remotos `PARTIALLY_FILLED` y `REJECTED` se reflejan correctamente en OMS local cuando la orden no aparece en `openOrders`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Estado:
  - se refuerza cobertura de regresion del lifecycle runtime no-live;
  - LIVE sigue **NO GO**.

## Revalidacion bibliografica AP-BOT-1015 - 2026-03-04

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Criterio aplicado:
  - misma base bibliografica de AP-BOT-1012 para semantica de estados de orden.

## Actualizacion tecnica AP-BOT-1016 (guard no-live para submit en `live`) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nueva bandera canonica: `LIVE_TRADING_ENABLED` (default `false`);
  - en `RuntimeBridge._maybe_submit_exchange_runtime_order(...)`:
    - para `mode=live`, bloquea submit de orden remota cuando `LIVE_TRADING_ENABLED=false`;
    - devuelve `reason=live_trading_disabled` y `error=LIVE_TRADING_ENABLED=false` (fail-closed), preservando trazabilidad de senal.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_flat_skips_remote_submit or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle or live_skips_submit_when_live_trading_disabled" -q` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`6 passed`).
- Estado:
  - staging/no-live queda mas robusto contra activacion accidental de submit en `live`;
  - LIVE sigue **NO GO** por decision operativa hasta tramo final con APIs reales/canary.

## Revalidacion bibliografica AP-BOT-1016 - 2026-03-05

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1016_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1017 (telemetria de motivo de submit runtime) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge.sync_runtime_state(...)` persiste `runtime_last_remote_submit_reason` en cada ciclo de submit/skip;
  - `_maybe_submit_exchange_runtime_order(...)` retorna `reason=submitted` cuando la orden se envia correctamente (ademas de razones de skip fail-closed ya existentes).
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell` valida `runtime_last_remote_submit_reason=submitted`;
  - `test_runtime_sync_live_skips_submit_when_live_trading_disabled` valida `runtime_last_remote_submit_reason=live_trading_disabled`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_meanreversion_submits_sell or live_skips_submit_when_live_trading_disabled or strategy_signal_flat_skips_remote_submit or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Estado:
  - mejora observabilidad operativa del runtime para diagnostico de por que se envio/no se envio orden en cada loop;
  - LIVE sigue **NO GO** por decision operativa hasta cierre final.

## Revalidacion bibliografica AP-BOT-1017 - 2026-03-05

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1017_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1019 (higiene de telemetria submit runtime) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - al salir de runtime real (`runtime_engine!=real` o `running=false`) se limpia tambien `runtime_last_remote_submit_reason`;
  - cuando el exchange no esta listo (`exchange_ready.ok=false`) tambien se limpia `runtime_last_remote_submit_reason`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "live_skips_submit_when_live_trading_disabled or clears_submit_reason_when_runtime_exits_real_mode or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Estado:
  - evita arrastre de motivo de submit de ciclos previos cuando runtime queda fuera de modo real;
  - mejora trazabilidad de diagnostico y reduce falsos positivos operativos.

## Revalidacion bibliografica AP-BOT-1019 - 2026-03-05

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1019_BIBLIO_VALIDATION_20260305.md`.

## Actualizacion tecnica AP-BOT-1020 (estados remotos avanzados en lifecycle) - 2026-03-05

- `rtlab_autotrader/rtlab_core/web/app.py`:
  - ajuste en `_apply_remote_order_status_to_local(...)`:
    - para `NEW/PENDING_CANCEL` conserva `PARTIALLY_FILLED` si hay `filled_qty>0` (evita degradar a `SUBMITTED`);
    - si `filled_qty>=qty`, cierra en `FILLED` (terminal) aun con estado remoto transitorio.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - nuevo `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "keeps_absent_open_order_open_when_order_status_is_new or keeps_partial_state_when_order_status_is_pending_cancel or updates_absent_open_order_partial_fill_from_order_status or marks_absent_open_order_expired_in_match_terminal or marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`5 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Estado:
  - reduce gap de lifecycle avanzado en reconciliacion runtime para `PENDING_CANCEL/EXPIRED_IN_MATCH`;
  - mejora coherencia de fills parciales en no-live.

## Revalidacion bibliografica AP-BOT-1020 - 2026-03-05

- Se agrega respaldo bibliografico local-first del AP en:
  - `docs/audit/AP_BOT_1020_BIBLIO_VALIDATION_20260305.md`.

## Revalidacion bibliografica AP-BOT-1006..1010 - 2026-03-04

- Se completo la revalidacion bibliografica integral por patch en:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- Cobertura:
  - `AP-BOT-1006`: idempotencia submit remoto (microestructura local + contrato API oficial).
  - `AP-BOT-1007`: reconciliacion de posiciones por account snapshot (post-trade local + endpoints oficiales).
  - `AP-BOT-1008`: costos runtime por fill-delta (impacto/spread/fees local + referencia API oficial).
  - `AP-BOT-1009`: hardening de secretos CLI (tokenizacion local + fuentes primarias OS/CWE).
  - `AP-BOT-1010`: cierre no-live (disciplina operativa local + rollout/rollback oficial).
- Regla aplicada:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`);
  - cuando falto especificidad local, se marco `NO EVIDENCIA LOCAL` y se complemento con fuentes primarias (no blogs).

## Auditoria integral de pe a pa (bots/conexion/lag/seguridad/apis) - 2026-03-04

- Se ejecuto auditoria transversal completa de backend + frontend + research + risk + ops + QA + UX + cerebro del bot.
- Entregables creados:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Estado ejecutivo actualizado:
  - LIVE: **NO GO** (bloqueante principal: runtime de ejecucion real todavia no completo end-to-end).
  - No-live/testnet: **GO** con controles actuales, manteniendo politica de no conectar LIVE hasta cierre total.
- Hallazgos principales confirmados:
  - `CRITICAL`: runtime de fills/order loop sigue parcialmente simulado para `testnet/live` en `RuntimeBridge`.
  - `HIGH`: fallback mock en BFF por ausencia de `BACKEND_API_URL`; uso de `--password` en scripts/workflows.
  - `HIGH`: divergencia entre estrategias declaradas y comportamiento ejecutado por dispatcher/familia.
  - `HIGH`: latencia `/api/v1/bots` no estable en todas las corridas productivas.
  - `HIGH`: divergencia de thresholds de gates entre `config/policies` y `knowledge/policies`.
- Evidencia de validacion corrida 2026-03-04:
  - `./scripts/security_scan.ps1 -Strict` -> PASS.
  - `python -m pytest -q rtlab_autotrader/tests` -> PASS.
  - `npm test -- --run` -> PASS (11 tests).
  - `npm run lint` -> PASS.
  - `npm run build` -> PASS (warnings Recharts pendientes).

## Hotfix tecnico AP-7003 (G9 mode-binding + gate read-only) - 2026-03-04

- Ajuste puntual en `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeSnapshot` reemplaza `exchange_mode_known` por `exchange_mode_match` (exige coincidencia estricta entre `runtime_exchange_mode` y `mode` objetivo).
  - `evaluate_gates(...)` deja de persistir/sincronizar estado runtime cuando no recibe `runtime_state`; ahora evalua en modo solo lectura sobre snapshot persistido.
- Cobertura de regresion en `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode`;
  - nuevo `test_evaluate_gates_does_not_persist_runtime_state_side_effects`;
  - ajuste de fixtures G9 para modo `live` real en tests de PASS.
- Evidencia de validacion:
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_passes_only_when_runtime_contract_is_fully_ready rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers rtlab_autotrader/tests/test_web_live_ready.py::test_evaluate_gates_does_not_persist_runtime_state_side_effects rtlab_autotrader/tests/test_web_live_ready.py::test_live_mode_blocked_when_runtime_engine_is_simulated` -> PASS (5).
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py -k "g9 or runtime_contract_snapshot_defaults_are_exposed_in_status or live_blocked_by_gates_when_requirements_fail or storage_gate_blocks_live_when_user_data_is_ephemeral"` -> PASS (7).
- Estado hallazgo:
  - `FM-EXEC-002`: CERRADO y revalidado con test de mismatch de modo runtime.

## Actualizacion tecnica Fase 2 (AP-7001/AP-7002) - 2026-03-04

- Runtime operativo reforzado en `rtlab_autotrader/rtlab_core/web/app.py`:
  - `evaluate_gates(...)` ahora usa estado runtime sincronizado cuando no recibe `runtime_state` (evita PASS de `G9` por snapshot viejo/manualmente inyectado).
  - `RuntimeSnapshot` incorpora checks de evidencia externa:
    - `exchange_connector_ok`
    - `exchange_order_ok`
    - `exchange_check_fresh`
    - `exchange_mode_known`
  - `sync_runtime_state` fail-closed:
    - si `runtime_engine=real` pero `diagnose_exchange` no da `connector_ok && order_ok`, se fuerza `telemetry_source=synthetic_v1`;
    - se exponen campos runtime nuevos (`runtime_exchange_*`) para trazabilidad.
  - reconciliacion no-paper usa `GET /api/v3/openOrders` firmado (Binance) y marca `source/source_ok/source_reason`.
- Riesgo operativo alineado a policy canonica:
  - se carga `config/policies/risk_policy.yaml` en runtime (`_load_runtime_risk_policy_thresholds`).
  - limites efectivos del `RiskEngine` toman el minimo entre settings y policy (soft/hard).
  - hard-kill por policy (`daily_loss` / `drawdown`) aplicado en runtime loop.
- Learning default sin hardcode ciego de perfil:
  - `rtlab_autotrader/rtlab_core/learning/service.py` ahora deriva `learning.risk_profile` por defecto desde `config/policies/risk_policy.yaml` (fallback seguro a `MEDIUM_RISK_PROFILE`).
- Cobertura de tests agregada/ajustada:
  - `rtlab_autotrader/tests/test_web_live_ready.py`:
    - `_mock_exchange_ok` ahora cubre `/api/v3/openOrders`;
    - `test_learning_default_risk_profile_prefers_policy_yaml` (nuevo);
    - ajustes en tests de `G9`/runtime real para contrato actualizado.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.
- Estado de hallazgos tras esta fase:
  - `FM-EXEC-002`: CERRADO (G9 ya no depende solo de estado/env stale).
  - `FM-RISK-003`: CERRADO (risk profile default ahora policy-driven).
  - `FM-EXEC-001`, `FM-EXEC-005`, `FM-RISK-002`: MITIGADOS (mejor wiring/runtime+policy; queda deuda para loop broker real full de ordenes/fills).
  - `FM-QUANT-008`: ABIERTO (sin pipeline ML productivo `fit/predict`).

## Actualizacion tecnica Bloque 1 (AP-1001/AP-1002/AP-1003) - 2026-03-04

- Backend runtime web ahora cableado internamente a:
  - `OMS`
  - `Reconciliation`
  - `RiskEngine`
  - `KillSwitch`
  (implementado en `rtlab_autotrader/rtlab_core/web/app.py` via `RuntimeBridge`).
- Endpoints operativos actualizados para usar snapshots runtime:
  - `/api/v1/status`
  - `/api/v1/execution/metrics`
  - `/api/v1/risk`
  - `/api/v1/health`
- Transiciones de control ahora sincronizan contrato runtime en cada evento:
  - `bot/mode`, `bot/start`, `bot/stop`, `bot/killswitch`, `control/pause`, `control/safe-mode`.
- Evidencia de validacion en esta corrida:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or health_reports_storage_persistence_status or storage_gate_blocks_live_when_user_data_is_ephemeral or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `8 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.
- Estado actual:
  - no-live/testnet queda mas robusto (sin payloads hardcodeados en esos endpoints);
  - LIVE real sigue bloqueado hasta acoplar broker/exchange real y cerrar gates de runtime estrictos.

## Actualizacion tecnica AP-1004 (telemetry fail-closed) - 2026-03-04

- Guard de telemetria runtime expuesto de forma canonica en:
  - `status`
  - `execution_metrics`
  - `risk`
  - `health`
- Campos operativos:
  - `runtime_telemetry_source`
  - `runtime_telemetry_ok`
  - `runtime_telemetry_fail_closed`
  - `runtime_telemetry_reason`
- En modo sintetico (`telemetry_source=synthetic_v1`) el backend aplica fail-closed en metricas de ejecucion para evitar falso positivo operativo:
  - `fill_ratio=0`
  - `maker_ratio=0`
  - latencia elevada (`latency_ms_p95>=999`)
  - errores/rate-limit minimos forzados para no promover estados no reales.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `6 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.

## Actualizacion tecnica AP-2001/AP-2002/AP-2003 - 2026-03-04

- AP-2001:
  - G9 ya depende de runtime contract con heartbeat/reconciliacion frescos.
  - evidencia adicional: test `test_g9_live_fails_when_runtime_heartbeat_is_stale`.
- AP-2002:
  - `GET /api/v1/diagnostics/breaker-events` incorpora `strict=true|false`.
  - en `strict=true`, `NO_DATA` ahora es fail-closed (`ok=false`) para impedir falsos PASS operativos.
  - en `strict=false`, se mantiene compatibilidad operativa (`NO_DATA` no rompe el check suave).
  - el reporte protegido (`scripts/ops_protected_checks_report.py`) ahora propaga `strict` al endpoint y publica `breaker_strict_mode`.
- AP-2003:
  - `POST /api/v1/rollout/evaluate-phase` ahora bloquea fail-closed cuando `runtime_telemetry_guard.ok=false` (telemetria sintetica).
  - el bloqueo deja trazabilidad en logs con evento `rollout_phase_eval_blocked`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_heartbeat_is_stale or runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `7 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint_pass or breaker_events_integrity_endpoint_no_data_non_strict_ok or breaker_events_integrity_endpoint_no_data_strict_fail_closed or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

## Actualizacion tecnica AP-3001 (Purged CV + embargo real) - 2026-03-04

- `BacktestEngine` ahora implementa `validation_mode=purged-cv` con ventana OOS real separada por `purge_bars` + `embargo_bars`:
  - aplica split IS/OOS, limita `purge/embargo` para preservar minimos (`train>=250`, `oos>=250`) y devuelve `validation_summary` trazable;
  - configuracion de `purge_bars/embargo_bars` queda reutilizable para CPCV (cerrado en AP-3002).
- `POST /api/v1/backtests/run` acepta opcionales `purge_bars` y `embargo_bars` (enteros `>=0`) y los propaga a engine + metadata/provenance.
- Learning rapido:
  - `_learning_eval_candidate` ahora toma `validation_mode` desde `settings.learning.validation`:
    - `validation_mode` explicito si existe (`walk-forward|purged-cv|cpcv`);
    - fallback: `walk-forward` si `walk_forward=true`, `purged-cv` si `walk_forward=false`.
  - `learning/service.py` deja de reportar `purged_cv` como `hook_only` y lo marca `implemented=true`.
- Cobertura de tests:
  - `test_backtests_run_supports_purged_cv_and_cpcv`.
  - `test_learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled`.
  - `test_learning_research_loop_and_adopt_option_b` verifica `purged_cv.implemented=true` y `cpcv.implemented=true`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_research_loop_and_adopt_option_b" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

## Actualizacion tecnica AP-3002 (CPCV real en learning/research rapido) - 2026-03-04

- `BacktestEngine` incorpora `validation_mode=cpcv` ejecutable:
  - genera paths combinatoriales (`n_splits`, `k_test_groups`, `max_paths`) con trimming por `purge_bars + embargo_bars`;
  - evalua cada path con `StrategyRunner` y consolida `equity/trades/costos` + `validation_summary` con `paths_evaluated`.
- `POST /api/v1/backtests/run` acepta parametros opcionales de CPCV:
  - `cpcv_n_splits` (`>=4`)
  - `cpcv_k_test_groups` (`>=1`)
  - `cpcv_max_paths` (`>=1`)
  y los persiste en metadata/provenance/params_json.
- Learning rapido:
  - `_learning_eval_candidate` propaga `cpcv_*` desde `settings.learning.validation` hacia `BacktestRequest`.
  - `learning/service.py` ahora reporta `validation.cpcv.implemented=true` (`enforce` respetando `enforce_cpcv`).
- Cobertura de tests:
  - `test_backtests_run_supports_purged_cv_and_cpcv`.
  - `test_learning_eval_candidate_supports_cpcv_mode_from_settings`.
  - `test_learning_research_loop_and_adopt_option_b` valida `cpcv.implemented=true`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_eval_candidate_supports_cpcv_mode_from_settings or learning_research_loop_and_adopt_option_b" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_rejects_synthetic_source or event_backtest_engine_runs_for_crypto_forex_equities or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

## Actualizacion tecnica AP-3003 (learning fail-closed sin fallback silencioso) - 2026-03-04

- `_learning_eval_candidate` ahora falla explicito cuando no hay dataset real:
  - si `DataLoader.load_resampled(...)` falla, levanta `ValueError` con contexto (`market/symbol/timeframe/period`);
  - si `dataset_source` resulta sintetico o vacio, levanta `ValueError` fail-closed.
- Se elimino el fallback silencioso a `runs_cache_fallback`/metricas dummy para evitar ocultar errores de datos.
- Cobertura de test actualizada:
  - `test_learning_research_loop_and_adopt_option_b` ahora usa stub explicito de evaluator (sin depender de fallback implicito).
  - nuevo `test_learning_run_now_fails_closed_when_real_dataset_missing` valida `400` + mensaje `fail-closed`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "learning_research_loop_and_adopt_option_b or learning_run_now_fails_closed_when_real_dataset_missing" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

## Actualizacion tecnica AP-3004 (separacion anti_proxy vs anti_advanced) - 2026-03-04

- `MassBacktestEngine` ahora expone explicitamente dos capas anti-overfitting en resultados de research:
  - `anti_proxy`: salida base del proxy rapido por folds.
  - `anti_advanced`: salida de gates avanzados (`pbo_cscv`, `dsr_deflated`, walk-forward/cost-stress/trade-quality/surrogate).
- Compatibilidad:
  - `anti_overfitting` se mantiene como alias legacy de `anti_advanced` para no romper consumidores existentes.
- Persistencia/catalogo:
  - `kpi_summary_json` y `artifacts_json` de batch child ahora prefieren `anti_advanced` y conservan `anti_proxy` en artefactos.
- Cobertura de tests:
  - `test_run_job_persists_results_and_duckdb_smoke_fallback` valida presencia/semantica de `anti_proxy` y `anti_advanced`.
  - nuevo `test_advanced_gates_exposes_anti_proxy_and_anti_advanced_separately`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`.

## Actualizacion tecnica AP-3005 (CompareEngine fail-closed con feature_set unknown) - 2026-03-04

- `rtlab_core/rollout/compare.py` ahora aplica fail-closed cuando baseline/candidato no declaran `orderflow_feature_set` de forma explicita:
  - `_extract_orderflow_feature_set` deja de asumir `orderflow_on` por compatibilidad historica y retorna `orderflow_unknown` cuando falta evidencia.
  - nuevo check `known_feature_set` en `CompareEngine.compare(...)`.
- `same_feature_set` se mantiene, pero ya no alcanza por si solo cuando ambos lados quedan `unknown`.
- Tests:
  - `test_compare_engine_improvement_rules` agrega caso `unknown` y exige fail por `known_feature_set`.
  - `_sample_run` en tests de rollout ahora declara `orderflow_feature_set=orderflow_on` explicito.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

## Actualizacion tecnica AP-3006 (strict_strategy_id obligatorio en research/promotion no-demo) - 2026-03-04

- Research masivo/beast ahora fuerza `strict_strategy_id=true` en folds no-demo:
  - `_mass_backtest_eval_fold` calcula `strict_strategy_id = (execution_mode != "demo")` y lo propaga a `create_event_backtest_run`.
  - endpoints `mass-backtest/start`, `batches`, `beast/start` fijan `execution_mode` en config para trazabilidad.
- Promotion/recommendation desde research:
  - `POST /api/v1/research/mass-backtest/mark-candidate` bloquea fail-closed si `strict_strategy_id` no esta en `true` para modo no-demo.
- Promotion de runs:
  - `_validate_run_for_promotion` incorpora check `strict_strategy_id_non_demo` en constraints (fuentes: report/provenance/metadata/params/catalog).
  - reportes reconstruidos desde catalogo preservan `strict_strategy_id` y `execution_mode` cuando existen en `params_json`.
- Motor de research:
  - `MassBacktestEngine` publica `strict_strategy_id` en `summary/result row` y lo persiste en `params_json/artifacts_json` del catalogo.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

## Actualizacion tecnica AP-4001 (security CI root) - 2026-03-04

- Workflow de seguridad root versionado en rama tecnica:
  - `/.github/workflows/security-ci.yml` (commit `0dbf55d`).
- Job `security` definido para `push`, `pull_request` y `workflow_dispatch`:
  - instala `pip-audit` + `gitleaks`;
  - ejecuta `scripts/security_scan.sh` en modo estricto;
  - publica artifacts `artifacts/security_audit/`.
- Validacion local de workflow:
  - parse YAML via `python + yaml.safe_load` -> `OK_WORKFLOW`.
- Evidencia de corrida remota inicial:
  - workflow run `22674323602` (`push`, branch `feature/runtime-contract-v1`) en `failure`;
  - falla en job `security` paso `Install security tooling` (instalacion de `gitleaks` en path con permisos).
- Fix incremental aplicado:
  - `security-ci.yml` instala `gitleaks` en `"$RUNNER_TEMP/bin"` y agrega ese path a `GITHUB_PATH` (sin requerir root).
- Pendiente operativo:
  - rerun/corrida verde de `Security CI` post-fix.

## Actualizacion tecnica AP-4002 (branch protection required check security) - 2026-03-04

- Branch protection aplicada en `main` via GitHub API:
  - `required_status_checks.strict=true`
  - `required_status_checks.contexts=["security"]`
- Evidencia de aplicacion/verificacion (API):
  - `PROTECTION_SET_OK contexts=security`
  - `PROTECTION_VERIFY strict=True contexts=security enforce_admins=False`
- Efecto operativo:
  - merge a `main` queda bloqueado si no pasa el check `security`.
- Pendiente:
  - completar primera corrida verde de `Security CI` despues del fix AP-4001.

## Actualizacion tecnica AP-4003 (login lockout/rate-limit backend compartido) - 2026-03-04

- `LoginRateLimiter` ahora soporta backend configurable:
  - `memory` (compatibilidad local).
  - `sqlite` (compartido multi-instancia sobre storage persistente).
- Implementacion aplicada en `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevos envs:
    - `RATE_LIMIT_LOGIN_BACKEND` (`sqlite` por default).
    - `RATE_LIMIT_LOGIN_SQLITE_PATH` (override opcional de ruta sqlite).
  - persistencia de estado de login en tabla `auth_login_rate_limit` (`limiter_key`, `failures_json`, `lock_until`, `updated_at`).
  - fallback seguro: backend invalido vuelve a `memory`.
- Cobertura de tests:
  - `rtlab_autotrader/tests/test_web_live_ready.py`:
    - `test_auth_login_rate_limit_and_lock_guard` (explicitamente en `backend="memory"`).
    - `test_auth_login_rate_limit_shared_sqlite_backend_across_instances` (nuevo, valida rate-limit/lockout/reset cross-instancia).
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_and_lock_guard or auth_login_rate_limit_shared_sqlite_backend_across_instances" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_and_admin_protection or api_general_rate_limit_guard or api_expensive_rate_limit_guard" -q` -> `3 passed`.

## Actualizacion tecnica AP-5001 (suite E2E critica backend) - 2026-03-04

- Cobertura E2E integral agregada en `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_e2e_critical_flow_login_backtest_validate_promote_rollout`.
- Flujo validado end-to-end:
  - `login`
  - `POST /api/v1/backtests/run` (baseline + candidate)
  - `POST /api/v1/runs/{id}/validate_promotion`
  - `POST /api/v1/runs/{id}/promote`
  - `POST /api/v1/rollout/advance`
- Ajuste de test helper:
  - `_force_runs_rollout_ready` normaliza metadatos/metrics/costos para mantener determinismo de gates/compare en entorno de test.
- Validacion:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "e2e_critical_flow_login_backtest_validate_promote_rollout or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

## Actualizacion tecnica AP-5002 (chaos/recovery runtime) - 2026-03-04

- Cobertura de caos/recovery agregada en `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo helper `_mock_exchange_down`.
  - nuevo `test_exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect`.
  - nuevo `test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers`.
- Escenarios cubiertos:
  - exchange/testnet no disponible (connector+order FAIL) y recuperacion por reconnect (PASS).
  - desincronizacion de reconciliacion runtime (`runtime_last_reconcile_at` stale) con fail de `G9` y recuperacion tras refrescar reconcile timestamp.
- Validacion:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers or g9_live_fails_when_runtime_heartbeat_is_stale or exchange_diagnose_passes_with_env_keys_and_mocked_exchange" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_shared_sqlite_backend_across_instances or e2e_critical_flow_login_backtest_validate_promote_rollout or exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `4 passed`.

## Actualizacion tecnica AP-5003 (alertas operativas minimas) - 2026-03-04

- Backend `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo `build_operational_alerts_payload`.
  - `GET /api/v1/alerts` ahora soporta `include_operational=true|false` y agrega alertas derivadas:
    - `ops_drift`
    - `ops_slippage_anomaly`
    - `ops_api_errors`
    - `ops_breaker_integrity`
  - umbrales configurables por ENV:
    - `OPS_ALERT_SLIPPAGE_P95_WARN_BPS`
    - `OPS_ALERT_API_ERRORS_WARN`
    - `OPS_ALERT_BREAKER_WINDOW_HOURS`
    - `OPS_ALERT_DRIFT_ENABLED`
- Cobertura de tests:
  - `test_alerts_include_operational_alerts_for_drift_slippage_api_and_breaker`.
  - `test_alerts_operational_alerts_clear_when_runtime_recovers`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `2 passed`.

## Actualizacion tecnica AP-6001 (decision final por hallazgo) - 2026-03-04

- Se versiona matriz final de decisiones:
  - `docs/audit/FINDINGS_DECISION_MATRIX_20260304.md`.
- Estado consolidado del tramo (sobre `docs/audit/FINDINGS_MASTER_20260304.md`):
  - `CERRADO`: `12`
  - `MITIGADO`: `8`
  - `ABIERTO`: `6`
- Hallazgos abiertos al cierre de este plan:
  - `FM-EXEC-001`, `FM-EXEC-002`, `FM-EXEC-005`, `FM-QUANT-008`, `FM-RISK-002`, `FM-RISK-003`.

## Actualizacion tecnica AP-6002 (politica formal bibliografia local) - 2026-03-04

- Se crea politica formal:
  - `docs/reference/BIBLIO_ACCESS_POLICY.md`.
- Politica aplicada:
  - `biblio_raw` y `biblio_txt` se mantienen no versionados por licencia/volumen;
  - `docs/reference/BIBLIO_INDEX.md` queda como fuente versionada de metadatos y hashes SHA256;
  - regeneracion estandarizada con `python scripts/biblio_extract.py`.

## Cierre PARTE 7/7 (Cerebro del bot) - 2026-03-04

- Auditoria del cerebro de decision/aprendizaje cerrada con evidencia en:
  - `rtlab_autotrader/rtlab_core/learning/brain.py`
  - `rtlab_autotrader/rtlab_core/learning/service.py`
  - `rtlab_autotrader/rtlab_core/src/backtest/engine.py`
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
  - `rtlab_autotrader/rtlab_core/rollout/manager.py`
  - `rtlab_autotrader/rtlab_core/rollout/compare.py`
  - `rtlab_autotrader/rtlab_core/rollout/gates.py`
  - `rtlab_autotrader/rtlab_core/web/app.py`
- Resultado tecnico:
  - selector/ranking/anti-overfitting/rollout estan implementados;
  - Opcion B se mantiene fail-closed (`allow_auto_apply=false`, `allow_live=false`);
  - `purged_cv` y `cpcv` ya implementados en quick backtest/learning rapido (con `purge/embargo` y paths combinatoriales);
  - runtime web operativo ya migro a `RuntimeBridge` para status/ejecucion/risk en no-live, pero sigue sin broker real para LIVE.
- Trazabilidad de cierre y plan:
  - `docs/audit/FINDINGS_MASTER_20260304.md`
  - `docs/audit/ACTION_PLAN_FINAL_20260304.md`
- Avance Bloque 0 (AP-0001/AP-0002) en curso:
  - contrato runtime `RuntimeSnapshot v1` y criterio exacto de `G9` definidos y versionados en `docs/audit/AP0001_AP0002_RUNTIME_CONTRACT_V1.md`;
  - backend ya publica metadata de contrato runtime en `health/status/execution_metrics`;
  - el runtime real end-to-end sigue pendiente (Bloque 1), por lo que `G9` permanece bloqueante para LIVE real.
- Decision operativa reafirmada: se cierra no-live/testnet primero y LIVE real queda para el final, luego de completar runtime real + CI security root + hardening final.

## Actualizacion auditoria integral (2026-03-04)

- Auditoria integral ejecutada sobre backend, frontend, research/backtests, risk, ejecucion, ops/SRE y QA.
- Decision de comite (estado actual): **NO LISTO para LIVE**.
- Bloqueantes confirmados por evidencia de codigo:
  - Runtime LIVE aun no acoplado a broker/exchange real end-to-end (el wiring actual es no-live interno); `G9` sigue bloqueante para LIVE.
  - `G9` todavia requiere cerrar evidencias estrictas de loop/heartbeat/reconciliacion sobre runtime de mercado real.
  - `breaker_events` solo queda fail-closed con `strict=true`; en `strict=false` sigue aceptando `NO_DATA` por compatibilidad.
  - `security-ci` root ya versionado + branch protection aplicada; resta corrida verde inicial post-fix de instalacion de `gitleaks`.
- Evidencia de validacion ejecutada en esta auditoria:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict` -> PASS (`pip-audit` runtime/research sin vulns conocidas, `gitleaks` sin leaks).
  - `python -m pytest rtlab_autotrader/tests --collect-only` -> `126 tests collected`.
  - `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - `npm --prefix rtlab_dashboard run lint` -> PASS.
- Bibliografia local:
  - `docs/reference/BIBLIO_INDEX.md` existe.
  - `docs/reference/biblio_raw/` no versiona PDFs por politica (`docs/reference/BIBLIO_ACCESS_POLICY.md`); reproducibilidad se mantiene via `BIBLIO_INDEX.md` + SHA256.
- Decision operativa vigente (confirmada): cierre no-live/testnet primero; LIVE real postergado hasta completar runtime real + evidencias.

## Actualizacion operativa (2026-03-05)

- Re-run remoto de `Remote Protected Checks (GitHub VM)` con defaults y `strict=true`:
  - run: `22704105623` (`success`).
  - evidencias extraidas de log GHA del run:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN` (esperado en no-live)
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
- Estado no-live:
  - checks protegidos remotos en PASS.
  - LIVE real sigue bloqueado por decision operativa hasta cierre final de runtime real + activacion APIs live.

## Actualizacion operativa benchmark (2026-03-05)

- Workflow remoto `Remote Bots Benchmark (GitHub VM)` con defaults:
  - run: `22706414197` (`success`).
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_GHA_22706414197_20260305.md`.
- Resultado canonico:
  - `p50_ms=106.54`
  - `p95_ms=184.546`
  - `p99_ms=351.142`
  - `server_p95_ms=0.07`
  - `rate_limit_retries=0`
  - `cache_hit_ratio=1.0` (`20/20` hits)
  - estado objetivo `p95<300ms`: `PASS`
- Hardening CI menor:
  - `/.github/workflows/remote-benchmark.yml` corrige quoting en `Build summary` (`grep -E` con comillas simples) para evitar errores de shell por backticks en la regex.

## Actualizacion operativa protected checks (2026-03-05, post AP-BOT-1020)

- Workflow remoto `Remote Protected Checks (GitHub VM)` con defaults y `strict=true`:
  - run: `22731722376` (`success`).
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.
- Resultado canonico:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- Estado:
  - no-live/testnet se mantiene en verde tras AP-BOT-1020;
  - LIVE sigue bloqueado por decision operativa hasta cierre final de runtime real + activacion APIs live.

## Actualizacion operativa de cierre no-live (2026-03-05)

- Checklist refresh:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md` actualizado con evidencia de runs:
    - benchmark `22706414197` (PASS),
    - protected checks `22731722376` (PASS).
- Estado consolidado:
  - tramo no-live/testnet: `GO` (actualizado con evidencia 2026-03-05),
  - LIVE: `NO GO` (postergado por decision operativa hasta fase final de APIs/canary/rollback).

## Actualizacion operativa (2026-03-03)

- Workflow remoto `Remote Protected Checks (GitHub VM)` ejecutado con defaults (`strict=true`):
  - run: `22648114549` (`success`).
  - evidencia GHA (artifact `protected-checks-22648114549`):
    - `ops_protected_checks_gha_22648114549_20260303_234740.json`
    - `ops_protected_checks_gha_22648114549_20260303_234740.md`
- Resultado checks protegidos (sin inferencias):
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true` (`breaker_status=NO_DATA`)
  - `internal_proxy_status_ok=true`
- Revalidacion de seguridad ejecutada (equivalente CI, Windows local):
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
  - resultado: `pip-audit` runtime/research sin vulnerabilidades conocidas + `gitleaks` baseline-aware sin leaks.
  - nota de CI: en GitHub Actions del repo root solo figuran workflows activos de benchmark/checks remotos; la verificacion de seguridad de este cierre queda documentada por la corrida estricta local.
  - avance adicional: workflow root `/.github/workflows/security-ci.yml` versionado en rama tecnica (commit `0dbf55d`) para security CI bloqueante.
  - pendiente operativo: push remoto + primera corrida verde en GitHub Actions + branch protection con required check `security`.
- Estado de cierre no-live del tramo:
  - benchmark remoto GitHub VM: PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin retries `429`).
  - checks protegidos remotos: PASS.
  - LIVE real se mantiene bloqueado hasta `G9_RUNTIME_ENGINE_REAL=PASS`.
  - decision operativa vigente: priorizar cierre testnet/no-live; LIVE se retoma al final con APIs definitivas.

## Actualizacion operativa (2026-03-02)

- Persistencia Railway validada en produccion:
  - `/api/v1/health` => `storage.persistent_storage=true`.
  - `/api/v1/gates` => `G10_STORAGE_PERSISTENCE=PASS`.
  - `user_data_dir` activo sobre volumen persistente (`/app/data/rtlab_user_data`).
- Gates testnet:
  - `G1..G8` en `PASS`.
  - `G9_RUNTIME_ENGINE_REAL` en `WARN` (runtime simulado; esperado en testnet).
- Soak tests locales operativos (pendientes de commit):
  - `scripts/soak_testnet.ps1` (parse fix + password por ENV/prompt).
  - `scripts/start_soak_20m_background.ps1` (launcher robusto en segundo plano).
  - `scripts/start_soak_1h_background.ps1` (launcher 1h en segundo plano para cierre operativo abreviado).
  - `scripts/start_soak_6h_background.ps1` (launcher robusto en segundo plano).
  - `scripts/resume_soak_6h_background.ps1` (reanuda automaticamente desde `status` si se corta proceso/sesion).
  - `scripts/build_ops_snapshot.py` (snapshot operativo y cierre provisional/final de bloque).
  - `scripts/run_protected_ops_checks.ps1` (chequeos protegidos en 1 comando, pidiendo password una sola vez).
  - `scripts/backup_restore_drill.py` (drill automatizado backup+restore con verificacion por hash).
  - `scripts/security_scan.ps1` (equivalente Windows del job security CI: pip-audit + gitleaks baseline-aware).
  - `scripts/run_bots_benchmark_remote.ps1` (launcher PowerShell para benchmark remoto estricto de `/api/v1/bots`).
  - `scripts/run_remote_closeout_bundle.ps1` (bundle remoto en 1 comando: storage+gates protegidos+snapshot+benchmark).
  - Soak `20m` completado: `ok=80`, `errors=0`, `g10_pass=80`.
  - Soak `1h` completado: `loops=240`, `ok=240`, `errors=0`, `g10_pass=240`.
  - Soak `6h` completado: `loops=1440`, `ok=1440`, `errors=0`, `g10_pass=1440`.
  - Cierre de tramo aceptado con criterio operativo `20m + 1h` valedero (soak `6h` queda opcional/no bloqueante para este tramo).
  - Snapshot final (sin supuestos) generado tras cierre real de `6h`:
    - `artifacts/ops_block2_snapshot_20260302_231911.json`
    - `artifacts/ops_block2_snapshot_20260302_231911.md`
  - `build_ops_snapshot.py` reforzado para cierre estricto:
    - `--ask-password` para pedir `ADMIN_PASSWORD` por consola cuando falta token,
    - `--require-protected` para exigir validacion de `/api/v1/gates`, `/api/v1/diagnostics/breaker-events` y `/api/v1/auth/internal-proxy/status`.
  - Backup/restore drill ejecutado localmente con evidencia:
    - `python scripts/backup_restore_drill.py`
    - `artifacts/backup_restore_drill_20260302_234205.json` (`backup_ok=true`, `restore_ok=true`, `manifest_match=true`).
  - Preflight de seguridad local (Windows) ejecutado en modo estricto:
    - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
    - resultado: `pip-audit` runtime/research sin vulnerabilidades conocidas + `gitleaks` baseline-aware sin leaks.
    - evidencia actualizada en `artifacts/security_audit/`:
      - `pip-audit-runtime.json`
      - `pip-audit-research.json`
      - `gitleaks.sarif`
  - Benchmark local `/api/v1/bots` re-ejecutado (regresión):
    - `python scripts/benchmark_bots_overview.py --bots 100 --requests 200 --warmup 30 --report-path docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260302_RERUN.md`
    - resultado: `p95=55.513ms` (PASS `<300ms`), `100` bots observados.
  - `benchmark_bots_overview.py` reforzado para operación remota:
    - `--ask-password` (prompt de `ADMIN_PASSWORD`),
    - `--require-evidence` (exit `2` si queda `NO_EVIDENCIA`),
    - `--require-target-pass` (exit `3` si no cumple objetivo p95).
  - Bundle operativo para cierre remoto con password una sola vez:
    - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_remote_closeout_bundle.ps1`
- Backtest por `strategy_id` (adelanto de bloque):
  - `BacktestEngine` agrega modo estricto opt-in (`strict_strategy_id=true`) con fail-closed para familias no soportadas.
  - comportamiento legacy se mantiene por defecto (`strict_strategy_id=false`): fallback conservador a `trend_pullback`.
  - endpoint `POST /api/v1/backtests/run` ya propaga `strict_strategy_id` hacia engine y metadata/provenance.
- Observabilidad adicional `/api/v1/bots` (adelanto de bloque performance):
  - `debug_perf=true` ahora incluye desglose interno de `overview` por etapas (`inputs/context/runs_index/kpis/db_reads/db_process/assemble/total`).
  - la cache de overview conserva y devuelve ese perf interno en `hit`, facilitando comparativas `miss` vs `hit`.
  - slow-log `bots_overview_slow` ahora adjunta `overview_perf` para aislar cuellos de botella.
  - optimizacion incremental aplicada: KPIs del overview se calculan solo para estrategias en pools de bots (`strategies_in_pool_count`), evitando trabajo sobre estrategias no asignadas.
  - optimizacion incremental aplicada en logs:
    - `logs.has_bot_ref` materializado + indice `idx_logs_has_bot_ref_id`,
    - prefiltrado SQL `has_bot_ref=1` para `recent_logs` en overview,
    - backfill reciente configurable por `BOTS_LOGS_REF_BACKFILL_MAX_ROWS`.
  - optimizacion incremental aplicada (fase siguiente):
    - tabla materializada `log_bot_refs(log_id, bot_id)` + indice por bot,
    - routing de logs recientes por join `log_bot_refs -> logs` en vez de escanear lote global,
    - fallback automatico para DB legacy y observabilidad con `logs_prefilter_mode`.
- Integridad de `breaker_events` (adelanto de bloque):
  - nuevo endpoint autenticado `GET /api/v1/diagnostics/breaker-events`.
  - expone estado `PASS/WARN/NO_DATA` y ratios de eventos `unknown_*` sobre total (global + ventana).
  - umbrales operativos configurables por ENV:
    - `BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS`
    - `BREAKER_EVENTS_UNKNOWN_RATIO_WARN`
    - `BREAKER_EVENTS_UNKNOWN_MIN_EVENTS`
- Seguridad auth interna (adelanto de bloque):
  - intentos de spoof con headers internos (`x-rtlab-role/x-rtlab-user`) sin `x-rtlab-proxy-token` valido ahora generan alerta en logs.
  - evidencia operativa via `security_auth` (`warn`, `module=auth`) con `reason`, `client_ip`, `path`, `method`.
  - throttle configurable por ENV `SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC` (default `60`).
- Rotacion token interno (adelanto de bloque):
  - backend soporta token activo + token previo con expiracion:
    - `INTERNAL_PROXY_TOKEN`,
    - `INTERNAL_PROXY_TOKEN_PREVIOUS`,
    - `INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT`.
  - token previo solo se acepta durante ventana de gracia; luego se rechaza con `reason=expired_previous_token`.
  - endpoint operativo `GET /api/v1/auth/internal-proxy/status` (admin) para validar readiness de rotacion.
- Validacion no-live (regresion amplia, 2026-03-02):
  - backend: `python -m pytest rtlab_autotrader/tests -q` -> `124 passed`.
  - frontend tests: `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - frontend lint: `npm --prefix rtlab_dashboard run lint` -> `0 errores, 0 warnings`.
- LIVE sigue bloqueado hasta runtime real (`G9` en `PASS`).

## Actualizacion auditoria comite (2026-02-28)

- Se generaron artefactos de auditoria completos en `docs/audit/`:
  - `AUDIT_REPORT_20260228.md`
  - `AUDIT_FINDINGS_20260228.md`
  - `AUDIT_BACKLOG_20260228.md`
- Seguridad endurecida adicional:
  - backend ahora rechaza headers internos (`x-rtlab-role/x-rtlab-user`) si falta `INTERNAL_PROXY_TOKEN` (fail-closed).
  - login backend con rate-limit + lockout (`10 intentos/10min`, lockout `30min` tras `20` fallos por `IP+user`).
  - BFF falla cerrado si falta `INTERNAL_PROXY_TOKEN`.
  - scanner de seguridad baseline-aware:
    - `scripts/security_scan.sh` usa `gitleaks git --baseline-path artifacts/security_audit/gitleaks-baseline.json` cuando existe baseline.
    - sin baseline, corre en modo estricto (`gitleaks git`).
  - CI bloqueante de seguridad:
    - `rtlab_autotrader/.github/workflows/ci.yml` agrega job `security` (pip-audit + gitleaks).
    - artefactos de auditoria en `artifacts/security_audit/*` se publican en cada corrida.
- Bibliografia:
  - nuevo extractor incremental `scripts/biblio_extract.py`.
  - `docs/reference/BIBLIO_INDEX.md` regenerado con SHA256 por fuente.
  - `docs/reference/biblio_txt/.gitignore` agregado para salida local de texto.
- Hallazgos abiertos bloqueantes para LIVE:
  - runtime real OMS/broker (hoy simulado).
- Estado `/api/v1/bots` (performance):
  - cache TTL in-memory activado en endpoint `GET /api/v1/bots` (`10s` default).
  - invalidacion explicita en create/patch/bulk de bots y en logs `breaker_triggered`.
  - limite de cardinalidad activa en backend: `BOTS_MAX_INSTANCES` (default `30`).
  - observabilidad por request activa en `/api/v1/bots`:
    - headers de cache/latencia/cantidad
    - `debug_perf=true` para inspeccion puntual.
  - switch de carga:
    - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS` permite apagar logs recientes por bot en overview para reducir costo en Railway.
  - benchmark local actualizado: `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260228_AFTER_CACHE.md` con `p95=35.524ms` (PASS `<300ms`).
  - benchmark remoto post-deploy:
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY.md` -> `p95=1032.039ms` (FAIL) + `NO EVIDENCIA` por cardinalidad (`1` bot).
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY_100BOTS.md` -> `p95=1458.513ms` con `100` bots (FAIL).
  - benchmark remoto A/B con telemetria server-side (30 bots):
    - `enabled`: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_ENABLED_30BOTS.md` -> `server_p95_ms=74.93`
    - `disabled`: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_DISABLED_30BOTS.md` -> `server_p95_ms=63.034`
    - decision: dejar `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false` en prod.
  - observacion de infraestructura:
    - redeploy por cambio de variables en Railway resetea estado runtime en este entorno (`RTLAB_USER_DATA_DIR=/tmp/...`), afectando cardinalidad de bots y repetibilidad de benchmark.
  - estado actual: objetivo `p95 < 300ms` en Railway sigue abierto; requiere optimizacion adicional.
- Estado backtest por strategy_id:
  - `StrategyRunner` ahora despacha senales por familia de estrategia (`trend`, `breakout`, `meanreversion`, `trend_scanning`, `defensive`).
  - el sesgo de logica unica en `BacktestEngine` quedo resuelto en modo incremental (sin refactor masivo).
- Estado gate de calidad por simbolo:
  - `MassBacktestEngine` ya aplica `min_trades_per_symbol` real en `min_trade_quality`.
  - cada variante publica `trade_count_by_symbol_oos` y `min_trades_per_symbol_oos` en `summary`.
  - UI `Backtests > Research Batch` ya expone esos campos en leaderboard y drilldown.
- Estado fuente canónica de gates:
  - learning/research/runtime consumen `config/policies/gates.yaml` como fuente primaria.
  - `knowledge/policies/gates.yaml` queda como fallback/soporte documental cuando falta config.
- Estado surrogate adjustments (research):
  - `enable_surrogate_adjustments` ya no se evalua directo desde request/config.
  - se resuelve por policy canónica (`gates.surrogate_adjustments`) con `allowed_execution_modes`.
  - default actual: solo `demo`, sin override por request y con bloqueo de promotion (`promotable=false`, `recommendable_option_b=false`).
  - trazabilidad visible en `summary/manifest/artifacts` bajo `surrogate_adjustments`.

## Estado actual (resumen ejecutivo)

El proyecto tiene:
- `Learning` Opcion B (recomienda, no auto-live)
- `Safe Update with Gates + Canary + Rollback`
- `Strategy Registry` persistente
- `Backtests & Research System` con runs/batches/catalogo/comparador/promocion controlada
- `Mass Backtests` (research offline) con ranking robusto
- UI `Research-first` con Backtests/Runs unificados y panel operativo de `Ejecucion`

## Cambios recientes (UI/UX Research-first)

- `Backtests / Runs` con paginacion, filtros, metadata minima visible y empty states guiados
- `Backtests / Runs` con orden por click en columnas clave (incluye `WinRate`) y sin recorte artificial de seleccion legacy
- Parser de errores de Backtests endurecido para evitar `[object Object]` en UI y mostrar `detail/message/cause` real
- `Research Batch` con shortlist persistente por `BX`:
  - guardado de variantes/runs en `best_runs_cache`
  - restauración de shortlist al reabrir batch
  - sincronización opcional con Comparador de Runs
- Backtests / Runs D2 (Comparison Table Pro) ahora renderiza por ventana visible (virtualizacion + overscan + espaciadores).
- Strategies compactado para escalar con 50+ filas (menos altura por fila y acciones principales mas compactas).
- `Detalle de Corrida` con estructura tipo Strategy Tester por pestanas
- `Quick Backtest Legacy` marcado como deprecado y colapsado
- `Settings` con diagnostico WS/SSE corregido (sin falso timeout)
- `Rollout / Gates` con empty states accionables
- `Ejecucion` convertida en `Trading en Vivo (Paper/Testnet/Live) + Diagnostico`
- `Ejecucion` reforzada (Bloque 4):
  - gestion de estrategias primarias por modo (`paper/testnet/live`) desde la misma pantalla
  - bloqueo explicito de cambio a `LIVE` si checklist critico no esta en PASS
  - atajos de seleccion masiva de operadores por estado/modo runtime
- `Portfolio`, `Riesgo`, `Operaciones` y `Alertas` con labels/empty states mas claros
- `Operaciones` reforzado (Bloque 3):
  - orden configurable de tabla
  - seleccion masiva + borrado por IDs
  - preview de borrado filtrado (`dry_run`)
  - filtros rapidos por modo/entorno/estrategia desde paneles resumen

## Bibliografia y trazabilidad externa

- Se agrego `docs/reference/BIBLIO_INDEX.md` con el listado consolidado de fuentes externas (1-20).
- Se agrego `docs/reference/biblio_raw/.gitignore` para permitir trabajo local con PDFs sin versionarlos.
- Politica vigente: bibliografia raw fuera de git; solo se versiona indice y metadatos de trazabilidad.

## Actualizacion 2026-02-28 (seguridad runtime + annualizacion + CI frontend)

- Auth interna backend endurecida:
  - `current_user` ahora acepta `x-rtlab-role/x-rtlab-user` solo si `x-rtlab-proxy-token` coincide con `INTERNAL_PROXY_TOKEN`.
  - sin token valido, los headers internos se ignoran y se requiere `Bearer` de sesion.
- BFF actualizado para proxy seguro:
  - `rtlab_dashboard/src/app/api/[...path]/route.ts` y `rtlab_dashboard/src/lib/events-stream.ts` ahora reenvian `x-rtlab-proxy-token` desde ENV.
- Credenciales por defecto en produccion:
  - fail-fast al boot si `NODE_ENV=production` y quedan credenciales default (`admin/admin123!`, `viewer/viewer123!`) o `AUTH_SECRET` debil.
  - `G2_AUTH_READY` ahora reporta `no_default_credentials` y falla si hay defaults.
- Runtime de ejecucion real:
  - estado del bot incorpora `runtime_engine` (`simulated|real`).
  - nuevo gate `G9_RUNTIME_ENGINE_REAL`.
  - `LIVE` queda bloqueado si runtime sigue simulado.
  - `status/health` exponen `runtime_engine/runtime_mode`.
- Backtest:
  - Sharpe/Sortino anualizados por timeframe real (`1m`, `5m`, `10m`, `15m`, `1h`, `1d` + parse generico `Nm/Nh/Nd`).
- CI:
  - workflow agrega job frontend (`npm ci`, `tsc --noEmit`, `vitest`, `next build`).

## Cambios recientes (RTLAB Strategy Console - Bloque 1)

- Nuevas policies numericas en `config/policies/` para:
  - gates (`PBO/CSCV`, `DSR`, `walk_forward`, `cost_stress`, calidad minima de trades)
  - microestructura L1 (`VPIN`, spread/slippage/vol guards)
  - risk policy con soft/hard kill por bot/estrategia/simbolo
  - beast mode (limites y budget governor)
  - fees/funding snapshots (TTL y fallback)
- Base de configuracion fija para pasar de defaults ambiguos a criterios auditables con numeros.

## Cambios recientes (RTLAB Strategy Console - Bloques 2-7)

- `config/policies/*` cargado desde backend via `GET /api/v1/config/policies`
- `GET /api/v1/config/learning` extendido con `numeric_policies_summary`
- `Research Batch` guarda `policy_snapshot` y `policy_snapshot_summary` por batch (audit trail)
- Cost model real baseline implementado:
  - `FeeProvider`, `FundingProvider`, `SpreadModel`, `SlippageModel`
  - snapshots persistentes en SQLite (`fee_snapshots`, `funding_snapshots`)
  - runs `BT-*` guardan `fee_snapshot_id`, `funding_snapshot_id`, `spread/slippage_model_params`
- Microestructura L1 (VPIN proxy desde OHLCV) integrada al motor masivo:
  - `VPIN`, `CDF(VPIN)`, spread/slippage/vol guards
  - flags `MICRO_SOFT_KILL` / `MICRO_HARD_KILL`
  - debug visible en drilldown de `Research Batch`
- Gates avanzados en research masivo:
  - `PBO/CSCV`, `DSR`, `walk-forward`, `cost stress`, `min_trade_quality`
  - PASS/FAIL por variante visible en leaderboards
  - `mark-candidate` fail-closed si no pasa gates
- Modo Bestia (fase 1, scheduler local):
  - endpoints `/api/v1/research/beast/*`
  - cola de jobs + budget governor + concurrencia
  - UI en `Backtests` con panel de estado/jobs/stop-all/resume
  - sin Celery/Redis todavia (pendiente fase 2)

## Cambios recientes (Calibracion real - fundamentals + costos)

- Nueva policy `config/policies/fundamentals_credit_filter.yaml`:
  - `enabled`, `fail_closed`, `apply_markets`, `freshness_max_days`
  - scoring y thresholds auditables
  - reglas por `common/preferred/bond/fund_bond`
  - snapshots con TTL
- Nuevo modulo `rtlab_core/fundamentals/credit_filter.py`:
  - calcula `fund_score`, `fund_status`, `allow_trade`, `risk_multiplier`, `explain[]`
  - aplica fail-closed cuando faltan datos y el mercado esta en scope
  - reutiliza snapshot vigente y persiste snapshot nuevo en DB
  - autoload opcional de snapshot local JSON para equities cuando source esta en `unknown/auto/local_snapshot`
  - traza de origen en `source_ref.source_path` + `DATA_SOURCE_LOCAL_SNAPSHOT`
  - soporte `remote_json` configurable por policy/env con `endpoint_template` y auth header por ENV
  - `source=auto` intenta remoto y luego fallback local (enforced/fail-closed se mantiene)
  - traza remota en `source_ref.source_url` + `DATA_SOURCE_REMOTE_SNAPSHOT|DATA_SOURCE_REMOTE_ERROR`
- Catalogo SQLite extendido:
  - nueva tabla `fundamentals_snapshots`
  - `backtest_runs` guarda `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`
- Wiring backend:
  - `app.py` y `mass_backtest_engine.py` ahora resuelven y guardan metadata fundamentals por run
  - ambos usan `source=auto` para habilitar remoto+fallback sin hardcode de proveedor
  - si `fundamentals_credit_filter` esta enforced y `allow_trade=false`, bloquea corrida (fail-closed)
- Cost model endurecido:
  - `FeeProvider` intenta endpoints reales Binance (`/api/v3/account/commission`, `/sapi/v1/asset/tradeFee`) y fallback seguro
  - `FeeProvider` soporta fallback por exchange (`per_exchange_defaults`) + override por ENV
  - `FundingProvider` intenta `/fapi/v1/fundingRate` (Binance) y `/v5/market/funding/history` (Bybit) para perps
  - `SpreadModel` agrega estimador `roll` cuando no hay BBO ni spread explicito
- Promotion/rollout endurecido (bloque 4/5):
  - `validate_promotion` agrega constraints fail-closed para corridas de catalogo:
    - `cost_snapshots_present`
    - `fundamentals_allow_trade`
  - `_build_rollout_report_from_catalog_row` ahora preserva trazabilidad de costos/fundamentals en el reporte de validacion y promocion.
- Admin multi-bot/live endurecido (bloque 5/5):
  - metricas de `BotInstance` ahora incluyen desglose por modo (`shadow/paper/testnet/live`) para `trades/winrate/net_pnl/sharpe/run_count`.
  - metricas de kills reales derivadas de logs (`breaker_triggered`) con `kills_total`, `kills_24h`, `kills_by_mode` y timestamp del ultimo kill.
  - transicion de bots a `mode=live` bloqueada por gates en backend (`create/patch/bulk-patch`) si LIVE no esta listo.
  - UI de `Ejecucion` bloquea el boton masivo `Modo LIVE` con motivo explicito cuando faltan checks.
- Gates default ajustado:
  - `dsr_min` default en rollout offline ahora `0.95`
- Tests ejecutados:
  - `test_backtest_catalog_db.py`
  - `test_fundamentals_credit_filter.py`
  - `test_cost_providers.py`
  - resultado: `11 passed`

## Actualizacion Opcion B + Opcion C (sin refactor masivo)

### Fundamentals gating por modo (policy explicita)

- Orden de severidad aplicado:
  - `UNKNOWN < WEAK < BASIC < STRONG`
- Reglas por modo:
  - `LIVE`: minimo `STRONG`, fail-closed si faltan requeridos (`allow_trade=false`)
  - `PAPER`: minimo `STRONG`, fail-closed si faltan requeridos (`allow_trade=false`)
  - `BACKTEST`: minimo `BASIC`; si faltan requeridos permite corrida con:
    - `fund_status=UNKNOWN`
    - `warnings` incluye `fundamentals_missing`
    - `promotion_blocked=true`
    - `fundamentals_quality=ohlc_only`
- Separacion Snapshot vs Decision:
  - `get_fundamentals_snapshot_cached(...)` cachea solo snapshot crudo
  - `evaluate_credit_policy(...)` calcula decision final por modo
  - `allow_trade` no se cachea
- Backtest equities sin snapshot fundamentals:
  - ya no aborta por defecto en BACKTEST
  - el run se crea con metadata/warnings y bloqueado para promocion
  - en PAPER/LIVE se mantiene fail-closed

### Bots overview performance (/api/v1/bots)

- Se elimino el patron N+1 por bot.
- Nuevo agregado batch en backend:
  - `ConsoleStore.get_bots_overview(...)`
- Carga en lote:
  - KPIs por modo y por pool de estrategias
  - logs recientes por bot (max 20 por bot; limite total 2000)
  - kills por bot y por modo
- Endpoint `GET /api/v1/bots` mantiene contrato actual y ahora consume overview batch interno.
- Benchmark reproducible local agregado:
  - script: `scripts/benchmark_bots_overview.py`
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_20260228.md`
  - resultado local (100 bots, 200 requests, warmup 30): `p95=280.875ms` (objetivo `<300ms` => PASS).
  - el mismo script ya soporta benchmark remoto (`--base-url`) con validacion minima opcional (`--min-bots-required`, default `0` = sin minimo).
- Benchmark remoto ejecutado (Railway):
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md`
  - resultado actual: `p95=1663.014ms` (FAIL vs `<300ms`)
  - `NO EVIDENCIA` de carga objetivo por cardinalidad: `/api/v1/bots` retorna `1` bot (se exigen `>=100` para este test).

### Breaker events schema (fuente canonica para kills)

- Tabla SQLite:
  - `breaker_events`
- Campos:
  - `bot_id` (obligatorio; faltante -> `unknown_bot`)
  - `mode` (obligatorio; faltante/invalid -> `unknown`)
  - `ts`
  - `reason`
  - `run_id` (nullable)
  - `symbol` (nullable)
  - `source_log_id` (unique cuando viene de logs)
- `add_log(..., event_type=\"breaker_triggered\")` inserta/actualiza `breaker_events` en tiempo real.
- Backfill legacy desde `logs` disponible en init (`_backfill_breaker_events_from_logs`).

## Lo que sigue faltando (verdad actual)

- Virtualizacion adicional en otras tablas grandes (D2 de comparador ya virtualizado)
- Orden server-side multi-columna (hoy sigue siendo 1 clave por request, aunque ya se puede ordenar por click en UI)
- Endpoints de shortlist por batch (CRUD completo; hoy hay guardado + lectura en detalle de batch)
- Smoke/E2E frontend automatizados
- UI de experimentos MLflow (si se habilita capability)
- Reportes avanzados en detalle de corrida (heatmap mensual, rolling Sharpe, distribuciones)
- Endpoints catalogo para `rerun_exact`, `clone_edit`, `export` unificado por `run_id`
- Adaptador remoto especifico de proveedor financiero pendiente (el motor remoto generico ya esta implementado)
- Fee/Funding provider multi-exchange avanzado pendiente (hoy Binance + Bybit base + fallback con snapshots)
- VPIN L1 con trade tape real (hoy proxy desde OHLCV; falta tape de trades y BBO real)
- Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)

## Restricciones vigentes (no negociables)

- Opcion B: no auto-live
- Promocion real siempre via gates + canary + rollback + approve humano
- Secrets solo por ENV/Secrets
- Runtime y Research separados

## Parametros y criterios exactos (RTLAB Strategy Console)

### Gates avanzados (research masivo)
- `PBO/CSCV`: reject si `PBO > 0.05` (policy)
- `DSR`: `min_dsr = 0.95` (proxy deflactado por batch/trials en esta fase)
- `Walk-forward`: `folds = 5`, deben ser positivos al menos `4`, degradacion IS->OOS <= `30%`
- `Cost stress`: reevaluacion con `x1.5` y `x2.0`; a `x1.5` debe seguir rentable, a `x2.0` no debe caer mas de `50%` del score
- `Min trade quality`: `min_trades_per_run = 150`, `min_trades_per_symbol = 30`

### Microestructura L1 (VPIN proxy actual)
- **Nivel actual**: proxy desde OHLCV (no tape tick-by-tick todavia)
- Bucketing:
  - `target_draws_per_day = 9`
  - `V = ADV / target_draws_per_day` (fallback fijo si falta ADV)
- Bulk classification:
  - cambio de precio estandarizado
  - probabilidad de compra/venta via `CDF Normal`
- `OI_tau = |V_B - V_S|`
- `VPIN = rolling_mean(OI_tau) / (n * V)` con `n = 50`
- `CDF(VPIN)` via distribucion rolling empirica (proxy)
- Kills por simbolo:
  - `SOFT`: `CDF(VPIN) >= 0.90` (o guards spread/slippage/vol)
  - `HARD`: `CDF(VPIN) >= 0.97`

### Modo Bestia (estado actual)
- **Fase 1 implementada**: scheduler local con cola + concurrencia + budget governor + stop/resume
- **Fase 2 pendiente**: Celery + Redis + workers distribuidos + rate limit real por exchange

#### Como habilitar Modo Bestia
1. Ajustar `config/policies/beast_mode.yaml`:
   - `beast_mode.enabled: true`
2. Deploy backend
3. Usar `Backtests -> Research Batch -> Ejecutar en Modo Bestia`
4. Monitorear panel `Modo Bestia` (cola/jobs/budget/stop-all)


## Evidencia UX + Bots + Backtests (2026-03-07)

- `execution/page.tsx` ya permite seleccionar y administrar bots desde `Ejecucion`:
  - selector de bot activo
  - cambio de modo `SHADOW/PAPER/TESTNET`
  - activar/pausar
  - archivar
  - KPIs basicos del bot seleccionado
- La grafica `Traza de Latencia y Spread` quedo aclarada:
  - eje X: `Tiempo / muestra`
  - eje Y izquierdo: `Latencia p95 (ms)`
  - eje Y derecho: `Spread (bps)`
  - leyenda visible
- `strategies/page.tsx` ya soporta operacion bot-centrica incremental:
  - seleccion multiple de estrategias por checkbox
  - `Seleccionar pagina` / `Seleccionar filtradas` / `Limpiar seleccion`
  - `Crear bot con seleccion`
  - enviar estrategias seleccionadas a un bot existente (`Agregar a bot`, `Reemplazar pool`)
  - editar pool del bot con checkboxes
  - borrar bot
  - exportar conocimiento del bot a JSON
  - agregar sugerencias/recomendaciones del bot a un bot destino
- `backtests/page.tsx` ya no confunde `Modo Bestia bloqueado` con `policy faltante`:
  - `GET /api/v1/research/beast/status` expone `policy_state`, `policy_source_root`, `policy_warnings`
  - UI distingue `habilitado`, `bloqueado por policy` y `runtime sin policy`
  - `mass-backtest` y `beast` envian `data_mode=dataset` de forma explicita
- `Research Batch` y `Modo Bestia` ya no encolan jobs inviables cuando falta dataset real:
  - `MassBacktestCoordinator` hace preflight de dataset antes de escribir estado `QUEUED`
  - `POST /api/v1/research/mass-backtest/start` y `POST /api/v1/research/beast/start` devuelven `400` con detalle accionable
  - se evita el patron engañoso `QUEUED -> FAILED` por traceback interno solo porque faltaba `market/symbol/timeframe`
- El polling de `Backtests` ya no consume el bucket `expensive` de la API:
  - `GET` read-only de research/catálogo (`mass status/results/artifacts`, `beast status/jobs`, `batches`, `runs`, `backtests/runs`, `bots`) usan bucket `general`
  - los `POST`/acciones que disparan trabajo siguen en `expensive`
  - el frontend bajó la frecuencia de polling (`mass status: 4s`, `beast panel: 10s`) para evitar `429` autoinducidos y estados viejos en pantalla
- La limpieza local conservadora de 2026-03-07 removió solo artefactos no versionados que confundían la lectura:
  - `tmp/`
  - `rtlab_autotrader/tmp_test_ud/`
  - `rtlab_autotrader/user_data/backtests/` con runs `synthetic_seeded`
  - `rtlab_autotrader/user_data/research/mass_backtests/` vacio
- No se limpiaron `learning/` ni DB/config locales mientras no exista evidencia fuerte de obsolescencia.
- La resolucion de roots de `config/policies` en backend ahora es fail-safe por presencia real de YAML:
  - `rtlab_core/policy_paths.py` rankea candidatos por archivos canonicos disponibles
  - `app.py`, `mass_backtest_engine.py`, `cost_providers.py` y `credit_filter.py` usan esa misma resolucion
  - caso cubierto: si `/app/config/policies` existe vacio pero `/app/rtlab_autotrader/config/policies` tiene los YAML, runtime toma la segunda raiz y deja de publicar `Modo Bestia deshabilitado` falso
- El hueco real que sigue abierto NO es de UI basica sino de trazabilidad historica fuerte:
  - persistir relacion exacta `run_id/episode_id -> bot_id`
  - hoy la vista bot-centrica usa pool/metadata actual derivada

### Validacion local cerrada (2026-03-07)
- `eslint` de `backtests/execution/strategies/client-api/types`: PASS
- `next build` en `rtlab_dashboard`: PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py`: PASS
- `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q`: PASS
- `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py -q`: PASS
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "config_learning_endpoint_reads_yaml_and_exposes_capabilities or config_policies_endpoint_exposes_numeric_policy_bundle or mass_backtest_start_rejects_missing_dataset or research_beast_start_rejects_missing_dataset or mass_backtest_research_endpoints_and_mark_candidate or research_beast_endpoints_smoke" -q`: PASS
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "api_general_rate_limit_guard or api_expensive_rate_limit_guard or api_bots_overview_uses_general_bucket or api_research_readonly_endpoints_use_general_bucket or mass_backtest_research_endpoints_and_mark_candidate" -q`: PASS
- Warnings remanentes: Recharts en prerender (`width/height(-1)`), no bloqueantes

### Nota de bibliografia para este bloque
- Este bloque fue de wiring UI/API, estado runtime y mensajes operativos.
- No introdujo formulas nuevas ni cambios teoricos de microestructura/aprendizaje.
- Base conceptual vigente: bibliografia local del proyecto (31 PDF + 1 TXT).


### Persistencia exacta run -> bot + Beast validado localmente (2026-03-07)
- `Backtests / Runs` ya no depende solo del pool actual para inferir bots relacionados.
- `POST /api/v1/backtests/run`, `POST /api/v1/research/mass-backtest/start`, `POST /api/v1/batches` y `POST /api/v1/research/beast/start` aceptan `bot_id` explicito.
- `create_event_backtest_run(...)` persiste `bot_id` en:
  - `metadata.bot_id`
  - `params_json.bot_id`
  - `provenance.bot_id`
  - `tags += bot:<bot_id>`
- `annotate_runs_with_related_bots(...)` ahora prioriza referencias explicitas del run (`metadata/params_json/provenance/tags`) y solo usa fallback por pool actual si el run historico no trae bot asociado.
- Si un bot historico ya no existe en registry, la UI mantiene el vinculo con placeholder `unknown` en vez de perder la trazabilidad del run.
- Validacion local cerrada:
  - `GET /api/v1/research/beast/status` -> `200`, `policy_state=enabled`, `policy_enabled_declared=true`
  - `POST /api/v1/research/beast/start` con dataset real seed -> `200`, `run_id=BX-000001`, `mode=beast`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strict_strategy_id_flag or preserves_explicit_bot_link_after_pool_change or mass_backtest_start_forwards_bot_id or beast_start_accepts_orderflow_toggle or runs_batches_catalog_endpoints_smoke" -q` -> PASS (`5 passed`)
- Lectura operativa correcta:
  - si la web publica sigue mostrando `Modo Bestia deshabilitado`, el problema restante ya no es esta rama local sino deploy/runtime viejo o entorno remoto sin este commit.

### Limpieza conservadora clasificada (2026-03-07)
- Se removio solo lo claramente obsoleto/no versionado y enga?oso para el trabajo actual:
  - `tmp/`
  - `rtlab_autotrader/tmp_test_ud/`
  - `rtlab_autotrader/user_data/backtests/` con corridas `synthetic_seeded`
  - `rtlab_autotrader/user_data/research/mass_backtests/` vacio
- Se clasifico como `mantener por ahora` todo lo que no tiene evidencia fuerte de obsolescencia:
  - `rtlab_autotrader/user_data/console_api.sqlite3`
  - `rtlab_autotrader/user_data/console_settings.json`
  - `rtlab_autotrader/user_data/learning/`
  - metadata local de estrategias
- Regla vigente de limpieza:
  - identificar
  - clasificar
  - proponer limpieza
  - borrar/mover solo lo claramente obsoleto, redundante o enga?oso
  - no tocar artefactos actuales/ambiguos solo por estar viejos o ser locales

## 2026-04-06

### Paridad frontend ↔ staging API en Backtests
- `Linear MCP` siguio sin estar disponible en esta sesion.
- Hallazgo operativo confirmado:
  - `https://bot-trading-ia-csud.vercel.app/backtests` **no** es la superficie correcta para validar staging.
  - El proyecto Vercel `bot-trading-ia-csud` usa `BACKEND_API_URL=https://bot-trading-ia-production.up.railway.app`.
  - El proyecto Vercel `bot-trading-ia-staging-2` usa `BACKEND_API_URL=https://bot-trading-ia-staging.up.railway.app`.
- Evidencia real contrastada:
  - `csud -> /api/v1/research/beast/status` devuelve `policy_state=missing` y warnings legacy de YAML faltantes.
  - `staging-2 -> /api/v1/research/beast/status` devuelve `policy_state=enabled`, sin warnings, alineado con Railway staging.
  - `health` de production expone `mode=live` y `user_data_dir=/app/data/rtlab_user_data`.
  - `health` de staging expone `mode=paper` y `user_data_dir=/app/user_data`.
- Causa raiz exacta:
  - la divergencia observada no era cache ni payload legacy del frontend;
  - era mezcla de superficies: `csud` muestra production, mientras el saneamiento previo de Beast se habia validado en staging.
- Decision operativa correcta:
  - URL canonica para validar Backtests/Beast contra staging: `https://bot-trading-ia-staging-2.vercel.app/backtests`
  - `csud` queda como superficie de production y no debe usarse como referencia de staging.
- Cambio minimo aplicado:
  - `Backtests` ahora expone en UI el backend objetivo del frontend via `NEXT_PUBLIC_BACKEND_URL`.
  - `staging-smoke.yml` y `scripts/staging_smoke_report.py` pasan a usar `bot-trading-ia-staging-2` como frontend staging por defecto.

### Beast / Backtests staging: test E2E real sobre BTCUSDT
- `Linear MCP` no estuvo disponible en esta sesion.
- El bloque se ejecuto como validacion operativa puntual, no como megaproyecto de Backtests.
- Verdad tecnica confirmada en staging:
  - `policy_state=enabled`
  - `policy_source_root=/app/config/policies`
  - `data_root=/app/user_data/data`
  - dataset base disponible: `BTCUSDT 1m` real en volumen persistente
- Se ejecuto una corrida real de Beast sobre staging con:
  - endpoint: `POST /api/v1/research/beast/start`
  - estrategia: `trend_pullback_orderflow_confirm_v1`
  - `market=crypto`
  - `symbol=BTCUSDT`
  - `timeframe=5m`
  - periodo: `2024-01-01 -> 2024-03-31`
  - `dataset_source=auto`
  - `data_mode=dataset`
  - `validation_mode=walk-forward`
  - `use_orderflow_data=false`
- Evidencia real del run:
  - workflow GitHub Actions: `24022545610`
  - artifact con reporte E2E + smoke + beast runtime
  - `run_id=BX-000001`
  - estado terminal: `COMPLETED`
  - `results_count=1`
  - `variants_total=1`
  - `strategy_id=trend_pullback_orderflow_confirm_v1`
- El motor resolvio correctamente `1m + resample`:
  - antes del run no habia dataset exacto `BTCUSDT 5m`
  - despues del run quedo `exact_present=true`
  - archivo generado: `/app/user_data/data/crypto/processed/BTCUSDT_5m.parquet`
  - manifest generado: `/app/user_data/data/crypto/manifests/BTCUSDT_5m.json`
- Lectura correcta del estado:
  - Beast/Backtests ya no esta roto por `policy root`
  - staging ya esta listo para testeo real sobre `BTCUSDT`
  - el siguiente cuello ya no es runtime basico sino cobertura de datasets/estrategias si se quiere ampliar el pool
- RTLOPS-70 / Cost Stack Reporting UI read-only (2026-05-05):
  - se agrega la superficie frontend `Costos` / `/reporting` para hacer visible el Cost Stack existente en backend;
  - consume solo endpoints read-only existentes:
    - `/api/v1/reporting/performance/summary`;
    - `/api/v1/reporting/performance/daily`;
    - `/api/v1/reporting/performance/monthly`;
    - `/api/v1/reporting/costs/breakdown`;
    - `/api/v1/reporting/trades`;
    - `/api/v1/reporting/exports`;
  - muestra gross/net PnL, costos estimados/realizados, fees, spread, slippage, funding, borrow interest, ledger de trades de reporting y manifiesto de exports;
  - `taxCommission` y `specialCommission` quedan explicitamente marcados como pendientes/no soportados todavia;
  - no agrega mutaciones, no consulta Binance privado y no activa LIVE;
  - RTLOPS-106 sigue abierto como deuda externa Vercel Git Integration / `routes-manifest-deterministic`.
- RTLOPS-70 / cobertura QA protegida de Reporting (2026-05-05):
  - se extiende `RTLOPS-109A Protected Preview QA` para incluir `/reporting` en el probe HTTP, Playwright read-only y QA autenticado viewer;
  - el QA autenticado verifica que la navegacion exponga `Costos` y que la pantalla muestre `Cost Stack`, `Reporting`, `taxCommission`, `specialCommission`, `pendiente` y `no soportado`;
  - la cobertura sigue siendo read-only: no agrega POST/PUT/PATCH/DELETE, no ejecuta ordenes y no toca Binance privado.
- RTLOPS-61 / taxCommission + specialCommission auditables (2026-05-06):
  - `FeeProvider` preserva componentes `standardCommission`, `taxCommission` y `specialCommission` cuando Binance Spot devuelve `GET /api/v3/account/commission`;
  - `ReportingBridgeService.costs_breakdown()` expone `commission_components` desde `cost_source_snapshots` y desde `fee_snapshots` locales existentes, con `value`, `asset`, `source`, `family`, `symbol`, `observed_at/fetched_at`, `freshness`, `status`, `provenance` y `estimated_vs_realized`;
  - Spot queda como contrato soportado por metadata oficial; sin snapshot autenticado el valor queda pendiente, no se infiere cero;
  - USD-M/COIN-M Futures quedan con `standard_commission` via maker/taker `commissionRate`, y `taxCommission`/`specialCommission` como `not_applicable`;
  - Margin conserva borrow/interest como fuente separada; `taxCommission`/`specialCommission` quedan `unsupported` hasta contrato oficial confirmado;
  - `/reporting` muestra la evidencia cuando existe y mantiene estados honestos `soportado`, `pendiente`, `no soportado` o `no aplica`;
  - no se usaron Binance keys reales, no se activo LIVE, no hubo ordenes ni mutaciones;
  - RTLOPS-106 sigue abierto como deuda externa Vercel Git Integration / `routes-manifest-deterministic`.
- RTLOPS-62 / Cost Stack compacto en Trades y Portfolio (2026-05-06):
  - `/reporting` sigue siendo el hub principal y fuente canonica visual del Cost Stack;
  - `/trades` agrega una vista compacta read-only por fila con gross/net PnL, fees, spread, slippage, funding, borrow interest, source, status y freshness cuando existe evidencia de reporting;
  - `/trades` mantiene fallback honesto al endpoint de trades para fees/slippage/gross/net y marca el resto como `pendiente` si no hay fila reporting asociada;
  - `/portfolio` agrega resumen agregado `Costos y PnL neto` desde `/api/v1/reporting/performance/summary` y `/api/v1/reporting/costs/breakdown`;
  - `/portfolio` muestra gross/net PnL, costos totales, fees, spread/slippage, funding/borrow, freshness/status/source y cobertura `standardCommission`/`taxCommission`/`specialCommission`;
  - no se crearon endpoints backend, no se consultaron Binance keys, no se activo LIVE y no hubo ordenes ni mutaciones;
  - quedan pendientes bloques especificos para `/execution` y `/risk`;
  - RTLOPS-106 sigue abierto como deuda externa Vercel Git Integration / `routes-manifest-deterministic`.
