# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T06:30:28.937691+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230037-EZE`
- Mínimo bots requerido: `25`
- Bots observados: `25`

## Resultado
- `p50_ms`: **511.166**
- `p95_ms`: **32920.976**
- `p99_ms`: **39115.348**
- `avg_ms`: **4053.39**
- `min_ms`: `411.972`
- `max_ms`: `39115.348`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `4`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.081**
- `server_p95_ms`: **141.769**
- `server_p99_ms`: **211.651**
- `server_avg_ms`: **29.1**
- `server_min_ms`: `0.052`
- `server_max_ms`: `211.651`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
