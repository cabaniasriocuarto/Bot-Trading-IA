# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T07:56:43.733918+00:00`
- Modo: `remote_http`
- Requests medidas: `8`
- Warmup requests: `2`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230039-EZE`
- Mínimo bots requerido: `30`
- Bots observados: `1`

## Resultado
- `p50_ms`: **266.497**
- `p95_ms`: **585.648**
- `p99_ms`: **585.648**
- `avg_ms`: **317.72**
- `min_ms`: `252.912`
- `max_ms`: `585.648`
- `cache_hits`: `7`
- `cache_misses`: `1`
- `cache_hit_ratio`: `0.875`
- `rate_limit_retries`: `0`
- `rate_limit_wait_ms_total`: `0.0`

## Resultado (sin espera de backoff 429)
- `p50_no_backoff_ms`: **266.497**
- `p95_no_backoff_ms`: **585.648**
- `p99_no_backoff_ms`: **585.648**
- `avg_no_backoff_ms`: **317.72**

## Estado
- Estado: **NO_EVIDENCIA**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.084**
- `server_p95_ms`: **193.853**
- `server_p99_ms`: **193.853**
- `server_avg_ms`: **24.301**
- `server_min_ms`: `0.071`
- `server_max_ms`: `193.853`
- `recent_logs_mode`: `None`
- Objetivo server p95<300ms: **PASS**

## NO EVIDENCIA
- NO EVIDENCIA: /api/v1/bots devolvio 1 bots, por debajo del minimo requerido 30 para este benchmark.

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
