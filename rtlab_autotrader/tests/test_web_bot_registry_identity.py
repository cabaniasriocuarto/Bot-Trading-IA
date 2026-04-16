from __future__ import annotations

from pathlib import Path

from test_web_live_ready import _auth_headers, _build_app, _login


def test_bot_registry_identity_crud_and_filters(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Momentum Spot",
      "alias": "momentum-a",
      "description": "Bot de registry para validar identidad editable.",
      "domain_type": "spot",
      "capital_base_usd": 25000,
      "max_total_exposure_pct": 70,
      "max_asset_exposure_pct": 25,
      "risk_profile": "medium",
      "risk_per_trade_pct": 0.5,
      "max_daily_loss_pct": 3.0,
      "max_drawdown_pct": 15.0,
      "max_positions": 8,
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
      "capital_base_usd": 40000,
      "max_total_exposure_pct": 85,
      "max_asset_exposure_pct": 35,
      "risk_profile": "aggressive",
      "risk_per_trade_pct": 1.0,
      "max_daily_loss_pct": 5.0,
      "max_drawdown_pct": 22.0,
      "max_positions": 12,
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
  ]

  for index, (payload, expected) in enumerate(invalid_cases):
    case_tmp = tmp_path / f"case_{index}"
    case_tmp.mkdir(parents=True, exist_ok=True)
    _module, client = _build_app(case_tmp, monkeypatch)
    admin_token = _login(client, "Wadmin", "moroco123")
    headers = _auth_headers(admin_token)
    res = client.post("/api/v1/bots", headers=headers, json=payload)
    assert res.status_code == 400, res.text
    assert expected in str(res.json().get("detail") or "")


def test_bot_registry_base_config_defaults_for_legacy_shape(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "display_name": "Bot Legacy Compatible",
      "domain_type": "spot",
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
