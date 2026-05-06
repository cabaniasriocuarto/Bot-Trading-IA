from __future__ import annotations

from pathlib import Path

import pandas as pd

from rtlab_core.backtest import BacktestCatalogDB, CostModelResolver, FeeProvider, SpreadModel


def _bounce_df(rows: int = 120) -> pd.DataFrame:
    base = 100.0
    close = [base + (1.0 if i % 2 else 0.0) for i in range(rows)]
    return pd.DataFrame({"close": close})


def test_spread_model_roll_estimator_when_no_explicit_and_no_bbo() -> None:
    params = SpreadModel.build_params(
        market="crypto",
        explicit_spread_bps=0.0,
        bbo_spread_bps=None,
        is_perp=False,
        df=_bounce_df(),
    )
    assert params["mode"] == "roll"
    assert float(params["used_bps"]) > 0
    assert isinstance(params.get("roll"), dict)


def test_cost_model_resolver_persists_snapshots_with_roll_spread(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    resolver = CostModelResolver(catalog=db, policies_root=Path("config/policies"))
    out = resolver.resolve(
        exchange="binance",
        market="crypto",
        symbol="BTCUSDT",
        costs={"fees_bps": 0.0, "spread_bps": 0.0, "slippage_bps": 3.0, "funding_bps": 0.0},
        df=_bounce_df(),
        is_perp=False,
    )
    assert str(out.get("fee_snapshot_id") or "").startswith("FS-")
    assert str(out.get("funding_snapshot_id") or "").startswith("FN-")
    assert (out.get("spread_model_params") or {}).get("mode") in {"roll", "static"}


def test_cost_model_uses_exchange_fee_fallback_for_bybit(tmp_path: Path) -> None:
    policies_root = tmp_path / "config" / "policies"
    policies_root.mkdir(parents=True, exist_ok=True)
    policies_root.joinpath("fees.yaml").write_text(
        """
fees:
  fee_snapshot_ttl_hours: 6
  funding_snapshot_ttl_minutes: 60
  default_fee_model_if_api_missing:
    maker_fee: 0.0002
    taker_fee: 0.0004
  per_exchange_defaults:
    bybit:
      maker_fee: 0.0011
      taker_fee: 0.0022
""".strip(),
        encoding="utf-8",
    )
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    resolver = CostModelResolver(catalog=db, policies_root=policies_root)
    out = resolver.resolve(
        exchange="bybit",
        market="crypto",
        symbol="BTCUSDT",
        costs={"fees_bps": 0.0, "spread_bps": 0.0, "slippage_bps": 2.0, "funding_bps": 0.0},
        df=_bounce_df(),
        is_perp=False,
    )
    fs = out.get("fee_snapshot") if isinstance(out.get("fee_snapshot"), dict) else {}
    assert abs(float(fs.get("maker_fee") or 0.0) - 0.0011) < 1e-12
    assert abs(float(fs.get("taker_fee") or 0.0) - 0.0022) < 1e-12
    assert str(fs.get("source") or "") == "policy_fallback"


def test_fee_provider_preserves_binance_tax_and_special_commission_components(tmp_path: Path, monkeypatch) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    monkeypatch.setenv("BINANCE_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "test-secret")

    class _Resp:
        ok = True
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {
                "symbol": "BTCUSDT",
                "standardCommission": {"maker": "0.00000040", "taker": "0.00000050", "buyer": "0.00000010", "seller": "0.00000010"},
                "taxCommission": {"maker": "0.00000128", "taker": "0.00000130", "buyer": "0.00000100", "seller": "0.00000100"},
                "specialCommission": {"maker": "0.04000000", "taker": "0.05000000", "buyer": "0.01000000", "seller": "0.01000000"},
            }

    class _Session:
        def get(self, url, headers=None, timeout=0):
            assert "/api/v3/account/commission" in url
            return _Resp()

    provider = FeeProvider(catalog=db, policies_root=Path("config/policies"), session=_Session())
    snapshot = provider.get_or_create_snapshot(exchange="binance", market="crypto", symbol="BTCUSDT")

    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    fetch = payload.get("exchange_fetch") if isinstance(payload.get("exchange_fetch"), dict) else {}
    components = fetch.get("commission_components") if isinstance(fetch.get("commission_components"), dict) else {}

    assert snapshot["source"] == "exchange_api"
    assert abs(float(snapshot["maker_fee"]) - 0.00000040) < 1e-12
    assert abs(float(snapshot["taker_fee"]) - 0.00000050) < 1e-12
    assert components["tax_commission"]["label"] == "taxCommission"
    assert components["tax_commission"]["rates"]["taker"] == 0.00000130
    assert components["special_commission"]["label"] == "specialCommission"
    assert components["special_commission"]["rates"]["seller"] == 0.01000000
    assert components["tax_commission"]["estimated_vs_realized"] == "rate_metadata"


def test_cost_model_fetches_bybit_funding_when_perp(tmp_path: Path, monkeypatch) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    resolver = CostModelResolver(catalog=db, policies_root=Path("config/policies"))

    class _Resp:
        ok = True
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {
                "retCode": 0,
                "result": {"list": [{"fundingRate": "0.0005"}]},
            }

    def _fake_get(url, params=None, timeout=0):
        return _Resp()

    monkeypatch.setattr(resolver.funding_provider._session, "get", _fake_get)

    out = resolver.resolve(
        exchange="bybit",
        market="crypto",
        symbol="BTCUSDT",
        costs={"fees_bps": 0.0, "spread_bps": 0.0, "slippage_bps": 2.0, "funding_bps": 0.0},
        df=_bounce_df(),
        is_perp=True,
    )
    fn = out.get("funding_snapshot") if isinstance(out.get("funding_snapshot"), dict) else {}
    assert str(fn.get("source") or "") == "exchange_api"
    assert abs(float(fn.get("funding_rate") or 0.0) - 0.0005) < 1e-12
    assert abs(float(fn.get("funding_bps") or 0.0) - 5.0) < 1e-12
