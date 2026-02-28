from __future__ import annotations

from pathlib import Path

from rtlab_core.learning.service import LearningService


def test_learning_service_uses_canonical_config_gates_thresholds(tmp_path: Path) -> None:
  repo_root = Path(__file__).resolve().parents[2]
  service = LearningService(user_data_dir=tmp_path, repo_root=repo_root)

  thresholds = service._canonical_gates_thresholds()

  assert thresholds["source"] == "config/policies/gates.yaml"
  assert float(thresholds["pbo_max"]) == 0.05
  assert float(thresholds["dsr_min"]) == 0.95
