# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T21:30:09.079715+00:00`
- Modo: `remote_http`
- Requests medidas: `80`
- Warmup requests: `10`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Bots observados: `30`

## Resultado
- `p50_ms`: **1302.69**
- `p95_ms`: **3001.484**
- `p99_ms`: **3449.006**
- `avg_ms`: **1543.801**
- `min_ms`: `978.433`
- `max_ms`: `4377.523`
- `cache_hits`: `69`
- `cache_misses`: `11`
- `cache_hit_ratio`: `0.8625`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.049**
- `server_p95_ms`: **63.034**
- `server_p99_ms`: **66.847**
- `server_avg_ms`: **8.678**
- `server_min_ms`: `0.04`
- `server_max_ms`: `75.474`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
