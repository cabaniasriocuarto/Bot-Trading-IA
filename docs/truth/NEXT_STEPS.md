# NEXT STEPS (Prioridades Reales)

Fecha: 2026-04-25

## Siguiente paso exacto despues de RTLOPS-89 - 2026-04-25
- [x] Cerrar el contrato canonico minimo de dataset/prerequisitos para Batch/Beast:
  - `POST /api/v1/research/dataset-preflight` ya existe como surface minima del backend;
  - el contrato ya expone:
    - `dataset_ready`
    - `dataset_status`
    - `dataset_source_type`
    - `market_family`
    - `symbol` / `symbols`
    - `timeframe`
    - `bootstrap_required`
    - `bootstrap_command`
    - `can_run_batch`
    - `can_run_beast`
    - `blocking_reason`
    - `eligible_symbols`
    - `ineligible_symbols`;
  - `start_async(...)` y `start_beast_async(...)` ya reutilizan la misma verdad canonica.
- [x] Cerrar el comportamiento fail-closed real del bloque:
  - dataset faltante -> bloqueo limpio con `dataset_status=missing`;
  - `dataset_source=synthetic` -> bloqueo limpio con `dataset_status=synthetic_blocked`;
  - `Backtests` ya consume el preflight canonico y deja de deducir readiness desde heuristicas locales.
- [x] Revalidacion minima real del bloque:
  - `uv run --project rtlab_autotrader python -m py_compile rtlab_autotrader/rtlab_core/src/research/mass_backtest_engine.py rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS
  - `uv run --project rtlab_autotrader --extra dev python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "dataset_preflight or research_mass_backtest_start_rejects_missing_dataset or research_beast_start_rejects_missing_dataset or research_beast_endpoints_smoke" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- [x] Mantener el bloque chico y profesional:
  - sin refactor masivo;
  - sin redisenio total de `Backtests`;
  - sin abrir `RTLOPS-90` dentro de este bloque;
  - sin tocar dominios no relacionados.
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-90 - Reordenamiento UX Backtests sin refactor masivo`;
  - resolver ahi solo:
    - reordenamiento y claridad operatoria de `Backtests` sobre el contrato ya canonico de preflight;
    - limpieza UX minima del bloque `Research Batch / Beast` sin reabrir backend salvo evidencia nueva;
  - mantener fuera de `RTLOPS-90`:
    - backend nuevo de dataset prereqs
    - refactor transversal
    - API grande nueva
    - dominios laterales fuera de Backtests UX

## Siguiente paso exacto despues del cierre administrativo de RTLOPS-28 - 2026-04-24
- [x] Revalidar repo + `docs/truth` + Linear:
  - `RTLOPS-28` ya tenia absorbido su alcance tecnico real sobre `rtlops28/v1`;
  - `drift_not_blocking`, `allow_review / hold / block`, `missingness` y `recommended_actions[]` ya estaban absorbidos.
- [x] Cerrar administrativamente `RTLOPS-28` sin split:
  - Linear ya la deja en `Done`;
  - no queda un gap tecnico vivo de `PSI/KS` dentro de esta issue;
  - cualquier `PSI/KS` futuro debera abrirse como issue nueva, chica y precisa.
- [ ] Siguiente paso exacto recomendado:
  - abrir un preflight limpio para decidir el dominio siguiente del programa, ya fuera de `RTLOPS-28`;
  - resolver ahi solo:
    - que dominio siguiente queda sostenido por repo + `docs/truth` + Linear;
    - cual es el slice minimo y auditable de ese dominio;
  - mantener fuera de ese bloque:
    - drift nuevo por inercia
    - `live console` si no queda canonizado por evidencia suficiente
    - monitoring completo
    - scorecard de produccion
    - frontend cosmetico

## Siguiente paso exacto despues de RTLRESE-32 - 2026-04-22
- [x] Fundar validacion independiente real por run sobre backend/catalogo:
  - `rtlrese32/v1` ya existe como contrato persistido por run;
  - la persistencia minima vive en `backtest_runs.independent_validation_json`;
  - la contract queda disponible en `GET /api/v1/runs/{run_id}`;
  - `validate_promotion` ya falla cerrado si la evidencia independiente no es reusable o no declara `promotion_stage_eligible`.
- [x] Reusar backlog previo sin abrir sobrealcance:
  - `RTLRESE-5` queda reutilizada para `PBO/CSCV`;
  - `RTLRESE-6` queda reutilizada para `PSR/DSR`, rechazo/review y elegibilidad por etapa;
  - `RTLRESE-4` no hizo falta tocarla porque no aparecio un gap nuevo de provenance persistente.
- [x] Mantener el bloque profesional y acotado:
  - sin abrir `live console`;
  - sin abrir monitoring/drift como dominio principal todavia;
  - sin abrir scorecard / portfolio risk;
  - sin refactor transversal.
- [x] Revalidacion minima real del bloque:
  - `pytest rtlab_autotrader/tests/test_backtest_catalog_db.py -q` -> PASS
  - `pytest rtlab_autotrader/tests/test_web_live_ready.py -k "independent_validation_contract or independent_validation_not_reusable" -q` -> PASS
  - `pytest rtlab_autotrader/tests/test_rollout_safe_update.py -k "gate_evaluator or compare_engine or rollout_manager" -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- [x] Siguiente paso exacto recomendado:
  - `RTLOPS-28` ya fue absorbida en repo/tests y cerrada administrativamente en Linear;
  - el frente siguiente pasa a decidir el dominio siguiente del programa, ya fuera de `RTLOPS-28`.

## Preflight posterior a RTLOPS-84 - cadena minima cerrada - 2026-04-21
- [x] Revalidar el agotamiento de la cadena de consumidores minimos:
  - `rtlops81/v1` ya tiene tres consumidores reales y auditables en:
    - `execution/page.tsx`
    - `strategies/page.tsx`
    - `backtests/page.tsx`
  - no aparece una cuarta surface natural comparable en el dashboard para seguir estirando la cadena minima de `lifecycle_operational`
  - por lo tanto, la cadena de consumidores minimos queda cerrada en `RTLOPS-84`
- [x] Revalidar el estado del dominio siguiente sin inventar backlog:
  - Linear muestra `RTLOPS-69` (`live console`) como backlog real del mismo proyecto
  - pero repo + `docs/truth` todavia no sostienen con honestidad que `live console` sea la sucesora inmediata del programa
  - tampoco queda sostenido todavia un dominio siguiente alternativo en `monitoring / health / alerts`, lifecycle operativo mas amplio o lifecycle completo entre entornos
- [ ] Siguiente paso exacto recomendado:
  - abrir un bloque de canonizacion del dominio posterior al cierre de la cadena minima
  - decidir, con repo + `docs/truth` + Linear, si corresponde promover `RTLOPS-69` (`live console`) u otro dominio explicito del backlog real
  - mantener fail-closed si ese dominio siguiente no queda sostenido con evidencia suficiente

## Siguiente paso exacto despues de RTLOPS-84 - 2026-04-21
- [x] Fundar el tercer consumidor real de `lifecycle_operational` sobre `rtlops81/v1`:
  - `backtests/page.tsx` ya consume `selectedMassBot.lifecycle_operational` como tercera surface minima operativa distinta de `execution/page.tsx` y `strategies/page.tsx`
  - la surface vive dentro de `Research Batch` y audita, en modo solo lectura, el subset operativo del bot elegido antes de correr batch
  - deja visible, sobre el universo del bot:
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - overrides `paused`
    - simbolos sin dato operativo
  - por simbolo muestra trazabilidad minima con:
    - `runtime_symbol_id`
    - `selected_strategy_id`
    - issues canonicos por simbolo
- [x] Mantener el bloque profesional y acotado:
  - sin tocar el contrato backend ya canonico
  - sin abrir `live console`
  - sin abrir LIVE lateral
  - sin abrir lifecycle completo entre entornos
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- [x] Siguiente paso exacto recomendado:
  - se ejecuto el preflight fail-closed posterior a `RTLOPS-84`
  - la cadena de consumidores minimos queda cerrada en `RTLOPS-84`
  - el dominio siguiente del programa todavia no queda canonizado con honestidad

## Preflight posterior a RTLOPS-83 - sucesora canonizada - 2026-04-21
- [x] Revalidar que `RTLOPS-83` ya cierra el segundo consumidor real de `lifecycle_operational` sobre `rtlops81/v1`:
  - `strategies/page.tsx` ya consume `bot.lifecycle_operational` como segunda surface minima operativa
  - el contrato `rtlops81/v1` ya tiene dos consumidores reales y auditables sin abrir dominios mayores
  - las surfaces vivas quedan hoy en:
    - `execution/page.tsx`
    - `strategies/page.tsx`
- [x] Revalidar que el siguiente gap minimo del frente sigue acotado:
  - el siguiente delta ya no es `live console`
  - no es LIVE lateral
  - no es lifecycle completo entre entornos
  - no requiere refactor transversal
- [x] Canonizacion explicita de la sucesora:
  - por decision humana explicita del usuario se fija `RTLOPS-84`:
    - `Bot Multi-Symbol — tercer consumidor mínimo de lifecycle_operational`
  - ese slice debe resolver solo:
    - tercer consumidor minimo de `lifecycle_operational`
    - tercera surface minima operativa en `rtlab_dashboard/src/app/(app)/backtests/page.tsx`
    - wiring minimo, chico y auditable sobre `rtlops81/v1`
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`)
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-84` y resolver solo el tercer consumidor minimo de `lifecycle_operational` sobre `rtlops81/v1`
  - resolver ahi solo:
    - surface minima operativa en `backtests/page.tsx`, distinta de `execution/page.tsx` y `strategies/page.tsx`
    - lectura/consumo minimo y auditable de `lifecycle_operational`
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`)
  - mantener fuera de ese bloque:
    - `live console`
    - LIVE lateral
    - lifecycle completo entre entornos
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Siguiente paso exacto despues de RTLOPS-83 - 2026-04-21
- [x] Fundar el segundo consumidor real de `lifecycle_operational` sobre `rtlops81/v1`:
  - `strategies/page.tsx` ahora consume `bot.lifecycle_operational` en una segunda surface minima operativa distinta de `execution/page.tsx`
  - la surface muestra:
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - `lifecycle_operational_by_symbol`
    - `items[*].runtime_symbol_id`
    - `items[*].selection_key`
    - `items[*].net_decision_key`
  - deja visible el estado por simbolo con:
    - `base_lifecycle_state`
    - `operational_status`
    - `lifecycle_state`
    - `selected_strategy_id`
    - errores canonicos por simbolo
  - el wiring queda solo de lectura para auditoria operativa y deriva a `Execution` para overrides puntuales
- [x] Mantener el bloque profesional y acotado:
  - sin tocar el contrato backend ya canonico
  - sin abrir `live console`
  - sin abrir LIVE lateral
  - sin abrir lifecycle completo entre entornos
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `npm.cmd test -- --run src/lib/lifecycle-operational.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- [ ] Siguiente paso exacto recomendado:
  - el preflight fail-closed posterior a `RTLOPS-83` ya quedo resuelto
  - por decision humana explicita del usuario se canoniza `RTLOPS-84` como sucesora minima del frente

## Preflight posterior a RTLOPS-82 - sucesora canonizada - 2026-04-21
- [x] Revalidar que `RTLOPS-82` ya cierra el primer consumidor real de `lifecycle_operational` sobre `rtlops81/v1`:
  - `execution/page.tsx` ya consume `GET/PATCH /api/v1/bots/{bot_id}/lifecycle-operational`
  - la primera surface minima operativa ya quedo absorbida en repo/docs/tests
  - el contrato `rtlops81/v1` ya tiene un consumidor real y auditable sin abrir dominios mayores
- [x] Revalidar que el siguiente gap minimo del frente sigue acotado:
  - el siguiente delta ya no es `live console`
  - no es LIVE lateral
  - no es lifecycle completo entre entornos
  - no requiere refactor transversal
- [x] Canonizacion explicita de la sucesora:
  - por decision humana explicita del usuario se fija `RTLOPS-83`:
    - `Bot Multi-Symbol — segundo consumidor mínimo de lifecycle_operational`
  - ese slice debe resolver solo:
    - segundo consumidor minimo de `lifecycle_operational`
    - segunda surface minima operativa distinta del primer consumidor en `execution/page.tsx`
    - wiring minimo, chico y auditable sobre `rtlops81/v1`
- [x] Siguiente paso exacto recomendado:
  - `RTLOPS-83` ya quedo absorbida en `strategies/page.tsx` como segundo consumidor minimo de `lifecycle_operational`
  - la segunda surface ya consume de forma auditable el subset canonico y mantiene los overrides operativos colgados del primer consumidor en `Execution`

## Siguiente paso exacto despues de RTLOPS-82 - 2026-04-21
- [x] Fundar el primer consumidor real de `lifecycle_operational` sobre `rtlops81/v1`:
  - `execution/page.tsx` ahora consume `GET /api/v1/bots/{bot_id}/lifecycle-operational`
  - la surface minima operativa expone:
    - `allowed_trade_symbols`
    - `rejected_trade_symbols`
    - `progressing_symbols`
    - `blocked_symbols`
    - `lifecycle_operational_by_symbol`
  - por simbolo muestra trazabilidad reutilizando:
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
  - habilita pausa/reanudacion minima por simbolo via `PATCH /api/v1/bots/{bot_id}/lifecycle-operational`
  - solo persiste overrides `paused`; reanudar vuelve al default implicito sin abrir una segunda verdad paralela
