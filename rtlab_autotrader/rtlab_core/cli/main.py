from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import typer
import yaml
from rich.console import Console
from rich.table import Table

from rtlab_core.backtest.metrics import compute_metrics
from rtlab_core.backtest.realism_gate import RealismConfig, RealismGate
from rtlab_core.backtest.stress import stress_metrics
from rtlab_core.backtest.validation import cpcv_paths, is_promotable, purged_cv_splits, walk_forward_splits
from rtlab_core.config import RuntimeConfig, load_config
from rtlab_core.strategy_packs.pack_compiler import compile_pack
from rtlab_core.strategy_packs.pack_loader import load_pack
from rtlab_core.strategy_packs.registry_db import RegistryDB


app = typer.Typer(help="RTLab AutoTrader CLI")
pack_app = typer.Typer(help="Strategy pack operations")
app.add_typer(pack_app, name="pack")
console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA = PROJECT_ROOT / "user_data"
PACKS_DIR = USER_DATA / "strategy_packs" / "packs"
RESULTS_DIR = USER_DATA / "strategy_packs" / "results"
REGISTRY_YAML = USER_DATA / "strategy_packs" / "registry.yaml"
REGISTRY_DB = USER_DATA / "strategy_packs" / "registry.sqlite3"
STATE_FILE = USER_DATA / "logs" / "run_state.json"


def _db() -> RegistryDB:
    return RegistryDB(REGISTRY_DB)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_runtime_config(config_path: str | None) -> RuntimeConfig:
    explicit = config_path or os.environ.get("RTLAB_CONFIG_PATH") or str(PROJECT_ROOT / "rtlab_config.yaml")
    return load_config(explicit)


def _json_log(event: str, **payload: Any) -> None:
    row = {"ts": _now(), "event": event, **payload}
    print(json.dumps(row, separators=(",", ":")))


def _send_telegram(cfg: RuntimeConfig, text: str) -> None:
    enabled = cfg.notifications.telegram_enabled and bool(cfg.notifications.bot_token) and bool(cfg.notifications.chat_id)
    if not enabled:
        return
    token = cfg.notifications.bot_token
    chat_id = cfg.notifications.chat_id
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=8)
    except requests.RequestException:
        _json_log("telegram_error", message="failed_to_send")


def _update_registry_yaml(db: RegistryDB) -> None:
    payload = {
        "generated_at": _now(),
        "strategies": db.list_strategies(),
        "principals": db.principals(),
    }
    REGISTRY_YAML.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_YAML.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _simulate_backtest(strategy_name: str, timerange: str, pairs: list[str], cfg: RuntimeConfig) -> dict[str, Any]:
    seed_input = f"{strategy_name}:{timerange}:{','.join(pairs)}"
    seed = int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    trades = 260
    raw_pnl = pd.Series(rng.normal(loc=9.0, scale=14.0, size=trades), name="raw_pnl")
    notional = pd.Series(rng.uniform(400.0, 2500.0, size=trades), name="notional")
    volume_share = pd.Series(rng.uniform(0.0, 3.0, size=trades), name="volume_share")
    spread_bps = pd.Series(rng.uniform(2.0, cfg.universe.max_spread_bps, size=trades), name="spread_bps")
    funding_bps = pd.Series(rng.uniform(0.0, cfg.execution.funding_proxy_bps * 1.4, size=trades), name="funding_bps")

    frame = pd.DataFrame(
        {
            "raw_pnl": raw_pnl,
            "notional": notional,
            "volume_share": volume_share,
            "spread_bps": spread_bps,
            "funding_bps": funding_bps,
            "fee_bps": cfg.execution.taker_fee_bps,
        }
    )

    realism = RealismGate(
        RealismConfig(
            maker_fee_bps=cfg.execution.maker_fee_bps,
            taker_fee_bps=cfg.execution.taker_fee_bps,
            spread_proxy_bps=cfg.execution.spread_proxy_bps,
            slippage_base_bps=cfg.execution.slippage_base_bps,
            slippage_vol_k=cfg.execution.slippage_vol_k,
            funding_proxy_bps=cfg.execution.funding_proxy_bps,
        )
    )
    applied = realism.apply(frame)
    summary = applied["summary"]
    net_pnl = applied["trades"]["net_pnl"]

    metrics = compute_metrics(net_pnl, equity_start=cfg.risk.starting_equity)
    stressed = stress_metrics(
        metrics,
        fees_mult=cfg.backtest.stress_fees_mult,
        slippage_mult=cfg.backtest.stress_slippage_mult,
        param_variation=cfg.backtest.stress_param_variation_pct,
    )

    wf_splits = walk_forward_splits(n_samples=len(net_pnl), train_size=120, test_size=40, step=20)
    segment_expectancies: list[float] = []
    for _, test_idx in wf_splits:
        if not test_idx:
            continue
        seg = net_pnl.iloc[test_idx]
        segment_expectancies.append(float(seg.mean()) if len(seg) else 0.0)
    oos_positive_segments = sum(1 for v in segment_expectancies if v > 0)

    purged = purged_cv_splits(n_samples=len(net_pnl), n_splits=5, embargo=5)
    cpcv = cpcv_paths(n_splits=5, n_test_paths=2)
    promotable = is_promotable(
        metrics=metrics,
        stressed=stressed,
        oos_positive_segments=oos_positive_segments,
        min_oos_segments=cfg.backtest.min_oos_segments,
    )

    robust_score = (
        100.0 * metrics["expectancy"]
        + 20.0 * metrics["sharpe"]
        - 80.0 * metrics["max_drawdown"]
        + (15.0 if stressed["stress_pass"] else -20.0)
    )

    return {
        "engine": "simulated",
        "realism": summary,
        "metrics": metrics,
        "stressed": stressed,
        "oos_positive_segments": oos_positive_segments,
        "validation": {
            "walk_forward_splits": len(wf_splits),
            "purged_cv_splits": len(purged),
            "cpcv_paths": len(cpcv),
            "oos_segment_expectancies": segment_expectancies,
        },
        "promotable": promotable,
        "robust_score": robust_score,
    }


