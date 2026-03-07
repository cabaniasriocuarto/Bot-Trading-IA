# AP-BOT-1016 - Revalidacion Bibliografica (guard no-live en submit `live`)

Fecha: 2026-03-05

Objetivo: respaldar el guard fail-closed que bloquea envio de ordenes nuevas cuando el runtime esta en `mode=live` y `LIVE_TRADING_ENABLED=false`.

## Fuentes usadas

### Bibliografia local (indice con hash)
- `docs/reference/BIBLIO_INDEX.md:37` -> `9 - Quantitative Trading_ How to Build Your Own Algorithmic Trading Business-Wiley (2008).pdf`.

### Evidencia tecnica del repo
- `rtlab_autotrader/rtlab_core/web/app.py`:
  - variable `LIVE_TRADING_ENABLED` (default `false`);
  - guard en `RuntimeBridge._maybe_submit_exchange_runtime_order(...)` con `reason=live_trading_disabled`.
- `rtlab_autotrader/tests/test_web_live_ready.py`:
  - `test_runtime_sync_live_skips_submit_when_live_trading_disabled`.

## Soporte bibliografico local
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:33`
  - gestion de dinero y riesgo como requisito operacional en estrategia automatizada.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:68-70`
  - marco de desarrollo + risk management + implementacion en tiempo real.
- `docs/reference/biblio_txt/9_-_Quantitative_Trading__How_to_Build_Your_Own_Algorithmic_Trading_Business-Wiley_2008.txt:272-274`
  - foco explicito en money/risk management para operacion automatizada.

## NO EVIDENCIA LOCAL
- No hay en biblio local una especificacion textual exacta para el control de bandera operacional `LIVE_TRADING_ENABLED`.

## Complemento primario (mismo nivel)
- OWASP ASVS (control de politicas de seguridad y fail-safe defaults):
  - https://owasp.org/www-project-application-security-verification-standard/
- MITRE CWE-693 (Protection Mechanism Failure):
  - https://cwe.mitre.org/data/definitions/693.html

## Conclusion
- AP-BOT-1016 queda alineado con el principio local de risk management operativo y reforzado por estandares primarios de fail-closed.
- El cambio reduce riesgo de activacion accidental de ordenes reales mientras el proyecto permanece en tramo no-live.
