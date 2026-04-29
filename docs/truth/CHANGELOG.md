# CHANGELOG (Truth Layer)

## 2026-04-28

### RTLOPS-97 / RTLOPS-68 Slice 2 - order_intents_by_symbol read model
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega contrato read-only `rtlops97/v1`;
    - agrega `GET /api/v1/bots/{bot_id}/order-intents-by-symbol`;
    - deriva `order_intents_by_symbol` desde runtime, scope operativo heredado del bot y guardrails existentes;
    - mantiene Paper como `single_intent_safe` y no activa ejecucion multi-symbol por ciclo;
    - preserva `404` para `bot_id` inexistente en el endpoint read-only.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre un intent neto por simbolo;
    - cubre que dos estrategias sobre el mismo simbolo no duplican intents;
    - cubre bloqueo por simbolo fuera del scope operativo;
    - cubre runtime faltante sin `500`;
    - cubre que `bot_id` inexistente conserva `404`.
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops97'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops97 or rtlops68 or rtlops94" -q` -> PASS, 16 tests
- Limite honesto:
  - no cierra todo `RTLOPS-68`;
  - no abre `RTLOPS-69`;
  - no toca frontend, live console, Railway/Vercel, risk/scorecard/portfolio ni `Strategy Truth/Evidence`.

### RTLOPS-68 Slice 1 - net symbol decision intent foundation
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega resolucion de intent operativo desde `runtime.net_decision_by_symbol` cuando existe `active_bot_id`;
    - aplica `bot_operation_scope_gate(...)` antes de derivar el intent del bot;
    - bloquea fail-closed si el runtime del bot no esta listo;
    - expone trazabilidad del intent con `source=bot_runtime_net_decision`, `net_decision_key`, `decision_log_scope` y conteos de intents candidatos/suprimidos;
    - evita volver a una estrategia primaria paralela cuando hay bot activo.
    - corrige el review blocker de PR #46: un start sin `bot_id` limpia `active_bot_id` stale y queda en strategy-only/principal strategy mode.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre que dos estrategias elegibles para un mismo simbolo no generan intents duplicados;
    - cubre que el intent usa la estrategia seleccionada por simbolo y su `net_decision_key`;
    - cubre fail-closed cuando `runtime.guardrails.execution_ready=false`.
    - cubre start con bot, stop y start sin bot para verificar que no se conserva contexto bot stale.
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops68'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops68_runtime_order_intent_uses_net_decision_by_symbol_without_strategy_duplication or rtlops68_runtime_order_intent_fails_closed_when_bot_runtime_is_not_ready or bot_runtime_surface_is_canonical_and_traceable or bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope or rtlops94_operation_modes_inherit_bot_scope or rtlops94_operation_preflight_rejects_parallel_manual_symbol or rtlops94_operation_scope_blocks_empty_or_over_cap_scope or rtlops94_operation_preflight_rejects_invalid_mode_even_with_valid_environment or rtlops94_operation_scope_blocks_unresolved_max_active_symbols_without_typeerror" -q` -> PASS
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops68'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "rtlops68 or rtlops94" -q` -> PASS, 11 tests
  - `npm.cmd run typecheck` -> PASS
- Limite honesto:
  - no cierra todo `RTLOPS-68`;
  - no agrega ejecucion multi-order nueva;
  - no toca frontend, live console, Railway/Vercel ni dominios laterales.

### RTLOPS-94 - close review blockers on operation scope gate
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - valida `payload.mode` de forma explicita cuando viene enviado;
    - deja de usar `environment` como fallback si `mode` fue enviado pero es invalido;
    - responde fail-closed con `invalid_operation_mode:<valor>` en vez de bypassear `bot_operation_scope_gate(...)`;
    - valida `max_active_symbols` antes de comparaciones numericas;
    - si `max_active_symbols` no se resuelve a entero positivo, bloquea con `max_active_symbols_unresolved` en vez de devolver `TypeError`/500.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - agrega cobertura para `payload.mode` invalido con `environment` valido;
    - agrega cobertura para `max_active_symbols=None` sin `TypeError` y con bloqueo auditable.
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops94'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope or rtlops94_operation_modes_inherit_bot_scope or rtlops94_operation_preflight_rejects_parallel_manual_symbol or rtlops94_operation_scope_blocks_empty_or_over_cap_scope or rtlops94_operation_preflight_rejects_invalid_mode_even_with_valid_environment or rtlops94_operation_scope_blocks_unresolved_max_active_symbols_without_typeerror" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
- Limite honesto:
  - no amplía RTLOPS-94;
  - no toca frontend ni otros dominios;
  - solo cierra los 2 review blockers tecnicos de PR #45.

## 2026-04-26

### RTLOPS-94 - operation modes inherit bot Trading Universe Scope
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega `bot_operation_scope_gate(...)` sobre el contrato `rtlops96/v1`;
    - `POST /api/v1/execution/preflight` y `POST /api/v1/execution/orders` enriquecen la request con `operation_scope` y bloquean si el scope heredado del bot no es operable;
    - `POST /api/v1/bot/start` valida el scope del bot para `shadow`, `paper`, `testnet` y `live`;
    - bloquea fail-closed por `bot_id` faltante, scope vacio, cap excedido, `market_family`/`quote_asset` no resueltos y simbolos inelegibles;
    - rechaza simbolos manuales fuera del subset elegible del bot en vez de tratarlos como selector paralelo.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - renombra la surface a `Scope operativo heredado del bot`;
    - explicita que Shadow/Paper/Testnet/Live consumen el scope persistido por el bot;
    - muestra estado bloqueante/no bloqueante sin agregar controles de seleccion paralelos.
  - `rtlab_dashboard/src/lib/types.ts`
    - agrega `is_blocking` al tipo de scope eligibility.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - valida que `shadow`, `paper`, `testnet` y `live` heredan el scope del bot;
    - valida rechazo de simbolo manual fuera del scope;
    - valida bloqueo por bot ausente, over-cap e inelegibles.
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS
  - `$env:UV_PROJECT_ENVIRONMENT='.uv-rtlops94'; $env:UV_LINK_MODE='copy'; uv run --project rtlab_autotrader --with pytest pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope or rtlops94_operation_modes_inherit_bot_scope or rtlops94_operation_preflight_rejects_parallel_manual_symbol or rtlops94_operation_scope_blocks_empty_or_over_cap_scope" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run lint -- "src/app/(app)/execution/page.tsx" "src/lib/types.ts"` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no abre live console nueva;
  - no toca scorecard/risk/portfolio;
  - no rehace `strategy truth/evidence`;
  - no reabre research ni `RTLOPS-95`.

### RTLOPS-96 - fundación canónica runtime / universe scope / eligibility en Execution
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega el contrato `rtlops96/v1` en `GET /api/v1/bots/{bot_id}/scope-eligibility`;
    - agrega un carrier read-only que compone:
      - `multi_symbol`
      - `strategy_eligibility`
      - `runtime`
      - `lifecycle_operational`;
    - deja explícito:
      - `persisted_scope_owner=bot_registry`
      - `scope_source=bot_runtime_scope`
      - `strategy_role=consumer_only`
      - `operation_manual_selector_allowed=false`;
    - expone:
      - `market_family`
      - `quote_asset`
      - `symbols_configured`
      - `eligible_symbols`
      - `ineligible_symbols`
      - `blocking_reasons`
      - items por símbolo con `lifecycle_state` y `operational_status`.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - suma una card mínima `Runtime scope / eligibility`;
    - muestra ownership, scope efectivo, subset elegible/inelegible y bloqueos sin abrir selector manual paralelo.
  - `rtlab_dashboard/src/lib/types.ts`
    - agrega el contrato tipado `BotScopeEligibility*`.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el nuevo carrier canónico y su presencia en el contract surface del bot registry.
- Límite honesto:
  - no cierra toda `RTLOPS-94`;
  - no agrega UX operativa final completa;
  - no toca scorecard/risk ni `strategy truth/evidence`.
- Siguiente paso exacto:
  - continuar `RTLOPS-94` sobre este carrier canónico, sin volver a abrir selectors paralelos.

## 2026-04-25

### RTLOPS-93 - selector reusable Bot vs Estrategia + Trading Universe Scope auditable en Batch/Beast
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - extiende research con carrier canonico:
      - `entity_type`
      - `entity_id`
      - `universe_name`
      - `symbols[]`;
    - agrega resolucion backend-first de `Trading Universe Scope` para research;
    - valida:
      - scope del bot
      - pertenencia al pool del bot
      - `universe_name` portable en crypto
      - limite de simbolos
      - simbolos elegibles / no elegibles;
    - integra ese contrato al preflight, start de `Research Batch` y start de `Beast`;
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
    - ejecuta research multi-simbolo real por `variantes x folds x simbolos`;
    - agrega fold summaries agregados sin perder trazabilidad por simbolo;
    - extiende `dataset_preflight` con scope research, `dataset_hashes`, manifests y bootstrap por simbolo;
  - `rtlab_autotrader/tests/test_web_live_ready.py`
    - cubre:
      - `entity_type=bot`
      - `entity_type=strategy`
      - payload multi-simbolo research
      - bloqueo por simbolos fuera del universe portable;
  - `rtlab_autotrader/tests/test_mass_backtest_engine.py`
    - sigue validando la ejecucion del motor con el slice actualizado.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - agrega selector explicito `Correr Bot` / `Correr Estrategias`;
    - agrega `Trading Universe Scope` reusable para `Research Batch` y `Beast`;
    - expone busqueda, chips, contador y seleccion multi-simbolo visible;
    - usa el mismo carrier backend del preflight y de los starts de batch/beast;
    - muestra entidad, scope source, universe, quote, request/effective, elegibles, no elegibles y bloqueos del preflight.
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "research_mass_backtest_start_rejects_missing_dataset or research_dataset_preflight_ready_payload or research_dataset_preflight_missing_blocks_cleanly or research_dataset_preflight_blocks_synthetic_even_with_real_dataset or research_dataset_preflight_bot_scope_multi_symbol_payload or research_dataset_preflight_strategy_scope_blocks_symbols_outside_universe or research_mass_backtest_start_forwards_bot_id or research_beast_endpoints_smoke or research_beast_start_rejects_missing_dataset or research_beast_start_accepts_orderflow_toggle" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> PASS en la rama limpia reconstruida desde `main`;
  - el `FAIL` observado antes no reprodujo como error del codigo del slice y quedo explicado por artefactos locales de `.next`/espacio en disco en la worktree stacked.
- Decision de integracion:
  - `44a023e` se conserva completo en este frente;
  - su contenido documental coincide con el slice implementado y sirve como preflight arquitectonico inmediato de `RTLOPS-93`, sin abrir `RTLOPS-94`.
- Limites honestos:
  - no abre `RTLOPS-94`;
  - no toca `Shadow / Testnet / Live`;
  - no abre CRUD global de universos;
  - no vuelve multi-simbolo a `Quick`.
- Siguiente paso exacto:
  - abrir `RTLOPS-94` para reusar el `Trading Universe Scope` del bot en operacion/deploy sin mezclar research con live.

### Preflight de arquitectura multi-simbolo - entidad, scope y modos
- Decision real asentada en repo + docs/truth + Linear:
  - el programa ya tiene una base canonica multi-simbolo por bot en el `Bot Registry`;
  - `Backtests` sigue usando `symbol` puntual para `Research Batch/Beast`;
  - no existe hoy una entidad CRUD separada de `symbol set` reusable.
- Decision canonica resultante:
  - separar:
    - `Entidad`
      - `Bot`
      - `Estrategia`
    - `Trading Universe Scope`
    - `Modo`;
  - no abrir primero un `symbol set registry` global;
  - si abrir un contrato canonico reusable de `Trading Universe Scope`:
    - persistido en `Bot` para operacion;
    - reusable en research como scope heredado o manual.
- Reglas cerradas para el siguiente frente:
  - `Quick` sigue single-symbol;
  - `Research Batch` y `Beast` deben compartir el mismo scope multi-simbolo y el mismo preflight;
  - `Shadow / Paper / Testnet / Live` deben reutilizar el scope persistido del bot;
  - cap inicial de hasta `12` simbolos, una sola `market_family`, una sola `quote_asset` y sin pruning silencioso en v1.
- Linear alineada:
  - `RTLOPS-91`
  - `RTLOPS-92`
  - `RTLOPS-93`
  - `RTLOPS-94`
- Siguiente paso exacto:
  - programar `RTLOPS-93` como primer bloque de implementacion;
  - dejar `RTLOPS-94` para el reuso operativo posterior.

### RTLOPS-90 - reordenamiento UX Backtests sin refactor masivo
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - reordena la surface principal de `Backtests` por modos reales de trabajo;
    - deja arriba:
      - `Quick`
      - `Backtests / Runs`
      - `Comparador Profesional`
      - `Research Batch`
      - `Beast / Infra`;
    - baja de jerarquia:
      - `Research Funnel y Trial Ledger`
      - `Detalle de Corrida (Strategy Tester)`
      - `Quick Backtest Legacy (Deprecado)`;
    - separa `Beast / Infra` del bloque principal de `Research Batch`;
    - mueve el disparador de `Modo Bestia` al bloque propio de infra;
    - mantiene la copy en espanol y evita vender legacy/auditoria como flujo principal.
- Dependencias backend reusadas:
  - el frontend sigue apoyado en el preflight canonico de `RTLOPS-89`;
  - no se tocan:
    - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
    - `rtlab_autotrader/rtlab_core/web/app.py`
    - contratos de dataset/prereqs ya cerrados.
- Tests corridos:
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no hay refactor masivo;
  - no hay backend nuevo;
  - `Research Funnel` y `Strategy Tester` siguen existiendo, pero en rol secundario;
  - no se reabre `RTLOPS-89`.
- Siguiente paso exacto:
  - la revalidacion con repo + `docs/truth` + Linear ya deja a `RTLOPS-87` cerrada administrativamente;
  - no corresponde abrir otro bloque de producto en `Backtests` por defecto;
  - si queda un gap nuevo real, abrir solo un microbloque UX chico sobre surfaces secundarias.

### RTLOPS-89 - preflight canonico de dataset/prerequisitos para Batch/Beast
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
    - agrega `MassBacktestCoordinator.dataset_preflight(...)` como contrato canonico minimo y auditable;
    - reutiliza `build_data_provider(...)`, manifiestos reales y `_preflight_dataset_ready(...)` sin duplicar dominio;
    - canoniza `market_family`, `dataset_status`, `dataset_source_type`, `can_run_batch`, `can_run_beast`, `blocking_reason` y listas `eligible/ineligible`;
    - mantiene fail-closed el start de Batch/Beast sobre la misma evaluacion;
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega `POST /api/v1/research/dataset-preflight` como surface minima reutilizable por frontend;
    - evita que `Backtests` tenga que deducir readiness desde heuristicas locales.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - consume el preflight canonico;
    - reemplaza heuristicas locales de dataset por `dataset_status`, `dataset_source_type`, `can_run_batch`, `can_run_beast` y `blocking_reason`;
    - muestra bootstrap requerido, simbolos elegibles/no elegibles y bloqueo por `synthetic` de forma explicita;
    - mantiene la misma surface general sin refactor masivo ni redisenio completo.
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_live_ready.py`
    - agrega cobertura para:
      - preflight `ready`
      - preflight `missing`
      - preflight `synthetic_blocked`
      - payload canonico minimo del endpoint.
- Tests corridos:
  - `uv run --project rtlab_autotrader python -m py_compile rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
  - `uv run --project rtlab_autotrader --extra dev python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "dataset_preflight or research_mass_backtest_start_rejects_missing_dataset or research_beast_start_rejects_missing_dataset or research_beast_endpoints_smoke" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no se abre `RTLOPS-90`;
  - no se reordena todavia la UX completa de `Backtests`;
  - no se abre una API transversal nueva;
  - no se agregan dominios laterales fuera de dataset prereqs.
- Siguiente paso exacto:
  - `RTLOPS-90 - Reordenamiento UX Backtests sin refactor masivo`.

## 2026-04-24

### RTLOPS-28 - cierre administrativo final sin split
- Revalidacion final ejecutada con prioridad de evidencia:
  - repo real
  - `docs/truth`
  - Linear
- Estado canonico confirmado:
  - `rtlops28/v1` ya habia absorbido el alcance tecnico real de la issue:
    - `drift_not_blocking`
    - `allow_review / hold / block`
    - `missingness`
    - `recommended_actions[]`
  - no quedo sostenido un gap tecnico vivo de `PSI/KS` dentro de `RTLOPS-28`;
  - no se abrio split nuevo.
- Sync administrativo aplicado:
  - `RTLOPS-28` queda cerrada en Linear (`Done`);
  - `docs/truth` pasan a reflejar ese cierre canonico;
  - cualquier `PSI/KS` futuro debe abrirse como issue nueva, chica y precisa.
- Siguiente paso exacto:
  - abrir un preflight limpio para decidir el dominio siguiente del programa, ya fuera de `RTLOPS-28`.

## 2026-04-22

### RTLRESE-32 - validacion independiente real por run
- Cambio real aplicado en backend/catalogo minimo:
  - `rtlab_autotrader/rtlab_core/backtest/independent_validation.py`
    - agrega el builder canonico de `rtlrese32/v1`;
    - carga thresholds reales desde `config/policies/gates.yaml`;
    - clasifica `PASS / REVIEW / REJECT`, `rejection_reasons`, `review_reasons` y `promotion_stage_eligible`;
  - `rtlab_autotrader/rtlab_core/backtest/catalog_db.py`
    - persiste `independent_validation_json` en `backtest_runs`;
    - expone `independent_validation` al leer corridas;
    - agrega patch minimo para backfill del contrato persistido;
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - genera `strategy_config_hash` reproducible para quick backtests reales;
    - persiste `independent_validation` en corridas simples;
    - integra la validacion independiente a `validate_promotion` con fail-closed explicito;
    - expone metrica derivada en `GET /api/v1/runs/{run_id}` solo como lectura auditada, sin convertirla en evidencia formal de promocion;
  - `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`
    - persiste `independent_validation_json` tambien en hijos de backtests masivos;
  - `rtlab_autotrader/rtlab_core/learning/brain.py`
    - agrega `probabilistic_sharpe_ratio`;
  - `rtlab_autotrader/rtlab_core/learning/experience_store.py`
    - reutiliza el helper canonico de `PSR`.
- Reuso canonico de backlog:
  - `RTLRESE-5` absorbida via `PBO/CSCV` trazable por run;
  - `RTLRESE-6` absorbida via `PSR/DSR`, `review_reasons`, `rejection_reasons` y `promotion_stage_eligible`;
  - `RTLRESE-4` no se toca porque no aparecio un gap nuevo de provenance persistente.
- Tests corridos:
  - `pytest rtlab_autotrader/tests/test_backtest_catalog_db.py -q` -> PASS
  - `pytest rtlab_autotrader/tests/test_web_live_ready.py -k "independent_validation_contract or independent_validation_not_reusable" -q` -> PASS
  - `pytest rtlab_autotrader/tests/test_rollout_safe_update.py -k "gate_evaluator or compare_engine or rollout_manager" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - `pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` sigue mostrando un FAIL preexistente del seed-run de rollout API;
  - ese fail ya reproduce tambien en `origin/main`, asi que no lo abre `RTLRESE-32`;
  - el bloque no abre `live console`, drift, scorecard, portfolio risk ni governance IA como dominio separado.
- Siguiente paso exacto:
  - abrir `RTLOPS-28` como drift layer minimo y auditable.

## 2026-04-21

### Preflight posterior a RTLOPS-84 - cadena minima cerrada
- Revalidacion real:
  - `rtlops81/v1` ya tiene tres consumidores reales y auditables en `execution/page.tsx`, `strategies/page.tsx` y `backtests/page.tsx`
  - no aparece una cuarta surface natural comparable en el repo para seguir la cadena minima de `lifecycle_operational`
  - por lo tanto, la cadena de consumidores minimos queda cerrada en `RTLOPS-84`
- Dominio siguiente:
  - Linear muestra `RTLOPS-69` (`live console`) como backlog real del mismo proyecto
  - pero repo + `docs/truth` todavia no sostienen con honestidad que ese sea el siguiente dominio correcto del programa
  - tampoco queda canonizado todavia otro dominio siguiente
- Regla canonica:
  - no se inventa `RTLOPS-85`
  - el dominio siguiente queda fail-closed hasta nueva canonizacion explicita

### RTLOPS-84 - tercer consumidor minimo de lifecycle_operational
- Cambio real aplicado en frontend minimo:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - consume `selectedMassBot.lifecycle_operational` como tercera surface minima operativa distinta de `execution/page.tsx` y `strategies/page.tsx`
    - expone el subset operativo del universo del bot con conteos `allowed`, `rejected`, `progressing`, `paused` y simbolos sin dato
    - deja visible trazabilidad minima por simbolo con `runtime_symbol_id`, `selected_strategy_id` e issues canonicos
    - mantiene el bloque en modo lectura y no agrega acciones operativas
  - `rtlab_dashboard/src/lib/lifecycle-operational.ts`
    - agrega `summarizeLifecycleOperationalUniverse` para resumir el contrato sobre el universo del bot
  - `rtlab_dashboard/src/lib/lifecycle-operational.test.ts`
    - cubre el resumen canonico del tercer consumidor minimo en `Backtests`
- Tests corridos:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no se abre `live console`
  - no se abre LIVE lateral
  - no se abre lifecycle completo `backtest/shadow/paper/testnet/live`
  - no se cambia el contrato backend ya canonico
- Siguiente paso exacto:
  - abrir un preflight fail-closed posterior a `RTLOPS-84`

### Canonizacion posterior a RTLOPS-83
- Revalidacion real:
  - repo + docs/truth + Linear confirman el cierre de `RTLOPS-83`
  - `rtlops81/v1` ya deja dos consumidores reales de `lifecycle_operational`
  - no existia todavia una sucesora explicita posterior a `RTLOPS-83`
- Canonizacion explicita:
  - por decision humana del usuario se fija `RTLOPS-84`:
    - `Bot Multi-Symbol — tercer consumidor mínimo de lifecycle_operational`
  - el scope minimo queda acotado a una tercera surface minima operativa en `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
  - se mantienen fuera `live console`, LIVE lateral, lifecycle completo entre entornos y refactor transversal
- Sync administrativo:
  - se crea `RTLOPS-84` en Linear
  - queda en `Backlog` como hija explicita de `RTLOPS-68`
- Documentos actualizados:
  - `docs/truth/NEXT_STEPS.md`
  - `docs/truth/SOURCE_OF_TRUTH.md`
- Limites honestos:
  - este bloque no implementa producto
  - no toca `main`
  - solo canoniza la sucesora posterior a `RTLOPS-83`

### RTLOPS-83 - segundo consumidor minimo de lifecycle_operational
- Cambio real aplicado en frontend minimo:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - consume `bot.lifecycle_operational` como segunda surface minima operativa distinta de `execution/page.tsx`
    - expone `allowed_trade_symbols`, `rejected_trade_symbols`, `progressing_symbols` y `lifecycle_operational_by_symbol`
    - muestra trazabilidad minima por simbolo con `runtime_symbol_id`, `selection_key` y `net_decision_key`
    - deja visible `base_lifecycle_state`, `operational_status`, `lifecycle_state` y errores por simbolo
    - deriva a `Execution` para overrides puntuales sin duplicar el primer consumidor
  - `rtlab_dashboard/src/lib/lifecycle-operational.ts`
    - agrega helpers puros para resumir y ordenar el contrato `lifecycle_operational`
  - `rtlab_dashboard/src/lib/lifecycle-operational.test.ts`
    - cubre el resumen canonico del segundo consumidor minimo
- Tests corridos:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no se abre `live console`
  - no se abre LIVE lateral
  - no se abre lifecycle completo `backtest/shadow/paper/testnet/live`
  - no se cambia el contrato backend ya canonico

### Canonizacion posterior a RTLOPS-82
- Revalidacion real:
  - repo + docs/truth + Linear confirman el cierre de `RTLOPS-82`
  - `rtlops81/v1` ya deja un primer consumidor real de `lifecycle_operational`
  - no existia todavia una sucesora explicita posterior a `RTLOPS-82`
- Canonizacion explicita:
  - por decision humana del usuario se fija `RTLOPS-83`:
    - `Bot Multi-Symbol — segundo consumidor mínimo de lifecycle_operational`
  - el scope minimo queda acotado a una segunda surface minima operativa sobre `rtlops81/v1`, distinta de `execution/page.tsx`
  - se mantienen fuera `live console`, LIVE lateral, lifecycle completo entre entornos y refactor transversal
- Sync administrativo:
  - se crea `RTLOPS-83` en Linear
  - queda en `Backlog` como hija explicita de `RTLOPS-68`
- Documentos actualizados:
  - `docs/truth/NEXT_STEPS.md`
  - `docs/truth/SOURCE_OF_TRUTH.md`
- Limites honestos:
  - este bloque no implementa producto
  - no toca `main`
  - solo canoniza la sucesora posterior a `RTLOPS-82`

### RTLOPS-82 - primer consumidor real de lifecycle_operational
- Cambio real aplicado en frontend mínimo:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - consume `GET /api/v1/bots/{bot_id}/lifecycle-operational`
    - expone una surface minima operativa en el bloque del bot seleccionado
    - muestra `allowed_trade_symbols`, `rejected_trade_symbols`, `progressing_symbols`, `blocked_symbols`
    - muestra trazabilidad minima por simbolo con `runtime_symbol_id`, `selection_key` y `net_decision_key`
    - consume `PATCH /api/v1/bots/{bot_id}/lifecycle-operational` para pausar/reanudar simbolos sin abrir otro dominio
  - `rtlab_dashboard/src/lib/execution-bots.ts`
    - agrega helpers minimos para derivar la accion operativa valida por simbolo
    - normaliza el patch para persistir solo overrides `paused`
  - `rtlab_dashboard/src/lib/execution-bots.test.ts`
    - cubre el wiring minimo del primer consumidor real
- Tests corridos:
  - `npm.cmd test -- --run src/lib/execution-bots.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - no se abre `live console`
  - no se abre LIVE lateral
  - no se abre lifecycle completo `backtest/shadow/paper/testnet/live`
  - no se introduce un scheduler/engine nuevo

