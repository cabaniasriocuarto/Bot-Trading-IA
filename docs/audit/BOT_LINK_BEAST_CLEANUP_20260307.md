# Bot Link + Beast + Limpieza Conservadora (2026-03-07)

## Objetivo del bloque
Cerrar el gap entre:
- UI bot-centrica ya visible en la rama
- trazabilidad historica exacta `run -> bot`
- confusion de `Modo Bestia deshabilitado`
- limpieza local sin borrar material ambiguo

## Evidencia funcional cerrada

### 1. Persistencia exacta `run -> bot`
Archivos:
- `rtlab_autotrader/rtlab_core/web/app.py`
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
- `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
- `rtlab_autotrader/tests/test_web_live_ready.py`

Resultado:
- Quick Backtest, Research Batch y Beast ahora reciben `bot_id` desde UI.
- El backend persiste `bot_id` en metadata/params/provenance/tags.
- El catalogo de runs preserva el bot historico aunque cambie el pool actual.

### 2. Beast validado localmente
- `GET /api/v1/research/beast/status` -> `200`
- `policy_state=enabled`
- `policy_enabled_declared=true`
- `policy_source_root=config/policies`
- `POST /api/v1/research/beast/start` con dataset real -> `200`, `run_id=BX-000001`

Lectura:
- el falso `deshabilitado` ya no corresponde a esta rama local;
- si sigue apareciendo en web, el problema es deploy/runtime viejo o entorno remoto sin estos commits.

### 3. Limpieza clasificada

#### Removido
Solo material claramente obsoleto/no versionado/enga?oso:
- `tmp/`
- `rtlab_autotrader/tmp_test_ud/`
- `rtlab_autotrader/user_data/backtests/` (`synthetic_seeded`)
- `rtlab_autotrader/user_data/research/mass_backtests/` vacio

#### Mantenido
Por falta de evidencia fuerte de obsolescencia:
- `rtlab_autotrader/user_data/console_api.sqlite3`
- `rtlab_autotrader/user_data/console_settings.json`
- `rtlab_autotrader/user_data/learning/`
- metadata local de estrategias

## Validacion
- `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py` -> PASS
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strict_strategy_id_flag or preserves_explicit_bot_link_after_pool_change or mass_backtest_start_forwards_bot_id or beast_start_accepts_orderflow_toggle or runs_batches_catalog_endpoints_smoke" -q` -> PASS
- `npm run build` en `rtlab_dashboard` -> PASS

## Riesgo residual abierto
- Falta persistencia fuerte `experience_episode -> bot_id`.
- Falta validar en deploy visible que la rama nueva este realmente arriba y no una version anterior.
