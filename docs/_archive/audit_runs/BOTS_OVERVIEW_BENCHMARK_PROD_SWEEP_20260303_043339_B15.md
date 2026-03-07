# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:35:40.165419+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `15`
- Bots observados: `30`

## Resultado
- `p50_ms`: **637.718**
- `p95_ms`: **861.355**
- `p99_ms`: **1120.9**
- `avg_ms`: **670.954**
- `min_ms`: `499.09`
- `max_ms`: `1120.9`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `0`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.073**
- `server_p95_ms`: **115.042**
- `server_p99_ms`: **173.233**
- `server_avg_ms`: **25.604**
- `server_min_ms`: `0.054`
- `server_max_ms`: `173.233`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
