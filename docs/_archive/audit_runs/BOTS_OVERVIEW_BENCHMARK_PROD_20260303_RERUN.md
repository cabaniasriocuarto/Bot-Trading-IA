# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T16:41:58.181306+00:00`
- Modo: `remote_http`
- Requests medidas: `12`
- Warmup requests: `2`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230059-EZE`
- Mínimo bots requerido: `2`
- Bots observados: `30`

## Resultado
- `p50_ms`: **197.811**
- `p95_ms`: **209.118**
- `p99_ms`: **212.429**
- `avg_ms`: **197.703**
- `min_ms`: `186.489`
- `max_ms`: `212.429`
- `cache_hits`: `12`
- `cache_misses`: `0`
- `cache_hit_ratio`: `1.0`
- `rate_limit_retries`: `0`
- `rate_limit_wait_ms_total`: `0.0`

## Resultado (sin espera de backoff 429)
- `p50_no_backoff_ms`: **197.811**
- `p95_no_backoff_ms`: **209.118**
- `p99_no_backoff_ms`: **212.429**
- `avg_no_backoff_ms`: **197.703**

## Estado
- Estado: **PASS**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.065**
- `server_p95_ms`: **0.075**
- `server_p99_ms`: **0.083**
- `server_avg_ms`: **0.062**
- `server_min_ms`: `0.05`
- `server_max_ms`: `0.083`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
