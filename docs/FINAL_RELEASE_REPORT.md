# FINAL READY? — Informe de Auditoría (Release Candidate)

Fecha de auditoría: 2026-02-23  
Estado del enfoque: **Opción B (recomienda, no auto-live)**  
Objetivo de este informe: decidir si el bot está en **release candidate** y qué falta para LIVE real.

---

## 1) Estado actual (qué funciona hoy)

### Backend / Core
- **Backtests**: corridas manuales, costos (fees/spread/slippage/funding), métricas extendidas, artifacts.
- **Data provenance**: `dataset_hash`, costos usados, `commit_hash`, modo/rango, manifests.
- **Knowledge Pack v2**: templates/ranges/filters/gates/learning_engines/visual_cues/strategies_v2 cargados.
- **Learning (Opción B)**:
  - selector config-driven (Thompson/UCB1/Fixed Rules)
  - drift detection (ADWIN/Page-Hinkley runtime options)
  - recomendaciones runtime + research loop
  - no auto-live
- **Strategy Registry** (SQLite):
  - pool de aprendizaje (`allow_learning`)
  - enable trading
  - primaria única
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
  - drilldown por régimen
  - mark candidate (draft Opción B)
  - sin auto-live

### Frontend / Dashboard
- **Settings** config-driven desde YAML (`/api/v1/config/learning`)
- **Strategies** con registry + toggles + KPIs + pool de aprendizaje
- **Backtests** con comparador + colores KPI
- **Backtests > Research Masivo** con botones, progreso, ranking, drilldown y “Marcar candidato”
- **Rollout / Gates** (panel operativo en Settings)

### Runtime / Operación
- PAPER / TESTNET / LIVE con gates de habilitación
- Diagnóstico backend/ws/exchange
- Opción B bloquea autopromoción a live

---

## 2) ¿Versión final? (criterio actual)

### Veredicto
- **No-Go para LIVE real “final” todavía**
- **Sí** está en nivel **Release Candidate técnico (RC)** para:
  - pruebas integrales en paper/testnet
  - research masivo offline
  - validación operativa de gates/canary/rollback

Motivo: faltan bloqueantes operativos/seguridad/infra y validaciones reales en entorno final.

---

## 3) Bloqueantes (impiden “versión final”)

1. **Conectividad real a testnet/live estable (infra)**
- Se observó `HTTP 451` con Binance Testnet desde Railway (restricción de proveedor/región/egress).
- Mientras eso exista, los gates de exchange/test order pueden fallar aunque el código esté bien.
- Acción: mover backend a región/proveedor permitido o validar testnet desde VPS/local permitido.

2. **PBO/DSR completos (hoy proxy fail-closed en research masivo)**
- El motor masivo usa proxy de PBO/DSR para evidencia y bloqueo de promoción.
- Para “versión final institucional” falta implementación robusta (CSCV/CPCV/DSR real) o integración auditada.

3. **CI/CD de seguridad y dependencias no automatizado**
- Hay scripts (`deps_check`, `security_audit`), pero falta integrarlos en pipeline (GitHub Actions / CI).
- Release final debería bloquear deploy ante conflictos/vulnerabilidades críticas.

4. **Validación operativa end-to-end con capital mínimo**
- Falta un drill completo real:
  - testnet soak
  - canary 5%→15%→rollback/approve
  - runbook confirmado

5. **Secrets de producción y hardening operativo**
- Aunque no hay API keys hardcodeadas, hay defaults inseguros posibles en `.env.example`/runtime si no se sobrescriben (`ADMIN_PASSWORD`, etc.).
- Para final real: todos los secrets deben estar definidos y rotados en Railway/Vercel/VPS.

---

## 4) Importantes (mejoras recomendadas antes/después del RC)

1. **Pandera en pipeline de datasets**
- Validar OHLCV (nulos, duplicados, monotonicidad, gaps) en downloader/pipeline de datasets.

2. **UI de Experimentos / MLflow (capability)**
- Endpoint ya existe; falta panel UI si se decide habilitar `mlflow_runs`.

3. **Visual cues 100% config-driven en Backtests**
- Ya existe base de colores y pack; ideal terminar de leer thresholds desde YAML también en todos los widgets.

4. **Reportes QuantStats/HTML por top-N del mass backtest**
- Hoy hay artifact HTML simple + JSON top candidates.
- Mejorar con reportes más ricos si `quantstats` está disponible.

5. **Métricas reales de ejecución (maker/taker ratio, slippage p95) consolidadas**
- Algunas métricas están, pero conviene unificar fuentes para live/testnet y explotarlas en ranking por régimen.

---

## 5) Nice-to-have

1. **Paralelización joblib/Ray efectiva** en motor masivo (actualmente el flujo es funcional y estable, no HPC).
2. **API mode** de data provider para research (opcional, no recomendado como modo principal).
3. **SBOM firmado** y publicación automática por release.
4. **Dashboards externos** (Grafana/Prometheus) para canary live.

---

## 6) Seguridad (estado actual)

### Secrets
- **API keys de exchange**: no se hardcodean; se leen por variables de entorno/secrets.
- **Telegram token/chat**: por env vars.
- **Auth secret**: por env var.

