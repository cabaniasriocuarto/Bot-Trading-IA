# AP-BOT-1006..1010 - Revalidacion Bibliografica Completa

Fecha: 2026-03-04

Objetivo: cerrar el gap reportado de validacion bibliografica en AP-BOT-1006, AP-BOT-1007, AP-BOT-1008, AP-BOT-1009 y AP-BOT-1010, con trazabilidad por AP.

## Fuentes usadas

### Bibliografia local (con hash en indice)
- `docs/reference/BIBLIO_INDEX.md:18` -> `1 - Hasbrouck's book.pdf` (SHA256 `2b5937a214f26f665365c4ededbec08f540585ea765948a6244560efec685a0f`).
- `docs/reference/BIBLIO_INDEX.md:31` -> `3 - Trading-Exchanges-Market-Microstructure-Practitioners Draft Copy.pdf` (SHA256 `030f6dbdf334f365d4aa24d6773053bc858f0b6f494631492a7fd70bfe8702ac`).
- `docs/reference/BIBLIO_INDEX.md:32` -> `4 - Price_Impact.pdf` (SHA256 `ca92d2ea4c74f351334abef492c222a18ec3e5e53aa6d9df1975fe981a228229`).
- `docs/reference/BIBLIO_INDEX.md:36` -> `8 - Algo_and_HFT_Trading_0610.pdf` (SHA256 `3cfb151464fec953187a93d97b182cf4a64f1a728949dd1203d724ca62d29056`).
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf` (SHA256 `85466da2a2d214aec44932922682e05441571fb59ada56466871d8da1057eeef`).
- `docs/reference/BIBLIO_INDEX.md:23` -> `14 - api-overview.pdf` (SHA256 `be1406126690e0f1d94c2a735e9231632a382325409daa1e259a1aad9b0e5384`).

### Fuentes web primarias (solo oficiales/alto nivel)
- Binance Spot API - Trading endpoints: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints
- Binance Spot API - Account endpoints: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints
- Binance USD-M Futures - Funding rate history: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
- Linux man-pages (`/proc/pid/cmdline`): https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html
- Microsoft (evento de proceso incluye command line): https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/component-updates/command-line-process-auditing
- MITRE CWE-532 (sensitive info in logs): https://cwe.mitre.org/data/definitions/532.html
- Kubernetes rollout/rollback: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

## AP-BOT-1006 - submit remoto idempotente (default-off)

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py:189-190` define flags de activacion e idempotencia (`RUNTIME_REMOTE_ORDERS_ENABLED=false`, `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC`).
- `rtlab_autotrader/rtlab_core/web/app.py:5433-5559` implementa memoria de idempotencia por `client_order_id`, construccion estable de ID y submit firmado.
- `rtlab_autotrader/rtlab_core/web/app.py:5808-5860` persiste trazabilidad runtime (`runtime_last_remote_submit_*`).

### Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1071-1077` describe que una orden debe definir condiciones de ejecucion (incluye validez temporal y partial fills).
- `...Draft_Copy.txt:1150-1153` define standing/open orders como estado operativo que persiste.
- `...Draft_Copy.txt:1235-1239` refuerza modelo operativo de `order routing`, reportes de fills y libros de `open orders`.

### NO EVIDENCIA LOCAL
- No hay semantica API-especifica en biblio local para unicidad idempotente tipo `newClientOrderId` ni codigos de error de exchange.

### Complemento web primario
- Binance `POST /api/v3/order` y parametro `newClientOrderId` (unicidad entre ordenes abiertas) en la doc oficial de trading endpoints.

### Conclusion
- AP-1006 queda bibliograficamente sustentado en principios de microestructura/ordenes (local) y contrato API de exchange (primario web).

## AP-BOT-1007 - reconciliacion de posiciones por account snapshot

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py:5350-5404` parsea balances a posiciones runtime y consulta `/api/v3/account`.
- `rtlab_autotrader/rtlab_core/web/app.py:5885-5908` actualiza `runtime_account_positions_*` con fallback seguro.
- `rtlab_autotrader/rtlab_core/web/app.py:5655-5658` y `5975` prioriza snapshot remoto en `positions()` y `risk_snapshot`.

### Soporte bibliografico local
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:1235-1239` describe ciclo de ordenes/fills y libros abiertos como base de reconciliacion operativa.
- `...Draft_Copy.txt:1523-1536` clearing/settlement como problema central de post-trade (necesidad de conciliacion/garantia).
- `...Draft_Copy.txt:885-889` definicion formal de posiciones long/short para snapshot de exposicion.

### NO EVIDENCIA LOCAL
- No hay especificacion de endpoints concretos `GET /api/v3/account` y `GET /api/v3/openOrders` en biblio local.

### Complemento web primario
- Binance account endpoints para `GET /api/v3/account` y `GET /api/v3/openOrders` (contrato oficial de datos de cuenta/ordenes).

