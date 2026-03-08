# AP-BOT-1019 - Revalidacion Bibliografica (higiene de telemetria runtime)

Fecha: 2026-03-05

Objetivo: respaldar la limpieza de `runtime_last_remote_submit_reason` cuando el runtime deja de estar en modo real o cuando el exchange no esta listo.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - limpieza de `runtime_last_remote_submit_reason` en ramas fail-closed de runtime.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:68-70`
  - marco operativo de implementacion en tiempo real con control de riesgo.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:272-274`
  - gestion de riesgo como parte central del sistema automatizado.

## NO EVIDENCIA LOCAL
- No hay definicion textual exacta en biblio local para el campo de telemetria interno `runtime_last_remote_submit_reason`.

## Complemento primario (mismo nivel)
- MITRE CWE-778 (Insufficient Logging):
  - https://cwe.mitre.org/data/definitions/778.html

## Conclusion
- AP-BOT-1019 mejora consistencia de telemetria operativa y evita diagnosticos arrastrados entre estados de runtime.
- El cambio mantiene alineacion con criterios de control operacional/riesgo y logging correcto.
