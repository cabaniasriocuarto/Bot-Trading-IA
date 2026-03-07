# Benchmark `/api/v1/bots`

- Fecha UTC: `2026-02-28T16:48:55.237302+00:00`
- User data dir: `C:\Users\Admin\AppData\Local\Temp\rtlab_bots_bench_zmveuqp6`
- Bots: `100`
- Warmup requests: `10`
- Requests medidas: `30`
- Logs seeded por bot: `5`
- Breakers seeded por bot: `2`

## Resultado
- `p50_ms`: **186.181**
- `p95_ms`: **202.754**
- `p99_ms`: **237.992**
- `avg_ms`: **188.097**
- `min_ms`: `179.505`
- `max_ms`: `237.992`

## Umbral objetivo
- Objetivo: `p95 < 300.0 ms`
- Estado: **PASS**

## Nota
- Este benchmark usa `FastAPI TestClient` en entorno local; para validación productiva repetir sobre despliegue real.