### Conclusion
- AP-1007 queda validado contra teoria de post-trade/reconciliacion local + especificacion oficial de exchange.

## AP-BOT-1008 - costos runtime por fill-delta

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py:5062-5173` define acumuladores y estimador incremental de costos (`fees/spread/slippage/funding/total`).
- `rtlab_autotrader/rtlab_core/web/app.py:5911` captura costos por delta de fills durante sync runtime.
- `rtlab_autotrader/rtlab_core/web/app.py:6083-6097` expone breakdown de costos en `execution_metrics`.
- `rtlab_autotrader/rtlab_core/web/app.py:6877-6891` fail-closed de costos a cero cuando telemetria es sintetica.

### Soporte bibliografico local
- `docs/reference/biblio_txt/1_-_Hasbrouck_s_book.txt:301-306` define liquidez con dimensiones de costo/tiempo.
- `...Hasbrouck_s_book.txt:1233-1235` relacion spread e impacto como costo microestructural.
- `...Hasbrouck_s_book.txt:5829` explicita componente de costo fijo de liquidez + parametro de impacto.
- `docs/reference/biblio_txt/4_-_Price_Impact.txt:6-12` impacto como costo de ejecucion.
- `...Price_Impact.txt:313-324` vinculo spread-impacto como dos caras del mismo mecanismo de costo.
- `docs/reference/biblio_txt/3_-_Trading-Exchanges-Market-Microstructure-Practitioners_Draft_Copy.txt:3413-3424` taxonomia de costos explicitos e implicitos (fees, spread, impact).

### NO EVIDENCIA LOCAL
- No hay especificacion local de `funding` por endpoint de exchange para cripto derivados.

### Complemento web primario
- Binance futures funding rate history para justificar trazabilidad futura de `funding` observado (hoy en AP-1008 queda proxy controlado por settings).
- Binance trading endpoints documenta respuesta de orden con estructura de fills, base para contabilidad por delta de fill.

### Conclusion
- AP-1008 queda respaldado por teoria microestructural fuerte (local) y contrato API oficial para evolucionar de proxy a observacion directa.

## AP-BOT-1009 - hardening de `--password` + guard CI

### Evidencia tecnica del repo
- `.github/workflows/security-ci.yml:19-28` agrega guard fail-closed para bloquear `--password` en automatizacion.
- `scripts/seed_bots_remote.py:20-31,167-171,199` y `scripts/check_storage_persistence.py:21-31,111-115,137` deprecan/bloquean password CLI por defecto.
- `scripts/run_bots_benchmark_sweep_remote.ps1:69-76,87,116,164-167` migra a variables de entorno temporales y restaura estado.

### Soporte bibliografico local
- `docs/reference/biblio_txt/14_-_api-overview.txt:46-53,90-92,107-110` enfatiza tokenizacion y entrega segura de credenciales de API (no password operativa en linea de comando).

### NO EVIDENCIA LOCAL
- No hay tratamiento explicito en biblio local sobre exposicion de secretos en argumentos de proceso CLI.

### Complemento web primario
- Linux `/proc/pid/cmdline` muestra argumentos completos del proceso.
- Microsoft documenta auditoria de procesos con command line.
- CWE-532 clasifica riesgo de exponer secretos en logs.

### Conclusion
- AP-1009 queda validado con principio local de token-seguro + evidencia primaria OS/CWE sobre riesgo de secrets en command line y trazas.

## AP-BOT-1010 - cierre no-live formal

### Evidencia tecnica del repo
- `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md` formaliza checklist de cierre no-live y estado GO/NO-GO.
- `docs/truth/SOURCE_OF_TRUTH.md:162-172` y `docs/truth/NEXT_STEPS.md:83-89` fijan decision operativa (testnet GO, LIVE postergado).

### Soporte bibliografico local
- `docs/reference/biblio_txt/8_-_Algo_and_HFT_Trading_0610.txt:42-44` exige monitoreo cercano de operacion y performance con controles prudenciales.
- `...Algo_and_HFT_Trading_0610.txt:174-177` monitoreo de volumen de ejecuciones y trafico de ordenes.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:6558-6561` automatizar con intervencion humana ante excepciones/problemas.
- `docs/reference/biblio_txt/14_-_api-overview.txt:184-210` valor de estado operacional API antes de ejecutar flujos productivos.

### NO EVIDENCIA LOCAL
- No hay procedimiento formal de canary/rollback detallado en los PDFs locales.

### Complemento web primario
- Kubernetes deployment docs para estrategia de rollout y rollback (`rollout undo`) como control operativo de liberacion.

### Conclusion
- AP-1010 queda sustentado en disciplina operativa local y estandares de despliegue controlado para el tramo previo a LIVE.

## Resultado global
- Estado de la revalidacion bibliografica AP-1006..1010: COMPLETA.
- Criterio aplicado: local-first; cuando falto especificidad, se complemento solo con fuente primaria oficial.
