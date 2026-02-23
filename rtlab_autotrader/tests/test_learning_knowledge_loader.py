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
  assert any(row["id"] == "trend_pullback_of" for row in templates)
  assert filters
  assert "pbo" in gates and "dsr" in gates

  ranges = loader.get_ranges("trend_pullback_of")
  assert "adx_threshold" in ranges
  assert "ema_fast" in ranges

  engines = loader.get_learning_engines()
  assert any(row["id"] == "bandit_thompson" for row in (engines.get("engines") or []))

  visual_cues = loader.get_visual_cues()
  assert "palette" in visual_cues and "thresholds" in visual_cues

  strategies_v2 = loader.get_strategies_v2()
  ids = {row["id"] for row in (strategies_v2.get("strategies") or [])}
  assert "trend_pullback_orderflow_v2" in ids
  assert "defensive_liquidity_v2" in ids

  explanation = loader.explain_candidate("cand_test")
  assert explanation["candidate_id"] == "cand_test"
  assert "PBO" in explanation["highlights"]


def test_knowledge_loader_falls_back_when_knowledge_dir_missing(tmp_path: Path) -> None:
  loader = KnowledgeLoader(repo_root=tmp_path)

  templates = loader.list_templates()
  filters = loader.list_filters()
  gates = loader.get_gates()
  ranges = loader.get_ranges("trend_pullback_of")
  engines = loader.get_learning_engines()
  visual_cues = loader.get_visual_cues()
  strategies_v2 = loader.get_strategies_v2()

  assert templates
  assert any(row["id"] == "trend_pullback_of" for row in templates)
  assert filters
  assert "pbo" in gates and "dsr" in gates
  assert "adx_threshold" in ranges
  assert (engines.get("engines") or [])
  assert "palette" in visual_cues
  assert (strategies_v2.get("strategies") or [])
