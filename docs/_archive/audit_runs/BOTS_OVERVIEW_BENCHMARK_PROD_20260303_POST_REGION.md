# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T03:30:06.146995+00:00`
- Modo: `remote_http`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `30`
- Bots observados: `30`

## Resultado
- `p50_ms`: **659.061**
- `p95_ms`: **835.291**
- `p99_ms`: **854.68**
- `avg_ms`: **669.942**
- `min_ms`: `524.3`
- `max_ms`: `854.68`
- `cache_hits`: `16`
- `cache_misses`: `4`
- `cache_hit_ratio`: `0.8`
- `rate_limit_retries`: `0`

## Estado
- Estado: **FAIL**

## Servidor (header `X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: **0.076**
- `server_p95_ms`: **111.258**
- `server_p99_ms`: **147.061**
- `server_avg_ms`: **23.895**
- `server_min_ms`: `0.056`
- `server_max_ms`: `147.061`
- `recent_logs_mode`: `disabled`
- Objetivo server p95<300ms: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