- [x] Mantener el bloque profesional y acotado:
  - sin tocar `live console`
  - sin abrir LIVE lateral
  - sin abrir lifecycle completo entre entornos
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `npm.cmd test -- --run src/lib/execution-bots.test.ts` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k lifecycle_operational -q` -> PASS
  - `npm.cmd run typecheck` -> PASS
  - `npm.cmd run build` -> PASS
- [x] Preflight fail-closed posterior ya resuelto:
  - repo + docs/truth + Linear revalidados sobre la punta real que cierra `RTLOPS-82`
  - no existia todavia una hija explicita posterior y la continuidad quedaba ambigua
  - por decision humana explicita del usuario se canoniza `RTLOPS-83` como sucesora minima del frente

## Siguiente paso exacto despues de RTLOPS-81 - 2026-04-20
- [x] Fundar los contratos minimos de lifecycle operativo por simbolo sobre `rtlops80/v1`:
  - `GET /api/v1/bots/{bot_id}/lifecycle-operational`
  - `PATCH /api/v1/bots/{bot_id}/lifecycle-operational`
  - `contract_version` del Bot Registry elevada a `rtlops81/v1`
  - `lifecycle_operational_by_symbol` persistido como storage minimo en `learning/bots.json`
  - solo persiste overrides `paused`; `active` sigue como default implicito para no abrir una segunda verdad paralela
- [x] Mantener el bloque profesional y acotado:
  - sin tocar `live console`
  - sin abrir ejecucion LIVE lateral
  - sin abrir lifecycle completo entre entornos
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle_operational or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`
- [x] Cierre exacto del gap contractual:
  - `lifecycle_operational` consume `rtlops80/v1` y solo agrega pausa operativa minima por simbolo
  - la continuidad sigue acotada al subset `allowed_trade_symbols`
  - `rejected_trade_symbols` permanecen fuera de progresion con motivo visible
  - se reutiliza la trazabilidad por simbolo con `runtime_symbol_id`, `selection_key`, `net_decision_key` y `decision_log_scope`
- [x] Preflight fail-closed posterior ya resuelto:
  - repo + docs/truth + Linear revalidados sobre la punta real que cierra `RTLOPS-81`
  - `rtlops81/v1` ya deja `lifecycle_operational` como capa canonica y consumible
  - no existia todavia una hija explicita posterior y la continuidad quedaba ambigua
  - por decision humana explicita del usuario se canoniza `RTLOPS-82` como sucesora minima del frente
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-82` y resolver solo el primer consumidor real de `lifecycle_operational` sobre `rtlops81/v1`
  - resolver ahi solo:
    - surface minima operativa que consuma `lifecycle_operational`
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols` / `rejected_trade_symbols`)
    - consumo auditable sin abrir un scheduler o engine nuevo
  - mantener fuera de ese bloque:
    - `live console`
    - LIVE lateral
    - lifecycle completo entre entornos
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Siguiente paso exacto despues de RTLOPS-80 - 2026-04-20
- [x] Fundar lifecycle minimo multi-symbol consumiendo el subset ejecutable ya canonizado:
  - `GET /api/v1/bots/{bot_id}/lifecycle`
  - `contract_version` del Bot Registry elevada a `rtlops80/v1`
  - consumo minimo de `policy_state.mode/status` y `runtime.guardrails.execution_ready`
  - progresion solo de `allowed_trade_symbols`
  - exclusion explicita de `rejected_trade_symbols` con motivo visible
  - reuse de trazabilidad por simbolo con:
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
- [x] Mantener el bloque profesional y acotado:
  - sin tocar `live console`
  - sin abrir ejecucion LIVE lateral por simbolo
  - sin abrir lifecycle completo entre entornos
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_bot_registry_identity.py` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -k "registry_contract_surface_is_canonical or lifecycle or runtime" -q` -> PASS
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd test -- --run src/lib/bot-registry.test.ts` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> FAIL inicial en frio por `.next/types` faltantes en esta worktree; PASS al rerun despues de `build`
- [x] Preflight fail-closed posterior ya resuelto:
  - repo + docs/truth + Linear revalidados sobre la punta real que cierra `RTLOPS-80`
  - `rtlops80/v1` ya resuelve `lifecycle` minimo derivado y auditable, pero el dominio sigue con `storage_fields=[]`
  - `RTLOPS-69` (`live console`) y `RTLRESE-25` (lifecycle completo entre entornos) sobrealcanzan y no corresponden como sucesora directa
  - el gap dominante real queda en contratos minimos de lifecycle operativo por simbolo sobre `rtlops80/v1`
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-81` y resolver solo los contratos minimos de lifecycle operativo por simbolo sobre `rtlops80/v1`
  - resolver ahi solo:
    - shape minimo de estado operativo por simbolo
    - storage/API minimo sin crear una segunda verdad paralela
    - continuidad acotada al subset ya canonico (`allowed_trade_symbols`)
    - exclusion explicita de `rejected_trade_symbols` con motivo visible
    - reuse de trazabilidad por simbolo con `runtime_symbol_id`, `selection_key`, `net_decision_key` y `decision_log_scope`
  - mantener fuera de ese bloque:
    - `live console`
    - ejecucion LIVE lateral
    - lifecycle completo entre entornos
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Preflight fail-closed posterior a RTLOPS-79 - lifecycle minimo multi-symbol - 2026-04-20
- [x] Revalidar que la base real ya sostiene abrir lifecycle minimo:
  - repo + docs/truth quedaron coherentes sobre la punta que cierra `RTLOPS-79`
  - `GET /api/v1/bots/{bot_id}/runtime` ya expone `guardrails.execution_ready`, `allowed_trade_symbols`, `rejected_trade_symbols` y `guardrails.prioritization_criterion`
  - el runtime ya expone trazabilidad por simbolo con `runtime_symbol_id`, `selection_key`, `net_decision_key` y `decision_log_scope`
  - `GET /api/v1/bots/{bot_id}/policy-state` ya sostiene el contexto minimo de `mode/status` del bot sin abrir live console
- [x] Revalidar Linear sin maquillaje:
  - `RTLOPS-79` quedo sincronizada a `Done` con comentario de cierre real repo/docs/tests
  - no aparece todavia una hija explicita y limpia para `lifecycle minimo multi-symbol`
  - `RTLRESE-25` sigue siendo un bloque mas grande de lifecycle completo y no corresponde usarlo como sucesora directa de este slice
- [x] Siguiente paso exacto recomendado:
  - abrir la implementacion minima de `lifecycle multi-symbol` consumiendo el subset ejecutable ya canonizado sobre `rtlops77/v1`
  - resolver ahi solo:
    - progresion minima sobre `allowed_trade_symbols`
    - exclusion explicita de `rejected_trade_symbols` por priorizacion
    - trazabilidad por simbolo reutilizando `runtime_symbol_id`, `selection_key`, `net_decision_key` y `decision_log_scope`
    - consumo minimo de `policy_state.mode/status` del bot
  - mantener fuera de ese bloque:
    - live console
    - ejecucion LIVE lateral
    - lifecycle completo entre entornos
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Siguiente paso exacto despues de RTLOPS-79 - 2026-04-20
- [x] Fundar el subset ejecutable y la priorizacion deterministica bajo caps sobre `rtlops77/v1`:
  - cuando `trade_decisions_count > max_live_symbols`, el runtime deja de bloquear todo el neto y prioriza un subset ejecutable por orden canonico de `symbols`
  - `guardrails.status` pasa a `warning` cuando aplica priorizacion sin incoherencia de configuracion
  - `allowed_trade_symbols` y `rejected_trade_symbols` pasan a reflejar el subset permitido vs rechazado por priorizacion
  - `guardrails.prioritization_criterion` queda expuesto como `symbol_order`
  - los simbolos rechazados por priorizacion quedan explicitados a nivel item con `reason_code=trade_decisions_exceed_live_cap`
- [x] Mantener el bloque profesional y acotado:
  - sin abrir lifecycle
  - sin tocar live console
  - sin abrir ejecucion remota LIVE lateral por simbolo
  - sin refactor transversal
- [x] Revalidacion minima real del bloque:
  - `rtlab_autotrader\.venv\Scripts\python.exe -m pytest rtlab_autotrader/tests/test_web_bot_registry_identity.py -q` -> PASS
  - `npm.cmd run build` -> PASS
  - `npm.cmd run typecheck` -> PASS despues de regenerar `.next/types` con `build`
- [x] Siguiente paso exacto recomendado:
  - abrir un preflight fail-closed del lifecycle minimo multi-symbol que consuma el subset ejecutable ya canonizado sobre `rtlops77/v1`
  - revalidar ahi, con repo + docs/truth + Linear, si corresponde recien abrir la implementacion minima de lifecycle
  - mantener fuera de ese preflight:
    - live console
    - ejecucion LIVE lateral
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Siguiente paso exacto despues de RTLOPS-77 - 2026-04-20
- [x] Endurecer el runtime multi-symbol con guardrails y caps explicitos:
  - `runtime.contract_version` elevada a `rtlops77/v1`
  - `caps` y `guardrails` agregados al runtime canonico
  - rechazo de configuracion incoherente cuando `max_live_symbols > max_positions`
  - fail-closed cuando el runtime deriva mas decisiones `trade` que el cap live permitido
- [x] Mantener el bloque profesional y acotado:
  - sin abrir lifecycle
  - sin tocar live console
  - sin abrir ejecucion remota LIVE lateral por simbolo
  - sin refactor transversal
- [x] Preflight fail-closed posterior ya resuelto:
  - repo + docs/truth + Linear revalidados sobre la punta real de `RTLOPS-77`
  - `live console` sigue fuera de alcance
  - abrir `lifecycle` ahora mezclaria de mas la politica de priorizacion bajo caps con el lifecycle operativo
  - el gap dominante real queda en la falta de un subset ejecutable y priorizacion deterministica cuando el neto excede caps
- [x] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-79` y resolver solo el subset ejecutable y la priorizacion deterministica bajo caps sobre `rtlops77/v1`
  - mantener fuera de ese bloque:
    - lifecycle
    - live console
    - ejecucion LIVE lateral
    - cualquier cleanup administrativo no necesario
    - cualquier refactor transversal

## Siguiente paso exacto despues de RTLOPS-76 - 2026-04-20
- [x] Fundar los contratos minimos de runtime/storage/API:
  - `GET /api/v1/bots/{bot_id}/runtime`
  - `runtime` derivado sobre `RTLOPS-72 + RTLOPS-73 + RTLOPS-74 + RTLOPS-75`
  - `contract_version` del Bot Registry elevada a `rtlops76/v1`
  - trazabilidad minima por simbolo con:
    - `runtime_symbol_id`
    - `selection_key`
    - `net_decision_key`
    - `decision_log_scope`
- [x] Mantener el bloque profesional y acotado:
  - sin abrir `RTLOPS-77`
  - sin tocar lifecycle
  - sin tocar live console
  - sin abrir ejecucion remota real por simbolo
- [x] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-77` y resolver solo guardrails, caps y rechazos de configuracion sobre el contrato `rtlops76/v1`
  - mantener fuera de ese bloque:
    - lifecycle
    - live console
    - cualquier refactor transversal
    - cualquier cleanup administrativo no necesario
    - ejecucion remota LIVE fuera del slice ya delimitado
    - features laterales sin dependencia directa de este contrato

## Siguiente paso exacto despues de RTLOPS-75 - 2026-04-18
- [x] Fundar la consolidacion canonica y la decision neta por simbolo:
  - `GET /api/v1/bots/{bot_id}/signal-consolidation`
  - `signal_consolidation` derivado sobre `RTLOPS-72 + RTLOPS-73 + RTLOPS-74`
  - `net_decision_by_symbol` con trazabilidad minima de inputs
  - `contract_version` del Bot Registry elevada a `rtlops75/v1`
  - surface minima de lectura en `strategies/page.tsx`
- [x] Mantener el bloque profesional y acotado:
  - sin abrir `RTLOPS-76/77`
  - sin tocar lifecycle
  - sin tocar live console
  - sin tocar ejecucion remota real por estrategia
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-76` y resolver solo los contratos minimos de runtime/storage/API para colgar la decision neta por simbolo ya canonica de:
    - `RTLOPS-72`
    - `RTLOPS-73`
    - `RTLOPS-74`
    - `RTLOPS-75`
  - mantener fuera de ese bloque:
    - `RTLOPS-77`
    - lifecycle
    - live console
    - cualquier ejecucion separada por estrategia o por subcuenta

## Siguiente paso exacto despues de RTLOPS-74 - 2026-04-18
- [x] Fundar seleccion canonica de estrategia por simbolo:
  - persistencia `strategy_selection_by_symbol`
  - `GET/PATCH /api/v1/bots/{bot_id}/strategy-selection`
  - resolucion deterministica `selected_strategy_by_symbol`
  - criterios minimos `explicit / single_eligible / primary_strategy / pool_order`
  - UI minima util en `strategies/page.tsx`
- [x] Mantener el bloque profesional y acotado:
  - sin abrir `RTLOPS-75/76/77`
  - sin tocar lifecycle
  - sin tocar live console
  - sin abrir execution neta por simbolo
- [x] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-75` y resolver solo la consolidacion de señales y la decision neta por simbolo sobre la base ya cerrada de:
    - `RTLOPS-72`
    - `RTLOPS-73`
    - `RTLOPS-74`
  - mantener fuera de ese bloque:
    - `RTLOPS-76`
    - `RTLOPS-77`
    - lifecycle
    - live console

