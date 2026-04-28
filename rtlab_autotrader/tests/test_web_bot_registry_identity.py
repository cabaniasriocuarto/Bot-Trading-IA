from __future__ import annotations

from pathlib import Path

import pytest

from test_web_live_ready import _auth_headers, _build_app, _catalog_item, _login, _seed_bot_registry_catalog


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


def _seed_large_spot_universe(module) -> list[str]:
  symbols = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "AVAXUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "MATICUSDT",
  ]
  module.store.instrument_registry.db.save_snapshot(
    family="spot",
    environment="live",
    source_endpoint="test://spot-live-large",
    raw_payload={"symbols": symbols},
    items=[
      _catalog_item(family="spot", symbol=symbol, base_asset=symbol.removesuffix("USDT"))
      for symbol in symbols
    ],
    policy_hash="test-policy-hash",
  )
  return symbols


def _create_scope_ready_bot(module, client, headers: dict[str, str], monkeypatch, *, universe: list[str] | None = None, max_live_symbols: int = 1) -> tuple[str, list[str]]:
  _seed_bot_registry_catalog(module)
  pool_ids = _eligible_pool_ids(client, headers)[: max(1, len(universe or ["BTCUSDT"]))]
  assert pool_ids
  symbols = universe or ["BTCUSDT"]
  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Scope Operativo RTLOPS-94",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": symbols,
      "max_live_symbols": max_live_symbols,
      "max_positions": max(1, max_live_symbols),
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])
  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        symbol: [pool_ids[min(index, len(pool_ids) - 1)]]
        for index, symbol in enumerate(symbols)
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text
  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        symbol: pool_ids[min(index, len(pool_ids) - 1)]
        for index, symbol in enumerate(symbols)
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text
  strategy_rows = [dict(row) for row in module.store.list_strategies()]
  pool_set = set(pool_ids)
  for row in strategy_rows:
    if str(row.get("id") or "") in pool_set:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
  monkeypatch.setattr(module.store, "list_strategies", lambda: strategy_rows)
  return bot_id, pool_ids


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
  assert created["last_change_type"] == "created"
  assert "Bot creado" in str(created.get("last_change_summary") or "")
  assert created["last_changed_by"] == "Wadmin"
  assert created["last_change_source"] == "bot_registry_api"
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
  assert detail["last_change_type"] == "created"

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
  assert patched["last_change_type"] == "updated"
  assert "display_name" in str(patched.get("last_change_summary") or "")
  assert patched["last_changed_by"] == "Wadmin"
  assert patched["last_change_source"] == "bot_registry_api"

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
  assert archived["last_change_type"] == "archived"
  assert "archivado" in str(archived.get("last_change_summary") or "").lower()

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
  assert restored["last_change_type"] == "reactivated"
  assert "reactivado" in str(restored.get("last_change_summary") or "").lower()
  assert restored["last_changed_by"] == "Wadmin"

  policy_state_res = client.get(f"/api/v1/bots/{bot_id}/policy-state", headers=headers)
  assert policy_state_res.status_code == 200, policy_state_res.text
  policy_state = policy_state_res.json()["policy_state"]
  assert policy_state["last_change_type"] == "reactivated"
  assert policy_state["last_changed_by"] == "Wadmin"
  assert policy_state["last_change_source"] == "bot_registry_api"

  decision_log_res = client.get(f"/api/v1/bots/{bot_id}/decision-log?page_size=10", headers=headers)
  assert decision_log_res.status_code == 200, decision_log_res.text
  decision_log = decision_log_res.json()
  decision_change_types = {
    str((row.get("payload") or {}).get("change_type") or "")
    for row in (decision_log.get("items") or [])
    if isinstance(row, dict)
  }
  assert {"created", "updated", "archived", "reactivated"}.issubset(decision_change_types)

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


