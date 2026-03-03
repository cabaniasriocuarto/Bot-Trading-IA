#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from time import sleep
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

    def _rate_limit_wait_seconds(self, res: requests.Response) -> float:
        retry_after = str(res.headers.get("Retry-After") or "").strip()
        if retry_after:
            try:
                return max(1.0, float(int(retry_after)))
            except Exception:
                pass
        body = str(res.text or "")
        m = re.search(r"(\d+)\s*s", body)
        if m:
            try:
                return max(1.0, float(int(m.group(1))))
            except Exception:
                pass
        return 5.0

    def get_json(self, path: str, *, retry_429: bool = False, max_retries_429: int = 10) -> dict[str, Any]:
        retries = 0
        while True:
            res = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout_sec)
            if res.status_code == 200:
                return res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}
            if res.status_code == 429 and retry_429 and retries < max(0, int(max_retries_429)):
                wait_sec = self._rate_limit_wait_seconds(res)
                retries += 1
                print(f"[seed] 429 GET {path} -> reintento {retries}/{max_retries_429} en {wait_sec:.1f}s")
                sleep(wait_sec)
                continue
            raise RuntimeError(f"GET {path} fallo: {res.status_code} {res.text[:300]}")

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        retry_429: bool = False,
        max_retries_429: int = 10,
    ) -> dict[str, Any]:
        retries = 0
        while True:
            res = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_sec,
            )
            if res.status_code == 200:
                return res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}
            if res.status_code == 429 and retry_429 and retries < max(0, int(max_retries_429)):
                wait_sec = self._rate_limit_wait_seconds(res)
                retries += 1
                print(f"[seed] 429 POST {path} -> reintento {retries}/{max_retries_429} en {wait_sec:.1f}s")
                sleep(wait_sec)
                continue
            raise RuntimeError(f"POST {path} fallo: {res.status_code} {res.text[:300]}")

    def delete_json(
        self,
        path: str,
        *,
        retry_429: bool = False,
        max_retries_429: int = 10,
    ) -> dict[str, Any]:
        retries = 0
        while True:
            res = requests.delete(
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.timeout_sec,
            )
            if res.status_code == 200:
                return res.json() if "json" in (res.headers.get("content-type") or "").lower() else {}
            if res.status_code == 429 and retry_429 and retries < max(0, int(max_retries_429)):
                wait_sec = self._rate_limit_wait_seconds(res)
                retries += 1
                print(f"[seed] 429 DELETE {path} -> reintento {retries}/{max_retries_429} en {wait_sec:.1f}s")
                sleep(wait_sec)
                continue
            raise RuntimeError(f"DELETE {path} fallo: {res.status_code} {res.text[:300]}")


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


def _extract_bot_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return [row for row in items if isinstance(row, dict)]


def _is_seed_bot(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "").strip().lower()
    notes = str(row.get("notes") or "").strip().lower()
    return name.startswith("benchbot prod") or ("seed benchmark /api/v1/bots" in notes)


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
    parser.add_argument("--retry-429", action="store_true", help="Reintenta automaticamente cuando API responde 429.")
    parser.add_argument("--max-retries-429", type=int, default=20, help="Maximo de reintentos por request ante 429.")
    parser.add_argument("--pace-sec", type=float, default=0.0, help="Pausa fija entre creaciones (segundos).")
    parser.add_argument("--exact", action="store_true", help="Ajusta cardinalidad exacta al target (si hay de mas, elimina).")
    parser.add_argument("--allow-delete", action="store_true", help="Permite borrado cuando --exact necesita bajar cardinalidad.")
    parser.add_argument(
        "--delete-policy",
        default="seed-only",
        choices=["seed-only", "any"],
        help="seed-only: borra solo bots de benchmark; any: permite borrar cualquier bot.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No crea bots, solo informa faltante.")
    args = parser.parse_args()

    base_url = _normalize_base_url(args.base_url)
    target = max(1, int(args.target_bots))
    timeout_sec = max(1.0, float(args.timeout_sec))

    token = _login(base_url, username=args.username, password=args.password, timeout_sec=timeout_sec)
    api = ApiClient(base_url=base_url, timeout_sec=timeout_sec, token=token)

    bots_payload = api.get_json("/api/v1/bots", retry_429=bool(args.retry_429), max_retries_429=int(args.max_retries_429))
    current_items = _extract_bot_items(bots_payload)
    current = len(current_items)
    missing = max(0, target - current)
    excess = max(0, current - target)

    strategies_payload = api.get_json("/api/v1/strategies", retry_429=bool(args.retry_429), max_retries_429=int(args.max_retries_429))
    strategy_rows = strategies_payload if isinstance(strategies_payload, list) else []
    pool_ids = [str(row.get("id") or "") for row in strategy_rows if str(row.get("id") or "")]
    pool_ids = [sid for sid in pool_ids if sid][:2]

    print(f"[seed] backend={base_url}")
    print(f"[seed] bots actuales={current} objetivo={target} faltan={missing} sobran={excess}")
    if not pool_ids:
        print("[seed] NO EVIDENCIA: no hay estrategias disponibles para pool_strategy_ids.")
        return 2
    print(f"[seed] pool_strategy_ids={pool_ids}")

    if bool(args.exact) and excess > 0:
        if args.dry_run:
            print(f"[seed] dry-run exact: habria que borrar {excess} bots.")
        else:
            if not bool(args.allow_delete):
                raise RuntimeError("Modo --exact requiere --allow-delete para bajar cardinalidad.")
            candidates = list(current_items)
            if str(args.delete_policy) == "seed-only":
                candidates = [row for row in candidates if _is_seed_bot(row)]
            candidates.sort(key=lambda row: str(row.get("created_at") or row.get("updated_at") or ""), reverse=True)
            if len(candidates) < excess:
                raise RuntimeError(
                    f"No hay suficientes bots borrables para --exact (sobran={excess}, elegibles={len(candidates)}, policy={args.delete_policy})."
                )
            deleted = 0
            for row in candidates[:excess]:
                bot_id = str(row.get("id") or "").strip()
                if not bot_id:
                    continue
                api.delete_json(
                    f"/api/v1/bots/{bot_id}",
                    retry_429=bool(args.retry_429),
                    max_retries_429=int(args.max_retries_429),
                )
                deleted += 1
                if deleted == 1 or deleted % 10 == 0 or deleted == excess:
                    print(f"[seed] borrados {deleted}/{excess}")
                if float(args.pace_sec) > 0:
                    sleep(max(0.0, float(args.pace_sec)))
            bots_payload = api.get_json("/api/v1/bots", retry_429=bool(args.retry_429), max_retries_429=int(args.max_retries_429))
            current_items = _extract_bot_items(bots_payload)
            current = len(current_items)
            missing = max(0, target - current)
            excess = max(0, current - target)
            print(f"[seed] post-delete bots={current} faltan={missing} sobran={excess}")

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
            api.post_json(
                "/api/v1/bots",
                payload,
                retry_429=bool(args.retry_429),
                max_retries_429=int(args.max_retries_429),
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "Limite maximo de bots alcanzado" in msg:
                print(f"[seed] stop: {msg}")
                break
            raise
        created += 1
        if float(args.pace_sec) > 0:
            sleep(max(0.0, float(args.pace_sec)))
        if created == 1 or created % 10 == 0 or created == missing:
            print(f"[seed] creados {created}/{missing}")

    final_payload = api.get_json("/api/v1/bots", retry_429=bool(args.retry_429), max_retries_429=int(args.max_retries_429))
    final_count = _extract_bot_count(final_payload)
    print(f"[seed] bots finales={final_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
