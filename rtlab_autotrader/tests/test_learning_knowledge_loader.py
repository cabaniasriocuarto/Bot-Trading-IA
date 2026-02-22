from __future__ import annotations

from pathlib import Path

from rtlab_core.learning import KnowledgeLoader


def test_knowledge_loader_reads_repo_pack() -> None:
  repo_root = Path(__file__).resolve().parents[2]
  loader = KnowledgeLoader(repo_root=repo_root)

  templates = loader.list_templates()
  filters = loader.list_filters()
  gates = loader.get_gates()

  assert templates
  assert any(row["id"] == "trend_pullback" for row in templates)
  assert filters
  assert "pbo" in gates and "dsr" in gates

  ranges = loader.get_ranges("trend_pullback")
  assert "adx_threshold" in ranges

  explanation = loader.explain_candidate("cand_test")
  assert explanation["candidate_id"] == "cand_test"
  assert "PBO" in explanation["highlights"]
