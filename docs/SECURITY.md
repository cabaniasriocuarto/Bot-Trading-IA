# Seguridad Operativa (RTLAB Bot-Trading-IA)

## Resumen
- **Secretos**: solo por variables de entorno / secrets manager (Railway, Vercel, VPS).
- **Opción B**: el sistema recomienda; **no** auto-promueve a LIVE.
- **Credenciales de exchange**: mínimo privilegio (**Read + Trade**) y **nunca** permisos de retiro (**Withdraw**).

## 1) Secrets (obligatorio)
### Dónde configurar
- **Railway (backend)**: Variables del servicio backend (`rtlab_autotrader`)
- **Vercel (frontend)**: solo secretos del frontend/proxy si aplica (no poner API keys del exchange en el cliente)
- **VPS/local**: `.env` local no versionado + systemd/env vars

### Reglas
- Nunca hardcodear API keys, passwords o tokens.
- Nunca commitear `.env` reales.
- Usar `.env.example` como plantilla.
- Rotar credenciales si:
  - se sospecha exposición,
  - hubo acceso compartido del repo/máquina,
  - o se cambian operadores/admins.

## 2) Exchange: mínimo privilegio
- **Permitir**: `Read` + `Trade`
- **Prohibido**: `Withdraw`
- Recomendado:
  - whitelist de IP (si el exchange lo soporta)
  - separar keys de `testnet` y `live`
  - una key por entorno / servicio (no reutilizar)

## 3) Logs y redacción
- Los endpoints de diagnóstico y gates deben mostrar **estado** y **errores**, pero no secretos.
- Revisar que en logs no se impriman:
  - API keys completas
  - secrets
  - tokens de Telegram
  - headers de auth
- Si necesitás debug, loguear solo:
  - últimos 4 caracteres (`****ABCD`)
  - key source (`env/json`)
  - nombre de variable faltante

## 4) Auditoría de dependencias (seguridad)
Script agregado:
- `scripts/security_audit.sh`

Qué hace:
- corre `pip-audit` sobre `requirements-runtime.txt`
- corre `pip-audit` sobre `requirements-research.txt`
- intenta generar SBOM CycloneDX (si `cyclonedx-py` o `cyclonedx-bom` está instalado)

Uso:
```bash
bash scripts/security_audit.sh
```

Salida esperada:
- reportes en `artifacts/security_audit/`

## 5) CI/CD (recomendado para “final”)
Estado actual:
- Hay scripts locales para auditoría y chequeo de dependencias.
- **Recomendación**: integrarlos en CI (GitHub Actions / pipeline) antes de LIVE real.

Pipeline mínimo sugerido:
1. `python -m py_compile`
2. `pytest` (suites críticas)
3. `npx tsc --noEmit`
4. `bash scripts/deps_check.sh`
5. `bash scripts/security_audit.sh`

## 6) Checklist rápido pre-LIVE
- [ ] `AUTH_SECRET` configurado y fuerte
- [ ] `ADMIN_PASSWORD` y `VIEWER_PASSWORD` cambiados
- [ ] Exchange keys con `Read+Trade` y sin `Withdraw`
- [ ] IP whitelist configurada (si aplica)
- [ ] `scripts/deps_check.sh` OK
- [ ] `scripts/security_audit.sh` revisado
- [ ] Gates + canary + rollback + approve validados
