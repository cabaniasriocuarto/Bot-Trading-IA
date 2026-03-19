from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from rtlab_core.policy_paths import describe_policy_root_resolution


UNIVERSES_FILENAME = "universes.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = ("instrument_registry.yaml", "universes.yaml")

FAIL_CLOSED_MINIMAL_UNIVERSES_POLICY: dict[str, Any] = {
    "globals": {
        "leveraged_token_suffixes": [],
    },
    "universes": {},
}


def _stable_payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _require_dict(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{path}.{key} debe ser dict")
        return {}
    return value


def _require_str(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} debe ser string no vacio")
        return ""
    return value.strip()


def _require_bool(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser bool")
        return False
    return value


def _require_str_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str, required: bool = False) -> list[str]:
    value = parent.get(key)
    if value is None:
        if required:
            errors.append(f"{path}.{key} debe ser lista")
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}.{key} debe ser lista de strings no vacios")
        return []
    return [str(item).strip() for item in value]


def _validate_universes_policy(candidate: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["universes policy debe ser dict"]

    globals_cfg = _require_dict(candidate, "globals", errors=errors, path="universes")
    _require_str_list(globals_cfg, "leveraged_token_suffixes", errors=errors, path="universes.globals")

    universes_cfg = _require_dict(candidate, "universes", errors=errors, path="universes")
    if not universes_cfg:
        errors.append("universes.universes debe contener al menos una definicion")
        return errors

    for name, definition in universes_cfg.items():
        if not isinstance(definition, dict):
            errors.append(f"universes.universes.{name} debe ser dict")
            continue
        _require_str(definition, "venue", errors=errors, path=f"universes.universes.{name}")
        _require_str(definition, "family", errors=errors, path=f"universes.universes.{name}")
        _require_str_list(definition, "quote_assets", errors=errors, path=f"universes.universes.{name}")
        _require_str_list(definition, "require_status", errors=errors, path=f"universes.universes.{name}")
        _require_str_list(definition, "contract_types", errors=errors, path=f"universes.universes.{name}")
        for flag in ("exclude_leveraged_tokens", "min_live_eligible", "require_margin_capability"):
            if flag in definition:
                _require_bool(definition, flag, errors=errors, path=f"universes.universes.{name}")

    return errors


def clear_universes_policy_cache() -> None:
    _load_universes_bundle_cached.cache_clear()


def _universes_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(policy_path.resolve())


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
    resolution = describe_policy_root_resolution(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    )
    selected_root = Path(resolution["selected_root"]).resolve()
    policy_path = (selected_root / UNIVERSES_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    errors: list[str] = []
    warnings = list(resolution.get("warnings") or [])
    if policy_path.exists():
        try:
            raw_bytes = policy_path.read_bytes()
            raw_text = raw_bytes.decode("utf-8")
            source_hash = hashlib.sha256(raw_bytes).hexdigest()
            raw = yaml.safe_load(raw_text) or {}
            validation_errors = _validate_universes_policy(raw) if isinstance(raw, dict) and raw else ["universes.yaml vacio o ausente"]
            if isinstance(raw, dict) and raw and not validation_errors:
                payload = raw
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            payload = {}
            valid = False
            errors.append("universes.yaml no pudo parsearse como YAML valido")
    else:
        errors.append("universes.yaml no existe en la raiz seleccionada")

    active_policy = copy.deepcopy(payload if valid else FAIL_CLOSED_MINIMAL_UNIVERSES_POLICY)
    policy_hash = _stable_payload_hash(active_policy)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "fallback_used": bool(resolution.get("fallback_used")),
        "selected_role": resolution.get("selected_role"),
        "canonical_root": resolution.get("canonical_root"),
        "canonical_role": resolution.get("canonical_role"),
        "divergent_candidates": copy.deepcopy(resolution.get("divergent_candidates") or []),
        "source_hash": source_hash,
        "policy_hash": policy_hash,
        "source": _universes_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "errors": errors,
        "warnings": warnings,
        "universes_bundle": active_policy,
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
    return payload if isinstance(payload, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_UNIVERSES_POLICY)


def _coerce_universes_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(policy) if isinstance(policy, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_UNIVERSES_POLICY)


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

    def policy_source(self) -> dict[str, Any]:
        bundle = self.policy_bundle()
        return {
            "path": bundle.get("path"),
            "source_root": bundle.get("source_root"),
            "source_hash": bundle.get("source_hash"),
            "policy_hash": bundle.get("policy_hash"),
            "valid": bool(bundle.get("valid")),
            "source": bundle.get("source"),
            "errors": list(bundle.get("errors") or []),
            "warnings": list(bundle.get("warnings") or []),
            "fallback_used": bool(bundle.get("fallback_used")),
            "selected_role": bundle.get("selected_role"),
            "canonical_root": bundle.get("canonical_root"),
            "canonical_role": bundle.get("canonical_role"),
            "divergent_candidates": copy.deepcopy(bundle.get("divergent_candidates") or []),
        }

    def summary(self) -> dict[str, Any]:
        policy_map = _coerce_universes_policy(self.policy())
        globals_cfg = policy_map["globals"]
        definitions = policy_map["universes"]
        leveraged_suffixes = [
            str(item or "").strip().upper()
            for item in globals_cfg["leveraged_token_suffixes"]
            if str(item or "").strip()
        ]
        registry_rows = self.registry_service.db.registry_rows(active_only=True)
        capabilities = self.registry_service.capabilities_summary().get("families") or {}
        live_parity = self.registry_service.live_parity_matrix()
        policy_source = self.policy_source()

        items: list[dict[str, Any]] = []
        for name, definition in sorted(definitions.items()):
            if not isinstance(definition, dict):
                continue
            venue = str(definition.get("venue") or "").strip().lower()
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
                    "policy_source": copy.deepcopy(policy_source),
                    "capability_required": require_margin_capability,
                    "capability_available": capability_available,
                    "sample_symbols": [str(row.get("symbol") or "") for row in selected[:10]],
                }
            )

        return {
            "items": items,
            "policy_source": policy_source,
        }
