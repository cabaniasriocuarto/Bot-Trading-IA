#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

import requests


def _normalize_base_url(url: str) -> str:
    out = str(url or "").strip()
    return out[:-1] if out.endswith("/") else out


@dataclass(slots=True)
class ApiClient:
    base_url: str
    timeout_sec: float
    token: str

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get_json(self, path: str) -> dict[str, Any]:
        res = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout_sec)
        if res.status_code != 200:
            raise RuntimeError(f"GET {path} fallo: {res.status_code} {res.text[:300]}")
        return res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        res = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_sec,
        )
        if res.status_code != 200:
            raise RuntimeError(f"POST {path} fallo: {res.status_code} {res.text[:300]}")
        return res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}


def _login(base_url: str, *, username: str, password: str, timeout_sec: float) -> str:
    res = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=timeout_sec,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Login fallo: {res.status_code} {res.text[:300]}")
    data = res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}
    token = str((data or {}).get("token") or "")
    if not token:
        raise RuntimeError("Login exitoso pero sin token.")
    return token


def _extract_bot_count(payload: dict[str, Any]) -> int:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return len(items)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea bots por API hasta alcanzar una cardinalidad objetivo.")
    parser.add_argument("--base-url", required=True, help="URL base del backend.")
    parser.add_argument("--username", default="Wadmin", help="Usuario admin.")
    parser.add_argument("--password", required=True, help="Password admin.")
    parser.add_argument("--target-bots", type=int, default=30, help="Cantidad objetivo de bots (recomendado Railway: 30).")
    parser.add_argument("--engine", default="bandit_thompson", help="Engine para bots creados.")
    parser.add_argument("--mode", default="paper", choices=["shadow", "paper", "testnet"], help="Modo para bots creados.")
    parser.add_argument("--status", default="active", choices=["active", "paused"], help="Estado para bots creados.")
    parser.add_argument("--timeout-sec", type=float, default=15.0, help="Timeout HTTP por request.")
    parser.add_argument("--dry-run", action="store_true", help="No crea bots, solo informa faltante.")
    args = parser.parse_args()

    base_url = _normalize_base_url(args.base_url)
    target = max(1, int(args.target_bots))
    timeout_sec = max(1.0, float(args.timeout_sec))

    token = _login(base_url, username=args.username, password=args.password, timeout_sec=timeout_sec)
    api = ApiClient(base_url=base_url, timeout_sec=timeout_sec, token=token)

    bots_payload = api.get_json("/api/v1/bots")
    current = _extract_bot_count(bots_payload)
    missing = max(0, target - current)

    strategies_payload = api.get_json("/api/v1/strategies")
    strategy_rows = strategies_payload if isinstance(strategies_payload, list) else []
    pool_ids = [str(row.get("id") or "") for row in strategy_rows if str(row.get("id") or "")]
    pool_ids = [sid for sid in pool_ids if sid][:2]

    print(f"[seed] backend={base_url}")
    print(f"[seed] bots actuales={current} objetivo={target} faltan={missing}")
    if not pool_ids:
        print("[seed] NO EVIDENCIA: no hay estrategias disponibles para pool_strategy_ids.")
        return 2
    print(f"[seed] pool_strategy_ids={pool_ids}")

    if args.dry_run or missing == 0:
        print("[seed] dry-run o nada para crear.")
        return 0

    created = 0
    for idx in range(1, missing + 1):
        payload = {
            "name": f"BenchBot Prod {current + idx}",
            "engine": str(args.engine),
            "mode": str(args.mode),
            "status": str(args.status),
            "pool_strategy_ids": pool_ids,
            "universe": ["BTCUSDT", "ETHUSDT"],
            "notes": "seed benchmark /api/v1/bots",
        }
        try:
            api.post_json("/api/v1/bots", payload)
        except RuntimeError as exc:
            msg = str(exc)
            if "Limite maximo de bots alcanzado" in msg:
                print(f"[seed] stop: {msg}")
                break
            raise
        created += 1
        if created == 1 or created % 10 == 0 or created == missing:
            print(f"[seed] creados {created}/{missing}")

    final_payload = api.get_json("/api/v1/bots")
    final_count = _extract_bot_count(final_payload)
    print(f"[seed] bots finales={final_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
