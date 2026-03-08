# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T03:50:52.877226+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `30`
- Bots observados: `1`

## Resultado
- `p50_ms`: **545.622**
- `p95_ms`: **3812.201**
- `p99_ms`: **4261.51**
- `avg_ms`: **1187.74**
- `min_ms`: `385.654`
- `max_ms`: `4261.51`
- `cache_hits`: `15`
- `cache_misses`: `5`
- `cache_hit_ratio`: `0.75`
- `rate_limit_retries`: `0`

## Estado
- Estado: **NO_EVIDENCIA**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.082**
- `server_p95_ms`: **123.288**
- `server_p99_ms`: **138.02**
- `server_avg_ms`: **30.167**
- `server_min_ms`: `0.053`
- `server_max_ms`: `138.02`
- `recent_logs_mode`: `None`
- Objetivo server p95<300ms: **PASS**

## NO EVIDENCIA
- NO EVIDENCIA: /api/v1/bots devolvio 1 bots, por debajo del minimo requerido 30 para este benchmark.

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