## Siguiente paso exacto despues de la canonizacion del type-check frio - 2026-04-18
- [x] Reproducir el comportamiento real del dashboard en frio:
  - sin `.next`
  - sin `tsconfig.tsbuildinfo`
  - shell nueva por comando
- [x] Validar la verdad tecnica correcta:
  - `npm.cmd exec tsc -- --noEmit` en frio -> PASS
  - `npm.cmd exec tsc -- --noEmit --incremental false` en frio -> PASS
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit` -> PASS
  - `npm.cmd run build` -> PASS
- [x] Formalizar el comando canonico del repo:
  - `npm.cmd run typecheck`
  - implementado como `tsc --noEmit --incremental false`
- [x] Siguiente paso exacto recomendado:
  - volver al frente funcional y abrir `RTLOPS-74` sobre la linea viva actual
  - mantener fuera de ese bloque cualquier re-auditoria de tooling salvo que aparezca una regresion nueva y reproducible

## Siguiente paso exacto despues de RTLOPS-73 - 2026-04-18
- [x] Fundar elegibilidad canonica simbolo↔estrategia sobre el pool del bot:
  - persistencia `strategy_eligibility_by_symbol`
  - `GET/PATCH /api/v1/bots/{bot_id}/symbol-strategy-eligibility`
  - reconciliacion fail-closed contra pool/universe
  - UI minima util en `strategies/page.tsx`
- [x] Mantener el bloque profesional y acotado:
  - sin tocar backend live
  - sin abrir `RTLOPS-74+`
  - sin tocar lifecycle ni live console
- [x] Caveat tecnico derivado ya cerrado:
  - el microbloque posterior de canonizacion confirmo que el comando canónico correcto del repo es `npm.cmd run typecheck`
  - `next typegen` no es prerequisito obligatorio para el type-check del dashboard
- [ ] Siguiente paso exacto recomendado:
  - volver al frente funcional y abrir `RTLOPS-74`

## Siguiente paso exacto despues del microbloque tecnico de `tsc --noEmit` - 2026-04-18
- [x] Revalidar el caveat tecnico con reproduccion real:
  - `npm.cmd exec tsc -- --noEmit` directo
  - `npm.cmd exec next -- typegen && npm.cmd exec tsc -- --noEmit`
  - `npm.cmd run build`
  - reproduccion en frio sin `.next` ni `tsconfig.tsbuildinfo`
- [x] Cerrar la narrativa falsa:
  - el `tsc` standalone ya pasa tambien en frio en esta punta
  - `next typegen` no cambia el resultado del type-check actual
  - en esta validacion inicial no hizo falta tocar `tsconfig.json`, `package.json` ni `next.config.ts`
- [ ] Siguiente paso exacto recomendado:
  - bloque ya superado por la canonizacion posterior del mismo dia

## Siguiente paso exacto despues de RTLOPS-71 subbloque 2 - 2026-04-18
- [x] Normalizar identidad visible del bot en `backtests/page.tsx`:
  - `display_name + bot_id` en selector, mensajes, resumen filtrado, vista centrica y related bots
- [x] Mantener el bloque quirurgico:
  - sin tocar backend
  - sin tocar `strategies/page.tsx`
  - sin tocar `strategies/[id]/page.tsx`
  - sin tocar comparador legacy ni evidence status
- [x] Caveat tecnico revalidado despues:
  - el microbloque tecnico del 2026-04-18 confirmo que `npm.cmd exec tsc -- --noEmit` ya pasa tambien en frio y que la narrativa de FAIL no describe el estado actual
- [ ] Siguiente paso exacto recomendado:
  - volver a priorizacion tecnica/producto ahora que el caveat quedo cerrado honestamente

## Siguiente paso exacto despues de RTLOPS-71 subbloque 1 - 2026-04-17
- [x] Endurecer el strategy detail para depender del contrato canonico:
  - quitar fallback frontend que reconstruia `truth/evidence`
  - fallar de forma honesta si falta `truth` canonica
  - mostrar aviso explicito si falta `evidence` canonica
- [x] Mantener el bloque quirurgico:
  - sin tocar `backtests/page.tsx` por defecto
  - sin abrir `RTLOPS-73+`
  - sin cleanup transversal del dashboard
- [ ] Siguiente paso exacto recomendado:
  - validar si corresponde un segundo subbloque chico de `RTLOPS-71` sobre surfaces derivadas:
    - naming legacy visible en `backtests/page.tsx`
    - textos/helpers de strategy frontend que todavia sobrevivan fuera de `strategies/[id]`
  - si esa validacion no confirma un subbloque chico y coherente:
    - volver a priorizacion antes de abrir producto nuevo

## Siguiente lote exacto despues del lote 1 de reparacion execution vs registry - 2026-04-17
- [x] Corregir deuda real de surface operatoria en `execution`:
  - quitar `DELETE /api/v1/bots/{bot_id}` de la UI
  - usar soft-archive / restore reales del registry
  - separar `status` runtime de `registry_status`
  - mostrar identidad canonica (`display_name` + `bot_id`) en selector y tabla
- [x] Mantener una reparacion chica y profesional:
  - sin tocar el core de execution/live safety
  - sin abrir `RTLOPS-73+`
  - sin mezclar admin con codigo
- [ ] Siguiente lote exacto recomendado:
  - abrir `RTLOPS-71` y resolver solo deuda fina de strategy/frontend ya absorbido:
    - surfaces que todavia viven de fallback o naming legacy
    - QA fino donde el frontend moderno todavia esta subrepresentado
  - mantener fuera de ese lote:
    - `RTLOPS-73+`
    - lifecycle
    - live console
    - refactor global del dashboard

## Siguiente bloque exacto despues de RTLOPS-72 - 2026-04-17
- [x] Fundar el modelo canonico multi-symbol por bot:
  - storage reutilizando `universe_name`, `universe` y `max_live_symbols`
  - `GET/PATCH /api/v1/bots/{bot_id}/multi-symbol`
  - limites base explicitos y fail-closed por catalogo/registry
- [x] Mantener una implementacion minima-profesional:
  - sin mapping estrategia<->simbolo
  - sin consolidacion de señales
  - sin lifecycle
  - sin live console
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-73` y resolver solo:
    - mapping/elegibilidad base de estrategias por simbolo sobre el modelo canonico multi-symbol ya persistido
    - sin abrir todavia consolidacion, net execution, lifecycle ni live console

## Siguiente bloque exacto despues de RTLRESE-31 - 2026-04-17
- [x] Consolidar el Bot Registry como surface minima canonica:
  - `GET /api/v1/bots/registry-contract`
  - defaults/limites/enums del registry definidos en backend y consumidos por frontend
  - storage real (`learning/bots.json`) visible sin crear una segunda verdad
- [x] Mantener una implementacion minima-profesional:
  - sin reabrir identidad, config base, symbols assignment, strategy pool ni gobierno basico
  - sin tocar runtime live, lifecycle ni live console
  - con frontend y API alineados sobre el mismo shape administrativo
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLOPS-72` como primer bloque del frente `RTLOPS-72+` y resolver solo runtime multi-symbol sobre el registry ya cerrado
  - mantener fuera de ese bloque:
    - lifecycle
    - live console
    - refactor global del registry
    - cleanup Git adicional

## Siguiente bloque exacto despues de RTLRESE-30 - 2026-04-16
- [x] Endurecer Bot Registry con gobierno basico y trazabilidad minima:
  - `last_change_type`
  - `last_change_summary`
  - `last_changed_by`
  - `last_change_source`
  - wiring real en backend/API/UI
- [x] Mantener una implementacion minima-profesional:
  - reactivacion fail-closed contra el registry actual
  - soft-archive sin borrado destructivo
  - visibilidad real de trazabilidad y errores de reactivacion
  - reuse del `decision_log` existente sin abrir auditoria paralela
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLRESE-31` y resolver solo:
    - contratos minimos de storage/API/frontend para el Bot Registry ya endurecido
    - sin reabrir identidad, config base, symbols assignment, strategy pool o gobierno basico ya cerrados en `RTLRESE-26/27/28/29/30`
  - mantener fuera de ese bloque:
    - runtime multi-symbol (`RTLOPS-72+`)
    - lifecycle
    - live console
    - elegibilidad estrategia<->simbolo

## Siguiente bloque exacto despues de RTLRESE-29 - 2026-04-16
- [x] Extender Bot Registry con strategy pool asignado por bot:
  - `pool_strategy_ids`
  - `pool_strategies`
  - `strategy_pool_status`
  - `strategy_pool_errors`
  - `max_pool_strategies`
  - wiring real en backend/API/UI
- [x] Mantener una implementacion minima-profesional:
  - persistencia real sobre el registry ya existente
  - fuente canonica apoyada en `strategy registry / truth`
  - validaciones explicitas de minimo, duplicados, ids invalidos y cap `15`
  - estado fail-closed visible si el pool deja de ser valido
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLRESE-30` y resolver solo:
    - gobierno avanzado / restricciones siguientes del Bot Registry sobre la base ya persistida
    - sin reabrir pool, simbolos o config base ya cerrados en `RTLRESE-27/28/29`
  - mantener fuera de ese bloque:
    - elegibilidad estrategia<->simbolo
    - runtime multi-symbol (`RTLOPS-72+`)
    - lifecycle
    - live console

## Siguiente bloque exacto despues de RTLRESE-28 - 2026-04-16
- [x] Extender Bot Registry con asignacion manual de simbolos por bot:
  - `universe_name`
  - `universe`
  - `max_live_symbols`
  - wiring real en backend/API/UI
- [x] Mantener una implementacion minima-profesional:
  - persistencia real sobre el registry ya existente
  - universo valido reutilizando el catalogo real del sistema
  - validaciones explicitas de dominio, duplicados y cap live
  - estado fail-closed visible si la asignacion deja de ser valida
- [x] Siguiente paso exacto recomendado:
  - abrir `RTLRESE-29` y resolver solo:
    - strategy pool asignado por bot
    - persistencia real del pool
    - limites minimos del pool dentro del registry
  - mantener fuera de ese bloque:
    - elegibilidad estrategia<->simbolo
    - runtime multi-symbol (`RTLOPS-72+`)
    - lifecycle
    - live console

## Siguiente bloque exacto despues de RTLRESE-27 - 2026-04-16
- [x] Extender Bot Registry con configuracion base operativa por bot:
  - `capital_base_usd`
  - `risk_profile`
  - limites minimos de exposicion, perdida y capacidad
  - wiring real en backend/API/UI
- [x] Mantener una implementacion minima-profesional:
  - persistencia real en el registry ya existente
  - validaciones explicitas
  - UI minima conectada al backend real
  - tests reales del bloque
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLRESE-28` y resolver solo:
    - asignacion de simbolos por bot
    - validaciones minimas de simbolos segun `domain_type`
    - superficie minima de UI para ver/agregar/quitar simbolos del bot
  - mantener fuera de ese bloque:
    - strategy pool (`RTLRESE-29`)
    - lifecycle (`RTLRESE-25`)
    - multi-symbol runtime (`RTLOPS-72+`)
    - live console
    - reglas avanzadas de portfolio por simbolo

## Siguiente bloque exacto despues de RTLRESE-26 - 2026-04-14
- [x] Dejar Bot Registry con identidad real y persistente:
  - `bot_id` estable
  - `display_name` editable
  - `alias`
  - `description`
  - `domain_type=spot|futures`
  - `registry_status=active|archived`
  - create/list/get/patch/archive/restore reales
- [x] Conectar UI minima al backend real:
  - alta desde registry
  - listado con identidad canonica
  - edicion inline
  - archivar / restaurar
- [ ] Siguiente paso exacto recomendado:
  - abrir `RTLRESE-27` y resolver solo:
    - capital / budget base por bot
    - risk profile base por bot
    - flags/config minima para que el bot exista como entidad configurable mas alla de su identidad
  - mantener fuera de ese bloque:
    - symbols assignment (`RTLRESE-28`)
    - strategy pool (`RTLRESE-29`)
    - lifecycle (`RTLRESE-25`)
    - multi-symbol runtime (`RTLOPS-72+`)

## Opcion 2 exacta: Binance LIVE readiness real, despues de dejar PAPER canonico - 2026-04-08
- [x] Dejar production online y fail-closed:
  - `/api/v1/health` ya responde `200`
  - el runtime canonico queda en `PAPER`
  - `LIVE` ya no debe verse como operativo mientras la readiness siga pendiente
- [x] Expresar el bloqueo real sin maquillaje:
  - Settings consulta gates de `LIVE`
  - `LIVE` queda bloqueado con razon honesta
  - `SHADOW` se mantiene permitido porque no toca exchange real
- [ ] Siguiente paso exacto:
  - rotar API keys Binance para production
  - aplicar IP whitelist correcta
  - validar permisos minimos de cuenta
  - configurar principal strategy `live`
  - correr rollout/canary real
  - recien cuando `G4/G5/G7/G9` y readiness final esten en `PASS`, habilitar `LIVE`

