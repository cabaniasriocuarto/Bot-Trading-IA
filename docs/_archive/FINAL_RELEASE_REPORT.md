# FINAL READY? â€” Informe de AuditorÃ­a (Release Candidate)

Fecha de auditorÃ­a: 2026-02-23  
Estado del enfoque: **OpciÃ³n B (recomienda, no auto-live)**  
Objetivo de este informe: decidir si el bot estÃ¡ en **release candidate** y quÃ© falta para LIVE real.

---

## 1) Estado actual (quÃ© funciona hoy)

### Backend / Core
- **Backtests**: corridas manuales, costos (fees/spread/slippage/funding), mÃ©tricas extendidas, artifacts.
- **Data provenance**: `dataset_hash`, costos usados, `commit_hash`, modo/rango, manifests.
- **Knowledge Pack v2**: templates/ranges/filters/gates/learning_engines/visual_cues/strategies_v2 cargados.
- **Learning (OpciÃ³n B)**:
  - selector config-driven (Thompson/UCB1/Fixed Rules)
  - drift detection (ADWIN/Page-Hinkley runtime options)
  - recomendaciones runtime + research loop
  - no auto-live
- **Strategy Registry** (SQLite):
  - pool de aprendizaje (`allow_learning`)
  - enable trading
  - primaria Ãºnica
  - archivo/soft delete
- **Safe Update with Gates**:
  - rollout manager
  - offline gates
  - compare vs baseline
  - paper/testnet soak
  - canary/shadow
  - rollback
  - approve/reject
- **Research Mass Backtests (nuevo)**:
  - start/status/results/artifacts
  - ranking robusto
  - drilldown por rÃ©gimen
  - mark candidate (draft OpciÃ³n B)
  - sin auto-live

### Frontend / Dashboard
- **Settings** config-driven desde YAML (`/api/v1/config/learning`)
- **Strategies** con registry + toggles + KPIs + pool de aprendizaje
- **Backtests** con comparador + colores KPI
- **Backtests > Research Masivo** con botones, progreso, ranking, drilldown y â€œMarcar candidatoâ€
- **Rollout / Gates** (panel operativo en Settings)

### Runtime / OperaciÃ³n
- PAPER / TESTNET / LIVE con gates de habilitaciÃ³n
- DiagnÃ³stico backend/ws/exchange
- OpciÃ³n B bloquea autopromociÃ³n a live

---

## 2) Â¿VersiÃ³n final? (criterio actual)

### Veredicto
- **No-Go para LIVE real â€œfinalâ€ todavÃ­a**
- **SÃ­** estÃ¡ en nivel **Release Candidate tÃ©cnico (RC)** para:
  - pruebas integrales en paper/testnet
  - research masivo offline
  - validaciÃ³n operativa de gates/canary/rollback

Motivo: faltan bloqueantes operativos/seguridad/infra y validaciones reales en entorno final.

---

## 3) Bloqueantes (impiden â€œversiÃ³n finalâ€)

1. **Conectividad real a testnet/live estable (infra)**
- Se observÃ³ `HTTP 451` con Binance Testnet desde Railway (restricciÃ³n de proveedor/regiÃ³n/egress).
- Mientras eso exista, los gates de exchange/test order pueden fallar aunque el cÃ³digo estÃ© bien.
- AcciÃ³n: mover backend a regiÃ³n/proveedor permitido o validar testnet desde VPS/local permitido.

2. **PBO/DSR completos (hoy proxy fail-closed en research masivo)**
- El motor masivo usa proxy de PBO/DSR para evidencia y bloqueo de promociÃ³n.
- Para â€œversiÃ³n final institucionalâ€ falta implementaciÃ³n robusta (CSCV/CPCV/DSR real) o integraciÃ³n auditada.

3. **CI/CD de seguridad y dependencias no automatizado**
- Hay scripts (`deps_check`, `security_audit`), pero falta integrarlos en pipeline (GitHub Actions / CI).
- Release final deberÃ­a bloquear deploy ante conflictos/vulnerabilidades crÃ­ticas.

4. **ValidaciÃ³n operativa end-to-end con capital mÃ­nimo**
- Falta un drill completo real:
  - testnet soak
  - canary 5%â†’15%â†’rollback/approve
  - runbook confirmado

5. **Secrets de producciÃ³n y hardening operativo**
- Aunque no hay API keys hardcodeadas, hay defaults inseguros posibles en `.env.example`/runtime si no se sobrescriben (`ADMIN_PASSWORD`, etc.).
- Para final real: todos los secrets deben estar definidos y rotados en Railway/Vercel/VPS.

