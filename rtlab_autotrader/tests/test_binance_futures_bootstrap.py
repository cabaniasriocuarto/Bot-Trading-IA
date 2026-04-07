from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rtlab_core.src.data.binance_futures_bootstrap import bootstrap_futures_datasets, select_top_symbols
from rtlab_core.src.data.catalog import DataCatalog


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, mapping: dict[str, object]) -> None:
        self.mapping = mapping

    def get(self, url: str, *args, **kwargs):
        payload = self.mapping.get(url)
        if payload is None:
            return _FakeResponse({}, status_code=404)
        return _FakeResponse(payload)


def test_select_top_symbols_uses_official_rank_metric_per_family() -> None:
    usdm = select_top_symbols(
        _FakeSession(
            {
                "https://fapi.binance.com/fapi/v1/exchangeInfo": {
                    "symbols": [
                        {"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL", "underlyingType": "COIN"},
                        {"symbol": "ETHUSDT", "status": "TRADING", "contractType": "PERPETUAL", "underlyingType": "COIN"},
                        {"symbol": "BNBUSDT", "status": "BREAK", "contractType": "PERPETUAL", "underlyingType": "COIN"},
                    ]
                },
                "https://fapi.binance.com/fapi/v1/ticker/24hr": [
                    {"symbol": "BTCUSDT", "quoteVolume": "2000000"},
                    {"symbol": "ETHUSDT", "quoteVolume": "1000000"},
                    {"symbol": "BNBUSDT", "quoteVolume": "999999999"},
                ],
            }
        ),
        "usdm",
        top_n=2,
    )
    assert usdm["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert usdm["selection_metric"] == "quoteVolume_24h_desc"

    coinm = select_top_symbols(
        _FakeSession(
            {
                "https://dapi.binance.com/dapi/v1/exchangeInfo": {
                    "symbols": [
                        {"symbol": "BTCUSD_PERP", "contractStatus": "TRADING", "contractType": "PERPETUAL", "underlyingType": "COIN"},
                        {"symbol": "ETHUSD_PERP", "contractStatus": "TRADING", "contractType": "PERPETUAL", "underlyingType": "COIN"},
                    ]
                },
                "https://dapi.binance.com/dapi/v1/ticker/24hr": [
                    {"symbol": "BTCUSD_PERP", "baseVolume": "1000", "weightedAvgPrice": "85000"},
                    {"symbol": "ETHUSD_PERP", "baseVolume": "5000", "weightedAvgPrice": "2000"},
                ],
            }
        ),
        "coinm",
        top_n=1,
    )
    assert coinm["symbols"] == ["BTCUSD_PERP"]
    assert coinm["selection_metric"] == "baseVolume_x_weightedAvgPrice_24h_desc"


def test_bootstrap_futures_datasets_writes_1m_and_5m_from_rest_fallback(tmp_path: Path, monkeypatch) -> None:
    def _fake_download_binary(session, url, dest):
        return False

    def _fake_fetch_rest_month(session, family, symbol, month):
        idx = pd.date_range("2024-01-01T00:00:00Z", periods=10, freq="1min")
        return pd.DataFrame(
            {
                "timestamp": idx,
                "open": [100 + i for i in range(len(idx))],
                "high": [101 + i for i in range(len(idx))],
                "low": [99 + i for i in range(len(idx))],
                "close": [100.5 + i for i in range(len(idx))],
                "volume": [10 + i for i in range(len(idx))],
            }
        )

    monkeypatch.setattr("rtlab_core.src.data.binance_futures_bootstrap._download_binary", _fake_download_binary)
    monkeypatch.setattr("rtlab_core.src.data.binance_futures_bootstrap._fetch_rest_month", _fake_fetch_rest_month)

    payload = bootstrap_futures_datasets(
        user_data_dir=tmp_path,
        market_family="usdm",
        symbols=["BTCUSDT"],
        start_month="2024-01",
        end_month="2024-01",
        resample_timeframes=["5m"],
    )
    assert payload["ok"] is True
    assert payload["symbols"] == ["BTCUSDT"]
    assert payload["bootstrapped"][0]["dataset_1m_present"] is True

    catalog = DataCatalog(tmp_path)
    entry_1m = catalog.find_entry("crypto", "BTCUSDT", "1m")
    entry_5m = catalog.find_entry("crypto", "BTCUSDT", "5m")
    assert entry_1m is not None
    assert entry_5m is not None
    assert str((entry_1m.metadata or {}).get("source_type") or "") == "binance_rest_klines"
    assert payload["data_status"]["available_count"] >= 2


def test_catalog_ignores_summary_json_manifests(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "data" / "crypto" / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "market": "crypto",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "source": "binance_public",
        "start": "2024-01-01T00:00:00+00:00",
        "end": "2024-01-01T00:09:00+00:00",
        "files": [],
        "dataset_hash": "hash",
    }
    (manifests_dir / "BTCUSDT_1m.json").write_text(json.dumps(manifest_payload), encoding="utf-8")
    (manifests_dir / "BTCUSDT_1m.summary.json").write_text(json.dumps(manifest_payload), encoding="utf-8")

    entries = DataCatalog(tmp_path).list_entries("crypto")
    assert len(entries) == 1
    assert entries[0].timeframe == "1m"