### Observación importante
- Existen defaults de credenciales admin/viewer para bootstrap/dev si el usuario no configura env vars.
- Para “final real” esto debe considerarse **bloqueante operativo** (cambiar/forzar secrets reales).

### Permisos de exchange
- Recomendación aplicada/documentada:
  - `Read + Trade`
  - **NUNCA Withdraw**
  - IP whitelist si el exchange lo soporta

### Logs
- La app reporta estado/errores, pero no debe exponer secrets.
- Recomendación: auditar logs de producción y aplicar redacción (últimos 4 chars) si se agrega debug extra.

### CI
- **No confirmado** pipeline automático de seguridad/deps en este informe.
- Se agregaron scripts locales para que el usuario los ejecute y/o los conecte al CI.

Referencias:
- `docs/SECURITY.md`
- `scripts/security_audit.sh`
- `scripts/deps_check.sh`

---

## 7) Compatibilidad de librerías (“¿hacen ruido?”)

### Estado
- Runtime y Research están **separados**.
- Las capabilities de research (`ruptures`, `mlflow`, etc.) tienen fallback seguro si faltan librerías.
- El backend no rompe si falta el stack research.

### Posibles puntos de ruido (compilación/peso)
- `pyarrow`, `cvxpy`, `vectorbt`, `riskfolio-lib`, `arch`

### Cómo confirmarlo (usuario)
1. Instalar runtime en entorno live:
   - `requirements-runtime.txt`
2. Instalar research en entorno research:
   - `requirements-research.txt`
3. Ejecutar:
   - `bash scripts/deps_check.sh`
   - `bash scripts/security_audit.sh`

Más detalle:
- `docs/DEPENDENCIES_COMPAT.md`

---

## 8) Mass Backtest Data: ¿necesita APIs?

### Respuesta
- **NO** necesita APIs privadas para funcionar (modo recomendado).
- Modo recomendado: **DATASET MODE** con datasets públicos + reproducibles.
- **Sí** necesita internet para descargar datasets públicos (si no están ya en disco).
- **API keys solo para trading** (`paper/testnet/live`) o API mode opcional.

### Data source recomendado (crypto)
- **Binance Public Data** (`data.binance.vision`) con el downloader existente:
  - `rtlab_autotrader/scripts/download_crypto_binance_public.py`

### Forex / Stocks
- Placeholder documentado (Dukascopy / Alpaca) sin obligarte a conectarlos ahora.

Más detalle:
- `docs/MASS_BACKTEST_DATA.md`

---

## 9) Checklist Go / No-Go para LIVE real

### Go (solo si TODO está cumplido)
- [ ] Secrets reales configurados en Railway/VPS (sin defaults)
- [ ] Permisos exchange mínimos (`Read+Trade`, sin `Withdraw`)
- [ ] Testnet operativo sin bloqueos de red (sin `HTTP 451`)
- [ ] `deps_check` OK
- [ ] `security_audit` revisado (sin CVEs críticas en runtime sin mitigación)
- [ ] Backtests robustos con datasets reales (`dataset_hash` consistente)
- [ ] PBO/DSR (o política fail-closed aceptada y aprobada) documentados
- [ ] Paper soak y Testnet soak validados
- [ ] Canary + rollback automático probados (drill)
- [ ] Aprobación humana (`approve`) confirmada antes de `STABLE_100`

### No-Go inmediato
- [ ] Testnet/live inaccesible por red/egress
- [ ] Secrets no configurados / credenciales por defecto activas
- [ ] Sin rollback drill
- [ ] Sin revisión de vulnerabilidades críticas runtime

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
1. Descargar datasets públicos crypto:
```bash
python rtlab_autotrader/scripts/download_crypto_binance_public.py --start-month 2024-01 --end-month 2024-06 --symbols BTCUSDT ETHUSDT
```
2. Verificar que exista manifest/dataset hash en `user_data/data/crypto/manifests/`
3. (Opcional) migrar/duplicar manifest a `user_data/datasets/binance_public/crypto/...` (el provider nuevo lo soporta)

### D. Correr un Mass Backtest de prueba
1. Abrir `Backtests` en el dashboard
2. Ir al panel **Research Masivo**
3. Seleccionar estrategias (pool research)
4. `dataset_source = auto` si ya descargaste datos reales, o `synthetic` para prueba rápida
5. Click en `Ejecutar Backtests Masivos`
6. Revisar:
   - progreso / logs
   - ranking robusto
   - KPIs por régimen
   - artifacts
7. Usar `Marcar candidato` (genera draft Opción B, no live)

### E. Safe Update (gates + canary + approve)
1. Ir a `Settings` → `Rollout / Gates`
2. Seleccionar `Run candidato` + baseline
3. `Start`
4. Evaluar fases (`paper_soak`, `testnet_soak`, `shadow`, `canaryXX`)
5. Verificar rollback automático si breach
6. `Approve` solo cuando corresponda (manual)

---

## 11) Confirmaciones clave (pedidas)

- **Research separado de runtime**: ✅
- **No performance-chasing**: ✅ (ventanas mínimas + gates + canary + rollback + Opción B; además guardrails/cooldowns en learning)
- **No auto-live**: ✅ (Opción B, approve humano requerido)
- **Mass Backtest no requiere APIs privadas**: ✅ (DATASET MODE recomendado)