def test_bot_registry_restore_requires_valid_current_registry(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  pool_ids = _eligible_pool_ids(client, headers)
  assert len(pool_ids) >= 2

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Reactivation Guard",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": [pool_ids[0]],
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  archive_res = client.post(f"/api/v1/bots/{bot_id}/archive", headers=headers)
  assert archive_res.status_code == 200, archive_res.text
  assert archive_res.json()["bot"]["registry_status"] == "archived"

  archive_strategy_res = client.patch(
    f"/api/v1/strategies/{pool_ids[0]}",
    headers=headers,
    json={"status": "archived"},
  )
  assert archive_strategy_res.status_code == 200, archive_strategy_res.text

  rejected_restore = client.post(f"/api/v1/bots/{bot_id}/restore", headers=headers)
  assert rejected_restore.status_code == 409, rejected_restore.text
  rejected_detail = str(rejected_restore.json().get("detail") or "")
  assert "registry invalido" in rejected_detail
  assert "archivada" in rejected_detail or "inactiva" in rejected_detail

  archived_detail = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert archived_detail.status_code == 200, archived_detail.text
  archived_bot = archived_detail.json()["bot"]
  assert archived_bot["registry_status"] == "archived"
  assert archived_bot["last_change_type"] == "archived"

  reactivate_strategy_res = client.patch(
    f"/api/v1/strategies/{pool_ids[0]}",
    headers=headers,
    json={"status": "active", "enabled_for_trading": True, "allow_learning": True},
  )
  assert reactivate_strategy_res.status_code == 200, reactivate_strategy_res.text

  restore_res = client.post(f"/api/v1/bots/{bot_id}/restore", headers=headers)
  assert restore_res.status_code == 200, restore_res.text
  restored = restore_res.json()["bot"]
  assert restored["registry_status"] == "active"
  assert restored["last_change_type"] == "reactivated"
  assert restored["last_change_source"] == "bot_registry_api"


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
      {
        "display_name": "Bot Valido",
        "domain_type": "spot",
        "universe_name": "core_spot_usdt",
        "universe": ["BTCUSDT", "ETHUSDT"],
        "max_live_symbols": 2,
        "max_positions": 1,
      },
      "max_live_symbols no puede superar max_positions",
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


def test_bot_registry_contract_surface_is_canonical(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/bots/registry-contract", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()

  assert payload["contract_version"] == "rtlops81/v1"
  assert payload["storage"]["kind"] == "json_file"
  assert payload["storage"]["path"] == "learning/bots.json"
  assert payload["storage"]["stable_id_field"] == "bot_id"
  assert payload["storage"]["supports_soft_archive"] is True
  assert "last_change_type" in payload["storage"]["trace_fields"]
  assert payload["storage"]["multi_symbol_fields"] == ["universe_name", "universe", "max_live_symbols"]
  assert payload["storage"]["strategy_eligibility_fields"] == ["strategy_eligibility_by_symbol"]
  assert payload["storage"]["strategy_selection_fields"] == ["strategy_selection_by_symbol"]
  assert payload["storage"]["signal_consolidation_fields"] == []
  assert payload["storage"]["runtime_fields"] == []
  assert payload["storage"]["lifecycle_fields"] == []
  assert payload["storage"]["lifecycle_operational_fields"] == ["lifecycle_operational_by_symbol"]
  assert payload["api"]["list_path"] == "/api/v1/bots"
  assert payload["api"]["patch_path"] == "/api/v1/bots/{bot_id}"
  assert payload["api"]["multi_symbol_path"] == "/api/v1/bots/{bot_id}/multi-symbol"
  assert payload["api"]["scope_eligibility_path"] == "/api/v1/bots/{bot_id}/scope-eligibility"
  assert payload["api"]["symbol_strategy_eligibility_path"] == "/api/v1/bots/{bot_id}/symbol-strategy-eligibility"
  assert payload["api"]["symbol_strategy_selection_path"] == "/api/v1/bots/{bot_id}/strategy-selection"
  assert payload["api"]["signal_consolidation_path"] == "/api/v1/bots/{bot_id}/signal-consolidation"
  assert payload["api"]["runtime_path"] == "/api/v1/bots/{bot_id}/runtime"
  assert payload["api"]["lifecycle_path"] == "/api/v1/bots/{bot_id}/lifecycle"
  assert payload["api"]["lifecycle_operational_path"] == "/api/v1/bots/{bot_id}/lifecycle-operational"
  assert payload["api"]["policy_state_path"] == "/api/v1/bots/{bot_id}/policy-state"
  assert payload["api"]["decision_log_path"] == "/api/v1/bots/{bot_id}/decision-log"
  assert payload["defaults"]["domain_type"] == "spot"
  assert payload["defaults"]["risk_profile"] == "medium"
  assert payload["defaults"]["strategy_eligibility_by_symbol"] == {}
  assert payload["defaults"]["strategy_selection_by_symbol"] == {}
  assert payload["defaults"]["lifecycle_operational_by_symbol"] == {}
  assert float(payload["defaults"]["capital_base_usd"]) == 10000.0
  assert float(payload["defaults"]["max_total_exposure_pct"]) == 65.0
  assert int(payload["defaults"]["max_positions"]) == 10
  assert int(payload["limits"]["max_pool_strategies"]) == 15
  assert int(payload["limits"]["max_live_symbols"]) == 12
  assert int(payload["limits"]["display_name_max_length"]) == 80
  assert int(payload["limits"]["max_instances"]) >= 1
  assert payload["enums"]["domain_types"] == ["spot", "futures"]
  assert payload["enums"]["registry_statuses"] == ["active", "archived"]
  assert payload["enums"]["engines"] == ["fixed_rules", "bandit_thompson", "bandit_ucb1"]
  assert float(payload["risk_profiles"]["aggressive"]["max_drawdown_pct"]) == 22.0
  assert "pool_strategy_ids" in payload["fields"]["strategy_pool"]
  assert "strategy_eligibility_by_symbol" in payload["fields"]["strategy_eligibility"]
  assert "strategy_selection_by_symbol" in payload["fields"]["strategy_selection"]
  assert payload["fields"]["signal_consolidation"] == ["signal_consolidation"]
  assert payload["fields"]["runtime"] == ["runtime"]
  assert payload["fields"]["lifecycle"] == ["lifecycle"]
  assert payload["fields"]["lifecycle_operational"] == ["lifecycle_operational"]
  assert "bot_id" in payload["fields"]["identity"]
  assert "last_change_source" in payload["fields"]["trace"]
  assert payload["multi_symbol"]["contract_version"] == "rtlops72/v1"
  assert payload["multi_symbol"]["storage_fields"] == ["universe_name", "universe", "max_live_symbols"]
  assert int(payload["multi_symbol"]["limits"]["configured_symbols_max"]) == 12
  assert int(payload["multi_symbol"]["limits"]["max_active_symbols_max"]) == 12
  assert "symbols" in payload["multi_symbol"]["fields"]
  assert payload["scope_eligibility"]["contract_version"] == "rtlops96/v1"
  assert payload["scope_eligibility"]["storage_fields"] == []
  assert payload["scope_eligibility"]["ownership"]["persisted_scope_owner"] == "bot_registry"
  assert payload["scope_eligibility"]["ownership"]["operation_manual_selector_allowed"] is False
  assert "shadow" in payload["scope_eligibility"]["ownership"]["operation_scope_modes"]
  assert "bot_inherited" in payload["scope_eligibility"]["ownership"]["research_scope_modes"]
  assert "eligible_symbols" in payload["scope_eligibility"]["fields"]
  assert "blocking_reasons" in payload["scope_eligibility"]["fields"]
  assert payload["strategy_eligibility"]["contract_version"] == "rtlops73/v1"
  assert payload["strategy_eligibility"]["storage_fields"] == ["strategy_eligibility_by_symbol"]
  assert "strategy_not_in_pool" in payload["strategy_eligibility"]["reason_codes"]
  assert "eligible_strategy_ids_by_symbol" in payload["strategy_eligibility"]["fields"]
  assert payload["strategy_selection"]["contract_version"] == "rtlops74/v1"
  assert payload["strategy_selection"]["storage_fields"] == ["strategy_selection_by_symbol"]
  assert "selected_strategy_not_eligible" in payload["strategy_selection"]["reason_codes"]
  assert "primary_strategy" in payload["strategy_selection"]["criteria"]
  assert "selected_strategy_by_symbol" in payload["strategy_selection"]["fields"]
  assert payload["signal_consolidation"]["contract_version"] == "rtlops75/v1"
  assert payload["signal_consolidation"]["storage_fields"] == []
  assert "selected_strategy" in payload["signal_consolidation"]["criteria"]
  assert "selected_strategy_signal_unresolved" in payload["signal_consolidation"]["reason_codes"]
  assert "net_decision_by_symbol" in payload["signal_consolidation"]["fields"]
  assert payload["runtime"]["contract_version"] == "rtlops77/v1"
  assert payload["runtime"]["storage_fields"] == []
  assert "signal_consolidation_invalid" in payload["runtime"]["reason_codes"]
  assert "live_cap_exceeds_max_positions" in payload["runtime"]["reason_codes"]
  assert "trade_decisions_exceed_live_cap" in payload["runtime"]["reason_codes"]
  assert "policy_state" in payload["runtime"]["fields"]
  assert "net_decision_by_symbol" in payload["runtime"]["fields"]
  assert "caps" in payload["runtime"]["fields"]
  assert "guardrails" in payload["runtime"]["fields"]
  assert payload["lifecycle"]["contract_version"] == "rtlops80/v1"
  assert payload["lifecycle"]["storage_fields"] == []
  assert "runtime_execution_not_ready" in payload["lifecycle"]["reason_codes"]
  assert "trade_decisions_exceed_live_cap" in payload["lifecycle"]["reason_codes"]
  assert "execution_ready" in payload["lifecycle"]["fields"]
  assert "allowed_trade_symbols" in payload["lifecycle"]["fields"]
  assert "rejected_trade_symbols" in payload["lifecycle"]["fields"]
  assert "progressing_symbols" in payload["lifecycle"]["fields"]
  assert payload["lifecycle_operational"]["contract_version"] == "rtlops81/v1"
  assert payload["lifecycle_operational"]["storage_fields"] == ["lifecycle_operational_by_symbol"]
  assert payload["lifecycle_operational"]["statuses"] == ["active", "paused"]
  assert "symbol_operational_paused" in payload["lifecycle_operational"]["reason_codes"]
  assert "lifecycle_operational_by_symbol" in payload["lifecycle_operational"]["fields"]


def test_bot_multi_symbol_surface_is_canonical_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Multi Symbol Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  created = create_res.json()["bot"]
  bot_id = str(created["id"])
  assert created["multi_symbol"]["contract_version"] == "rtlops72/v1"
  assert created["multi_symbol"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
  assert int(created["multi_symbol"]["configured_symbols_count"]) == 2
  assert int(created["multi_symbol"]["max_configured_symbols"]) == 12
  assert int(created["multi_symbol"]["max_active_symbols"]) == 2
  assert created["multi_symbol"]["status"] == "valid"

  multi_symbol_res = client.get(f"/api/v1/bots/{bot_id}/multi-symbol", headers=headers)
  assert multi_symbol_res.status_code == 200, multi_symbol_res.text
  multi_symbol = multi_symbol_res.json()["multi_symbol"]
  assert multi_symbol["contract_version"] == "rtlops72/v1"
  assert multi_symbol["universe_name"] == "core_spot_usdt"
  assert multi_symbol["symbols"] == ["BTCUSDT", "ETHUSDT"]
  assert int(multi_symbol["configured_symbols_count"]) == 2
  assert int(multi_symbol["max_configured_symbols"]) == 12
  assert int(multi_symbol["max_active_symbols"]) == 2
  assert multi_symbol["storage_fields"] == ["universe_name", "universe", "max_live_symbols"]
  assert multi_symbol["status"] == "valid"

  _module.store.instrument_registry.db.save_snapshot(
    family="spot",
    environment="live",
    source_endpoint="test://spot-live-stale-multisymbol",
    raw_payload={"symbols": ["BTCUSDT"]},
    items=[
      _catalog_item(family="spot", symbol="BTCUSDT", base_asset="BTC"),
    ],
    policy_hash="test-policy-hash",
  )

  stale_multi_symbol_res = client.get(f"/api/v1/bots/{bot_id}/multi-symbol", headers=headers)
  assert stale_multi_symbol_res.status_code == 200, stale_multi_symbol_res.text
  stale_multi_symbol = stale_multi_symbol_res.json()["multi_symbol"]
  assert stale_multi_symbol["status"] == "error"
  assert any("ETHUSDT" in str(item) for item in (stale_multi_symbol.get("errors") or []))


def test_bot_strategy_eligibility_surface_is_canonical_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Eligibility Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  created = create_res.json()["bot"]
  bot_id = str(created["id"])
  assert created["strategy_eligibility"]["contract_version"] == "rtlops73/v1"
  assert created["strategy_eligibility"]["status"] == "valid"
  assert created["strategy_eligibility"]["strategy_eligibility_by_symbol"] == {
    "BTCUSDT": pool_ids,
    "ETHUSDT": pool_ids,
  }
  assert created["strategy_eligibility"]["eligible_strategy_ids_by_symbol"] == {
    "BTCUSDT": pool_ids,
    "ETHUSDT": pool_ids,
  }

  eligibility_res = client.get(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
  )
  assert eligibility_res.status_code == 200, eligibility_res.text
  eligibility = eligibility_res.json()["strategy_eligibility"]
  assert eligibility["contract_version"] == "rtlops73/v1"
  assert eligibility["symbols"] == ["BTCUSDT", "ETHUSDT"]
  assert eligibility["pool_strategy_ids"] == pool_ids
  assert eligibility["status"] == "valid"

  archive_res = client.patch(
    f"/api/v1/strategies/{pool_ids[1]}",
    headers=headers,
    json={"status": "archived"},
  )
  assert archive_res.status_code == 200, archive_res.text

  stale_res = client.get(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
  )
  assert stale_res.status_code == 200, stale_res.text
  stale = stale_res.json()["strategy_eligibility"]
  assert stale["status"] == "error"
  assert "strategy_pool_invalid" in stale["reason_codes"]
  assert "strategy_not_effective_in_pool" in stale["reason_codes"]
  assert any(pool_ids[1] in str(item) for item in (stale.get("errors") or []))


def test_bot_strategy_eligibility_patch_validates_scope_and_archive_guard(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RATE_LIMIT_EXPENSIVE_REQ_PER_MIN", "20")
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
      "display_name": "Bot Eligibility Patch",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  missing_symbol_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={"strategy_eligibility_by_symbol": {"BTCUSDT": [pool_ids[0]]}},
  )
  assert missing_symbol_res.status_code == 400, missing_symbol_res.text
  assert "debe cubrir todos los símbolos" in str(missing_symbol_res.json().get("detail") or "")

  out_of_pool_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": ["missing_strategy_for_symbol"],
      },
    },
  )
  assert out_of_pool_res.status_code == 400, out_of_pool_res.text
  assert "fuera del pool actual" in str(out_of_pool_res.json().get("detail") or "")

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert patch_res.status_code == 200, patch_res.text
  eligibility = patch_res.json()["strategy_eligibility"]
  assert eligibility["status"] == "valid"
  assert eligibility["strategy_eligibility_by_symbol"] == {
    "BTCUSDT": [pool_ids[0]],
    "ETHUSDT": [pool_ids[1]],
  }

  invalid_pool_patch = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": [pool_ids[0]]},
  )
  assert invalid_pool_patch.status_code == 400, invalid_pool_patch.text
  assert "queda sin estrategias elegibles" in str(invalid_pool_patch.json().get("detail") or "")

  archive_bot_res = client.post(f"/api/v1/bots/{bot_id}/archive", headers=headers)
  assert archive_bot_res.status_code == 200, archive_bot_res.text

  archived_patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[0]],
      },
    },
  )
  assert archived_patch_res.status_code == 409, archived_patch_res.text
  assert "archivado" in str(archived_patch_res.json().get("detail") or "").lower()


