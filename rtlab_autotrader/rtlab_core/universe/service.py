from __future__ import annotations

import copy
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from rtlab_core.policy_paths import resolve_policy_root


UNIVERSES_FILENAME = "universes.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = ("instrument_registry.yaml", "universes.yaml")

DEFAULT_UNIVERSES_POLICY: dict[str, Any] = {
    "globals": {
        "leveraged_token_suffixes": ["UP", "DOWN", "BULL", "BEAR"],
    },
    "universes": {
        "core_spot_usdt": {
            "venue": "binance",
            "family": "spot",
            "quote_assets": ["USDT"],
            "require_status": ["TRADING"],
            "exclude_leveraged_tokens": True,
            "min_live_eligible": True,
        },
        "core_margin_usdt": {
            "venue": "binance",
            "family": "margin",
            "quote_assets": ["USDT"],
            "require_status": ["TRADING"],
            "min_live_eligible": True,
            "require_margin_capability": True,
        },
        "core_usdm_perps": {
            "venue": "binance",
            "family": "usdm_futures",
            "contract_types": ["PERPETUAL"],
            "require_status": ["TRADING"],
            "min_live_eligible": True,
        },
        "core_coinm_perps": {
            "venue": "binance",
            "family": "coinm_futures",
            "contract_types": ["PERPETUAL"],
            "require_status": ["TRADING"],
            "min_live_eligible": True,
        },
    },
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


@lru_cache(maxsize=8)
def _load_universes_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    ).resolve()
    policy_path = (selected_root / UNIVERSES_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    if policy_path.exists():
        try:
            raw_text = policy_path.read_text(encoding="utf-8")
            source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            raw = yaml.safe_load(raw_text) or {}
            if isinstance(raw, dict) and raw:
                payload = raw
                valid = True
        except Exception:
            payload = {}
            valid = False

    merged = _deep_merge(DEFAULT_UNIVERSES_POLICY, payload)
    if not source_hash:
        source_hash = hashlib.sha256(str(merged).encode("utf-8")).hexdigest()
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source_hash": source_hash,
        "source": "config/policies/universes.yaml" if valid else "default_fail_closed",
        "universes_bundle": merged,
    }


def load_universes_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_universes_bundle_cached(str(resolved_repo_root), explicit_root_str))


def universes_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_universes_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("universes_bundle")
    return payload if isinstance(payload, dict) else copy.deepcopy(DEFAULT_UNIVERSES_POLICY)


def _is_leveraged_token(symbol: str, base_asset: str, suffixes: list[str]) -> bool:
    symbol_u = str(symbol or "").strip().upper()
    base_u = str(base_asset or "").strip().upper()
    return any(symbol_u.endswith(f"{suffix}USDT") or base_u.endswith(suffix) for suffix in suffixes)


