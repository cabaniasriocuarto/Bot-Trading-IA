# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T17:24:51.968338+00:00`
- Modo: `remote_http`
- Requests medidas: `12`
- Warmup requests: `2`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230031-EZE`
- Mínimo bots requerido: `30`
- Bots observados: `30`

## Resultado
- `p50_ms`: **324.55**
- `p95_ms`: **467.372**
- `p99_ms`: **507.052**
- `avg_ms`: **349.683**
- `min_ms`: `200.405`
- `max_ms`: `507.052`
- `cache_hits`: `10`
- `cache_misses`: `2`
- `cache_hit_ratio`: `0.8333`
- `rate_limit_retries`: `0`
- `rate_limit_wait_ms_total`: `0.0`
- `pass_criterion`: `server`
- `client_target_pass`: `False`
- `server_target_pass`: `True`

## Resultado (sin espera de backoff 429)
- `p50_no_backoff_ms`: **324.55**
- `p95_no_backoff_ms`: **467.372**
- `p99_no_backoff_ms`: **507.052**
- `avg_no_backoff_ms`: **349.683**

## Estado
- Estado: **PASS**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.058**
- `server_p95_ms`: **48.277**
- `server_p99_ms`: **60.43**
- `server_avg_ms`: **9.105**
- `server_min_ms`: `0.049`
- `server_max_ms`: `60.43`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
