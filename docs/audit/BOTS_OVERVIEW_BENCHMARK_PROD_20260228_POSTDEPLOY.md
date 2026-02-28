# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T20:00:38.863032+00:00`
- Modo: `remote_http`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `100`
- Bots observados: `1`

## Resultado
- `p50_ms`: **881.59**
- `p95_ms`: **1032.039**
- `p99_ms`: **1236.711**
- `avg_ms`: **896.531**
- `min_ms`: `773.12`
- `max_ms`: `1241.959`

## Estado
- Estado: **NO_EVIDENCIA**

## NO EVIDENCIA
- NO EVIDENCIA: /api/v1/bots devolvio 1 bots, por debajo del minimo requerido 100 para este benchmark.

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
