# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T19:26:43.332428+00:00`
- Modo: `remote_http`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `100`
- Bots observados: `100`

## Resultado
- `p50_ms`: **1272.912**
- `p95_ms`: **1497.775**
- `p99_ms`: **1823.173**
- `avg_ms`: **1306.27**
- `min_ms`: `1064.997`
- `max_ms`: `1854.046`

## Estado
- Estado: **FAIL**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