## Siguiente bloque exacto para confirmar si el `502` estaba en el backfill del decision log - 2026-04-07
- [x] Aislar nueva causa repo-side plausible:
  - `BotDecisionLogRepository.initialize()` seguia haciendo backfill pesado en el arranque sync del servicio.
- [x] Aplicar correccion minima:
  - dejar solo esquema/migraciones minimas en init sync
  - mover backfill de `decision_log` al mantenimiento de startup en background
  - reflejar `decision_log_backfill_failed` si esa etapa se degrada
- [ ] Siguiente paso exacto:
  - mergear este fix
  - esperar auto-deploy de Railway produccion
  - confirmar `GET /api/v1/health -> 200`
  - solo despues revalidar:
    - `/api/v1/data/status`
    - `/api/v1/research/beast/status`
    - `/api/v1/research/mass-backtest/status`

## Siguiente bloque exacto para confirmar recuperacion de `502` tras aliviar startup - 2026-04-07
- [x] Aislar causa repo-side mas fuerte del residual:
  - `LoginRateLimiter` global con backend sqlite en import-time;
  - `ConsoleStore` corriendo seed/sync/reporting en `__init__`;
  - `/api/v1/health` persistiendo estado en vez de solo leer.
- [x] Aplicar correccion minima:
  - lazy init para login rate limiter
  - mantenimiento de `ConsoleStore` no bloqueante
  - startup hooks de sync/recovery no bloqueantes
  - `health` read-only
- [ ] Siguiente paso exacto:
  - confirmar que Railway produccion esta corriendo el deploy ya mergeado
  - esperar auto-deploy de Railway produccion
  - confirmar `GET /api/v1/health -> 200`
  - solo despues revalidar:
    - `/api/v1/data/status`
    - `/api/v1/research/beast/status`
    - `/api/v1/research/mass-backtest/status`

## Siguiente bloque exacto para recuperar `502` en Railway produccion - 2026-04-07
- [x] Aislar una causa concreta de startup en repo:
  - servicios globales construidos por `rtlab_core.web.app` seguian resolviendo `RTLAB_USER_DATA_DIR`/roots runtime por filesystem.
- [x] Aplicar correccion minima:
  - migrar esos constructores a `runtime_path(...)`
  - agregar tests anti-regresion
- [ ] Siguiente paso exacto:
  - confirmar que Railway produccion esta corriendo el deploy ya mergeado
  - esperar auto-deploy de Railway produccion
  - confirmar `GET /api/v1/health -> 200`
  - solo despues revalidar:
    - `/api/v1/data/status`
    - `/api/v1/research/beast/status`
    - `/api/v1/research/mass-backtest/status`

## Siguiente bloque exacto para Backtests / Beast / Masivo tras auditoria seria - 2026-04-07
- [x] Confirmar paridad Beast vs Masivo:
  - comparten `USER_DATA_DIR`, `DataCatalog`, `build_data_provider(...)` y preflight de dataset;
  - no hay evidencia de que uno lea otro root/catalogo.
- [x] Identificar deuda inmediata del dominio:
  - seguian quedando `Path.resolve()` sobre roots runtime dentro de dataset/catalog/provider/engine/artifacts aunque `health/startup` ya se habia saneado.
- [x] Aplicar reparacion chica y coherente en rama de auditoria:
  - introducir `runtime_path(...)`
  - migrar Backtests runtime paths a esa normalizacion
  - hacer fail-honest el panel Beast cuando el backend no responde
  - agregar tests anti-regresion
- [ ] Siguiente paso exacto:
  - confirmar que produccion ya tomo el hardening mergeado en `main`
  - esperar deploy de produccion
  - confirmar `200` en `/api/v1/health`
  - rerun de validacion Backtests:
    - `/api/v1/data/status`
    - `/api/v1/research/beast/status`
    - `/api/v1/research/mass-backtest/status`
  - solo si produccion vuelve a `200`, rebootstrapear `BTCUSDT` y reconfirmar durabilidad/catalogo

## Siguiente bloque exacto para estabilidad de mount detection en produccion - 2026-04-07
- [x] Confirmar que el fix anterior de persistencia dejo de ser solo un problema de catalogo:
  - despues del merge de `#24`, produccion paso a `502 Application failed to respond`
  - el workflow `Production Storage Durability` (`24063115973`) fallo por timeout antes del bootstrap
- [x] Confirmar la hipotesis tecnica mas fuerte:
  - el runtime no debe tocar el filesystem del volumen con `exists()/is_mount()` para decidir persistencia
  - esa sonda puede bloquear el proceso en Railway
- [x] Aplicar correccion minima:
  - detectar mount por `mountinfo` solamente
  - mantener fail-closed sin tocar el volume path
  - quitar `Path.resolve()` del camino critico de `RTLAB_USER_DATA_DIR`
- [ ] Siguiente paso exacto:
  - confirmar que Railway produccion esta corriendo el ajuste ya mergeado
  - esperar que produccion vuelva a `200`
  - rerun `Production Storage Durability`
  - si el workflow pasa `Check mounted storage gate`, recien ahi rebootstrapear `BTCUSDT` y reconfirmar Beast/Backtests

## Siguiente bloque exacto para persistencia durable de datasets en produccion - 2026-04-07
- [x] Confirmar que el problema residual ya no era Beast ni bootstrap:
  - el bootstrap real de `BTCUSDT` funciono
  - Beast completo `BX-000001`
  - el catalogo luego reaparecio vacio
- [x] Confirmar la brecha raiz en runtime:
  - `persistent_storage=true` solo significaba “no esta en `/tmp`”
  - no habia verificacion de mount real
- [x] Aplicar fix fail-closed:
  - detectar mount real en runtime
  - exponer `mount_detected`, `mount_point`, `mount_source`, `selection_drift`
  - bloquear `G10_STORAGE_PERSISTENCE` si el root no esta montado
- [x] Dejar validacion operativa canonica:
  - workflow `production-storage-durability.yml`
  - reusa secretos productivos
  - checa mount real + bootstrap `BTCUSDT` + re-check del dataset exacto `5m`
- [ ] Siguiente paso exacto:
  - correr `production-storage-durability.yml` contra `main`
  - si `mount_detected=false`, corregir mount/variable en Railway produccion
  - si `mount_detected=true` y el dataset sobrevive, volver a validar `csud/backtests`

## Siguiente bloque exacto para Beast/Backtests dataset bootstrap en produccion - 2026-04-06
- [x] Confirmar que el bloqueo actual ya no era `policy_state=missing`:
  - produccion devuelve `policy_state=enabled`
  - `csud` apunta a produccion real
- [x] Confirmar la causa raiz exacta del faltante:
  - `GET /api/v1/data/status` en produccion devolvia `available_count=0`
  - el catalogo se resuelve en `${RTLAB_USER_DATA_DIR}/data`
- [x] Dejar armado el pipeline canonico de Futures:
  - zips oficiales de Binance Futures + `.CHECKSUM`
  - fallback REST oficial
  - base `1m`
  - derivados `5m`, `15m`, `1h`, `4h`, `1d`
  - manifests con provenance
  - seleccion top 40 auditable para `usdm` y `coinm`
- [x] Ejecutar el desbloqueo inmediato en produccion/main:
  - `POST /api/v1/data/bootstrap/binance-futures-public`
  - `market_family=usdm`
  - `symbols=[BTCUSDT]`
  - `start_month=2024-01`
  - `end_month=2024-12`
  - `resample_timeframes=[5m,15m,1h,4h,1d]`
- [x] Validar post-bootstrap:
  - `GET /api/v1/data/status` ya no reporta faltante para `BTCUSDT/5m`
  - Beast ya corrio una prueba real minima en produccion:
    - `run_id=BX-000001`
    - `terminal_state=COMPLETED`
    - `results_count=1`
- [ ] Siguiente paso exacto:
  - ampliar el bootstrap canonico al universo objetivo:
    - top 40 `usdm` TRADING/PERPETUAL
    - top 40 `coinm` TRADING/PERPETUAL
  - mantener `1m` como base unica y derivar `5m/15m/1h/4h/1d`

## Siguiente bloque exacto para Beast en produccion / csud - 2026-04-06
- [x] Confirmar que `bot-trading-ia-csud.vercel.app/backtests` apunta a produccion:
  - `BACKEND_API_URL=https://bot-trading-ia-production.up.railway.app`
- [x] Confirmar que el problema real ya no era frontend parity:
  - `csud` devolvia `policy_state=missing`
  - `staging-2` devolvia `policy_state=enabled`
- [x] Confirmar la causa raiz exacta en produccion:
  - `GET /api/v1/config/policies` reporta ausentes:
    - `/app/config/policies`
    - `/app/rtlab_autotrader/config/policies`
  - el Dockerfile legacy `rtlab_autotrader/docker/Dockerfile` no copiaba `config/`
- [x] Aplicar fix minimo de empaquetado:
  - `COPY config /app/config` en `rtlab_autotrader/docker/Dockerfile`
- [ ] Validar el deploy productivo posterior:
  - `GET /api/v1/config/policies` en produccion debe pasar a `available=true`
  - `GET /api/v1/research/beast/status` en produccion debe dejar `policy_state=missing`
  - `https://bot-trading-ia-csud.vercel.app/backtests` debe reflejar ese estado sano sin warning legacy desalineado

## Siguiente bloque exacto para paridad frontend ↔ staging API en Backtests - 2026-04-06
- [x] Auditar la URL reportada por usuario:
  - `https://bot-trading-ia-csud.vercel.app/backtests`
  - corresponde al proyecto Vercel `bot-trading-ia-csud`
  - ese frontend apunta a `BACKEND_API_URL=https://bot-trading-ia-production.up.railway.app`
- [x] Confirmar la superficie correcta para validar staging:
  - `https://bot-trading-ia-staging-2.vercel.app/backtests`
  - ese frontend apunta a `BACKEND_API_URL=https://bot-trading-ia-staging.up.railway.app`
- [x] Confirmar por payload real que no habia bug de cache ni warning legacy inventado:
  - `csud` devolvia `policy_state=missing` porque estaba leyendo produccion
  - `staging-2` devolvia `policy_state=enabled` porque estaba leyendo staging saneado
- [x] Dejar trazabilidad minima en frontend/ops:
  - `Backtests` expone `Backend objetivo del frontend`
  - `staging-smoke` usa por default `bot-trading-ia-staging-2`
- [ ] Validar el deploy publicado del frontend ya corregido:
  - abrir `https://bot-trading-ia-staging-2.vercel.app/backtests`
  - confirmar que muestra el backend objetivo de staging
  - dejar de usar `bot-trading-ia-csud.vercel.app/backtests` como superficie de validacion de staging

## Siguiente bloque exacto para Railway auto-deploy root-safe - 2026-04-06
- [x] Auditar `staging` real:
  - `rootDirectory=null`
  - `dockerfilePath=docker/Dockerfile`
  - GitHub auto-deploy fallando porque el repo root no tenia ese archivo
- [x] Dejar solucion por codigo/config:
  - `docker/Dockerfile` en repo root
  - `railway.json` con `dockerfilePath=docker/Dockerfile`
  - `watchPatterns` restringidos al backend/config
- [x] Validar con deploy real desde la raiz del repo:
  - deployment `dc35aa67-1c8e-44cc-b21b-8fc2b1413bda`
  - `configFile=railway.json`
  - `status=SUCCESS`
  - `GET /api/v1/health -> 200`
- [ ] Luego, validar el siguiente merge a `main`:
  - debe auto-desplegar sin volver a fallar por `Dockerfile 'docker/Dockerfile' does not exist`

## Siguiente bloque exacto tras mergear PR 1 runtime - 2026-04-05
- [x] Resolver el status viejo de Vercel que bloqueaba `#15`.
- [x] Sacar `#15` de draft y mergearlo a `main` con `Squash and merge`.
- [x] Dejar el monitor de `PAPER` ya presente en default branch.
- [x] Crear una rama limpia para PR 2 documental:
  - `integration/product-inputs-and-truth-main`
- [ ] Abrir y revisar el PR 2 con:
  - `docs/product/inputs/*`
  - `docs/truth/*` minimas asociadas
  - estructura lista para sync administrativo a Linear
- [ ] Una vez mergeado el PR 2:
  - hacer el sync administrativo real a Linear cuando la integracion este disponible
  - elegir un dominio para implementacion backend-first
  - preferencia actual:
    - `Capital & Allocation Control`
    - empezando por `Treasury snapshot consolidado por cuenta y venue`

## Siguiente bloque exacto tras preparar PR 1 runtime live/paper hardening - 2026-04-05
- [x] Crear rama limpia desde `origin/main` para integrar solo runtime validado.
- [x] Dejar afuera:
  - `docs/product/inputs/*`
  - sync/modelado administrativo de Linear
  - backlog/documentacion grande de producto
- [x] Portar runtime live/paper ya validado:
  - `margin_guard`
  - persistencia paper al ledger
  - accounting/backfill paper
  - monitor externo de `PAPER`
- [ ] Abrir y revisar el PR 1 contra `main`.
- [ ] Una vez mergeado el PR 1:
  - dejar activo el cron de `.github/workflows/paper-validation-monitor.yml` en default branch
  - seguir acumulando evidencia honesta de `PAPER`
  - reevaluar `PAPER` cuando suban `orders` / `trading_days`
