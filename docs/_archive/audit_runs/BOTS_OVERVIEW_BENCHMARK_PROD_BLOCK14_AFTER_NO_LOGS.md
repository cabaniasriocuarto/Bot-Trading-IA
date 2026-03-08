# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T21:18:32.979650+00:00`
- Modo: `remote_http`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Bots observados: `1`

## Resultado
- `p50_ms`: **880.274**
- `p95_ms`: **1065.058**
- `p99_ms`: **1298.958**
- `avg_ms`: **919.013**
- `min_ms`: `761.734`
- `max_ms`: `3877.223`

## Estado
- Estado: **FAIL**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
