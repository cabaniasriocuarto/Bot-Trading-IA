# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:34:40.697927+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `10`
- Bots observados: `30`

## Resultado
- `p50_ms`: **622.464**
- `p95_ms`: **742.176**
- `p99_ms`: **826.083**
- `avg_ms`: **621.036**
- `min_ms`: `508.977`
- `max_ms`: `826.083`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `0`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.072**
- `server_p95_ms`: **118.218**
- `server_p99_ms`: **130.152**
- `server_avg_ms`: **22.868**
- `server_min_ms`: `0.05`
- `server_max_ms`: `130.152`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
