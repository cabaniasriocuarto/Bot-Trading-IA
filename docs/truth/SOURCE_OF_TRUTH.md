# SOURCE OF TRUTH (Estado Real del Proyecto)

Fecha de actualizacion: 2026-03-16

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
    - `live` visible solo como referencia, NO GO
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
  - restauraciÃ³n de shortlist al reabrir batch
  - sincronizaciÃ³n opcional con Comparador de Runs
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
