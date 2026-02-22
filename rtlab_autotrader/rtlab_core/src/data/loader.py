from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from rtlab_core.data.marketdata import ensure_datetime_index

from .catalog import CatalogEntry, DataCatalog
from .universes import DEFAULT_SOURCES, normalize_market, normalize_symbol, normalize_timeframe


def _resample_rule(tf: str) -> str:
    minutes = int(tf.replace("m", ""))
    return f"{minutes}min"


def _read_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported dataset file: {path}")


def _write_parquet_or_csv(df: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(target, index=True)
        return target
    except Exception:
        csv_path = target.with_suffix(".csv")
        df.to_csv(csv_path, index=True)
        return csv_path


def _slice_timerange(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = ensure_datetime_index(df)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    # UX/API often sends date-only strings; include the full end day in that case.
    if "T" not in str(end):
        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return out.loc[start_ts:end_ts]


def _resample_ohlc(df: pd.DataFrame, rule: str, *, include_bid_ask: bool) -> pd.DataFrame:
    source = ensure_datetime_index(df)
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if include_bid_ask:
        for prefix in ("bid", "ask"):
            for field in ("open", "high", "low", "close"):
                col = f"{prefix}_{field}"
                if col in source.columns:
                    agg[col] = {"open": "first", "high": "max", "low": "min", "close": "last"}[field]
    resampled = source.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"])
    if "volume" not in resampled.columns:
        resampled["volume"] = 0.0
    return resampled


def ticks_to_1m_forex(df: pd.DataFrame) -> pd.DataFrame:
    source = ensure_datetime_index(df)
    if "bid" not in source.columns or "ask" not in source.columns:
        raise ValueError("Forex tick dataset requires bid and ask columns")
    source = source.copy()
    source["mid"] = (source["bid"] + source["ask"]) / 2.0
    out = pd.DataFrame(index=source.resample("1min").size().index)
    for px in ("mid", "bid", "ask"):
        out[f"{px}_open"] = source[px].resample("1min").first()
        out[f"{px}_high"] = source[px].resample("1min").max()
        out[f"{px}_low"] = source[px].resample("1min").min()
        out[f"{px}_close"] = source[px].resample("1min").last()
    out["open"] = out["mid_open"]
    out["high"] = out["mid_high"]
    out["low"] = out["mid_low"]
    out["close"] = out["mid_close"]
    out["volume"] = source["bid"].resample("1min").count().astype(float)
    return out.dropna()


@dataclass(slots=True)
class LoadedDataset:
    market: str
    symbol: str
    timeframe: str
    source: str
    dataset_hash: str
    start: str
    end: str
    df: pd.DataFrame
    manifest: dict[str, Any]


class DataLoader:
    def __init__(self, user_data_dir: Path) -> None:
        self.user_data_dir = user_data_dir.resolve()
        self.catalog = DataCatalog(self.user_data_dir)

    def _processed_path(self, market: str, symbol: str, timeframe: str) -> Path:
        mk = normalize_market(market)
        sym = normalize_symbol(symbol)
        tf = timeframe.lower()
        return self.catalog.processed_dir(mk) / f"{sym}_{tf}.parquet"

    def _load_from_entry(self, entry: CatalogEntry) -> pd.DataFrame:
        candidates: list[Path] = []
        if entry.processed_path:
            candidates.append(Path(entry.processed_path))
        for file_str in entry.files:
            candidates.append(Path(file_str))
        for path in candidates:
            if path.exists():
                df = _read_df(path)
                return ensure_datetime_index(df)
        raise FileNotFoundError(f"No dataset files found for {entry.market}/{entry.symbol}/{entry.timeframe}")

    def load_1m(self, market: str, symbol: str, start: str, end: str) -> LoadedDataset:
        mk = normalize_market(market)
        sym = normalize_symbol(symbol)
        entry = self.catalog.find_entry(mk, sym, "1m")
        if not entry:
            raise FileNotFoundError(f"Faltan datos para {mk}/{sym}/1m")
        df = self._load_from_entry(entry)
        if mk == "forex" and {"bid", "ask"}.issubset(set(df.columns)):
            df = ticks_to_1m_forex(df)
        df = _slice_timerange(df, start, end)
        return LoadedDataset(
            market=mk,
            symbol=sym,
            timeframe="1m",
            source=entry.source,
            dataset_hash=entry.dataset_hash,
            start=entry.start,
            end=entry.end,
            df=df,
            manifest=entry.metadata or {},
        )

    def load_resampled(self, market: str, symbol: str, timeframe: str, start: str, end: str) -> LoadedDataset:
        mk = normalize_market(market)
        sym = normalize_symbol(symbol)
        tf = normalize_timeframe(timeframe)

        existing = self.catalog.find_entry(mk, sym, tf)
        if existing:
            df = _slice_timerange(self._load_from_entry(existing), start, end)
            return LoadedDataset(
                market=mk,
                symbol=sym,
                timeframe=tf,
                source=existing.source,
                dataset_hash=existing.dataset_hash,
                start=existing.start,
                end=existing.end,
                df=df,
                manifest=existing.metadata or {},
            )

        base = self.load_1m(mk, sym, start, end)
        if base.df.empty:
            raise FileNotFoundError(f"Faltan datos para {mk}/{sym}/{tf} en rango {start}..{end}")

        include_bid_ask = mk == "forex" and any(col.startswith("bid_") or col.startswith("ask_") for col in base.df.columns)
        resampled = _resample_ohlc(base.df, _resample_rule(tf), include_bid_ask=include_bid_ask)
        target = self._processed_path(mk, sym, tf)
        actual_file = _write_parquet_or_csv(resampled, target)
        manifest = self.catalog.write_manifest(
            market=mk,
            symbol=sym,
            timeframe=tf,
            source=base.source or DEFAULT_SOURCES[mk],
            start=str(resampled.index.min().isoformat()) if not resampled.empty else start,
            end=str(resampled.index.max().isoformat()) if not resampled.empty else end,
            files=[actual_file],
            processed_path=actual_file,
            extra={"derived_from": "1m"},
        )
        return LoadedDataset(
            market=mk,
            symbol=sym,
            timeframe=tf,
            source=str(manifest.get("source", "")),
            dataset_hash=str(manifest.get("dataset_hash", "")),
            start=str(manifest.get("start", start)),
            end=str(manifest.get("end", end)),
            df=resampled,
            manifest=manifest,
        )