- [ ] Siguiente PR recomendado despues de este:
  - elegir un dominio grande separado y abrirlo en bloque propio, empezando por backend-first;
  - preferencia actual:
    - `Capital & Allocation Control`
    - empezando por `Treasury snapshot consolidado por cuenta y venue`

## Cierre del bloque RTLOPS-2 / RTLOPS-1 / RTLOPS-7 - 2026-03-18
- [x] Fijar `config/policies/` de la raiz del monorepo como fuente operativa canonica.
- [x] Dejar `rtlab_autotrader/config/policies/` solo como compatibilidad/fallback y no como autoridad equivalente.
- [x] Exponer por API la metadata de autoridad (`authority`) y la taxonomia canonica (`mode_taxonomy`).
- [x] Cerrar el micro-hardening final del frontend de authority/runtime:
  - `lint` deja de escanear `rtlab_dashboard/.pytest_cache` por ignores explicitos en flat config.
  - `auth-backend.test.ts` usa un helper de env de test valido con `NODE_ENV=test` y `BACKEND_API_URL=https://api.example.com`.
  - validacion local final ejecutada:
    - `npm.cmd run lint`
    - `npm.cmd run build`
    - `npx.cmd tsc --noEmit`
- [x] Documentar jerarquia de autoridad tecnica en:
  - `docs/truth/SOURCE_OF_TRUTH.md`
  - `docs/plan/AUTHORITY_HIERARCHY.md`
- [x] Normalizar semanticamente la taxonomia visible:
  - runtime global `PAPER / TESTNET / LIVE`
  - bots `shadow / paper / testnet / live`
  - evidence `backtest / shadow / paper / testnet`
  - `MOCK` como alias legado local, no como runtime real

## Siguiente bloque recomendado
- [ ] Cerrar M2 de `Nucleo Arquitectonico y Policies` en pasos chicos:
  - centralizar thresholds numericos explicitos en YAML;
  - auditar y acotar `execution_modes`, `observability`, `drift`, `health_scoring` y `alert_thresholds` para que no queden como backlog demasiado amplio.
- [ ] Solo despues de ese cierre, abrir el bloque `Binance Catalog + Universes + Live Parity`.

## Seguimiento RTLRESE backend domains/contracts - 2026-03-16
- [x] RTLRESE-13:
  - persistencia backend separada por dominio (`truth/evidence/policy_state/decision_log`).
- [x] RTLRESE-14:
  - contratos FastAPI separados por dominio:
    - `GET /api/v1/strategies/{strategy_id}/truth`
    - `GET /api/v1/strategies/{strategy_id}/evidence`
    - `GET /api/v1/bots/{bot_id}/policy-state`
    - `PATCH /api/v1/bots/{bot_id}/policy-state`
    - `GET /api/v1/bots/{bot_id}/decision-log`
- [ ] Seguimiento chico posterior a RTLRESE-14:
  - migrar consumidores hacia estos contratos de dominio y reducir dependencia de endpoints legacy mezclados (`GET /api/v1/strategies/{id}`, `PATCH /api/v1/bots/{id}`, `GET /api/v1/logs`);
  - agregar smoke HTTP de estos endpoints cuando la venv tenga `httpx` y pueda correr `starlette.testclient`.
- [ ] Pendiente chico posterior a RTLRESE-13:
  - partir `RegistryDB` en repos internos por subdominio;
  - sacar helpers residuales de bot refs / breaker mode del `ConsoleStore`;
  - evaluar si `strategy_policy_guidance` debe quedar en `truth/` o migrar a un subdominio de policy mas especifico.

## Cierre inmediato post RTLRESE-16
- [x] Frontera documental canonica consolidada en `docs/truth`:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- [x] Separacion visual frontend entre:
  - `strategy_truth`
  - `strategy_evidence`
  - `bot_policy_state`
  - `bot_decision_log`
- [x] Dominios y endpoints canonicos ya absorbidos en la base real:
  - `rtlab_autotrader/rtlab_core/domains/*.py` ya esta trackeado
  - `GET /api/v1/strategies/{id}/truth`
  - `GET /api/v1/strategies/{id}/evidence`
  - `GET/PATCH /api/v1/bots/{id}/policy-state`
  - `GET /api/v1/bots/{id}/decision-log`
- [x] Reejecutar validacion frontend real con Node disponible:
  - `npm.cmd run build` -> PASS
  - `npm.cmd exec tsc -- --noEmit` -> PASS tambien en frio tras limpieza controlada de artefactos locales (`.next/types`, `.next/dev/types`, `tsconfig.tsbuildinfo`)
- [ ] Si aparece una pagina dedicada de bots en RTLRESE-16:
  - conservar la misma separacion semantica ya aplicada en `Execution`;
  - no volver a mezclar runtime global con `policy_state` del bot.
- [x] Frontend base ya opera sobre esos contratos en `strategies/[id]` y `execution`.
- [x] Ajustar los mensajes legacy que seguian diciendo que RTLRESE-14 no estaba integrada.
- [ ] Pendiente chico residual:
  - si reaparece un backend remoto viejo sin contratos de dominio, degradar con mensaje transicional honesto;
  - no volver a presentar esa degradacion como si `RTLRESE-13/14/15` siguieran sin absorberse en la base real.

## Siguiente bloque chico tras RTLRESE-7
- [x] Clasificacion minima `trusted/legacy/quarantine` en `strategy_evidence`.
- [x] Exclusión de `quarantine` de aprendizaje, guidance y rankings de Option B.
- [x] `legacy` conservado con `needs_validation` explicito y penalizacion de confianza.
- [ ] Exponer `evidence_status/evidence_flags` en endpoints o UI solo donde haga falta auditoria operativa, sin volver a mezclar truth con evidence.
- [ ] Extender esta misma frontera a rankings/catalogos fuera de Option B solo cuando exista un consumidor real y justificado.
- [ ] Revisar si conviene un backfill chico para episodios legacy historicos que hoy no traen metadata suficiente para clasificacion fina.
- [ ] Mantener RTLRESE-10 separado: no mezclar esta cuarentena de evidencia con cambios nuevos de producto, frontend o refactors masivos.
## RTLRESE-10 · research funnel / trial ledger
- [x] Exponer `GET /api/v1/research/funnel`.
- [x] Exponer `GET /api/v1/research/trial-ledger`.
- [x] Mostrar `Research Funnel y Trial Ledger` en `Backtests`.
- [x] Marcar visualmente `trusted/legacy/quarantine` sin vender evidence degradada como confiable.
- [ ] Repetir smoke HTTP de `test_web_live_ready.py` cuando la venv tenga `httpx`.
- [ ] Correr `lint` / `tsc --noEmit` / `build` del dashboard en una maquina con `node`/`npm` disponibles en PATH.
- [ ] Cuando exista estado canonico persistido de evidence en esta linea de codigo, hacer que funnel/ledger lo lean directamente y dejar de derivarlo on-the-fly.

## Tramo vigente (experience learning + shadow + no-live)
- [x] Experience store persistente integrado al registry SQLite.
- [x] Opcion B con proposals, rationale y gating conservador.
- [x] Shadow/mock en vivo sin ordenes, con experiencia `source=shadow`.
- [x] UI de estrategias ampliada con:
  - propuestas
  - guidance
  - estado shadow
  - experiencia por fuente por bot
- [x] UI de backtests ampliada con:
  - selector de bot
  - `Usar pool del bot`
  - fix del `422` en `Backtests / Runs`
- [x] Documentacion base creada:
  - `docs/research/EXPERIENCE_LEARNING.md`
  - `docs/research/BRAIN_OF_BOTS.md`
  - `docs/runbooks/SHADOW_MODE.md`
- [x] Evidencia local escrita del tramo:
  - `docs/audit/LEARNING_EXPERIENCE_VALIDATION_20260306.md`
  - bestia real `BX-000001` completado
  - shadow/mock con default corregido persistiendo experiencia real
- [x] Root de `config/policies` resuelto por YAML reales en backend:
  - evita elegir `/app/config/policies` vacio en deploy
  - habilita que `Modo Bestia` refleje la policy publicada correcta

## Proximo tramo tecnico real
1. Revalidar backend publicado despues del deploy de este fix:
   - `GET /api/v1/research/beast/status` debe dejar de reportar snapshot vacio si el runtime tiene los YAML nested
   - la UI no debe mostrar `Modo Bestia deshabilitado` salvo que la policy real este en `enabled: false`
2. Validar en deploy publicado que `Research Batch` / `Modo Bestia` devuelven `400` fail-closed cuando falta dataset real:
   - no debe crearse un batch nuevo en estado `FAILED` solo por dataset ausente
   - el detalle debe exponer `market/symbol/timeframe` y la accion recomendada
3. Persistir atribucion historica exacta `run_id -> bot_id` / `episode_id -> bot_id`:
   - hoy la vista bot-centrica de runs usa el pool actual del bot
   - falta guardar la relacion historica explicita para no depender de cambios futuros del pool
4. Agregar evidencia visual/operativa de la pestana de aprendizaje en `docs/audit/`.
5. Mantener `LIVE_TRADING_ENABLED=false` y cerrar runtime real solo al final del programa.

## Riesgos abiertos del tramo
- NO EVIDENCIA de OPE conservador (`IPS/DR/SWITCH`) cableado al motor de promotion.
- NO EVIDENCIA de RL offline serio en produccion.
- Shadow sigue siendo simulacion de ejecucion, no orden real.
- Parte de la bibliografia TXT local sigue vacia/danada y reduce trazabilidad automatica.

## Tramo vigente (cleanroom + staging online, sin LIVE)
- [x] Documentacion ordenada con indice unico:
  - `docs/START_HERE.md`
  - `docs/audit/INDEX.md`
  - `docs/_archive/README_ARCHIVE.md`
- [x] App online en staging (solo no-live):
  - frontend: `https://bot-trading-ia-staging.vercel.app`
  - backend: `https://bot-trading-ia-staging.up.railway.app`
  - health backend esperado: `ok=true`, `mode=paper`, `runtime_ready_for_live=false`.
- [x] Runbooks de rollback documentados:
  - `docs/deploy/VERCEL_STAGING.md`
  - `docs/deploy/RAILWAY_STAGING.md`
- [x] Policy de logging seguro publicada:
  - `docs/security/LOGGING_POLICY.md` (CWE-532).

## Proximo tramo operativo (sin habilitar LIVE)
1. [x] Ejecutado smoke de staging del dia y evidencia registrada:
   - `docs/audit/STAGING_SMOKE_20260305.md`
   - comando: `python scripts/staging_smoke_report.py --report-prefix artifacts/staging_smoke_ghafree`
2. Mantener smoke diario en staging (login + `/api/v1/health` + `/api/v1/bots`) y registrar evidencia en `docs/audit/`.
   - Nota: si faltan secretos locales, el script marca `NO_EVIDENCE_NO_SECRET` para checks autenticados.
   - workflow automatizado: `Staging Smoke (GitHub VM)` (`/.github/workflows/staging-smoke.yml`).
3. Mantener enforcement no-live en entornos de prueba:
   - `LIVE_TRADING_ENABLED=false`
   - `KILL_SWITCH_ENABLED=true`
   - `MODE/TRADING_MODE=paper` (o `testnet` cuando aplique).
4. Cerrar pendientes tecnicos de runtime end-to-end (orden/fill/reconciliacion/costos) antes de cualquier canary LIVE.
5. Revalidar security CI y branch protection en cada release de hardening.
6. Preparar checklist final paper -> testnet -> canary -> live (sin ejecutar live hasta aprobacion explicita).

## Actualizacion tecnica AP-BOT-1024 (2026-03-05)
- [x] Workflow diario de smoke staging agregado:
  - `/.github/workflows/staging-smoke.yml`
- [x] Validacion bibliografica del patch:
  - `docs/audit/AP_BOT_1024_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - correr al menos 1 run remoto del workflow y registrar artefacto en `docs/audit/`.
  - nota: hoy el workflow todavia no existe en `main`; `gh workflow run staging-smoke.yml` devuelve `404` hasta merge a branch por defecto.

## Actualizacion tecnica AP-BOT-1025 (2026-03-05)
- [x] Fix workflow `remote-protected-checks` en rama tecnica:
  - `strict=false` ahora usa `--no-strict`.
  - eliminado fallback insecure `--password` por CLI.
- [x] Evidencia del hallazgo previo en `main`:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732410544_20260305.md`
- [x] Validacion del fix en corrida real (rama tecnica):
  - `docs/audit/PROTECTED_CHECKS_GHA_22732584979_NON_STRICT_20260305.md`
- [ ] Pendiente operativo:
  - re-run remoto del workflow ya corregido (tras merge) para validar staging con flujo actualizado.

## Actualizacion tecnica AP-BOT-1026 (2026-03-05)
- [x] Workflows remotos con seleccion de secretos por entorno:
  - `remote-protected-checks.yml` y `staging-smoke.yml` priorizan `RTLAB_STAGING_*` en staging.
- [x] No-regresion validada en produccion:
  - `docs/audit/PROTECTED_CHECKS_GHA_22732769817_20260305.md` (`success`).
- [ ] Pendiente operativo:
  - cargar/validar `RTLAB_STAGING_AUTH_TOKEN` o `RTLAB_STAGING_ADMIN_PASSWORD` para runs autenticados de staging.
  - evidencia actual del faltante: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22732896736_20260305.md`.

## Actualizacion tecnica AP-BOT-1027 (2026-03-05)
- [x] Hardening de workflows para separar secretos por entorno sin fallback cruzado:
  - `remote-protected-checks.yml`
  - `staging-smoke.yml`
- [x] Runs remotos post-push registrados:
  - produccion `strict=true` sin regresion:
    - `docs/audit/PROTECTED_CHECKS_GHA_22733438064_20260305.md`
  - staging fail-fast con mensaje explicito de secreto faltante:
    - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22733461982_20260305.md`
