from __future__ import annotations

from pathlib import Path

from test_web_live_ready import _auth_headers, _build_app, _login, _seed_bot_registry_catalog


def _eligible_pool_ids(client, headers: dict[str, str]) -> list[str]:
  res = client.get("/api/v1/strategies", headers=headers)
  assert res.status_code == 200, res.text
  return [
    str(row["id"])
    for row in res.json()
    if (
      str(row.get("status") or "").strip().lower() == "active"
      and bool(row.get("enabled_for_trading", row.get("enabled", False)))
      and bool(row.get("allow_learning", True))
    )
  ]


def _seed_extra_pool_strategies(module, *, total: int) -> list[str]:
  meta = module.store.load_strategy_meta()
  seeded_ids: list[str] = []
  for index in range(total):
    strategy_id = f"rtlrese29_pool_seed_{index:02d}"
    meta[strategy_id] = {
      "name": f"RTLRESE-29 Pool Seed {index:02d}",
      "version": "1.0.0",
      "enabled": True,
      "allow_learning": True,
      "is_primary": False,
      "source": "uploaded",
      "status": "active",
      "notes": "Seed extra para validar cap del pool.",
      "description": "Seed de test para pool del bot.",
      "params_yaml": "",
      "tags": ["test", "rtlrese29"],
    }
    module.store.registry.upsert_strategy_registry(
      strategy_key=strategy_id,
      name=f"RTLRESE-29 Pool Seed {index:02d}",
      version="1.0.0",
      source="uploaded",
      status="active",
      enabled_for_trading=True,
      allow_learning=True,
      is_primary=False,
      tags=["test", "rtlrese29"],
    )
    seeded_ids.append(strategy_id)
  module.store.save_strategy_meta(meta)
  module.store._ensure_strategy_registry_invariants()
  return seeded_ids


