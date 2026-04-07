from __future__ import annotations

import hashlib
import io
import json
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zipfile import ZipFile

import pandas as pd
import requests

from rtlab_core.data.marketdata import ensure_datetime_index, resample_ohlcv

from .catalog import DataCatalog
from .runtime_path import runtime_path
from .universes import normalize_symbol

BINANCE_PUBLIC_BASE = "https://data.binance.vision/"
USDM_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
COINM_EXCHANGE_INFO_URL = "https://dapi.binance.com/dapi/v1/exchangeInfo"
USDM_TICKER_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
COINM_TICKER_24H_URL = "https://dapi.binance.com/dapi/v1/ticker/24hr"
USDM_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
COINM_KLINES_URL = "https://dapi.binance.com/dapi/v1/klines"

SUPPORTED_FAMILIES = {"usdm", "coinm"}
DEFAULT_CANONICAL_RESAMPLES = ("5m", "15m", "1h", "4h", "1d")
SUPPORTED_RESAMPLES = set(DEFAULT_CANONICAL_RESAMPLES) | {"10m"}


def normalize_family(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in SUPPORTED_FAMILIES:
        raise ValueError(f"Unsupported market_family: {value}")
    return normalized


def normalize_resample_timeframes(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return list(DEFAULT_CANONICAL_RESAMPLES)
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if not normalized:
            continue
        if normalized not in SUPPORTED_RESAMPLES:
            raise ValueError(f"Unsupported resample timeframe: {value}")
        if normalized not in out:
            out.append(normalized)
    return out or list(DEFAULT_CANONICAL_RESAMPLES)


def _month_iter(start_ym: str, end_ym: str) -> list[str]:
    current = datetime.strptime(start_ym, "%Y-%m")
    end = datetime.strptime(end_ym, "%Y-%m")
    months: list[str] = []
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return months


def _raw_root(user_data_dir: Path) -> Path:
    return user_data_dir / "data" / "crypto" / "binance_futures_public"


def _universe_manifest_path(user_data_dir: Path, family: str, top_n: int) -> Path:
    return _raw_root(user_data_dir) / "universes" / f"{family}_top_{top_n}.json"


def _monthly_raw_dir(user_data_dir: Path, family: str, symbol: str) -> Path:
    return _raw_root(user_data_dir) / family / normalize_symbol(symbol) / "1m"


def _public_prefix(family: str) -> str:
    normalized = normalize_family(family)
    return "um" if normalized == "usdm" else "cm"


def _zip_url(family: str, symbol: str, interval: str, month: str) -> str:
    normalized = normalize_family(family)
    sym = normalize_symbol(symbol)
    fname = f"{sym}-{interval}-{month}.zip"
    rel = f"data/futures/{_public_prefix(normalized)}/monthly/klines/{sym}/{interval}/{fname}"
    return urljoin(BINANCE_PUBLIC_BASE, rel)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet_or_csv(df: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    materialized = df.copy()
    if isinstance(materialized.index, pd.DatetimeIndex):
        materialized.index.name = "timestamp"
        materialized = materialized.reset_index()
    try:
        materialized.to_parquet(target, index=False)
        return target
    except Exception:
        csv_path = target.with_suffix(".csv")
        materialized.to_csv(csv_path, index=False)
        return csv_path


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _generated_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_kline_zip(zip_path: Path) -> pd.DataFrame:
    with ZipFile(zip_path, "r") as zf:
        members = [name for name in zf.namelist() if name.lower().endswith(".csv")]
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
            "aux_1",
            "aux_2",
            "aux_3",
            "aux_4",
            "ignore",
        ],
    )
    if not frame.empty and str(frame.iloc[0, 0]).strip().lower() == "open_time":
        frame = frame.iloc[1:].reset_index(drop=True)
    out = frame[["open_time", "open", "high", "low", "close", "volume"]].copy()
    out["open_time"] = pd.to_numeric(out["open_time"], errors="coerce")
    out["timestamp"] = pd.to_datetime(out["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna().drop(columns=["open_time"]).sort_values("timestamp")
    return out[["timestamp", "open", "high", "low", "close", "volume"]]


def _rows_to_dataframe(rows: list[list[Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(frame.iloc[:, 0], unit="ms", utc=True),
            "open": pd.to_numeric(frame.iloc[:, 1], errors="coerce"),
            "high": pd.to_numeric(frame.iloc[:, 2], errors="coerce"),
            "low": pd.to_numeric(frame.iloc[:, 3], errors="coerce"),
            "close": pd.to_numeric(frame.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(frame.iloc[:, 5], errors="coerce"),
        }
    )
    return out.dropna().sort_values("timestamp")


def _download_binary(session: requests.Session, url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return True
    with session.get(url, timeout=120, stream=True) as res:
        if res.status_code == 404:
            return False
        res.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in res.iter_content(chunk_size=1024 * 128):
                if chunk:
                    fh.write(chunk)
    return True


def _download_text(session: requests.Session, url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    res = session.get(url, timeout=60)
    if res.status_code == 404:
        return False
    res.raise_for_status()
    dest.write_text(str(res.text or ""), encoding="utf-8")
    return True


def _verify_checksum(session: requests.Session, zip_url: str, zip_path: Path, checksum_path: Path) -> bool:
    available = _download_text(session, f"{zip_url}.CHECKSUM", checksum_path)
    if not available:
        raise RuntimeError(f"CHECKSUM file not found for {zip_url}")
    first_line = checksum_path.read_text(encoding="utf-8").strip().splitlines()[0]
    expected = first_line.split()[0].strip().lower()
    actual = _sha256_file(zip_path).lower()
    if expected != actual:
        raise RuntimeError(f"CHECKSUM mismatch for {zip_path.name}: expected {expected}, got {actual}")
    return True


def _month_bounds(month: str) -> tuple[int, int]:
    base = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    _, days_in_month = monthrange(base.year, base.month)
    end = base.replace(day=days_in_month, hour=23, minute=59, second=59, microsecond=999000)
    return int(base.timestamp() * 1000), int(end.timestamp() * 1000)


def _rest_klines_url(family: str) -> str:
    normalized = normalize_family(family)
    return USDM_KLINES_URL if normalized == "usdm" else COINM_KLINES_URL


def _fetch_rest_month(session: requests.Session, family: str, symbol: str, month: str) -> pd.DataFrame:
    start_ms, end_ms = _month_bounds(month)
    url = _rest_klines_url(family)
    rows: list[list[Any]] = []
    current = start_ms
    while current <= end_ms:
        params = {
            "symbol": normalize_symbol(symbol),
            "interval": "1m",
            "startTime": current,
            "endTime": end_ms,
            "limit": 1500,
        }
        res = session.get(url, params=params, timeout=60)
        res.raise_for_status()
        chunk = res.json()
        if not isinstance(chunk, list) or not chunk:
            break
        typed_chunk = [item for item in chunk if isinstance(item, list) and len(item) >= 6]
        if not typed_chunk:
            break
        rows.extend(typed_chunk)
        last_open_time = int(typed_chunk[-1][0])
        next_cursor = last_open_time + 60_000
        if next_cursor <= current:
            break
        current = next_cursor
        if len(typed_chunk) < 1500:
            break
    return _rows_to_dataframe(rows)


def _fetch_exchange_info(session: requests.Session, family: str) -> dict[str, Any]:
    url = USDM_EXCHANGE_INFO_URL if normalize_family(family) == "usdm" else COINM_EXCHANGE_INFO_URL
    res = session.get(url, timeout=60)
    res.raise_for_status()
    payload = res.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected exchangeInfo payload for {family}")
    return payload


def _fetch_tickers(session: requests.Session, family: str) -> list[dict[str, Any]]:
    url = USDM_TICKER_24H_URL if normalize_family(family) == "usdm" else COINM_TICKER_24H_URL
    res = session.get(url, timeout=60)
    res.raise_for_status()
    payload = res.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected ticker payload for {family}")
    return [item for item in payload if isinstance(item, dict)]


def _ticker_rank_value(family: str, ticker: dict[str, Any]) -> float:
    normalized = normalize_family(family)
    if normalized == "usdm":
        return _coerce_float(ticker.get("quoteVolume"))
    return _coerce_float(ticker.get("baseVolume")) * _coerce_float(ticker.get("weightedAvgPrice"))


def _ticker_rank_metric_name(family: str) -> str:
    return "quote_volume_24h_usd" if normalize_family(family) == "usdm" else "base_volume_x_weighted_avg_price_24h_usd"


def select_top_symbols(session: requests.Session, family: str, *, top_n: int) -> dict[str, Any]:
    normalized = normalize_family(family)
    info = _fetch_exchange_info(session, normalized)
    tickers = _fetch_tickers(session, normalized)
    ticker_by_symbol = {str(item.get("symbol") or "").upper(): item for item in tickers if str(item.get("symbol") or "").strip()}

    selected: list[dict[str, Any]] = []
    for raw in info.get("symbols") or []:
        if not isinstance(raw, dict):
            continue
        contract_type = str(raw.get("contractType") or "").upper()
        status_key = "status" if normalized == "usdm" else "contractStatus"
        status = str(raw.get(status_key) or "").upper()
        underlying_type = str(raw.get("underlyingType") or "").upper()
        symbol = str(raw.get("symbol") or "").upper()
        if not symbol:
            continue
        if status != "TRADING":
            continue
        if contract_type != "PERPETUAL":
            continue
        if underlying_type and underlying_type != "COIN":
            continue
        ticker = ticker_by_symbol.get(symbol)
        if ticker is None:
            continue
        rank_value = _ticker_rank_value(normalized, ticker)
        if rank_value <= 0:
            continue
        selected.append(
            {
                "symbol": symbol,
                "pair": str(raw.get("pair") or ""),
                "base_asset": str(raw.get("baseAsset") or ""),
                "quote_asset": str(raw.get("quoteAsset") or ""),
                "rank_metric": _ticker_rank_metric_name(normalized),
                "rank_value": rank_value,
                "contract_type": contract_type,
                "status": status,
                "market_family": normalized,
                "weighted_avg_price": _coerce_float(ticker.get("weightedAvgPrice")),
                "quote_volume": _coerce_float(ticker.get("quoteVolume")),
                "base_volume": _coerce_float(ticker.get("baseVolume")),
            }
        )

    selected.sort(key=lambda row: (-float(row["rank_value"]), str(row["symbol"])))
    top_rows = selected[: max(1, top_n)]
    return {
        "market_family": normalized,
        "selection_metric": _ticker_rank_metric_name(normalized),
        "top_n": max(1, top_n),
        "symbols": [str(row["symbol"]) for row in top_rows],
        "items": top_rows,
        "source_endpoints": {
            "exchange_info": USDM_EXCHANGE_INFO_URL if normalized == "usdm" else COINM_EXCHANGE_INFO_URL,
            "ticker_24h": USDM_TICKER_24H_URL if normalized == "usdm" else COINM_TICKER_24H_URL,
        },
        "generated_at": _generated_at_iso(),
    }


def _write_universe_manifest(user_data_dir: Path, *, family: str, top_n: int, payload: dict[str, Any]) -> Path:
    target = _universe_manifest_path(user_data_dir, family, top_n)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def _symbol_bootstrap_plan(
    *,
    family: str,
    symbol: str,
    start_month: str,
    end_month: str,
    resample_timeframes: list[str],
) -> dict[str, Any]:
    return {
        "market": "crypto",
        "market_family": normalize_family(family),
        "symbol": normalize_symbol(symbol),
        "base_interval": "1m",
        "resample_timeframes": list(resample_timeframes),
        "start_month": start_month,
        "end_month": end_month,
    }


def bootstrap_futures_datasets(
    *,
    user_data_dir: Path,
    market_family: str,
    start_month: str,
    end_month: str,
    symbols: list[str] | None = None,
    top_n: int | None = None,
    resample_timeframes: list[str] | tuple[str, ...] | None = None,
    skip_checksum: bool = False,
    allow_rest_fallback: bool = True,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    family = normalize_family(market_family)
    resolved_symbols = [normalize_symbol(symbol) for symbol in (symbols or []) if str(symbol or "").strip()]
    if not resolved_symbols and not top_n:
        raise ValueError("Debe informar symbols o top_n para bootstrap Futures.")
    if resolved_symbols and top_n:
        raise ValueError("Usar symbols o top_n, no ambos.")
    if end_month < start_month:
        raise ValueError("end_month debe ser >= start_month")

    derived_timeframes = normalize_resample_timeframes(list(resample_timeframes or []))
    owned_session = session is None
    current_session = session or requests.Session()
    current_session.headers.update({"User-Agent": "rtlab-futures-bootstrap/1.0"})
    catalog = DataCatalog(user_data_dir)

    universe_payload: dict[str, Any] | None = None
    universe_manifest_path: str | None = None
    if not resolved_symbols and top_n:
        universe_payload = select_top_symbols(current_session, family, top_n=top_n)
        resolved_symbols = [str(symbol) for symbol in universe_payload.get("symbols") or []]
        universe_manifest_path = str(
            runtime_path(_write_universe_manifest(user_data_dir, family=family, top_n=int(universe_payload["top_n"]), payload=universe_payload))
        )

    bootstrapped: list[dict[str, Any]] = []
    months = _month_iter(start_month, end_month)
    try:
        for symbol in resolved_symbols:
            raw_dir = _monthly_raw_dir(user_data_dir, family, symbol)
            monthly_segments: list[dict[str, Any]] = []
            monthly_frames: list[pd.DataFrame] = []
            for month in months:
                zip_url = _zip_url(family, symbol, "1m", month)
                archive_path = raw_dir / Path(zip_url).name
                checksum_path = raw_dir / f"{archive_path.name}.CHECKSUM"
                used_zip = _download_binary(current_session, zip_url, archive_path)
                if used_zip:
                    checksum_valid = False
                    if not skip_checksum:
                        checksum_valid = _verify_checksum(current_session, zip_url, archive_path, checksum_path)
                    segment_df = _read_kline_zip(archive_path)
                    monthly_segments.append(
                        {
                            "month": month,
                            "source_type": "binance_public_zip",
                            "archive_path": str(runtime_path(archive_path)),
                            "archive_url": zip_url,
                            "checksum_file_path": str(runtime_path(checksum_path)) if checksum_path.exists() else "",
                            "checksum_validation_result": bool(checksum_valid) or bool(skip_checksum),
                            "rows": int(len(segment_df)),
                        }
                    )
                    monthly_frames.append(segment_df)
                    continue
                if not allow_rest_fallback:
                    raise RuntimeError(f"Archive not found for {family}/{symbol}/{month}: {zip_url}")
                rest_df = _fetch_rest_month(current_session, family, symbol, month)
                monthly_segments.append(
                    {
                        "month": month,
                        "source_type": "binance_rest_klines",
                        "archive_path": "",
                        "archive_url": "",
                        "checksum_file_path": "",
                        "checksum_validation_result": False,
                        "rows": int(len(rest_df)),
                        "rest_endpoint": _rest_klines_url(family),
                    }
                )
                monthly_frames.append(rest_df)

            base_df = pd.concat(monthly_frames, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            if base_df.empty:
                raise RuntimeError(f"Sin filas descargadas para {family}/{symbol}/1m en {start_month}..{end_month}")
            processed_dir = catalog.processed_dir("crypto")
            base_target = processed_dir / f"{symbol}_1m.parquet"
            actual_base_file = _write_parquet_or_csv(base_df, base_target)
            base_df_indexed = ensure_datetime_index(base_df)
            base_min_ts = base_df_indexed.index.min().isoformat() if not base_df_indexed.empty else ""
            base_max_ts = base_df_indexed.index.max().isoformat() if not base_df_indexed.empty else ""
            base_source_type = "binance_public_zip" if all(
                str(item.get("source_type") or "") == "binance_public_zip" for item in monthly_segments
            ) else "binance_rest_klines"
            zip_segments = [item for item in monthly_segments if str(item.get("source_type") or "") == "binance_public_zip"]
            base_manifest = catalog.write_manifest(
                market="crypto",
                symbol=symbol,
                timeframe="1m",
                source="binance_public",
                start=base_min_ts,
                end=base_max_ts,
                files=[actual_base_file],
                processed_path=actual_base_file,
                extra={
                    "provider": "binance_public",
                    "market_family": family,
                    "source_type": base_source_type,
                    "base_interval": "1m",
                    "derived_interval": None,
                    "generated_at": _generated_at_iso(),
                    "rows": int(len(base_df_indexed)),
                    "min_ts": base_min_ts,
                    "max_ts": base_max_ts,
                    "raw_segments": monthly_segments,
                    "archive_paths": [str(item.get("archive_path") or "") for item in monthly_segments if str(item.get("archive_path") or "")],
                    "checksum_file_paths": [str(item.get("checksum_file_path") or "") for item in monthly_segments if str(item.get("checksum_file_path") or "")],
                    "checksum_validation_result": (
                        all(bool(item.get("checksum_validation_result")) for item in zip_segments) if zip_segments else None
                    ),
                    "dataset_file_hash": _sha256_file(actual_base_file),
                    "selection": _symbol_bootstrap_plan(
                        family=family,
                        symbol=symbol,
                        start_month=start_month,
                        end_month=end_month,
                        resample_timeframes=derived_timeframes,
                    ),
                },
            )

            derived_items: list[dict[str, Any]] = []
            for timeframe in derived_timeframes:
                resampled = resample_ohlcv(base_df, timeframe)
                derived_target = processed_dir / f"{symbol}_{timeframe}.parquet"
                actual_derived_file = _write_parquet_or_csv(resampled, derived_target)
                derived_min_ts = resampled.index.min().isoformat() if not resampled.empty else base_min_ts
                derived_max_ts = resampled.index.max().isoformat() if not resampled.empty else base_max_ts
                derived_manifest = catalog.write_manifest(
                    market="crypto",
                    symbol=symbol,
                    timeframe=timeframe,
                    source="binance_public",
                    start=derived_min_ts,
                    end=derived_max_ts,
                    files=[actual_derived_file],
                    processed_path=actual_derived_file,
                    extra={
                        "provider": "binance_public",
                        "market_family": family,
                        "source_type": base_source_type,
                        "base_interval": "1m",
                        "derived_interval": timeframe,
                        "derived_from": "1m",
                        "generated_at": _generated_at_iso(),
                        "rows": int(len(resampled)),
                        "min_ts": derived_min_ts,
                        "max_ts": derived_max_ts,
                        "dataset_file_hash": _sha256_file(actual_derived_file),
                        "base_manifest_path": str(runtime_path(catalog.manifests_dir("crypto") / f"{symbol}_1m.json")),
                    },
                )
                derived_items.append(
                    {
                        "timeframe": timeframe,
                        "dataset_present": True,
                        "dataset_hash": str(derived_manifest.get("dataset_hash") or ""),
                        "manifest_path": str(runtime_path(catalog.manifests_dir("crypto") / f"{symbol}_{timeframe}.json")),
                        "processed_path": str(runtime_path(actual_derived_file)),
                        "rows": int(len(resampled)),
                    }
                )

            bootstrapped.append(
                {
                    "symbol": symbol,
                    "market_family": family,
                    "dataset_1m_present": True,
                    "dataset_1m_hash": str(base_manifest.get("dataset_hash") or ""),
                    "manifest_1m_path": str(runtime_path(catalog.manifests_dir("crypto") / f"{symbol}_1m.json")),
                    "processed_1m_path": str(runtime_path(actual_base_file)),
                    "rows_1m": int(len(base_df_indexed)),
                    "source_type": base_source_type,
                    "derived": derived_items,
                }
            )
    finally:
        if owned_session:
            current_session.close()

    return {
        "ok": True,
        "provider": "binance_public",
        "market": "crypto",
        "market_family": family,
        "selection_mode": "symbols" if symbols else "top_n",
        "selection_criterion": (
            "status=TRADING + contractType=PERPETUAL + underlyingType=COIN; rank por quoteVolume 24h desc"
            if family == "usdm"
            else "contractStatus=TRADING + contractType=PERPETUAL + underlyingType=COIN; rank por baseVolume*weightedAvgPrice 24h desc"
        ),
        "symbols": resolved_symbols,
        "top_n": int(top_n) if top_n else None,
        "start_month": start_month,
        "end_month": end_month,
        "resample_timeframes": derived_timeframes,
        "user_data_dir": str(runtime_path(user_data_dir)),
        "data_root": str(runtime_path(user_data_dir / "data")),
        "bootstrapped": bootstrapped,
        "data_status": catalog.status(),
        "universe_manifest_path": universe_manifest_path,
        "universe_selection": universe_payload,
    }