6. **Performance real de `/api/v1/bots` en produccion (objetivo no cumplido)**
- Benchmark remoto ejecutado en Railway:
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md`
  - resultado: `p95 = 1663.014 ms` (objetivo `< 300 ms`) => **FAIL**
- Estado de evidencia:
  - **NO EVIDENCIA** para benchmark objetivo de 100 bots (el endpoint devolvio `1` bot; minimo requerido `100`).

---

## 4) Importantes (mejoras recomendadas antes/despuÃ©s del RC)

1. **Pandera en pipeline de datasets**
- Validar OHLCV (nulos, duplicados, monotonicidad, gaps) en downloader/pipeline de datasets.

2. **UI de Experimentos / MLflow (capability)**
- Endpoint ya existe; falta panel UI si se decide habilitar `mlflow_runs`.

3. **Visual cues 100% config-driven en Backtests**
- Ya existe base de colores y pack; ideal terminar de leer thresholds desde YAML tambiÃ©n en todos los widgets.

4. **Reportes QuantStats/HTML por top-N del mass backtest**
- Hoy hay artifact HTML simple + JSON top candidates.
- Mejorar con reportes mÃ¡s ricos si `quantstats` estÃ¡ disponible.

5. **MÃ©tricas reales de ejecuciÃ³n (maker/taker ratio, slippage p95) consolidadas**
- Algunas mÃ©tricas estÃ¡n, pero conviene unificar fuentes para live/testnet y explotarlas en ranking por rÃ©gimen.

---

## 5) Nice-to-have

1. **ParalelizaciÃ³n joblib/Ray efectiva** en motor masivo (actualmente el flujo es funcional y estable, no HPC).
2. **API mode** de data provider para research (opcional, no recomendado como modo principal).
3. **SBOM firmado** y publicaciÃ³n automÃ¡tica por release.
4. **Dashboards externos** (Grafana/Prometheus) para canary live.

---

## 6) Seguridad (estado actual)

### Secrets
- **API keys de exchange**: no se hardcodean; se leen por variables de entorno/secrets.
- **Telegram token/chat**: por env vars.
- **Auth secret**: por env var.

### ObservaciÃ³n importante
- Existen defaults de credenciales admin/viewer para bootstrap/dev si el usuario no configura env vars.
- Para â€œfinal realâ€ esto debe considerarse **bloqueante operativo** (cambiar/forzar secrets reales).

### Permisos de exchange
- RecomendaciÃ³n aplicada/documentada:
  - `Read + Trade`
  - **NUNCA Withdraw**
  - IP whitelist si el exchange lo soporta

### Logs
- La app reporta estado/errores, pero no debe exponer secrets.
- RecomendaciÃ³n: auditar logs de producciÃ³n y aplicar redacciÃ³n (Ãºltimos 4 chars) si se agrega debug extra.

### CI
- **No confirmado** pipeline automÃ¡tico de seguridad/deps en este informe.
- Se agregaron scripts locales para que el usuario los ejecute y/o los conecte al CI.

Referencias:
- `docs/SECURITY.md`
- `scripts/security_audit.sh`
- `scripts/deps_check.sh`

---

## 7) Compatibilidad de librerÃ­as (â€œÂ¿hacen ruido?â€)

### Estado
- Runtime y Research estÃ¡n **separados**.
- Las capabilities de research (`ruptures`, `mlflow`, etc.) tienen fallback seguro si faltan librerÃ­as.
- El backend no rompe si falta el stack research.

### Posibles puntos de ruido (compilaciÃ³n/peso)
- `pyarrow`, `cvxpy`, `vectorbt`, `riskfolio-lib`, `arch`

### CÃ³mo confirmarlo (usuario)
1. Instalar runtime en entorno live:
   - `requirements-runtime.txt`
2. Instalar research en entorno research:
   - `requirements-research.txt`
3. Ejecutar:
   - `bash scripts/deps_check.sh`
   - `bash scripts/security_audit.sh`

MÃ¡s detalle:
- `docs/DEPENDENCIES_COMPAT.md`

---

## 8) Mass Backtest Data: Â¿necesita APIs?

### Respuesta
- **NO** necesita APIs privadas para funcionar (modo recomendado).
- Modo recomendado: **DATASET MODE** con datasets pÃºblicos + reproducibles.
- **SÃ­** necesita internet para descargar datasets pÃºblicos (si no estÃ¡n ya en disco).
- **API keys solo para trading** (`paper/testnet/live`) o API mode opcional.

### Data source recomendado (crypto)
- **Binance Public Data** (`data.binance.vision`) con el downloader existente:
  - `rtlab_autotrader/scripts/download_crypto_binance_public.py`

### Forex / Stocks
- Placeholder documentado (Dukascopy / Alpaca) sin obligarte a conectarlos ahora.

MÃ¡s detalle:
- `docs/MASS_BACKTEST_DATA.md`

---

## 9) Checklist Go / No-Go para LIVE real

### Go (solo si TODO estÃ¡ cumplido)
- [ ] Secrets reales configurados en Railway/VPS (sin defaults)
- [ ] Permisos exchange mÃ­nimos (`Read+Trade`, sin `Withdraw`)
- [ ] Testnet operativo sin bloqueos de red (sin `HTTP 451`)
- [ ] `deps_check` OK
- [ ] `security_audit` revisado (sin CVEs crÃ­ticas en runtime sin mitigaciÃ³n)
- [ ] Benchmark remoto de /api/v1/bots con >=100 bots y p95 < 300ms con evidencia en docs/audit/
- [ ] Backtests robustos con datasets reales (`dataset_hash` consistente)
- [ ] PBO/DSR (o polÃ­tica fail-closed aceptada y aprobada) documentados
- [ ] Paper soak y Testnet soak validados
- [ ] Canary + rollback automÃ¡tico probados (drill)
- [ ] AprobaciÃ³n humana (`approve`) confirmada antes de `STABLE_100`

### No-Go inmediato
- [ ] Testnet/live inaccesible por red/egress
- [ ] Secrets no configurados / credenciales por defecto activas
- [ ] Sin rollback drill
- [ ] `/api/v1/bots` sin evidencia de carga objetivo (100 bots) o con `p95` fuera de umbral
- [ ] Sin revisiÃ³n de vulnerabilidades crÃ­ticas runtime

---

## 10) Acciones del usuario (paso a paso)

### A. Secrets y seguridad
1. Cargar secrets en **Railway (backend)**:
   - `AUTH_SECRET`
   - `ADMIN_PASSWORD`, `VIEWER_PASSWORD`
   - `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET` (testnet)
   - `BINANCE_API_KEY`, `BINANCE_API_SECRET` (live, solo cuando toque)
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (opcional)
2. Confirmar permisos de exchange:
   - `Read + Trade`
   - **No Withdraw**
3. Activar whitelist de IP (si posible).

### B. Chequeo de dependencias y seguridad
1. Entorno runtime:
   - instalar `requirements-runtime.txt`
2. Entorno research (local/VPS research):
   - instalar `requirements-research.txt`
3. Ejecutar:
   - `bash scripts/deps_check.sh`
   - `bash scripts/security_audit.sh`
4. Revisar reportes en `artifacts/security_audit/`

### C. Datasets (Mass Backtest sin API keys)
1. Descargar datasets pÃºblicos crypto:
```bash
python rtlab_autotrader/scripts/download_crypto_binance_public.py --start-month 2024-01 --end-month 2024-06 --symbols BTCUSDT ETHUSDT
```
2. Verificar que exista manifest/dataset hash en `user_data/data/crypto/manifests/`
3. (Opcional) migrar/duplicar manifest a `user_data/datasets/binance_public/crypto/...` (el provider nuevo lo soporta)

### D. Correr un Mass Backtest de prueba
1. Abrir `Backtests` en el dashboard
2. Ir al panel **Research Masivo**
3. Seleccionar estrategias (pool research)
4. `dataset_source = auto` si ya descargaste datos reales, o `synthetic` para prueba rÃ¡pida
5. Click en `Ejecutar Backtests Masivos`
6. Revisar:
   - progreso / logs
   - ranking robusto
   - KPIs por rÃ©gimen
   - artifacts
7. Usar `Marcar candidato` (genera draft OpciÃ³n B, no live)

### E. Safe Update (gates + canary + approve)
1. Ir a `Settings` â†’ `Rollout / Gates`
2. Seleccionar `Run candidato` + baseline
3. `Start`
4. Evaluar fases (`paper_soak`, `testnet_soak`, `shadow`, `canaryXX`)
5. Verificar rollback automÃ¡tico si breach
6. `Approve` solo cuando corresponda (manual)


### F. Benchmark remoto de /api/v1/bots (produccion)
1. Ejecutar benchmark remoto con 100 bots requeridos:
```bash
python scripts/benchmark_bots_overview.py --base-url https://bot-trading-ia-production.up.railway.app --username "Wadmin" --password "***" --requests 200 --warmup 30 --min-bots-required 100 --report-path docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md
```
2. Revisar en el reporte:
   - `bots_seen` (debe ser `>=100`)
   - `p95_ms` (debe ser `<300`)
3. Si falla por cardinalidad o latencia, queda **No-Go** hasta remediar y rerun.
---

## 11) Confirmaciones clave (pedidas)

- **Research separado de runtime**: âœ…
- **No performance-chasing**: âœ… (ventanas mÃ­nimas + gates + canary + rollback + OpciÃ³n B; ademÃ¡s guardrails/cooldowns en learning)
- **No auto-live**: âœ… (OpciÃ³n B, approve humano requerido)
- **Mass Backtest no requiere APIs privadas**: âœ… (DATASET MODE recomendado)

