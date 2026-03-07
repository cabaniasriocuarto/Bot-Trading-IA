# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-03-03T00:21:48.003745+00:00`
- Modo: `local_testclient`
- Requests medidas: `200`
- Warmup requests: `30`
- Objetivo p95: `< 300.0 ms`
- User data dir: `C:\Users\Admin\AppData\Local\Temp\rtlab_bots_bench_votsvlhp`
- Bots objetivo seed: `100`
- Logs seeded por bot: `20`
- Breakers seeded por bot: `4`
- Bots observados: `100`

## Resultado
- `p50_ms`: **36.914**
- `p95_ms`: **55.513**
- `p99_ms`: **81.628**
- `avg_ms`: **41.052**
- `min_ms`: `34.769`
- `max_ms`: `149.32`
- `cache_hits`: `None`
- `cache_misses`: `None`
- `cache_hit_ratio`: `None`

## Estado
- Estado: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
