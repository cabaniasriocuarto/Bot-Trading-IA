# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:37:57.157907+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `25`
- Bots observados: `30`

## Resultado
- `p50_ms`: **628.8**
- `p95_ms`: **810.098**
- `p99_ms`: **19208.562**
- `avg_ms`: **1571.085**
- `min_ms`: `562.064`
- `max_ms`: `19208.562`
- `cache_hits`: `15`
- `cache_misses`: `5`
- `cache_hit_ratio`: `0.75`
- `rate_limit_retries`: `1`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.078**
- `server_p95_ms`: **129.009**
- `server_p99_ms`: **144.0**
- `server_avg_ms`: **30.724**
- `server_min_ms`: `0.056`
- `server_max_ms`: `144.0`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