- [ ] Pendiente operativo:
  - cargar `RTLAB_STAGING_AUTH_TOKEN` o `RTLAB_STAGING_ADMIN_PASSWORD` y re-ejecutar check staging.

## Actualizacion tecnica AP-BOT-1028 (2026-03-05)
- [x] Runbook de secrets publicado:
  - `docs/deploy/GITHUB_ACTIONS_SECRETS.md`
- [ ] Pendiente operativo:
  - aplicar `gh secret set RTLAB_STAGING_ADMIN_PASSWORD` (o token staging) y repetir run staging.

## Actualizacion tecnica AP-BOT-1029 (2026-03-05)
- [x] Runtime readiness con refresh inmediato tras cache negativo:
  - `RuntimeBridge._runtime_exchange_ready(...)`
- [x] Tests runtime agregados y en PASS:
  - `docs/audit/AP_BOT_1029_BIBLIO_VALIDATION_20260305.md`
- [x] Revalidacion remota post-patch:
  - `docs/audit/PROTECTED_CHECKS_GHA_22733869311_20260305.md`
- [ ] Pendiente operativo:
  - seguir cerrando tramo runtime real para `G9_RUNTIME_ENGINE_REAL=PASS` en fase final.

## Actualizacion tecnica AP-BOT-1030 (2026-03-05)
- [x] Script de automatizacion GitHub VM agregado:
  - `scripts/run_protected_checks_github_vm.ps1`
- [x] Revalidacion remota automatizada en `success`:
  - `docs/audit/PROTECTED_CHECKS_GHA_22734260830_20260305.md`
  - campos canonicos:
    - `overall_pass=true`
    - `protected_checks_complete=true`
    - `g10_status=PASS`
    - `g9_status=WARN`
    - `breaker_ok=true`
    - `internal_proxy_status_ok=true`
- [x] Validacion bibliografica del patch:
  - `docs/audit/AP_BOT_1030_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - mantener este script como runner canonico de checks protegidos en releases no-live.

## Actualizacion tecnica AP-BOT-1031 (2026-03-05)
- [x] Runtime fail-closed ante orden local no verificada:
  - no cerrar localmente cuando `order status` falla;
  - bloquear submit remoto si hay orden local abierta no verificada.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1031_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - completar tramo runtime real restante para llevar `G9_RUNTIME_ENGINE_REAL` a `PASS` al final del programa.

## Actualizacion tecnica AP-BOT-1032 (2026-03-05)
- [x] Submit runtime bloqueado sin snapshot de cuenta valido:
  - `reason=account_positions_fetch_failed` en `testnet/live`.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1032_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - cerrar wiring runtime real restante y revalidar remoto post-deploy para mover `G9_RUNTIME_ENGINE_REAL` a `PASS`.

## Actualizacion tecnica AP-BOT-1033 (2026-03-05)
- [x] Submit runtime bloqueado con reconciliacion no valida:
  - `reason=reconciliation_not_ok` cuando `runtime_reconciliation_ok=false`.
- [x] Tests de regresion en verde:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1033_BIBLIO_VALIDATION_20260305.md`
- [ ] Pendiente operativo:
  - desplegar rama tecnica y confirmar en entorno remoto que el guard mantiene `no-live` estable sin falsos positivos de submit.

## Actualizacion tecnica AP-BOT-1034 (2026-03-05)
- [x] Runner de checks protegidos robustecido para fallo temprano sin JSON:
  - `scripts/run_protected_checks_github_vm.ps1` ahora emite resumen diagnostico `NO_EVIDENCE`.
- [x] Evidencia de bloqueo staging registrada:
  - `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22738098708_20260305.md`
  - causa: `401 Invalid credentials`.
- [x] Sanity run produccion post-patch en verde:
  - `docs/audit/PROTECTED_CHECKS_GHA_22738228159_20260305.md`
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1034_BIBLIO_VALIDATION_20260305.md`
- [x] Revalidacion de credenciales staging completada:
  - re-run `22740010128` confirma auth staging OK con `username=Wadmin`;
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22740010128_20260305.md`.
- [x] Pendiente operativo cerrado por AP-BOT-1035:
  - criterio no-live de staging aplicado y revalidado en run `22741088468` (`success`).

## Actualizacion tecnica AP-BOT-1035 (2026-03-05)
- [x] Reporter de checks con criterio no-live exclusivo para staging:
  - `scripts/ops_protected_checks_report.py` agrega `--allow-staging-warns`;
  - en staging permite `G10=WARN` y `breaker=NO_DATA` sin relajar produccion.
- [x] Workflow remoto actualizado:
  - `/.github/workflows/remote-protected-checks.yml` aplica `--allow-staging-warns` cuando `base_url` contiene `staging`.
- [x] Revalidacion remota staging en verde:
  - run `22741088468` -> `success`
  - evidencia: `docs/audit/PROTECTED_CHECKS_STAGING_GHA_22741088468_20260305.md`.
- [x] Persistencia staging corregida sin crash:
  - volumen operativo en `/app/user_data`;
  - `RTLAB_USER_DATA_DIR=/app/user_data`;
  - run `22741651051` en `success` con `g10_status=PASS`.
- [x] Validacion bibliografica:
  - `docs/audit/AP_BOT_1035_BIBLIO_VALIDATION_20260305.md`.
- [x] Pendiente operativo cerrado:
  - staging ya no usa `/tmp` para user data.

## Actualizacion operativa (2026-03-05)
- [x] Re-run `Remote Protected Checks (GitHub VM)` en `success` (run `22704105623`) con `strict=true`.
- [x] Campos de cierre verificados:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- [ ] Pendiente mantenido: `G9_RUNTIME_ENGINE_REAL=PASS` para habilitacion LIVE al final del programa.

## Actualizacion tecnica AP-8001 (2026-03-04)
- [x] BFF fail-closed para fallback mock en error de backend:
  - `production/staging` no permiten fallback mock.
  - `USE_MOCK_API=false` bloquea fallback en cualquier entorno.
- [x] Reglas centralizadas reutilizadas por:
  - `src/app/api/[...path]/route.ts`
  - `src/lib/events-stream.ts`
- Evidencia:
  - `npm test -- --run src/lib/security.test.ts` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar wiring runtime broker/exchange end-to-end (orden/fill/reconciliacion real) y corrida verde de `Security CI` root.

## Actualizacion tecnica AP-8002 (2026-03-04)
- [x] Workflow `security-ci` endurecido para instalar `gitleaks` desde release oficial versionado (`8.30.0`) con retries.
- [x] Fallback agregado a install script versionado (`v8.30.0`) + check fail-closed de binario instalado.
- [x] Export `PATH` en el mismo step de instalacion para validar `gitleaks version` en esa corrida.
- [x] Baseline canónica versionada para CI:
  - `docs/security/gitleaks-baseline.json`
  - `scripts/security_scan.sh` actualizado para usarla por defecto.
- [x] `setup-python` en Security CI alineado a `3.11`.
- [x] `actions/checkout` actualizado a `fetch-depth: 0` para alinear `gitleaks git` con baseline historica.
- [x] Corrida verde validada en GitHub Actions (`Security CI`) y `FM-SEC-004` cerrado.
- Evidencia local:
  - cambio en `/.github/workflows/security-ci.yml` (checkout + install tooling).
  - reproduccion del fallo en clone shallow (`1 commit scanned`, `leaks found: 1`) y validacion PASS al convertir a historial completo (`88 commits scanned`, `no leaks found`).
  - run GitHub Actions `22697627615` -> `success` (job `security` `65807494809`).

## Actualizacion tecnica AP-8007 (2026-03-04)
- [x] Thresholds de gates unificados a fuente canonica `config/policies/gates.yaml`.
- [x] Eliminado fallback permisivo a `knowledge/policies/gates.yaml` en learning thresholds.
- [x] Fail-closed aplicado cuando falta config (`pbo/dsr` requeridos + defaults estrictos).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_learning_service_gates_source.py rtlab_autotrader/tests/test_gates_policy_source_fail_closed.py rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS (`17 passed`).
- Pendiente inmediato:
  - completar runtime real end-to-end (broker/exchange) y confirmar corrida verde del workflow `Security CI` en GitHub.

## Actualizacion tecnica AP-8011 (2026-03-04)
- [x] Optimizacion incremental aplicada en `/api/v1/bots`:
  - carga lazy de recomendaciones en `cache miss`;
  - indexado de runs limitado a estrategias de pools activos;
  - cap por `(strategy_id, mode)` con `BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE`.
- [x] Regresion funcional del endpoint:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- [ ] Pendiente de cierre:
  - rerun benchmark remoto para confirmar `p95` estable en entorno productivo (objetivo `< 300ms` sostenido).

## Actualizacion tecnica AP-8003 (2026-03-04)
- [x] Reconciliacion runtime alineada a semantica real de `openOrders`:
  - compara exchange vs `OMS.open_orders()` (no incluye ordenes locales cerradas).
- [x] Cierre de ordenes locales abiertas ausentes en exchange con grace:
  - `RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC` (default `20`).
- [x] Tests nuevos de regresion runtime en verde:
  - `test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation`
  - `test_runtime_sync_testnet_closes_absent_local_open_orders_after_grace`
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or runtime_stop_testnet_cancels_remote_open_orders_idempotently" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or g9_live" -q` -> PASS (`11 passed`).
- Pendiente inmediato:
  - completar wiring de ejecucion real por señales (no solo seed/diagnose/reconcile), y rerun de checks protegidos + benchmark remoto.


## Actualizacion tecnica AP-8012 (2026-03-04)
- [x] `breaker_events` en modo fail-closed por defecto:
  - `store.breaker_events_integrity(..., strict=True)` default estricto.
  - endpoint `/api/v1/diagnostics/breaker-events` con `strict=true` default.
- [x] `ops_protected_checks_report.py` endurecido:
  - `--strict` default `true`.
  - `--no-strict` agregado como override explicito.
- [x] `FM-EXEC-003` cerrado.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "breaker_events_integrity_endpoint" -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "alerts_include_operational_alerts_for_drift_slippage_api_and_breaker or alerts_operational_alerts_clear_when_runtime_recovers" -q` -> PASS.
## Actualizacion tecnica AP-BOT-1001/AP-BOT-1002 (2026-03-04)
- [x] AP-BOT-1001: coherencia de ejecucion por estrategia/familia en BacktestEngine.
- [x] AP-BOT-1002: inferencia `orderflow_feature_set` fail-closed + check `known_feature_set` en promotion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_backtest_execution_profiles.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_backtest_strategy_dispatch.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_feature_set_fail_closed.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "validate_promotion_blocks_mixed_orderflow_feature_set or mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo" -q` -> PASS.

## Actualizacion tecnica AP-BOT-1003 (2026-03-04)
- [x] Estabilizacion de `/api/v1/bots` para cardinalidad alta:
  - auto-disable de logs recientes en polling default con muchos bots (`BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT`, default `40`);
  - override explicito `recent_logs=true` preservado;
  - cache key separa `source=default|explicit`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "bots_overview" -q` -> PASS (`7 passed`).
- Siguiente AP recomendado:
  - cerrar runtime real end-to-end (idempotencia submit/cancel/fill + reconciliacion de posiciones/ordenes externas).