def test_bot_registry_identity_crud_and_filters(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  pool_ids = _eligible_pool_ids(client, headers)[:2]
  assert len(pool_ids) == 2

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Momentum Spot",
      "alias": "momentum-a",
      "description": "Bot de registry para validar identidad editable.",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "capital_base_usd": 25000,
      "max_total_exposure_pct": 70,
      "max_asset_exposure_pct": 25,
      "risk_profile": "medium",
      "risk_per_trade_pct": 0.5,
      "max_daily_loss_pct": 3.0,
      "max_drawdown_pct": 15.0,
      "max_positions": 8,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  created = create_res.json()["bot"]
  bot_id = str(created["id"])
  assert bot_id.startswith("BOT-")
  assert created["bot_id"] == bot_id
  assert created["display_name"] == "Bot Momentum Spot"
  assert created["name"] == "Bot Momentum Spot"
  assert created["alias"] == "momentum-a"
  assert created["description"] == "Bot de registry para validar identidad editable."
  assert created["domain_type"] == "spot"
  assert created["registry_status"] == "active"
  assert created["archived_at"] is None
  assert created["universe_name"] == "core_spot_usdt"
  assert created["universe"] == ["BTCUSDT", "ETHUSDT"]
  assert int(created["max_live_symbols"]) == 2
  assert created["pool_strategy_ids"] == pool_ids
  assert created["strategy_pool_status"] == "valid"
  assert int(created["max_pool_strategies"]) == 15
  assert created["symbol_assignment_status"] == "valid"
  assert float(created["capital_base_usd"]) == 25000.0
  assert float(created["max_total_exposure_pct"]) == 70.0
  assert float(created["max_asset_exposure_pct"]) == 25.0
  assert created["risk_profile"] == "medium"
  assert float(created["risk_per_trade_pct"]) == 0.5
  assert float(created["max_daily_loss_pct"]) == 3.0
  assert float(created["max_drawdown_pct"]) == 15.0
  assert int(created["max_positions"]) == 8

  detail_res = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert detail_res.status_code == 200, detail_res.text
  detail = detail_res.json()["bot"]
  assert detail["id"] == bot_id
  assert detail["display_name"] == "Bot Momentum Spot"
  assert detail["domain_type"] == "spot"
  assert detail["risk_profile"] == "medium"
  assert detail["pool_strategy_ids"] == pool_ids
  assert detail["strategy_pool_status"] == "valid"
  assert detail["symbol_assignment_status"] == "valid"

  active_res = client.get("/api/v1/bots?registry_status=active&recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert active_res.status_code == 200, active_res.text
  active_ids = {str(row["id"]) for row in active_res.json()["items"]}
  assert bot_id in active_ids

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={
      "display_name": "Bot Momentum Futures",
      "alias": "momentum-b",
      "description": "Nombre visible actualizado sin perder bot_id.",
      "domain_type": "futures",
      "universe_name": "core_usdm_perps",
      "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
      "max_live_symbols": 3,
      "capital_base_usd": 40000,
      "max_total_exposure_pct": 85,
      "max_asset_exposure_pct": 35,
      "risk_profile": "aggressive",
      "risk_per_trade_pct": 1.0,
      "max_daily_loss_pct": 5.0,
      "max_drawdown_pct": 22.0,
      "max_positions": 12,
      "pool_strategy_ids": [pool_ids[-1]],
    },
  )
  assert patch_res.status_code == 200, patch_res.text
  patched = patch_res.json()["bot"]
  assert patched["id"] == bot_id
  assert patched["display_name"] == "Bot Momentum Futures"
  assert patched["name"] == "Bot Momentum Futures"
  assert patched["alias"] == "momentum-b"
  assert patched["description"] == "Nombre visible actualizado sin perder bot_id."
  assert patched["domain_type"] == "futures"
  assert patched["universe_name"] == "core_usdm_perps"
  assert patched["universe_family"] == "usdm_futures"
  assert patched["universe"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
  assert int(patched["max_live_symbols"]) == 3
  assert patched["pool_strategy_ids"] == [pool_ids[-1]]
  assert patched["strategy_pool_status"] == "valid"
  assert patched["symbol_assignment_status"] == "valid"
  assert patched["registry_status"] == "active"
  assert float(patched["capital_base_usd"]) == 40000.0
  assert float(patched["max_total_exposure_pct"]) == 85.0
  assert float(patched["max_asset_exposure_pct"]) == 35.0
  assert patched["risk_profile"] == "aggressive"
  assert float(patched["risk_per_trade_pct"]) == 1.0
  assert float(patched["max_daily_loss_pct"]) == 5.0
  assert float(patched["max_drawdown_pct"]) == 22.0
  assert int(patched["max_positions"]) == 12

  delete_res = client.delete(f"/api/v1/bots/{bot_id}", headers=headers)
  assert delete_res.status_code == 409, delete_res.text
  assert "soft-archive" in str(delete_res.json().get("detail") or "")

  archive_res = client.post(f"/api/v1/bots/{bot_id}/archive", headers=headers)
  assert archive_res.status_code == 200, archive_res.text
  archived = archive_res.json()["bot"]
  assert archived["id"] == bot_id
  assert archived["registry_status"] == "archived"
  assert archived["status"] == "archived"
  assert archive_res.json()["archived"]

  archived_res = client.get("/api/v1/bots?registry_status=archived&recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert archived_res.status_code == 200, archived_res.text
  archived_ids = {str(row["id"]) for row in archived_res.json()["items"]}
  assert bot_id in archived_ids

  active_after_archive = client.get("/api/v1/bots?registry_status=active&recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert active_after_archive.status_code == 200, active_after_archive.text
  assert bot_id not in {str(row["id"]) for row in active_after_archive.json()["items"]}

  restore_res = client.post(f"/api/v1/bots/{bot_id}/restore", headers=headers)
  assert restore_res.status_code == 200, restore_res.text
  restored = restore_res.json()["bot"]
  assert restored["id"] == bot_id
  assert restored["registry_status"] == "active"
  assert restored["status"] == "active"
  assert restored["archived_at"] is None
  _module.store.instrument_registry.db.save_snapshot(
    family="usdm_futures",
    environment="live",
    source_endpoint="test://usdm-live-refresh",
    raw_payload={"symbols": ["BTCUSDT", "SOLUSDT"]},
    items=[
      {
        "instrument_id": "binance:usdm_futures:BTCUSDT",
        "symbol": "BTCUSDT",
        "family": "usdm_futures",
        "environment": "live",
        "status": "TRADING",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "contract_type": "PERPETUAL",
        "margin_asset": "USDT",
        "catalog_source": "test_fixture",
        "filter_summary": {},
        "permission_summary": {},
        "live_eligible": True,
        "testnet_eligible": True,
        "paper_eligible": True,
        "raw_hash": "usdm_futures:BTCUSDT",
        "raw_payload": {"symbol": "BTCUSDT", "family": "usdm_futures", "status": "TRADING"},
      },
      {
        "instrument_id": "binance:usdm_futures:SOLUSDT",
        "symbol": "SOLUSDT",
        "family": "usdm_futures",
        "environment": "live",
        "status": "TRADING",
        "base_asset": "SOL",
        "quote_asset": "USDT",
        "contract_type": "PERPETUAL",
        "margin_asset": "USDT",
        "catalog_source": "test_fixture",
        "filter_summary": {},
        "permission_summary": {},
        "live_eligible": True,
        "testnet_eligible": True,
        "paper_eligible": True,
        "raw_hash": "usdm_futures:SOLUSDT",
        "raw_payload": {"symbol": "SOLUSDT", "family": "usdm_futures", "status": "TRADING"},
      },
    ],
    policy_hash="test-policy-hash",
  )
  stale_detail = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert stale_detail.status_code == 200, stale_detail.text
  stale_bot = stale_detail.json()["bot"]
  assert stale_bot["symbol_assignment_status"] == "error"
  assert any("ETHUSDT" in str(item) for item in (stale_bot.get("symbol_assignment_errors") or []))

  all_res = client.get("/api/v1/bots?registry_status=all&recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert all_res.status_code == 200, all_res.text
  all_ids = {str(row["id"]) for row in all_res.json()["items"]}
  assert bot_id in all_ids

def test_bot_registry_identity_validations(tmp_path: Path, monkeypatch) -> None:
  invalid_cases = [
    (
      {"display_name": "ab", "domain_type": "spot"},
      "display_name debe tener al menos 3 caracteres",
    ),
    (
      {"display_name": "Bot Valido", "alias": "x" * 41, "domain_type": "spot"},
      "alias no puede superar 40 caracteres",
    ),
    (
      {"display_name": "Bot Valido", "description": "x" * 281, "domain_type": "spot"},
      "description no puede superar 280 caracteres",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "margin"},
      "domain_type debe ser 'spot' o 'futures'",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "capital_base_usd": 0},
      "capital_base_usd debe ser > 0",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "risk_profile": "wild"},
      "risk_profile debe ser 'conservative', 'medium' o 'aggressive'",
    ),
    (
      {
        "display_name": "Bot Valido",
        "domain_type": "spot",
        "max_total_exposure_pct": 20,
        "max_asset_exposure_pct": 25,
      },
      "max_asset_exposure_pct no puede superar max_total_exposure_pct",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "max_positions": 0},
      "max_positions debe ser >= 1",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "universe_name": "missing", "universe": ["BTCUSDT"], "max_live_symbols": 1},
      "universe_name invalido",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "universe_name": "core_spot_usdt", "universe": ["BTCUSDT", "BTCUSDT"], "max_live_symbols": 1},
      "simbolos duplicados",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "universe_name": "core_spot_usdt", "universe": ["BTCUSDT"], "max_live_symbols": 2},
      "no puede superar la cantidad de simbolos asignados",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "universe_name": "core_usdm_perps", "universe": ["BTCUSDT"], "max_live_symbols": 1},
      "no es compatible con domain_type=spot",
    ),
    (
      {"display_name": "Bot Valido", "domain_type": "spot", "pool_strategy_ids": []},
      "al menos 1 estrategia asignada",
    ),
  ]

  for index, (payload, expected) in enumerate(invalid_cases):
    case_tmp = tmp_path / f"case_{index}"
    case_tmp.mkdir(parents=True, exist_ok=True)
    _module, client = _build_app(case_tmp, monkeypatch)
    _seed_bot_registry_catalog(_module)
    admin_token = _login(client, "Wadmin", "moroco123")
    headers = _auth_headers(admin_token)
    eligible_pool_ids = _eligible_pool_ids(client, headers)
    assert eligible_pool_ids
    base_payload = {
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": [eligible_pool_ids[0]],
      **payload,
    }
    res = client.post("/api/v1/bots", headers=headers, json=base_payload)
    assert res.status_code == 400, res.text
    assert expected in str(res.json().get("detail") or "")


