# Guardrails de Research (Opcion B)

- El research loop puede proponer cambios, pero no aplicar a LIVE.
- Las recomendaciones solo se adoptan manualmente por admin en `paper` o `testnet`.
- Los candidatos deben salir de `templates + parameter_ranges + filters` permitidos.
- Se rechazan candidatos con PBO alto o DSR bajo cuando los flags `enforce_*` estan activos.
- Mantener trazabilidad: guardar config, dataset hash, costos y razones de rechazo/aprobacion.

