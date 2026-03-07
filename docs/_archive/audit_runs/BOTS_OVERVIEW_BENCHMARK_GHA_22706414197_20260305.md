# Remote Benchmark Evidence - Run 22706414197 (2026-03-05)

Fuente: GitHub Actions `Remote Bots Benchmark (GitHub VM)` en `main`.

- Run URL: `https://github.com/cabaniasriocuarto/Bot-Trading-IA/actions/runs/22706414197`
- Conclusión: `success`
- Config: defaults del workflow (`requests=20`, `warmup=5`, `min_bots_required=30`, `pass_criterion=server`)
- Base URL: `https://bot-trading-ia-production.up.railway.app`

## Resultado principal
- `p50_ms`: `106.54`
- `p95_ms`: `184.546`
- `p99_ms`: `351.142`
- `avg_ms`: `123.506`
- `min_ms`: `105.257`
- `max_ms`: `351.142`
- `rate_limit_retries`: `0`
- `rate_limit_wait_ms_total`: `0.0`
- `cache_hit_ratio`: `1.0` (`cache_hits=20`, `cache_misses=0`)

## Server timing (`X-RTLAB-Bots-Overview-MS`)
- `server_p50_ms`: `0.055`
- `server_p95_ms`: `0.07`
- `server_p99_ms`: `0.081`
- `server_avg_ms`: `0.056`

## Estado
- Objetivo `p95 < 300ms`: `PASS`
- Objetivo `server_p95 < 300ms`: `PASS`

## Nota operacional
- El step `Build summary` del workflow mostró errores de shell por backticks en el patrón `grep -E` (no bloqueante del job).
- Se corrige quoting en `/.github/workflows/remote-benchmark.yml` para evitar ruido en corridas siguientes.
