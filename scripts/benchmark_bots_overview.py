#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import requests


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    idx = int(round((p / 100.0) * (len(sorted_values) - 1)))
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def _ensure_repo_import_path(repo_root: Path) -> None:
    package_root = (repo_root / "rtlab_autotrader").resolve()
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def _normalize_base_url(url: str) -> str:
    out = str(url or "").strip()
    if not out:
        return ""
    return out[:-1] if out.endswith("/") else out


def _build_metrics(times_ms: list[float], *, target_p95_ms: float = 300.0) -> dict[str, Any]:
    ordered = sorted(times_ms)
    p50 = _percentile(ordered, 50.0)
    p95 = _percentile(ordered, 95.0)
    p99 = _percentile(ordered, 99.0)
    avg = mean(ordered) if ordered else 0.0
    return {
        "requests": len(times_ms),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "avg_ms": round(avg, 3),
        "min_ms": round(ordered[0], 3) if ordered else 0.0,
        "max_ms": round(ordered[-1], 3) if ordered else 0.0,
        "target_p95_ms": float(target_p95_ms),
        "target_pass": bool(p95 < target_p95_ms),
    }


def _seed_bots(module: Any, target_bots: int, logs_per_bot: int, breakers_per_bot: int) -> list[str]:
    store = module.store
    strategies = store.list_strategies()
    pool_strategy_ids = [str(row.get("id") or "") for row in strategies if str(row.get("id") or "")]
    universe = ["BTCUSDT", "ETHUSDT"]
    if not pool_strategy_ids:
        raise RuntimeError("No hay estrategias disponibles para crear bots de benchmark.")

    rows = store.load_bots()
    while len(rows) < target_bots:
        bot = store.create_bot_instance(
            name=f"BenchBot {len(rows) + 1}",
            engine="bandit_thompson",
            mode="paper",
            status="active",
            pool_strategy_ids=pool_strategy_ids,
            universe=universe,
            notes="benchmark /api/v1/bots",
        )
        rows.append(bot)

    bot_ids = [str(row.get("id") or "") for row in rows[:target_bots] if str(row.get("id") or "")]
    for bot_id in bot_ids:
        for i in range(max(0, logs_per_bot)):
            store.add_log(
                event_type="bot_runtime",
                severity="info",
                module="learning",
                message=f"benchmark_log_{i}",
                related_ids=[bot_id],
                payload={"bot_id": bot_id, "mode": "paper", "kind": "benchmark"},
            )
        for i in range(max(0, breakers_per_bot)):
            store.add_log(
                event_type="breaker_triggered",
                severity="warn",
                module="risk",
                message=f"benchmark_breaker_{i}",
                related_ids=[bot_id],
                payload={"bot_id": bot_id, "mode": "paper", "reason": "benchmark_breaker", "symbol": "BTCUSDT"},
            )
    return bot_ids


def _run_local_benchmark(module: Any, requests_n: int, warmup_n: int) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    app = module.create_app()
    client = TestClient(app)

    username = module.admin_username()
    password = module.admin_password()
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if login.status_code != 200:
        raise RuntimeError(f"Login fallo para benchmark local: {login.status_code} {login.text}")
    token = str((login.json() or {}).get("token") or "")
    if not token:
        raise RuntimeError("Login local exitoso pero sin token.")
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(max(0, warmup_n)):
        res = client.get("/api/v1/bots", headers=headers)
        if res.status_code != 200:
            raise RuntimeError(f"Warmup local fallo: {res.status_code} {res.text}")

    times_ms: list[float] = []
    for _ in range(max(1, requests_n)):
        t0 = perf_counter()
        res = client.get("/api/v1/bots", headers=headers)
        t1 = perf_counter()
        if res.status_code != 200:
            raise RuntimeError(f"Benchmark local fallo: {res.status_code} {res.text}")
        times_ms.append((t1 - t0) * 1000.0)

    metrics = _build_metrics(times_ms)
    metrics["bots_seen"] = len(((res.json() or {}).get("items") or [])) if isinstance(res.json(), dict) else 0
    metrics["mode"] = "local_testclient"
    metrics["no_evidencia_min_bots"] = False
    return metrics


