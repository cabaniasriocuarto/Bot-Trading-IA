from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not path.exists() or not path.is_file():
            continue
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class DatasetResolution:
    mode: str  # dataset | api
    provider: str
    market: str
    symbol: str
    timeframe: str
    dataset_source: str
    dataset_hash: str
    start: str
    end: str
    manifest: dict[str, Any]
    files: list[str]
    public_downloadable: bool
    api_keys_required: bool
    ready: bool
    warnings: list[str]
    hints: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "dataset_source": self.dataset_source,
            "dataset_hash": self.dataset_hash,
            "start": self.start,
            "end": self.end,
            "manifest": self.manifest,
            "files": self.files,
            "public_downloadable": self.public_downloadable,
            "api_keys_required": self.api_keys_required,
            "ready": self.ready,
            "warnings": self.warnings,
            "hints": self.hints,
        }


class DataProvider(Protocol):
    def resolve(self, *, market: str, symbol: str, timeframe: str, start: str, end: str) -> DatasetResolution: ...


class DatasetModeDataProvider:
    def __init__(self, *, user_data_dir: Path, catalog: Any) -> None:
        self.user_data_dir = Path(user_data_dir).resolve()
        self.catalog = catalog

    def _standard_dataset_dir(self, provider: str, market: str, symbol: str, timeframe: str) -> Path:
        return self.user_data_dir / "datasets" / provider / market / symbol / timeframe

    def _standard_manifest(self, provider: str, market: str, symbol: str, timeframe: str) -> Path:
        return self._standard_dataset_dir(provider, market, symbol, timeframe) / "manifest.json"

    def _build_standard_manifest_from_catalog(self, *, provider: str, market: str, symbol: str, timeframe: str, entry: Any) -> dict[str, Any]:
        files = []
        processed_path = str(getattr(entry, "processed_path", "") or "")
        if processed_path:
            files.append(processed_path)
        for f in (getattr(entry, "files", None) or []):
            if isinstance(f, str):
                files.append(f)
        unique_files = [str(Path(f).resolve()) for f in dict.fromkeys(files)]
        payload = {
            "provider": provider,
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "dataset_source": str(getattr(entry, "source", "") or provider),
            "dataset_hash": str(getattr(entry, "dataset_hash", "") or ""),
            "start": str(getattr(entry, "start", "") or ""),
            "end": str(getattr(entry, "end", "") or ""),
            "files": unique_files,
            "manifest_path": str(getattr(entry, "manifest_path", "") or ""),
            "catalog_metadata": getattr(entry, "metadata", None) or {},
        }
        # Recalcular hash combinando archivos + manifest payload si falta hash del catálogo.
        if not payload["dataset_hash"]:
            payload["dataset_hash"] = _sha256_files([Path(x) for x in unique_files]) or hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
        return payload

    def _persist_standard_manifest(self, payload: dict[str, Any]) -> Path:
        provider = str(payload.get("provider") or "unknown")
        market = str(payload.get("market") or "crypto")
        symbol = str(payload.get("symbol") or "BTCUSDT").upper()
        timeframe = str(payload.get("timeframe") or "1m").lower()
        target = self._standard_manifest(provider, market, symbol, timeframe)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def _provider_for_market(self, market: str) -> str:
        mk = str(market).lower()
        if mk == "crypto":
            return "binance_public"
        if mk == "forex":
            return "dukascopy_placeholder"
        if mk == "equities":
            return "alpaca_placeholder"
        return "unknown"

    def _download_hints(self, market: str) -> list[str]:
        mk = str(market).lower()
        if mk == "crypto":
            return [
                "Sin API keys: usar scripts/download_crypto_binance_public.py para descargar Binance Public Data (data.binance.vision).",
                "Luego reintentar el mass backtest en dataset mode.",
            ]
        if mk == "forex":
            return ["Placeholder: agregar downloader de Dukascopy o cargar CSV/Parquet manual en user_data/data/forex."]
        if mk == "equities":
            return ["Placeholder: agregar downloader de Alpaca Market Data o cargar CSV/Parquet manual en user_data/data/equities."]
        return ["Configurar datasets en user_data/data o user_data/datasets antes de correr el mass backtest."]

    def resolve(self, *, market: str, symbol: str, timeframe: str, start: str, end: str) -> DatasetResolution:
        mk = str(market).lower()
        sym = str(symbol).upper()
        tf = str(timeframe).lower()
        provider = self._provider_for_market(mk)
        warnings: list[str] = []
        hints: list[str] = []

        # 1) Intentar carpeta estándar nueva (user_data/datasets/...)
        std_manifest_path = self._standard_manifest(provider, mk, sym, tf)
        if std_manifest_path.exists():
            manifest = _json_load(std_manifest_path, {})
            files = [str(x) for x in (manifest.get("files") or []) if isinstance(x, str)]
            dataset_hash = str(manifest.get("dataset_hash") or "")
            if not dataset_hash:
                dataset_hash = _sha256_files([Path(x) for x in files]) or hashlib.sha256(std_manifest_path.read_bytes()).hexdigest()
                manifest["dataset_hash"] = dataset_hash
                self._persist_standard_manifest(manifest)
            return DatasetResolution(
                mode="dataset",
                provider=provider,
                market=mk,
                symbol=sym,
                timeframe=tf,
                dataset_source=str(manifest.get("dataset_source") or manifest.get("source") or provider),
                dataset_hash=dataset_hash,
                start=str(manifest.get("start") or start),
                end=str(manifest.get("end") or end),
                manifest=manifest,
                files=files,
                public_downloadable=(mk == "crypto"),
                api_keys_required=False,
                ready=True,
                warnings=[],
                hints=[],
            )

        # 2) Fallback a catálogo existente (user_data/data/**/manifests)
        entry = self.catalog.find_entry(mk, sym, tf)
        if entry is None and tf != "1m":
            entry = self.catalog.find_entry(mk, sym, "1m")
            if entry is not None:
                warnings.append(f"No existe dataset {tf} directo; se usará 1m y resample en runtime ({sym}).")
        if entry is not None:
            manifest = self._build_standard_manifest_from_catalog(provider=provider, market=mk, symbol=sym, timeframe=tf, entry=entry)
            self._persist_standard_manifest(manifest)
            return DatasetResolution(
                mode="dataset",
                provider=provider,
                market=mk,
                symbol=sym,
                timeframe=tf,
                dataset_source=str(manifest.get("dataset_source") or provider),
                dataset_hash=str(manifest.get("dataset_hash") or ""),
                start=str(manifest.get("start") or start),
                end=str(manifest.get("end") or end),
                manifest=manifest,
                files=[str(x) for x in (manifest.get("files") or []) if isinstance(x, str)],
                public_downloadable=(mk == "crypto"),
                api_keys_required=False,
                ready=True,
                warnings=warnings,
                hints=[],
            )

        hints.extend(self._download_hints(mk))
        return DatasetResolution(
            mode="dataset",
            provider=provider,
            market=mk,
            symbol=sym,
            timeframe=tf,
            dataset_source=provider,
            dataset_hash="",
            start=start,
            end=end,
            manifest={},
            files=[],
            public_downloadable=(mk == "crypto"),
            api_keys_required=False,
            ready=False,
            warnings=warnings,
            hints=hints,
        )


class ApiModeDataProvider:
    def resolve(self, *, market: str, symbol: str, timeframe: str, start: str, end: str) -> DatasetResolution:
        mk = str(market).lower()
        sym = str(symbol).upper()
        tf = str(timeframe).lower()
        provider = "api_mode_optional"
        return DatasetResolution(
            mode="api",
            provider=provider,
            market=mk,
            symbol=sym,
            timeframe=tf,
            dataset_source=provider,
            dataset_hash="",
            start=start,
            end=end,
            manifest={},
            files=[],
            public_downloadable=False,
            api_keys_required=False,  # para velas públicas puede no requerir; depende del proveedor
            ready=False,
            warnings=["API MODE es opcional y no está implementado para producción en el motor masivo actual."],
            hints=["Usá DATASET MODE (recomendado) con datasets públicos y reproducibles."],
        )


def build_data_provider(*, mode: str, user_data_dir: Path, catalog: Any) -> DataProvider:
    selected = str(mode or "dataset").strip().lower()
    if selected == "api":
        return ApiModeDataProvider()
    return DatasetModeDataProvider(user_data_dir=user_data_dir, catalog=catalog)