### Canonizacion posterior a RTLOPS-81
- Revalidacion real:
  - repo + docs/truth + Linear confirman el cierre de `RTLOPS-81`
  - `rtlops81/v1` ya deja `lifecycle_operational` como contrato valido del frente
  - no existia todavia una sucesora explicita posterior a `RTLOPS-81`
- Canonizacion explicita:
  - por decision humana del usuario se fija `RTLOPS-82`:
    - `Bot Multi-Symbol — primer consumidor real de lifecycle_operational`
  - el scope minimo queda acotado a una surface minima operativa sobre `rtlops81/v1`
  - se mantienen fuera `live console`, LIVE lateral, lifecycle completo entre entornos y refactor transversal
- Sync administrativo:
  - se crea `RTLOPS-82` en Linear
  - queda en `Backlog` como hija explicita de `RTLOPS-68`
- Documentos actualizados:
  - `docs/truth/NEXT_STEPS.md`
  - `docs/truth/SOURCE_OF_TRUTH.md`
- Limites honestos:
  - este bloque no implementa producto
  - no toca `main`
  - solo canoniza la sucesora posterior a `RTLOPS-81`

## 2026-04-20

### RTLOPS-81 - contratos minimos de lifecycle operativo por simbolo
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega el submodelo `lifecycle_operational`
    - agrega `GET /api/v1/bots/{bot_id}/lifecycle-operational`
    - agrega `PATCH /api/v1/bots/{bot_id}/lifecycle-operational`
    - eleva el contrato del Bot Registry a `rtlops81/v1`
    - persiste solo `lifecycle_operational_by_symbol` como storage minimo
    - mantiene `active` como default implicito y solo persiste overrides `paused`
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el contrato `rtlops81/v1`
    - cubre el endpoint dedicado de lifecycle operativo
    - cubre la pausa operativa de simbolos permitidos sin abrir ejecucion LIVE lateral
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `lifecycle_operational`, `lifecycle_operational_path` y el contrato extendido del registry
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza el fixture del contrato canonico a `rtlops81/v1`
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle_operational or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes; PASS al rerun despues de `build`
- Limites honestos:
  - no se abre `live console`
  - no se abre ejecucion LIVE lateral por simbolo
  - no se abre lifecycle completo `backtest/shadow/paper/testnet/live`
  - no se introduce un scheduler o engine nuevo fuera del contrato minimo

### Preflight posterior a RTLOPS-80 - sucesora canonizada
- Revalidación real:
  - repo + docs/truth + Linear confirman el cierre de `RTLOPS-80`
  - `rtlops80/v1` ya deja un `lifecycle` mínimo derivado y auditable
  - el contrato actual sigue con `storage_fields=[]`, así que el gap mínimo restante no es visual ni cross-environment sino de lifecycle operativo por símbolo
  - `RTLOPS-69` (`live console`) y `RTLRESE-25` (lifecycle completo entre entornos) se mantienen fuera por sobrealcance
- Sync administrativo:
  - se crea `RTLOPS-81` en Linear:
    - `Bot Multi-Symbol — contratos mínimos de lifecycle operativo por símbolo`
  - queda en `Backlog` como hija explícita de `RTLOPS-68`
- Siguiente paso exacto fijado:
  - abrir `RTLOPS-81`
  - resolver solo shape mínimo + storage/API mínimo del lifecycle operativo por símbolo sobre `rtlops80/v1`
  - mantener fuera `live console`, ejecución LIVE lateral, lifecycle completo entre entornos y refactor transversal
- Límites honestos:
  - este bloque no implementa producto
  - no toca `main`
  - solo canoniza la sucesora posterior a `RTLOPS-80`

### RTLOPS-80 - lifecycle minimo multi-symbol
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega el submodelo derivado `lifecycle`
    - agrega `GET /api/v1/bots/{bot_id}/lifecycle`
    - eleva el contrato del Bot Registry a `rtlops80/v1`
    - consume `policy_state.mode/status` y `runtime.guardrails.execution_ready`
    - progresa solo `allowed_trade_symbols`
    - deja `rejected_trade_symbols` fuera de progresion con motivo visible
    - reutiliza la trazabilidad por simbolo ya canonica (`runtime_symbol_id`, `selection_key`, `net_decision_key`, `decision_log_scope`)
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el contrato `rtlops80/v1`
    - cubre el endpoint dedicado de lifecycle
    - cubre progresion minima de simbolos permitidos
    - cubre simbolos rechazados por priorizacion
    - cubre bloqueo explicito cuando `policy_state.status=paused`
    - cubre bloqueo explicito cuando `runtime.guardrails.execution_ready=false`
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `lifecycle`, `lifecycle_path` y el contrato extendido del registry
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza el fixture del contrato canonico a `rtlops80/v1`
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`
- Limites honestos:
  - no se abre `live console`
  - no se abre ejecucion LIVE lateral por simbolo
  - no se abre lifecycle completo `backtest/shadow/paper/testnet/live`
  - no se introduce un scheduler o engine nuevo fuera del subset ya canonico

### Preflight posterior a RTLOPS-79 - lifecycle mínimo multi-symbol
- Revalidación real:
  - repo + docs/truth confirman que `RTLOPS-79` ya dejó canonizado el subset ejecutable bajo caps sobre `rtlops77/v1`
  - el contrato vigente ya expone `guardrails.execution_ready`, `allowed_trade_symbols`, `rejected_trade_symbols` y trazabilidad estable por símbolo
  - `policy_state` ya aporta `mode/status` mínimo del bot para que el siguiente slice consuma esa base sin abrir live console
- Sync administrativo:
  - `RTLOPS-79` pasó a `Done` en Linear
  - se dejó comentario con evidencia real repo/docs/tests
  - no aparece todavía una hija explícita para `lifecycle mínimo multi-symbol`
  - `RTLRESE-25` se mantiene fuera como issue más grande de lifecycle completo
- Siguiente paso exacto fijado:
  - abrir implementación mínima de lifecycle multi-symbol consumiendo el subset ejecutable ya canonizado
  - mantener fuera live console, ejecución LIVE lateral, lifecycle completo entre entornos y refactor transversal
- Límites honestos:
  - este bloque no implementa lifecycle todavía
  - no toca producto
  - solo fija el siguiente slice correcto y alinea la verdad documental/administrativa

### RTLOPS-79 - subset ejecutable y priorización determinística bajo caps
- Cambio real aplicado en backend/API minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - mantiene el contrato sobre `rtlops77/v1`
    - prioriza el subset ejecutable por orden canonico de `symbols` cuando `trade_decisions_count > max_live_symbols`
    - deja `guardrails.status=warning` cuando la priorizacion resuelve el overflow sin incoherencia de configuracion
    - mantiene `live_cap_exceeds_max_positions` como bloqueo fail-closed
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el subset permitido vs rechazado por priorizacion
    - cubre el criterio deterministico `symbol_order`
    - revalida que `max_live_symbols > max_positions` sigue en `error`
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`
- Limites honestos:
  - no se abre lifecycle
  - no se abre live console
  - no se abre ejecucion LIVE lateral
  - no se introduce un scheduler o engine nuevo fuera del contrato runtime ya canonico

### Preflight posterior a RTLOPS-77 - sucesora canonizada
- Verdad documental alineada:
  - repo + docs/truth + Linear revalidados sobre la punta real que cierra `RTLOPS-77`
  - se fija como sucesora explicita `RTLOPS-79`:
    - `Bot Multi-Symbol — subset ejecutable y priorización determinística bajo caps`
  - se descarta abrir `lifecycle` como siguiente bloque inmediato porque hoy mezclaría de más la priorización bajo caps con el lifecycle operativo
- Documentos actualizados:
  - `docs/truth/NEXT_STEPS.md`
  - `docs/truth/SOURCE_OF_TRUTH.md`
- Limites honestos:
  - no se implementa producto en este bloque
  - no se abre lifecycle
  - no se abre live console

### RTLOPS-77 - guardrails, caps y rechazos de configuracion
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - eleva el contrato runtime y del Bot Registry a `rtlops77/v1`
    - agrega la capa explicita `caps + guardrails` sobre el runtime multi-symbol derivado
    - rechaza configuraciones incoherentes cuando `max_live_symbols > max_positions`
    - deja fail-closed el runtime cuando el neto por simbolo excede el cap live o cuando reaparece drift legacy entre `max_live_symbols` y `max_positions`
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el contrato `rtlops77/v1`
    - cubre rechazos de configuracion incoherente en create/patch multi-symbol
    - cubre guardrails fail-closed cuando el runtime deriva mas decisiones `trade` que el cap live
    - cubre drift legacy donde `max_live_symbols` supera `max_positions`
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - agrega rechazo frontend coherente para `max_live_symbols > max_positions`
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `runtime.caps` y `runtime.guardrails`
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza el fixture canonico a `rtlops77/v1`
    - cubre los nuevos reason codes y fields de runtime
- Tests corridos:
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - `RTLOPS-77` no abre lifecycle ni live console
  - no agrega ejecucion remota LIVE lateral por simbolo
  - no introduce una politica de priorizacion/seleccion de subset cuando el runtime excede caps: falla cerrado y deja el rechazo explicito
  - `next build` sigue emitiendo warnings no bloqueantes de chart sizing ya visibles en la base, sin romper el resultado `PASS`

### RTLOPS-76 - contratos minimos de runtime, storage y API
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega el submodelo derivado `runtime`
    - agrega `GET /api/v1/bots/{bot_id}/runtime`
    - eleva el contrato del Bot Registry a `rtlops76/v1`
    - expone referencias minimas de storage/API para colgar el runtime multi-symbol sobre la verdad ya canonica de:
      - `RTLOPS-72`
      - `RTLOPS-73`
      - `RTLOPS-74`
      - `RTLOPS-75`
    - mantiene fail-closed el contrato runtime cuando `signal_consolidation` no queda valida
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el contrato `rtlops76/v1`
    - cubre la surface `GET /api/v1/bots/{bot_id}/runtime`
    - cubre trazabilidad minima por simbolo (`runtime_symbol_id`, `selection_key`, `net_decision_key`, `decision_log_scope`)
    - cubre el fail-closed cuando la consolidacion upstream no permite exponer decision neta por simbolo
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `runtime`, `runtime_path` y la extension del contrato canonico del registry
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza el fixture del contrato canonico a `rtlops76/v1`
- Tests corridos:
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Limites honestos:
  - `RTLOPS-76` no abre lifecycle ni live console
  - no agrega ejecucion remota real por simbolo
  - no abre `RTLOPS-77`
  - `next build` sigue emitiendo warnings no bloqueantes de chart sizing ya visibles en la base, sin romper el resultado `PASS`

## 2026-04-18

### Microbloque de seguridad - desbloqueo de `Security CI` en PR #35
- Cambio real aplicado en dependencias:
  - `requirements-runtime.txt`
    - sube `python-multipart` de `0.0.22` a `0.0.26` para cubrir el advisory `CVE-2026-40347` / `GHSA-mj87-hwqh-73pj`
  - `requirements-research.txt`
    - no requiere edicion directa; sigue heredando el runtime mediante `-r requirements-runtime.txt`
  - `rtlab_autotrader/uv.lock`
    - se regenera de forma minima para reflejar `python-multipart==0.0.26` en el lock del backend
- Validacion real ejecutada:
  - `uv lock -P python-multipart==0.0.26` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`14 passed`)
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL en frio por caveat preexistente de `.next/types` faltantes; `npm.cmd run typecheck` post-build -> PASS
  - validacion puntual del paquete corregido: `uvx pip-audit -r <tmp python-multipart==0.0.26>` -> PASS (`No known vulnerabilities found`)
- Limites honestos:
  - `scripts/security_scan.ps1 -Strict` no pudo reproducirse localmente porque faltan `pip-audit` y `gitleaks` en `PATH`
  - `uvx pip-audit -r requirements-runtime.txt` y `-r requirements-research.txt` no cerraron localmente por resolucion/metadata de `numpy` en Windows sin toolchain C; el desbloqueo definitivo del gate queda pendiente del rerun server-side de GitHub Actions
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-76`
  - producto funcional
  - Railway/Vercel prod

### RTLOPS-75 - consolidacion de señales y decision neta por simbolo
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega el submodelo derivado `signal_consolidation`
    - agrega `GET /api/v1/bots/{bot_id}/signal-consolidation`
    - agrega `net_decision_by_symbol` con trazabilidad minima de inputs por simbolo
    - eleva el contrato del registry a `rtlops75/v1`
    - deja fail-closed la consolidacion cuando la seleccion previa o la metadata de la estrategia no permiten derivar una decision coherente
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre el contrato `rtlops75/v1`
    - cubre la decision neta por simbolo y la trazabilidad de inputs
    - cubre el fail-closed cuando la estrategia seleccionada no expone una señal canónica derivable
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `signal_consolidation`, `net_decision_by_symbol` y el contrato extendido del registry
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza el fixture del contrato canonico a `rtlops75/v1`
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - agrega una surface minima de lectura para ver decision neta, inputs participantes y acuerdo/conflicto por simbolo
- Tests corridos:
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`14 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run lint -- "src/app/(app)/strategies/page.tsx"` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Observacion operativa honesta:
  - el primer `build` volvio a fallar por `EPERM` al limpiar `.next` dentro de OneDrive;
  - se resolvio con limpieza segura de `.next` (solo artefacto generado no trackeado), sin tocar archivos tracked del repo.
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - ejecucion remota real por estrategia
  - subcuentas

### RTLOPS-74 - seleccion de estrategia por simbolo
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega persistencia canonica `strategy_selection_by_symbol`
    - agrega `GET/PATCH /api/v1/bots/{bot_id}/strategy-selection`
    - agrega resolucion deterministica `selected_strategy_by_symbol`
    - agrega criterios y reason codes canonicos del contrato `rtlops74/v1`
    - endurece invalidacion fail-closed cuando un mapping explicito deja de ser elegible
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre contrato `rtlops74/v1`
    - cubre surface dedicada de seleccion
    - cubre criterios `explicit` y `single_eligible`
    - cubre invalidaciones fail-closed y guard de archivado
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `strategy_selection` y el contrato extendido del registry
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza fixture del contrato canonico a `rtlops74/v1`
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - agrega surface minima para ver/editar seleccion por simbolo dentro del mismo panel de registry
- Tests corridos:
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`12 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run lint -- "src/app/(app)/strategies/page.tsx"` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- Observacion operativa honesta:
  - el primer `build` fallo por `EPERM` al limpiar `.next` dentro de OneDrive;
  - se resolvio con limpieza segura de `.next` (solo artefacto generado no trackeado), sin tocar archivos del repo.
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-75`
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - execution net/consolidation

### Microbloque tecnico - canonizacion del type-check frio del dashboard
- Cambio real aplicado en tooling/documentacion:
  - `rtlab_dashboard/package.json`
    - agrega script canónico `typecheck: tsc --noEmit --incremental false`
  - `docs/truth/SOURCE_OF_TRUTH.md`
  - `docs/truth/CHANGELOG.md`
  - `docs/truth/NEXT_STEPS.md`
- Comandos validados con reproduccion real:
  - `npm.cmd run typecheck` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit --incremental false` en frio -> PASS
  - `npm.cmd exec next -- typegen` -> PASS
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
- Definicion operativa de `en frio`:
  - sin `.next`
  - sin `tsconfig.tsbuildinfo`
  - shell nueva por comando
- Conclusion tecnica:
  - el repo NO requiere `next typegen` como paso obligatorio para type-check estable;
  - el comando canónico correcto pasa a ser `npm.cmd run typecheck`;
  - `next typegen` queda como paso compatible, no como prerequisito obligatorio.
- Limite honesto:
  - no quedo reconstruida con certeza la causa historica exacta de los FAIL observados antes;
  - la inferencia mas fuerte es estado transitorio/parcial de `.next/types` o medicion tomada mientras otro flujo mutaba artefactos.

### RTLOPS-73 - mapping simbolo↔estrategias elegibles del pool
- Cambio real aplicado en backend/API/frontend minimo:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega persistencia canonica `strategy_eligibility_by_symbol`
    - agrega `GET/PATCH /api/v1/bots/{bot_id}/symbol-strategy-eligibility`
    - agrega reconciliacion fail-closed entre pool, universe y elegibilidad efectiva
    - eleva el contrato del registry a `rtlops73/v1`
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre contrato canonico
    - cubre surface dedicada de elegibilidad
    - cubre invalidaciones fail-closed y guard de archivado
  - `rtlab_dashboard/src/lib/types.ts`
    - expone el contrato `strategy_eligibility`
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - actualiza fixture del contrato canonico
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - agrega surface minima para ver/editar elegibilidad por simbolo sobre pool persistido
- Tests corridos:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run lint -- "src/app/(app)/strategies/page.tsx"` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> FAIL inicial en frio por `.next/types/cache-life.d.ts` faltante
  - `npm.cmd exec next -- typegen` -> PASS
  - `npm.cmd exec tsc -- --noEmit` despues del build/typegen -> PASS
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-74`
  - `RTLOPS-75`
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - execution net/consolidation

### Microbloque tecnico - validacion y cierre honesto del caveat de `tsc --noEmit`
- Revalidacion real de tooling:
  - `rtlab_dashboard/tsconfig.json` sigue siendo el unico `tsconfig` efectivo;
  - `rtlab_dashboard/next.config.ts` no usa `typescript.tsconfigPath`;
  - `ignoreBuildErrors` sigue inactivo;
  - no existe script `typecheck` en `package.json`.
- Definicion operativa de `en frio` usada en esta validacion:
  - borrar solo artefactos no trackeados:
    - `rtlab_dashboard/.next`
    - `rtlab_dashboard/tsconfig.tsbuildinfo`
  - correr cada comando en una shell nueva
- Comandos validados:
  - `npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit --incremental false` en frio -> PASS
- Conclusion tecnica:
  - la narrativa previa de `FAIL en frio por includes .next/types` no reproduce en esta punta;
  - `next typegen` no cambia el resultado del type-check standalone actual: regenera tipos, pero no corrige un fallo activo;
  - no hizo falta tocar `tsconfig.json`, `package.json` ni `next.config.ts`.
- Observacion corregida por evidencia posterior del mismo dia:
  - durante el cierre real de `RTLOPS-73` reaparecio un `FAIL` inicial en frio de `npm.cmd exec tsc -- --noEmit`;
  - ese `FAIL` desaparece despues de `npm.cmd run build` y con `next typegen` disponible;
  - no tomar esta entrada como cierre definitivo del caveat sin esa salvedad.

## 2026-04-17

### RTLOPS-71 - subbloque 2 de identidad canonica en backtests
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - normaliza la identidad visible del bot a `display_name + bot_id`
    - aplica esa identidad en:
      - selector de bot para mass backtest
      - mensaje de carga de pool
      - resumen `Bot filtrado`
      - vista centrica por bot
      - badges/lista de related bots
- Tests corridos:
  - `npm.cmd run lint -- "src/app/(app)/backtests/page.tsx"` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> observacion historica luego revalidada en el microbloque tecnico del 2026-04-18; no tomar como estado actual
- Fuera de alcance mantenido a proposito:
  - `strategies/page.tsx`
  - `strategies/[id]/page.tsx`
  - `rtlab_dashboard/src/lib/types.ts`
  - `legacy_json_id`
  - comparador legacy
  - evidence `trusted / legacy / quarantine`
  - `RTLOPS-73+`
  - lifecycle
  - live console

### RTLOPS-71 - subbloque 1 de strategy detail canonico
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/[id]/page.tsx`
    - elimina el fallback que reconstruia `truth` desde `/api/v1/strategies`
    - elimina el fallback que reconstruia `evidence` desde `/api/v1/backtests/runs`
    - agrega carga honesta con:
      - error explicito si falta `truth` canonica
      - aviso explicito si falta `evidence` canonica
    - deja de presentar `backtests/trades` como fallback legacy de `truth/evidence`
- Tests corridos:
  - `npm.cmd run lint -- "src/app/(app)/strategies/[id]/page.tsx"` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> observacion historica luego revalidada en el microbloque tecnico del 2026-04-18; no tomar como estado actual
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` despues de `build` -> PASS
- Fuera de alcance mantenido a proposito:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
  - cleanup transversal de naming legacy fuera del detail de estrategia
  - `RTLOPS-73+`
  - lifecycle
  - live console

### Auditoria de deuda real - lote 1 de reparacion RTLOPS-24 + RTLOPS-34
- Cambio real aplicado en frontend operatorio:
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - deja de usar `DELETE /api/v1/bots/{bot_id}` desde UI
    - usa archive/restore reales del registry
    - separa badges y filtros de:
      - `status` runtime
      - `registry_status`
    - muestra identidad canonica por `display_name` y `bot_id`
- Cambio real aplicado en helper/test:
  - `rtlab_dashboard/src/lib/execution-bots.ts`
    - helper canonico para labels, filtros y badges del panel operatorio
  - `rtlab_dashboard/src/lib/execution-bots.test.ts`
    - cubre filtro archived por registry, label canonico y badges separados
- Tests corridos:
  - `npm.cmd test -- src/lib/bot-registry.test.ts src/lib/execution-bots.test.ts` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
  - `rtlab_autotrader\\.venv\\Scripts\\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`8 passed`)
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-73`
  - `RTLOPS-74`
  - `RTLOPS-75`
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console
  - cleanup administrativo de Linear

### RTLOPS-72 - Bot Multi-Symbol con modelo canonico de simbolos por bot y limites base
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega `GET /api/v1/bots/{bot_id}/multi-symbol`
    - agrega `PATCH /api/v1/bots/{bot_id}/multi-symbol`
    - expone `multi_symbol` dentro del contrato canonico del registry y dentro de la respuesta de bots
    - endurece el limite de simbolos configurados por bot con cap base `12`
    - traduce errores del surface multi-symbol a naming canonico (`symbols`, `max_active_symbols`) sin romper el storage existente
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/lib/types.ts`
    - tipa `BotMultiSymbolModel`, `BotMultiSymbolResponse` y el surface extendido del contrato
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - valida el cap de simbolos configurados usando el contrato canonico
    - toma el limite activo desde `multi_symbol.limits.max_active_symbols_max`
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - cubre el cap de simbolos configurados y el contrato actualizado `rtlops72/v1`
- Cambio real aplicado en tests backend:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre `GET /api/v1/bots/{bot_id}/multi-symbol`
    - cubre `PATCH /api/v1/bots/{bot_id}/multi-symbol`
    - cubre duplicados, cap configurado, cap activo, fail-closed por catalogo y guard de bot archivado
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`8 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS (`4 passed`)
  - `npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
- Fuera de alcance mantenido a proposito:
  - `RTLOPS-73`
  - `RTLOPS-74`
  - `RTLOPS-75`
  - `RTLOPS-76`
  - `RTLOPS-77`
  - lifecycle
  - live console

### Auditoria global + cleanup controlado de residuos live/legacy
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - la ayuda de `mode=live` deja de expresar `NO GO` global y pasa a describir gating real por `preflight/readiness/gates`
  - `rtlab_dashboard/src/app/(app)/strategies/[id]/page.tsx`
    - el fallback de `truth/evidence` deja de decir que `RTLRESE-14` no esta integrada
  - `rtlab_dashboard/src/app/(app)/execution/page.tsx`
    - el fallback de `policy_state/decision_log` deja de decir que `RTLRESE-14` no esta integrada
- Cambio real aplicado en docs/truth:
  - `docs/truth/SOURCE_OF_TRUTH.md`
    - corrige el estado actual de integracion de `RTLRESE-13/14/15` en la base real
    - deja explicitado que `LIVE` sigue bloqueado por guardrails reales y no por un slogan viejo
  - `docs/truth/NEXT_STEPS.md`
    - elimina pendientes falsos de "mergear o recrear" `RTLRESE-13/14/15`
    - deja solo pendiente residual de compatibilidad transicional contra backends remotos viejos
- Verificacion real aplicada:
  - `rtlab_autotrader/rtlab_core/domains/*.py` ya esta trackeado en repo
  - `rtlab_autotrader/rtlab_core/web/app.py` ya expone:
    - `GET /api/v1/strategies/{id}/truth`
    - `GET /api/v1/strategies/{id}/evidence`
    - `GET/PATCH /api/v1/bots/{id}/policy-state`
    - `GET /api/v1/bots/{id}/decision-log`
  - no se removio ningun guardrail real de `LIVE`
- Tests corridos:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_live_mode_blocked_by_gates or bots_creation_respects_max_instances_limit or bots_overview_cache_hit_and_invalidation_on_create or log_bot_refs_table_is_populated_and_used_in_overview or bots_overview_scopes_kills_by_bot_and_mode" -q` -> PASS (`5 passed`)
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> PASS tambien en frio tras limpieza controlada de artefactos locales (`.next/types`, `.next/dev/types`, `tsconfig.tsbuildinfo`)

