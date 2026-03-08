# AP-BOT-1017 - Revalidacion Bibliografica (telemetria de `submit_reason`)

Fecha: 2026-03-05

Objetivo: respaldar la incorporacion de trazabilidad explicita del motivo de submit/skip en el runtime (`runtime_last_remote_submit_reason`).

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - persistencia de `runtime_last_remote_submit_reason`;
  - `reason=submitted` en submit exitoso.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - assert de `runtime_last_remote_submit_reason=submitted`;
  - assert de `runtime_last_remote_submit_reason=live_trading_disabled`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:68-70`
  - marco operativo completo para estrategia automatizada con control de riesgo y ejecucion en tiempo real.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:272-274`
  - gestion de riesgo como componente central de la operacion automatizada.

## NO EVIDENCIA LOCAL
- No hay en biblio local una definicion textual exacta del campo de telemetria `runtime_last_remote_submit_reason`.

## Complemento primario (mismo nivel)
- MITRE CWE-778 (Insufficient Logging):
  - https://cwe.mitre.org/data/definitions/778.html

## Conclusion
- AP-BOT-1017 queda respaldado por la necesidad de control operacional/riesgo en trading automatizado y por estandar primario de seguridad/observabilidad.
- El cambio mejora auditoria de decisiones runtime sin alterar logica de ejecucion.
