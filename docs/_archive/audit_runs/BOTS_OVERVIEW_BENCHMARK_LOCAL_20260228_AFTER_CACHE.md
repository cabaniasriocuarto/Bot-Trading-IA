# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T19:32:17.984714+00:00`
- Modo: `local_testclient`
- Requests medidas: `120`
- Warmup requests: `20`
- Objetivo p95: `< 300.0 ms`
- User data dir: `C:\Users\Admin\AppData\Local\Temp\rtlab_bots_bench_no7jnd_h`
- Bots objetivo seed: `100`
- Logs seeded por bot: `20`
- Breakers seeded por bot: `4`
- Bots observados: `100`

## Resultado
- `p50_ms`: **31.453**
- `p95_ms`: **35.524**
- `p99_ms`: **37.875**
- `avg_ms`: **32.408**
- `min_ms`: `30.123`
- `max_ms`: `86.173`

## Estado
- Estado: **PASS**

## Nota
- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.