### RTLRESE-31 - Bot Registry con contratos minimos de storage, API y frontend
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py`
    - agrega `GET /api/v1/bots/registry-contract`
    - expone version, storage, defaults, limites, enums y grupos de campos del registry
  - el storage real del bot sigue en `learning/bots.json`; este bloque no crea persistencia paralela.
- Cambio real aplicado en API:
  - el registry ahora tiene una surface minima canonica separada y consultable por frontend:
    - `GET /api/v1/bots/registry-contract`
  - se mantienen consistentes sin renombre arbitrario:
    - `GET /api/v1/bots`
    - `GET /api/v1/bots/{bot_id}`
    - `PATCH /api/v1/bots/{bot_id}`
    - `POST /api/v1/bots/{bot_id}/archive`
    - `POST /api/v1/bots/{bot_id}/restore`
    - `GET/PATCH /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/decision-log`
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - deja de hardcodear defaults/limits del registry
    - consume `BotRegistryContractResponse` para construir y validar drafts
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - carga el contrato canonico del registry
    - usa defaults/limits/enums del backend para crear/editar bots
    - muestra contract version y storage real del registry
  - `rtlab_dashboard/src/lib/types.ts`
    - agrega typing del contrato minimo del registry
- Cambio real aplicado en tests:
  - `rtlab_autotrader/tests/test_web_bot_registry_identity.py`
    - cubre la surface API nueva `/api/v1/bots/registry-contract`
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - cubre que el draft/validacion del frontend dependen del contrato canonico y no de limites duros
- Tests corridos:
  - `C:\Users\walte\OneDrive\Desktop\Compu Vieja\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA-rtlrese-26-bot-registry\rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `C:\Users\walte\OneDrive\Desktop\Compu Vieja\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA-rtlrese-26-bot-registry\rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`6 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS (`4 passed`)
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> FAIL preexistente por include roto de `.next/types` en `tsconfig.json`; no fue introducido por `RTLRESE-31`
- Fuera de alcance mantenido a proposito:
  - runtime multi-symbol (`RTLOPS-72+`)
  - mapping estrategia<->simbolo
  - lifecycle
  - live console
  - nuevas features de negocio del bot

## 2026-04-16

### RTLRESE-30 - Bot Registry con edicion, archivado/reactivacion y gobierno basico con trazabilidad
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py` endurece el registry del bot con:
    - `last_change_type`
    - `last_change_summary`
    - `last_changed_by`
    - `last_change_source`
  - create/edit/archive/restore/policy-state ahora persisten trazabilidad minima coherente en el mismo bot;
  - `restore` deja de aceptar bots invalidos silenciosamente y pasa a rechazar:
    - symbols assignment invalido contra el catalogo actual
    - strategy pool invalido contra strategy registry/truth
    - `mode=live` no habilitado por gates actuales
  - el backend sigue reutilizando `decision_log` como respaldo auditable del cambio, sin abrir un subsistema paralelo.
- Cambio real aplicado en API:
  - `POST /api/v1/bots`, `PATCH /api/v1/bots/{bot_id}`, `POST /api/v1/bots/{bot_id}/archive`, `POST /api/v1/bots/{bot_id}/restore` y `PATCH /api/v1/bots/{bot_id}/policy-state` ahora registran actor/source/tipo/resumen del cambio;
  - `GET /api/v1/bots`, `GET /api/v1/bots/{bot_id}` y `GET /api/v1/bots/{bot_id}/policy-state` devuelven la metadata minima de trazabilidad;
  - `GET /api/v1/bots/{bot_id}/decision-log` sigue siendo la vista auditable historica del bot.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - muestra trazabilidad minima por bot
    - muestra `updated_at` / `archived_at`
    - expone errores reales de restauracion invalida
    - deja visible que la reactivacion exige registry valido
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` y `BotPolicyState` tipados con metadata minima de cambio
- Tests corridos:
  - `C:\Users\walte\OneDrive\Desktop\Compu Vieja\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA-rtlrese-26-bot-registry\rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `C:\Users\walte\OneDrive\Desktop\Compu Vieja\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA-rtlrese-26-bot-registry\rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`5 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> FAIL por desalineacion preexistente de `tsconfig.json` con `.next/types` faltantes; no fue introducido por `RTLRESE-30`
- Fuera de alcance mantenido a proposito:
  - `RTLRESE-31`
  - runtime multi-symbol (`RTLOPS-72+`)
  - lifecycle
  - live console
  - elegibilidad estrategia<->simbolo

### RTLRESE-29 - Bot Registry con strategy pool asignado, persistencia y limites
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py` introduce:
    - `BOT_MAX_POOL_STRATEGIES = 15`
    - helper canonico para validar/resolver `pool_strategy_ids`
    - `strategy_pool_status`
    - `strategy_pool_errors`
    - `max_pool_strategies`
  - el backend ya no elimina `strategy_id` invalidas en silencio al normalizar bots;
  - crea validacion explicita contra la fuente real de `list_strategies()` y rechaza:
    - pool vacio
    - duplicados
    - ids inexistentes
    - estrategias `archived`
    - estrategias `disabled/inactive`
    - estrategias con `allow_learning=false`
  - si un bot ya persistido queda desalineado por cambios del strategy registry/truth, el pool queda fail-closed con error visible por API.
- Cambio real aplicado en API:
  - `POST /api/v1/bots` y `PATCH /api/v1/bots/{bot_id}` ahora validan `pool_strategy_ids` con cap `15`;
  - `GET /api/v1/bots`, `GET /api/v1/bots/{bot_id}` y `GET /api/v1/bots/{bot_id}/policy-state` devuelven estado, errores y limite del pool;
  - `PATCH /api/v1/bots/{bot_id}/policy-state` y `bulk-patch` reutilizan la misma validacion del pool.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - alta con selector real de strategy pool
    - edicion de pool por bot sobre el mismo draft del registry
    - visualizacion del cap `15`
    - errores reales de pool y estado fail-closed por bot
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema/helpers del draft extendidos con `pool_strategy_ids`
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstanceStrategyRef`, `BotInstance` y `BotPolicyState` tipados con estado del pool
- Tests corridos:
  - `C:\Users\walte\OneDrive\Desktop\Compu Vieja\Nueva carpeta\VS Code\Trading IA\Bot-Trading-IA-rtlrese-26-bot-registry\rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS (`4 passed`)
  - `npm.cmd test -- src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> FAIL por desalineacion preexistente de `tsconfig.json` con `.next/types` faltantes; no bloquea `next build` y no fue introducido por `RTLRESE-29`
- Fuera de alcance mantenido a proposito:
  - elegibilidad estrategia<->simbolo
  - seleccion de estrategia por simbolo
  - consolidacion / runtime multi-symbol (`RTLOPS-72+`)
  - lifecycle
  - live console

### RTLRESE-28 - Bot Registry con simbolos asignados, universo valido y cap live
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py` extiende el registry del bot con:
    - `universe_name`
    - `universe`
    - `max_live_symbols`
    - `symbol_assignment_status`
    - `symbol_assignment_errors`
  - el backend persiste esos campos en la misma capa canonica de bots;
  - reutiliza `InstrumentUniverseService` y `config/policies/universes.yaml` como fuente real del catalogo;
  - valida duplicados, existencia real de simbolos, compatibilidad con `domain_type` y limite `max_live_symbols <= len(universe)`;
  - si el catalogo deja invalida una asignacion ya persistida, el bot queda fail-closed con error de configuracion visible por API.
- Cambio real aplicado en API:
  - `POST /api/v1/bots` y `PATCH /api/v1/bots/{bot_id}` ahora aceptan y validan `universe_name`, `universe` y `max_live_symbols`;
  - `GET /api/v1/bots` y `GET /api/v1/bots/{bot_id}` devuelven el estado de asignacion;
  - el registry se apoya en `GET /api/v1/instruments/universes` como catalogo canonico del universo valido.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - alta y edicion inline con universo valido, simbolos asignados y `cap live`
    - errores reales de validacion de asignacion
    - resumen por bot de universo, cantidad de simbolos, `cap live` y estado de validez
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema y validaciones cruzadas para duplicados y `max_live_symbols`
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` tipado con estado de asignacion y errores
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - cobertura minima para simbolos duplicados y `cap live`
- Tests corridos:
  - `uv run --project rtlab_autotrader --link-mode=copy --extra dev python -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `uv run --project rtlab_autotrader --link-mode=copy --extra dev python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "api_expensive_rate_limit_guard or bots_multi_instance_endpoints or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override or log_bot_refs_table_is_populated_and_used_in_overview or bots_overview_scopes_kills_by_bot_and_mode or bots_live_mode_blocked_by_gates or bots_creation_respects_max_instances_limit"` -> PASS
  - `npm.cmd exec vitest run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> FAIL por desalineacion preexistente de `.next/types` en el repo; `next build` si paso con el bloque nuevo
- Fuera de alcance mantenido a proposito:
  - `RTLRESE-29` strategy pool
  - elegibilidad estrategia<->simbolo
  - `RTLOPS-72+` runtime multi-symbol
  - lifecycle y live console

### RTLRESE-27 - Bot Registry con capital base, perfil de riesgo y configuracion minima por bot
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py` extiende el registry del bot con:
    - `capital_base_usd`
    - `risk_profile = conservative|medium|aggressive`
    - `max_total_exposure_pct`
    - `max_asset_exposure_pct`
    - `risk_per_trade_pct`
    - `max_daily_loss_pct`
    - `max_drawdown_pct`
    - `max_positions`
  - el backend persiste esos campos en la misma capa canonica de bots;
  - agrega validaciones server-side para montos, porcentajes, enteros y consistencia entre exposicion total y exposicion por activo;
  - cuando faltan limites explicitos, aplica defaults minimos coherentes con el `risk_profile`.
- Cambio real aplicado en API:
  - `POST /api/v1/bots` y `PATCH /api/v1/bots/{bot_id}` ahora aceptan capital/risk/base config minima;
  - `GET /api/v1/bots` y `GET /api/v1/bots/{bot_id}` devuelven esos campos persistidos.
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - formulario minimo de alta con capital base y limites de riesgo
    - edicion inline de esos campos
    - resumen visual de capital/risk profile por bot
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema y helpers para el draft extendido
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` tipado con los nuevos campos
  - `rtlab_dashboard/src/lib/bot-registry.test.ts`
    - cobertura minima para normalizacion numerica y validacion de exposicion
- Tests corridos:
  - `uv run --project rtlab_autotrader --link-mode=copy --extra dev python -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `uv run --project rtlab_autotrader --link-mode=copy --extra dev python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "test_bots_multi_instance_endpoints"` -> PASS
  - `npm.cmd exec vitest run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> PASS
- Fuera de alcance mantenido a proposito:
  - `RTLRESE-28` symbols assignment
  - `RTLRESE-29` strategy pool
  - `RTLRESE-30` gobierno avanzado
  - `RTLRESE-31` contratos extensos adicionales
  - `RTLOPS-72+` multi-symbol/runtime
  - lifecycle y live console

## 2026-04-14

### RTLRESE-26 - Bot Registry con identidad editable, dominio y archivado persistente
- Cambio real aplicado en backend:
  - `rtlab_autotrader/rtlab_core/web/app.py` ahora modela identidad canonica de bot con:
    - `bot_id`
    - `display_name`
    - `alias`
    - `description`
    - `domain_type = spot|futures`
    - `registry_status = active|archived`
    - `archived_at`
  - se preserva `bot_id` estable aunque el nombre visible cambie;
  - `archive` y `restore` pasan a operar como soft-archive real, sin borrado destructivo.
- Cambio real aplicado en API:
  - `GET /api/v1/bots`
    - ahora soporta `registry_status=all|active|archived`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/{bot_id}/archive`
  - `POST /api/v1/bots/{bot_id}/restore`
  - `DELETE /api/v1/bots/{bot_id}`
    - queda explicitamente bloqueado con `409` para no permitir borrado destructivo en un bloque de soft-archive
- Cambio real aplicado en frontend:
  - `rtlab_dashboard/src/app/(app)/strategies/page.tsx`
    - alta de bot por registry minimo
    - edicion inline de identidad
    - badges de dominio y estado de registry
    - archivado/restauracion visibles
    - las altas nuevas ya no dependen de nombres pobres tipo `AutoBot N`
  - `rtlab_dashboard/src/lib/bot-registry.ts`
    - schema y helpers de validacion del formulario de registry
  - `rtlab_dashboard/src/lib/types.ts`
    - `BotInstance` tipado con campos canonicos de registry
- Tests corridos:
  - `uv run --project rtlab_autotrader --link-mode=copy python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `uv run --project rtlab_autotrader --link-mode=copy --extra dev python -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py rtlab_autotrader/tests/test_web_live_ready.py -k "test_bot_registry_identity_crud_and_filters or test_bot_registry_identity_validations or test_bots_multi_instance_endpoints"` -> PASS
  - la suite de `RTLRESE-26` ahora cubre explicitamente que `DELETE /api/v1/bots/{bot_id}` devuelve `409` y obliga a usar `archive`
  - `npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd exec vitest run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
- Fuera de alcance mantenido a proposito:
  - `RTLRESE-27` capital/risk profile
  - `RTLRESE-28` symbols assignment
  - `RTLRESE-29` strategy pool
  - `RTLRESE-30` gobierno avanzado
  - `RTLRESE-31` contracts extensos
  - `RTLOPS-72+` multi-symbol/runtime

## 2026-04-08

### Produccion: PAPER canonico con LIVE bloqueado de forma honesta
- Diagnostico real:
  - production ya estaba online y `/api/v1/health` respondia `200`;
  - pero seguia exponiendo `mode=live` con `runtime_ready_for_live=false`;
  - Settings consultaba gates del modo actual, no la readiness real de `LIVE`.
- Cambio minimo/profesional aplicado:
  - `rtlab_core.web.app` degrada fail-closed a `paper` cualquier estado legado `live` cuando las gates/live readiness siguen en `FAIL`;
  - la degradacion tambien deja el bot en `PAUSED` y `running=false`;
  - `PUT /api/v1/settings` rechaza transiciones invalidas a `LIVE`;
  - `/api/v1/gates` y `/api/v1/gates/reevaluate` aceptan `?mode=live`;
  - Settings usa gates de `LIVE` y deja visible que `PAPER` es la postura canonica hasta cerrar readiness.
- Validacion local:
  - `git diff --check` -> PASS
  - `uv run --project rtlab_autotrader --with pytest python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "health_endpoint_reports_paper_when_live_readiness_is_pending or settings_endpoint_fail_closed_to_paper_when_live_readiness_is_pending or settings_update_rejects_live_without_readiness or gates_endpoint_accepts_explicit_live_mode_query or settings_endpoint_recovers_legacy_settings_shape"` -> PASS
  - `npm.cmd exec eslint -- "src/app/(app)/settings/page.tsx"` -> PASS

## 2026-04-07

### Produccion Railway: decision log deja el backfill pesado fuera del boot blocking path
- Diagnostico repo-side adicional del `502`:
  - `ConsoleStore.__init__()` seguia llamando `BotDecisionLogRepository.initialize()` en startup sync;
  - ese init corria backfills sobre `logs`, `log_bot_refs` y `breaker_events`, lo que en produccion puede pegarle al volumen/SQLite mucho mas que en staging.
- Cambio minimo/profesional aplicado:
  - `initialize(include_backfill=False)` asegura esquema/migraciones minimas sin hacer backfill pesado;
  - el backfill de `decision_log` pasa a `startup maintenance` en background;
  - si esa etapa falla, `startup_maintenance_status` ahora lo refleja con `decision_log_backfill_failed`.
- Validacion local:
  - `pytest rtlab_autotrader/tests/test_web_live_ready.py -k decision_log or startup_maintenance` -> PASS.

### Auditoria implementada: startup maintenance y wrappers SQLite ya no se quedan en estado ambiguo ni resuelven runtime paths
- Hallazgo real de review sobre lo implementado:
  - el mantenimiento de startup podia romper antes del refresh de reporting y dejar `startup_maintenance_status` clavado en `running`;
  - ademas seguian quedando wrappers SQLite del camino de arranque haciendo `Path.resolve()` sobre runtime paths:
    - `ReportingBridgeDB`
    - `ExecutionRealityDB`
    - `ValidationDB`
    - `LivePreflightDB`
    - `BinanceInstrumentRegistryDB`
- Cambio minimo/profesional aplicado en rama de auditoria:
  - `_run_startup_maintenance()` ahora marca fallo explicito por etapa y siempre publica `finished_at`;
  - esos wrappers SQLite pasan a `runtime_path(...)` en vez de `resolve()`.
- Validacion local:
  - `pytest rtlab_autotrader/tests/test_web_live_ready.py -k startup_maintenance_records_failure_status or startup_db_wrappers_do_not_resolve_runtime_sqlite_paths` -> PASS.

### Produccion Railway: startup deja de bloquearse por auth sqlite y mantenimiento de ConsoleStore
- Diagnostico mas fuerte del `502` residual:
  - el import de `rtlab_core.web.main` seguia tardando ~33s con la configuracion default;
  - al pasar `RATE_LIMIT_LOGIN_BACKEND=memory`, ese import caia a ~4.6s.
- Cambio minimo/profesional aplicado:
  - `LoginRateLimiter` deja de instanciarse en import-time y pasa a lazy init on-demand;
  - su sqlite path deja de resolver roots runtime;
  - `ConsoleStore` saca `_ensure_seed_backtest`, `_sync_backtest_runs_catalog` y `refresh_materialized_views(...)` del boot blocking path y los corre como mantenimiento no bloqueante;
  - los hooks `startup` de instrument registry y live order recovery pasan a background no bloqueante;
  - `/api/v1/health` deja de persistir runtime state.
- Validacion local:
  - `main import` local: ~33s -> ~4s;
  - `py_compile` -> PASS;
  - `pytest rtlab_autotrader/tests/test_web_live_ready.py -k login_rate_limit or health_endpoint_does_not_persist_runtime_state or startup_hooks_schedule_background_work_without_blocking` -> PASS.

### Produccion Railway: startup path deja de resolver roots runtime en servicios globales
- Diagnostico mas fuerte del `502`:
  - `rtlab_core.web.app` seguia construyendo servicios globales que resolvian `user_data_dir` por filesystem durante import/startup.
- Cambio minimo/profesional aplicado:
  - `ReportingBridgeService`
  - `ExecutionRealityService`
  - `ValidationService`
  - `LearningService`
  - `RolloutManager`
  pasan a usar `runtime_path(...)` para roots runtime.
- Validacion local:
  - tests puntuales agregados para esos constructores;
  - `py_compile` y `pytest` del camino critico -> PASS.

### Auditoria seria de Backtests / Beast / Masivo
- Diagnostico real del dominio sobre `main`:
  - Beast y Masivo comparten `USER_DATA_DIR`, `DataCatalog`, `build_data_provider(...)` y preflight de dataset;
  - no habia evidencia de roots separados ni de un bug de frontend inventando dataset faltante.
- Hallazgo importante corregido en rama de auditoria:
  - seguian vivos `Path.resolve()` sobre roots runtime dentro de:
    - `rtlab_core.src.data.catalog`
    - `rtlab_core.src.data.loader`
    - `rtlab_core.src.research.data_provider`
    - `rtlab_core.src.research.mass_backtest_engine`
    - `rtlab_core.src.reports.reporting`
    - `rtlab_core.src.data.binance_futures_bootstrap`
  - se introduce `rtlab_core.src.data.runtime_path` para normalizar paths runtime sin tocar el filesystem del volumen.
  - `Backtests` deja de silenciar errores de refresh en el panel Beast y ahora muestra un error explicito si no puede leer el backend real.
- Lectura honesta:
  - Backtests mejora y queda mas coherente internamente;
  - pero mientras produccion siga devolviendo `502 Application failed to respond`, el dominio no puede considerarse cerrado sobre `main`.

### Produccion Railway: mount detection no bloqueante por `mountinfo`
- Diagnostico real posterior al merge de `#24`:
  - produccion empezo a responder `502 Application failed to respond`;
  - el workflow `Production Storage Durability` (`24063115973`) fallo por `Read timed out` en el primer chequeo de storage.
- Causa raiz mas fuerte:
  - la deteccion de mount apoyada en `Path.exists()` + `Path.is_mount()` podia bloquear el runtime al tocar roots de volumen en Railway.
- Cambio minimo/profesional aplicado:
  - `rtlab_core.web.app` ahora resuelve mounts runtime solo via `/proc/self/mountinfo` (longest-prefix match);
  - elimina `Path.resolve()` del camino critico de `RTLAB_USER_DATA_DIR` para no tocar el volume path durante startup/health;
  - se elimina la necesidad de tocar el filesystem del volumen para determinar persistencia.

### Produccion Railway: persistencia durable de datasets requiere mount real
- Diagnostico real:
  - `storage.persistent_storage` y `G10_STORAGE_PERSISTENCE` estaban basados solo en “path fuera de `/tmp`”.
  - eso producia falsos positivos de persistencia si `RTLAB_USER_DATA_DIR` apuntaba a un directorio no montado dentro del contenedor.
- Cambio minimo/profesional aplicado:
  - `rtlab_core.web.app` ahora detecta mount real con `Path.is_mount()` + `/proc/self/mountinfo`
  - `health.storage` expone:
    - `configured_user_data_dir`
    - `selection_drift`
    - `mount_detected`
    - `mount_point`
    - `mount_source`
    - `mount_fs_type`
    - `mounted_runtime_candidates`
  - `G10_STORAGE_PERSISTENCE` queda fail-closed:
    - `PASS` solo si el root efectivo esta sobre un mount real
    - `FAIL/WARN` si el path es efimero o no montado
  - si el env apunta a un root no montado y existe un candidate soportado montado, el runtime prioriza el candidate montado
- Validacion operativa agregada:
  - nuevo workflow `.github/workflows/production-storage-durability.yml`
  - usa secretos productivos para:
    - chequear persistencia real
    - bootstrap `BTCUSDT`
    - revalidar presencia del dataset exacto `5m`

## 2026-04-06

### Produccion Beast/Backtests: bootstrap canonico de datasets Binance Futures
- Diagnostico real:
  - el warning visible en `csud/backtests` ya no venia de `policy_state=missing`;
  - produccion tenia `policy_state=enabled`, pero `GET /api/v1/data/status` devolvia `available_count=0` en `${RTLAB_USER_DATA_DIR}/data`.
- Causa raiz cerrada en repo:
  - no existia un bootstrap canonico de datasets Futures persistido sobre el volumen runtime real de produccion.
- Cambio minimo/profesional aplicado:
  - nuevo modulo `rtlab_core/src/data/binance_futures_bootstrap.py`
  - nuevo script `rtlab_autotrader/scripts/bootstrap_binance_futures_public.py`
  - nuevo endpoint admin `POST /api/v1/data/bootstrap/binance-futures-public`
  - `DataCatalog` ignora `*.summary.json` y deja de contarlos como datasets reales
  - `Backtests` ahora sugiere el comando canonico de Futures, no el downloader legacy spot
- Fuente y criterio canónicos:
  - prioridad: zips historicos oficiales de Binance Futures + `.CHECKSUM`
  - fallback: REST oficial de klines Futures
  - base única: `1m`
  - resample canonico: `5m`, `15m`, `1h`, `4h`, `1d`
  - seleccion top 40:
    - USD-M: `quoteVolume` 24h desc sobre contratos `TRADING/PERPETUAL`
    - COIN-M: `baseVolume * weightedAvgPrice` 24h desc sobre contratos `TRADING/PERPETUAL`
- Validacion real de cierre:
  - mergeado en `main`
  - auto-deploy productivo confirmado por la aparicion del endpoint nuevo en `bot-trading-ia-production.up.railway.app`
  - bootstrap productivo ejecutado para:
    - `BTCUSDT`
    - `usdm`
    - `2024-01..2024-12`
    - `5m/15m/1h/4h/1d`
  - catalogo productivo paso a `available_count=6`
  - Beast produjo una corrida real E2E:
    - `run_id=BX-000001`
    - `terminal_state=COMPLETED`
    - `results_count=1`

### Produccion Beast/runtime: empaquetado legacy sin `config/`
- Diagnostico real:
  - `bot-trading-ia-csud` no estaba mintiendo; estaba leyendo produccion real.
  - `GET /api/v1/config/policies` en produccion devolvia `available=false` y ausencia total de:
    - `/app/config/policies`
    - `/app/rtlab_autotrader/config/policies`
- Causa raiz cerrada en repo:
  - `rtlab_autotrader/docker/Dockerfile` no copiaba `config/` al contenedor.
- Cambio minimo:
  - `rtlab_autotrader/docker/Dockerfile` ahora agrega `COPY config /app/config`.
- Objetivo:
  - alinear el build legacy/nested de produccion con el runtime que staging ya usa sano;
  - evitar que Beast vuelva a quedar en `policy_state=missing` por empaquetado incompleto.

### Railway staging: auto-deploy reproducible desde GitHub/main
- Diagnostico real de infraestructura:
  - en `staging`, Railway quedo con `rootDirectory=null` y `dockerfilePath=docker/Dockerfile`.
  - los auto-deploys por GitHub de `main` fallaban porque el repo root no tenia `docker/Dockerfile`.
  - los deploys manuales por CLI seguian funcionando cuando se usaba `railway up rtlab_autotrader --path-as-root`, porque ahi el source directory pasaba a ser `rtlab_autotrader/` y `docker/Dockerfile` si existia dentro de esa raiz.
- Solucion automatica dejada por codigo:
  - nuevo `railway.json` en la raiz del repo con:
    - `builder=DOCKERFILE`
    - `dockerfilePath=docker/Dockerfile`
    - `watchPatterns` limitados al backend/config
  - nuevo `docker/Dockerfile` en la raiz del repo, compatible con build context repo root
- Objetivo:
  - que Railway pueda auto-desplegar desde GitHub/main aun con `rootDirectory=null`;
  - dejar el deploy backend reproducible sin depender del control de UI de `Root Directory`.
## 2026-04-05

### PR 2 documental preparado desde rama limpia
- Se creo la rama limpia `integration/product-inputs-and-truth-main` desde `main` ya actualizado con el merge del PR runtime.
- Se portan solo:
  - `docs/product/inputs/*`
  - `docs/truth/*` minimas asociadas
- Se introducen los 3 inputs canonicos de producto:
  - `2026-04-ui-trades-console.md`
  - `2026-04-capital-allocation-control.md`
  - `2026-04-runtime-incidents-ops.md`
