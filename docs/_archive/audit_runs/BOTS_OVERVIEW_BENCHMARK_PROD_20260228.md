# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T19:07:19.417507+00:00`
- Modo: `remote_http`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- Base URL: `https://bot-trading-ia-production.up.railway.app`
- Mínimo bots requerido: `100`
- Bots observados: `1`

## Resultado
- `p50_ms`: **977.579**
- `p95_ms`: **1663.014**
- `p99_ms`: **1923.523**
- `avg_ms`: **1146.97**
- `min_ms`: `795.675`
- `max_ms`: `1994.824`

## Estado
- Estado: **NO_EVIDENCIA**

## NO EVIDENCIA
- NO EVIDENCIA: /api/v1/bots devolvio 1 bots, por debajo del minimo requerido 100 para este benchmark.

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
