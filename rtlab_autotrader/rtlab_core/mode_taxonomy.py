from __future__ import annotations

from typing import Any

from rtlab_core.runtime_controls import execution_modes_policy


def _normalized_modes(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return default
    out = tuple(str(item).strip().lower() for item in raw if str(item).strip())
    return out if out else default


def _legacy_aliases(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {
            "mock": {
                "canonical_category": "local_frontend_alias",
                "counts_as_real_runtime": False,
            },
            "demo": {
                "canonical_category": "research_legacy_context",
                "counts_as_real_runtime": False,
            },
        }
    out: dict[str, dict[str, Any]] = {}
    for alias, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        out[str(alias).strip().lower()] = {
            "canonical_category": str(payload.get("canonical_category") or "").strip().lower() or "legacy_alias",
            "counts_as_real_runtime": bool(payload.get("counts_as_real_runtime", False)),
        }
    return out or {
        "mock": {
            "canonical_category": "local_frontend_alias",
            "counts_as_real_runtime": False,
        },
        "demo": {
            "canonical_category": "research_legacy_context",
            "counts_as_real_runtime": False,
        },
    }


def _shadow_runtime_relation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "counts_as_real_runtime": False,
            "allowed_global_runtimes": ["paper", "testnet", "live"],
            "requires_bot_mode": "shadow",
        }
    allowed = _normalized_modes(raw.get("allowed_global_runtimes"), ("paper", "testnet", "live"))
    return {
        "counts_as_real_runtime": bool(raw.get("counts_as_real_runtime", False)),
        "allowed_global_runtimes": list(allowed),
        "requires_bot_mode": str(raw.get("requires_bot_mode") or "shadow").strip().lower() or "shadow",
    }


_EXECUTION_MODES = execution_modes_policy()
GLOBAL_RUNTIME_MODES: tuple[str, ...] = _normalized_modes(
    _EXECUTION_MODES.get("global_runtime_modes"),
    ("paper", "testnet", "live"),
)
BOT_POLICY_MODES: tuple[str, ...] = _normalized_modes(
    _EXECUTION_MODES.get("bot_policy_modes"),
    ("shadow", "paper", "testnet", "live"),
)
RESEARCH_EVIDENCE_MODES: tuple[str, ...] = _normalized_modes(
    _EXECUTION_MODES.get("research_evidence_modes"),
    ("backtest", "shadow", "paper", "testnet"),
)
DEFAULT_GLOBAL_RUNTIME_MODE = str(_EXECUTION_MODES.get("default_global_runtime_mode") or "").strip().lower()
if DEFAULT_GLOBAL_RUNTIME_MODE not in GLOBAL_RUNTIME_MODES:
    DEFAULT_GLOBAL_RUNTIME_MODE = GLOBAL_RUNTIME_MODES[0] if GLOBAL_RUNTIME_MODES else "paper"
SHADOW_RUNTIME_RELATION = _shadow_runtime_relation(_EXECUTION_MODES.get("shadow"))

# Alias legacy que hoy aparecen en capas auxiliares, pero no son la taxonomia
# canonica del runtime real.
LEGACY_MODE_ALIASES = _legacy_aliases(_EXECUTION_MODES.get("legacy_aliases"))


def _legacy_alias_message(alias: str, payload: dict[str, Any]) -> str:
    category = str(payload.get("canonical_category") or "").strip().lower()
    if alias == "mock":
        return "Solo alias del mock local de frontend; no es modo canonico del runtime real."
    if alias == "demo":
        return "Contexto legacy de research/promocion; no es modo operativo canonico."
    if category:
        return f"Alias legacy ({category}); no es modo canonico del runtime real."
    return "Alias legacy; no es modo canonico del runtime real."


def normalize_global_runtime_mode(value: str | None, *, default: str = DEFAULT_GLOBAL_RUNTIME_MODE) -> str:
    mode = str(value or "").strip().lower()
    if mode in GLOBAL_RUNTIME_MODES:
        return mode
    return default


def normalize_bot_policy_mode(value: str | None, *, default: str = "paper") -> str:
    mode = str(value or "").strip().lower()
    if mode in BOT_POLICY_MODES:
        return mode
    return default


def mode_taxonomy_payload() -> dict[str, Any]:
    return {
        "global_runtime_modes": [mode.upper() for mode in GLOBAL_RUNTIME_MODES],
        "default_global_runtime_mode": DEFAULT_GLOBAL_RUNTIME_MODE.upper(),
        "bot_policy_modes": list(BOT_POLICY_MODES),
        "research_evidence_modes": list(RESEARCH_EVIDENCE_MODES),
        "shadow_runtime_relation": {
            "counts_as_real_runtime": bool(SHADOW_RUNTIME_RELATION.get("counts_as_real_runtime", False)),
            "allowed_global_runtimes": [
                str(mode).upper() for mode in (SHADOW_RUNTIME_RELATION.get("allowed_global_runtimes") or [])
            ],
            "requires_bot_mode": str(SHADOW_RUNTIME_RELATION.get("requires_bot_mode") or "shadow"),
        },
        "legacy_aliases": {
            ("MOCK" if alias == "mock" else alias): _legacy_alias_message(alias, payload)
            for alias, payload in LEGACY_MODE_ALIASES.items()
        },
        "legacy_aliases_detail": {
            ("MOCK" if alias == "mock" else alias): payload for alias, payload in LEGACY_MODE_ALIASES.items()
        },
    }
