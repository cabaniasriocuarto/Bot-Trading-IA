# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T21:22:46.111024+00:00`
- Modo: `remote_http`
- Requests medidas: `80`
- Warmup requests: `10`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Bots observados: `1`

## Resultado
- `p50_ms`: **869.773**
- `p95_ms`: **1122.483**
- `p99_ms`: **3862.786**
- `avg_ms`: **969.297**
- `min_ms`: `763.014`
- `max_ms`: `4100.149`
- `cache_hits`: `73`
- `cache_misses`: `7`
- `cache_hit_ratio`: `0.9125`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.045**
- `server_p95_ms`: **56.797**
- `server_p99_ms`: **59.305**
- `server_avg_ms`: **5.243**
- `server_min_ms`: `0.036`
- `server_max_ms`: `70.686`
- `recent_logs_mode`: `enabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
