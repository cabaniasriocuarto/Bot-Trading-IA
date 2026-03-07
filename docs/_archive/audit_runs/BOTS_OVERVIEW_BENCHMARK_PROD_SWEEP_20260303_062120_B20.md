# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T06:27:25.485767+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230064-EZE`
- Mínimo bots requerido: `20`
- Bots observados: `20`

## Resultado
- `p50_ms`: **443.659**
- `p95_ms`: **43239.684**
- `p99_ms`: **47822.732**
- `avg_ms`: **4945.968**
- `min_ms`: `343.867`
- `max_ms`: `47822.732`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `2`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.069**
- `server_p95_ms`: **126.939**
- `server_p99_ms`: **128.427**
- `server_avg_ms`: **23.729**
- `server_min_ms`: `0.052`
- `server_max_ms`: `128.427`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
