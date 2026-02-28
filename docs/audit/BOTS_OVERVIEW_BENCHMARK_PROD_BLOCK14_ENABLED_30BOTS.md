# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T21:34:32.208230+00:00`
- Modo: `remote_http`
- Requests medidas: `80`
- Warmup requests: `10`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Bots observados: `30`

## Resultado
- `p50_ms`: **1154.18**
- `p95_ms`: **1600.645**
- `p99_ms`: **1944.019**
- `avg_ms`: **1228.291**
- `min_ms`: `977.239`
- `max_ms`: `2673.074`
- `cache_hits`: `71`
- `cache_misses`: `9`
- `cache_hit_ratio`: `0.8875`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.052**
- `server_p95_ms`: **74.93**
- `server_p99_ms`: **111.58**
- `server_avg_ms`: **10.153**
- `server_min_ms`: `0.035`
- `server_max_ms`: `143.871`
- `recent_logs_mode`: `enabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
