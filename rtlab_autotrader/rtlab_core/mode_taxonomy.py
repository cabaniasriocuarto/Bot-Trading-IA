from __future__ import annotations

from typing import Any


GLOBAL_RUNTIME_MODES: tuple[str, ...] = ("paper", "testnet", "live")
BOT_POLICY_MODES: tuple[str, ...] = ("shadow", "paper", "testnet", "live")
RESEARCH_EVIDENCE_MODES: tuple[str, ...] = ("backtest", "shadow", "paper", "testnet")

# Alias legacy que hoy aparecen en capas auxiliares, pero no son la taxonomia
# canonica del runtime real.
LEGACY_MODE_ALIASES: dict[str, str] = {
    "mock": "alias_local_frontend",
    "demo": "contexto_legacy_de_research",
}


def normalize_global_runtime_mode(value: str | None, *, default: str = "paper") -> str:
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
        "bot_policy_modes": list(BOT_POLICY_MODES),
        "research_evidence_modes": list(RESEARCH_EVIDENCE_MODES),
        "legacy_aliases": {
            "MOCK": "Solo alias del mock local de frontend; no es modo canonico del runtime real.",
            "demo": "Contexto legacy de research/promocion; no es modo operativo canonico.",
        },
    }
