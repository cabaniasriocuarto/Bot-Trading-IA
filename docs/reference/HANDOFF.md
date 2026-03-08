# HANDOFF (RTLAB Strategy Console / Bot-Trading-IA)

## Objetivo del proyecto
Consolidar una consola de research + backtesting + operacion paper/testnet con gates de seguridad/riesgo, trazabilidad completa y politicas fail-closed, dejando LIVE real bloqueado hasta tener runtime de ejecucion real y controles operativos validados.

## Estado actual
### Funciona
- Backend desplegado en Railway (`testnet`) con auth, gates, diagnostico y persistencia.
- `G1..G8` en PASS en entorno testnet.
- Persistencia de storage resuelta: `G10_STORAGE_PERSISTENCE=PASS`.
- Seguridad endurecida: proxy token interno, rate limits login/API, scanner security en CI.
- Research/mass backtest con gates avanzados, costos y fundamentals por politica.
- Soak corto `20m` completado: `ok=80`, `errors=0`, `g10_pass=80`.
- Soak abreviado `1h` completado y aceptado como valedero para cierre de tramo:
  - `loops=240`, `ok=240`, `errors=0`, `g10_pass=240`.
- Soak extendido `6h` completado (evidencia final):
  - `loops=1440`, `ok=1440`, `errors=0`, `g10_pass=1440`.
- Backup/restore drill ejecutado con verificacion hash:
  - `artifacts/backup_restore_drill_20260302_234205.json` => `backup_ok=true`, `restore_ok=true`, `manifest_match=true`.
- Backtest strict mode adelantado: `strict_strategy_id=true` activa fail-closed para `strategy_id` no soportado.
- `/api/v1/bots` con debug de performance por etapas (`debug_perf.overview`) para aislar cuellos de botella en Railway.
- `/api/v1/bots` optimizado de forma incremental: KPIs se calculan solo para estrategias presentes en pools de bots (menos CPU cuando hay estrategias no asignadas).
- `/api/v1/bots` optimizado en carga de logs recientes: `logs.has_bot_ref` materializado + indice, con prefiltrado SQL (`has_bot_ref=1`) para reducir parseo de logs no relacionados.
- `/api/v1/bots` optimizado adicionalmente con tabla `log_bot_refs(log_id, bot_id)` para enrutar logs por bot target con join indexado (menos scan global de logs).
- Benchmark local actualizado de `/api/v1/bots` (post-optimización):
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260302_RERUN.md`
  - `100` bots, `200` requests, `warmup=30` -> `p95=55.513ms` (PASS `<300ms`).
- Diagnostico de integridad para kills:
  - `GET /api/v1/diagnostics/breaker-events` con estado `PASS/WARN/NO_DATA` y ratio de eventos `unknown_*` (global + ventana).
  - umbrales por ENV (`BREAKER_EVENTS_*`) para alertar drift de calidad de datos en `breaker_events`.
- Seguridad auth interna:
  - spoof de `x-rtlab-role/x-rtlab-user` sin proxy token valido deja evidencia en logs (`security_auth`, `warn`, `module=auth`).
  - throttle configurable por ENV `SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC`.
- Rotacion de proxy token interna:
  - soportado `INTERNAL_PROXY_TOKEN_PREVIOUS` + `INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT` para ventana de gracia durante rotacion.
  - endpoint admin de verificacion: `GET /api/v1/auth/internal-proxy/status` (sin exponer valor de tokens).
- Validacion no-live cerrada:
  - backend completo: `124 passed` (`python -m pytest rtlab_autotrader/tests -q`, desde raiz).
  - frontend tests: `11 passed` (`npm --prefix rtlab_dashboard run test`).
  - frontend lint: `0 errores, 0 warnings` (`npm --prefix rtlab_dashboard run lint`).

### Roto o pendiente
- `G9_RUNTIME_ENGINE_REAL` sigue en WARN (runtime simulado), por lo que LIVE real sigue bloqueado.
- Performance remota `/api/v1/bots` en Railway aun por encima de objetivo p95<300ms bajo carga alta.
- Verificacion de endpoints protegidos (`/api/v1/gates`, `/api/v1/diagnostics/breaker-events`, `/api/v1/auth/internal-proxy/status`) pendiente con token admin para evidencia final sin inferencias.

## Decisiones tomadas
- Opcion B activa: no auto-live, promocion con gates + aprobacion humana.
- Fuente canonica de gates: `config/policies/gates.yaml` (fallback knowledge solo si falta config).
- Fail-closed en seguridad y promocion.
- Storage persistente en Railway obligatorio para continuidad (`RTLAB_USER_DATA_DIR` sobre volumen).
- Flujo operativo de soak local: solo `20m` y `6h`.
- Criterio de cierre de este tramo (acordado): `20m + 1h` valedero; `6h` opcional.
- El soak `6h` se completo igualmente y ya tiene evidencia local en `artifacts/`.

## Restricciones y preferencias
- Sin refactor masivo; cambios incrementales y auditables.
- No exponer secretos ni hardcodear contraseñas.
- UI en español y errores/logs claros.
- `artifacts/` y outputs locales fuera de git.
- Decision operativa vigente (2026-03-03): LIVE real postergado hasta terminar cierre testnet/no-live y configurar APIs definitivas.

## Archivos clave
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/tests/test_web_live_ready.py`
- `config/policies/gates.yaml`
- `config/policies/risk_policy.yaml`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/CHANGELOG.md`
- `docs/truth/NEXT_STEPS.md`
- `scripts/security_scan.sh`
- `scripts/security_scan.ps1`
- `scripts/check_storage_persistence.py`
- `scripts/soak_testnet.ps1` (local)
- `scripts/start_soak_20m_background.ps1` (local)
- `scripts/start_soak_1h_background.ps1` (local)
- `scripts/start_soak_6h_background.ps1` (local)
- `scripts/resume_soak_6h_background.ps1` (local)
- `scripts/build_ops_snapshot.py` (local)
- `scripts/run_protected_ops_checks.ps1` (local)
- `scripts/backup_restore_drill.py` (local)
- `scripts/run_bots_benchmark_remote.ps1` (local)
- `scripts/run_remote_closeout_bundle.ps1` (local)

## Como correr / testear
### Gates + health
```powershell
$BASE="https://bot-trading-ia-production.up.railway.app"
$USER="Wadmin"
$PASS=Read-Host "ADMIN_PASSWORD"

