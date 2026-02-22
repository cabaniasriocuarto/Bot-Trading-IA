from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .universes import DEFAULT_SOURCES, MARKET_UNIVERSES, SUPPORTED_MARKETS, SUPPORTED_TIMEFRAMES, normalize_market, normalize_symbol


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_files(paths: list[Path]) -> str:
    digest = sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(slots=True)
class CatalogEntry:
    market: str
    symbol: str
    timeframe: str
    source: str
    start: str
    end: str
    dataset_hash: str
    files: list[str]
    manifest_path: str
    processed_path: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "source": self.source,
            "start": self.start,
            "end": self.end,
            "dataset_hash": self.dataset_hash,
            "files": self.files,
            "manifest_path": self.manifest_path,
            "processed_path": self.processed_path,
            "metadata": self.metadata or {},
        }


class DataCatalog:
    def __init__(self, user_data_dir: Path) -> None:
        self.user_data_dir = user_data_dir.resolve()
        self.data_root = (self.user_data_dir / "data").resolve()

    def manifests_dir(self, market: str) -> Path:
        return self.data_root / normalize_market(market) / "manifests"

    def processed_dir(self, market: str) -> Path:
        return self.data_root / normalize_market(market) / "processed"

    def list_entries(self, market: str | None = None) -> list[CatalogEntry]:
        markets = [normalize_market(market)] if market else list(SUPPORTED_MARKETS)
        out: list[CatalogEntry] = []
        for mk in markets:
            manifests = self.manifests_dir(mk)
            if not manifests.exists():
                continue
            for path in sorted(manifests.glob("*.json")):
                try:
                    payload = _json_load(path)
                    out.append(
                        CatalogEntry(
                            market=str(payload.get("market", mk)),
                            symbol=str(payload.get("symbol", "")).upper(),
                            timeframe=str(payload.get("timeframe", "1m")).lower(),
                            source=str(payload.get("source", DEFAULT_SOURCES.get(mk, "unknown"))),
                            start=str(payload.get("start", "")),
                            end=str(payload.get("end", "")),
                            dataset_hash=str(payload.get("dataset_hash", "")),
                            files=[str(item) for item in payload.get("files", []) if isinstance(item, str)],
                            manifest_path=str(path),
                            processed_path=str(payload.get("processed_path")) if payload.get("processed_path") else None,
                            metadata=payload,
                        )
                    )
                except Exception:
                    continue
        return out

    def find_entry(self, market: str, symbol: str, timeframe: str) -> CatalogEntry | None:
        mk = normalize_market(market)
        sym = normalize_symbol(symbol)
        tf = timeframe.lower()
        for entry in self.list_entries(mk):
            if entry.symbol == sym and entry.timeframe == tf:
                return entry
        return None

    def status(self) -> dict[str, Any]:
        entries = self.list_entries()
        present = {(e.market, e.symbol, e.timeframe) for e in entries}
        missing: list[dict[str, Any]] = []
        for market, symbols in MARKET_UNIVERSES.items():
            for symbol in symbols:
                for tf in SUPPORTED_TIMEFRAMES:
                    if (market, symbol, tf) not in present:
                        missing.append(
                            {
                                "market": market,
                                "symbol": symbol,
                                "timeframe": tf,
                                "hint": f"Descarga datos con scripts/download_{'crypto_binance_public' if market=='crypto' else 'forex_dukascopy' if market=='forex' else 'equities_alpaca'}.py",
                            }
                        )
        return {
            "data_root": str(self.data_root),
            "available_count": len(entries),
            "available": [e.to_dict() for e in entries],
            "missing_count": len(missing),
            "missing": missing,
        }

    def write_manifest(
        self,
        *,
        market: str,
        symbol: str,
        timeframe: str,
        source: str,
        start: str,
        end: str,
        files: list[Path],
        processed_path: Path | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mk = normalize_market(market)
        sym = normalize_symbol(symbol)
        tf = timeframe.lower()
        manifest_dir = self.manifests_dir(mk)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        normalized_files = [Path(p).resolve() for p in files]
        dataset_hash = _sha256_files([p for p in normalized_files if p.exists()])
        payload: dict[str, Any] = {
            "market": mk,
            "symbol": sym,
            "timeframe": tf,
            "source": source,
            "start": start,
            "end": end,
            "files": [str(p) for p in normalized_files],
            "processed_path": str(processed_path.resolve()) if processed_path else None,
            "dataset_hash": dataset_hash,
        }
        if extra:
            payload.update(extra)
        manifest_path = manifest_dir / f"{sym}_{tf}.json"
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

