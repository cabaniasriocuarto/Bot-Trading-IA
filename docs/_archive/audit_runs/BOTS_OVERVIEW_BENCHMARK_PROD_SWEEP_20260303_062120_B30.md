# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T06:32:51.818148+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230024-EZE`
- Mínimo bots requerido: `30`
- Bots observados: `30`

## Resultado
- `p50_ms`: **541.951**
- `p95_ms`: **718.954**
- `p99_ms`: **37926.104**
- `avg_ms`: **2424.46**
- `min_ms`: `431.244`
- `max_ms`: `37926.104`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `2`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.079**
- `server_p95_ms`: **136.141**
- `server_p99_ms`: **137.925**
- `server_avg_ms`: **26.889**
- `server_min_ms`: `0.062`
- `server_max_ms`: `137.925`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
