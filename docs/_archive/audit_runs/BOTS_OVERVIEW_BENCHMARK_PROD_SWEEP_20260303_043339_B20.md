# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:36:39.749979+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `20`
- Bots observados: `30`

## Resultado
- `p50_ms`: **615.366**
- `p95_ms`: **760.354**
- `p99_ms`: **821.426**
- `avg_ms`: **630.858**
- `min_ms`: `552.443`
- `max_ms`: `821.426`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `0`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.08**
- `server_p95_ms`: **131.792**
- `server_p99_ms`: **191.006**
- `server_avg_ms`: **27.461**
- `server_min_ms`: `0.054`
- `server_max_ms`: `191.006`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
