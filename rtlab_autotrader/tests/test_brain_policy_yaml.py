from __future__ import annotations

import yaml
from pathlib import Path

from rtlab_core.policy_paths import resolve_policy_root


def _load_policy(name: str) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    root = resolve_policy_root(repo_root)
    return yaml.safe_load((root / name).read_text(encoding="utf-8")) or {}


def test_gates_yaml_exposes_brain_policy_and_live_source_weight() -> None:
    payload = _load_policy("gates.yaml")
    gates = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}

    assert (gates.get("source_weights") or {}).get("live") == 1.0
    assert (gates.get("source_weights") or {}).get("legacy_untrusted") == 0.0
    assert (gates.get("brain_policy") or {}).get("exact_bot_threshold_trades") == 50
    assert (gates.get("promotion") or {}).get("candidate", {}).get("min_psr") == 0.95
    assert (gates.get("quarantine") or {}).get("require_complete_provenance") is True


def test_microstructure_and_fees_yaml_expose_extended_guards() -> None:
    micro_payload = _load_policy("microstructure.yaml")
    fees_payload = _load_policy("fees.yaml")
    fundamentals_payload = _load_policy("fundamentals_credit_filter.yaml")

    micro = micro_payload.get("microstructure") if isinstance(micro_payload.get("microstructure"), dict) else {}
    fees = fees_payload.get("fees") if isinstance(fees_payload.get("fees"), dict) else {}
    fundamentals = (
        fundamentals_payload.get("fundamentals_credit_filter")
        if isinstance(fundamentals_payload.get("fundamentals_credit_filter"), dict)
        else {}
    )

    assert (micro.get("sampling") or {}).get("volume_bars") is True
    assert (micro.get("impact") or {}).get("model") == "hybrid_linear_to_sqrt"
    assert (fees.get("cost_realism_factor") or {}).get("missing") == 0.0
    assert fees.get("require_complete_cost_stack_for_learning") is True
    assert fundamentals.get("point_in_time_required") is True
    assert fundamentals.get("reject_revised_data_as_if_known_in_past") is True
