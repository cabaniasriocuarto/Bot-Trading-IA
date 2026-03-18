from __future__ import annotations

from pathlib import Path

from rtlab_core.policy_paths import EXPECTED_POLICY_FILENAMES, describe_policy_root_resolution, resolve_policy_root


def test_describe_policy_root_resolution_marks_nested_as_compat_when_root_is_empty(tmp_path: Path) -> None:
  repo_root = tmp_path / "repo"
  root_policies = repo_root / "config" / "policies"
  nested_policies = repo_root / "rtlab_autotrader" / "config" / "policies"
  root_policies.mkdir(parents=True, exist_ok=True)
  nested_policies.mkdir(parents=True, exist_ok=True)
  (nested_policies / "beast_mode.yaml").write_text("beast_mode:\n  enabled: true\n", encoding="utf-8")

  payload = describe_policy_root_resolution(repo_root, explicit=root_policies)

  assert resolve_policy_root(repo_root, explicit=root_policies) == nested_policies.resolve()
  assert payload["selected_root"] == str(nested_policies.resolve())
  assert payload["canonical_root"] == str(root_policies.resolve())
  assert payload["fallback_used"] is True
  assert any("compatibilidad" in warning.lower() for warning in payload["warnings"])


def test_describe_policy_root_resolution_flags_divergent_duplicate_yaml(tmp_path: Path) -> None:
  repo_root = tmp_path / "repo"
  root_policies = repo_root / "config" / "policies"
  nested_policies = repo_root / "rtlab_autotrader" / "config" / "policies"
  root_policies.mkdir(parents=True, exist_ok=True)
  nested_policies.mkdir(parents=True, exist_ok=True)

  assert "runtime_controls.yaml" in EXPECTED_POLICY_FILENAMES

  for name in EXPECTED_POLICY_FILENAMES:
    root_policies.joinpath(name).write_text("root: true\n", encoding="utf-8")
    nested_policies.joinpath(name).write_text("nested: true\n", encoding="utf-8")

  payload = describe_policy_root_resolution(repo_root, explicit=root_policies)

  assert payload["selected_root"] == str(root_policies.resolve())
  divergent = payload["divergent_candidates"]
  assert divergent
  assert divergent[0]["role"] == "nested_backend_compat"
  assert "gates.yaml" in divergent[0]["differing_files_vs_selected"]