def _run_freqtrade_backtest(config_path: str, timerange: str, pairs: list[str]) -> None:
    if shutil.which("freqtrade") is None:
        raise RuntimeError("freqtrade binary not found")
    pair_args: list[str] = []
    for pair in pairs:
        pair_args.extend(["--pairs", pair])
    cmd = [
        "freqtrade",
        "backtesting",
        "--config",
        config_path,
        "--strategy",
        "DslStrategy",
        "--timerange",
        timerange,
        "--timeframe-detail",
        "1m",
    ] + pair_args
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


@pack_app.command("import")
def pack_import(
    file: str = typer.Option(..., "--file", help="Path to pack TXT"),
    notes: str = typer.Option("", "--notes", help="Optional notes"),
) -> None:
    file_path = Path(file)
    pack = load_pack(file_path)

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    target = PACKS_DIR / file_path.name
    target.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")

    db = _db()
    strategy_id = db.upsert_strategy(
        name=pack.spec.metadata.name,
        version=pack.spec.metadata.version,
        path=str(target),
        sha256=_sha256_file(target),
        status="draft",
        notes=notes or None,
    )

    _update_registry_yaml(db)
    console.print(f"Imported pack '{pack.spec.metadata.name}' ({pack.spec.metadata.version}) id={strategy_id}")


@pack_app.command("validate")
def pack_validate(name: str = typer.Option(..., "--name")) -> None:
    db = _db()
    row = db.get_strategy_by_name(name)
    if not row:
        raise typer.BadParameter(f"strategy '{name}' not found")

    pack = load_pack(row["path"])
    compiled_path = compile_pack(pack, RESULTS_DIR)
    db.set_status(int(row["id"]), "tested")
    _update_registry_yaml(db)
    console.print(f"Validation OK. Compiled artifact: {compiled_path}")


@pack_app.command("list")
def pack_list() -> None:
    db = _db()
    rows = db.list_strategies()
    table = Table("id", "name", "version", "status", "created_at")
    for row in rows:
        table.add_row(str(row["id"]), row["name"], row["version"], row["status"], row["created_at"])
    console.print(table)


@pack_app.command("backtest")
def pack_backtest(
    name: str = typer.Option(..., "--name"),
    timerange: str = typer.Option(..., "--timerange"),
    pairs: str = typer.Option(..., "--pairs", help="Comma-separated pairs"),
    config: str = typer.Option("", "--config", help="Path to rtlab config"),
    engine: str = typer.Option("auto", "--engine", help="auto|simulated|freqtrade"),
) -> None:
    db = _db()
    strategy = db.get_strategy_by_name(name)
    if not strategy:
        raise typer.BadParameter(f"strategy '{name}' not found")

    cfg = _load_runtime_config(config or None)
    pair_list = [p.strip() for p in pairs.split(",") if p.strip()]
    if not pair_list:
        raise typer.BadParameter("pairs cannot be empty")

    selected_engine = engine
    if engine == "auto":
        selected_engine = "freqtrade" if shutil.which("freqtrade") else "simulated"

    if selected_engine == "freqtrade":
        try:
            _run_freqtrade_backtest(config_path=config or "rtlab_config.yaml", timerange=timerange, pairs=pair_list)
        except Exception as exc:
            raise typer.BadParameter(f"freqtrade backtest failed: {exc}") from exc

    result = _simulate_backtest(name, timerange, pair_list, cfg)
    result["engine"] = selected_engine

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = RESULTS_DIR / f"{name}_{timerange.replace(':', '_').replace('/', '_')}.json"
    artifact.write_text(json.dumps(result, indent=2), encoding="utf-8")

    db.add_backtest(
        strategy_id=int(strategy["id"]),
        timerange=timerange,
        exchange=cfg.universe.exchange,
        pairs=pair_list,
        metrics=result,
        artifacts_path=str(artifact),
    )
    db.set_status(int(strategy["id"]), "tested")
    _update_registry_yaml(db)

    console.print(f"Backtest stored. robust_score={result['robust_score']:.2f} promotable={result['promotable']}")