- Este PR 2 deja lista la estructura para Linear, pero no hace sync real si la integracion no esta disponible.
- Queda explicitamente afuera:
  - implementacion de `Capital & Allocation Control`
  - implementacion grande de `UI / Trades Console`
  - implementacion grande de `Runtime Incidents / Logs / Alerts / Ops`

### PR 1 runtime live/paper hardening preparado desde rama limpia
- Se creo la rama limpia `integration/runtime-live-paper-hardening-main` desde `origin/main`.
- Se porto un paquete coherente de runtime validado sin mezclar:
  - `docs/product/inputs/*`
  - sync de Linear
  - structuring/backlog administrativo
- Se incluyeron en este PR 1:
  - `ExecutionRealityService` y surfaces runtime asociadas
  - instrument registry / reporting / validation runtime requeridos por el flujo live/paper
  - fixes validados de:
    - `margin_guard`
    - quote reuse para `paper`
    - persistencia paper al ledger operativo
    - `gross/net/cost` en trade rows paper
    - backfill via reconcile
  - monitor externo de `PAPER`:
    - `.github/workflows/paper-validation-monitor.yml`
    - `scripts/paper_validation_monitor.py`
- Se deja explicitado que el cron del monitor solo quedara activo al mergear a la branch por defecto.
- Queda explicitamente afuera de este PR 1:
  - `docs/product/inputs/*`
  - sync administrativo/modelado en Linear
  - bloques grandes de `Capital & Allocation Control`, `UI / Trades Console` y `Runtime Incidents / Logs / Alerts / Ops`

## 2026-03-18

### RTLOPS-2 / RTLOPS-1 / RTLOPS-7 - micro-hardening final frontend de authority/runtime
- Frontend `rtlab_dashboard`:
  - `eslint.config.mjs` agrega ignores explicitos y minimos para `.pytest_cache/**`, `.next/**` y `node_modules/**` usando flat config (`globalIgnores`) para evitar el `EPERM` del cache local en `lint`.
  - `src/lib/auth-backend.test.ts` reemplaza casts repetidos a `NodeJS.ProcessEnv` por un helper de test valido con `NODE_ENV=test` y `BACKEND_API_URL=https://api.example.com`.
- Validacion local final del micro-cierre:
  - `npm.cmd run lint` -> PASS
  - `npm.cmd run build` -> PASS
  - `npx.cmd tsc --noEmit` -> PASS

### RTLOPS-2 / RTLOPS-1 / RTLOPS-7 - autoridad de policies + taxonomia de modos
- Backend:
  - se explicita la autoridad de `config/policies` con metadata runtime en `GET /api/v1/config/policies`:
    - `authority`
    - `mode_taxonomy`
  - la raiz canonica queda fijada en `config/policies/`;
  - `rtlab_autotrader/config/policies/` queda solo como compatibilidad/fallback.
- Deteccion operativa:
  - si existen YAML duplicados y divergentes entre la raiz canonica y la nested, el backend ahora lo expone como warning de autoridad.
- Taxonomia canonica documentada y usada:
  - runtime global:
    - `PAPER`
    - `TESTNET`
    - `LIVE`
  - modos por bot:
    - `shadow`
    - `paper`
    - `testnet`
    - `live`
  - fuentes de evidence:
    - `backtest`
    - `shadow`
    - `paper`
    - `testnet`
- Frontend:
  - `Settings` y `Execution` dejan de vender `MOCK` como modo runtime real;
  - `MOCK` queda rotulado como alias legado del mock local.
- Documentacion:
  - nueva `docs/plan/AUTHORITY_HIERARCHY.md`
  - `docs/truth` actualizadas con jerarquia de autoridad tecnica y siguiente bloque recomendado

## 2026-03-16

### RTLRESE-13 backend domains: separacion minima por dominio
- Backend:
  - nuevo arbol operativo en `rtlab_autotrader/rtlab_core/domains/`:
    - `truth/`
    - `evidence/`
    - `policy_state/`
    - `decision_log/`
  - `ConsoleStore` deja de persistir directo `strategy_meta`, `runs`, `settings`, `bot_state`, `bots` y `logs`;
  - ahora delega esa persistencia a repositorios de dominio explicitos.
- Frontera semantica aplicada:
  - `strategy_truth` -> metadata persistente de estrategias
  - `strategy_evidence` -> runs + cableado a `ExperienceStore`
  - `bot_policy_state` -> `console_settings.json`, `bot_state.json`, `bots.json`
  - `bot_decision_log` -> `console_api.sqlite3` (`logs`, `breaker_events`)
- Alcance:
  - sin refactor masivo de endpoints
  - sin cambios de frontend
  - sin mezclar RTLRESE-14/15/16
- Pendiente documentado:
  - `RegistryDB` sigue agrupando tablas de truth/evidence/policy guidance;
  - si hace falta profundizar la separacion, ese split interno queda para un tramo posterior.
- Validacion local:
  - `uv run python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/domains/common.py rtlab_autotrader/rtlab_core/domains/truth/repository.py rtlab_autotrader/rtlab_core/domains/evidence/repository.py rtlab_autotrader/rtlab_core/domains/policy_state/repository.py rtlab_autotrader/rtlab_core/domains/decision_log/repository.py` -> PASS

### RTLRESE-14 backend API contracts por dominio
- Backend FastAPI:
  - agrega `GET /api/v1/strategies/{strategy_id}/truth`
  - agrega `GET /api/v1/strategies/{strategy_id}/evidence`
  - agrega `GET /api/v1/bots/{bot_id}/policy-state`
  - agrega `PATCH /api/v1/bots/{bot_id}/policy-state`
  - agrega `GET /api/v1/bots/{bot_id}/decision-log`
- Compatibilidad:
  - `GET /api/v1/strategies/{strategy_id}` se mantiene como endpoint legado y ahora recompone `last_oos` desde los helpers de dominio.
- Frontera operativa:
  - `truth` ya no comparte payload principal con evidencia;
  - `policy_state` queda separado del patch generico de bot;
  - `decision_log` queda separado de `logs` globales.
- Alcance explicitamente no mezclado:
  - sin cambios en frontend;
  - sin tocar RTLRESE-15/16.
- Validacion:
  - `py_compile` sobre `app.py` y `test_web_live_ready.py` -> PASS
  - smoke funcional directo sobre `ConsoleStore` -> PASS
  - smoke HTTP con `pytest` bloqueado por entorno (`httpx` faltante para `starlette.testclient`)

### RTLRESE-15 - frontend domains split con fallback legacy
- Frontend `Strategy detail`:
  - consume `truth/evidence` por separado cuando los endpoints nuevos existen;
  - cae de forma controlada a `GET /api/v1/strategies/{id}` + `GET /api/v1/backtests/runs` cuando el backend actual no expone RTLRESE-14.
- Frontend `Execution`:
  - agrega bloques separados de `Bot policy state` y `Bot decision log`;
  - usa `GET /api/v1/bots/{id}/policy-state` y `GET /api/v1/bots/{id}/decision-log` si existen;
  - si no existen, recompone desde `GET /api/v1/bots` y `GET /api/v1/logs`.
- Frontend `Strategies`:
  - deja mas explicito que KPIs/sharpe/max-dd son evidence agregada;
  - las acciones de bot intentan `PATCH /policy-state` y mantienen fallback a `PATCH /api/v1/bots/{id}`.
- Tipos:
  - nuevos tipos de dominio frontend en `src/lib/types.ts` para `truth`, `evidence`, `policy_state` y `decision_log`.
- No incluido:
  - sin cambios backend;
  - sin cambios frontend fuera de pantallas/consumo de contratos;
  - sin mezcla con RTLRESE-16.
- Validacion:
  - inspeccion manual del diff + chequeo de contratos legacy/nuevos en repo.
  - limitacion de entorno: no se pudo correr `next lint` / `tsc` / `next build` porque falta `node.exe` en esta sesion.

### RTLRESE-16 - cierre documental de la frontera operativa
- Se consolida en `docs/truth` la frontera canonica entre:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- Resumen de sub-issues previas:
  - RTLRESE-11 / RTLRESE-12:
    - fijan la frontera semantica y el lenguaje de contratos para separar verdad base, evidencia y estado operativo.
  - RTLRESE-13:
    - separacion backend por dominios cerrada en rama `feature/rtlrese-13-backend-domains` (`4497029`).
  - RTLRESE-14:
    - separacion API por endpoints cerrada en rama `feature/rtlrese-14-api-contracts` (`703cea8`).
  - RTLRESE-15:
    - separacion frontend por bloques y tipos cerrada en rama `feature/rtlrese-15-frontend-domains` (`1443789`).
- Estado real asentado por RTLRESE-16:
  - la base activa de esta rama todavia conserva contratos y pantallas legacy;
  - por eso `SOURCE_OF_TRUTH` ahora diferencia explicitamente entre:
    - frontera canonica ya definida/cerrada
    - integracion realmente visible hoy en la base trackeada.
- Sin cambios de producto:
  - esta sub-issue toca solo `docs/truth`;
  - no agrega features nuevas de backend ni frontend.

### RTLRESE-7: strategy_evidence legacy/quarantine
- `ExperienceStore` ahora clasifica evidencia en:
  - `trusted`
  - `legacy`
  - `quarantine`
- `quarantine` se aplica cuando falta metadata critica, trazabilidad temporal minima, `dataset_hash` de backtest o costos totales completos.
- `legacy` se aplica cuando la evidencia sigue siendo usable pero degradada:
  - `costs_breakdown` faltante y reconstruido desde trades
  - `commit_hash` faltante
  - `dataset_source`/`validation_mode` faltantes en backtest
  - `feature_set` faltante/unknown
  - componentes de costo incompletos
  - `validation_quality=synthetic_or_bootstrap`
- `RegistryDB.list_experience_episodes(...)` expone `evidence_status`, `evidence_flags` y `learning_excluded`.
- `OptionBLearningEngine` ahora:
  - excluye episodios `quarantine` de contexts/eventos/rankings
  - mantiene episodios `legacy`, pero los marca `needs_validation`
  - agrega conteos/flags de evidencia en summary y proposals
- `strategy_policy_guidance` anota presencia de `legacy` y exclusion de `quarantine` en `notes`.
- Validacion:
  - `uv run --project rtlab_autotrader python -m py_compile rtlab_autotrader/rtlab_core/learning/experience_store.py rtlab_autotrader/rtlab_core/learning/option_b_engine.py rtlab_autotrader/rtlab_core/strategy_packs/registry_db.py rtlab_autotrader/tests/test_learning_experience_option_b.py` -> PASS
  - `uv run --project rtlab_autotrader --extra dev python -m pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS (`8 passed`)
### RTLRESE-10 · Research funnel + trial ledger
- Backend:
  - nuevos endpoints `GET /api/v1/research/funnel` y `GET /api/v1/research/trial-ledger`;
  - el ledger combina `BacktestCatalogDB`, `experience_episode (source=backtest)` y `learning_proposal`;
  - si la evidencia todavia no tiene estado canonico persistido, clasifica on-the-fly en:
    - `trusted`
    - `legacy`
    - `quarantine`
  - `catalog_only_no_episode` queda visible como `legacy` para no ocultar corridas viejas ni venderlas como evidence fuerte.
- Frontend `Backtests`:
  - nueva seccion `Research Funnel y Trial Ledger`;
  - separa conteos de runs, evidence `trusted/legacy/quarantine`, pipeline de candidates y tabla corta de ledger;
  - no mezcla `strategy_truth` ni runtime con research evidence.
- Compatibilidad:
  - la UI nueva convive con `Backtests / Runs` y `Research Batch`;
  - se mantienen contratos legacy existentes.
- Validacion:
  - `py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
  - smoke funcional directo del modulo con `user_data` temporal -> PASS
  - smoke HTTP con `pytest` pendiente por entorno: falta `httpx` para `starlette.testclient`

## 2026-03-06

### Vista bot-centrica en Backtests / Runs
- Backend:
  - `GET /api/v1/runs` acepta `bot_id`;
  - cada run devuelve `related_bot_ids` y `related_bots` derivados del pool actual de estrategias.
- Frontend `Backtests / Runs`:
  - agrega filtro por bot;
  - muestra chips de bots por run;
  - agrega panel centrico por bot con:
    - metricas acumuladas,
    - historial por fuente,
    - performance por modo,
    - pool actual.
- Tests:
  - smoke de `runs` valida metadatos `related_bot_ids/related_bots` y filtro `bot_id`.
- Limite actual conocido:
  - la atribucion run -> bot sigue siendo por pool actual del bot; todavia no se persiste relacion historica exacta en catalogo.

### Hotfix shadow/beast + evidencia local controlada
- `ShadowRunConfig`:
  - corrige default mutable de `costs` con `default_factory(...)` para no romper import en Python 3.13;
  - sube `lookback_bars` default de `240` a `300`.
- API/runtime shadow:
  - `SHADOW_DEFAULT_LOOKBACK_BARS` y `ShadowStartBody.lookback_bars` quedan en `300`.
- `MassBacktestCoordinator`:
  - corrige fallback de `beast_mode.yaml` cuando la cola esta vacia (`self.engine.repo_root`).
- Evidencia local agregada:
  - `docs/audit/LEARNING_EXPERIENCE_VALIDATION_20260306.md`
  - bestia real `BX-000001` -> `COMPLETED`
  - shadow real con default corregido -> `1` episodio persistido (`source=shadow`)
- Estado abierto:
  - previews Vercel del commit `ffabe9e` siguen en `failure`.

### Experience learning + shadow + backtests UX
- Backend:
  - se consolido persistencia de experiencia en `RegistryDB`:
    - `experience_episode`
    - `experience_event`
    - `regime_kpi`
    - `learning_proposal`
    - `strategy_policy_guidance`
  - `ConsoleStore.record_experience_run(...)` queda cableado para runs de backtest y shadow.
- Shadow/mock:
  - `ShadowRunner` usa market data publico de Binance Spot;
  - no envia ordenes;
  - expone endpoints:
    - `GET /api/v1/learning/shadow/status`
    - `POST /api/v1/learning/shadow/start`
    - `POST /api/v1/learning/shadow/stop`
  - persiste episodios `source=shadow`.
- Opcion B:
  - `OptionBLearningEngine` filtra `allow_learning=true`;
  - aplica pesos por fuente:
    - `shadow=1.00`
    - `testnet=0.90`
    - `paper=0.80`
    - `backtest=0.60`
  - bloquea propuestas cuando falla evidencia/costos/feature-set/baseline.
- Batch / Modo Bestia:
  - `_mass_backtest_eval_fold(...)` genera sub-runs via `create_event_backtest_run(...)`;
  - los sub-runs del batch dejan experiencia persistente;
  - se mantiene bloqueo de datos sinteticos para research/bestia.
- Frontend `Strategies`:
  - nuevas secciones de experiencia, propuestas Opcion B, guidance y shadow;
  - nuevas ayudas para modo/engine;
  - bots muestran experiencia por fuente.
- Frontend `Backtests`:
  - selector de bot y accion `Usar pool del bot`;
  - mensajes mas claros para batch vs shadow/mock;
  - `GET /api/v1/runs` pasa de `limit=5000` a `limit=2000` y corrige `422` en `Backtests / Runs`.
- Docs nuevas:
  - `docs/research/EXPERIENCE_LEARNING.md`
  - `docs/research/BRAIN_OF_BOTS.md`
  - `docs/runbooks/SHADOW_MODE.md`
- Validacion:
  - `py_compile` backend learning/shadow -> PASS
  - `pytest rtlab_autotrader/tests/test_learning_experience_option_b.py -q` -> PASS
  - `npm run lint -- "src/app/(app)/backtests/page.tsx" "src/app/(app)/strategies/page.tsx" "src/lib/types.ts"` -> PASS
  - `npm run build` (`rtlab_dashboard`) -> PASS

## 2026-03-05

### Staging persistence fix + protected checks PASS (run 22741651051)
- Infra staging:
  - volumen adjunto en `/app/user_data`;
  - permisos de volumen corregidos para runtime (`uid=1000`):
    - `chown -R 1000:1000 /app/user_data`
    - `chmod 775 /app/user_data`
  - variable activa: `RTLAB_USER_DATA_DIR=/app/user_data`.
- Validacion health staging:
  - `ok=true`, `mode=paper`, `runtime_ready_for_live=false`, `storage_persistent=true`.
- Revalidacion remota `Remote Protected Checks (GitHub VM)`:
  - run `22741651051` -> `success`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
- Evidencia:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741651051_20260305.md`.

### AP-BOT-1035 (staging strict=true sin falso negativo no-live)
- `scripts/ops_protected_checks_report.py`:
  - nuevo flag `--allow-staging-warns` para aceptar en staging no-live:
    - `g10_status=WARN`
    - `breaker_status=NO_DATA`
  - mantiene reporte explicito de status reales (`g10_status`, `breaker_status`) y marca `allow_staging_warns_applied=true`.
- `/.github/workflows/remote-protected-checks.yml`:
  - aplica `--allow-staging-warns` automaticamente cuando `base_url` contiene `staging`.
- Evidencia operativa:
  - run staging `22741088468` -> `success`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=WARN`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
  - documento: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741088468_20260305.md`.
- Nota de estabilidad staging:
  - intento de persistencia con volumen (`/data` y `/app/user_data`) genero crash por permisos SQLite;
  - rollback operativo aplicado: `RTLAB_USER_DATA_DIR=/tmp/rtlab_user_data`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1035_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1034 (runner protegido con diagnostico sin JSON)
- `scripts/run_protected_checks_github_vm.ps1`:
  - ahora genera `protected_checks_summary_<run_id>.json` incluso si el workflow falla antes de crear `ops_protected_checks_gha_*.json`;
  - reporta `NO_EVIDENCE` en campos canonicos cuando no hay reporte estructurado.
- Evidencia operativa:
  - run staging `22738098708` (`failure`) documentado en:
    - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22738098708_20260305.md`
  - causa: `401 Invalid credentials` en login.
  - sanity run produccion `22738228159` (`success`) documentado en:
    - `docs/audit/PROTECTED_CHECKS_GHA_22738228159_20260305.md`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1034_BIBLIO_VALIDATION_20260305.md`.

### Revalidacion staging auth + checks operativos (run 22739570506)
- `Remote Protected Checks (GitHub VM)` contra staging:
  - run `22739570506` -> `failure`.
- Resultado:
  - login/auth staging ya operativo (sin `401`);
  - fallo por checks operativos:
    - `g10_status=WARN` (`storage_persistent=false`)
    - `breaker_ok=false` (`breaker_status=NO_DATA`, `strict_mode=true`)
  - `g9_status=WARN` esperado en no-live.
- Evidencia:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22739570506_20260305.md`.

### Revalidacion staging auth + checks operativos (run 22740010128)
- `Remote Protected Checks (GitHub VM)` contra staging:
  - run `22740010128` -> `failure`.
- Resultado:
  - auth staging confirmada (sin `401 Invalid credentials`);
  - falla operativa mantenida:
    - `g10_status=WARN` (`storage_persistent=false`)
    - `breaker_ok=false` (`breaker_status=NO_DATA`, `strict_mode=true`)
  - `g9_status=WARN` esperado en no-live.
- Evidencia:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22740010128_20260305.md`.

### AP-BOT-1033 (submit bloqueado con reconciliacion no valida)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` ahora bloquea submit cuando `runtime_reconciliation_ok=false` (`reason=reconciliation_not_ok`).
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_testnet_skips_submit_when_reconciliation_not_ok`;
  - ajuste de test de orden local no verificada para reflejar guard de reconciliacion.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1033_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1032 (submit bloqueado si falla account snapshot)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` ahora aplica fail-closed con `reason=account_positions_fetch_failed` cuando `runtime_account_positions_ok=false`.
  - `sync_runtime_state(...)` propaga `account_positions_reason` al submitter para trazabilidad.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_testnet_skips_submit_when_account_positions_fetch_fails`;
  - ajuste del test de idempotencia para mockear `GET /api/v3/account`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1032_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1031 (fail-closed por orden local no verificada)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_close_absent_local_open_orders(...)` ya no cierra localmente si falla `order status`; conserva la orden abierta.
  - `_maybe_submit_exchange_runtime_order(...)` bloquea submit remoto cuando existen ordenes locales abiertas no verificadas (`local_open_orders_present`).
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - renombrado/ajustado test de reconciliacion por fallo de `order status`;
  - nuevo test que verifica bloqueo de submit con orden local abierta no verificada.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1031_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1030 (automatizacion de protected checks en GitHub VM)
- Nuevo script operativo:
  - `scripts/run_protected_checks_github_vm.ps1`.
- Cobertura:
  - detecta `gh.exe` aun si no esta en `PATH` (rutas tipicas Windows);
  - dispara `remote-protected-checks.yml` por `workflow_dispatch`;
  - espera completion, descarga artifacts y parsea JSON del reporte;
  - extrae automaticamente los 6 campos canonicos:
    - `overall_pass`
    - `protected_checks_complete`
    - `g10_status`
    - `g9_status`
    - `breaker_ok`
    - `internal_proxy_status_ok`
- Revalidacion operativa post-patch:
  - run `22734260830` -> `success`.
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22734260830_20260305.md`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1030_BIBLIO_VALIDATION_20260305.md`.

### Remote protected checks (rerun estricto)
- Workflow `Remote Protected Checks (GitHub VM)` re-ejecutado con defaults y `strict=true`:
  - run `22704105623` -> `success`.
- Resultado canonico del reporte remoto:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- Impacto operativo:
  - se confirma continuidad del cierre no-live en verde;
  - LIVE permanece en `NO GO` hasta cierre de runtime real end-to-end y activacion final de APIs live.

### AP-BOT-1023 (smoke staging automatizado + evidencia)
- Nuevo script de smoke no-live:
  - `scripts/staging_smoke_report.py`
  - verifica `frontend /login`, `backend /api/v1/health`, guardas de modo no-live y, cuando hay credenciales, `/api/v1/bots`.
  - salida en `json` + `md` bajo `artifacts/staging_smoke_*`.
- Evidencia registrada:
  - `docs/audit/STAGING_SMOKE_20260305.md`.
- Corrida validada:
  - `python scripts/staging_smoke_report.py --report-prefix artifacts/staging_smoke_ghafree` -> PASS (`overall_pass=true`).
- Nota de seguridad/operacion:
  - en esta corrida local no hubo secretos cargados (`RTLAB_AUTH_TOKEN`/`RTLAB_ADMIN_PASSWORD`), por eso el check autenticado queda explicitado como `NO_EVIDENCE_NO_SECRET`.
  - la validacion autenticada completa sigue cubierta por `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.

### AP-BOT-1024 (workflow diario de staging smoke)
- Nuevo workflow:
  - `/.github/workflows/staging-smoke.yml`.
- Cobertura:
  - trigger programado diario (`schedule`) y trigger manual (`workflow_dispatch`);
  - ejecucion de `scripts/staging_smoke_report.py`;
  - validacion fail-closed de secretos cuando se exigen checks autenticados;
  - publicacion de artefactos (`staging_smoke_gha_<run_id>_*.md/json` + stdout).
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1024_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1025 (fix de workflow protected checks)
- `/.github/workflows/remote-protected-checks.yml`:
  - se agrega `--no-strict` cuando input `strict=false`;
  - se elimina fallback legacy de `--password` por CLI.
- Evidencia del hallazgo en staging:
  - run `22732410544` (`failure`) en `main`:
    - `401 Invalid credentials`;
    - evidencia de ruta legacy con `--password`.
  - reporte: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732410544_20260305.md`.
- Validacion del fix en rama tecnica:
  - run `22732584979` (`success`) con `expect_g9=PASS` y `strict=false`;
  - `overall_pass=false` pero job exitoso, confirmando aplicacion de `--no-strict`.
  - reporte: `docs/audit/PROTECTED_CHECKS_GHA_22732584979_NON_STRICT_20260305.md`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1025_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1026 (secretos por entorno en workflows remotos)
- `/.github/workflows/remote-protected-checks.yml`:
  - seleccion de auth por entorno (`RTLAB_STAGING_*` con fallback a `RTLAB_*`).
- `/.github/workflows/staging-smoke.yml`:
  - staging smoke prioriza secretos `RTLAB_STAGING_*`.
- Validacion de no-regresion:
  - run `22732769817` (`success`) con `strict=true` y `expect_g9=WARN`.
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22732769817_20260305.md`.
- Validacion staging:
  - run `22732896736` (`failure`) por credenciales staging ausentes (`RTLAB_STAGING_*` vacios).
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732896736_20260305.md`.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1026_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1027 (hardening no-fallback cross-env)
- Workflows actualizados para evitar fallback cruzado de credenciales:
  - `remote-protected-checks.yml`: staging usa solo `RTLAB_STAGING_*`, produccion solo `RTLAB_*`.
  - `staging-smoke.yml`: auth en staging requiere solo `RTLAB_STAGING_*`.
- Motivacion:
  - prevenir login fallido por uso de password/token de produccion en staging;
  - endurecer separacion de secretos por entorno.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1027_BIBLIO_VALIDATION_20260305.md`.
- Evidencia post-push:
  - produccion: run `22733438064` -> `success` (`docs/audit/PROTECTED_CHECKS_GHA_22733438064_20260305.md`).
  - staging: run `22733461982` -> `failure` fail-fast por secreto faltante (`docs/audit/PROTECTED_CHECKS_STAGING_GHA_22733461982_20260305.md`).

### AP-BOT-1028 (runbook de secrets GitHub Actions)
- Nuevo documento:
  - `docs/deploy/GITHUB_ACTIONS_SECRETS.md`
- Incluye:
  - separacion de secretos staging/produccion;
  - comandos `gh secret list` y `gh secret set`;
  - checklist de validacion post-configuracion.
- Trazabilidad bibliografica:
  - `docs/audit/AP_BOT_1028_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1029 (runtime readiness refresh sobre cache negativo)
- `RuntimeBridge._runtime_exchange_ready(...)`:
  - cuando el diagnostico cacheado falla, fuerza `diagnose_exchange(..., force_refresh=true)`.
  - mantiene cache hit directo cuando el diagnostico inicial es OK.
