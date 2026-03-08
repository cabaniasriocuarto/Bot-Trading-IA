# Logging Policy (CWE-532)

Objetivo: evitar exposicion de secretos o datos sensibles en logs, errores y trazas.

Referencias:
- MITRE CWE-532: Information Exposure Through Log Files.
- Linux `/proc/<pid>/cmdline`: argumentos CLI visibles.
- Microsoft process command-line auditing (Event 4688).

## Prohibido loguear
- API keys, tokens, passwords, secretos de sesion.
- Headers sensibles (`Authorization`, cookies, proxy tokens).
- Query strings con credenciales.
- Payloads completos que incluyan PII/secrets.

## Reglas operativas
- Usar logs estructurados con campos explicitos.
- Redactar secretos (`***`) antes de loguear.
- En errores HTTP, loguear codigo + categoria, no credenciales ni body completo.
- No pasar secretos por argumentos CLI; usar env vars o stdin efimero.
- En CI/CD, bloquear patrones inseguros (`--password`) en scripts y workflows.

## Do / Don't rapido
- `DO`: `{"event":"auth_failed","user":"admin","reason":"invalid_credentials"}`
- `DON'T`: `{"event":"auth_failed","password":"..."}`
- `DO`: `token_prefix=abcd...`
- `DON'T`: `token_full=abcd1234...`

## Checklist minimo por release
- [ ] No hay `--password` en automation operativa.
- [ ] Sanitizacion de logs validada en rutas criticas.
- [ ] Secrets solo por variables de entorno/secret manager.
- [ ] Reporte de seguridad actualizado en `docs/truth/*`.