## Actualizacion tecnica AP-BOT-1004 (2026-03-04)
- [x] Runtime `testnet/live` sin avance de fills simulados en loop local.
- [x] OMS local sincronizado desde `openOrders` para mejorar coherencia de reconciliacion.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`9 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato:
  - wiring de submit/cancel/fill real con `client_order_id` idempotente y reconciliacion de posiciones (no solo open orders).

## Actualizacion tecnica AP-BOT-1005 (2026-03-04)
- [x] Cancel remoto idempotente por `client_order_id/order_id` en runtime `testnet/live` para `stop/kill/mode_change`.
- [x] Parser comun de `openOrders` reutilizado en reconciliacion + cancel.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or live_mode_blocked_when_runtime_engine_is_simulated or bots_overview" -q` -> PASS (`10 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers" -q` -> PASS.
- Pendiente inmediato de runtime real:
  - submit real idempotente (`newClientOrderId`) con pipeline de señales/ejecución, y reconciliacion de posiciones (no solo órdenes abiertas).

## Actualizacion tecnica AP-BOT-1006 (2026-03-04)
- [x] Submit remoto idempotente agregado en runtime `testnet/live` con `newClientOrderId` y ventana configurable.
- [x] Feature flag segura por defecto (`RUNTIME_REMOTE_ORDERS_ENABLED=false`) para no alterar operacion no-live actual.
- [x] Trazabilidad runtime agregada (`runtime_last_remote_submit_at`, `runtime_last_remote_client_order_id`, `runtime_last_remote_submit_error`).
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS.
- Pendiente inmediato:
  - cerrar `AP-BOT-1007`: reconciliacion de posiciones reales (`/api/v3/account`) y wiring de costos/fills finales end-to-end.

## Actualizacion tecnica AP-BOT-1007 (2026-03-04)
- [x] Reconciliacion de posiciones runtime `testnet/live` contra account snapshot real (`/api/v3/account`).
- [x] Posiciones runtime/risk priorizan balances reconciliados cuando estan disponibles.
- [x] Fallback seguro a posiciones derivadas de `openOrders` cuando account snapshot falla.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`7 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1008`: wiring final de costos/fills netos por ejecucion real (fees/slippage/funding por run/runtime) para cierre no-live.

## Actualizacion tecnica AP-BOT-1008 (2026-03-04)
- [x] Costos runtime por fill-delta integrados en `execution metrics` (fees/spread/slippage/funding/total).
- [x] Reset por sesion runtime (`start`/`mode_change`) para evitar mezcla de acumulados.
- [x] Fail-closed de costos runtime en telemetry sintetica.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_execution_metrics_accumulate_costs_from_fill_deltas or execution_metrics_fail_closed_when_telemetry_source_is_synthetic or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot or runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default or runtime_stop_testnet_cancels_remote_open_orders_idempotently or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression or g9_live_passes_only_when_runtime_contract_is_fully_ready" -q` -> PASS (`9 passed`).
- Pendiente inmediato:
  - cerrar `AP-BOT-1009`: hardening de seguridad operativa restante (`--password` en workflows/scripts remotos y validacion CI security root).

## Actualizacion tecnica AP-BOT-1009 (2026-03-04)
- [x] Eliminado uso de `--password` en automatizacion remota (workflows + `scripts/*.ps1`).
- [x] Scripts remotos endurecidos (`seed_bots_remote.py`, `check_storage_persistence.py`): `--password` queda deprecado y bloqueado por defecto (requiere `ALLOW_INSECURE_PASSWORD_CLI=1`).
- [x] Security CI reforzado con guard fail-closed para detectar regresiones de `--password`.
- [x] Revalidacion local de seguridad ejecutada en PASS (`pip-audit` + `gitleaks`).
- Evidencia:
  - `python -m py_compile scripts/seed_bots_remote.py scripts/check_storage_persistence.py` -> PASS.
  - `C:\Program Files\Git\bin\bash.exe scripts/security_scan.sh` -> PASS.
  - `rg -n --glob '*.yml' --glob '!security-ci.yml' -- '--password([[:space:]]|=|\\\")' .github/workflows` -> sin matches.
  - `rg -n --glob '*.ps1' -- '--password([[:space:]]|=|\\\")' scripts` -> sin matches.
- Pendiente inmediato:
  - cerrar `AP-BOT-1010`: estabilizacion final operativa (latencia/soak/checklist no-live de cierre).

## Actualizacion tecnica AP-BOT-1010 (2026-03-04)
- [x] Checklist formal de cierre no-live generado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md`.
- [x] Tramo no-live/testnet consolidado en estado GO.
- [ ] LIVE postergado hasta fase final (configuracion APIs/canary/rollback).
- Pendiente inmediato:
  - avanzar con runtime orientado por senales de estrategia para reducir brecha FM-EXEC-001/FM-EXEC-005.

## Actualizacion tecnica AP-BOT-1011 (2026-03-04)
- [x] Runtime remoto ahora decide submit desde estrategia principal (no semilla ciega).
- [x] Guardas fail-closed previas al submit:
  - estrategia principal valida y habilitada;
  - `risk.allow_new_positions=true`;
  - sin posiciones abiertas reconciliadas;
  - sin cooldown activo ni open orders pendientes.
- [x] Trazabilidad de senal runtime agregada:
  - `runtime_last_signal_action`,
  - `runtime_last_signal_reason`,
  - `runtime_last_signal_strategy_id`,
  - `runtime_last_signal_symbol`,
  - `runtime_last_signal_side`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1011_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency or runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`91 passed`).
- Pendiente inmediato:
  - cerrar lifecycle final de ejecucion real (partial fills/cancel-replace/estado final de orden) para pasar FM-EXEC-001/FM-EXEC-005 a CERRADO.

## Actualizacion tecnica AP-BOT-1012 (2026-03-04)
- [x] Runtime ahora resuelve orden ausente via `order status` remoto antes de cerrar localmente.
- [x] Cierre por estado remoto implementado:
  - `FILLED`/`CANCELED`/`EXPIRED`/`REJECTED` con mapeo de estado local consistente.
- [x] Si orden sigue `NEW/PARTIALLY_FILLED/PENDING_CANCEL`, se mantiene abierta y se reinyecta al snapshot de reconciliacion.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1012_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`14 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`93 passed`).
- Pendiente inmediato:
  - cerrar parte final de runtime end-to-end (cancel-replace/partial fills avanzados + wiring de riesgo en el mismo ciclo de decision).

## Actualizacion tecnica AP-BOT-1013 (2026-03-04)
- [x] Submit remoto movido despues del calculo de riesgo del mismo ciclo.
- [x] Submit bloqueado cuando el decisionado de riesgo del ciclo actual no permite nuevas posiciones.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1013_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_flat_skips_remote_submit or runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`5 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - cerrar tramo restante de runtime real (cancel-replace/fills parciales avanzados) y revalidar checks protegidos + benchmark remoto.

## Actualizacion tecnica AP-BOT-1014 (2026-03-04)
- [x] Submit runtime reutiliza snapshot de cuenta del ciclo y evita doble `GET /api/v3/account`.
- [x] Se mantiene gate funcional de posiciones abiertas con menor overhead de API.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1014_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_strategy_signal_meanreversion_submits_sell or runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet or runtime_stop_testnet_cancels_remote_open_orders_idempotently or g9_live_passes_only_when_runtime_contract_is_fully_ready or g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers"` -> PASS (`15 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`94 passed`).
- Pendiente inmediato:
  - completar cierre de runtime end-to-end restante (cancel-replace/fills parciales avanzados) y ejecutar checks protegidos remotos.

## Actualizacion tecnica AP-BOT-1015 (2026-03-04)
- [x] Cobertura de regresion agregada para estados remotos:
  - `PARTIALLY_FILLED`,
  - `REJECTED`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1015_BIBLIO_VALIDATION_20260304.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new"` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py` -> PASS (`96 passed`).
- Pendiente inmediato:
  - completar bloque de runtime real restante (cancel-replace avanzado + revalidacion remota protegida).

## Actualizacion tecnica AP-BOT-1016 (2026-03-05)
- [x] Guard fail-closed agregado para submit remoto en `mode=live`:
  - `LIVE_TRADING_ENABLED=false` bloquea ordenes nuevas en runtime;
  - se registra `runtime_last_remote_submit_error=LIVE_TRADING_ENABLED=false`.
- [x] Test de regresion agregado:
  - `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1016_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_flat_skips_remote_submit or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle or live_skips_submit_when_live_trading_disabled" -q` -> PASS (`4 passed`).
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation or runtime_sync_testnet_closes_absent_local_open_orders_after_grace or runtime_sync_testnet_marks_absent_open_order_filled_from_order_status or runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new or runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status or runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`6 passed`).
- Pendiente inmediato:
  - cerrar tramo runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE ahora).

## Actualizacion tecnica AP-BOT-1017 (2026-03-05)
- [x] Telemetria de motivo de submit agregada al runtime:
  - nuevo campo `runtime_last_remote_submit_reason`.
- [x] Submit exitoso ahora deja `reason=submitted` para trazabilidad.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1017_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "strategy_signal_meanreversion_submits_sell or live_skips_submit_when_live_trading_disabled or strategy_signal_flat_skips_remote_submit or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - mantener cierre de runtime real restante (cancel-replace/fills avanzados/reconciliacion final) para `G9_RUNTIME_ENGINE_REAL=PASS`.

## Actualizacion tecnica AP-BOT-1018 (2026-03-05)
- [x] Revalidacion remota de latencia en GitHub VM:
  - workflow `Remote Bots Benchmark (GitHub VM)` run `22706414197` en `success`.
  - evidencia: `docs/audit/BOTS_OVERVIEW_BENCHMARK_GHA_22706414197_20260305.md`.
- [x] Resultado objetivo:
  - `p95_ms=184.546` (`PASS` contra `<300ms`),
  - `server_p95_ms=0.07`,
  - `rate_limit_retries=0`.
- [x] Hardening menor del workflow:
  - fix de quoting en `/.github/workflows/remote-benchmark.yml` (`Build summary`) para evitar ruido no bloqueante por backticks.
- Pendiente inmediato:
  - cerrar tramo runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE en esta fase).

## Actualizacion tecnica AP-BOT-1019 (2026-03-05)
- [x] Higiene de telemetria runtime:
  - `runtime_last_remote_submit_reason` se limpia al salir de runtime real;
  - tambien se limpia cuando `exchange_ready` falla.
