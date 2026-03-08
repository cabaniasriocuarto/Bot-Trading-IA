# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T06:23:06.350601+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230040-EZE`
- Mínimo bots requerido: `10`
- Bots observados: `10`

## Resultado
- `p50_ms`: **422.334**
- `p95_ms`: **16248.815**
- `p99_ms`: **17861.254**
- `avg_ms`: **2102.552**
- `min_ms`: `333.872`
- `max_ms`: `17861.254`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `3`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.084**
- `server_p95_ms`: **119.476**
- `server_p99_ms`: **120.19**
- `server_avg_ms`: **22.735**
- `server_min_ms`: `0.052`
- `server_max_ms`: `120.19`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