def test_bot_registry_base_config_defaults_for_legacy_shape(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  eligible_pool_ids = _eligible_pool_ids(client, headers)
  assert eligible_pool_ids

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Legacy Compatible",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": [eligible_pool_ids[0]],
    },
  )
  assert create_res.status_code == 200, create_res.text
  created = create_res.json()["bot"]

  assert float(created["capital_base_usd"]) == 10000.0
  assert float(created["max_total_exposure_pct"]) == 65.0
  assert float(created["max_asset_exposure_pct"]) == 25.0
  assert created["risk_profile"] == "medium"
  assert float(created["risk_per_trade_pct"]) == 0.5
  assert float(created["max_daily_loss_pct"]) == 3.0
  assert float(created["max_drawdown_pct"]) == 15.0
  assert int(created["max_positions"]) == 10
  assert created["universe_name"] == "core_spot_usdt"
  assert created["universe"] == ["BTCUSDT"]
  assert int(created["max_live_symbols"]) == 1
  assert created["pool_strategy_ids"] == [eligible_pool_ids[0]]
  assert created["strategy_pool_status"] == "valid"


def test_bot_registry_strategy_pool_validation_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  _seed_extra_pool_strategies(_module, total=20)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  eligible_pool_ids = _eligible_pool_ids(client, headers)
  assert len(eligible_pool_ids) >= 16

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Pool Validation",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": eligible_pool_ids[:2],
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot = create_res.json()["bot"]
  bot_id = str(bot["id"])
  assert bot["strategy_pool_status"] == "valid"
  assert bot["pool_strategy_ids"] == eligible_pool_ids[:2]
  assert int(bot["max_pool_strategies"]) == 15

  duplicate_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": [eligible_pool_ids[0], eligible_pool_ids[0]]},
  )
  assert duplicate_res.status_code == 400, duplicate_res.text
  assert "duplicados" in str(duplicate_res.json().get("detail") or "")

  missing_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": ["missing_strategy_for_pool"]},
  )
  assert missing_res.status_code == 400, missing_res.text
  assert "inexistente" in str(missing_res.json().get("detail") or "")

  too_large_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": eligible_pool_ids[:16]},
  )
  assert too_large_res.status_code == 400, too_large_res.text
  assert "no puede superar 15" in str(too_large_res.json().get("detail") or "")

  no_learning_strategy = eligible_pool_ids[2]
  learning_block_res = client.patch(
    f"/api/v1/strategies/{no_learning_strategy}",
    headers=headers,
    json={"allow_learning": False},
  )
  assert learning_block_res.status_code == 200, learning_block_res.text
  rejected_no_learning = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": [no_learning_strategy]},
  )
  assert rejected_no_learning.status_code == 400, rejected_no_learning.text
  assert "allow_learning=false" in str(rejected_no_learning.json().get("detail") or "")

  archived_strategy = eligible_pool_ids[1]
  archive_res = client.patch(
    f"/api/v1/strategies/{archived_strategy}",
    headers=headers,
    json={"status": "archived"},
  )
  assert archive_res.status_code == 200, archive_res.text

  detail_res = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert detail_res.status_code == 200, detail_res.text
  detail = detail_res.json()["bot"]
  assert detail["pool_strategy_ids"] == eligible_pool_ids[:2]
  assert detail["strategy_pool_status"] == "error"
  assert any(archived_strategy in str(item) for item in (detail.get("strategy_pool_errors") or []))

  policy_res = client.get(f"/api/v1/bots/{bot_id}/policy-state", headers=headers)
  assert policy_res.status_code == 200, policy_res.text
  policy_state = policy_res.json()["policy_state"]
  assert policy_state["pool_strategy_ids"] == eligible_pool_ids[:2]
  assert policy_state["strategy_pool_status"] == "error"
  assert any(archived_strategy in str(item) for item in (policy_state.get("strategy_pool_errors") or []))
