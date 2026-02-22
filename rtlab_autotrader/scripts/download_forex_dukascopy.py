from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rtlab_core.src.data.catalog import DataCatalog  # noqa: E402
from rtlab_core.src.data.loader import ticks_to_1m_forex  # noqa: E402
from rtlab_core.src.data.universes import MARKET_UNIVERSES  # noqa: E402


def _iter_csv_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(list(root.rglob("*.csv")))


def _normalize_tick_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    ts_col = next((cols[c] for c in ("timestamp", "time", "ts", "date") if c in cols), None)
    bid_col = next((cols[c] for c in ("bid", "bidprice", "bid_price") if c in cols), None)
    ask_col = next((cols[c] for c in ("ask", "askprice", "ask_price") if c in cols), None)
    if not ts_col or not bid_col or not ask_col:
        raise ValueError("Tick CSV requiere columnas timestamp/time + bid + ask")
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[ts_col], utc=True, errors="coerce"),
            "bid": pd.to_numeric(df[bid_col], errors="coerce"),
            "ask": pd.to_numeric(df[ask_col], errors="coerce"),
        }
    ).dropna()
    return out.sort_values("timestamp")


def _write_parquet_or_csv(df: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(target, index=False)
        return target
    except Exception:
        csv_path = target.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def _run_external_downloader(template: str, pair: str, start: str, end: str, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = template.format(pair=pair, start=start, end=end, outdir=str(outdir))
    print(f"[forex] Ejecutando downloader externo: {cmd}")
    proc = subprocess.run(shlex.split(cmd), check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Fallo downloader externo para Dukascopy.\n"
            f"cmd={cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Procesa ticks Dukascopy (CSV) -> OHLC 1m con bid/ask y genera manifest. "
            "Opcionalmente invoca un downloader externo (ej. dukascopy-node) vía plantilla."
        )
    )
    parser.add_argument("--user-data-dir", default=str(BACKEND_ROOT / "user_data"))
    parser.add_argument("--pairs", nargs="*", default=MARKET_UNIVERSES["forex"])
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--download-cmd-template",
        default="",
        help="Plantilla comando externo con placeholders {pair} {start} {end} {outdir}",
    )
    parser.add_argument(
        "--input-root",
        default="",
        help="Ruta con ticks CSV ya descargados (default: user_data/data/forex/dukascopy/raw)",
    )
    args = parser.parse_args()

    user_data_dir = Path(args.user_data_dir).resolve()
    catalog = DataCatalog(user_data_dir)

    for pair in [p.upper().replace("/", "") for p in args.pairs]:
        raw_root = Path(args.input_root).resolve() if args.input_root else (user_data_dir / "data" / "forex" / "dukascopy" / "raw" / pair / "tick")
        raw_root.mkdir(parents=True, exist_ok=True)
        if args.download_cmd_template:
            _run_external_downloader(args.download_cmd_template, pair, args.start, args.end, raw_root)

        csv_files = list(_iter_csv_files(raw_root))
        if not csv_files:
            raise SystemExit(
                f"[forex] No se encontraron CSV ticks para {pair} en {raw_root}. "
                "Usa --download-cmd-template (ej. dukascopy-node) o coloca CSVs con columnas timestamp,bid,ask."
            )

        tick_frames: list[pd.DataFrame] = []
        for path in csv_files:
            try:
                tick_frames.append(_normalize_tick_frame(pd.read_csv(path)))
            except Exception as exc:
                print(f"[forex] WARNING {pair}: no se pudo leer {path.name}: {exc}")
        if not tick_frames:
            raise SystemExit(f"[forex] No hay ticks válidos para {pair}")

        ticks = pd.concat(tick_frames, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        # Filtra rango solicitado antes de agregar.
        start_ts = pd.Timestamp(args.start, tz="UTC")
        end_ts = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        ticks = ticks[(ticks["timestamp"] >= start_ts) & (ticks["timestamp"] <= end_ts)]
        if ticks.empty:
            raise SystemExit(f"[forex] Rango sin datos para {pair}: {args.start}..{args.end}")

        bars_1m = ticks_to_1m_forex(ticks)
        bars_1m = bars_1m.reset_index().rename(columns={"index": "timestamp"})

        processed_dir = user_data_dir / "data" / "forex" / "processed"
        processed_path = _write_parquet_or_csv(bars_1m, processed_dir / f"{pair}_1m.parquet")
        manifest = catalog.write_manifest(
            market="forex",
            symbol=pair,
            timeframe="1m",
            source="dukascopy",
            start=str(bars_1m["timestamp"].min().isoformat()),
            end=str(bars_1m["timestamp"].max().isoformat()),
            files=[processed_path],
            processed_path=processed_path,
            extra={
                "raw_dir": str(raw_root),
                "raw_files": [str(p) for p in csv_files],
                "provider": "dukascopy",
                "contains_bid_ask_ohlc": True,
            },
        )

        summary = {
            "pair": pair,
            "rows_ticks": int(len(ticks)),
            "rows_1m": int(len(bars_1m)),
            "dataset_hash": manifest["dataset_hash"],
            "processed_path": str(processed_path),
        }
        print(f"[forex] {json.dumps(summary, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

