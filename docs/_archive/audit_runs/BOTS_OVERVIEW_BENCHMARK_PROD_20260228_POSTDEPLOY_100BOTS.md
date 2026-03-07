# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T20:05:44.077411+00:00`
- Modo: `remote_http`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `100`
- Bots observados: `100`

## Resultado
- `p50_ms`: **1265.135**
- `p95_ms`: **1458.513**
- `p99_ms`: **1519.641**
- `avg_ms`: **1278.476**
- `min_ms`: `1092.077`
- `max_ms`: `1551.912`

## Estado
- Estado: **FAIL**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
