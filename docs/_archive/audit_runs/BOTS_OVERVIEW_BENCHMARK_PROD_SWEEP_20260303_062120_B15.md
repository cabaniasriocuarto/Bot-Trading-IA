# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T06:24:46.410388+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Railway edge: `railway/us-east4-eqdc4a`
- Railway CDN edge: `fastly/cache-eze2230022-EZE`
- Mínimo bots requerido: `15`
- Bots observados: `15`

## Resultado
- `p50_ms`: **425.607**
- `p95_ms`: **13259.036**
- `p99_ms`: **21107.507**
- `avg_ms`: **2315.143**
- `min_ms`: `338.753`
- `max_ms`: `21107.507`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `5`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.076**
- `server_p95_ms`: **115.587**
- `server_p99_ms`: **117.47**
- `server_avg_ms`: **22.071**
- `server_min_ms`: `0.056`
- `server_max_ms`: `117.47`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
