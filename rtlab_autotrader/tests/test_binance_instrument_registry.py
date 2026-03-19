from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from rtlab_core.instruments.registry import (
    BinanceInstrumentRegistryService,
    clear_instrument_registry_policy_cache,
    derive_margin_catalog_from_spot,
    diff_snapshot_items,
    instrument_registry_policy,
    load_instrument_registry_bundle,
    parse_coinm_exchange_info,
    parse_spot_exchange_info,
    parse_usdm_exchange_info,
)
from rtlab_core.universe.service import (
    InstrumentUniverseService,
    clear_universes_policy_cache,
    load_universes_bundle,
)


def _spot_exchange_info() -> dict:
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "permissions": ["SPOT", "MARGIN"],
                "permissionSets": [["SPOT", "MARGIN"]],
                "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": True,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "1000", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.0", "applyToMarket": True, "avgPriceMins": 5},
                ],
            },
            {
                "symbol": "ETHUPUSDT",
                "status": "TRADING",
                "baseAsset": "ETHUP",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
                "permissionSets": [["SPOT"]],
                "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": False,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "100000", "stepSize": "0.01"},
                ],
            },
        ],
    }


def _usdm_exchange_info() -> dict:
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "contractType": "PERPETUAL",
                "triggerProtect": "0.0500",
                "deliveryDate": 4133404800000,
                "onboardDate": 1704067200000,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1500", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ],
    }


def _coinm_exchange_info(*, delivery_ms: int = 4133404800000, contract_type: str = "PERPETUAL") -> dict:
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": "BTCUSD_PERP",
                "pair": "BTCUSD",
                "status": "TRADING",
                "contractStatus": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USD",
                "marginAsset": "BTC",
                "contractType": contract_type,
                "triggerProtect": "0.0500",
                "deliveryDate": delivery_ms,
                "onboardDate": 1704067200000,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                    {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                ],
            }
        ],
    }


def _repo_policy_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_parse_spot_exchange_info_extracts_filters_permissions_and_eligibility() -> None:
    items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())

    assert len(items) == 2
    btc = next(item for item in items if item["symbol"] == "BTCUSDT")
    assert btc["live_eligible"] is True
    assert btc["paper_eligible"] is True
    assert btc["filter_summary"]["price_filter"]["tick_size"] == "0.01"
    assert btc["filter_summary"]["min_notional"]["min_notional"] == "10.0"
    assert btc["permission_summary"]["permissions"] == ["SPOT", "MARGIN"]
    assert btc["permission_summary"]["permission_sets"] == [["SPOT", "MARGIN"]]


