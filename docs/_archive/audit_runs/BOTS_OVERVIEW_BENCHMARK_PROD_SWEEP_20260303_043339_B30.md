# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:38:55.820867+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `30`
- Bots observados: `30`

## Resultado
- `p50_ms`: **665.301**
- `p95_ms`: **801.437**
- `p99_ms`: **807.025**
- `avg_ms`: **651.239**
- `min_ms`: `505.925`
- `max_ms`: `807.025`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `0`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.09**
- `server_p95_ms`: **113.84**
- `server_p99_ms`: **117.634**
- `server_avg_ms`: **22.127**
- `server_min_ms`: `0.048`
- `server_max_ms`: `117.634`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
