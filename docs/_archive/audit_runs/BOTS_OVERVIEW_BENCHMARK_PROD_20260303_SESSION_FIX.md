# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:54:24.372117+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230058-EZE`
- Mínimo bots requerido: `30`
- Bots observados: `30`

## Resultado
- `p50_ms`: **695.341**
- `p95_ms`: **28141.676**
- `p99_ms`: **36251.105**
- `avg_ms`: **4250.118**
- `min_ms`: `487.826`
- `max_ms`: `36251.105`
- `cache_hits`: `14`
- `cache_misses`: `6`
- `cache_hit_ratio`: `0.7`
- `rate_limit_retries`: `3`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.075**
- `server_p95_ms`: **140.781**
- `server_p99_ms`: **208.354**
- `server_avg_ms`: **38.258**
- `server_min_ms`: `0.052`
- `server_max_ms`: `208.354`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
