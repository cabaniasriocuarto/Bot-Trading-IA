# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T16:48:01.054107+00:00`
- User data dir: `C:\Users\Admin\AppData\Local\Temp\rtlab_bots_bench_zdze0h83`
- Bots: `100`
- Warmup requests: `30`
- Requests medidas: `200`
- Logs seeded por bot: `20`
- Breakers seeded por bot: `4`

## Resultado
- `p50_ms`: **221.267**
- `p95_ms`: **280.875**
- `p99_ms`: **372.16**
- `avg_ms`: **231.393**
- `min_ms`: `213.612`
- `max_ms`: `434.786`

## Umbral objetivo
- Objetivo: `p95 < 300.0 ms`
- Estado: **PASS**

## Nota
- Este benchmark usa `FastAPI TestClient` en entorno local; para validación productiva repetir sobre despliegue real.
