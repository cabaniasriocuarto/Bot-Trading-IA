from __future__ import annotations

from pathlib import Path

from test_web_live_ready import _auth_headers, _build_app, _login


def test_research_funnel_returns_trials_and_summary(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(token)

  module.store.backtest_catalog.upsert_research_trial(
    {
      "trial_id": "BX-API-001:v001",
      "batch_id": "BX-API-001",
      "run_id": "BT-API-001",
      "variant_id": "v001",
      "strategy_id": "trend_pullback_orderflow_confirm_v1",
      "strategy_name": "Trend Pullback + Orderflow Confirm",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "dataset_source": "binance_public",
      "dataset_hash": "ds_api_001",
      "universe_json": ["BTCUSDT", "ETHUSDT"],
      "rank_num": 1,
      "score": 0.83,
      "hard_filters_pass": 1,
      "gates_pass": 1,
      "promotable": 1,
      "recommendable_option_b": 1,
      "promotion_stage": "candidate",
      "rejection_reason_json": [],
      "summary_json": {"trade_count_oos": 160},
      "gates_json": {"passed": True},
      "anti_overfit_json": {"pbo": 0.12, "dsr": 0.95},
    }
  )
  module.store.backtest_catalog.upsert_research_trial(
    {
      "trial_id": "BX-API-001:v002",
      "batch_id": "BX-API-001",
      "run_id": "BT-API-002",
      "variant_id": "v002",
      "strategy_id": "trend_scanning_regime_v2",
      "strategy_name": "Trend Scanning + Regimenes",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "dataset_source": "binance_public",
      "dataset_hash": "ds_api_001",
      "universe_json": ["BTCUSDT", "ETHUSDT"],
      "rank_num": 2,
      "score": 0.42,
      "hard_filters_pass": 1,
      "gates_pass": 0,
      "promotable": 0,
      "recommendable_option_b": 0,
      "promotion_stage": "rejected_gates",
      "rejection_reason_json": ["pbo_cscv"],
      "summary_json": {"trade_count_oos": 110},
      "gates_json": {"passed": False, "fail_reasons": ["pbo_cscv"]},
      "anti_overfit_json": {"pbo": 0.41, "dsr": 0.62},
    }
  )

  res = client.get("/api/v1/research/funnel?batch_id=BX-API-001", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()
  assert payload["summary"]["total_trials"] == 2
  assert payload["summary"]["promotable_count"] == 1
  assert payload["summary"]["rejection_reason_counts"]["pbo_cscv"] == 1
  assert len(payload["items"]) == 2
  assert payload["items"][0]["trial_id"] == "BX-API-001:v001"

  filtered = client.get(
    "/api/v1/research/funnel?batch_id=BX-API-001&promotion_stage=candidate&promotable_only=true",
    headers=headers,
  )
  assert filtered.status_code == 200, filtered.text
  filtered_payload = filtered.json()
  assert filtered_payload["summary"]["total_trials"] == 2
  assert len(filtered_payload["items"]) == 1
  assert filtered_payload["items"][0]["trial_id"] == "BX-API-001:v001"
