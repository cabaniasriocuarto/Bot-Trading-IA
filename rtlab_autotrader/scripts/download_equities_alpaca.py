from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rtlab_core.src.data.catalog import DataCatalog  # noqa: E402
from rtlab_core.src.data.universes import MARKET_UNIVERSES  # noqa: E402


ALPACA_DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"


def _write_parquet_or_csv(df: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(target, index=False)
        return target
    except Exception:
        csv_path = target.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def _alpaca_headers() -> dict[str, str]:
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")
    secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Faltan APCA_API_KEY_ID/APCA_API_SECRET_KEY (o aliases ALPACA_API_KEY/ALPACA_API_SECRET)")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _fetch_alpaca_1m(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    headers = _alpaca_headers()
    session = requests.Session()
    session.headers.update(headers)

    page_token: str | None = None
    rows: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    while True:
        params = {
            "symbols": symbol,
            "timeframe": "1Min",
            "start": f"{start}T00:00:00Z" if "T" not in start else start,
            "end": f"{end}T23:59:59Z" if "T" not in end else end,
            "limit": 10000,
            "adjustment": "raw",
            "feed": "iex",
        }
        if page_token:
            params["page_token"] = page_token
        res = session.get(ALPACA_DATA_URL, params=params, timeout=60)
        res.raise_for_status()
        payload = res.json()
        raw_pages.append(payload)
        bars = (payload.get("bars") or {}).get(symbol, [])
        for row in bars:
            rows.append(row)
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    if not rows:
        raise RuntimeError(f"Alpaca no devolvió barras para {symbol} ({start}..{end})")

    df = pd.DataFrame(rows)
    # Alpaca keys: t,o,h,l,c,v
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df["t"], utc=True, errors="coerce"),
            "open": pd.to_numeric(df["o"], errors="coerce"),
            "high": pd.to_numeric(df["h"], errors="coerce"),
            "low": pd.to_numeric(df["l"], errors="coerce"),
            "close": pd.to_numeric(df["c"], errors="coerce"),
            "volume": pd.to_numeric(df["v"], errors="coerce").fillna(0.0),
        }
    ).dropna()
    out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return out, raw_pages


def _load_csv_fallback(csv_root: Path, symbol: str, start: str, end: str) -> tuple[pd.DataFrame, list[str]]:
    candidates = [
        csv_root / f"{symbol}.csv",
        csv_root / f"{symbol}_1m.csv",
        csv_root / symbol / "1m.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise RuntimeError(f"No se encontró CSV fallback para {symbol} en {csv_root}")
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    ts_col = next((cols[c] for c in ("timestamp", "time", "date") if c in cols), None)
    o_col = next((cols[c] for c in ("open", "o") if c in cols), None)
    h_col = next((cols[c] for c in ("high", "h") if c in cols), None)
    l_col = next((cols[c] for c in ("low", "l") if c in cols), None)
    c_col = next((cols[c] for c in ("close", "c") if c in cols), None)
    v_col = next((cols[c] for c in ("volume", "v") if c in cols), None)
    if not all([ts_col, o_col, h_col, l_col, c_col]):
        raise RuntimeError(f"CSV {path} no tiene columnas OHLC válidas")
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[ts_col], utc=True, errors="coerce"),
            "open": pd.to_numeric(df[o_col], errors="coerce"),
            "high": pd.to_numeric(df[h_col], errors="coerce"),
            "low": pd.to_numeric(df[l_col], errors="coerce"),
            "close": pd.to_numeric(df[c_col], errors="coerce"),
            "volume": pd.to_numeric(df[v_col], errors="coerce").fillna(0.0) if v_col else 0.0,
        }
    ).dropna()
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    out = out[(out["timestamp"] >= start_ts) & (out["timestamp"] <= end_ts)].sort_values("timestamp")
    return out, [str(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga barras 1Min de Alpaca (o CSV fallback) y genera dataset+manifest.")
    parser.add_argument("--user-data-dir", default=str(BACKEND_ROOT / "user_data"))
    parser.add_argument("--symbols", nargs="*", default=MARKET_UNIVERSES["equities"])
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--csv-root", default="", help="Fallback CSV root si no hay API keys. Marca source=csv.")
    args = parser.parse_args()

    user_data_dir = Path(args.user_data_dir).resolve()
    catalog = DataCatalog(user_data_dir)

    for symbol in [s.upper() for s in args.symbols]:
        print(f"[equities] {symbol}: {args.start}..{args.end}")
        raw_dir = user_data_dir / "data" / "equities" / "alpaca" / "raw" / symbol / "1m"
        processed_dir = user_data_dir / "data" / "equities" / "processed"
        raw_dir.mkdir(parents=True, exist_ok=True)

        source = "alpaca"
        raw_files: list[str] = []
        try:
            df, raw_pages = _fetch_alpaca_1m(symbol, args.start, args.end)
            raw_json_path = raw_dir / f"{symbol}_{args.start}_{args.end}.json"
            raw_json_path.write_text(json.dumps(raw_pages, indent=2), encoding="utf-8")
            raw_files = [str(raw_json_path)]
        except Exception as exc:
            if not args.csv_root:
                raise SystemExit(f"[equities] {symbol}: error Alpaca y sin --csv-root fallback. Detalle: {exc}")
            source = "csv"
            df, raw_files = _load_csv_fallback(Path(args.csv_root).resolve(), symbol, args.start, args.end)

        if df.empty:
            raise SystemExit(f"[equities] {symbol}: sin datos 1m en rango")

        processed_path = _write_parquet_or_csv(df, processed_dir / f"{symbol}_1m.parquet")
        manifest = catalog.write_manifest(
            market="equities",
            symbol=symbol,
            timeframe="1m",
            source=source,
            start=str(df["timestamp"].min().isoformat()),
            end=str(df["timestamp"].max().isoformat()),
            files=[processed_path],
            processed_path=processed_path,
            extra={
                "raw_files": raw_files,
                "provider": "alpaca" if source == "alpaca" else "csv",
            },
        )
        print(
            json.dumps(
                {
                    "market": "equities",
                    "symbol": symbol,
                    "rows_1m": int(len(df)),
                    "source": source,
                    "dataset_hash": manifest["dataset_hash"],
                    "processed_path": str(processed_path),
                },
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

