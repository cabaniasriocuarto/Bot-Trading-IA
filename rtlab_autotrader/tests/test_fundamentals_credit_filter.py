from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from rtlab_core.backtest import BacktestCatalogDB
import rtlab_core.fundamentals.credit_filter as credit_filter_mod
from rtlab_core.fundamentals import FundamentalsCreditFilter


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_fundamentals_not_applicable_market_allows_trade(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    filt = FundamentalsCreditFilter(catalog=db, policies_root=Path("config/policies"))
    out = filt.evaluate(
        exchange="binance",
        market="crypto",
        symbol="BTCUSDT",
        instrument_type="other",
        target_mode="backtest",
        asof_date=_now_iso(),
        source="test",
        source_id="crypto:BTCUSDT",
        raw_payload={"market": "crypto", "symbol": "BTCUSDT"},
    )
    assert out["enabled"] is True
    assert out["enforced"] is False
    assert out["allow_trade"] is True
    assert out["fund_status"] == "NOT_APPLICABLE"
    assert str(out.get("snapshot_id") or "").startswith("FD-")
    snap = db.latest_valid_fundamentals_snapshot(exchange="binance", market="crypto", symbol="BTCUSDT")
    assert snap is not None
    assert snap["fund_status"] == "NOT_APPLICABLE"


def test_fundamentals_fail_closed_when_required_data_missing(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    filt = FundamentalsCreditFilter(catalog=db, policies_root=Path("config/policies"))
    out = filt.evaluate(
        exchange="alpaca",
        market="equities",
        symbol="AAPL",
        instrument_type="common",
        target_mode="backtest",
        asof_date=_now_iso(),
        source="test",
        source_id="equities:AAPL",
        raw_payload={"market": "equities", "symbol": "AAPL"},
    )
    assert out["enforced"] is True
    assert out["allow_trade"] is True
    assert out["fund_status"] == "UNKNOWN"
    assert out["promotion_blocked"] is True
    assert "fundamentals_missing" in list(out.get("warnings") or [])
    codes = {str((r or {}).get("code") or "") for r in out.get("explain") or [] if isinstance(r, dict)}
    assert "DATA_MISSING_BALANCE" in codes


def test_fundamentals_live_fail_closed_when_required_data_missing(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    filt = FundamentalsCreditFilter(catalog=db, policies_root=Path("config/policies"))
    out = filt.evaluate(
        exchange="alpaca",
        market="equities",
        symbol="AAPL",
        instrument_type="common",
        target_mode="live",
        asof_date=_now_iso(),
        source="test",
        source_id="equities:AAPL",
        raw_payload={"market": "equities", "symbol": "AAPL"},
    )
    assert out["enforced"] is True
    assert out["allow_trade"] is False
    assert out["fund_status"] == "UNKNOWN"
    assert out["promotion_blocked"] is True
    assert "fundamentals_missing" in list(out.get("warnings") or [])


def test_fundamentals_common_strong_allows_backtest(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    filt = FundamentalsCreditFilter(catalog=db, policies_root=Path("config/policies"))
    out = filt.evaluate(
        exchange="alpaca",
        market="equities",
        symbol="MSFT",
        instrument_type="common",
        target_mode="backtest",
        asof_date=_now_iso(),
        source="test",
        source_id="equities:MSFT",
        raw_payload={"market": "equities", "symbol": "MSFT"},
        current_assets=200.0,
        current_liabilities=100.0,
        bonds_outstanding=100.0,
        fair_value=120.0,
        price=100.0,
    )
    assert out["enforced"] is True
    assert out["allow_trade"] is True
    assert out["fund_status"] in {"STRONG", "BASIC"}
    assert float(out["fund_score"]) >= 60.0


def test_fundamentals_autoload_local_snapshot_for_equities(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    policies_root = tmp_path / "config" / "policies"
    policies_root.mkdir(parents=True, exist_ok=True)
    policies_root.joinpath("fundamentals_credit_filter.yaml").write_text(
        """
fundamentals_credit_filter:
  enabled: true
  fail_closed: true
  apply_markets: ["equities"]
  freshness_max_days: 120
  data_source:
    mode: local_json
    local_snapshot_dir: user_data/fundamentals
    auto_load_when_source_unknown: true
  scoring:
    weights:
      liquidity: 40
      solvency: 30
      margin_of_safety: 30
    thresholds:
      current_ratio_min: 2.0
      working_capital_to_bonds_outstanding_min: 1.0
  policy_by_instrument:
    common:
      backtest_allow_statuses: ["STRONG", "BASIC"]
  snapshots:
    persist: true
    snapshot_ttl_hours: 24
""".strip(),
        encoding="utf-8",
    )
    snap_dir = tmp_path / "user_data" / "fundamentals" / "equities"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = {
        "asof_date": _now_iso(),
        "source_id": "local:TSLA",
        "current_assets": 300.0,
        "current_liabilities": 100.0,
        "bonds_outstanding": 120.0,
        "price": 90.0,
        "fair_value": 110.0,
    }
    (snap_dir / "TSLA.json").write_text(json.dumps(snap), encoding="utf-8")

    filt = FundamentalsCreditFilter(catalog=db, policies_root=policies_root)
    out = filt.evaluate(
        exchange="alpaca",
        market="equities",
        symbol="TSLA",
        instrument_type="common",
        target_mode="backtest",
        source="unknown",
    )
    assert out["enforced"] is True
    assert out["allow_trade"] is True
    assert out["fund_status"] in {"STRONG", "BASIC"}
    assert float(out["fund_score"]) >= 60.0
    codes = {str((r or {}).get("code") or "") for r in out.get("explain") or [] if isinstance(r, dict)}
    assert "DATA_SOURCE_LOCAL_SNAPSHOT" in codes


def test_fundamentals_autoload_remote_snapshot_for_equities(tmp_path: Path, monkeypatch) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    policies_root = tmp_path / "config" / "policies"
    policies_root.mkdir(parents=True, exist_ok=True)
    policies_root.joinpath("fundamentals_credit_filter.yaml").write_text(
        """
fundamentals_credit_filter:
  enabled: true
  fail_closed: true
  apply_markets: ["equities"]
  freshness_max_days: 120
  data_source:
    mode: remote_json
    local_snapshot_dir: user_data/fundamentals
    auto_load_when_source_unknown: true
    remote:
      enabled: true
      base_url_env: FUNDAMENTALS_API_BASE_URL
      endpoint_template: /v1/fund/{market}/{symbol}
      timeout_seconds: 5
      auth_header_name: Authorization
      auth_header_env: FUNDAMENTALS_API_TOKEN
      auth_header_prefix: "Bearer "
  scoring:
    weights:
      liquidity: 40
      solvency: 30
      margin_of_safety: 30
    thresholds:
      current_ratio_min: 2.0
      working_capital_to_bonds_outstanding_min: 1.0
  policy_by_instrument:
    common:
      backtest_allow_statuses: ["STRONG", "BASIC"]
  snapshots:
    persist: true
    snapshot_ttl_hours: 24
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("FUNDAMENTALS_API_BASE_URL", "https://fund.example")
    monkeypatch.setenv("FUNDAMENTALS_API_TOKEN", "token_test")

    class _Resp:
        status = 200

        def __init__(self, payload: dict):
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        assert "AAPL" in str(getattr(req, "full_url", ""))
        return _Resp(
            {
                "asof_date": _now_iso(),
                "source_id": "remote:AAPL",
                "total_current_assets": 250.0,
                "total_current_liabilities": 100.0,
                "total_bonds_outstanding": 100.0,
                "price": 95.0,
                "fair_value": 120.0,
            }
        )

    monkeypatch.setattr(credit_filter_mod, "urlopen", _fake_urlopen)

    filt = FundamentalsCreditFilter(catalog=db, policies_root=policies_root)
    out = filt.evaluate(
        exchange="alpaca",
        market="equities",
        symbol="AAPL",
        instrument_type="common",
        target_mode="backtest",
        source="auto",
    )
    assert out["enforced"] is True
    assert out["allow_trade"] is True
    assert out["fund_status"] in {"STRONG", "BASIC"}
    assert float(out["fund_score"]) >= 60.0
    assert str((out.get("source_ref") or {}).get("source_url") or "").startswith("https://fund.example")
    codes = {str((r or {}).get("code") or "") for r in out.get("explain") or [] if isinstance(r, dict)}
    assert "DATA_SOURCE_REMOTE_SNAPSHOT" in codes