def test_policy_bundles_expose_distinct_source_hash_and_policy_hash() -> None:
    clear_instrument_registry_policy_cache()
    clear_universes_policy_cache()

    instrument_bundle = load_instrument_registry_bundle()
    universes_bundle = load_universes_bundle()

    instrument_path = Path(instrument_bundle["path"])
    universes_path = Path(universes_bundle["path"])

    expected_instrument_source_hash = hashlib.sha256(instrument_path.read_bytes()).hexdigest()
    expected_universes_source_hash = hashlib.sha256(universes_path.read_bytes()).hexdigest()
    expected_instrument_policy_hash = hashlib.sha256(
        json.dumps(instrument_bundle["instrument_registry"], ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    expected_universes_policy_hash = hashlib.sha256(
        json.dumps(universes_bundle["universes_bundle"], ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    assert instrument_bundle["source"] == "config/policies/instrument_registry.yaml"
    assert instrument_bundle["source_hash"] == expected_instrument_source_hash
    assert instrument_bundle["policy_hash"] == expected_instrument_policy_hash
    assert instrument_bundle["policy_hash"] != instrument_bundle["source_hash"]
    assert instrument_bundle["errors"] == []

    assert universes_bundle["source"] == "config/policies/universes.yaml"
    assert universes_bundle["source_hash"] == expected_universes_source_hash
    assert universes_bundle["policy_hash"] == expected_universes_policy_hash
    assert universes_bundle["policy_hash"] != universes_bundle["source_hash"]
    assert universes_bundle["errors"] == []


def test_parse_usdm_and_coinm_exchange_info_extract_metadata() -> None:
    usdm_items = parse_usdm_exchange_info(_usdm_exchange_info(), environment="testnet", policy=instrument_registry_policy())
    coinm_items = parse_coinm_exchange_info(_coinm_exchange_info(), environment="testnet", policy=instrument_registry_policy())

    assert usdm_items[0]["contract_type"] == "PERPETUAL"
    assert usdm_items[0]["filter_summary"]["market_lot_size"]["step_size"] == "0.001"
    assert usdm_items[0]["testnet_eligible"] is True
    assert coinm_items[0]["margin_asset"] == "BTC"
    assert coinm_items[0]["filter_summary"]["trigger_protect"]["value"] == "0.0500"
    assert coinm_items[0]["testnet_eligible"] is True


def test_instrument_registry_bundle_fails_closed_when_yaml_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)
    (root_policies / "universes.yaml").write_text(
        _repo_policy_path("config", "policies", "universes.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    clear_instrument_registry_policy_cache()
    bundle = load_instrument_registry_bundle(repo_root=repo_root, explicit_root=root_policies)

    assert bundle["source"] == "default_fail_closed_minimal"
    assert bundle["source_hash"] == ""
    assert isinstance(bundle["policy_hash"], str) and len(bundle["policy_hash"]) == 64
    assert "no existe" in " ".join(bundle["errors"]).lower()
    assert bundle["instrument_registry"]["sync"]["manual_enabled"] is False
    assert bundle["instrument_registry"]["sync"]["startup_enabled"] is False
    assert bundle["instrument_registry"]["environments"]["spot"]["live"] is False
    assert bundle["instrument_registry"]["diffing"]["symbol_count_block_delta_pct"] == 0.0


def test_universes_bundle_fails_closed_when_yaml_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)
    (root_policies / "instrument_registry.yaml").write_text(
        _repo_policy_path("config", "policies", "instrument_registry.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    clear_universes_policy_cache()
    bundle = load_universes_bundle(repo_root=repo_root, explicit_root=root_policies)

    assert bundle["source"] == "default_fail_closed_minimal"
    assert bundle["source_hash"] == ""
    assert isinstance(bundle["policy_hash"], str) and len(bundle["policy_hash"]) == 64
    assert "no existe" in " ".join(bundle["errors"]).lower()
    assert bundle["universes_bundle"]["universes"] == {}
    assert bundle["universes_bundle"]["globals"]["leveraged_token_suffixes"] == []


def test_derive_margin_from_spot_permissions_and_capability() -> None:
    spot_items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    margin_items = derive_margin_catalog_from_spot(
        spot_items,
        environment="live",
        policy=instrument_registry_policy(),
        account_capability={"can_margin": True},
    )

    assert [item["symbol"] for item in margin_items] == ["BTCUSDT"]
    assert margin_items[0]["permission_summary"]["account_margin_capable"] is True
    assert margin_items[0]["live_eligible"] is True


def test_policy_bundles_prefer_selected_root_and_expose_divergence_warning(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    nested_policies = repo_root / "rtlab_autotrader" / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)
    nested_policies.mkdir(parents=True, exist_ok=True)

    root_instrument = _load_yaml(_repo_policy_path("config", "policies", "instrument_registry.yaml"))
    nested_instrument = _load_yaml(_repo_policy_path("config", "policies", "instrument_registry.yaml"))
    nested_instrument["instrument_registry"]["sync"]["manual_enabled"] = False

    root_universes = _load_yaml(_repo_policy_path("config", "policies", "universes.yaml"))
    nested_universes = _load_yaml(_repo_policy_path("config", "policies", "universes.yaml"))
    nested_universes["universes"]["core_spot_usdt"]["quote_assets"] = ["BUSD"]

    (root_policies / "instrument_registry.yaml").write_text(yaml.safe_dump(root_instrument, sort_keys=False), encoding="utf-8")
    (nested_policies / "instrument_registry.yaml").write_text(yaml.safe_dump(nested_instrument, sort_keys=False), encoding="utf-8")
    (root_policies / "universes.yaml").write_text(yaml.safe_dump(root_universes, sort_keys=False), encoding="utf-8")
    (nested_policies / "universes.yaml").write_text(yaml.safe_dump(nested_universes, sort_keys=False), encoding="utf-8")

    clear_instrument_registry_policy_cache()
    clear_universes_policy_cache()
    instrument_bundle = load_instrument_registry_bundle(repo_root=repo_root, explicit_root=root_policies)
    universes_bundle = load_universes_bundle(repo_root=repo_root, explicit_root=root_policies)

    assert instrument_bundle["source_hash"] == hashlib.sha256((root_policies / "instrument_registry.yaml").read_bytes()).hexdigest()
    assert universes_bundle["source_hash"] == hashlib.sha256((root_policies / "universes.yaml").read_bytes()).hexdigest()
    assert instrument_bundle["instrument_registry"]["sync"]["manual_enabled"] is True
    assert universes_bundle["universes_bundle"]["universes"]["core_spot_usdt"]["quote_assets"] == ["USDT"]
    assert instrument_bundle["warnings"]
    assert universes_bundle["warnings"]
    assert instrument_bundle["fallback_used"] is False
    assert universes_bundle["fallback_used"] is False


def test_coinm_delivery_contract_near_expiry_not_live_eligible() -> None:
    near_expiry_payload = _coinm_exchange_info(delivery_ms=1, contract_type="CURRENT_QUARTER")
    items = parse_coinm_exchange_info(near_expiry_payload, environment="live", policy=instrument_registry_policy())

    assert items[0]["live_eligible"] is False
    assert "delivery_too_close_or_expired" in items[0]["consistency_errors"]


def test_diff_snapshot_items_detects_blocking_removals() -> None:
    before = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    after = [before[1]]

    diff = diff_snapshot_items(before, after, policy=instrument_registry_policy())

    assert diff["symbols_removed"] == 1
    assert diff["removed_live_eligible_count"] == 1
    assert diff["severity"] == "BLOCK"


def test_universe_service_filters_by_family_and_excludes_leveraged_tokens(tmp_path: Path) -> None:
    service = BinanceInstrumentRegistryService(db_path=tmp_path / "instrument_registry.sqlite3")
    policy_hash = str(service.policy_source().get("policy_hash") or "")

    spot_items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    margin_items = derive_margin_catalog_from_spot(
        spot_items,
        environment="live",
        policy=instrument_registry_policy(),
        account_capability={"can_margin": True},
    )
    usdm_items = parse_usdm_exchange_info(_usdm_exchange_info(), environment="live", policy=instrument_registry_policy())
    coinm_items = parse_coinm_exchange_info(_coinm_exchange_info(), environment="live", policy=instrument_registry_policy())

    service.db.save_snapshot(
        family="spot",
        environment="live",
        source_endpoint="https://api.binance.com/api/v3/exchangeInfo",
        raw_payload=_spot_exchange_info(),
        items=spot_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="margin",
        environment="live",
        source_endpoint="derived:spot:/api/v3/exchangeInfo",
        raw_payload={"derived": True},
        items=margin_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="usdm_futures",
        environment="live",
        source_endpoint="https://fapi.binance.com/fapi/v1/exchangeInfo",
        raw_payload=_usdm_exchange_info(),
        items=usdm_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="coinm_futures",
        environment="live",
        source_endpoint="https://dapi.binance.com/dapi/v1/exchangeInfo",
        raw_payload=_coinm_exchange_info(),
        items=coinm_items,
        policy_hash=policy_hash,
    )
    service.db.save_capability_snapshot(
        family="margin",
        environment="live",
        can_read_market_data=True,
        can_trade=True,
        can_margin=True,
        can_user_data=True,
        can_testnet=False,
        capability_source="test",
        notes={},
    )

    universes = InstrumentUniverseService(service).summary()["items"]
    universes_summary = InstrumentUniverseService(service).summary()
    spot_universe = next(item for item in universes if item["name"] == "core_spot_usdt")
    margin_universe = next(item for item in universes if item["name"] == "core_margin_usdt")
    usdm_universe = next(item for item in universes if item["name"] == "core_usdm_perps")

    assert spot_universe["size"] == 1
    assert spot_universe["sample_symbols"] == ["BTCUSDT"]
    assert margin_universe["size"] == 1
    assert usdm_universe["size"] == 1
    assert service.policy_source()["source_hash"]
    assert service.policy_source()["policy_hash"]
    assert universes_summary["policy_source"]["source_hash"]
    assert universes_summary["policy_source"]["policy_hash"]
    assert universes_summary["policy_source"]["errors"] == []
