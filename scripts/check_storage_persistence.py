#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def _normalize_base_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return value
    return value[:-1] if value.endswith("/") else value


def _fetch_json(
    *,
    base_url: str,
    path: str,
    token: str,
    timeout_sec: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{base_url}{path}", headers=headers, timeout=timeout_sec)
    if res.status_code != 200:
        raise RuntimeError(f"GET {path} fallo: {res.status_code} {res.text[:200]}")
    if "json" not in str(res.headers.get("content-type", "")).lower():
        raise RuntimeError(f"GET {path} no devolvio JSON")
    data = res.json()
    return data if isinstance(data, dict) else {}


def _resolve_token(
    *,
    base_url: str,
    auth_token: str,
    username: str,
    password: str,
    timeout_sec: float,
) -> str:
    token = str(auth_token or "").strip()
    if token:
        return token
    user = str(username or "").strip()
    pwd = str(password or "").strip()
    if not user or not pwd:
        raise RuntimeError("Falta token o credenciales para login.")
    login = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": user, "password": pwd},
        timeout=timeout_sec,
    )
    if login.status_code != 200:
        raise RuntimeError(f"Login fallo: {login.status_code} {login.text[:200]}")
    payload = login.json() if "json" in str(login.headers.get("content-type", "")).lower() else {}
    token = str((payload or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError("Login exitoso pero sin token.")
    return token


def _find_gate(payload: dict[str, Any], gate_id: str) -> dict[str, Any]:
    gates = payload.get("gates") if isinstance(payload.get("gates"), list) else []
    for row in gates:
        if isinstance(row, dict) and str(row.get("id") or "") == gate_id:
            return row
    return {}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida persistencia de storage y gate G10 en una instancia RTLAB."
    )
    parser.add_argument("--base-url", required=True, help="URL base backend, ej: https://...up.railway.app")
    parser.add_argument(
        "--auth-token",
        default=os.getenv("RTLAB_AUTH_TOKEN", ""),
        help="Bearer token opcional (si no se pasa, usa login).",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("RTLAB_USERNAME", "Wadmin"),
        help="Usuario para login si no hay token (default: Wadmin).",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("RTLAB_PASSWORD", ""),
        help="Password para login si no hay token.",
    )
    parser.add_argument("--timeout-sec", type=float, default=15.0, help="Timeout HTTP por request.")
    parser.add_argument(
        "--require-persistent",
        action="store_true",
        help="Falla (exit 2) si storage no es persistente o G10 no esta en PASS.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    base_url = _normalize_base_url(args.base_url)
    if not base_url:
        raise RuntimeError("base-url vacia.")

    token = _resolve_token(
        base_url=base_url,
        auth_token=args.auth_token,
        username=args.username,
        password=args.password,
        timeout_sec=float(args.timeout_sec),
    )
    health = _fetch_json(base_url=base_url, path="/api/v1/health", token=token, timeout_sec=float(args.timeout_sec))
    gates = _fetch_json(base_url=base_url, path="/api/v1/gates", token=token, timeout_sec=float(args.timeout_sec))

    storage = health.get("storage") if isinstance(health.get("storage"), dict) else {}
    g10 = _find_gate(gates, "G10_STORAGE_PERSISTENCE")
    result = {
        "base_url": base_url,
        "health_ok": bool(health.get("ok", False)),
        "runtime_mode": str(health.get("runtime_mode") or ""),
        "storage": {
            "user_data_dir": storage.get("user_data_dir"),
            "storage_ephemeral": storage.get("storage_ephemeral"),
            "persistent_storage": storage.get("persistent_storage"),
            "warning": storage.get("warning"),
        },
        "g10_storage_persistence": {
            "status": g10.get("status"),
            "reason": g10.get("reason"),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.require_persistent:
        storage_ok = bool(storage.get("persistent_storage"))
        g10_ok = str(g10.get("status") or "").upper() == "PASS"
        if not storage_ok or not g10_ok:
            print(
                "ERROR: storage no persistente o gate G10 en no-PASS; revisar volumen y RTLAB_USER_DATA_DIR.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