def _remote_login(base_url: str, *, username: str, password: str, timeout_sec: float) -> str:
    login_url = f"{base_url}/api/v1/auth/login"
    res = requests.post(
        login_url,
        json={"username": username, "password": password},
        timeout=timeout_sec,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Login remoto fallo: {res.status_code} {res.text[:200]}")
    data = res.json() if res.headers.get("content-type", "").lower().find("json") >= 0 else {}
    token = str((data or {}).get("token") or "")
    if not token:
        raise RuntimeError("Login remoto exitoso pero sin token.")
    return token


def _remote_get_bots(
    base_url: str,
    *,
    token: str,
    timeout_sec: float,
) -> tuple[int, requests.Response]:
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{base_url}/api/v1/bots", headers=headers, timeout=timeout_sec)
    if res.status_code != 200:
        raise RuntimeError(f"GET /api/v1/bots remoto fallo: {res.status_code} {res.text[:200]}")
    data = res.json() if res.headers.get("content-type", "").lower().find("json") >= 0 else {}
    items = (data or {}).get("items") if isinstance(data, dict) else []
    bot_count = len(items) if isinstance(items, list) else 0
    return bot_count, res


def _run_remote_benchmark(
    *,
    base_url: str,
    auth_token: str,
    username: str,
    password: str,
    requests_n: int,
    warmup_n: int,
    timeout_sec: float,
    min_bots_required: int,
) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        if not password:
            raise RuntimeError("Modo remoto requiere --auth-token o --password para login.")
        token = _remote_login(base_url, username=username, password=password, timeout_sec=timeout_sec)

    min_required = max(0, int(min_bots_required))
    bot_count, _ = _remote_get_bots(base_url, token=token, timeout_sec=timeout_sec)
    no_evidence = bool(min_required > 0 and bot_count < min_required)

    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(max(0, warmup_n)):
        res = requests.get(f"{base_url}/api/v1/bots", headers=headers, timeout=timeout_sec)
        if res.status_code != 200:
            raise RuntimeError(f"Warmup remoto fallo: {res.status_code} {res.text[:200]}")

    times_ms: list[float] = []
    server_ms_values: list[float] = []
    cache_hits = 0
    cache_misses = 0
    last_ok_response: requests.Response | None = None
    for _ in range(max(1, requests_n)):
        t0 = perf_counter()
        res = requests.get(f"{base_url}/api/v1/bots", headers=headers, timeout=timeout_sec)
        t1 = perf_counter()
        if res.status_code != 200:
            raise RuntimeError(f"Benchmark remoto fallo: {res.status_code} {res.text[:200]}")
        last_ok_response = res
        times_ms.append((t1 - t0) * 1000.0)
        server_ms_raw = str(res.headers.get("X-RTLAB-Bots-Overview-MS") or "").strip()
        if server_ms_raw:
            try:
                server_ms_values.append(float(server_ms_raw))
            except Exception:
                pass
        cache_state = str(res.headers.get("X-RTLAB-Bots-Overview-Cache") or "").strip().lower()
        if cache_state == "hit":
            cache_hits += 1
        elif cache_state == "miss":
            cache_misses += 1

    metrics = _build_metrics(times_ms)
    metrics["mode"] = "remote_http"
    metrics["bots_seen"] = bot_count
    metrics["min_bots_required"] = min_required if min_required > 0 else None
    metrics["no_evidencia_min_bots"] = bool(no_evidence)
    if no_evidence:
        metrics["target_pass"] = False
        metrics["no_evidencia_reason"] = (
            f"NO EVIDENCIA: /api/v1/bots devolvio {bot_count} bots, por debajo del minimo requerido "
            f"{min_required} para este benchmark."
        )
    elif last_ok_response is not None:
        data = last_ok_response.json() if last_ok_response.headers.get("content-type", "").lower().find("json") >= 0 else {}
        items = (data or {}).get("items") if isinstance(data, dict) else []
        metrics["bots_seen_last_response"] = len(items) if isinstance(items, list) else 0
        metrics["recent_logs_mode"] = str(last_ok_response.headers.get("X-RTLAB-Bots-Recent-Logs") or "unknown")
    metrics["cache_hits"] = int(cache_hits)
    metrics["cache_misses"] = int(cache_misses)
    metrics["cache_hit_ratio"] = round((cache_hits / max(1, cache_hits + cache_misses)), 4)
    if server_ms_values:
        server_stats = _build_metrics(server_ms_values)
        metrics["server_p50_ms"] = server_stats["p50_ms"]
        metrics["server_p95_ms"] = server_stats["p95_ms"]
        metrics["server_p99_ms"] = server_stats["p99_ms"]
        metrics["server_avg_ms"] = server_stats["avg_ms"]
        metrics["server_min_ms"] = server_stats["min_ms"]
        metrics["server_max_ms"] = server_stats["max_ms"]
        metrics["server_target_pass"] = bool(server_stats["target_pass"])
    return metrics


def _write_report(path: Path, *, context: dict[str, Any], metrics: dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    if metrics.get("no_evidencia_min_bots"):
        status = "NO_EVIDENCIA"
    else:
        status = "PASS" if metrics.get("target_pass") else "FAIL"
    lines = [
        "# Benchmark `/api/v1/bots`",
        "",
        f"- Fecha UTC: `{ts}`",
        f"- Modo: `{metrics.get('mode')}`",
        f"- Requests medidas: `{metrics.get('requests')}`",
        f"- Warmup requests: `{context.get('warmup')}`",
        f"- Objetivo p95: `< {metrics.get('target_p95_ms')} ms`",
    ]
    if context.get("base_url"):
        lines.append(f"- Base URL: `{context.get('base_url')}`")
    if context.get("user_data_dir"):
        lines.append(f"- User data dir: `{context.get('user_data_dir')}`")
    if context.get("bots"):
        lines.append(f"- Bots objetivo seed: `{context.get('bots')}`")
    if context.get("logs_per_bot") is not None:
        lines.append(f"- Logs seeded por bot: `{context.get('logs_per_bot')}`")
    if context.get("breakers_per_bot") is not None:
        lines.append(f"- Breakers seeded por bot: `{context.get('breakers_per_bot')}`")
    if metrics.get("min_bots_required") is not None:
        lines.append(f"- Mínimo bots requerido: `{metrics.get('min_bots_required')}`")
    lines.append(f"- Bots observados: `{metrics.get('bots_seen')}`")
    lines.extend(
        [
            "",
            "## Resultado",
            f"- `p50_ms`: **{metrics.get('p50_ms')}**",
            f"- `p95_ms`: **{metrics.get('p95_ms')}**",
            f"- `p99_ms`: **{metrics.get('p99_ms')}**",
            f"- `avg_ms`: **{metrics.get('avg_ms')}**",
            f"- `min_ms`: `{metrics.get('min_ms')}`",
            f"- `max_ms`: `{metrics.get('max_ms')}`",
            f"- `cache_hits`: `{metrics.get('cache_hits')}`",
            f"- `cache_misses`: `{metrics.get('cache_misses')}`",
            f"- `cache_hit_ratio`: `{metrics.get('cache_hit_ratio')}`",
            "",
            "## Estado",
            f"- Estado: **{status}**",
        ]
    )
    if metrics.get("server_p95_ms") is not None:
        lines.extend(
            [
                "",
                "## Servidor (header `X-RTLAB-Bots-Overview-MS`)",
                f"- `server_p50_ms`: **{metrics.get('server_p50_ms')}**",
                f"- `server_p95_ms`: **{metrics.get('server_p95_ms')}**",
                f"- `server_p99_ms`: **{metrics.get('server_p99_ms')}**",
                f"- `server_avg_ms`: **{metrics.get('server_avg_ms')}**",
                f"- `server_min_ms`: `{metrics.get('server_min_ms')}`",
                f"- `server_max_ms`: `{metrics.get('server_max_ms')}`",
                f"- `recent_logs_mode`: `{metrics.get('recent_logs_mode')}`",
                f"- Objetivo server p95<300ms: **{'PASS' if metrics.get('server_target_pass') else 'FAIL'}**",
            ]
        )
    if metrics.get("no_evidencia_reason"):
        lines.extend(["", "## NO EVIDENCIA", f"- {metrics.get('no_evidencia_reason')}"])
    lines.extend(
        [
            "",
            "## Nota",
            "- Para cierre LIVE, usar `mode=remote_http` sobre entorno desplegado y conservar este archivo como evidencia.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de /api/v1/bots (overview).")
    parser.add_argument("--bots", type=int, default=100, help="Cantidad de bots a seedear en modo local.")
    parser.add_argument("--requests", type=int, default=200, help="Cantidad de requests medidas.")
    parser.add_argument("--warmup", type=int, default=30, help="Cantidad de requests de warmup.")
    parser.add_argument("--logs-per-bot", type=int, default=20, help="Logs seed por bot (modo local).")
    parser.add_argument("--breakers-per-bot", type=int, default=4, help="Breaker events seed por bot (modo local).")
    parser.add_argument("--user-data-dir", type=str, default="", help="Directorio user_data (modo local, opcional).")
    parser.add_argument("--base-url", type=str, default="", help="URL base de backend desplegado para benchmark remoto.")
    parser.add_argument("--auth-token", type=str, default="", help="Bearer token para modo remoto.")
    parser.add_argument("--username", type=str, default="admin", help="Usuario para login remoto cuando no hay token.")
    parser.add_argument("--password", type=str, default="", help="Password para login remoto cuando no hay token.")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="Timeout HTTP en segundos para modo remoto.")
    parser.add_argument(
        "--min-bots-required",
        type=int,
        default=0,
        help="Minimo de bots exigido para evidencia valida en remoto (0 = sin minimo).",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=f"docs/audit/BOTS_OVERVIEW_BENCHMARK_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md",
        help="Ruta del reporte markdown.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    report_path = (repo_root / args.report_path).resolve()
    base_url = _normalize_base_url(args.base_url)
    password = str(args.password or os.getenv("RTLAB_BENCH_PASSWORD", "")).strip()
    auth_token = str(args.auth_token or os.getenv("RTLAB_BENCH_TOKEN", "")).strip()

    if base_url:
        context = {
            "base_url": base_url,
            "warmup": max(0, args.warmup),
            "user_data_dir": "",
            "bots": None,
            "logs_per_bot": None,
            "breakers_per_bot": None,
        }
        metrics = _run_remote_benchmark(
            base_url=base_url,
            auth_token=auth_token,
            username=str(args.username or "admin"),
            password=password,
            requests_n=max(1, args.requests),
            warmup_n=max(0, args.warmup),
            timeout_sec=max(1.0, float(args.timeout_sec)),
            min_bots_required=max(0, int(args.min_bots_required)),
        )
        _write_report(report_path, context=context, metrics=metrics)
        print(f"[benchmark] reporte: {report_path}")
        print(
            f"[benchmark] mode=remote p50={metrics['p50_ms']}ms p95={metrics['p95_ms']}ms p99={metrics['p99_ms']}ms "
            f"(objetivo p95<300ms: {'PASS' if metrics['target_pass'] else 'FAIL'})"
        )
        if metrics.get("no_evidencia_reason"):
            print(f"[benchmark] {metrics['no_evidencia_reason']}")
        return 0

    _ensure_repo_import_path(repo_root)
    temp_dir_cm = None
    if args.user_data_dir.strip():
        user_data_dir = Path(args.user_data_dir).resolve()
        user_data_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir_cm = tempfile.TemporaryDirectory(prefix="rtlab_bots_bench_")
        user_data_dir = Path(temp_dir_cm.name).resolve()

    try:
        os.environ["RTLAB_USER_DATA_DIR"] = str(user_data_dir)
        os.environ.setdefault("NODE_ENV", "development")

        import importlib

        module = importlib.import_module("rtlab_core.web.app")
        _seed_bots(
            module,
            target_bots=max(1, args.bots),
            logs_per_bot=max(0, args.logs_per_bot),
            breakers_per_bot=max(0, args.breakers_per_bot),
        )
        metrics = _run_local_benchmark(module, requests_n=max(1, args.requests), warmup_n=max(0, args.warmup))
        context = {
            "base_url": "",
            "warmup": max(0, args.warmup),
            "user_data_dir": user_data_dir,
            "bots": max(1, args.bots),
            "logs_per_bot": max(0, args.logs_per_bot),
            "breakers_per_bot": max(0, args.breakers_per_bot),
        }
        _write_report(report_path, context=context, metrics=metrics)
        print(f"[benchmark] reporte: {report_path}")
        print(
            f"[benchmark] mode=local p50={metrics['p50_ms']}ms p95={metrics['p95_ms']}ms p99={metrics['p99_ms']}ms "
            f"(objetivo p95<300ms: {'PASS' if metrics['target_pass'] else 'FAIL'})"
        )
        return 0
    finally:
        if temp_dir_cm is not None:
            try:
                temp_dir_cm.cleanup()
            except Exception:
                # En Windows puede quedar un handle sqlite abierto hasta finalizar el proceso.
                pass


if __name__ == "__main__":
    raise SystemExit(main())