@pack_app.command("rank")
def pack_rank(timerange: str = typer.Option(..., "--timerange")) -> None:
    db = _db()
    backtests = db.list_backtests(timerange=timerange)
    if not backtests:
        console.print("No backtests found for timerange")
        raise typer.Exit(code=1)

    strategies = {row["id"]: row for row in db.list_strategies()}
    ranked: list[tuple[str, float, float, float, bool]] = []

    for bt in backtests:
        metrics = bt["metrics_json"]
        strategy = strategies.get(bt["strategy_id"], {})
        name = strategy.get("name", f"id:{bt['strategy_id']}")
        score = float(metrics.get("robust_score", 0.0))
        expectancy = float(metrics.get("metrics", {}).get("expectancy", 0.0))
        max_dd = float(metrics.get("metrics", {}).get("max_drawdown", 1.0))
        promotable = bool(metrics.get("promotable", False))
        ranked.append((name, score, expectancy, max_dd, promotable))

    ranked.sort(key=lambda row: row[1], reverse=True)

    table = Table("rank", "name", "robust_score", "expectancy", "max_dd", "promotable")
    for idx, row in enumerate(ranked, start=1):
        table.add_row(str(idx), row[0], f"{row[1]:.2f}", f"{row[2]:.4f}", f"{row[3]:.4f}", str(row[4]))
    console.print(table)


@pack_app.command("promote")
def pack_promote(
    name: str = typer.Option(..., "--name"),
    mode: str = typer.Option(..., "--mode", help="paper|testnet|live"),
) -> None:
    if mode not in {"paper", "testnet", "live"}:
        raise typer.BadParameter("mode must be paper|testnet|live")

    db = _db()
    strategy = db.get_strategy_by_name(name)
    if not strategy:
        raise typer.BadParameter(f"strategy '{name}' not found")

    latest = db.get_latest_backtest(int(strategy["id"]))
    if not latest:
        raise typer.BadParameter("strategy has no backtest")

    metrics = latest["metrics_json"]
    if not metrics.get("promotable", False):
        raise typer.BadParameter("strategy does not pass promotable criteria")

    db.set_principal(int(strategy["id"]), mode)
    _update_registry_yaml(db)
    console.print(f"Promoted '{name}' to principal for mode={mode}")


@app.command("run")
def run_mode(
    mode: str = typer.Option(..., "--mode", help="paper|testnet|live"),
    config: str = typer.Option("", "--config", help="Path to rtlab config"),
) -> None:
    if mode not in {"paper", "testnet", "live"}:
        raise typer.BadParameter("mode must be paper|testnet|live")

    cfg = _load_runtime_config(config or None)
    db = _db()
    principal = db.get_principal(mode)
    if not principal:
        raise typer.BadParameter(f"No principal strategy for mode={mode}")

    state = {
        "mode": mode,
        "started_at": _now(),
        "principal": {
            "strategy_id": principal["strategy_id"],
            "name": principal["name"],
            "version": principal["version"],
            "path": principal["path"],
        },
        "safe_mode": False,
        "kill_switch": False,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    _json_log("run_started", mode=mode, strategy=principal["name"], version=principal["version"])
    _send_telegram(cfg, f"RTLab run started | mode={mode} | strategy={principal['name']}:{principal['version']}")
    console.print(f"Run state persisted to {STATE_FILE}")


@app.command("status")
def status() -> None:
    db = _db()
    principals = db.principals()
    backtests = db.list_backtests()[:10]

    ptable = Table("mode", "strategy", "version", "activated_at")
    for row in principals:
        ptable.add_row(row["mode"], row["name"], row["version"], row["activated_at"])
    if principals:
        console.print(ptable)
    else:
        console.print("No principals configured")

    btable = Table("strategy_id", "timerange", "exchange", "created_at", "robust_score", "promotable")
    for row in backtests:
        metrics = row["metrics_json"]
        btable.add_row(
            str(row["strategy_id"]),
            row["timerange"],
            row["exchange"],
            row["created_at"],
            f"{float(metrics.get('robust_score', 0.0)):.2f}",
            str(bool(metrics.get("promotable", False))),
        )
    if backtests:
        console.print(btable)


if __name__ == "__main__":
    app()
