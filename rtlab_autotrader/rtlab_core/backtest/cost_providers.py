from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from .catalog_db import BacktestCatalogDB


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc_now().isoformat()


def _iso_after(*, hours: int = 0, minutes: int = 0) -> str:
    return (_utc_now() + timedelta(hours=hours, minutes=minutes)).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _resolve_policies_root() -> Path:
    project_root = Path(os.getenv("RTLAB_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
    monorepo_root = (project_root.parent if (project_root.parent / "knowledge").exists() else project_root).resolve()
    return (monorepo_root / "config" / "policies").resolve()


def _load_policies_bundle(policies_root: Path | None = None) -> dict[str, Any]:
    root = (policies_root or _resolve_policies_root()).resolve()
    fees = _safe_yaml(root / "fees.yaml")
    micro = _safe_yaml(root / "microstructure.yaml")
    return {"root": str(root), "fees": fees, "microstructure": micro}


@dataclass(slots=True)
class FeeProvider:
    catalog: BacktestCatalogDB
    policies_root: Path | None = None
    session: requests.Session | None = None
    _session: requests.Session | None = None
    _bundle: dict[str, Any] | None = None
    _ttl_hours: int = 6
    _maker_fallback: float = 0.0002
    _taker_fallback: float = 0.0004

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()
        self._bundle = _load_policies_bundle(self.policies_root)
        fees = self._bundle.get("fees") if isinstance(self._bundle.get("fees"), dict) else {}
        f = fees.get("fees") if isinstance(fees.get("fees"), dict) else {}
        fallback = f.get("default_fee_model_if_api_missing") if isinstance(f.get("default_fee_model_if_api_missing"), dict) else {}
        self._ttl_hours = int(f.get("fee_snapshot_ttl_hours") or 6)
        self._maker_fallback = _f(fallback.get("maker_fee"), 0.0002)
        self._taker_fallback = _f(fallback.get("taker_fee"), 0.0004)

    def get_or_create_snapshot(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        explicit_fees_bps: float | None = None,
    ) -> dict[str, Any]:
        cached = self.catalog.latest_valid_fee_snapshot(exchange=exchange, market=market, symbol=symbol)
        if cached:
            return cached
        maker = self._maker_fallback
        taker = self._taker_fallback
        source = "policy_fallback"
        payload: dict[str, Any] = {
            "reason": "No fee endpoint integrado para este entorno; usando fallback persistente.",
            "policies_root": self._bundle.get("root"),
        }
        if explicit_fees_bps is not None:
            payload["explicit_fees_bps_input"] = _f(explicit_fees_bps, 0.0)
        return self.catalog.insert_fee_snapshot(
            exchange=exchange,
            market=market,
            symbol=symbol,
            maker_fee=maker,
            taker_fee=taker,
            commission_rate=None,
            source=source,
            payload=payload,
            fetched_at=_utc_iso(),
            expires_at=_iso_after(hours=self._ttl_hours),
        )


@dataclass(slots=True)
class FundingProvider:
    catalog: BacktestCatalogDB
    policies_root: Path | None = None
    session: requests.Session | None = None
    _session: requests.Session | None = None
    _bundle: dict[str, Any] | None = None
    _ttl_minutes: int = 60

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()
        self._bundle = _load_policies_bundle(self.policies_root)
        fees = self._bundle.get("fees") if isinstance(self._bundle.get("fees"), dict) else {}
        f = fees.get("fees") if isinstance(fees.get("fees"), dict) else {}
        self._ttl_minutes = int(f.get("funding_snapshot_ttl_minutes") or 60)

    def get_or_create_snapshot(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        explicit_funding_bps: float | None = None,
        is_perp: bool = False,
    ) -> dict[str, Any]:
        cached = self.catalog.latest_valid_funding_snapshot(exchange=exchange, market=market, symbol=symbol)
        if cached:
            return cached
        source = "not_applicable_spot"
        funding_rate: float | None = 0.0
        funding_bps = 0.0
        payload: dict[str, Any] = {
            "reason": "Mercado spot/sin perps; funding=0 por defecto." if not is_perp else "Fallback sin endpoint de funding.",
            "policies_root": self._bundle.get("root"),
        }
        if is_perp:
            source = "explicit_or_fallback"
            funding_bps = _f(explicit_funding_bps, 0.0)
            funding_rate = funding_bps / 10000.0
        elif explicit_funding_bps is not None:
            payload["explicit_funding_bps_input"] = _f(explicit_funding_bps, 0.0)
        return self.catalog.insert_funding_snapshot(
            exchange=exchange,
            market=market,
            symbol=symbol,
            funding_rate=funding_rate,
            funding_bps=funding_bps,
            source=source,
            payload=payload,
            fetched_at=_utc_iso(),
            expires_at=_iso_after(minutes=self._ttl_minutes),
        )


class SpreadModel:
    @staticmethod
    def build_params(
        *,
        market: str,
        explicit_spread_bps: float | None = None,
        bbo_spread_bps: float | None = None,
        is_perp: bool = False,
    ) -> dict[str, Any]:
        fallback_bps = 2.0 if is_perp else 1.0
        if bbo_spread_bps is not None:
            used_bps = _f(bbo_spread_bps, fallback_bps)
            return {
                "mode": "dynamic_bbo",
                "used_bps": round(used_bps, 6),
                "fallback_bps": fallback_bps,
                "source": "bbo",
                "market": str(market),
            }
        return {
            "mode": "static",
            "used_bps": round(_f(explicit_spread_bps, fallback_bps), 6),
            "fallback_bps": fallback_bps,
            "source": "explicit_or_fallback",
            "market": str(market),
        }


class SlippageModel:
    def __init__(self, *, policies_root: Path | None = None) -> None:
        self._bundle = _load_policies_bundle(policies_root)
        micro = self._bundle.get("microstructure") if isinstance(self._bundle.get("microstructure"), dict) else {}
        ms = micro.get("microstructure") if isinstance(micro.get("microstructure"), dict) else {}
        self._vol_guard = ms.get("volatility_guard") if isinstance(ms.get("volatility_guard"), dict) else {}

    def build_params(
        self,
        *,
        market: str,
        explicit_slippage_bps: float | None = None,
        is_perp: bool = False,
        high_volatility: bool = False,
    ) -> dict[str, Any]:
        base_bps = 5.0 if is_perp else 2.0
        explicit = _f(explicit_slippage_bps, base_bps)
        multiplier = 1.0
        reason = "normal"
        if bool(self._vol_guard.get("enabled")) and high_volatility:
            multiplier = 2.0
            reason = "volatility_guard_high_vol"
        used_bps = explicit * multiplier
        return {
            "mode": "dynamic_v2" if multiplier > 1.0 else "static",
            "base_bps_default": base_bps,
            "explicit_bps": explicit,
            "multiplier": multiplier,
            "used_bps": round(used_bps, 6),
            "high_volatility": bool(high_volatility),
            "reason": reason,
            "market": str(market),
        }


class CostModelResolver:
    def __init__(self, *, catalog: BacktestCatalogDB, policies_root: Path | None = None) -> None:
        self.catalog = catalog
        self.policies_root = policies_root
        self.fee_provider = FeeProvider(catalog=catalog, policies_root=policies_root)
        self.funding_provider = FundingProvider(catalog=catalog, policies_root=policies_root)
        self.slippage_model = SlippageModel(policies_root=policies_root)

    @staticmethod
    def _infer_high_volatility(df: Any | None) -> bool:
        try:
            if df is None or "close" not in df.columns:
                return False
            series = df["close"].astype(float).pct_change().dropna()
            if len(series) < 60:
                return False
            recent = float(series.tail(min(len(series), 60)).std() or 0.0)
            baseline = float(series.tail(min(len(series), 390)).std() or 0.0)
            if baseline <= 0:
                return False
            return recent >= (baseline * 3.0)
        except Exception:
            return False

    def resolve(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        costs: dict[str, Any] | None = None,
        df: Any | None = None,
        is_perp: bool = False,
        bbo_spread_bps: float | None = None,
    ) -> dict[str, Any]:
        c = costs if isinstance(costs, dict) else {}
        fees_bps = _f(c.get("fees_bps"), 0.0)
        spread_bps = _f(c.get("spread_bps"), 0.0)
        slippage_bps = _f(c.get("slippage_bps"), 0.0)
        funding_bps = _f(c.get("funding_bps"), 0.0)
        high_vol = self._infer_high_volatility(df)
        fee_snapshot = self.fee_provider.get_or_create_snapshot(
            exchange=exchange,
            market=market,
            symbol=symbol,
            explicit_fees_bps=fees_bps,
        )
        funding_snapshot = self.funding_provider.get_or_create_snapshot(
            exchange=exchange,
            market=market,
            symbol=symbol,
            explicit_funding_bps=funding_bps,
            is_perp=is_perp,
        )
        spread_params = SpreadModel.build_params(
            market=market,
            explicit_spread_bps=spread_bps,
            bbo_spread_bps=bbo_spread_bps,
            is_perp=is_perp,
        )
        slippage_params = self.slippage_model.build_params(
            market=market,
            explicit_slippage_bps=slippage_bps,
            is_perp=is_perp,
            high_volatility=high_vol,
        )
        return {
            "fee_snapshot_id": fee_snapshot.get("snapshot_id"),
            "funding_snapshot_id": funding_snapshot.get("snapshot_id"),
            "fee_snapshot": fee_snapshot,
            "funding_snapshot": funding_snapshot,
            "spread_model_params": spread_params,
            "slippage_model_params": slippage_params,
            "high_volatility": bool(high_vol),
        }