- Tests nuevos:
  - `test_runtime_exchange_ready_forces_refresh_after_cached_failure`
  - `test_runtime_exchange_ready_uses_cached_success_without_forced_refresh`
- Evidencia:
  - `docs/audit/AP_BOT_1029_BIBLIO_VALIDATION_20260305.md`.
- Revalidacion remota post-patch:
  - run `22733869311` -> `success` (`strict=true`, `expect_g9=WARN`).
  - reporte: `docs/audit/PROTECTED_CHECKS_GHA_22733869311_20260305.md`.

### AP-BOT-1016 (guard fail-closed para submit en `live`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nueva variable `LIVE_TRADING_ENABLED` (default `false`);
  - `RuntimeBridge._maybe_submit_exchange_runtime_order(...)` bloquea submit remoto en `mode=live` cuando `LIVE_TRADING_ENABLED=false`;
  - retorna `reason=live_trading_disabled` + `error=LIVE_TRADING_ENABLED=false` para trazabilidad operativa.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_flat_skips_remote_submit or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle or live_skips_submit_when_live_trading_disabled" -q` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`6 passed`).
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1016_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1017 (telemetria de `submit_reason` en runtime)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo estado `runtime_last_remote_submit_reason` persistido por ciclo;
  - `_maybe_submit_exchange_runtime_order(...)` retorna `reason=submitted` cuando el envio remoto fue exitoso.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - assertions nuevas para `runtime_last_remote_submit_reason` en casos:
    - submit exitoso testnet (`submitted`);
    - bloqueo live por flag (`live_trading_disabled`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_meanreversion_submits_sell or live_skips_submit_when_live_trading_disabled or strategy_signal_flat_skips_remote_submit or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1017_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1018 (revalidacion benchmark remoto + fix summary workflow)
- Operativo:
  - ejecutado `Remote Bots Benchmark (GitHub VM)` con defaults:
    - run `22706414197` -> `success`.
  - evidencia registrada en:
    - `docs/audit/BOTS_OVERVIEW_BENCHMARK_GHA_22706414197_20260305.md`.
  - metricas clave:
    - `p95_ms=184.546`
    - `server_p95_ms=0.07`
    - `rate_limit_retries=0`
    - objetivo `p95<300ms`: `PASS`.
- CI workflow:
  - `/.github/workflows/remote-benchmark.yml`:
    - `Build summary` pasa regex de `grep -E` a comillas simples para evitar evaluacion de backticks como comandos shell.

### AP-BOT-1019 (limpieza de `runtime_last_remote_submit_reason`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - limpia `runtime_last_remote_submit_reason` al salir de runtime real y cuando `exchange_ready` falla.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "live_skips_submit_when_live_trading_disabled or clears_submit_reason_when_runtime_exits_real_mode or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1019_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1020 (reconciliacion avanzada `PENDING_CANCEL` / `EXPIRED_IN_MATCH`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `NEW/PENDING_CANCEL` ya no pisa `PARTIALLY_FILLED` cuando existe fill parcial;
  - si `filled_qty>=qty`, cierra terminal en `FILLED`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - nuevo `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "keeps_absent_open_order_open_when_order_status_is_new or keeps_partial_state_when_order_status_is_pending_cancel or updates_absent_open_order_partial_fill_from_order_status or marks_absent_open_order_expired_in_match_terminal or marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`5 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Revalidacion bibliografica:
  - `docs/audit/AP_BOT_1020_BIBLIO_VALIDATION_20260305.md`.

### AP-BOT-1021 (revalidacion remota protected checks post runtime)
- Operativo:
  - ejecutado `Remote Protected Checks (GitHub VM)` con defaults y `strict=true`:
    - run `22731722376` -> `success`.
  - evidencia registrada en:
    - `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.
- Campos de cierre:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`

### AP-BOT-1022 (refresh de closeout no-live)
- `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`:
  - agregado refresh de evidencia del dia (`2026-03-05`) con runs:
    - benchmark `22706414197` (`PASS`),
    - protected checks `22731722376` (`PASS`).
- Estado operativo consolidado:
  - no-live/testnet se mantiene `GO`;
  - LIVE permanece `NO GO` por decision operativa (fase final).

## 2026-03-04

### AP-8001 (BFF fail-closed de mock fallback)
- `rtlab_dashboard/src/lib/security.ts`:
  - agregado `isProtectedRuntimeEnv` (`NODE_ENV=production` o `APP_ENV in {staging, production, prod}`).
  - agregado `shouldFallbackToMockOnBackendError` con politica fail-closed:
    - en entornos protegidos siempre `false`;
    - con `USE_MOCK_API=false`, siempre `false`;
    - solo permite fallback en no-protegido + flag `ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR=true`.
- `rtlab_dashboard/src/app/api/[...path]/route.ts`:
  - elimina helper local y usa regla centralizada.
- `rtlab_dashboard/src/lib/events-stream.ts`:
  - fallback a stream mock en error de backend ahora usa regla centralizada.
- `rtlab_dashboard/src/lib/security.test.ts`:
  - nuevos tests para bloqueo en `production`/`staging` y comportamiento en `local`.
- Evidencia:
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).

### AP-8002 (security CI: instalacion robusta de gitleaks)
- `.github/workflows/security-ci.yml`:
  - `actions/checkout@v4` pasa a `fetch-depth: 0` para evitar falsos positivos de `gitleaks` al usar baseline historica sobre clones shallow.
  - `setup-python` alineado a `3.11` (coherente con workflows operativos remotos).
  - reemplazada instalacion via script `master/install.sh` por descarga de release oficial:
    - `gitleaks_8.30.0_linux_x64.tar.gz`
  - agregado `curl` con retries y timeout para runners GitHub.
  - agregado fallback a install script versionado (`v8.30.0`) si la descarga tarball falla.
  - agregado check explicito de binario ejecutable (`$RUNNER_TEMP/bin/gitleaks`) con error claro si no queda instalado.
  - export `PATH` en el mismo step antes de `gitleaks version` (evita falso fail por `GITHUB_PATH` no aplicado aun).
  - extraccion directa a `RUNNER_TEMP/bin` y validacion de `gitleaks version`.
  - `scripts/security_scan.sh` ahora toma baseline canónica en `docs/security/gitleaks-baseline.json` (o `GITLEAKS_BASELINE_PATH`), evitando depender de archivos `artifacts/` no versionados en CI.
- Nuevo archivo versionado:
  - `docs/security/gitleaks-baseline.json` (redactado).
- Resultado esperado:
  - reducir fallos espurios en `Install security tooling` y en `Run security scan (strict)` por baseline/history mismatch, facilitando cierre de `FM-SEC-004` al rerun del workflow.
- Evidencia de cierre:
  - GitHub Actions `Security CI` run `22697627615` en `success` (job `security` id `65807494809`).
  - `FM-SEC-004` actualizado a `CERRADO` en `docs/audit/FINDINGS_MASTER_20260304.md`.

### AP-8007 (unificacion de thresholds de gates)
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - eliminado fallback de thresholds a `knowledge/policies/gates.yaml`;
  - si no hay config valida, se usa `default_fail_closed` (`pbo_max=0.05`, `dsr_min=0.95`).
- `rtlab_autotrader/rtlab_core/rollout/gates.py`:
  - `GateEvaluator` usa `config/policies/gates.yaml` como fuente canonica;
  - en ausencia/error de config, marca `source_mode=default_fail_closed` y exige `pbo/dsr`.
- Test agregado:
  - `rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).

### AP-8011 (optimizacion incremental de `/api/v1/bots`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - evita `learning_service.load_all_recommendations()` en cada request cuando hay cache hit;
  - filtra indexado de `runs` por `strategy_ids` presentes en pools de bots;
  - limita runs indexados por `(strategy_id, mode)` con `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE` (default `250`);
  - expone nuevos campos de perfilado interno en debug: `runs_indexed`, `runs_skipped_outside_pool`, `max_runs_per_strategy_mode`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Nota:
  - requiere rerun remoto de benchmark para verificar impacto final de `p95` en entorno productivo.

### AP-8003 (runtime reconcile: open orders + cierre de ausentes)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_reconcile` usa `OMS.open_orders()` como espejo local para comparar contra `GET /api/v3/openOrders`.
  - agregado cierre local de ordenes abiertas ausentes en exchange luego de `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`).
  - evita desync falso por ordenes locales ya cerradas (`FILLED`/terminal) fuera de `openOrders`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`.
  - nuevo `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).

### AP-8012 (`breaker_events` strict por defecto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `breaker_events_integrity(..., strict=True)` cambia a fail-closed por defecto.
  - endpoint `GET /api/v1/diagnostics/breaker-events` ahora usa `strict=true` por defecto.
- `scripts/ops_protected_checks_report.py`:
  - `--strict` pasa a default `true`.
  - nuevo flag `--no-strict` para override explícito.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - ajuste de pruebas para default estricto + override no estricto.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.

### Cleanroom docs + staging no-live (docops/devops)
- Limpieza de documentacion vigente/historica:
  - movidos a `docs/_archive/*`: `BACKTESTS_RESEARCH_SYSTEM_FINAL.md`, `MASS_BACKTEST_DATA.md`, `research_mass_backtests.md`, `research_stack.md`, `FINAL_RELEASE_REPORT.md`, `DEPENDENCIES_COMPAT.md`, `UI_UX_RESEARCH_FIRST_FINAL.md`, `CONVERSACION_SCREENSHOTS_REFERENCIA_UNIVERSOS_COSTOS_GATES_EXCHANGES.txt`.
  - agregado `docs/_archive/README_ARCHIVE.md` con disclaimer de no vigencia.
- Indices nuevos para lectura canonica:
  - `docs/START_HERE.md`
  - `docs/audit/INDEX.md`
- Seguridad documental:
  - `docs/security/LOGGING_POLICY.md` (alineado a CWE-532).
  - `docs/SECURITY.md` actualizado con referencia obligatoria a policy de logging seguro.
- Runbooks de staging y rollback:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- Verificacion operativa no-live (staging):
  - backend `https://bot-trading-ia-staging.up.railway.app` en `mode=paper`, `runtime_ready_for_live=false`.
  - frontend `https://bot-trading-ia-staging.vercel.app` accesible (`/login` OK).
- Hardening complementario de docs/runbooks:
  - `docs/runbooks/RAILWAY_STORAGE_PERSISTENCE.md` elimina ejemplo con `--password` en CLI y usa env var.

### AP-BOT-1001/AP-BOT-1002 (coherencia estrategia + fail-closed feature-set)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`
  - agregado `ExecutionProfile` por familia (`trend_pullback`, `breakout`, `meanreversion`, `defensive`, `trend_scanning`);
  - `StrategyRunner.run(...)` deja de usar hardcodes globales (`2.0/3.0/12`) y aplica stop/take/trailing/time-stop por perfil;
  - `trend_scanning` ahora devuelve familia efectiva del sub-regimen para usar perfil correcto;
  - `reason_code` de trades pasa a reflejar familia real ejecutada.
- `rtlab_autotrader/rtlab_core/web/app.py`
  - `_infer_orderflow_feature_set(...)` cambia fallback a `orderflow_unknown` (`missing_fail_closed`);
  - `validate_promotion` agrega check `known_feature_set`;
  - baseline picker no bloquea por feature-set cuando candidato esta en `orderflow_unknown` (evita falsos `No baseline`).
- Tests agregados:
  - `rtlab_autotrader/tests/test_backtest_execution_profiles.py`
  - `rtlab_autotrader/tests/test_web_feature_set_fail_closed.py`
- Evidencia de validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_backtest_execution_profiles.py rtlab_autotrader/tests/test_web_feature_set_fail_closed.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.

### AP-BOT-1003 (estabilizacion de latencia en `/api/v1/bots`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado `BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT` (default `40`);
  - en polling default (`recent_logs` sin explicitar), se auto-desactiva carga de logs recientes con muchos bots;
  - `recent_logs=true` explicito mantiene logs habilitados;
  - cache key de overview distingue `source=default|explicit`;
  - debug perf expone `logs_auto_disabled`, threshold y `bots_count`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_supports_recent_logs_query_overrides_and_cache_key or bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override or bots_overview_perf_headers_and_debug_payload" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).

### AP-BOT-1004 (runtime testnet sin fill sintético)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._reconcile(...)` ahora parsea `openOrders` con `qty/symbol/side` y sincroniza OMS local;
  - `RuntimeBridge.sync_runtime_state(...)` deja progresion de fill incremental solo para `paper` (en `testnet/live` no simula fills);
  - reconciliacion se calcula sobre snapshot OMS ya sincronizado con exchange.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.

### AP-BOT-1005 (cancel remoto idempotente por `client_order_id`)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado parser comun de `openOrders` con `client_order_id/order_id`;
  - agregado cancel remoto en runtime para `testnet/live` (`DELETE /api/v3/order`) durante `stop/kill/mode_change`;
  - idempotencia temporal de cancel con:
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC=30` (default),
    - `RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS=2000` (default);
  - si exchange responde `unknown order`, se toma como cancel idempotente exitoso.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_stop_testnet_cancels_remote_open_orders_idempotently`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.

### AP-BOT-1006 (submit remoto idempotente, default-off)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado submit remoto opcional para runtime `real` en `testnet/live` (`POST /api/v3/order`) con `newClientOrderId` estable por ventana;
  - nuevo control idempotente local:
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC` (default `60`),
    - `RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS` (default `2000`);
  - manejo idempotente de duplicate submit Binance (`code=-2010`, `duplicate order`);
  - feature flag segura por defecto:
    - `RUNTIME_REMOTE_ORDERS_ENABLED=false`,
    - parametros de semilla `RUNTIME_REMOTE_ORDER_NOTIONAL_USD`, `RUNTIME_REMOTE_ORDER_SYMBOL`, `RUNTIME_REMOTE_ORDER_SIDE`;
  - estado runtime ahora incluye:
    - `runtime_last_remote_submit_at`,
    - `runtime_last_remote_client_order_id`,
    - `runtime_last_remote_submit_error`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default`;
  - nuevo `test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1007 (reconciliacion de posiciones por account snapshot)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado fetch firmado de `/api/v3/account` para runtime `testnet/live` y parser de balances spot a posiciones;
  - `RuntimeBridge` expone posiciones reconciliadas por account snapshot cuando la fuente remota responde OK;
  - fallback: si account falla, se mantiene snapshot derivado de `openOrders` (sin frenar loop);
  - nuevo estado runtime:
    - `runtime_account_positions_ok`,
    - `runtime_account_positions_verified_at`,
    - `runtime_account_positions_reason`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot`;
  - nuevo `test_runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1008 (costos runtime por fill-delta)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - agregado acumulador de costos runtime en `RuntimeBridge` con deltas de fill (`OMS`) para fees/spread/slippage/funding;
  - nuevos campos en `execution_metrics_snapshot`:
    - `fills_count_runtime`,
    - `fills_notional_runtime_usd`,
    - `fees_total_runtime_usd`,
    - `spread_total_runtime_usd`,
    - `slippage_total_runtime_usd`,
    - `funding_total_runtime_usd`,
    - `total_cost_runtime_usd`,
    - `runtime_costs`.
  - reset de acumuladores al evento `start`/`mode_change` en runtime real.
  - `build_execution_metrics_payload` fail-closed fuerza costos runtime a cero cuando telemetry es sintetica.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_execution_metrics_accumulate_costs_from_fill_deltas`;
  - `test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic` ahora valida `runtime_costs` en cero.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.

### AP-BOT-1009 (hardening `--password` + guard CI)
- `.github/workflows`:
  - `security-ci.yml` agrega guard fail-closed para detectar `--password` en workflows/`scripts/*.ps1`.
- `scripts`:
  - `seed_bots_remote.py` y `check_storage_persistence.py`:
    - `--password` pasa a deprecado/inseguro;
    - uso por CLI queda bloqueado por defecto (solo se habilita con `ALLOW_INSECURE_PASSWORD_CLI=1`);
    - fallback de password remoto prioriza `RTLAB_ADMIN_PASSWORD`.
  - `run_bots_benchmark_sweep_remote.ps1` elimina `--password` en comandos python y usa env temporal.
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\\Program Files\\Git\\bin\\bash.exe scripts/security_scan.sh` -> PASS.
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.

### AP-BOT-1010 (cierre no-live formal)
- Nuevo artefacto:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- Resultado consolidado:
  - no-live/testnet: GO.
  - LIVE: NO GO (postergado por decision operativa, pendiente tramo final con APIs reales/canary).

### AP-BOT-1011 (submit runtime por intencion de estrategia, fail-closed)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo `RuntimeBridge._runtime_order_intent(...)` para derivar `action/side/symbol/notional` desde estrategia principal por modo;
  - fail-closed cuando no hay estrategia principal valida o esta deshabilitada (`action=flat`);
  - nuevo control de enfriamiento de submit:
    - `RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC` (default `120`);
  - nuevo flujo `RuntimeBridge._maybe_submit_exchange_runtime_order(...)`:
    - bloquea submit si `risk.allow_new_positions=false`;
    - bloquea submit si ya hay posiciones abiertas por account snapshot;
    - bloquea submit si hay `openOrders` o cooldown activo;
    - conserva idempotencia de `client_order_id` ya implementada en AP previos.
  - estado runtime ampliado con trazabilidad de senal:
    - `runtime_last_signal_action`,
    - `runtime_last_signal_reason`,
    - `runtime_last_signal_strategy_id`,
    - `runtime_last_signal_symbol`,
    - `runtime_last_signal_side`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit`;
  - agregado `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Nota de estado:
  - reduce brecha de `FM-EXEC-001/FM-EXEC-005` en no-live;
  - LIVE permanece `NO GO` hasta cerrar lifecycle real completo (fills/partial fills/cancel-replace/reconciliacion final).

### Revalidacion bibliografica AP-BOT-1011
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) y declaracion explicita de `NO EVIDENCIA LOCAL` cuando corresponde.

### AP-BOT-1012 (finalizacion de ordenes ausentes con `order status` remoto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge._parse_exchange_open_orders_payload(...)` incorpora `status` remoto cuando existe;
  - nuevo `RuntimeBridge._fetch_exchange_order_status(...)` con `GET /api/v3/order` para resolver estado final de orden ausente en `openOrders`;
  - nuevo `RuntimeBridge._apply_remote_order_status_to_local(...)`:
    - `FILLED` -> cierra en `OrderStatus.FILLED` y ajusta `filled_qty`;
    - `CANCELED/EXPIRED/EXPIRED_IN_MATCH` -> terminal `CANCELED` (o `FILLED` si ya completo);
    - `REJECTED` -> terminal `REJECTED`;
    - `NEW/PARTIALLY_FILLED/PENDING_CANCEL` -> mantiene orden abierta.
  - `_close_absent_local_open_orders(...)` ahora:
    - consulta `order status` antes de cancelar localmente;
    - si orden sigue abierta, la reinyecta en snapshot de reconciliacion para evitar desync falso;
    - si no hay evidencia remota, mantiene fallback conservador a cancel local.
  - `_reconcile(...)` pasa `mode` al cierre de ausentes para habilitar esta resolucion en `testnet/live`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status`;
  - agregado `test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new`;
  - ajuste de regresion en `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace` para cubrir ruta real de grace sin chocar con `cancel_stale`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Nota de estado:
  - mejora cierre de lifecycle de orden en no-live y reduce desync por ausencias transitorias en `openOrders`;
  - LIVE permanece `NO GO` (todavia falta cierre global de runtime end-to-end + riesgos abiertos no-runtime).

### Revalidacion bibliografica AP-BOT-1012
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) y fuentes primarias oficiales cuando falta contrato API especifico.

### AP-BOT-1013 (riesgo del mismo ciclo antes de submit remoto)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeBridge.sync_runtime_state(...)` reordena el flujo: el submit remoto en `testnet/live` ahora corre despues de recalcular riesgo del ciclo actual;
  - el gate de submit usa `self._last_risk` ya actualizado del mismo ciclo (no snapshot atrasado);
  - condicion de submit endurecida:
    - solo si `decision.kill=false`,
    - `running=true`,
    - `killed=false`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Nota de estado:
  - reduce la brecha de `FM-RISK-002` en no-live al evitar submits con riesgo bloqueado en el mismo loop;
  - LIVE sigue `NO GO` por pendientes globales de cierre end-to-end.

### Revalidacion bibliografica AP-BOT-1013
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first (`BIBLIO_INDEX` + `biblio_txt`) para principios de risk management y gates fail-closed.

### AP-BOT-1014 (reuso de account snapshot en submit runtime)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_maybe_submit_exchange_runtime_order(...)` acepta snapshot de cuenta ya resuelto en el ciclo (`account_positions`, `account_positions_ok`);
  - `sync_runtime_state(...)` pasa ese snapshot al submit remoto para evitar segunda llamada a `/api/v3/account` en el mismo loop;
  - mantiene mismo comportamiento funcional (bloqueo si hay posiciones abiertas) con menos llamadas remotas.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell` ahora verifica `account_get == 1` (sin doble fetch de cuenta).
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Nota de estado:
  - reduce overhead de API por ciclo en runtime real no-live;
  - LIVE sigue `NO GO`.

### Revalidacion bibliografica AP-BOT-1014
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - local-first en principios de eficiencia operativa + contrato API oficial para account/order endpoints.

### AP-BOT-1015 (cobertura de estados remotos PARTIALLY_FILLED/REJECTED)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - agregado `test_runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status`;
  - agregado `test_runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status`.
- Objetivo:
  - fijar regresion para mapping de estados remotos ya implementados en runtime (`PARTIALLY_FILLED`, `REJECTED`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Nota de estado:
  - mejora cobertura de lifecycle runtime y reduce riesgo de regresion en reconciliacion no-live.

### Revalidacion bibliografica AP-BOT-1015
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Criterio:
  - misma base local-first usada en AP-BOT-1012 (microestructura de open orders + contrato API oficial).

### Revalidacion bibliografica completa AP-BOT-1006..1010
- Nuevo artefacto:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- Incluye para cada AP:
  - evidencia tecnica exacta en repo;
  - soporte bibliografico local (`BIBLIO_INDEX` + `biblio_txt` con lineas);
  - `NO EVIDENCIA LOCAL` cuando corresponde;
  - complemento exclusivo con fuentes primarias oficiales (Binance, Linux man-pages, Microsoft, MITRE CWE, Kubernetes).

### Auditoria integral de pe a pa (estado actualizado)
- Nuevos artefactos de auditoria:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Consolidacion de estado real:
  - `LIVE`: `NO GO` por runtime de ejecucion real no cerrado end-to-end.
  - `No-live/testnet`: operativo con controles actuales (decision de proyecto: LIVE al final).
- Hallazgos criticos/high registrados en reporte:
  - runtime `testnet/live` aun con loop de fills simulados en `RuntimeBridge`.
  - fallback mock del BFF si falta `BACKEND_API_URL`.
  - scripts/workflows con rutas `--password` (exposicion de secretos en CLI).
  - divergencia de policy `gates` entre `config` y `knowledge`.
  - variabilidad de latencia `/api/v1/bots` en productivo.
- Evidencia de corrida del dia:
  - `./scripts/security_scan.ps1 -Strict` -> PASS.
  - `python -m pytest -q rtlab_autotrader/tests` -> PASS.
  - `npm test -- --run` -> PASS.
  - `npm run lint` -> PASS.
  - `npm run build` -> PASS (warning de charts pendiente).

### AP-7003 hotfix (G9 estricto por modo + evaluate_gates read-only)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `RuntimeSnapshot.checks` cambia `exchange_mode_known` -> `exchange_mode_match` para exigir `runtime_exchange_mode == mode objetivo`.
  - `evaluate_gates(...)` deja de llamar `_sync_runtime_state(..., persist=True)` cuando no recibe `runtime_state`; queda sin efectos de persistencia sobre `bot_state`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode`.
  - nuevo test `test_evaluate_gates_does_not_persist_runtime_state_side_effects`.
  - ajustes en tests G9 para usar `runtime_exchange_mode=\"live\"` en escenarios PASS para LIVE.
