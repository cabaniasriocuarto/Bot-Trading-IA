from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from zipfile import ZipFile

import pandas as pd
import requests


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rtlab_core.src.data.catalog import DataCatalog  # noqa: E402
from rtlab_core.src.data.universes import MARKET_UNIVERSES  # noqa: E402


BINANCE_PUBLIC_BASE = "https://data.binance.vision/"


def _month_iter(start_ym: str, end_ym: str) -> Iterable[str]:
    cur = datetime.strptime(start_ym, "%Y-%m")
    end = datetime.strptime(end_ym, "%Y-%m")
    while cur <= end:
        yield cur.strftime("%Y-%m")
        year = cur.year + (1 if cur.month == 12 else 0)
        month = 1 if cur.month == 12 else cur.month + 1
        cur = cur.replace(year=year, month=month)


def _download_file(session: requests.Session, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    with session.get(url, timeout=60, stream=True) as res:
        res.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in res.iter_content(chunk_size=1024 * 128):
                if chunk:
                    fh.write(chunk)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_checksum(session: requests.Session, zip_url: str, zip_path: Path) -> bool:
    checksum_url = f"{zip_url}.CHECKSUM"
    try:
        res = session.get(checksum_url, timeout=30)
        if not res.ok:
            return False
        line = (res.text or "").strip().splitlines()[0]
        expected = line.split()[0].strip().lower()
        actual = _sha256_file(zip_path).lower()
        if expected != actual:
            raise RuntimeError(f"CHECKSUM mismatch for {zip_path.name}: expected {expected}, got {actual}")
        return True
    except requests.RequestException:
        return False


def _read_kline_zip(zip_path: Path) -> pd.DataFrame:
    with ZipFile(zip_path, "r") as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise RuntimeError(f"No CSV found in {zip_path}")
        with zf.open(members[0], "r") as fh:
            raw = fh.read()
    frame = pd.read_csv(
        io.BytesIO(raw),
        header=None,
        names=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ],
    )
    out = frame[["open_time", "open", "high", "low", "close", "volume"]].copy()
    out["timestamp"] = pd.to_datetime(out["open_time"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna().drop(columns=["open_time"]).sort_values("timestamp")
    return out[["timestamp", "open", "high", "low", "close", "volume"]]


def _write_parquet_or_csv(df: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(target, index=False)
        return target
    except Exception:
        csv_path = target.with_suffix(".csv")
        df.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)
        return csv_path


def _manifest_summary(user_data_dir: Path, market: str, symbol: str, manifest: dict) -> None:
    summary_path = user_data_dir / "data" / market / "manifests" / f"{symbol}_1m.summary.json"
    payload = {
        "market": market,
        "symbol": symbol,
        "timeframe": "1m",
        "source": manifest.get("source"),
        "dataset_hash": manifest.get("dataset_hash"),
        "start": manifest.get("start"),
        "end": manifest.get("end"),
        "files": manifest.get("files", []),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga klines 1m de Binance Public Data y genera dataset procesado+manifest.")
    parser.add_argument("--user-data-dir", default=str(BACKEND_ROOT / "user_data"))
    parser.add_argument("--symbols", nargs="*", default=MARKET_UNIVERSES["crypto"])
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    parser.add_argument("--skip-checksum", action="store_true")
    args = parser.parse_args()

    user_data_dir = Path(args.user_data_dir).resolve()
    catalog = DataCatalog(user_data_dir)
    session = requests.Session()
    session.headers.update({"User-Agent": "rtlab-backtest-downloader/1.0"})

    for symbol in [s.upper() for s in args.symbols]:
        print(f"[crypto] {symbol}: descargando {args.start_month}..{args.end_month}")
        raw_dir = user_data_dir / "data" / "crypto" / "binance_public" / symbol / "1m"
        processed_dir = user_data_dir / "data" / "crypto" / "processed"
        zips: list[Path] = []
        frames: list[pd.DataFrame] = []

        for ym in _month_iter(args.start_month, args.end_month):
            fname = f"{symbol}-1m-{ym}.zip"
            rel = f"data/spot/monthly/klines/{symbol}/1m/{fname}"
            url = urljoin(BINANCE_PUBLIC_BASE, rel)
            dest = raw_dir / fname
            _download_file(session, url, dest)
            if not args.skip_checksum:
                _verify_checksum(session, url, dest)
            zips.append(dest)
            frames.append(_read_kline_zip(dest))

        if not frames:
            print(f"[crypto] {symbol}: sin datos descargados")
            continue

        df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        target = processed_dir / f"{symbol}_1m.parquet"
        actual_processed = _write_parquet_or_csv(df, target)
        manifest = catalog.write_manifest(
            market="crypto",
            symbol=symbol,
            timeframe="1m",
            source="binance_public",
            start=str(df["timestamp"].min().isoformat()),
            end=str(df["timestamp"].max().isoformat()),
            files=[actual_processed],
            processed_path=actual_processed,
            extra={
                "raw_files": [str(p) for p in zips],
                "raw_dir": str(raw_dir),
                "checksum_verified": not args.skip_checksum,
                "provider": "data.binance.vision",
            },
        )
        _manifest_summary(user_data_dir, "crypto", symbol, manifest)
        print(f"[crypto] {symbol}: ok rows={len(df)} hash={manifest['dataset_hash'][:12]} file={actual_processed.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

