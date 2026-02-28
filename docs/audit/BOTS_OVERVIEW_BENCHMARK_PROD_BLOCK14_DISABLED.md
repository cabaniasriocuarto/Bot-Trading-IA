# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T21:26:37.006818+00:00`
- Modo: `remote_http`
- Requests medidas: `80`
- Warmup requests: `10`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Bots observados: `1`

## Resultado
- `p50_ms`: **892.57**
- `p95_ms`: **1269.336**
- `p99_ms`: **1528.765**
- `avg_ms`: **966.625**
- `min_ms`: `775.186`
- `max_ms`: `2210.983`
- `cache_hits`: `72`
- `cache_misses`: `8`
- `cache_hit_ratio`: `0.9`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.046**
- `server_p95_ms`: **60.829**
- `server_p99_ms`: **67.424**
- `server_avg_ms`: **6.468**
- `server_min_ms`: `0.039`
- `server_max_ms`: `80.359`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