- Evidencia:
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_passes_only_when_runtime_contract_is_fully_ready rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode rtlab_autotrader/tests/test_web_live_ready.py::test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers rtlab_autotrader/tests/test_web_live_ready.py::test_evaluate_gates_does_not_persist_runtime_state_side_effects rtlab_autotrader/tests/test_web_live_ready.py::test_live_mode_blocked_when_runtime_engine_is_simulated` -> PASS.
  - `python -m pytest -q rtlab_autotrader/tests/test_web_live_ready.py -k "g9 or runtime_contract_snapshot_defaults_are_exposed_in_status or live_blocked_by_gates_when_requirements_fail or storage_gate_blocks_live_when_user_data_is_ephemeral"` -> PASS.

### AP-7001/AP-7002 completados (runtime exchange-evidence + risk policy wiring)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `evaluate_gates(...)` ahora sincroniza runtime state cuando no se pasa `runtime_state` (reduce bypass por estado stale).
  - `RuntimeSnapshot` agrega checks de exchange (`exchange_connector_ok`, `exchange_order_ok`, `exchange_check_fresh`, `exchange_mode_known`).
  - runtime fail-closed: si engine real no valida connector+order en exchange, fuerza `runtime_telemetry_source=synthetic_v1`.
  - reconciliacion no-paper ahora consulta `GET /api/v3/openOrders` firmado y publica `source/source_ok/source_reason`.
  - runtime risk ahora carga `config/policies/risk_policy.yaml` y aplica hard-kill policy-driven (`daily_loss`/`drawdown`).
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `default_learning_settings().risk_profile` pasa a derivarse desde `config/policies/risk_policy.yaml` (fallback: `MEDIUM_RISK_PROFILE`).
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `_mock_exchange_ok` cubre `openOrders`.
  - nuevo test `test_learning_default_risk_profile_prefers_policy_yaml`.
  - ajustes en tests de `G9` y runtime real para contrato actualizado.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.

### Cierre auditoria PARTE 7/7 (cerebro del bot)
- Se cerro la auditoria de aprendizaje/decision/rollout con evidencia de codigo en:
  - `learning/brain.py`, `learning/service.py`,
  - `src/backtest/engine.py`, `src/research/mass_backtest_engine.py`,
  - `rollout/manager.py`, `rollout/compare.py`, `rollout/gates.py`,
  - `web/app.py`.
- Se agregaron artefactos de cierre para no perder contexto y planificar reparacion sin retrabajo:
  - `docs/audit/FINDINGS_MASTER_20260304.md` (registro maestro de problemas con estado).
  - `docs/audit/ACTION_PLAN_FINAL_20260304.md` (plan final por bloques y dependencias).
- Confirmado:
  - Opcion B sigue obligatoria (`allow_auto_apply=false`, `allow_live=false`).
  - `purged_cv` y `cpcv` quedan implementados en quick backtest/learning rapido.
  - runtime web seguia con payloads sinteticos en endpoints operativos clave (`status`/`execution metrics`) al inicio de la auditoria; mitigado parcialmente en Bloque 1.
- Se deja trazado que faltan 3 bloques no-live para cierre final: runtime real no-live, security CI root protegido y hardening final de operacion/pruebas.

### Bloque 0 iniciado (AP-0001/AP-0002)
- Rama tecnica creada: `feature/runtime-contract-v1`.
- Contrato canonico `RuntimeSnapshot v1` y criterio exacto `G9` documentados en:
  - `docs/audit/AP0001_AP0002_RUNTIME_CONTRACT_V1.md`.
- Implementacion base (sin runtime real aun):
  - `web/app.py` ahora expone metadata de contrato runtime en `/health`, `/status`, `/execution/metrics`.
  - `evaluate_gates` usa evaluacion de contrato runtime para `G9_RUNTIME_ENGINE_REAL`.
- Tests focales agregados y en verde:
  - `test_runtime_contract_snapshot_defaults_are_exposed_in_status`
  - `test_g9_live_passes_only_when_runtime_contract_is_fully_ready`
  - `test_live_mode_blocked_when_runtime_engine_is_simulated`

### Bloque 1 en progreso (AP-1001/AP-1002/AP-1003)
- Wiring runtime aplicado en backend web (`rtlab_autotrader/rtlab_core/web/app.py`):
  - nuevo `RuntimeBridge` acoplado a `OMS + Reconciliation + RiskEngine + KillSwitch`;
  - sincronizacion runtime integrada en `/api/v1/status`, `/api/v1/execution/metrics`, `/api/v1/risk` y `/api/v1/health`;
  - endpoints de control (`bot/mode`, `bot/start`, `bot/stop`, `bot/killswitch`, `control/pause`, `control/safe-mode`) ahora actualizan contrato runtime en cada transicion.
- Payloads operativos ya no usan valores hardcodeados:
  - `build_status_payload` usa `positions` y health derivados del runtime bridge.
  - `build_execution_metrics_payload` usa series/ratios calculados por runtime bridge.
  - `/api/v1/risk` usa snapshot de exposicion/riesgo/reconciliacion del runtime bridge.
- Tests agregados en `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk`
  - `test_runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live`
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or health_reports_storage_persistence_status or storage_gate_blocks_live_when_user_data_is_ephemeral or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `8 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.
- Estado: mitigacion fuerte de `FM-EXEC-001/FM-EXEC-005` en no-live; sigue pendiente wiring de broker/exchange real para LIVE y cierre de gates estrictos de runtime (AP-200x).

### AP-1004 completado (telemetry_source + fail-closed sintetico)
- `build_status_payload`, `build_execution_metrics_payload`, `/api/v1/risk` y `/api/v1/health` exponen guard de telemetria runtime:
  - `runtime_telemetry_source`
  - `runtime_telemetry_ok`
  - `runtime_telemetry_fail_closed`
  - `runtime_telemetry_reason`
- Regla fail-closed aplicada cuando `telemetry_source=synthetic_v1`:
  - `execution_metrics` fuerza metricas conservadoras (ej. `fill_ratio=0`, `maker_ratio=0`, `latency_ms_p95>=999`) para no permitir lecturas falsas de salud operativa.
- Tests agregados/ajustados:
  - `test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic`
  - `test_runtime_contract_snapshot_defaults_are_exposed_in_status` (assert de `telemetry_fail_closed`)
  - `test_runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk` (assert de `telemetry_ok`)
  - `test_rollout_safe_update.py` API e2e ajustado para levantar runtime real no-live en setup (`_ensure_runtime_real_for_rollout_api`).
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or g9_live_passes_only_when_runtime_contract_is_fully_ready or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `6 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `13 passed`.

### AP-2001/AP-2002/AP-2003 completados (gating runtime + breaker strict + bloqueo de evaluacion sintetica)
- AP-2001 (G9 con heartbeat/reconciliacion frescos) reforzado con test especifico:
  - `test_g9_live_fails_when_runtime_heartbeat_is_stale` en `rtlab_autotrader/tests/test_web_live_ready.py`.
- AP-2002 aplicado en diagnostico de `breaker_events`:
  - `GET /api/v1/diagnostics/breaker-events` acepta `strict=true|false`;
  - en modo estricto, `NO_DATA` pasa a fail-closed (`ok=false`);
  - `scripts/ops_protected_checks_report.py` propaga el flag y reporta `breaker_strict_mode`.
  - cobertura nueva:
    - `test_breaker_events_integrity_endpoint_no_data_non_strict_ok`
    - `test_breaker_events_integrity_endpoint_no_data_strict_fail_closed`
- AP-2003 aplicado en `POST /api/v1/rollout/evaluate-phase`:
  - fail-closed explicito cuando `runtime_telemetry_guard.ok=false` (telemetry sintetica);
  - se registra log `rollout_phase_eval_blocked` con fase + fuente de telemetria.
- Cobertura nueva:
  - `test_rollout_api_evaluate_phase_fail_closed_when_runtime_telemetry_synthetic` en `rtlab_autotrader/tests/test_rollout_safe_update.py`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_heartbeat_is_stale or runtime_contract_snapshot_defaults_are_exposed_in_status or runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live or live_mode_blocked_when_runtime_engine_is_simulated" -q` -> `7 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint_pass or breaker_events_integrity_endpoint_no_data_non_strict_ok or breaker_events_integrity_endpoint_no_data_strict_fail_closed or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-3001 completado (Purged CV + embargo real)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`:
  - `validation_mode=purged-cv` deja de ser hook y ejecuta split OOS real con `purge_bars + embargo_bars`;
  - `validation_summary` ahora registra `purge_bars`, `embargo_bars`, `oos_bars`, `is_bars` y rango temporal OOS;
  - base de configuracion (`purge/embargo`) queda lista para CPCV.
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `POST /api/v1/backtests/run` acepta `purge_bars` y `embargo_bars` (opcionales, enteros `>=0`);
  - `_learning_eval_candidate` usa `settings.learning.validation` para resolver modo (`walk-forward`/`purged-cv`/`cpcv`).
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `validation.purged_cv` pasa a `implemented=true`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_backtests_run_supports_purged_cv_and_cpcv`.
  - `test_learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled`.
  - `test_learning_research_loop_and_adopt_option_b` valida estado de `purged_cv/cpcv`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_research_loop_and_adopt_option_b" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

### AP-3002 completado (CPCV real en learning/research rapido)
- `rtlab_autotrader/rtlab_core/src/backtest/engine.py`:
  - `validation_mode=cpcv` ya no es hook-only y ejecuta paths combinatoriales (`n_splits`, `k_test_groups`, `max_paths`);
  - cada path aplica trimming por `purge_bars + embargo_bars`, se evalua con `StrategyRunner` y se consolida en `validation_summary`.
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `POST /api/v1/backtests/run` acepta `cpcv_n_splits`, `cpcv_k_test_groups`, `cpcv_max_paths` (enteros validados);
  - `_learning_eval_candidate` propaga `cpcv_*` desde `settings.learning.validation`.
- `rtlab_autotrader/rtlab_core/learning/service.py`:
  - `validation.cpcv` pasa a `implemented=true` con `enforce` atado a `enforce_cpcv`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_backtests_run_supports_purged_cv_and_cpcv` ahora valida `cpcv` en `200` + `paths_evaluated>=1`.
  - nuevo `test_learning_eval_candidate_supports_cpcv_mode_from_settings`.
  - `test_learning_research_loop_and_adopt_option_b` exige `cpcv.implemented=true`.
- Validacion:
  - `python -m py_compile rtlab_autotrader/rtlab_core/src/backtest/engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_supports_purged_cv_and_cpcv or learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled or learning_eval_candidate_supports_cpcv_mode_from_settings or learning_research_loop_and_adopt_option_b" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "backtests_run_rejects_synthetic_source or event_backtest_engine_runs_for_crypto_forex_equities or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.

### AP-3003 completado (learning eval fail-closed sin fallback silencioso)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `_learning_eval_candidate` deja de usar fallback silencioso a runs cache/dummy;
  - ante falta de dataset real o `dataset_source` sintetico, ahora lanza `ValueError` fail-closed.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_learning_research_loop_and_adopt_option_b` se estabiliza con evaluator stub explicito;
  - nuevo `test_learning_run_now_fails_closed_when_real_dataset_missing`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "learning_research_loop_and_adopt_option_b or learning_run_now_fails_closed_when_real_dataset_missing" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-3004 completado (separar `anti_proxy` y `anti_advanced` en research)
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`:
  - resultados de `run_job` ahora incluyen `anti_proxy`, `anti_advanced` y `anti_overfitting` (alias legacy de `anti_advanced`);
  - `_apply_advanced_gates` deja trazabilidad separada de proxy vs gates avanzados;
  - persistencia de batch (`kpi_summary_json`/`artifacts_json`) prioriza valores de `anti_advanced` y conserva `anti_proxy`.
- `rtlab_autotrader/tests/test_mass_backtest_engine.py`:
  - se amplian asserts en `test_run_job_persists_results_and_duckdb_smoke_fallback`;
  - nuevo `test_advanced_gates_exposes_anti_proxy_and_anti_advanced_separately`.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`.

### AP-3005 completado (CompareEngine fail-closed cuando feature_set es unknown)
- `rtlab_autotrader/rtlab_core/rollout/compare.py`:
  - `_extract_orderflow_feature_set` ya no hace fallback silencioso a `orderflow_on`;
  - nuevo check `known_feature_set` bloquea compare cuando baseline/candidato quedan `orderflow_unknown`.
- `rtlab_autotrader/tests/test_rollout_safe_update.py`:
  - `_sample_run` pasa a declarar `orderflow_feature_set` explicito;
  - `test_compare_engine_improvement_rules` agrega caso fail-closed por unknown.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

### AP-3006 completado (strict_strategy_id obligatorio en research/promotion no-demo)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - research mass/beast propaga `execution_mode` y fuerza `strict_strategy_id` en `_mass_backtest_eval_fold` para no-demo;
  - `POST /api/v1/research/mass-backtest/mark-candidate` bloquea candidatos sin `strict_strategy_id=true` en no-demo;
  - `validate_promotion/promote` agregan constraint `strict_strategy_id_non_demo`.
- `rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py`:
  - resultados incluyen `strict_strategy_id` + `execution_mode` y se persisten en `params_json/artifacts_json`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo` nuevo;
  - `test_mass_backtest_research_endpoints_and_mark_candidate` y `test_runs_validate_and_promote_endpoints_smoke` actualizados.
- Validacion:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo or runs_validate_and_promote_endpoints_smoke" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `14 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> `14 passed`.

### AP-4001 (security CI root) - versionado tecnico
- Se versiona `/.github/workflows/security-ci.yml` en rama tecnica (`feature/runtime-contract-v1`, commit `0dbf55d`).
- Contenido del workflow:
  - instala `pip-audit` + `gitleaks`,
  - ejecuta `scripts/security_scan.sh` en modo estricto,
  - sube artifacts `artifacts/security_audit/`.
- Validacion local de sintaxis:
  - parse YAML de workflow con `python + yaml.safe_load` -> `OK_WORKFLOW`.
- Pendiente para cierre operativo:
  - corrida verde en GitHub Actions.
- Evidencia remota inicial:
  - run `22674323602` (evento `push`) en `failure`;
  - causa: paso `Install security tooling` del job `security`.
- Fix incremental:
  - instalacion de `gitleaks` migrada a `"$RUNNER_TEMP/bin"` + `GITHUB_PATH` para evitar error de permisos.

### AP-4002 completado (branch protection con required check security)
- Proteccion de rama `main` aplicada por API:
  - `required_status_checks.strict=true`
  - `required_status_checks.contexts=["security"]`
- Evidencia de verificacion:
  - `PROTECTION_SET_OK contexts=security`
  - `PROTECTION_VERIFY strict=True contexts=security enforce_admins=False`
- Resultado:
  - merge a `main` queda condicionado al check `security`.

### AP-4003 completado (lockout/rate-limit login backend compartido)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - `LoginRateLimiter` ahora soporta backend `sqlite|memory` (default `sqlite`).
  - nuevos envs:
    - `RATE_LIMIT_LOGIN_BACKEND`
    - `RATE_LIMIT_LOGIN_SQLITE_PATH`
  - persistencia de estado de login en tabla `auth_login_rate_limit` para compartir lockout/rate-limit entre instancias.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_auth_login_rate_limit_and_lock_guard` ajustado a `backend="memory"` para estabilidad deterministica.
  - nuevo `test_auth_login_rate_limit_shared_sqlite_backend_across_instances`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_and_lock_guard or auth_login_rate_limit_shared_sqlite_backend_across_instances" -q` -> `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_and_admin_protection or api_general_rate_limit_guard or api_expensive_rate_limit_guard" -q` -> `3 passed`.

### AP-5001 completado (suite E2E critica backend)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo test `test_e2e_critical_flow_login_backtest_validate_promote_rollout`.
  - helper `_force_runs_rollout_ready` para datos deterministas en gates/compare durante la suite.
- Flujo cubierto:
  - `login -> backtests/run -> runs/validate_promotion -> runs/promote -> rollout/advance`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "e2e_critical_flow_login_backtest_validate_promote_rollout or runs_validate_and_promote_endpoints_smoke" -q` -> `2 passed`.

### AP-5002 completado (chaos/recovery runtime)
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - helper nuevo `_mock_exchange_down`.
  - nuevo `test_exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect`.
  - nuevo `test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers`.
- Escenarios cerrados:
  - exchange down/reconnect en testnet (diagnose + gates).
  - desync de reconciliacion runtime (`G9` FAIL -> PASS tras refresh).
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers or g9_live_fails_when_runtime_heartbeat_is_stale or exchange_diagnose_passes_with_env_keys_and_mocked_exchange" -q` -> `4 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "auth_login_rate_limit_shared_sqlite_backend_across_instances or e2e_critical_flow_login_backtest_validate_promote_rollout or exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `4 passed`.

### AP-5003 completado (alertas operativas minimas)
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - nuevo `build_operational_alerts_payload`.
  - `/api/v1/alerts` agrega alertas derivadas (`include_operational=true` por default):
    - `ops_drift`, `ops_slippage_anomaly`, `ops_api_errors`, `ops_breaker_integrity`.
  - nuevos umbrales por ENV: `OPS_ALERT_SLIPPAGE_P95_WARN_BPS`, `OPS_ALERT_API_ERRORS_WARN`, `OPS_ALERT_BREAKER_WINDOW_HOURS`, `OPS_ALERT_DRIFT_ENABLED`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - nuevo `test_alerts_include_operational_alerts_for_drift_slippage_api_and_breaker`.
  - nuevo `test_alerts_operational_alerts_clear_when_runtime_recovers`.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers or breaker_events_integrity_endpoint_warn_when_unknown_ratio_high" -q` -> `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> `2 passed`.

### AP-6001 completado (decision final de hallazgos)
- Se versiona `docs/audit/FINDINGS_DECISION_MATRIX_20260304.md` con decision final por `FM-*`.
- Snapshot de cierre del plan:
  - `CERRADO=12`
  - `MITIGADO=8`
  - `ABIERTO=6`
- Abiertos priorizados para fase siguiente:
  - `FM-EXEC-001`, `FM-EXEC-002`, `FM-EXEC-005`, `FM-QUANT-008`, `FM-RISK-002`, `FM-RISK-003`.

### AP-6002 completado (politica formal de biblio_raw/metadatos)
- Nueva politica: `docs/reference/BIBLIO_ACCESS_POLICY.md`.
- Se formaliza:
  - `biblio_raw`/`biblio_txt` no versionados en git.
  - versionado obligatorio de metadatos/hashes en `docs/reference/BIBLIO_INDEX.md`.
  - flujo canonico de actualizacion con `python scripts/biblio_extract.py`.

### Auditoria integral (comite senior) + evidencia operativa
- Se ejecuto auditoria E2E del sistema (AppSec/DevSecOps, ejecucion, quant/backtests, risk, SRE, QA, UX) con evidencia por rutas y lineas.
- Resultado de go/no-go actualizado: **NO GO para LIVE** por bloqueantes tecnicos de runtime real.
- Evidencia de ejecucion local en esta corrida:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict` -> PASS (`pip-audit` runtime/research sin vulnerabilidades conocidas + `gitleaks` sin leaks).
  - `python -m pytest rtlab_autotrader/tests --collect-only` -> `126 tests collected`.
  - `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - `npm --prefix rtlab_dashboard run lint` -> PASS.
- Hallazgos criticos consolidados:
  - runtime live en backend web todavia desacoplado de OMS/risk/reconciliacion reales;
  - payloads sinteticos en endpoints de estado/ejecucion/riesgo (estado previo, mitigado parcialmente en Bloque 1);
  - `breaker_events` queda fail-closed solo en modo estricto (`strict=true`).
- CI/security:
  - en root siguen activos solo `remote-benchmark.yml` y `remote-protected-checks.yml`;
  - `/.github/workflows/security-ci.yml` ya versionado en rama tecnica (`0dbf55d`); pendiente push + corrida en GitHub Actions.
- Bibliografia:
  - se confirma `BIBLIO_INDEX.md`;
  - `docs/reference/biblio_raw/` en repo continua sin PDFs versionados (solo `.gitignore`), por lo que se registro faltante para trazabilidad local reproducible.

## 2026-03-03

### Remote protected checks + cierre no-live
- Workflow `Remote Protected Checks (GitHub VM)` ejecutado con defaults (`strict=true`):
  - run `22648114549` -> `success`.
  - artifact `protected-checks-22648114549` con:
    - `ops_protected_checks_gha_22648114549_20260303_234740.json`
    - `ops_protected_checks_gha_22648114549_20260303_234740.md`
    - `protected_checks_stdout.log`
- Resultado canonico del reporte remoto:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en etapa no-live)
  - `breaker_ok=true` (`breaker_status=NO_DATA`)
  - `internal_proxy_status_ok=true`
- Revalidacion de seguridad ejecutada en local (equivalente al job security):
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
  - resultado: `pip-audit` runtime/research sin vulnerabilidades conocidas y `gitleaks` baseline-aware sin leaks.
  - nota de CI: en GitHub Actions del repo root solo se observan workflows remotos (`Remote Bots Benchmark` y `Remote Protected Checks`), por lo que este cierre registra la verificacion estricta local como evidencia operativa de seguridad.
  - para cerrar ese gap, se versiona workflow root `/.github/workflows/security-ci.yml` (security CI bloqueante); queda pendiente push + corrida en GitHub Actions.
- Estado no-live consolidado:
  - benchmark remoto GitHub VM previamente en PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin `429` retries).
  - checks protegidos remotos en PASS.
  - LIVE real continua bloqueado por `G9_RUNTIME_ENGINE_REAL` hasta runtime real.

## 2026-03-02

### Cierre final de bloque (6h real + lint limpio)
- Soak extendido `6h` finalizado en segundo plano con evidencia real:
  - `artifacts/soak_6h_bg_status.json` -> `loops=1440`, `ok=1440`, `errors=0`, `g10_pass=1440`.
  - `artifacts/soak_6h_bg_20260302_132230_DONE.txt`.
- Snapshot operativo final (sin supuestos) ejecutado:
  - `python scripts/build_ops_snapshot.py`
  - evidencia: `artifacts/ops_block2_snapshot_20260302_231911.json` + `.md`.
  - resultado: `block2_provisional_ready=true`, `soak_6h_effective_pass=true`.
- Limpieza de warnings frontend completada:
  - `rtlab_dashboard/src/app/(app)/backtests/page.tsx`: deps de hooks corregidas + memoizacion de `focusTrades` + remocion de variable no usada.
  - `rtlab_dashboard/src/app/(app)/settings/page.tsx`: remocion de estado no usado `learningConfigError`.
  - validacion: `npm --prefix rtlab_dashboard run lint` -> `0 errores, 0 warnings`.
  - validacion: `npm --prefix rtlab_dashboard run test` -> `11 passed`.
- Cierre estricto de checks protegidos preparado:
  - `scripts/build_ops_snapshot.py` agrega:
    - `--ask-password` (prompt de `ADMIN_PASSWORD` cuando falta token),
    - `--require-protected` (falla si no valida endpoints protegidos),
    - checks nuevos en reporte: `protected_checks_complete`, `breaker_integrity_ok`, `internal_proxy_status_ok`, `block2_ready_strict`.
  - nuevo launcher `scripts/run_protected_ops_checks.ps1`:
    - pide password una sola vez,
    - ejecuta `check_storage_persistence --require-persistent`,
    - ejecuta `build_ops_snapshot --require-protected --label ops_block2_snapshot_final`.
- Drill de backup/restore ejecutado y documentado:
  - nuevo script `scripts/backup_restore_drill.py` (usa scripts existentes de backup/restore y valida integridad por SHA256).
  - corrida ejecutada:
    - `python scripts/backup_restore_drill.py`
    - evidencia: `artifacts/backup_restore_drill_20260302_234205.json` + `.md`.
    - resultado: `backup_ok=true`, `restore_ok=true`, `manifest_match=true`.
  - runbook actualizado: `docs/runbooks/BACKUP_RESTORE_USER_DATA.md`.
- Bloque seguridad local (Windows) cerrado:
  - nuevo script `scripts/security_scan.ps1` (equivalente del job CI security sin dependencia de bash).
  - corrida estricta ejecutada:
    - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/security_scan.ps1 -Strict`
    - `pip-audit` runtime/research: sin vulnerabilidades conocidas.
    - `gitleaks` baseline-aware: sin leaks.
  - evidencia refrescada:
    - `artifacts/security_audit/pip-audit-runtime.json`
    - `artifacts/security_audit/pip-audit-research.json`
    - `artifacts/security_audit/gitleaks.sarif`
- Bloque benchmark `/api/v1/bots` (regresión local + endurecimiento remoto):
  - `scripts/benchmark_bots_overview.py` agrega:
    - `--ask-password`,
    - `--require-evidence` (exit `2` cuando no hay cardinalidad mínima),
    - `--require-target-pass` (exit `3` cuando no cumple objetivo p95).
  - nuevo launcher `scripts/run_bots_benchmark_remote.ps1` para ejecutar benchmark remoto estricto en Windows con prompt de password.
  - rerun local ejecutado:
    - `python scripts/benchmark_bots_overview.py --bots 100 --requests 200 --warmup 30 --report-path docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260302_RERUN.md`
    - resultado: `p50=36.914ms`, `p95=55.513ms`, `p99=81.628ms` (PASS `<300ms`).
- Bundle remoto de cierre (operación en 1 comando):
  - nuevo script `scripts/run_remote_closeout_bundle.ps1`.
  - ejecuta secuencialmente con una sola captura de `ADMIN_PASSWORD`:
    - `check_storage_persistence.py --require-persistent`,
    - `build_ops_snapshot.py --require-protected --label ops_block2_snapshot_final`,
    - `benchmark_bots_overview.py` remoto con `--require-evidence` (y opcional `-RequireTargetPass`).

### Handoff + soak tests operativos (traspaso corto)
- Se creo `docs/reference/HANDOFF.md` con contexto de traspaso listo para abrir chat nuevo.
- Se actualizo `docs/truth/SOURCE_OF_TRUTH.md` con estado operativo de hoy:
  - persistencia Railway validada (`G10_STORAGE_PERSISTENCE=PASS`),
  - testnet estable con `G1..G8=PASS`,
  - LIVE sigue bloqueado por `G9` (runtime simulado).
- Se agregaron scripts locales para soak:
  - `scripts/soak_testnet.ps1` (parse fix + soporte `SOAK_ADMIN_PASSWORD`),
  - `scripts/start_soak_20m_background.ps1`,
  - `scripts/start_soak_6h_background.ps1`.
- Smoke corto de soak validado con evidencia local:
  - `ok=7`, `errors=0`, `g10_pass=7`.
- Soak operativo de `20m` ejecutado y finalizado en background:
  - `loops=80`, `ok=80`, `errors=0`, `g10_pass=80`.
