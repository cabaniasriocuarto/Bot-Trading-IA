# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T04:18:36.202128+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `1015202530`
- Bots observados: `30`

## Resultado
- `p50_ms`: **636.194**
- `p95_ms`: **793.969**
- `p99_ms`: **12266.295**
- `avg_ms`: **1211.296**
- `min_ms`: `543.957`
- `max_ms`: `12266.295`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `1`

## Estado
- Estado: **NO_EVIDENCIA**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.074**
- `server_p95_ms`: **110.658**
- `server_p99_ms`: **128.529**
- `server_avg_ms`: **22.169**
- `server_min_ms`: `0.056`
- `server_max_ms`: `128.529`
- `recent_logs_mode`: `None`
- Objetivo server p95<300ms: **PASS**

## NO EVIDENCIA
- NO EVIDENCIA: /api/v1/bots devolvio 30 bots, por debajo del minimo requerido 1015202530 para este benchmark.

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
