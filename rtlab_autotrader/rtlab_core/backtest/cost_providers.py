from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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


def _env_binance_credentials() -> tuple[str | None, str | None, str]:
    api_key = os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_TESTNET_API_SECRET")
    base = (
        os.getenv("BINANCE_SPOT_BASE_URL")
        or os.getenv("BINANCE_SPOT_TESTNET_BASE_URL")
        or "https://api.binance.com"
    )
    return api_key, api_secret, base.rstrip("/")


def _env_bybit_credentials() -> tuple[str | None, str | None, str]:
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    base = os.getenv("BYBIT_BASE_URL") or os.getenv("BYBIT_TESTNET_BASE_URL") or "https://api.bybit.com"
    return api_key, api_secret, base.rstrip("/")


def _exchange_key(exchange: str) -> str:
    ex = str(exchange or "").lower().strip()
    if "binance" in ex:
        return "binance"
    if "bybit" in ex:
        return "bybit"
    if "okx" in ex:
        return "okx"
    return ex or "unknown"


def _signed_params(params: dict[str, Any], *, secret: str) -> str:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    signature = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{query}&signature={signature}" if query else f"signature={signature}"


def _try_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


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
    _per_exchange_defaults: dict[str, dict[str, float]] | None = None

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()
        self._bundle = _load_policies_bundle(self.policies_root)
        fees = self._bundle.get("fees") if isinstance(self._bundle.get("fees"), dict) else {}
        f = fees.get("fees") if isinstance(fees.get("fees"), dict) else {}
        fallback = f.get("default_fee_model_if_api_missing") if isinstance(f.get("default_fee_model_if_api_missing"), dict) else {}
        raw_per_ex = f.get("per_exchange_defaults") if isinstance(f.get("per_exchange_defaults"), dict) else {}
        per_ex: dict[str, dict[str, float]] = {}
        for k, v in raw_per_ex.items():
            if not isinstance(v, dict):
                continue
            key = _exchange_key(str(k))
            per_ex[key] = {
                "maker_fee": _f(v.get("maker_fee"), _f(v.get("maker"), 0.0)),
                "taker_fee": _f(v.get("taker_fee"), _f(v.get("taker"), 0.0)),
            }
        self._per_exchange_defaults = per_ex
        self._ttl_hours = int(f.get("fee_snapshot_ttl_hours") or 6)
        self._maker_fallback = _f(fallback.get("maker_fee"), 0.0002)
        self._taker_fallback = _f(fallback.get("taker_fee"), 0.0004)

    def _fallback_for_exchange(self, *, exchange: str) -> tuple[float, float]:
        key = _exchange_key(exchange)
        by_env_maker = os.getenv(f"{key.upper()}_MAKER_FEE")
        by_env_taker = os.getenv(f"{key.upper()}_TAKER_FEE")
        if by_env_maker is not None and by_env_taker is not None:
            return _f(by_env_maker, self._maker_fallback), _f(by_env_taker, self._taker_fallback)
        node = (self._per_exchange_defaults or {}).get(key) or {}
        maker = _f(node.get("maker_fee"), self._maker_fallback)
        taker = _f(node.get("taker_fee"), self._taker_fallback)
        return maker, taker

    def _fetch_from_exchange(self, *, exchange: str, symbol: str, market: str = "crypto", is_perp: bool = False) -> tuple[float | None, float | None, dict[str, Any]]:
        ex = _exchange_key(exchange)
        if ex != "binance":
            return None, None, {"reason": "exchange_api_not_implemented_for_fees", "exchange": ex}
        api_key, api_secret, base = _env_binance_credentials()
        if not api_key or not api_secret:
            return None, None, {"reason": "missing_binance_credentials", "base_url": base}
        headers = {"X-MBX-APIKEY": api_key}
        timeout = 5
        attempts: list[dict[str, Any]] = []

        # Endpoint 1: /api/v3/account/commission (spot; signed)
        try:
            params = {"symbol": str(symbol).upper(), "timestamp": int(_utc_now().timestamp() * 1000)}
            query = _signed_params(params, secret=api_secret)
            url = f"{base}/api/v3/account/commission?{query}"
            res = self._session.get(url, headers=headers, timeout=timeout)
            attempts.append({"endpoint": "/api/v3/account/commission", "status_code": int(res.status_code)})
            if res.ok:
                payload = res.json() if res.content else {}
                std = payload.get("standardCommission") if isinstance(payload, dict) else {}
                maker = _try_float((std or {}).get("maker"), None)
                taker = _try_float((std or {}).get("taker"), None)
                if maker is not None and taker is not None:
                    return maker, taker, {"endpoint": "/api/v3/account/commission", "payload": payload}
        except Exception as exc:
            attempts.append({"endpoint": "/api/v3/account/commission", "error": str(exc)})

        # Endpoint 2: /sapi/v1/asset/tradeFee (spot; signed)
        try:
            params = {"symbol": str(symbol).upper(), "timestamp": int(_utc_now().timestamp() * 1000)}
            query = _signed_params(params, secret=api_secret)
            url = f"{base}/sapi/v1/asset/tradeFee?{query}"
            res = self._session.get(url, headers=headers, timeout=timeout)
            attempts.append({"endpoint": "/sapi/v1/asset/tradeFee", "status_code": int(res.status_code)})
            if res.ok:
                payload = res.json() if res.content else {}
                row = payload[0] if isinstance(payload, list) and payload else (payload if isinstance(payload, dict) else {})
                maker = _try_float(row.get("makerCommission"), None)
                taker = _try_float(row.get("takerCommission"), None)
                if maker is not None and taker is not None:
                    return maker, taker, {"endpoint": "/sapi/v1/asset/tradeFee", "payload": payload}
        except Exception as exc:
            attempts.append({"endpoint": "/sapi/v1/asset/tradeFee", "error": str(exc)})
        return None, None, {"reason": "exchange_api_failed", "attempts": attempts, "base_url": base}

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
        maker, taker = self._fallback_for_exchange(exchange=exchange)
        source = "policy_fallback"
        fetched_maker, fetched_taker, fetched_payload = self._fetch_from_exchange(exchange=exchange, symbol=symbol, market=market, is_perp=False)
        payload: dict[str, Any] = {"policies_root": self._bundle.get("root")}
        if fetched_maker is not None and fetched_taker is not None:
            maker = fetched_maker
            taker = fetched_taker
            source = "exchange_api"
            payload["exchange_fetch"] = fetched_payload
        else:
            payload["reason"] = "No se pudo obtener fee real por endpoint; usando fallback persistente."
            payload["exchange_fetch"] = fetched_payload
            payload["fallback_by_exchange"] = {"maker_fee": maker, "taker_fee": taker, "exchange": _exchange_key(exchange)}
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

    def _fetch_binance(self, *, symbol: str) -> tuple[float | None, dict[str, Any]]:
        base = os.getenv("BINANCE_FUTURES_BASE_URL") or os.getenv("BINANCE_FUTURES_TESTNET_BASE_URL") or "https://fapi.binance.com"
        attempts: list[dict[str, Any]] = []
        timeout = 5
        try:
            url = f"{base.rstrip('/')}/fapi/v1/fundingRate"
            res = self._session.get(url, params={"symbol": str(symbol).upper(), "limit": 1}, timeout=timeout)
            attempts.append({"endpoint": "/fapi/v1/fundingRate", "status_code": int(res.status_code)})
            if res.ok:
                payload = res.json() if res.content else []
                row = payload[0] if isinstance(payload, list) and payload else {}
                funding_rate = _try_float(row.get("fundingRate"), None)
                if funding_rate is not None:
                    return funding_rate, {"endpoint": "/fapi/v1/fundingRate", "payload": payload}
        except Exception as exc:
            attempts.append({"endpoint": "/fapi/v1/fundingRate", "error": str(exc)})
        return None, {"reason": "exchange_api_failed", "attempts": attempts, "base_url": base}

    def _fetch_bybit(self, *, symbol: str, is_perp: bool = True) -> tuple[float | None, dict[str, Any]]:
        base = os.getenv("BYBIT_BASE_URL") or os.getenv("BYBIT_TESTNET_BASE_URL") or "https://api.bybit.com"
        attempts: list[dict[str, Any]] = []
        timeout = 5
        category = "linear" if is_perp else "spot"
        try:
            url = f"{base.rstrip('/')}/v5/market/funding/history"
            res = self._session.get(url, params={"category": category, "symbol": str(symbol).upper(), "limit": 1}, timeout=timeout)
            attempts.append({"endpoint": "/v5/market/funding/history", "status_code": int(res.status_code), "category": category})
            if res.ok:
                payload = res.json() if res.content else {}
                result = payload.get("result") if isinstance(payload, dict) else {}
                rows = result.get("list") if isinstance(result, dict) else []
                row = rows[0] if isinstance(rows, list) and rows else {}
                funding_rate = _try_float(row.get("fundingRate"), None) if isinstance(row, dict) else None
                if funding_rate is not None:
                    return funding_rate, {"endpoint": "/v5/market/funding/history", "payload": payload}
        except Exception as exc:
            attempts.append({"endpoint": "/v5/market/funding/history", "error": str(exc), "category": category})
        return None, {"reason": "exchange_api_failed", "attempts": attempts, "base_url": base}

    def _fetch_from_exchange(self, *, exchange: str, symbol: str, is_perp: bool = False) -> tuple[float | None, dict[str, Any]]:
        ex = _exchange_key(exchange)
        if ex == "binance":
            return self._fetch_binance(symbol=symbol)
        if ex == "bybit":
            return self._fetch_bybit(symbol=symbol, is_perp=is_perp)
        return None, {"reason": "exchange_not_supported", "exchange": ex}

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
            api_rate, api_payload = self._fetch_from_exchange(exchange=exchange, symbol=symbol, is_perp=is_perp)
            payload["exchange_fetch"] = api_payload
            if api_rate is not None:
                funding_rate = float(api_rate)
                funding_bps = float(api_rate) * 10000.0
                source = "exchange_api"
            else:
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
    def _roll_spread_bps(df: Any | None) -> tuple[float | None, dict[str, Any]]:
        try:
            if df is None or "close" not in df.columns:
                return None, {"usable": False, "reason": "missing_close_series"}
            close = df["close"].astype(float).dropna()
            if len(close) < 20:
                return None, {"usable": False, "reason": "insufficient_bars", "bars": int(len(close))}
            dp = close.diff().dropna()
            if len(dp) < 3:
                return None, {"usable": False, "reason": "insufficient_deltas", "bars": int(len(dp))}
            a = dp.iloc[1:].to_numpy(dtype=float)
            b = dp.iloc[:-1].to_numpy(dtype=float)
            if len(a) < 2 or len(b) < 2:
                return None, {"usable": False, "reason": "insufficient_cov_samples", "bars": int(len(a))}
            g1 = float(((a - a.mean()) * (b - b.mean())).mean())
            if g1 >= 0:
                return 0.0, {"usable": False, "reason": "non_negative_autocov", "g1": g1}
            spread_abs = 2.0 * ((-g1) ** 0.5)
            mid = float(close.mean() or 0.0)
            if mid <= 0:
                return None, {"usable": False, "reason": "invalid_mid", "g1": g1}
            spread_bps = (spread_abs / mid) * 10000.0
            return float(max(0.0, spread_bps)), {"usable": True, "g1": g1, "spread_abs": spread_abs, "mid": mid}
        except Exception as exc:
            return None, {"usable": False, "reason": "roll_error", "error": str(exc)}

    @staticmethod
    def build_params(
        *,
        market: str,
        explicit_spread_bps: float | None = None,
        bbo_spread_bps: float | None = None,
        is_perp: bool = False,
        df: Any | None = None,
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
        explicit = _f(explicit_spread_bps, 0.0)
        if explicit > 0:
            return {
                "mode": "static",
                "used_bps": round(explicit, 6),
                "fallback_bps": fallback_bps,
                "source": "explicit_or_fallback",
                "market": str(market),
            }
        roll_bps, roll_meta = SpreadModel._roll_spread_bps(df)
        if roll_bps is not None and roll_bps > 0:
            return {
                "mode": "roll",
                "used_bps": round(roll_bps, 6),
                "fallback_bps": fallback_bps,
                "source": "roll_estimator",
                "market": str(market),
                "roll": roll_meta,
            }
        return {
            "mode": "static",
            "used_bps": round(fallback_bps, 6),
            "fallback_bps": fallback_bps,
            "source": "fallback_default",
            "market": str(market),
            "roll": roll_meta if isinstance(roll_meta, dict) else {},
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
            df=df,
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