- Flujo operativo actualizado: se usa solo soak `20m` + `6h` (sin `8h`).
- Adelanto de bloque (sin esperar cierre de soak 6h):
  - `BacktestEngine` incorpora `strict_strategy_id` opt-in para fail-closed de `strategy_id` no soportado.
  - default sigue compatible (`strict_strategy_id=false`) con fallback legacy a `trend_pullback`.
  - `POST /api/v1/backtests/run` propaga `strict_strategy_id`.
  - tests nuevos:
    - `test_unknown_strategy_falls_back_to_trend_pullback_when_not_strict`
    - `test_unknown_strategy_fails_closed_when_strict_mode_enabled`
    - `test_backtests_run_forwards_strict_strategy_id_flag`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py rtlab_autotrader/tests/test_web_live_ready.py -k "strict_strategy_id_flag or unknown_strategy_fails_closed_when_strict_mode_enabled or unknown_strategy_falls_back_to_trend_pullback_when_not_strict" -q` -> `3 passed`.
- Adelanto de bloque performance `/api/v1/bots`:
  - `ConsoleStore.get_bots_overview(...)` ahora registra timings por etapa (inputs/context/pool/runs_index/kpis/db_reads/db_process/assemble/total).
  - cache interna de overview guarda tambien perf y lo devuelve en `debug_perf=true` (tanto `hit` como `miss`).
  - `bots_overview_slow` agrega `overview_perf` al payload de log.
  - tests actualizados:
    - `test_bots_overview_perf_headers_and_debug_payload`
    - `test_bots_overview_cache_hit_and_invalidation_on_create` (wrapper ajustado a nuevo arg `overview_perf`).
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create" -q` -> `2 passed`.
- Adelanto de bloque `breaker_events` (integridad y diagnostico):
  - nuevo endpoint `GET /api/v1/diagnostics/breaker-events` (auth requerido) con ventana configurable (`window_hours`).
  - integra chequeo de integridad de catalogo `breaker_events`:
    - volumen total/ventana,
    - ratios de `unknown_bot`/`unknown_mode`/`unknown_any`,
    - warning por umbral (`BREAKER_EVENTS_UNKNOWN_RATIO_WARN`) con minimo de eventos (`BREAKER_EVENTS_UNKNOWN_MIN_EVENTS`).
  - tests nuevos:
    - `test_breaker_events_integrity_endpoint_pass`
    - `test_breaker_events_integrity_endpoint_warn_when_unknown_ratio_high`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity" -q` -> `2 passed`.
- Adelanto de bloque seguridad auth interna:
  - `current_user` ahora emite log de seguridad cuando detecta `x-rtlab-role/x-rtlab-user` sin proxy token valido.
  - evento generado: `type=security_auth`, `severity=warn`, `module=auth`.
  - payload incluye `reason` (`missing_proxy_token` o `invalid_proxy_token`), `client_ip`, `path`, `method`.
  - anti-ruido: throttle por `SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC` (default `60s`) para no inundar logs.
  - test ajustado:
    - `test_internal_headers_require_proxy_token` ahora valida bloqueo + evidencia de logs `security_auth`.
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token" -q` -> `1 passed`.
- Adelanto de bloque rotacion `INTERNAL_PROXY_TOKEN`:
  - soporte de rotacion con ventana de gracia:
    - `INTERNAL_PROXY_TOKEN` (token activo),
    - `INTERNAL_PROXY_TOKEN_PREVIOUS`,
    - `INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT` (ISO8601).
  - `current_user` ahora acepta token previo solo si no expiro; al expirar se rechaza (`reason=expired_previous_token`).
  - nuevo endpoint admin: `GET /api/v1/auth/internal-proxy/status` para verificar estado de rotacion sin exponer secretos.
  - tests nuevos:
    - `test_internal_proxy_allows_previous_token_with_future_expiry`
    - `test_internal_proxy_rejects_previous_token_when_expired`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_proxy" -q` -> `2 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "internal_headers_require_proxy_token or internal_proxy_allows_previous_token_with_future_expiry or internal_proxy_rejects_previous_token_when_expired" -q` -> `3 passed`.
- Adelanto de bloque performance `/api/v1/bots` (scope de KPIs):
  - `ConsoleStore.get_bots_overview(...)` ahora calcula KPIs solo para estrategias presentes en pools de bots (`strategies_in_pool_count`) y no para todo el registry.
  - objetivo: reducir CPU en `stage_kpis_ms` cuando hay muchas estrategias no asignadas.
  - test nuevo:
    - `test_bots_overview_only_computes_kpis_for_strategies_in_pool`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_only_computes_kpis_for_strategies_in_pool" -q` -> `1 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `4 passed`.
- Adelanto de bloque performance `/api/v1/bots` (logs prefiltrados por bot_ref):
  - tabla `logs` incorpora flag materializado `has_bot_ref` (0/1).
  - migracion incremental al boot:
    - agrega columna si falta,
    - crea indice `idx_logs_has_bot_ref_id`,
    - backfill acotado por ventana reciente (`BOTS_LOGS_REF_BACKFILL_MAX_ROWS`, default `50000`).
  - `add_log(...)` ahora persiste `has_bot_ref` en escritura.
  - `get_bots_overview(...)` usa `WHERE has_bot_ref = 1` para cargar logs recientes de bots (fallback legacy si falta columna), reduciendo parseo de logs no relacionados.
  - `debug_perf.overview` agrega:
    - `logs_prefilter_has_bot_ref`
    - `logs_rows_read`
  - test nuevo:
    - `test_logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated" -q` -> `1 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `5 passed`.
- Adelanto de bloque performance `/api/v1/bots` (materializacion `log_bot_refs`):
  - nueva tabla `log_bot_refs(log_id, bot_id)` + indice `idx_log_bot_refs_bot_id_log_id`.
  - `add_log(...)` ahora indexa refs de bots en tiempo de escritura (desde `related_ids`, `payload.bot_id`, `payload.bot_ids[]`).
  - migracion/backfill incremental para DB legacy (`_backfill_log_bot_refs`) con ventana controlada por `BOTS_LOGS_REF_BACKFILL_MAX_ROWS`.
  - `get_bots_overview(...)` pasa a leer logs recientes via join `log_bot_refs -> logs` (prefilter por bots target), con fallback a `has_bot_ref`/legacy.
  - `debug_perf.overview.logs_prefilter_mode` ahora distingue `log_bot_refs`, `has_bot_ref`, `legacy_full_logs`.
  - tests nuevos:
    - `test_log_bot_refs_table_is_populated_and_used_in_overview`
  - validacion ejecutada:
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "log_bot_refs_table_is_populated_and_used_in_overview or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated" -q` -> `2 passed`.
    - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview_perf_headers_and_debug_payload or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_only_computes_kpis_for_strategies_in_pool or logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated or log_bot_refs_table_is_populated_and_used_in_overview or bots_overview_scopes_kills_by_bot_and_mode" -q` -> `6 passed`.
- Adelanto de bloque operativo soak 6h (resume fail-safe):
  - `scripts/soak_testnet.ps1` ahora soporta reanudacion por segmento sin perder acumulados:
    - `StartIter`, `TotalLoops`,
    - offsets `OffsetOk/OffsetErrors/OffsetG10Pass`,
    - override de rutas `StatusPath/LogPath/DonePath`,
    - preservacion de `StartedAt`.
  - nuevo launcher `scripts/resume_soak_6h_background.ps1`:
    - detecta status existente (`soak_6h_bg_status.json`),
    - calcula iteraciones restantes,
    - evita duplicar ejecucion si ya hay proceso activo,
    - relanza en background continuando counters y log principal.
  - validacion de sintaxis PowerShell:
    - parser OK en `scripts/soak_testnet.ps1`.
    - parser OK en `scripts/resume_soak_6h_background.ps1`.
- Adelanto de bloque 2 operativo (cierre provisional mientras corre soak 6h):
  - nuevo script `scripts/build_ops_snapshot.py` para snapshot consolidado de operacion:
    - consume health remoto (sin auth) + artefactos de soak locales,
    - opcion `--assume-soak-6h-from-20m` para cierre temporal solicitado por usuario,
    - opcion `--assume-soak-6h-from-1h` para cierre temporal basado en soak 1h,
    - genera reporte JSON + Markdown en `artifacts/ops_block2_snapshot_<timestamp>.*`.
  - corrida ejecutada (modo provisional):
    - `python scripts/build_ops_snapshot.py --assume-soak-6h-from-20m`
    - resultado: `block2_provisional_ready=true` con nota explicita de suposicion temporal.
  - validacion ejecutada:
    - `python -m py_compile scripts/build_ops_snapshot.py` -> `OK`.
- Adelanto operativo soak abreviado 1h:
  - nuevo launcher `scripts/start_soak_1h_background.ps1` (`240 loops x 15s`) para ejecucion en segundo plano.
  - sintaxis PowerShell validada via parser: `OK`.
- Cierre de tramo con criterio valedero `1h`:
  - soak `1h` ejecutado y completado:
    - `loops=240`, `ok=240`, `errors=0`, `g10_pass=240`, `done=true`.
  - snapshot operativo de cierre generado con:
    - `python scripts/build_ops_snapshot.py --assume-soak-6h-from-1h`
  - evidencia:
    - `artifacts/soak_1h_bg_status.json`
    - `artifacts/soak_1h_bg_*_DONE.txt`
    - `artifacts/ops_block2_snapshot_20260302_211848.json`
    - `artifacts/ops_block2_snapshot_20260302_211848.md`
  - `build_ops_snapshot.py` ahora reporta `g10_effective_pass` y permite inferencia `PASS_INFERRED_FROM_SOAK` cuando `gates` no esta disponible por falta de token.
- Validacion integral no-live (backend + frontend):
  - backend: `python -m pytest rtlab_autotrader/tests -q` -> `124 passed`.
  - frontend: `npm --prefix rtlab_dashboard run test` -> `11 passed`.
  - frontend lint: `npm --prefix rtlab_dashboard run lint` -> `0 errores, 0 warnings`.
  - nota operativa: ejecutar pytest desde la raiz del repo para resolver correctamente `config/policies/*`.

## 2026-03-01

### Bloque 15: cierre hardening + limpieza de repo (commit limpio)
- `.gitignore` endurecido:
  - se ignoran `artifacts/`, `backups/`, `__pycache__/`, `*.pyc`.
  - se ignora bibliografia cruda local `docs/reference/biblio_raw/*` (manteniendo `.gitignore` del directorio).
- `scripts/security_scan.sh` corregido:
  - flujo `gitleaks` baseline-aware.
  - usa baseline si existe `artifacts/security_audit/gitleaks-baseline.json`.
  - sin baseline, ejecuta modo estricto con `gitleaks git`.
  - elimina falso warning de “gitleaks no instalado” cuando el binario esta presente.
- CI de seguridad:
  - `rtlab_autotrader/.github/workflows/ci.yml` agrega job `security` bloqueante.
  - ejecuta `pip-audit` + `gitleaks` y sube artefactos de auditoria.
  - ajuste del job Python para correr en `rtlab_autotrader` (coherente con `pyproject.toml`).
- Config local exchange:
  - `rtlab_autotrader/user_data/config/exchange_binance_spot.json` verificado con placeholders de ENV (sin claves reales).
- Requisitos:
  - `requirements-runtime.txt` y `requirements-research.txt` auditados (pip-audit sin vulns reportadas en esta corrida).

## 2026-02-28

### Bloque 2: backtest por strategy_id (sin refactor masivo)
- `BacktestEngine/StrategyRunner` ya no usa una unica senal para todas las estrategias.
- Se agrego dispatcher por familia de `strategy_id`:
  - `trend_pullback_orderflow_v2`
  - `breakout_volatility_v2`
  - `meanreversion_range_v2`
  - `trend_scanning_regime_v2`
  - `defensive_liquidity_v2`
- Fallback conservador:
  - cualquier `strategy_id` no reconocido sigue usando `trend_pullback` para mantener compatibilidad.
- Tests nuevos:
  - `rtlab_autotrader/tests/test_backtest_strategy_dispatch.py`
    - verifica que el mismo contexto produce decisiones distintas segun `strategy_id`.
    - valida ruteo de `trend_scanning` y gate de `obi_topn` en `defensive_liquidity`.
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> `4 passed`
  - `python -m pytest rtlab_autotrader/tests/test_backtest_annualization.py -q` -> `2 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "event_backtest_engine_runs_for_crypto_forex_equities or backtest_orderflow_toggle_metadata_and_gating" -q` -> `1 passed`

### Bloque 3: min_trades_per_symbol real en gates masivos
- `MassBacktestEngine` ahora calcula y persiste en `summary`:
  - `trade_count_by_symbol_oos`
  - `min_trades_per_symbol_oos`
- Gate `min_trade_quality` actualizado:
  - ya no mira solo `trade_count_oos`
  - ahora exige simultaneamente:
    - `trade_count_oos >= min_trades_per_run`
    - `min_trades_per_symbol_oos >= min_trades_per_symbol`
  - expone detalle en `gates_eval.checks.min_trade_quality`:
    - `run_trade_pass`
    - `symbol_trade_pass`
    - `symbols_below_min_trades`
- Compatibilidad hacia atras:
  - si faltan conteos por simbolo en corridas legacy, usa fallback `UNSPECIFIED=trade_count_oos`.
- Tests agregados:
  - `test_advanced_gates_fail_when_min_trades_per_symbol_is_below_threshold`
  - `test_advanced_gates_pass_when_min_trades_per_symbol_meets_threshold`
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `9 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`

### Bloque 4: fuente canonica de gates unificada (config > knowledge)
- `build_learning_config_payload` ahora toma gates desde `config/policies/gates.yaml` como fuente primaria.
- Si `safe_update.gates_file` en knowledge difiere de la canónica, se agrega warning y se fuerza la fuente canónica.
- `gates_summary` en `/api/v1/config/learning` ahora expone:
  - `source` (ruta canónica efectiva)
  - flags `pbo_enabled` / `dsr_enabled` derivados de política canónica.
- `LearningService` para recomendaciones usa thresholds de gates canónicos:
  - `pbo_max` desde `reject_if_gt`
  - `dsr_min` desde `min_dsr`
  - fallback explícito a `knowledge/policies/gates.yaml` solo si no existe config.
- `MassBacktestEngine` añade trazabilidad de política en artefactos:
  - `knowledge_snapshot.gates_canonical`
  - `knowledge_snapshot.gates_source`
- Tests agregados/ajustados:
  - `test_learning_service_uses_canonical_config_gates_thresholds`
  - `test_config_learning_endpoint_reads_yaml_and_exposes_capabilities` (assert de `gates_summary.source` y `safe_update.gates_file`)
- Validación ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "config_learning_endpoint_reads_yaml_and_exposes_capabilities or config_policies_endpoint_exposes_numeric_policy_bundle" -q` -> `2 passed`
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `10 passed`

### Bloque 5: UI Research Batch con calidad por simbolo visible
- `Backtests > Research Batch` ahora muestra en leaderboard:
  - columna `Mín trades/símbolo`
  - badge de mínimo requerido cuando existe en `gates_eval.min_trade_quality`.
- Drilldown de variante agrega:
  - `Mín trades/símbolo` con umbral requerido
  - detalle `Trades OOS por símbolo` (mapa agregado).
- Tipado frontend actualizado:
  - `MassBacktestResultRow.summary.trade_count_by_symbol_oos`
  - `MassBacktestResultRow.summary.min_trades_per_symbol_oos`
- Validación ejecutada:
  - `npm --prefix rtlab_dashboard run test -- src/lib/auth.test.ts src/lib/security.test.ts` -> `11 passed`
  - `npm --prefix rtlab_dashboard run lint` -> `0 errores` (warnings existentes no bloqueantes)

### Bloque 6: politica canonica para `enable_surrogate_adjustments` (fail-closed)
- `MassBacktestEngine` ahora resuelve surrogate por policy con trazabilidad:
  - nuevo resolver `_resolve_surrogate_adjustments(cfg)` con:
    - `enabled_effective`
    - `allowed_execution_modes`
    - `reason`
    - `promotion_blocked_effective`
    - `evaluation_mode`
- Policy canónica agregada en `config/policies/gates.yaml`:
  - `gates.surrogate_adjustments.enabled=false`
  - `allow_request_override=false`
  - `allowed_execution_modes=["demo"]`
  - `promotion_blocked=true`
- El motor ya no usa `cfg.enable_surrogate_adjustments` de forma directa.
- Si surrogate queda activo (solo `demo` por policy), la variante:
  - se etiqueta `evaluation_mode=engine_surrogate_adjusted`
  - falla `gates_eval.checks.surrogate_adjustments`
  - queda `promotable=false` y `recommendable_option_b=false` (fail-closed para promotion).
- Trazabilidad agregada en artifacts/manifest/summary:
  - `summary.surrogate_adjustments`
  - `manifest.surrogate_adjustments`
  - flags de catalogo `SURROGATE_ADJUSTMENTS` y `EVALUATION_MODE`.
- Tests agregados:
  - `test_surrogate_adjustments_policy_requires_allowed_execution_mode`
  - `test_surrogate_adjustments_request_override_rejected_by_default`
  - `test_advanced_gates_block_promotion_when_surrogate_adjustments_enabled`
  - `test_run_job_applies_surrogate_only_in_demo_mode_and_blocks_promotion`
- Validación ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> `13 passed`
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "mass_backtest_research_endpoints_and_mark_candidate" -q` -> `1 passed`

### Bloque 7: benchmark reproducible de `/api/v1/bots` (100 bots)
- Script nuevo: `scripts/benchmark_bots_overview.py`
  - seed controlado de bots/logs/breakers.
  - benchmark con `FastAPI TestClient` sobre endpoint real `/api/v1/bots`.
  - reporte markdown automatico en `docs/audit/`.
- Evidencia generada:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_20260228.md`
  - resultado: `p95=280.875ms` con `100 bots` y `200 requests` (objetivo `< 300ms`: PASS).
- Smoke adicional:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_SMOKE_20260228.md`.

### Bloque 8: benchmark remoto de `/api/v1/bots` (entorno desplegado)
- `scripts/benchmark_bots_overview.py` extendido con modo remoto:
  - `--base-url`, `--auth-token` (o login con `--username/--password`).
  - `--timeout-sec`.
  - `--min-bots-required` (default `100`).
- Criterio estricto de evidencia:
  - si `/api/v1/bots` devuelve menos bots que el minimo requerido, el reporte marca:
    - estado `NO_EVIDENCIA`
    - `target_pass=false`
    - motivo explicito en `no_evidencia_reason`.
- Smoke local de regresion del script actualizado:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_SMOKE2_20260228.md`.

### Bloque 9: ejecucion real benchmark remoto `/api/v1/bots` (Railway)
- Corrida remota ejecutada contra:
  - `https://bot-trading-ia-production.up.railway.app`