def test_bot_strategy_selection_surface_is_canonical_and_deterministic(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Selection Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[0], pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text
  selection = selection_res.json()["strategy_selection"]
  assert selection["contract_version"] == "rtlops74/v1"
  assert selection["status"] == "valid"
  assert selection["strategy_selection_by_symbol"] == {"ETHUSDT": pool_ids[1]}
  assert selection["selected_strategy_by_symbol"] == {
    "BTCUSDT": pool_ids[0],
    "ETHUSDT": pool_ids[1],
  }
  items = {str(item["symbol"]): item for item in selection["items"]}
  assert items["BTCUSDT"]["selection_source"] == "derived"
  assert items["BTCUSDT"]["selection_criterion"] == "single_eligible"
  assert items["BTCUSDT"]["selected_strategy_id"] == pool_ids[0]
  assert items["ETHUSDT"]["selection_source"] == "explicit"
  assert items["ETHUSDT"]["selection_criterion"] == "explicit"
  assert items["ETHUSDT"]["selected_strategy_id"] == pool_ids[1]

  get_res = client.get(f"/api/v1/bots/{bot_id}/strategy-selection", headers=headers)
  assert get_res.status_code == 200, get_res.text
  get_selection = get_res.json()["strategy_selection"]
  assert get_selection["strategy_selection_by_symbol"] == {"ETHUSDT": pool_ids[1]}
  assert get_selection["selected_strategy_by_symbol"]["BTCUSDT"] == pool_ids[0]
  assert get_selection["selected_strategy_by_symbol"]["ETHUSDT"] == pool_ids[1]


def test_bot_strategy_selection_patch_validates_scope_and_archive_guard(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RATE_LIMIT_EXPENSIVE_REQ_PER_MIN", "20")
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
      "display_name": "Bot Selection Patch",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  out_of_scope_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={"strategy_selection_by_symbol": {"SOLUSDT": pool_ids[0]}},
  )
  assert out_of_scope_res.status_code == 400, out_of_scope_res.text
  assert "fuera del universe actual" in str(out_of_scope_res.json().get("detail") or "")

  invalid_symbol_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={"strategy_selection_by_symbol": {"BTCUSDT": pool_ids[1]}},
  )
  assert invalid_symbol_res.status_code == 400, invalid_symbol_res.text
  assert "no elegible" in str(invalid_symbol_res.json().get("detail") or "")

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert patch_res.status_code == 200, patch_res.text
  selection = patch_res.json()["strategy_selection"]
  assert selection["status"] == "valid"
  assert selection["strategy_selection_by_symbol"] == {
    "BTCUSDT": pool_ids[0],
    "ETHUSDT": pool_ids[1],
  }

  reset_eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0], pool_ids[1]],
        "ETHUSDT": [pool_ids[0], pool_ids[1]],
      },
    },
  )
  assert reset_eligibility_res.status_code == 200, reset_eligibility_res.text

  invalid_pool_patch = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": [pool_ids[0]]},
  )
  assert invalid_pool_patch.status_code == 400, invalid_pool_patch.text
  assert "strategy_selection_by_symbol[ETHUSDT]" in str(invalid_pool_patch.json().get("detail") or "")

  archive_res = client.post(f"/api/v1/bots/{bot_id}/archive", headers=headers)
  assert archive_res.status_code == 200, archive_res.text

  archived_patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={"strategy_selection_by_symbol": {"BTCUSDT": pool_ids[0]}},
  )
  assert archived_patch_res.status_code == 409, archived_patch_res.text
  assert "archivado" in str(archived_patch_res.json().get("detail") or "").lower()


