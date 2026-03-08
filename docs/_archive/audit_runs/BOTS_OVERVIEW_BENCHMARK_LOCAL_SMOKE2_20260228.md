# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T18:43:29.716172+00:00`
- Modo: `local_testclient`
- Requests medidas: `20`
- Warmup requests: `5`
- Objetivo p95: `< 300.0 ms`
- User data dir: `C:\Users\Admin\AppData\Local\Temp\rtlab_bots_bench_6ftwfl1p`
- Bots objetivo seed: `100`
- Logs seeded por bot: `5`
- Breakers seeded por bot: `2`
- Bots observados: `100`

## Resultado
- `p50_ms`: **187.978**
- `p95_ms`: **243.401**
- `p99_ms`: **304.385**
- `avg_ms`: **198.454**
- `min_ms`: `183.109`
- `max_ms`: `304.385`

## Estado
- Estado: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