- Evidencia:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228.md`
- Resultado:
  - `p50=977.579ms`
  - `p95=1663.014ms`
  - `p99=1923.523ms`
  - objetivo `p95 < 300ms`: **FAIL**
- Estado de evidencia:
  - **NO EVIDENCIA** para benchmark objetivo de 100 bots, porque `/api/v1/bots` devolvio `1` bot (minimo requerido `100`).

### Bloque 10: cache TTL en `/api/v1/bots` + invalidacion explicita
- Backend:
  - `GET /api/v1/bots` ahora usa cache in-memory con TTL (`BOTS_OVERVIEW_CACHE_TTL_SEC`, default `10s`).
  - invalidacion explicita del cache en:
    - `POST /api/v1/bots`
    - `PATCH /api/v1/bots/{bot_id}`
    - `POST /api/v1/bots/bulk-patch`
  - `add_log(event_type=\"breaker_triggered\")` invalida cache para reflejar kills por bot/mode sin esperar TTL.
- Test de regresion agregado:
  - `test_bots_overview_cache_hit_and_invalidation_on_create`
  - verifica cache hit en GET consecutivos e invalidacion al crear bot.
- Validacion ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_multi_instance_endpoints or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_scopes_kills_by_bot_and_mode or bots_live_mode_blocked_by_gates" -q` -> `4 passed`.
- Benchmark local posterior al cambio:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_LOCAL_20260228_AFTER_CACHE.md`
  - resultado: `p50=31.453ms`, `p95=35.524ms`, `p99=37.875ms` (objetivo `<300ms`: PASS).
- Pendiente:
  - deploy del backend en Railway y rerun remoto para medir impacto real en prod.

### Bloque 11: validacion remota post-deploy `/api/v1/bots` (Railway)
- Push realizado a `main` con commit:
  - `11544ae`
- Benchmark remoto post-deploy (sin reseed) ejecutado:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY.md`
  - resultado: `p50=881.590ms`, `p95=1032.039ms`, `p99=1236.711ms` (FAIL `<300ms`)
  - estado evidencia: `NO EVIDENCIA` (la instancia devolvio `1` bot, minimo requerido `100`).
- Seeding remoto aplicado de nuevo a `100` bots:
  - script: `scripts/seed_bots_remote.py`
  - resultado: `bots finales=100`.
- Benchmark remoto post-deploy con 100 bots:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_20260228_POSTDEPLOY_100BOTS.md`
  - resultado: `p50=1265.135ms`, `p95=1458.513ms`, `p99=1519.641ms` (FAIL `<300ms`).
- Conclusion del bloque:
  - el cache TTL local mejora benchmark local pero no alcanza objetivo p95 en Railway con 100 bots;
  - se requiere siguiente ronda de optimizacion estructural en backend/storage para overview batch.

### Bloque 12: cardinalidad operativa de bots (sin minimos, con maximos)
- Backend:
  - nuevo limite maximo configurable por entorno: `BOTS_MAX_INSTANCES` (default `30`).
  - `POST /api/v1/bots` bloquea altas al alcanzar el tope y devuelve error claro en espanol.
- Script de benchmark:
  - `scripts/benchmark_bots_overview.py` ahora permite `--min-bots-required 0` (sin minimo obligatorio de evidencia).
  - mantiene modo estricto opcional cuando se quiera exigir una cardinalidad minima.
- Script de seed remoto:
  - default de `--target-bots` ajustado a `30` (recomendado para Railway actual).
  - si el backend rechaza por limite maximo, corta seed con mensaje explicito.
- Config:
  - `rtlab_autotrader/.env.example` documenta `BOTS_MAX_INSTANCES=30`.
- Tests:
  - nuevo `test_bots_creation_respects_max_instances_limit`.
  - validacion focal bots: `4 passed`.

### Bloque 13: observabilidad de performance en `/api/v1/bots`
- Endpoint `GET /api/v1/bots` ahora expone telemetria de latencia/cache por request:
  - headers:
    - `X-RTLAB-Bots-Overview-Cache` (`hit|miss`)
    - `X-RTLAB-Bots-Overview-MS`
    - `X-RTLAB-Bots-Count`
    - `X-RTLAB-Bots-Recent-Logs` (`enabled|disabled`)
  - query opcional `debug_perf=true` agrega bloque `perf` en payload (sin romper contrato base).
- Nuevo switch de carga:
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS` (default `true`) para poder desactivar logs recientes en overview cuando Railway este bajo presion.
- Slow-log controlado (throttled):
  - si `/api/v1/bots` supera `BOTS_OVERVIEW_PROFILE_SLOW_MS` (default `500ms`) registra `bots_overview_slow`.
  - throttling de logs con `BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC` (default `30s`) para evitar spam.
- Config documentada en `.env.example`:
  - `BOTS_OVERVIEW_CACHE_TTL_SEC`
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS`
  - `BOTS_OVERVIEW_PROFILE_SLOW_MS`
  - `BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC`
- Test nuevo:
  - `test_bots_overview_perf_headers_and_debug_payload`
- Validacion focal ejecutada:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_multi_instance_endpoints or bots_overview_cache_hit_and_invalidation_on_create or bots_overview_perf_headers_and_debug_payload or bots_overview_scopes_kills_by_bot_and_mode or bots_live_mode_blocked_by_gates or bots_creation_respects_max_instances_limit" -q` -> `6 passed`.

### Bloque 14: benchmark remoto A/B con `recent_logs` y metrica server-side
- Script `scripts/benchmark_bots_overview.py` extendido:
  - ahora reporta metricas server-side via header `X-RTLAB-Bots-Overview-MS`:
    - `server_p50_ms`, `server_p95_ms`, `server_p99_ms`, `server_avg_ms`
  - agrega trazabilidad de cache:
    - `cache_hits`, `cache_misses`, `cache_hit_ratio`
    - `recent_logs_mode` (enabled/disabled).
- Evidencia remota A/B en Railway:
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_ENABLED_30BOTS.md`
  - `docs/audit/BOTS_OVERVIEW_BENCHMARK_PROD_BLOCK14_DISABLED_30BOTS.md`
- Resultado relevante (server-side, 30 bots):
  - `enabled`: `server_p95_ms=74.93`
  - `disabled`: `server_p95_ms=63.034`
  - mejora aproximada: `~15.9%` al desactivar `recent_logs`.
- Observacion operativa critica:
  - cambios de variables en Railway disparan redeploy y en este entorno se observa reset de datos runtime (`/tmp/rtlab_user_data`), con cardinalidad de bots volviendo de `30` a `1`.
  - conclusion: la comparativa robusta exige persistencia de storage o reseed controlado tras cada redeploy.
- Estado final de config en prod:
  - `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false`.

### Auditoria comité + hardening adicional
- Seguridad:
  - `current_user` ahora ignora headers internos si no existe `INTERNAL_PROXY_TOKEN` válido (fail-closed en todos los entornos).
  - login backend con rate-limit/lockout por `IP+user`:
    - `10` intentos en `10` min -> `429`
    - lockout `30` min tras `20` fallos.
  - BFF (`[...path]` y `events-stream`) ahora falla con `500` explícito si falta `INTERNAL_PROXY_TOKEN`.
- Config:
  - `.env.example` backend y frontend actualizados con `INTERNAL_PROXY_TOKEN`.
- Auditoría:
  - nuevos artefactos `docs/audit/AUDIT_REPORT_20260228.md`, `docs/audit/AUDIT_FINDINGS_20260228.md`, `docs/audit/AUDIT_BACKLOG_20260228.md`.
- Bibliografía:
  - nuevo `scripts/biblio_extract.py` (indexación SHA256 + extracción incremental a txt).
  - nuevo `docs/reference/biblio_txt/.gitignore`.
  - `docs/reference/BIBLIO_INDEX.md` regenerado con hashes.
- Seguridad documental:
  - `docs/SECURITY.md` reescrito con threat model mínimo, checklist y comandos de auditoría.
- Test agregado:
  - `test_auth_login_rate_limit_and_lock_guard`.

### Seguridad + Runtime + CI (T1 + T2 + T4 + T6 + T9)
- T1 auth bypass mitigado:
  - backend ya no confia ciegamente en `x-rtlab-role/x-rtlab-user`.
  - ahora exige `x-rtlab-proxy-token` valido contra `INTERNAL_PROXY_TOKEN`.
  - BFF (`[...path]` + `events-stream`) envia el token interno desde ENV.
- T2 defaults peligrosos endurecidos:
  - fail-fast en boot cuando `NODE_ENV=production` y hay defaults en admin/viewer o `AUTH_SECRET` corto.
  - `G2_AUTH_READY` actualizado con `no_default_credentials`.
- T4 runtime simulado explicitado:
  - estado del bot persistido con `runtime_engine`.
  - nuevo gate `G9_RUNTIME_ENGINE_REAL`.
  - `POST /api/v1/bot/mode` bloquea `LIVE` si `runtime_engine != real`.
  - `/api/v1/status` y `/api/v1/health` exponen `runtime_engine/runtime_mode`.
- T6 annualizacion por timeframe:
  - `ReportEngine.build_metrics` ya no usa constante fija 5m para Sharpe/Sortino.
  - factor anual se calcula por timeframe real (`1m/5m/10m/15m/1h/1d` + parse generico).
- T9 CI frontend agregado:
  - nuevo job `frontend` en GitHub Actions con `npm ci`, typecheck, vitest y build.
- Tests agregados/ajustados:
  - `test_web_live_ready.py`:
    - `test_internal_headers_require_proxy_token`
    - `test_auth_validation_fails_in_production_with_default_credentials`
    - `test_live_mode_blocked_when_runtime_engine_is_simulated`
  - `test_backtest_annualization.py` (factor y scaling de Sharpe por timeframe).

### Ajustes auditoria comite (quick wins adicionales)
- `GET /api/v1/gates` ahora requiere auth (`current_user`) para evitar exposicion publica del checklist.
- `BacktestEngine` bloquea `validation_mode=purged-cv|cpcv` en Quick Backtest con error explicito (fail-closed; sin `hook_only` silencioso).
- `MassBacktestEngine` desactiva surrogate adjustments por defecto:
  - nuevo comportamiento default `evaluation_mode=engine_raw`.
  - surrogate solo segun policy canónica (`gates.surrogate_adjustments`) y modo permitido.
- `GateEvaluator` migra fuente primaria de thresholds a `config/policies/gates.yaml` (fallback `knowledge/policies/gates.yaml`).
- `GateEvaluator` pasa a fail-closed para PBO/DSR cuando policy los marca como habilitados y faltan en el reporte.

### Bibliografia
- Nuevo `docs/reference/BIBLIO_INDEX.md` con las 20 fuentes externas informadas.
- Nuevo `docs/reference/biblio_raw/.gitignore` para trabajo local sin subir PDFs/TXT al repo.

## 2026-02-27

### Opcion B + Opcion C (hotfix calibracion sin refactor masivo)
- `FundamentalsCreditFilter` separado en:
  - `get_fundamentals_snapshot_cached(...)` (snapshot crudo)
  - `evaluate_credit_policy(...)` (decision por modo)
- Fix leakage por modo:
  - mismo snapshot puede dar decision distinta segun `BACKTEST` vs `LIVE/PAPER`.
  - `allow_trade` ya no depende de cache de decision.
- Backtest equities sin fundamentals preexistentes:
  - en `BACKTEST` no aborta por 400; corre con `fundamentals_missing`, `fundamentals_quality=ohlc_only`, `promotion_blocked=true`.
  - en `LIVE/PAPER` se mantiene fail-closed.
- `/api/v1/bots` sin N+1:
  - nuevo batch `get_bots_overview(...)` para KPIs/logs/kills por bot.
  - `list_bot_instances` usa overview batch interno.
- Kills correctamente scopeados por `bot_id + mode`:
  - nueva tabla `breaker_events` ya conectada al flujo runtime (`add_log` con `breaker_triggered`).
  - `mode` faltante pasa a `unknown` (no se imputa a `paper`).
- Tests nuevos/ajustados:
  - `test_fundamentals_mode_leakage.py`
  - `test_fundamentals_credit_filter.py` (policy nueva BACKTEST/LIVE)
  - `test_web_live_ready.py` (equities ohlc_only + kills por bot/mode)
- Suite focal corrida:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_mode_leakage.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_web_live_ready.py::test_event_backtest_engine_runs_for_crypto_forex_equities rtlab_autotrader/tests/test_web_live_ready.py::test_bots_multi_instance_endpoints rtlab_autotrader/tests/test_web_live_ready.py::test_bots_overview_scopes_kills_by_bot_and_mode rtlab_autotrader/tests/test_web_live_ready.py::test_bots_live_mode_blocked_by_gates -q`
  - resultado: `11 passed`.

### Calibracion real (fundamentals + costos)
- Nueva policy `config/policies/fundamentals_credit_filter.yaml` con scoring, thresholds, reglas por instrumento y snapshots.
- Nuevo modulo `rtlab_core/fundamentals/credit_filter.py` con evaluacion auditable:
  - `fund_score`, `fund_status`, `allow_trade`, `risk_multiplier`, `explain[]`
  - cache/snapshot con TTL y persistencia en SQLite.
- Catalogo SQLite extendido:
  - nueva tabla `fundamentals_snapshots`
  - columnas en `backtest_runs`: `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`.
- Wiring en backend (`app.py` + `mass_backtest_engine.py`):
  - run metadata/provenance ahora incluye fundamentals
  - bloqueo fail-closed cuando fundamentals enforced retorna `allow_trade=false`.
- Cost model reforzado:
  - `FeeProvider` intenta endpoints Binance reales (`/api/v3/account/commission`, `/sapi/v1/asset/tradeFee`) + fallback seguro
  - `FundingProvider` intenta `/fapi/v1/fundingRate` + fallback seguro
  - `SpreadModel` agrega estimador `roll` cuando no hay BBO ni spread explicito.
- Ajuste de gates default:
  - `dsr_min` en rollout offline pasa a `0.95`.
- Tests corridos:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `7 passed`.

### Calibracion real (bloque siguiente: fundamentals con fuente local)
- `FundamentalsCreditFilter` ahora puede autoleer snapshot local JSON cuando `source` llega en `unknown/auto/local_snapshot`.
- Nueva configuracion en policy:
  - `data_source.mode`
  - `data_source.local_snapshot_dir`
  - `data_source.auto_load_when_source_unknown`
- El filtro rellena `asof_date` y metricas financieras desde snapshot local y agrega traza:
  - `explain.code = DATA_SOURCE_LOCAL_SNAPSHOT`
  - `source_ref.source_path`
- Paths soportados para snapshot:
  - `user_data/fundamentals/{market}/{symbol}.json`
  - y fallback legacy en `user_data/data/fundamentals/{market}/{symbol}.json`
- Test agregado:
  - `test_fundamentals_autoload_local_snapshot_for_equities`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `8 passed`.

### Calibracion real (bloque 2/5: fundamentals remoto + fallback local)
- `FundamentalsCreditFilter` ahora soporta `remote_json` configurable por policy/env:
  - `data_source.remote.enabled`
  - `base_url_env/base_url`
  - `endpoint_template` con placeholders `{market}`, `{symbol}`, `{exchange}`, `{instrument_type}`
  - timeout y header de auth por ENV.
- Flujo de resolucion de fuente:
  - `source=auto|unknown|runtime_policy|research_batch` -> intenta remoto y luego fallback local
  - `source=remote` -> solo remoto (si falla queda evidencia y aplica fail-closed segun policy)
  - `source=local_snapshot` -> solo local.
- En metadata/explain se agrega trazabilidad de origen:
  - `source_ref.source_url`
  - `source_ref.source_http_status`
  - `DATA_SOURCE_REMOTE_SNAPSHOT` / `DATA_SOURCE_REMOTE_ERROR`.
- Wiring actualizado para usar `source=auto` en:
  - `rtlab_core/web/app.py`
  - `rtlab_core/src/research/mass_backtest_engine.py`
- Test nuevo:
  - `test_fundamentals_autoload_remote_snapshot_for_equities`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py rtlab_autotrader/tests/test_cost_providers.py -q`
  - resultado: `9 passed`.

### Calibracion real (bloque 3/5: costos multi-exchange base)
- `FeeProvider` ahora usa fallback por exchange desde policy:
  - `fees.per_exchange_defaults` (binance/bybit/okx)
  - override opcional por ENV (`{EXCHANGE}_MAKER_FEE`, `{EXCHANGE}_TAKER_FEE`).
- `FundingProvider` agrega fetch para Bybit perps:
  - endpoint `/v5/market/funding/history` (publico)
  - parsea `fundingRate` y persiste snapshot.
- Se mantiene fail-safe:
  - si endpoint no responde, guarda snapshot con fallback y trazabilidad en payload.
- Policy actualizada:
  - `config/policies/fees.yaml` incluye `per_exchange_defaults`.
- Tests nuevos:
  - `test_cost_model_uses_exchange_fee_fallback_for_bybit`
  - `test_cost_model_fetches_bybit_funding_when_perp`
- Suite parcial recalibrada:
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Calibracion real (bloque 4/5: promotion fail-closed con trazabilidad)
- `validate_promotion` ahora exige constraints adicionales en corridas de catalogo:
  - `cost_snapshots_present` (`fee_snapshot_id` + `funding_snapshot_id`)
  - `fundamentals_allow_trade` (`fund_allow_trade=true`)
- `_build_rollout_report_from_catalog_row` expone metadata de trazabilidad en report de rollout:
  - `market`, `exchange`
  - `fee_snapshot_id`, `funding_snapshot_id`
  - `fundamentals_snapshot_id`, `fund_status`, `fund_allow_trade`, `fund_risk_multiplier`, `fund_score`
- Si el run viene de legado (`legacy_json_id`), se completa metadata faltante desde catalogo para no perder trazabilidad en promotion.
- Tests actualizados:
  - `test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke` ahora verifica presencia de ambos checks nuevos.
- Suites corridas:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke rtlab_autotrader/tests/test_web_live_ready.py::test_runs_batches_catalog_endpoints_smoke -q`
  - resultado: `2 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Calibracion real (bloque 5/5: admin multi-bot/live + cierre)
- `BotInstance` metrics reforzadas en backend (`_bot_metrics`):
  - agrega breakdown por modo (`shadow/paper/testnet/live`) con `trade_count`, `winrate`, `net_pnl`, `avg_sharpe`, `run_count`.
  - agrega kills reales desde logs `module=risk`, `type=breaker_triggered`:
    - `kills_total` por modo del bot
    - `kills_24h` por modo
    - `kills_global_total`, `kills_global_24h`
    - `kills_by_mode`, `kills_by_mode_24h`, `last_kill_at`.
- `kill switch` ahora guarda `mode` en payload del log para trazabilidad de kills por entorno.
- Endpoints de bots endurecidos para LIVE:
  - `POST /api/v1/bots`
  - `PATCH /api/v1/bots/{bot_id}`
  - `POST /api/v1/bots/bulk-patch`
  - todos bloquean `mode=live` si `live_can_be_enabled(evaluate_gates("live"))` no pasa.
- UI:
  - `strategies/page.tsx`: tabla de bots ahora muestra `runs` debajo de `trades` y `kills 24h`.
  - `execution/page.tsx`:
    - botón masivo `Modo LIVE` bloqueado cuando checklist LIVE no está en PASS
    - tabla de operadores agrega columnas `Sharpe` y `Kills (total/24h)`.
- Tipos frontend actualizados en `src/lib/types.ts` para nuevos campos de métricas de bot.
- Tests:
  - nuevo `test_bots_live_mode_blocked_by_gates`
  - se mantiene `test_bots_multi_instance_endpoints`.
- Suites corridas:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py::test_bots_multi_instance_endpoints rtlab_autotrader/tests/test_web_live_ready.py::test_bots_live_mode_blocked_by_gates rtlab_autotrader/tests/test_web_live_ready.py::test_runs_validate_and_promote_endpoints_smoke -q`
  - resultado: `3 passed`.
  - `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py rtlab_autotrader/tests/test_backtest_catalog_db.py -q`
  - resultado: `11 passed`.

### Backtests / Runs (bloque continuo de UX + escala)
- Runs table ahora permite ordenar haciendo click en cabeceras (Run ID, Fecha, Estrategia, Ret%, MaxDD, Sharpe, PF, WinRate, Trades, Expectancy) con toggle asc/desc.
- Se agregó `sort_by=winrate` en backend (`BacktestCatalogDB.query_runs`) para ranking directo por winrate.
- Se eliminó el límite rígido de `5` en selección legacy (`selectedRuns`) para no recortar comparaciones manuales.
- Parser de errores UI reforzado (`uiErrMsg`) para evitar renderizar `[object Object]` y mostrar mensajes útiles (`detail/message/error/cause`).
- Tests actualizados: `test_backtest_catalog_db.py` valida ordenamiento por `winrate`.

### Research Batch (shortlist BX persistente)
- Backend:
  - nuevo `BacktestCatalogDB.patch_batch(...)` para actualizar `best_runs_cache`/summary del batch.
  - nuevo endpoint `POST /api/v1/batches/{batch_id}/shortlist` (admin) para guardar shortlist de variantes/runs.
- Frontend (`Backtests > Research Batch`):
  - botones `Guardar shortlist BX` y `Cargar shortlist BX`.
  - restauración automática de shortlist al seleccionar un batch.
  - en tabla de Batches se muestra columna `Shortlist` (cantidad guardada) y acción `Cargar shortlist`.
- Tests:
  - `test_web_live_ready.py::test_batch_shortlist_save_and_load`
  - `test_backtest_catalog_db.py` cubre patch de batch con `best_runs_cache`.

### Backtests / Strategies (bloque UX escala)
- `Backtests / Runs` D2 (`Comparison Table Pro`) ahora usa virtualizacion por ventana visible:
  - contenedor con scroll vertical fijo
  - render de filas visibles + overscan
  - espaciadores superior/inferior para mantener altura total
  - contador de ventana (`X-Y de N`) para trazabilidad visual.
- `Strategies` compactado para escalar mejor con 50+ estrategias:
  - filas mas bajas (`align-middle`, menor padding)
  - acciones visibles reducidas en fila (selector compacto + menu `Mas`)
  - menor ancho minimo de columna de acciones.

### Operaciones / Trades (Bloque 3)
- Tabla de operaciones ahora tiene orden configurable (`timestamp`, `PnL`, `estrategia`, `simbolo`, `modo`, `fees`, `slippage`, `qty`).
- Seleccion masiva por checkbox:
  - seleccionar/quitar pagina
  - limpiar seleccion
  - borrar operaciones seleccionadas (admin).
- Borrado filtrado con `preview` (`dry_run`) antes de ejecutar borrado real.
- Resumen operacional extendido:
  - panel por `modo + entorno` clickable para aplicar filtros rapidos
  - `Top estrategias` ahora permite aplicar filtro directo por estrategia.
- En tabla de trades, `strategy_id` es clickable para filtrar al instante.

### Ejecucion / Live Admin (Bloque 4)
- Nuevo panel de **estrategias primarias por modo** dentro de `Ejecucion`:
  - selector y guardado rapido de primaria para `PAPER`, `TESTNET` y `LIVE`
  - usa endpoint existente `POST /api/v1/strategies/{id}/primary` (sin API nueva).
- Modo `LIVE` mas seguro y explicito en UI:
  - muestra bloqueos concretos de checklist (`keys`, `connector`, `gates`)
  - boton `Aplicar modo` se bloquea si `LIVE` no esta listo.
- Administracion de operadores mas intuitiva:
  - atajos de seleccion masiva `Seleccionar activos` y `Seleccionar modo runtime`
  - mensaje contextual que separa runtime global vs operadores de aprendizaje.

## 2026-02-26

### RTLAB Strategy Console (Bloque 1 - Policies numericas)
- Agregada carpeta `config/policies/`
- `gates.yaml` con numeros explicitos para `PBO/CSCV`, `DSR`, `walk_forward`, `cost_stress`, calidad minima de trades
- `microstructure.yaml` con Order Flow L1 (`VPIN`, spread_guard, slippage_guard, volatility_guard)
- `risk_policy.yaml` con soft/hard kill por `bot/strategy/symbol`
- `beast_mode.yaml` con limites (`5000 trials`, concurrencia, budget governor)
- `fees.yaml` con TTLs y fallback maker/taker

### RTLAB Strategy Console (Bloques 2-7)
- Backend: `GET /api/v1/config/policies` + resumen numerico de policies
- Backend: `GET /api/v1/config/learning` extendido con `numeric_policies_summary`
- Research Batch: persistencia de `policy_snapshot` / `policy_snapshot_summary`
- Cost model baseline:
  - `FeeProvider`, `FundingProvider`, `SpreadModel`, `SlippageModel`
  - snapshots persistentes en SQLite
  - metadata de costos/snapshots por `BT-*`
- Order Flow L1 (VPIN proxy desde OHLCV) en motor masivo + debug UI + flags `MICRO_SOFT_KILL` / `MICRO_HARD_KILL`
- Gates avanzados en research masivo (PBO/DSR/WF/cost stress/min trade quality) con PASS/FAIL visible y bloqueo fail-closed de `mark-candidate`
- Modo Bestia (fase 1):
  - scheduler local con cola de jobs, concurrencia y budget governor
  - endpoints `/api/v1/research/beast/start|status|jobs|stop-all|resume`
  - panel UI de Modo Bestia en `Backtests`

### UI/UX Research-first (Bloques 1-6)
- Fix del falso `WS timeout` en diagnostico SSE (`/api/events`)
- `Backtests / Runs`: paginacion obligatoria (30/60/100), labels mas claros, empty state con CTA
- `Settings > Rollout / Gates`: empty states accionables en offline gates / compare / fase / telemetria
- `Portfolio`: empty states guiados + historial con timestamp/tipo/detalle
- `Riesgo`: foco en riesgo (sin duplicar gates) + explicacion de correlacion/concentracion
- `Ejecucion`: panel `Trading en Vivo (Paper/Testnet/Live) + Diagnostico` con checklist `Live Ready`, conectores y controles admin
- `Trades` y `Alertas`: filtros con labels en espanol + empty states guiados
- `Backtests`: `Detalle de Corrida` con pestanas estilo Strategy Tester
- `Backtests`: `Quick Backtest Legacy` marcado como deprecado y colapsado

### Documentacion
- `docs/_archive/UI_UX_RESEARCH_FIRST_FINAL.md`
- `docs/truth/SOURCE_OF_TRUTH.md`
- `docs/truth/NEXT_STEPS.md`

## 2026-03-07

### UX bots + backtests + beast
- `execution/page.tsx`: nuevo selector de bot en `Ejecucion` con KPIs basicos y acciones de modo/estado sin tocar LIVE.
- `execution/page.tsx`: grafica `Traza de Latencia y Spread` ahora muestra nombres de ejes (`Tiempo / muestra`, `Latencia p95 (ms)`, `Spread (bps)`) y leyenda.
- `strategies/page.tsx`: seleccion multiple de estrategias, creacion de bot desde seleccion, envio a bot existente, pool editable, borrado de bot y export JSON de conocimiento.
- `strategies/page.tsx`: las sugerencias/recomendaciones del bot ya pueden agregarse a un bot destino.
- `app.py` + `types.ts`: `/api/v1/research/beast/status` expone metadata de policy (`policy_state`, `policy_source_root`, `policy_warnings`).
- `backtests/page.tsx`: `Research Batch / Beast` ahora distingue `policy faltante` vs `policy deshabilitada` y envia `data_mode=dataset` explicitamente.
- `backtests/page.tsx`: nuevo panel `Dataset real para batch` muestra si existe dataset exacto, si hay fallback `1m + resample`, y el comando sugerido cuando falta dataset real.
- `policy_paths.py` + wiring backend (`app.py`, `mass_backtest_engine.py`, `cost_providers.py`, `credit_filter.py`):
  - la raiz `config/policies` ya no se resuelve solo porque exista una carpeta;
  - ahora se elige la raiz con YAML reales disponibles;
  - se corrige el caso de deploy donde `/app/config/policies` existe vacio y la policy valida vive en `/app/rtlab_autotrader/config/policies`;
  - esto evita falsos `Modo Bestia deshabilitado` por snapshot vacio en runtime.
- `mass_backtest_engine.py` + `app.py`:
  - `Research Batch` y `Modo Bestia` ahora hacen preflight de dataset real antes de encolar;
  - si falta dataset, responden `400` con detalle accionable y no crean un batch `FAILED` por traceback interno.

### Validacion
- `eslint src/app/(app)/backtests/page.tsx src/app/(app)/execution/page.tsx src/app/(app)/strategies/page.tsx src/lib/client-api.ts src/lib/types.ts` -> PASS
- `npm run build` en `rtlab_dashboard` -> PASS
- `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py` -> PASS
- Warnings no bloqueantes: Recharts en prerender
- `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS (`17 passed`)
- `python -m pytest rtlab_autotrader/tests/test_cost_providers.py rtlab_autotrader/tests/test_fundamentals_credit_filter.py -q` -> PASS (`10 passed`)
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "config_learning_endpoint_reads_yaml_and_exposes_capabilities or config_policies_endpoint_exposes_numeric_policy_bundle or mass_backtest_start_rejects_missing_dataset or research_beast_start_rejects_missing_dataset or mass_backtest_research_endpoints_and_mark_candidate or research_beast_endpoints_smoke" -q` -> PASS (`6 passed`)
- `python -m py_compile rtlab_autotrader/rtlab_core/policy_paths.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/backtest/cost_providers.py rtlab_autotrader/rtlab_core/fundamentals/credit_filter.py` -> PASS

### Rate limit research/backtests (2026-03-07)
- `app.py`: los `GET` read-only usados por polling/catalogo (`research mass status/results/artifacts`, `beast status/jobs`, `batches`, `runs`, `backtests/runs`, `bots`) pasan a bucket `general`; solo las acciones que disparan trabajo quedan en `expensive`.
- `backtests/page.tsx`: polling reducido de `mass status` (`1.2s -> 4s`) y panel `Beast` (`2s -> 10s`) para no autogenerar `429`.
- Se corrige el falso estado viejo de UI cuando el propio polling consumia el bucket `expensive`.

### Validacion adicional (2026-03-07)
- `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "api_general_rate_limit_guard or api_expensive_rate_limit_guard or api_bots_overview_uses_general_bucket or api_research_readonly_endpoints_use_general_bucket or mass_backtest_research_endpoints_and_mark_candidate" -q` -> PASS (`5 passed`)
- `eslint src/app/(app)/backtests/page.tsx` -> PASS
- `npm run build` en `rtlab_dashboard` -> PASS

### Limpieza local conservadora (2026-03-07)
- Se removieron solo artefactos locales no versionados y engañosos:
  - `tmp/`
  - `rtlab_autotrader/tmp_test_ud/`
  - `rtlab_autotrader/user_data/backtests/` (6 runs `synthetic_seeded`)
  - `rtlab_autotrader/user_data/research/mass_backtests/` (metadata local vacia)
- No se tocaron `learning/`, `console_api.sqlite3`, `console_settings.json` ni metadata local de estrategias por no existir evidencia suficiente de que sobraran.

- `app.py`: `backtests/run`, `research/mass-backtest/start`, `batches` y `research/beast/start` ahora aceptan `bot_id` explicito y lo propagan al runtime.
- `app.py`: `create_event_backtest_run(...)` persiste `bot_id` en metadata, params, provenance y tags (`bot:<id>`).
- `app.py`: `annotate_runs_with_related_bots(...)` prioriza referencias historicas del run antes de inferir bots por pool actual.
- `mass_backtest_engine.py`: los child runs de research/batch guardan `bot_id` en `params_json` y tag estructurado `bot:<id>`.
- `backtests/page.tsx`: quick backtest, research batch y beast envian `bot_id` del selector activo.
- `backtests/page.tsx`: overlays/equity/drawdown ahora muestran ejes con nombre (`Paso / muestra`, `Equity neta`, `Drawdown`).
- `test_web_live_ready.py`: nuevas validaciones para `run -> bot` persistente aun si cambia el pool del bot, y forwarding de `bot_id` en mass/beast.
- Limpieza local conservadora: eliminados solo `tmp/`, `tmp_test_ud/`, runs `synthetic_seeded` no versionados y metadata vacia de `mass_backtests/`.

## 2026-04-06

### Paridad frontend ↔ staging API en Backtests
- Se audito Vercel real y se confirmo que `bot-trading-ia-csud` apunta a `production`, no a `staging`.
- Se confirmo que `bot-trading-ia-staging-2` es la superficie correcta para validar la paridad con Railway staging.
- `Backtests` ahora muestra el backend objetivo del frontend (`NEXT_PUBLIC_BACKEND_URL`) para evitar leer production como si fuera staging.
- `scripts/staging_smoke_report.py` y `.github/workflows/staging-smoke.yml` pasan a usar `bot-trading-ia-staging-2` como frontend staging por defecto.

### Beast staging E2E
- Se agrego sonda reutilizable de test E2E para Beast en staging:
  - `scripts/beast_staging_e2e_report.py`
  - `staging-smoke.yml` ahora puede ejecutar Beast E2E sobre `BTCUSDT`
  - workflow dedicado adicional: `.github/workflows/beast-staging-e2e.yml`
- Validacion real cerrada:
  - workflow: `24022545610`
  - run real: `BX-000001`
  - estrategia: `trend_pullback_orderflow_confirm_v1`
  - `timeframe=5m`
  - `dataset_source=auto`
  - `use_orderflow_data=false`
  - estado final: `COMPLETED`
  - `results_count=1`
- El run materializo dataset exacto `BTCUSDT 5m` a partir de `1m`:
  - `exact_present=false -> true`
  - output: `/app/user_data/data/crypto/processed/BTCUSDT_5m.parquet`
- Conclusión operativa:
  - Beast/Backtests en staging ya es usable para testeo real sobre `BTCUSDT`
  - no hizo falta fix adicional de backend/producto en este bloque