def test_bot_signal_consolidation_surface_is_canonical_and_traceable(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Consolidation Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0], pool_ids[1]],
        "ETHUSDT": [pool_ids[0], pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {"runtime_side": "BUY"}
      row["tags"] = []
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  consolidation_res = client.get(f"/api/v1/bots/{bot_id}/signal-consolidation", headers=headers)
  assert consolidation_res.status_code == 200, consolidation_res.text
  consolidation = consolidation_res.json()["signal_consolidation"]
  assert consolidation["contract_version"] == "rtlops75/v1"
  assert consolidation["status"] == "valid"
  assert consolidation["net_decision_by_symbol"]["BTCUSDT"]["action"] == "trade"
  assert consolidation["net_decision_by_symbol"]["BTCUSDT"]["side"] == "BUY"
  assert consolidation["net_decision_by_symbol"]["BTCUSDT"]["selected_strategy_id"] == pool_ids[0]
  assert consolidation["net_decision_by_symbol"]["ETHUSDT"]["action"] == "trade"
  assert consolidation["net_decision_by_symbol"]["ETHUSDT"]["side"] == "SELL"
  assert consolidation["net_decision_by_symbol"]["ETHUSDT"]["selected_strategy_id"] == pool_ids[1]

  items = {str(item["symbol"]): item for item in consolidation["items"]}
  assert items["BTCUSDT"]["input_summary"]["agreement_status"] == "conflicted"
  assert items["BTCUSDT"]["input_summary"]["buy_signals"] == 1
  assert items["BTCUSDT"]["input_summary"]["sell_signals"] == 1
  assert items["BTCUSDT"]["net_strategy_id"] == pool_ids[0]
  assert items["BTCUSDT"]["net_criterion"] == "selected_strategy:side_override"
  assert items["ETHUSDT"]["net_strategy_id"] == pool_ids[1]
  assert items["ETHUSDT"]["net_criterion"] == "selected_strategy:meanreversion_tags_sell"

  detail_res = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert detail_res.status_code == 200, detail_res.text
  detail_bot = detail_res.json()["bot"]
  assert detail_bot["signal_consolidation"]["net_decision_by_symbol"]["BTCUSDT"]["selected_strategy_id"] == pool_ids[0]
  assert detail_bot["signal_consolidation"]["net_decision_by_symbol"]["ETHUSDT"]["selected_strategy_id"] == pool_ids[1]


def test_bot_runtime_surface_is_canonical_and_traceable(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Runtime Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0], pool_ids[1]],
        "ETHUSDT": [pool_ids[0], pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {"runtime_side": "BUY"}
      row["tags"] = []
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  runtime_res = client.get(f"/api/v1/bots/{bot_id}/runtime", headers=headers)
  assert runtime_res.status_code == 200, runtime_res.text
  runtime = runtime_res.json()["runtime"]
  assert runtime["contract_version"] == "rtlops77/v1"
  assert runtime["status"] == "valid"
  assert runtime["storage_fields"] == []
  assert runtime["caps"] == {
    "configured_symbols_count": 2,
    "trade_decisions_count": 2,
    "max_live_symbols": 2,
    "max_positions": 10,
  }
  assert runtime["guardrails"] == {
    "status": "valid",
    "execution_ready": True,
    "allowed_trade_symbols": ["BTCUSDT", "ETHUSDT"],
    "rejected_trade_symbols": [],
    "reason_codes": [],
    "errors": [],
    "prioritization_criterion": None,
  }
  assert runtime["storage"]["registry"]["path"] == "learning/bots.json"
  assert runtime["storage"]["decision_log"]["path"] == "console_api.sqlite3"
  assert runtime["storage"]["runtime_state"]["path"] == "logs/bot_state.json"
  assert runtime["api"]["runtime_path"] == f"/api/v1/bots/{bot_id}/runtime"
  assert runtime["api"]["signal_consolidation_path"] == f"/api/v1/bots/{bot_id}/signal-consolidation"
  assert runtime["selected_strategy_by_symbol"] == {
    "BTCUSDT": pool_ids[0],
    "ETHUSDT": pool_ids[1],
  }
  assert runtime["net_decision_by_symbol"]["BTCUSDT"]["selected_strategy_id"] == pool_ids[0]
  assert runtime["net_decision_by_symbol"]["ETHUSDT"]["selected_strategy_id"] == pool_ids[1]
  items = {str(item["symbol"]): item for item in runtime["items"]}
  assert items["BTCUSDT"]["runtime_symbol_id"] == f"{bot_id}:BTCUSDT"
  assert items["BTCUSDT"]["selection_key"] == f"{bot_id}:BTCUSDT:selection"
  assert items["BTCUSDT"]["net_decision_key"] == f"{bot_id}:BTCUSDT:net_decision"
  assert items["BTCUSDT"]["decision_action"] == "trade"
  assert items["BTCUSDT"]["decision_side"] == "BUY"
  assert items["BTCUSDT"]["decision_log_scope"] == {"bot_id": bot_id, "symbol": "BTCUSDT"}
  assert items["ETHUSDT"]["decision_reason"] == "strategy_tags_meanreversion"
  assert items["ETHUSDT"]["agreement_status"] == "conflicted"

  detail_res = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert detail_res.status_code == 200, detail_res.text
  detail_bot = detail_res.json()["bot"]
  assert detail_bot["runtime"]["contract_version"] == "rtlops77/v1"
  assert detail_bot["runtime"]["items"][0]["runtime_symbol_id"].startswith(f"{bot_id}:")


def test_rtlops68_runtime_order_intent_uses_net_decision_by_symbol_without_strategy_duplication(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Net Symbol Intent",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={"strategy_eligibility_by_symbol": {"BTCUSDT": pool_ids}},
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={"strategy_selection_by_symbol": {"BTCUSDT": pool_ids[0]}},
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {"runtime_side": "BUY"}
      row["tags"] = []
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {"runtime_side": "SELL"}
      row["tags"] = []
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  intent = _module.runtime_bridge._runtime_order_intent_from_bot_net_decision(
    state={"active_bot_id": bot_id},
    mode="paper",
  )
  assert intent["source"] == "bot_runtime_net_decision"
  assert intent["action"] == "trade"
  assert intent["symbol"] == "BTCUSDT"
  assert intent["side"] == "BUY"
  assert intent["strategy_id"] == pool_ids[0]
  assert intent["selected_strategy_id"] == pool_ids[0]
  assert intent["net_decision_key"] == f"{bot_id}:BTCUSDT:net_decision"
  assert intent["decision_log_scope"] == {"bot_id": bot_id, "symbol": "BTCUSDT"}
  assert intent["candidate_intents_count"] == 1
  assert intent["suppressed_intents_count"] == 0
  assert len(intent["net_decision_intents"]) == 1


def test_rtlops68_runtime_order_intent_fails_closed_when_bot_runtime_is_not_ready(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["BTCUSDT"], max_live_symbols=1)
  runtime = _module.store.bot_runtime_or_404(bot_id)
  runtime["status"] = "error"
  runtime["reason_codes"] = ["signal_consolidation_invalid"]
  runtime["guardrails"] = {
    **dict(runtime.get("guardrails") or {}),
    "execution_ready": False,
    "reason_codes": ["runtime_execution_not_ready"],
  }
  monkeypatch.setattr(_module.store, "bot_runtime_or_404", lambda target_bot_id: runtime)

  intent = _module.runtime_bridge._runtime_order_intent_from_bot_net_decision(
    state={"active_bot_id": bot_id},
    mode="paper",
  )
  assert intent["source"] == "bot_runtime_net_decision"
  assert intent["action"] == "blocked"
  assert intent["reason"] == "bot_runtime_execution_not_ready"
  assert "signal_consolidation_invalid" in intent["blocking_reasons"]

  submit_result = _module.runtime_bridge._maybe_submit_paper_runtime_order(state={"active_bot_id": bot_id})
  assert submit_result["submitted"] is False
  assert submit_result["intent_source"] == "bot_runtime_net_decision"
  assert submit_result["reason"] == "bot_runtime_execution_not_ready"
  assert "signal_consolidation_invalid" in submit_result["blocking_reasons"]


def test_bot_scope_eligibility_surface_is_canonical_and_operation_inherits_bot_scope(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Scope Eligibility Canonico",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["ETHUSDT", "BTCUSDT"],
      "max_live_symbols": 1,
      "max_positions": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  scope_res = client.get(f"/api/v1/bots/{bot_id}/scope-eligibility", headers=headers)
  assert scope_res.status_code == 200, scope_res.text
  scope = scope_res.json()["scope_eligibility"]
  assert scope["contract_version"] == "rtlops96/v1"
  assert scope["scope_source"] == "bot_runtime_scope"
  assert scope["ownership"] == {
    "entity_kind": "bot",
    "entity_id": bot_id,
    "persisted_scope_owner": "bot_registry",
    "strategy_role": "consumer_only",
    "research_scope_modes": ["manual", "bot_inherited"],
    "operation_scope_modes": ["shadow", "paper", "testnet", "live"],
    "operation_manual_selector_allowed": False,
  }
  assert scope["universe_name"] == "core_spot_usdt"
  assert scope["market_family"] == "spot"
  assert scope["quote_asset"] == "USDT"
  assert scope["symbols_configured"] == ["ETHUSDT", "BTCUSDT"]
  assert scope["configured_symbols_count"] == 2
  assert scope["max_active_symbols"] == 1
  assert scope["eligible_symbols"] == ["ETHUSDT"]
  assert scope["ineligible_symbols"] == ["BTCUSDT"]
  assert scope["status"] == "warning"
  assert "trade_decisions_exceed_live_cap" in scope["reason_codes"]
  assert scope["api"]["scope_eligibility_path"] == f"/api/v1/bots/{bot_id}/scope-eligibility"
  items = {str(item["symbol"]): item for item in scope["items"]}
  assert items["ETHUSDT"]["scope_status"] == "eligible"
  assert items["ETHUSDT"]["progression_allowed"] is True
  assert items["ETHUSDT"]["blocking_reasons"] == []
  assert items["BTCUSDT"]["scope_status"] == "ineligible"
  assert items["BTCUSDT"]["progression_allowed"] is False
  assert items["BTCUSDT"]["selected_strategy_id"] == pool_ids[0]
  assert "trade_decisions_exceed_live_cap" in items["BTCUSDT"]["reason_codes"]
  assert items["BTCUSDT"]["blocking_reasons"]


@pytest.mark.parametrize("mode,environment", [("shadow", "paper"), ("paper", "paper"), ("testnet", "testnet"), ("live", "live")])
def test_rtlops94_operation_modes_inherit_bot_scope(tmp_path: Path, monkeypatch, mode: str, environment: str) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["BTCUSDT"], max_live_symbols=1)

  gate = _module.store.bot_operation_scope_gate(bot_id, mode=mode, requested_symbols=["BTCUSDT"])
  assert gate["status"] == "ready"
  assert gate["scope_source"] == "bot_runtime_scope"
  assert gate["entity_kind"] == "bot"
  assert gate["eligible_symbols"] == ["BTCUSDT"]
  assert gate["ineligible_symbols"] == []
  assert gate["manual_selector_allowed"] is False

  payload = {
    "family": "spot",
    "environment": environment,
    "mode": mode,
    "bot_id": bot_id,
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.01,
    "price": 50000.0,
    "market_snapshot": {"best_bid": 49990.0, "best_ask": 50010.0, "last": 50000.0, "mark": 50000.0},
  }
  preflight_res = client.post("/api/v1/execution/preflight", headers=headers, json=payload)
  assert preflight_res.status_code == 200, preflight_res.text
  operation_scope = preflight_res.json()["operation_scope"]
  assert operation_scope["mode"] == mode
  assert operation_scope["bot_id"] == bot_id
  assert operation_scope["eligible_symbols"] == ["BTCUSDT"]
  assert operation_scope["is_blocking"] is False


def test_rtlops94_operation_preflight_rejects_parallel_manual_symbol(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["BTCUSDT"], max_live_symbols=1)

  payload = {
    "family": "spot",
    "environment": "paper",
    "mode": "paper",
    "bot_id": bot_id,
    "symbol": "ETHUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.01,
    "price": 3000.0,
    "market_snapshot": {"best_bid": 2990.0, "best_ask": 3010.0, "last": 3000.0, "mark": 3000.0},
  }
  res = client.post("/api/v1/execution/preflight", headers=headers, json=payload)
  assert res.status_code == 400
  detail = res.json()["detail"]
  assert detail["code"] == "operation_scope_blocked"
  assert "manual_symbol_not_in_bot_scope:ETHUSDT" in detail["blocking_reasons"]


def test_rtlops94_operation_scope_blocks_empty_or_over_cap_scope(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["ETHUSDT", "BTCUSDT"], max_live_symbols=1)

  over_cap_gate = _module.store.bot_operation_scope_gate(bot_id, mode="paper", requested_symbols=["ETHUSDT"])
  assert over_cap_gate["is_blocking"] is True
  assert "operation_scope_exceeds_max_active_symbols" in over_cap_gate["blocking_reasons"]
  assert "operation_scope_contains_ineligible_symbols" in over_cap_gate["blocking_reasons"]

  missing_bot_gate = _module.store.bot_operation_scope_gate(None, mode="paper")
  assert missing_bot_gate["is_blocking"] is True
  assert "operation_scope_requires_bot_id" in missing_bot_gate["blocking_reasons"]


def test_rtlops94_operation_preflight_rejects_invalid_mode_even_with_valid_environment(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["BTCUSDT"], max_live_symbols=1)

  payload = {
    "family": "spot",
    "environment": "live",
    "mode": "banana",
    "bot_id": bot_id,
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.01,
    "price": 50000.0,
    "market_snapshot": {"best_bid": 49990.0, "best_ask": 50010.0, "last": 50000.0, "mark": 50000.0},
  }
  res = client.post("/api/v1/execution/preflight", headers=headers, json=payload)
  assert res.status_code == 400
  detail = res.json()["detail"]
  assert detail["code"] == "operation_scope_blocked"
  assert detail["mode"] == "banana"
  assert "invalid_operation_mode:banana" in detail["blocking_reasons"]


def test_rtlops94_operation_scope_blocks_unresolved_max_active_symbols_without_typeerror(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  bot_id, _pool_ids = _create_scope_ready_bot(_module, client, headers, monkeypatch, universe=["BTCUSDT"], max_live_symbols=1)

  original_scope = _module.store.bot_scope_eligibility_or_404(bot_id)

  def _scope_with_unresolved_cap(target_bot_id: str) -> dict:
    scope = dict(original_scope)
    scope["bot_id"] = target_bot_id
    scope["max_active_symbols"] = None
    return scope

  monkeypatch.setattr(_module.store, "bot_scope_eligibility_or_404", _scope_with_unresolved_cap)

  gate = _module.store.bot_operation_scope_gate(bot_id, mode="paper", requested_symbols=["BTCUSDT"])
  assert gate["is_blocking"] is True
  assert "max_active_symbols_unresolved" in gate["blocking_reasons"]

  payload = {
    "family": "spot",
    "environment": "paper",
    "mode": "paper",
    "bot_id": bot_id,
    "symbol": "BTCUSDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.01,
    "price": 50000.0,
    "market_snapshot": {"best_bid": 49990.0, "best_ask": 50010.0, "last": 50000.0, "mark": 50000.0},
  }
  res = client.post("/api/v1/execution/preflight", headers=headers, json=payload)
  assert res.status_code == 400
  detail = res.json()["detail"]
  assert detail["code"] == "operation_scope_blocked"
  assert "max_active_symbols_unresolved" in detail["blocking_reasons"]


def test_bot_signal_consolidation_fails_closed_when_selected_strategy_signal_is_unresolved(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  pool_ids = _eligible_pool_ids(client, headers)[:1]
  assert len(pool_ids) == 1

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Consolidation Fail Closed",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = []
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  consolidation_res = client.get(f"/api/v1/bots/{bot_id}/signal-consolidation", headers=headers)
  assert consolidation_res.status_code == 200, consolidation_res.text
  consolidation = consolidation_res.json()["signal_consolidation"]
  assert consolidation["status"] == "error"
  assert "selected_strategy_signal_unresolved" in consolidation["reason_codes"]
  item = consolidation["items"][0]
  assert item["status"] == "error"
  assert item["net_action"] is None
  assert any(issue["reason_code"] == "selected_strategy_signal_unresolved" for issue in item["errors"])
  assert consolidation["net_decision_by_symbol"] == {}

  runtime_res = client.get(f"/api/v1/bots/{bot_id}/runtime", headers=headers)
  assert runtime_res.status_code == 200, runtime_res.text
  runtime = runtime_res.json()["runtime"]
  assert runtime["status"] == "error"
  assert "signal_consolidation_invalid" in runtime["reason_codes"]
  assert runtime["net_decision_by_symbol"] == {}
  runtime_item = runtime["items"][0]
  assert runtime_item["status"] == "error"
  assert runtime_item["decision_action"] is None
  assert any(issue["reason_code"] == "selected_strategy_signal_unresolved" for issue in runtime_item["errors"])

  lifecycle_res = client.get(f"/api/v1/bots/{bot_id}/lifecycle", headers=headers)
  assert lifecycle_res.status_code == 200, lifecycle_res.text
  lifecycle = lifecycle_res.json()["lifecycle"]
  assert lifecycle["contract_version"] == "rtlops80/v1"
  assert lifecycle["runtime_contract_version"] == "rtlops77/v1"
  assert lifecycle["status"] == "error"
  assert lifecycle["execution_ready"] is False
  assert lifecycle["allowed_trade_symbols"] == []
  assert lifecycle["rejected_trade_symbols"] == []
  assert lifecycle["progressing_symbols"] == []
  assert lifecycle["blocked_symbols"] == []
  assert lifecycle["progression_allowed"] is False
  assert "runtime_execution_not_ready" in lifecycle["reason_codes"]
  lifecycle_item = lifecycle["items"][0]
  assert lifecycle_item["lifecycle_state"] == "inactive"
  assert lifecycle_item["progression_allowed"] is False
  assert lifecycle_item["status"] == "valid"


def test_bot_runtime_prioritizes_trade_subset_when_trade_decisions_exceed_live_cap(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Runtime Guardrails Live Cap",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["ETHUSDT", "BTCUSDT"],
      "max_live_symbols": 1,
      "max_positions": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  runtime_res = client.get(f"/api/v1/bots/{bot_id}/runtime", headers=headers)
  assert runtime_res.status_code == 200, runtime_res.text
  runtime = runtime_res.json()["runtime"]
  assert runtime["contract_version"] == "rtlops77/v1"
  assert runtime["status"] == "warning"
  assert "trade_decisions_exceed_live_cap" in runtime["reason_codes"]
  assert runtime["caps"] == {
    "configured_symbols_count": 2,
    "trade_decisions_count": 2,
    "max_live_symbols": 1,
    "max_positions": 2,
  }
  assert runtime["guardrails"] == {
    "status": "warning",
    "execution_ready": True,
    "allowed_trade_symbols": ["ETHUSDT"],
    "rejected_trade_symbols": ["BTCUSDT"],
    "reason_codes": ["trade_decisions_exceed_live_cap"],
    "errors": [
      "El runtime derivo 2 decisiones trade pero el cap live permitido es 1; se prioriza el subset ejecutable por orden canonico de symbols."
    ],
    "prioritization_criterion": "symbol_order",
  }
  assert runtime["errors"] == [
    "El runtime derivo 2 decisiones trade pero el cap live permitido es 1; se prioriza el subset ejecutable por orden canonico de symbols."
  ]
  assert len(runtime["net_decision_by_symbol"]) == 2
  items = {str(item["symbol"]): item for item in runtime["items"]}
  assert items["ETHUSDT"]["status"] == "valid"
  assert items["ETHUSDT"]["errors"] == []
  assert items["BTCUSDT"]["status"] == "error"
  assert any(issue["reason_code"] == "trade_decisions_exceed_live_cap" for issue in items["BTCUSDT"]["errors"])
  assert any("priority_rank=2" in str(issue["message"] or "") for issue in items["BTCUSDT"]["errors"])

  lifecycle_res = client.get(f"/api/v1/bots/{bot_id}/lifecycle", headers=headers)
  assert lifecycle_res.status_code == 200, lifecycle_res.text
  lifecycle = lifecycle_res.json()["lifecycle"]
  assert lifecycle["contract_version"] == "rtlops80/v1"
  assert lifecycle["runtime_contract_version"] == "rtlops77/v1"
  assert lifecycle["policy_state"]["mode"] == "paper"
  assert lifecycle["policy_state"]["status"] == "active"
  assert lifecycle["status"] == "warning"
  assert lifecycle["execution_ready"] is True
  assert lifecycle["allowed_trade_symbols"] == ["ETHUSDT"]
  assert lifecycle["rejected_trade_symbols"] == ["BTCUSDT"]
  assert lifecycle["progressing_symbols"] == ["ETHUSDT"]
  assert lifecycle["blocked_symbols"] == []
  assert lifecycle["progression_allowed"] is True
  assert lifecycle["api"]["lifecycle_path"] == f"/api/v1/bots/{bot_id}/lifecycle"
  lifecycle_items = {str(item["symbol"]): item for item in lifecycle["items"]}
  assert lifecycle_items["ETHUSDT"]["lifecycle_state"] == "progressing"
  assert lifecycle_items["ETHUSDT"]["progression_allowed"] is True
  assert lifecycle_items["ETHUSDT"]["status"] == "valid"
  assert lifecycle_items["ETHUSDT"]["errors"] == []
  assert lifecycle_items["BTCUSDT"]["lifecycle_state"] == "rejected"
  assert lifecycle_items["BTCUSDT"]["progression_allowed"] is False
  assert lifecycle_items["BTCUSDT"]["status"] == "warning"
  assert any(issue["reason_code"] == "trade_decisions_exceed_live_cap" for issue in lifecycle_items["BTCUSDT"]["errors"])


def test_bot_lifecycle_blocks_allowed_symbols_when_policy_state_is_paused(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  pool_ids = _eligible_pool_ids(client, headers)[:1]
  assert len(pool_ids) == 1

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Lifecycle Policy Pause",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "max_positions": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  policy_patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/policy-state",
    headers=headers,
    json={"status": "paused"},
  )
  assert policy_patch_res.status_code == 200, policy_patch_res.text

  lifecycle_res = client.get(f"/api/v1/bots/{bot_id}/lifecycle", headers=headers)
  assert lifecycle_res.status_code == 200, lifecycle_res.text
  lifecycle = lifecycle_res.json()["lifecycle"]
  assert lifecycle["policy_state"]["status"] == "paused"
  assert lifecycle["execution_ready"] is True
  assert lifecycle["status"] == "error"
  assert lifecycle["allowed_trade_symbols"] == ["BTCUSDT"]
  assert lifecycle["rejected_trade_symbols"] == []
  assert lifecycle["progressing_symbols"] == []
  assert lifecycle["blocked_symbols"] == ["BTCUSDT"]
  assert lifecycle["progression_allowed"] is False
  assert "bot_status_paused" in lifecycle["reason_codes"]
  assert any("policy_state.status=paused" in str(item) for item in (lifecycle.get("errors") or []))
  lifecycle_item = lifecycle["items"][0]
  assert lifecycle_item["symbol"] == "BTCUSDT"
  assert lifecycle_item["lifecycle_state"] == "blocked"
  assert lifecycle_item["progression_allowed"] is False
  assert lifecycle_item["status"] == "error"
  assert any(issue["reason_code"] == "bot_status_paused" for issue in lifecycle_item["errors"])


def test_bot_lifecycle_operational_surface_pauses_allowed_symbols_without_opening_live_lateral(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Lifecycle Operativo",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["ETHUSDT", "BTCUSDT"],
      "max_live_symbols": 1,
      "max_positions": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  base_res = client.get(f"/api/v1/bots/{bot_id}/lifecycle-operational", headers=headers)
  assert base_res.status_code == 200, base_res.text
  base_operational = base_res.json()["lifecycle_operational"]
  assert base_operational["contract_version"] == "rtlops81/v1"
  assert base_operational["lifecycle_contract_version"] == "rtlops80/v1"
  assert base_operational["lifecycle_operational_by_symbol"] == {}
  assert base_operational["progressing_symbols"] == ["ETHUSDT"]
  assert base_operational["blocked_symbols"] == []
  assert base_operational["api"]["lifecycle_operational_path"] == f"/api/v1/bots/{bot_id}/lifecycle-operational"

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/lifecycle-operational",
    headers=headers,
    json={
      "lifecycle_operational_by_symbol": {
        "ETHUSDT": "paused",
      },
    },
  )
  assert patch_res.status_code == 200, patch_res.text
  operational = patch_res.json()["lifecycle_operational"]
  assert operational["lifecycle_operational_by_symbol"] == {"ETHUSDT": "paused"}
  assert operational["progressing_symbols"] == []
  assert operational["blocked_symbols"] == ["ETHUSDT"]
  assert operational["progression_allowed"] is False
  assert operational["status"] == "warning"
  assert "symbol_operational_paused" in operational["reason_codes"]
  items = {str(item["symbol"]): item for item in operational["items"]}
  assert items["ETHUSDT"]["base_lifecycle_state"] == "progressing"
  assert items["ETHUSDT"]["operational_status"] == "paused"
  assert items["ETHUSDT"]["lifecycle_state"] == "blocked"
  assert items["ETHUSDT"]["progression_allowed"] is False
  assert items["ETHUSDT"]["status"] == "warning"
  assert any(issue["reason_code"] == "symbol_operational_paused" for issue in items["ETHUSDT"]["errors"])
  assert items["BTCUSDT"]["base_lifecycle_state"] == "rejected"
  assert items["BTCUSDT"]["lifecycle_state"] == "rejected"
  assert items["BTCUSDT"]["operational_status"] == "active"

  detail_res = client.get(f"/api/v1/bots/{bot_id}", headers=headers)
  assert detail_res.status_code == 200, detail_res.text
  detail_bot = detail_res.json()["bot"]
  assert detail_bot["lifecycle_operational"]["contract_version"] == "rtlops81/v1"
  assert detail_bot["lifecycle_operational"]["lifecycle_operational_by_symbol"] == {"ETHUSDT": "paused"}


def test_bot_runtime_flags_legacy_live_cap_above_max_positions_fail_closed(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Runtime Legacy Caps",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT", "ETHUSDT"],
      "max_live_symbols": 2,
      "max_positions": 2,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  eligibility_res = client.patch(
    f"/api/v1/bots/{bot_id}/symbol-strategy-eligibility",
    headers=headers,
    json={
      "strategy_eligibility_by_symbol": {
        "BTCUSDT": [pool_ids[0]],
        "ETHUSDT": [pool_ids[1]],
      },
    },
  )
  assert eligibility_res.status_code == 200, eligibility_res.text

  selection_res = client.patch(
    f"/api/v1/bots/{bot_id}/strategy-selection",
    headers=headers,
    json={
      "strategy_selection_by_symbol": {
        "BTCUSDT": pool_ids[0],
        "ETHUSDT": pool_ids[1],
      },
    },
  )
  assert selection_res.status_code == 200, selection_res.text

  rows = _module.store.load_bots()
  for row in rows:
    if str(row.get("id") or "") == bot_id:
      row["max_positions"] = 1
      break
  _module.store.save_bots(rows)

  strategy_rows = [dict(row) for row in _module.store.list_strategies()]
  for row in strategy_rows:
    if str(row.get("id") or "") == pool_ids[0]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["trend", "breakout"]
    elif str(row.get("id") or "") == pool_ids[1]:
      row["enabled_for_trading"] = True
      row["params"] = {}
      row["tags"] = ["mean_reversion", "range"]
  monkeypatch.setattr(_module.store, "list_strategies", lambda: strategy_rows)

  runtime_res = client.get(f"/api/v1/bots/{bot_id}/runtime", headers=headers)
  assert runtime_res.status_code == 200, runtime_res.text
  runtime = runtime_res.json()["runtime"]
  assert runtime["status"] == "error"
  assert "live_cap_exceeds_max_positions" in runtime["reason_codes"]
  assert runtime["caps"] == {
    "configured_symbols_count": 2,
    "trade_decisions_count": 2,
    "max_live_symbols": 2,
    "max_positions": 1,
  }
  assert runtime["guardrails"]["status"] == "error"
  assert runtime["guardrails"]["execution_ready"] is False
  assert runtime["guardrails"]["allowed_trade_symbols"] == []
  assert runtime["guardrails"]["rejected_trade_symbols"] == ["BTCUSDT", "ETHUSDT"]
  assert runtime["guardrails"]["prioritization_criterion"] is None
  assert "live_cap_exceeds_max_positions" in runtime["guardrails"]["reason_codes"]
  assert any("max_live_symbols=2 no puede superar max_positions=1" in err for err in runtime["guardrails"]["errors"])


def test_bot_multi_symbol_patch_validates_limits_and_archive_guard(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RATE_LIMIT_EXPENSIVE_REQ_PER_MIN", "20")
  _module, client = _build_app(tmp_path, monkeypatch)
  _seed_bot_registry_catalog(_module)
  large_symbols = _seed_large_spot_universe(_module)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  pool_ids = _eligible_pool_ids(client, headers)[:2]
  assert len(pool_ids) == 2

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Multi Symbol Patch",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  duplicate_res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"symbols": ["BTCUSDT", "BTCUSDT"]},
  )
  assert duplicate_res.status_code == 400, duplicate_res.text
  assert "duplicados" in str(duplicate_res.json().get("detail") or "")

  max_active_res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"symbols": ["BTCUSDT"], "max_active_symbols": 2},
  )
  assert max_active_res.status_code == 400, max_active_res.text
  assert "max_active_symbols" in str(max_active_res.json().get("detail") or "")
  assert "cantidad de simbolos configurados" in str(max_active_res.json().get("detail") or "")

  too_many_res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"universe_name": "core_spot_usdt", "symbols": large_symbols, "max_active_symbols": 12},
  )
  assert too_many_res.status_code == 400, too_many_res.text
  assert "12 simbolos configurados" in str(too_many_res.json().get("detail") or "")

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "max_active_symbols": 2},
  )
  assert patch_res.status_code == 200, patch_res.text
  multi_symbol = patch_res.json()["multi_symbol"]
  assert multi_symbol["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
  assert int(multi_symbol["configured_symbols_count"]) == 3
  assert int(multi_symbol["max_active_symbols"]) == 2
  assert multi_symbol["status"] == "valid"

  archive_res = client.post(f"/api/v1/bots/{bot_id}/archive", headers=headers)
  assert archive_res.status_code == 200, archive_res.text

  archived_patch_res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"max_active_symbols": 1},
  )
  assert archived_patch_res.status_code == 409, archived_patch_res.text
  assert "archivado" in str(archived_patch_res.json().get("detail") or "").lower()


def test_bot_multi_symbol_patch_rejects_live_cap_above_max_positions(tmp_path: Path, monkeypatch) -> None:
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
      "display_name": "Bot Multi Symbol Config Guard",
      "domain_type": "spot",
      "universe_name": "core_spot_usdt",
      "universe": ["BTCUSDT"],
      "max_live_symbols": 1,
      "max_positions": 1,
      "pool_strategy_ids": pool_ids,
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot_id = str(create_res.json()["bot"]["id"])

  res = client.patch(
    f"/api/v1/bots/{bot_id}/multi-symbol",
    headers=headers,
    json={"symbols": ["BTCUSDT", "ETHUSDT"], "max_active_symbols": 2},
  )
  assert res.status_code == 400, res.text
  assert "max_active_symbols no puede superar max_positions" in str(res.json().get("detail") or "")


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