$loginBody = @{ username=$USER; password=$PASS } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$BASE/api/v1/auth/login" -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.token)" }

$h = Invoke-RestMethod -Method Get -Uri "$BASE/api/v1/health"
$g = Invoke-RestMethod -Method Get -Uri "$BASE/api/v1/gates" -Headers $headers
$h.storage | Format-List *
$g.gates | Select-Object id,status,reason | Format-Table -AutoSize
```

### Soak test en background
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_soak_20m_background.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_soak_1h_background.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_soak_6h_background.ps1
```

### Reanudar soak 6h si se interrumpe
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/resume_soak_6h_background.ps1
```

### Seguimiento de soak
```powershell
Get-Content artifacts\soak_20m_bg_status.json
Get-Content artifacts\soak_6h_bg_status.json
Get-Content artifacts\soak_20m_bg_stderr.log -Tail 30
Get-Content artifacts\soak_6h_bg_stderr.log -Tail 30
Get-ChildItem .\artifacts\soak_20m_bg_*_DONE.txt, .\artifacts\soak_6h_bg_*_DONE.txt -ErrorAction SilentlyContinue
```

### Snapshot operativo (bloque 2 provisional/final)
```powershell
# Provisional (mientras 6h sigue corriendo):
python scripts/build_ops_snapshot.py --assume-soak-6h-from-20m

# Provisional (si se decide cerrar con soak de 1h):
python scripts/build_ops_snapshot.py --assume-soak-6h-from-1h

# Final (cuando cierre real 6h):
python scripts/build_ops_snapshot.py

# Final estricto (sin inferencias; exige endpoints protegidos):
python scripts/build_ops_snapshot.py --ask-password --require-protected --label ops_block2_snapshot_final
```

### Checks protegidos en 1 comando (password 1 sola vez)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_protected_ops_checks.ps1
```

### Security scan local (equivalente CI, Windows)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict
```

### Benchmark remoto `/api/v1/bots` (estricto, con password)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_bots_benchmark_remote.ps1
```

### Cierre remoto en 1 comando (checks protegidos + snapshot + benchmark)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_remote_closeout_bundle.ps1
```

## Proximos 10 pasos (checklist)
- [x] Completar soak corto (20m) y guardar resumen.
- [x] Completar soak abreviado (1h) y guardar resumen (criterio valedero de cierre).
- [x] Cierre operativo de tramo completado con criterio valedero `20m + 1h`.
- [x] Regresion no-live backend/frontend en verde (sin errores bloqueantes).
- [x] (Opcional) Completar soak extendido (6h) y anexar evidencia.
- [x] Revisar `GET /api/v1/diagnostics/breaker-events` y registrar resultado (workflow remoto protegido: `breaker_ok=true`, `breaker_status=NO_DATA`).
- [x] Correr `scripts/check_storage_persistence.py --require-persistent` (cobertura equivalente validada por workflow remoto protegido: `storage_persistent=true` + `g10_status=PASS`).
- [x] Verificar `G10` en PASS post-redeploy (workflow remoto protegido: `g10_status=PASS`).
- [x] Confirmar que `G9` sigue WARN (esperado) y LIVE queda bloqueado (workflow remoto protegido: `g9_status=WARN`).
- [x] Validar en deploy `GET /api/v1/auth/internal-proxy/status` durante rotacion de `INTERNAL_PROXY_TOKEN` (workflow remoto protegido: `internal_proxy_status_ok=true`).
- [x] Ejecutar backup + restore drill con scripts de runbook.
- [ ] Revalidar job `security` verde en CI (workflow root `/.github/workflows/security-ci.yml` agregado; pendiente push + corrida verde).
- [x] Preflight local de seguridad en Windows ejecutado (`security_scan.ps1 -Strict`): pip-audit runtime/research OK + gitleaks baseline-aware sin leaks.
- [x] Medir `/api/v1/bots` en remoto con carga controlada y guardar evidencia (benchmark remoto GitHub VM: PASS).
- [x] Re-run local de benchmark `/api/v1/bots` actualizado (`p95=55.513ms`, PASS `<300ms`) con 100 bots.
- [ ] Limpiar y commitear scripts/docs pendientes (sin artifacts).
- [ ] Definir plan tecnico para runtime real (criterio para subir `G9` a PASS) [POSTERGADO por decision operativa de priorizar testnet].

## Definicion de hecho (DoD)
- Testnet estable con `health.ok=true`, `G1..G8=PASS`, `G10=PASS`.
- Soaks de `20m`, `1h` y `6h` finalizados con evidencia JSONL y `*_DONE.txt`.
- Sin secretos en repo ni en logs versionados.
- `docs/truth/*` y este handoff actualizados con estado real.
- LIVE real sigue bloqueado hasta tener runtime real validado (`G9=PASS`).