class InstrumentUniverseService:
    def __init__(self, registry_service: Any) -> None:
        self.registry_service = registry_service

    def policy_bundle(self) -> dict[str, Any]:
        return load_universes_bundle(
            self.registry_service.repo_root,
            explicit_root=self.registry_service.explicit_policy_root,
        )

    def policy(self) -> dict[str, Any]:
        return universes_policy(
            self.registry_service.repo_root,
            explicit_root=self.registry_service.explicit_policy_root,
        )

    def summary(self) -> dict[str, Any]:
        policy_map = self.policy()
        globals_cfg = policy_map.get("globals") if isinstance(policy_map.get("globals"), dict) else {}
        definitions = policy_map.get("universes") if isinstance(policy_map.get("universes"), dict) else {}
        leveraged_suffixes = [
            str(item or "").strip().upper()
            for item in (globals_cfg.get("leveraged_token_suffixes") or [])
            if str(item or "").strip()
        ]
        registry_rows = self.registry_service.db.registry_rows(active_only=True)
        capabilities = self.registry_service.capabilities_summary().get("families") or {}
        live_parity = self.registry_service.live_parity_matrix()

        items: list[dict[str, Any]] = []
        for name, definition in sorted(definitions.items()):
            if not isinstance(definition, dict):
                continue
            venue = str(definition.get("venue") or "binance").strip().lower()
            family = str(definition.get("family") or "").strip().lower()
            quote_assets = {str(row).strip().upper() for row in (definition.get("quote_assets") or []) if str(row).strip()}
            require_status = {str(row).strip().upper() for row in (definition.get("require_status") or []) if str(row).strip()}
            contract_types = {str(row).strip().upper() for row in (definition.get("contract_types") or []) if str(row).strip()}
            require_live_eligible = bool(definition.get("min_live_eligible", False))
            exclude_leveraged = bool(definition.get("exclude_leveraged_tokens", False))
            require_margin_capability = bool(definition.get("require_margin_capability", False))

            selected = [
                row
                for row in registry_rows
                if str(row.get("venue") or "").strip().lower() == venue
                and str(row.get("family") or "").strip().lower() == family
            ]
            if quote_assets:
                selected = [row for row in selected if str(row.get("quote_asset") or "").strip().upper() in quote_assets]
            if require_status:
                selected = [row for row in selected if str(row.get("status") or "").strip().upper() in require_status]
            if contract_types:
                selected = [row for row in selected if str(row.get("contract_type") or "").strip().upper() in contract_types]
            if require_live_eligible:
                selected = [row for row in selected if bool(row.get("live_eligible"))]
            if exclude_leveraged and leveraged_suffixes:
                selected = [
                    row
                    for row in selected
                    if not _is_leveraged_token(
                        str(row.get("symbol") or ""),
                        str(row.get("base_asset") or ""),
                        leveraged_suffixes,
                    )
                ]

            capability_available = True
            if require_margin_capability:
                capability_available = bool(
                    ((capabilities.get(family) or {}).get("live") or {}).get("can_margin")
                )
                if not capability_available:
                    selected = []

            latest_snapshot = self.registry_service.db.latest_snapshot(family, "live", success_only=False)
            freshness = ((live_parity.get(family) or {}).get("live") or {}).get("freshness") or {"status": "missing"}
            items.append(
                {
                    "name": name,
                    "venue": venue,
                    "family": family,
                    "size": len(selected),
                    "filters_applied": {
                        **definition,
                        "leveraged_token_suffixes": leveraged_suffixes if exclude_leveraged else [],
                    },
                    "snapshot_source": {
                        "snapshot_id": (latest_snapshot or {}).get("snapshot_id"),
                        "fetched_at": (latest_snapshot or {}).get("fetched_at"),
                        "environment": "live",
                        "diff_severity": (latest_snapshot or {}).get("diff_severity"),
                    },
                    "fresh": freshness.get("status") == "fresh",
                    "stale": freshness.get("status") != "fresh",
                    "policy_source": {
                        "path": self.policy_bundle().get("path"),
                        "hash": self.policy_bundle().get("source_hash"),
                        "source": self.policy_bundle().get("source"),
                    },
                    "capability_required": require_margin_capability,
                    "capability_available": capability_available,
                    "symbols": [str(row.get("symbol") or "") for row in selected],
                    "sample_symbols": [str(row.get("symbol") or "") for row in selected[:10]],
                }
            )

        return {
            "items": items,
            "policy_source": {
                "path": self.policy_bundle().get("path"),
                "hash": self.policy_bundle().get("source_hash"),
                "source": self.policy_bundle().get("source"),
                "valid": bool(self.policy_bundle().get("valid")),
            },
        }

    def membership(self, *, family: str, symbol: str, venue: str = "binance") -> dict[str, Any]:
        summary = self.summary()
        items = summary.get("items") if isinstance(summary.get("items"), list) else []
        target_symbol = str(symbol or "").strip().upper()
        matched: list[dict[str, Any]] = []
        for row in items:
            if str(row.get("family") or "").strip().lower() != str(family or "").strip().lower():
                continue
            if str(row.get("venue") or "").strip().lower() != str(venue or "binance").strip().lower():
                continue
            symbols = row.get("symbols") if isinstance(row.get("symbols"), list) else []
            if target_symbol in {str(item or "").strip().upper() for item in symbols}:
                matched.append(row)
        return {
            "matched": bool(matched),
            "universes": [str(row.get("name") or "") for row in matched],
            "snapshot_source": next((row.get("snapshot_source") for row in matched), None),
            "policy_source": summary.get("policy_source"),
        }