- [x] Test de regresion agregado:
  - `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1019_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "live_skips_submit_when_live_trading_disabled or clears_submit_reason_when_runtime_exits_real_mode or strategy_signal_meanreversion_submits_sell or skips_submit_when_risk_blocks_current_cycle" -q` -> PASS (`4 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - seguir con cierre runtime real restante (cancel-replace/fills avanzados/reconciliacion final) para `G9_RUNTIME_ENGINE_REAL=PASS`.

## Actualizacion tecnica AP-BOT-1020 (2026-03-05)
- [x] Reconciliacion avanzada de estados remotos:
  - `PENDING_CANCEL` conserva `PARTIALLY_FILLED` cuando hay fill parcial;
  - `EXPIRED_IN_MATCH` queda cubierto con cierre terminal correcto.
- [x] Tests de regresion agregados:
  - `test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel`;
  - `test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal`.
- [x] Revalidacion bibliografica local-first por patch:
  - `docs/audit/AP_BOT_1020_BIBLIO_VALIDATION_20260305.md`.
- Evidencia:
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -k "keeps_absent_open_order_open_when_order_status_is_new or keeps_partial_state_when_order_status_is_pending_cancel or updates_absent_open_order_partial_fill_from_order_status or marks_absent_open_order_expired_in_match_terminal or marks_absent_open_order_rejected_from_order_status" -q` -> PASS (`5 passed`).
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
- Pendiente inmediato:
  - continuar con cierre de runtime real restante para `G9_RUNTIME_ENGINE_REAL=PASS` (sin habilitar LIVE en esta fase).

## Actualizacion tecnica AP-BOT-1021 (2026-03-05)
- [x] Revalidacion remota de checks protegidos post AP-BOT-1020:
  - workflow `Remote Protected Checks (GitHub VM)` run `22731722376` en `success`.
  - evidencia: `docs/audit/PROTECTED_CHECKS_GHA_22731722376_20260305.md`.
- [x] Campos canonicos confirmados:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- Pendiente inmediato:
  - cierre final de runtime real para mover `G9_RUNTIME_ENGINE_REAL` a `PASS` (sin habilitar LIVE aun).

## Actualizacion tecnica AP-BOT-1022 (2026-03-05)
- [x] Refresh del closeout no-live completado:
  - `docs/audit/NON_LIVE_CLOSEOUT_CHECKLIST_20260304.md` actualizado con evidencia fresh:
    - benchmark `22706414197` PASS;
    - protected checks `22731722376` PASS.
- [x] Estado no-live/testnet consolidado en `GO` con evidencia actualizada.
- [ ] Pendiente unico de tramo final:
  - mover `G9_RUNTIME_ENGINE_REAL` a `PASS` al final del programa, junto con habilitacion live controlada (APIs + canary + rollback).

## Revalidacion bibliografica AP-BOT-1006..1010 (2026-03-04)
- [x] Cerrada validacion bibliografica completa por patch:
  - `docs/audit/AP_BOT_1006_1010_BIBLIO_VALIDATION_20260304.md`.
- [x] En cada AP se declaro `NO EVIDENCIA LOCAL` cuando aplico y se uso solo fuente primaria oficial para cubrir el vacio.
- Pendiente inmediato:
  - mantener este criterio (local-first + fuentes primarias) para AP nuevos.

## Cierre de auditoria integral (2026-03-04)
- Auditoria completa finalizada y documentada en:
  - `docs/audit/AUDIT_REPORT_20260304.md`
  - `docs/audit/AUDIT_FINDINGS_ALL_20260304.md`
  - `docs/audit/AUDIT_BACKLOG_20260304.md`
- Estado:
  - `LIVE`: NO GO (bloqueante tecnico de ejecucion real end-to-end).
  - `No-live/testnet`: GO y estable para continuar hardening antes de conectar APIs LIVE.
- Proximo tramo recomendado (orden):
1. `AP-8001` fail-closed de mock API en BFF.
2. `AP-8002` eliminar `--password` en scripts/workflows remotos.
3. `AP-8007` unificar thresholds de gates (`config` vs `knowledge`) con test de drift.
4. `AP-8011` estabilizar `/api/v1/bots` a `p95 < 300ms` sostenido.
5. `AP-8003` cerrar adapter de ejecucion real con idempotencia/reconciliacion.

## Referencias canonicas de reparacion (2026-03-04)
- Registro maestro de problemas: `docs/audit/FINDINGS_MASTER_20260304.md`
- Plan final de implementacion: `docs/audit/ACTION_PLAN_FINAL_20260304.md`

## Progreso AP (plan final)
- Total AP (plan original): `23`
- AP cerrados (plan original): `23`
- AP adicionales fase 2: `2` (`AP-7001`, `AP-7002`)
- AP cerrados (total extendido): `25`
- AP pendientes (total extendido): `0`
- Avance global extendido: `100%` (`25/25`)

## Estado post-plan AP
- El plan AP original queda ejecutado al `100%`, pero el programa **todavia NO esta listo para LIVE**.
- Hallazgos criticos abiertos para fase siguiente:
  - `FM-EXEC-001`
  - `FM-EXEC-005`
  - `FM-QUANT-008`
  - `FM-RISK-002`
- Hallazgos cerrados en fase 2:
  - `FM-EXEC-002` (G9 reforzado con sync runtime + evidencia exchange + freshness checks).
  - `FM-RISK-003` (learning risk profile por defecto ahora policy-driven).

## Evidencia tecnica fase 2 (2026-03-04)
- Cambios aplicados:
  - `AP-7001`: hardening runtime/gates (`exchange evidence`, `sync runtime`, reconciliacion `openOrders`, fail-closed sintetico).
  - `AP-7002`: risk policy wiring en runtime + default risk profile policy-driven en learning.
- Validacion ejecutada:
  - `python -m py_compile rtlab_autotrader/rtlab_core/web/app.py rtlab_autotrader/rtlab_core/learning/service.py rtlab_autotrader/tests/test_web_live_ready.py` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_web_live_ready.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_rollout_safe_update.py -q` -> PASS.
  - `python -m pytest rtlab_autotrader/tests/test_mass_backtest_engine.py -q` -> PASS.

## Cierre PARTE 7/7 (cerebro del bot)
- Auditoria de cerebro cerrada: decision/learning/rollout validados por codigo.
- Se mantiene politica operativa: **no conectar LIVE todavia**.
- Checklist inmediato de cierre no-live (orden obligatorio):
1. Acoplar runtime operativo real a OMS/risk/reconciliacion y reemplazar payloads sinteticos de `status`/`execution`.
   - avance: AP-0001/AP-0002 + AP-1001/AP-1002/AP-1003/AP-1004 + AP-2001/AP-2002/AP-2003 + AP-7001/AP-7002 implementados (`RuntimeBridge`, telemetry fail-closed, breaker strict, bloqueo de evaluate-phase sin telemetry real, G9 con sync runtime/evidencia exchange y risk policy wiring).
   - pendiente: wiring broker/exchange real end-to-end para ordenes/fills reales (no solo `diagnose` + `openOrders`).
2. Versionar y activar `/.github/workflows/security-ci.yml` en GitHub Actions + branch protection.
   - avance: AP-4001 versionado en branch (`0dbf55d`) + AP-4002 aplicado en GitHub (`main` con required check `security`, `strict=true`) + AP-4003 cerrado (login lockout/rate-limit con backend compartido sqlite).
   - pendiente: corrida verde de `Security CI` tras fix de instalacion de `gitleaks` (run `22674323602` fallo en `Install security tooling`; fix aplicado en workflow, pendiente rerun).
3. Ejecutar hardening final (alertas/recovery/e2e criticos) y volver a correr checks protegidos con evidencia.

## Bloque 3 (quant/learning) - estado actual
- [x] AP-3003: eliminado fallback silencioso de `_learning_eval_candidate` (fail-closed explicito).
- [x] AP-3004: separadas salidas `anti_proxy` y `anti_advanced` en research (con alias legacy).
- [x] AP-3005: `CompareEngine` fail-closed cuando `orderflow_feature_set` queda unknown.
- [x] AP-3006: `strict_strategy_id=true` obligatorio en research/promotion no-demo.
- [x] AP-3001: Purged CV + embargo real en learning/research rapido.
- [x] AP-3002: CPCV real en learning/research.

## Estimacion de bloques restantes (sin LIVE)
- Objetivo declarado: terminar programa en modo no-live/testnet y dejar LIVE para el final.
- Estimacion actual: **faltan 3 bloques tecnicos** para cierre no-live robusto.
1. Bloque A - Runtime de verdad no-live:
   - cerrar reconciliacion/heartbeat sobre broker real (hoy no-live interno).
2. Bloque B - CI/seguridad protegida en root:
   - versionar/activar workflow security root y exigirlo en branch protection.
3. Bloque C - Hardening final de operacion:
   - cerrar gaps de observabilidad/alertas y completar pruebas criticas faltantes (integration/e2e de flujos peligrosos).
- Bloque LIVE real: **postergado por decision operativa** (configuracion de APIs y canary al final).

## Estado de cierre no-live (2026-03-03)
- [x] Benchmark remoto en GitHub VM en PASS (`p95_ms ~18ms`, `server_p95_ms ~0.068ms`, sin retries `429`).
- [x] `Remote Protected Checks (GitHub VM)` en PASS con `strict=true`:
  - `overall_pass=true`
  - `protected_checks_complete=true`
  - `g10_status=PASS`
  - `g9_status=WARN` (esperado en no-live)
  - `breaker_ok=true`
  - `internal_proxy_status_ok=true`
- [x] Revalidacion de seguridad ejecutada en modo estricto (`scripts/security_scan.ps1 -Strict`) sin vulnerabilidades ni leaks.
- [ ] `G9_RUNTIME_ENGINE_REAL` en `PASS` (pendiente runtime real OMS/broker) [POSTERGADO por decision operativa].
- [ ] Habilitacion LIVE real (bloqueada hasta resolver item anterior) [POSTERGADO por decision operativa].
- Criterio actual de tramo: priorizar estabilidad testnet/no-live; LIVE se retoma al final con APIs definitivas configuradas.

## Bloqueantes LIVE (auditoria comite)
1. Completar runtime de ejecucion real contra broker/exchange (paper/testnet/live) con reconciliacion externa y telemetria estricta fail-closed.

## Prioridad 1 (RC operativo)
1. Configurar `INTERNAL_PROXY_TOKEN` en Vercel + Railway y validar que requests directos al backend sin token fallen (hard check de T1 en entorno real).
2. Validar `runtime_engine=real` solo cuando exista loop de ejecucion real y reconciliacion; mantener `simulated` en cualquier otro caso.
3. Confirmar gates LIVE con `G9_RUNTIME_ENGINE_REAL` en PASS antes de habilitar canary.
4. Remediar benchmark remoto de `/api/v1/bots`:
   - ya desplegado cache TTL/invalidacion; evidencia actual sigue en FAIL con 100 bots (`p95=1458.513ms`),
   - mantener `BOTS_MAX_INSTANCES` en rango conservador (recomendado Railway actual: `30`, bajar a `20` si aparece saturacion),
   - probar en Railway `BOTS_OVERVIEW_INCLUDE_RECENT_LOGS=false` y medir impacto real de latencia,
   - usar headers `X-RTLAB-Bots-Overview-*` y `debug_perf=true` para separar hit/miss y medir efecto de cache,
   - instrumentar timing interno por etapas en `get_bots_overview` (kpis/logs/kills/serialization),
   - agregar indice/materializacion para datos de overview de bots (si el costo principal viene de agregacion en request),
   - rerun remoto con `100` bots y objetivo `p95 < 300ms`.
  - [x] storage persistente estabilizado en staging (`RTLAB_USER_DATA_DIR=/app/user_data`).
5. Validar integridad de `breaker_events` (`bot_id/mode`) y monitorear volumen de `unknown`.
6. Afinar thresholds/parametros por estrategia del dispatcher de `BacktestEngine` y agregar `fail-closed` explicito para strategy_ids no soportados en modo estricto.
7. Validar en entorno desplegado que `surrogate_adjustments` se mantenga apagado fuera de `execution_mode=demo` y que promotion quede bloqueada cuando se active.

## Prioridad 2 (operacion + hardening)
1. Agregar rotacion/expiracion para `INTERNAL_PROXY_TOKEN` y checklist de cambio en runbook.
2. [x] Lockout/rate-limit de login backend con backend compartido sqlite (AP-4003 cerrado).
3. Instrumentar alertas de seguridad para intentos de headers internos sin token valido.
4. Definir policy de despliegue que impida `NODE_ENV=production` con defaults de auth.
5. Asegurar que backend no sea accesible en bypass directo (allowlist/zero-trust) aun con token interno.
6. Branch protection para requerir job `security` antes de merge a `main` (AP-4002 completado).
7. Rotar claves de exchange (testnet/live) y validar que no exista hardcode en archivos locales.

## Prioridad 3 (UX / producto)
1. Deploy frontend/backend y validacion visual completa de UI `Research-first`
2. Validar `Settings -> Diagnostico` (WS/Exchange)
3. Validar `Backtests / Runs -> Validate -> Promote -> Rollout / Gates`
4. Resolver infraestructura testnet/live (si reaparece bloqueo de red/egress)
5. Validar Modo Bestia fase 1 en produccion (cola, budget governor, stop-all, resume)
6. Validar en produccion el bloqueo de `bots mode=live` por gates y revisar mensajes de bloqueo en UI
7. Medir `/api/v1/bots` con 100 bots y verificar objetivo p95 `< 300ms` (tracing real en entorno productivo)
8. Verificar integridad de `breaker_events` (bot_id/mode) en logs reales y alertar filas `unknown_bot`/`unknown` por encima de umbral

## Prioridad 4 (UX / producto)
1. Virtualizacion adicional en tablas grandes restantes (D2 comparador ya virtualizado)
2. Deep Compare avanzado (heatmap mensual, rolling Sharpe, distribucion retornos)
3. Componente reutilizable unico para empty states / CTA
4. Tooltips consistentes en acciones de runs (rerun/clone/export cuando existan)

## Prioridad 5 (robustez / automatizacion)
1. [x] AP-5001: suite E2E critica backend (`login -> backtest -> validate -> promote -> rollout`) cerrada.
2. [x] AP-5002: chaos/recovery runtime (`exchange down -> reconnect`, `desync reconcile -> recover`) cerrado.
3. [x] AP-5003: alertas operativas minimas en `/api/v1/alerts` (drift/slippage/api_errors/breaker_integrity) cerrada.
4. Extender `Fee/Funding` a multi-exchange avanzado (hoy Binance + Bybit base + fallback) con manejo de limites/errores por proveedor
5. Integrar proveedor financiero especifico (mapeos/contratos) sobre el adaptador remoto generico de fundamentals
6. Order Flow L1 full (trade tape/BBO real) sobre VPIN proxy actual
7. Materializar agregados para overview de bots (si sube cardinalidad) e indices adicionales por ventana temporal
8. Revisar y refrescar `gitleaks-baseline.json` cuando se remedien hallazgos historicos.

## Prioridad 6 (nice-to-have)
1. UI de experimentos MLflow (capability)
2. SBOM firmado por release
3. Dashboards externos para canary live (Prometheus/Grafana)
4. Modo Bestia fase 2 (Celery + Redis + workers distribuidos + rate limit real por exchange)

## Siguiente bloque tecnico (2026-03-07)
1. Persistir relacion historica exacta `run_id/episode_id -> bot_id` para que `Backtests / Runs` y `Experience` no dependan del pool actual derivado.
2. Validar preview/deploy de `feature/learning-experience-v1` y confirmar en web los fixes de bots/backtests/beast.
3. Verificar en deploy que desaparezca el falso `Modo Bestia deshabilitado` y que los nuevos intents de batch sin dataset respondan `400` sin crear runs `FAILED` historicos.
4. Revisar simplificacion UX adicional en `Strategies` para evitar exceso de botones visibles por fila (mantener acciones masivas arriba y acciones finas en menu contextual).
5. Evaluar export adicional de conocimiento por lote de bots/estrategias (no solo por bot individual) sin tocar LIVE.

- [x] Persistir `run -> bot` exacto para quick/mass/beast y dejar de depender solo del pool actual derivado.
- [ ] Extender la persistencia fuerte a `experience_episode -> bot_id` para analitica historica por bot sin reconstruccion derivada.
- [ ] Validar en deploy visible que la rama con `beast/status` corregido este realmente desplegada y deje de mostrar `Modo Bestia deshabilitado` falso.
- [ ] Completar export consolidado de conocimiento por lote de bots (no solo export JSON por bot individual).
- [ ] Seguir con simplificacion UX: agrupar acciones masivas/edicion de pool para reducir ruido por fila en `Strategies`.

## 2026-04-06

### Beast / Backtests staging
- [x] Confirmar runtime Beast sano en staging (`policy_state=enabled`, `policy_source_root=/app/config/policies`, `data_root=/app/user_data/data`).
- [x] Ejecutar test E2E real de Beast sobre `BTCUSDT` en staging.
- [x] Confirmar corrida real `BX-000001` en `COMPLETED` con `trend_pullback_orderflow_confirm_v1`.
- [x] Confirmar generacion de dataset exacto `BTCUSDT 5m` via resample desde `1m`.
- [ ] Si se quiere ampliar el testeo de Beast, bootstrappear datasets reales adicionales del pool (`ETHUSDT`, `BNBUSDT`, `SOLUSDT`, etc.) antes de abrir otro bloque de runtime.
- [ ] Cuando Linear vuelva a estar disponible, registrar este cierre como issue puntual: `Backtests/Beast: testeo real en staging sobre BTCUSDT`.

### Siguiente bloque recomendado
1. Repetir el workflow de Beast E2E para una segunda estrategia real o para otro simbolo del pool, sin abrir cambios de producto si el runtime sigue sano.
2. Si el objetivo pasa a cobertura de pool, abrir un bloque chico de datos para poblar timeframes/simbolos faltantes en `/app/user_data/data`.
