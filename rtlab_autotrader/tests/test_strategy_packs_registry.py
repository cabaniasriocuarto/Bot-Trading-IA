from pathlib import Path

from rtlab_core.strategy_packs.pack_loader import load_pack
from rtlab_core.strategy_packs.registry_db import RegistryDB


def test_registry_import_backtest_and_promote(tmp_path: Path) -> None:
    pack_file = tmp_path / "sample_pack.txt"
    pack_file.write_text(
        """
---
metadata:
  name: sample
  version: v1
  market: crypto_perps
  timeframes: [\"1h\", \"15m\", \"5m\", \"1m\"]
universe:
  min_volume_24h_usd: 1000000
  max_spread_bps: 12
microstructure:
  enable_vpin: true
  enable_obi: true
  enable_cvd: true
params: {}
---
rule environment: LIQUIDITY_OK() and SPREAD_BPS() <= 12
rule direction: TSCAN_TMAX() >= 2
""".strip(),
        encoding="utf-8",
    )

    pack = load_pack(pack_file)
    assert pack.spec.metadata.name == "sample"
    assert "environment" in pack.rules

    db = RegistryDB(tmp_path / "registry.sqlite3")
    sid = db.upsert_strategy(
        name=pack.spec.metadata.name,
        version=pack.spec.metadata.version,
        path=str(pack_file),
        sha256="abc123",
        status="tested",
    )
    db.add_backtest(
        strategy_id=sid,
        timerange="20240101-20241231",
        exchange="bybit",
        pairs=["BTC/USDT:USDT"],
        metrics={"robust_score": 10.0, "promotable": True, "metrics": {"expectancy": 0.1, "max_drawdown": 0.1}},
        artifacts_path=str(tmp_path / "artifact.json"),
    )
    latest = db.get_latest_backtest(sid)
    assert latest is not None
    assert latest["metrics_json"]["promotable"] is True

    db.set_principal(sid, "paper")
    principal = db.get_principal("paper")
    assert principal is not None
    assert principal["name"] == "sample"
