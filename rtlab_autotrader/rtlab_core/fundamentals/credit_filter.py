from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import yaml

from rtlab_core.backtest.catalog_db import BacktestCatalogDB


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc_now().isoformat()


def _f(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _norm_weights(weights: dict[str, Any]) -> dict[str, float]:
    raw = {
        "liquidity": float(_f(weights.get("liquidity"), 40.0) or 40.0),
        "solvency": float(_f(weights.get("solvency"), 30.0) or 30.0),
        "margin_of_safety": float(_f(weights.get("margin_of_safety"), 30.0) or 30.0),
    }
    total = sum(max(0.0, v) for v in raw.values()) or 1.0
    return {k: max(0.0, v) / total for k, v in raw.items()}


def _safe_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _pick(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _pick_float(payload: dict[str, Any], *keys: str) -> float | None:
    return _f(_pick(payload, *keys), None)


STATUS_ORDER: dict[str, int] = {
    "UNKNOWN": 0,
    "WEAK": 1,
    "SPECULATIVE": 1,  # Compat con snapshots legacy.
    "BASIC": 2,
    "STRONG": 3,
    "NOT_APPLICABLE": 4,
}

DEFAULT_MIN_STATUS_BY_MODE: dict[str, str] = {
    "backtest": "BASIC",
    "paper": "STRONG",
    "testnet": "STRONG",
    "live": "STRONG",
}

DEFAULT_FAIL_CLOSED_MODES: set[str] = {"paper", "live"}

REQUIRED_MISSING_CODES: set[str] = {
    "DATA_MISSING_ASOF",
    "DATA_STALE",
    "DATA_MISSING_BALANCE",
    "FUND_BOND_DATA_MISSING",
    "COLLATERAL_BREACH",
    "DATA_SOURCE_REMOTE_ERROR",
}


def _normalize_status(value: str | None) -> str:
    status = str(value or "UNKNOWN").strip().upper()
    if status == "SPECULATIVE":
        return "WEAK"
    return status if status in STATUS_ORDER else "UNKNOWN"


def _status_rank(value: str | None) -> int:
    return int(STATUS_ORDER.get(_normalize_status(value), 0))


def _resolve_repo_root(explicit_policies_root: Path | None = None) -> Path:
    if explicit_policies_root:
        pr = explicit_policies_root.resolve()
        if pr.name.lower() == "policies" and pr.parent.name.lower() == "config":
            return pr.parent.parent.resolve()
        return pr.parent.resolve()
    project_root = Path(os.getenv("RTLAB_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
    return (project_root.parent if (project_root.parent / "knowledge").exists() else project_root).resolve()


def _resolve_policies_root(explicit: Path | None = None) -> Path:
    if explicit:
        return explicit.resolve()
    monorepo_root = _resolve_repo_root(None)
    return (monorepo_root / "config" / "policies").resolve()


class FundamentalsCreditFilter:
    """Filtro fundamentals/credit_filter con score auditable + snapshots."""

    def __init__(self, *, catalog: BacktestCatalogDB, policies_root: Path | None = None) -> None:
        self.catalog = catalog
        self.policies_root = _resolve_policies_root(policies_root)
        self.repo_root = _resolve_repo_root(policies_root)
        raw = _safe_yaml(self.policies_root / "fundamentals_credit_filter.yaml")
        self.policy = raw.get("fundamentals_credit_filter") if isinstance(raw.get("fundamentals_credit_filter"), dict) else {}
        self.data_source = self.policy.get("data_source") if isinstance(self.policy.get("data_source"), dict) else {}

    def _mode_allow_statuses(self, *, instrument_type: str, target_mode: str) -> list[str]:
        by_inst = self.policy.get("policy_by_instrument") if isinstance(self.policy.get("policy_by_instrument"), dict) else {}
        node = by_inst.get(instrument_type) if isinstance(by_inst.get(instrument_type), dict) else {}
        mode_key = {
            "live": "live_allow_statuses",
            "paper": "paper_allow_statuses",
            "testnet": "testnet_allow_statuses",
            "backtest": "backtest_allow_statuses",
        }.get(str(target_mode).lower(), "backtest_allow_statuses")
        vals = node.get(mode_key) if isinstance(node.get(mode_key), list) else []
        return [str(x).upper() for x in vals if str(x).strip()]

    def _local_snapshot_candidates(self, *, market: str, symbol: str) -> list[Path]:
        local_dir_cfg = str(self.data_source.get("local_snapshot_dir") or "user_data/fundamentals").strip()
        base = Path(local_dir_cfg)
        if not base.is_absolute():
            base = (self.repo_root / base).resolve()
        market_n = str(market or "").lower()
        symbol_n = str(symbol or "").upper()
        legacy_base = (self.repo_root / "user_data" / "data" / "fundamentals").resolve()
        out = [
            base / market_n / f"{symbol_n}.json",
            base / market_n / f"{symbol_n.lower()}.json",
            base / f"{market_n}_{symbol_n}.json",
            base / f"{symbol_n}.json",
            legacy_base / market_n / f"{symbol_n}.json",
        ]
        dedup: list[Path] = []
        seen: set[str] = set()
        for p in out:
            key = str(p.resolve()) if not p.is_absolute() else str(p)
            if key in seen:
                continue
            seen.add(key)
            dedup.append(p)
        return dedup

    def _load_local_snapshot(self, *, market: str, symbol: str) -> tuple[dict[str, Any] | None, Path | None]:
        for p in self._local_snapshot_candidates(market=market, symbol=symbol):
            payload = _safe_json(p)
            if isinstance(payload, dict) and payload:
                return payload, p
        return None, None

    def _fetch_remote_snapshot(
        self,
        *,
        market: str,
        symbol: str,
        exchange: str,
        instrument_type: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        remote_cfg = self.data_source.get("remote") if isinstance(self.data_source.get("remote"), dict) else {}
        if not bool(remote_cfg.get("enabled", False)):
            return None, {"reason": "remote_disabled"}
        base_url_env = str(remote_cfg.get("base_url_env") or "FUNDAMENTALS_API_BASE_URL").strip()
        base_url = str(os.getenv(base_url_env, "") or remote_cfg.get("base_url") or "").strip()
        if not base_url:
            return None, {"reason": "missing_base_url", "base_url_env": base_url_env}
        endpoint_tmpl = str(remote_cfg.get("endpoint_template") or "/api/v1/fundamentals/{market}/{symbol}").strip()
        values = {
            "market": quote_plus(str(market or "").lower()),
            "symbol": quote_plus(str(symbol or "").upper()),
            "exchange": quote_plus(str(exchange or "").lower()),
            "instrument_type": quote_plus(str(instrument_type or "").lower()),
        }
        try:
            endpoint = endpoint_tmpl.format(**values)
        except Exception:
            endpoint = f"/api/v1/fundamentals/{values['market']}/{values['symbol']}"
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        timeout = max(1, int(_f(remote_cfg.get("timeout_seconds"), 8) or 8))
        headers: dict[str, str] = {"Accept": "application/json"}
        auth_header_name = str(remote_cfg.get("auth_header_name") or "Authorization").strip()
        auth_header_env = str(remote_cfg.get("auth_header_env") or "FUNDAMENTALS_API_TOKEN").strip()
        auth_header_prefix = str(remote_cfg.get("auth_header_prefix") or "Bearer ").strip()
        auth_token = str(os.getenv(auth_header_env, "") or "").strip()
        if auth_token and auth_header_name:
            headers[auth_header_name] = f"{auth_header_prefix}{auth_token}"
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=timeout) as res:  # noqa: S310
                raw = res.read().decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw else {}
                if isinstance(payload, list):
                    payload = next((x for x in payload if isinstance(x, dict)), {})
                if not isinstance(payload, dict):
                    return None, {"url": url, "reason": "invalid_payload_type"}
                return payload, {"url": url, "http_status": int(getattr(res, "status", 200))}
        except HTTPError as exc:
            return None, {"url": url, "http_status": int(getattr(exc, "code", 0) or 0), "error": str(exc)}
        except URLError as exc:
            return None, {"url": url, "error": str(exc)}
        except Exception as exc:
            return None, {"url": url, "error": str(exc)}

    def _snapshot_version(self) -> str:
        snapshots_cfg = self.policy.get("snapshots") if isinstance(self.policy.get("snapshots"), dict) else {}
        return str(snapshots_cfg.get("snapshot_version") or "v2").strip().lower()

    def get_fundamentals_snapshot_cached(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        instrument_type: str,
        snapshot_version: str,
        asof_ts: str | None = None,
    ) -> dict[str, Any] | None:
        cached = self.catalog.latest_valid_fundamentals_snapshot(
            exchange=str(exchange),
            market=str(market).lower(),
            symbol=str(symbol).upper(),
            as_of=asof_ts,
        )
        if not cached:
            return None
        if str(cached.get("instrument_type") or "").lower() != str(instrument_type or "").lower():
            return None
        payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else {}
        existing_version = str(payload.get("snapshot_version") or "").strip().lower()
        expected_version = str(snapshot_version or "").strip().lower()
        if expected_version:
            if not existing_version:
                return None
            if existing_version != expected_version:
                return None
        return cached

    def evaluate_credit_policy(
        self,
        *,
        snapshot: dict[str, Any],
        mode: str,
        min_status_by_mode: dict[str, str] | None = None,
        fail_closed_modes: set[str] | None = None,
    ) -> dict[str, Any]:
        mode_n = str(mode or "backtest").strip().lower()
        min_map = {**DEFAULT_MIN_STATUS_BY_MODE, **(min_status_by_mode or {})}
        fail_closed = {str(x).strip().lower() for x in (fail_closed_modes or DEFAULT_FAIL_CLOSED_MODES) if str(x).strip()}
        explain = snapshot.get("explain") if isinstance(snapshot.get("explain"), list) else []
        required_missing: list[str] = []
        reasons: list[str] = []
        warnings: list[str] = []

        for row in explain:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip().upper()
            sev = str(row.get("severity") or "").strip().upper()
            if code in REQUIRED_MISSING_CODES or code.startswith("DATA_MISSING_"):
                if code and code not in required_missing:
                    required_missing.append(code)
            if sev == "FAIL":
                msg = str(row.get("message") or code or "").strip()
                if msg:
                    reasons.append(msg)

        base_status = _normalize_status(str(snapshot.get("fund_status") or "UNKNOWN"))
        min_status = _normalize_status(min_map.get(mode_n, "STRONG"))
        enforced = bool(snapshot.get("enforced", False))
        promotion_blocked = False
        allow_trade = bool(snapshot.get("allow_trade", False))
        status_final = base_status

        if not enforced or base_status == "NOT_APPLICABLE":
            allow_trade = True
            promotion_blocked = False
            status_final = "NOT_APPLICABLE" if base_status == "NOT_APPLICABLE" else base_status
        elif mode_n == "backtest" and required_missing:
            allow_trade = True
            promotion_blocked = True
            status_final = "UNKNOWN"
            warnings.append("fundamentals_missing")
            reasons.append("BACKTEST autorizado con OHLC-only: faltan fundamentals requeridos.")
        elif required_missing and mode_n in fail_closed:
            allow_trade = False
            promotion_blocked = True
            status_final = "UNKNOWN"
            reasons.append(f"{mode_n.upper()} bloqueado por faltantes requeridos de fundamentals (fail-closed).")
        else:
            allow_trade = _status_rank(base_status) >= _status_rank(min_status)
            promotion_blocked = not allow_trade
            if not allow_trade:
                reasons.append(
                    f"Estado fundamentals {base_status} por debajo del minimo {min_status} para {mode_n.upper()}."
                )

        if promotion_blocked and "fundamentals_missing" not in warnings and required_missing:
            warnings.append("fundamentals_missing")

        fundamentals_quality = "ohlc_only" if "fundamentals_missing" in warnings else "snapshot"
        return {
            "allow_trade": bool(allow_trade),
            "fund_status": status_final,
            "required_missing": required_missing,
            "promotion_blocked": bool(promotion_blocked),
            "warnings": warnings,
            "reasons": reasons,
            "fundamentals_quality": fundamentals_quality,
        }

    def evaluate(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        instrument_type: str = "other",
        target_mode: str = "backtest",
        asof_date: str | None = None,
        source: str = "unknown",
        source_id: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        current_assets: float | None = None,
        current_liabilities: float | None = None,
        bonds_outstanding: float | None = None,
        total_debt: float | None = None,
        price: float | None = None,
        fair_value: float | None = None,
        portfolio_market_value: float | None = None,
        debt_amount: float | None = None,
        waiver_active: bool | None = None,
    ) -> dict[str, Any]:
        market_n = str(market or "").lower()
        symbol_n = str(symbol or "").upper()
        instr_n = str(instrument_type or "other").lower()
        mode_n = str(target_mode or "backtest").lower()
        enabled = bool(self.policy.get("enabled", False))
        fail_closed = bool(self.policy.get("fail_closed", True))
        apply_markets = [str(x).lower() for x in (self.policy.get("apply_markets") or ["equities"]) if str(x).strip()]
        snapshots_cfg = self.policy.get("snapshots") if isinstance(self.policy.get("snapshots"), dict) else {}
        persist_snapshots = bool(snapshots_cfg.get("persist", True))
        ttl_hours = int(_f(snapshots_cfg.get("snapshot_ttl_hours"), 24) or 24)
        snapshot_version = self._snapshot_version()
        min_status_by_mode = DEFAULT_MIN_STATUS_BY_MODE.copy()
        fail_closed_modes = set(DEFAULT_FAIL_CLOSED_MODES if fail_closed else set())

        if not enabled:
            return {
                "enabled": False,
                "enforced": False,
                "snapshot_id": None,
                "allow_trade": True,
                "risk_multiplier": 1.0,
                "fund_score": 100.0,
                "fund_status": "DISABLED",
                "explain": [{"code": "DISABLED", "severity": "INFO", "message": "fundamentals_credit_filter deshabilitado"}],
                "reasons": [],
                "required_missing": [],
                "promotion_blocked": False,
                "warnings": [],
                "fundamentals_quality": "snapshot",
            }

        cached = self.get_fundamentals_snapshot_cached(
            exchange=str(exchange),
            market=market_n,
            symbol=symbol_n,
            instrument_type=instr_n,
            snapshot_version=snapshot_version,
            asof_ts=asof_date,
        )
        if cached:
            decision = self.evaluate_credit_policy(
                snapshot=cached,
                mode=mode_n,
                min_status_by_mode=min_status_by_mode,
                fail_closed_modes=fail_closed_modes,
            )
            payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else {}
            source_ref = payload.get("source_ref") if isinstance(payload.get("source_ref"), dict) else {}
            return {
                "enabled": True,
                "enforced": bool(cached.get("enforced", False)),
                "snapshot_id": cached.get("snapshot_id"),
                "allow_trade": bool(decision.get("allow_trade", False)),
                "risk_multiplier": float(cached.get("risk_multiplier") or 1.0),
                "fund_score": float(cached.get("fund_score") or 0.0),
                "fund_status": str(decision.get("fund_status") or "UNKNOWN"),
                "explain": list(cached.get("explain") or []),
                "source_ref": source_ref,
                "reasons": decision.get("reasons") if isinstance(decision.get("reasons"), list) else [],
                "required_missing": decision.get("required_missing") if isinstance(decision.get("required_missing"), list) else [],
                "promotion_blocked": bool(decision.get("promotion_blocked", False)),
                "warnings": decision.get("warnings") if isinstance(decision.get("warnings"), list) else [],
                "fundamentals_quality": str(decision.get("fundamentals_quality") or "snapshot"),
            }

        local_payload: dict[str, Any] | None = None
        local_path: Path | None = None
        remote_payload: dict[str, Any] | None = None
        remote_meta: dict[str, Any] = {}
        raw = raw_payload if isinstance(raw_payload, dict) else {}
        auto_local = bool(self.data_source.get("auto_load_when_source_unknown", True))
        source_n = str(source or "").strip().lower()
        explicit_remote = source_n in {"remote", "remote_snapshot"}
        explicit_local = source_n in {"local", "local_snapshot"}
        auto_mode = source_n in {"", "unknown", "auto", "runtime_policy", "research_batch"}
        if explicit_remote or auto_mode:
            remote_payload, remote_meta = self._fetch_remote_snapshot(
                market=market_n,
                symbol=symbol_n,
                exchange=str(exchange or ""),
                instrument_type=instr_n,
            )
            if remote_payload:
                source = "remote_snapshot"
                source_id = source_id or str(_pick(remote_payload, "source_id", "id", "provider_id") or f"{market_n}:{symbol_n}")
                asof_date = asof_date or str(_pick(remote_payload, "asof_date", "as_of", "date", "timestamp") or "")
                if not raw:
                    raw = dict(remote_payload)
                current_assets = current_assets if current_assets is not None else _pick_float(remote_payload, "current_assets", "total_current_assets")
                current_liabilities = (
                    current_liabilities if current_liabilities is not None else _pick_float(remote_payload, "current_liabilities", "total_current_liabilities")
                )
                bonds_outstanding = bonds_outstanding if bonds_outstanding is not None else _pick_float(remote_payload, "bonds_outstanding", "total_bonds_outstanding")
                total_debt = total_debt if total_debt is not None else _pick_float(remote_payload, "total_debt", "debt_total")
                price = price if price is not None else _pick_float(remote_payload, "price", "last_price", "close")
                fair_value = fair_value if fair_value is not None else _pick_float(remote_payload, "fair_value", "intrinsic_value")
                portfolio_market_value = (
                    portfolio_market_value if portfolio_market_value is not None else _pick_float(remote_payload, "portfolio_market_value", "collateral_value")
                )
                debt_amount = debt_amount if debt_amount is not None else _pick_float(remote_payload, "debt_amount", "loan_amount")
                if waiver_active is None and _pick(remote_payload, "waiver_active", "covenant_waiver_active") is not None:
                    waiver_active = bool(_pick(remote_payload, "waiver_active", "covenant_waiver_active"))

        if local_payload is None and (explicit_local or (auto_local and auto_mode and not remote_payload)):
            local_payload, local_path = self._load_local_snapshot(market=market_n, symbol=symbol_n)
            if local_payload:
                source = "local_snapshot"
                source_id = source_id or str(local_payload.get("source_id") or f"{market_n}:{symbol_n}")
                asof_date = asof_date or str(local_payload.get("asof_date") or "")
                if not raw:
                    raw = dict(local_payload)
                current_assets = current_assets if current_assets is not None else _f(local_payload.get("current_assets"), None)
                current_liabilities = current_liabilities if current_liabilities is not None else _f(local_payload.get("current_liabilities"), None)
                bonds_outstanding = bonds_outstanding if bonds_outstanding is not None else _f(local_payload.get("bonds_outstanding"), None)
                total_debt = total_debt if total_debt is not None else _f(local_payload.get("total_debt"), None)
                price = price if price is not None else _f(local_payload.get("price"), None)
                fair_value = fair_value if fair_value is not None else _f(local_payload.get("fair_value"), None)
                portfolio_market_value = (
                    portfolio_market_value if portfolio_market_value is not None else _f(local_payload.get("portfolio_market_value"), None)
                )
                debt_amount = debt_amount if debt_amount is not None else _f(local_payload.get("debt_amount"), None)
                if waiver_active is None and "waiver_active" in local_payload:
                    waiver_active = bool(local_payload.get("waiver_active"))

        source_ref = {
            "source": str(source or "unknown"),
            "source_id": str(source_id or ""),
            "asof_date": str(asof_date or ""),
        }
        if local_path is not None:
            source_ref["source_path"] = str(local_path)
        if remote_meta:
            if remote_meta.get("url"):
                source_ref["source_url"] = str(remote_meta.get("url"))
            if remote_meta.get("http_status") is not None:
                source_ref["source_http_status"] = remote_meta.get("http_status")
        explain: list[dict[str, Any]] = []
        enforced = market_n in apply_markets
        if explicit_remote and not remote_payload:
            explain.append(
                {
                    "code": "DATA_SOURCE_REMOTE_ERROR",
                    "severity": "WARN",
                    "metric": "remote_fetch",
                    "value": remote_meta,
                    "threshold": "HTTP 200 + JSON dict",
                    "message": "No se pudo cargar snapshot remoto de fundamentals.",
                    "source_ref": source_ref,
                }
            )
        if remote_payload is not None:
            explain.append(
                {
                    "code": "DATA_SOURCE_REMOTE_SNAPSHOT",
                    "severity": "INFO",
                    "metric": "source_url",
                    "value": str((remote_meta or {}).get("url") or ""),
                    "threshold": "endpoint remoto",
                    "message": "Fundamentals cargado desde snapshot remoto.",
                    "source_ref": source_ref,
                }
            )
        if local_payload is not None and local_path is not None:
            explain.append(
                {
                    "code": "DATA_SOURCE_LOCAL_SNAPSHOT",
                    "severity": "INFO",
                    "metric": "source_path",
                    "value": str(local_path),
                    "threshold": "snapshot JSON",
                    "message": "Fundamentals cargado desde snapshot local.",
                    "source_ref": source_ref,
                }
            )

        if not enforced:
            status = "NOT_APPLICABLE"
            score = 100.0
            allow_trade = True
            risk_multiplier = 1.0
            explain.append(
                {
                    "code": "NO_APLICA_MERCADO",
                    "severity": "INFO",
                    "metric": "market",
                    "value": market_n,
                    "threshold": apply_markets,
                    "message": "Filtro fundamentals no aplica para este mercado.",
                    "source_ref": source_ref,
                }
            )
        else:
            thresholds = ((self.policy.get("scoring") or {}).get("thresholds") or {}) if isinstance((self.policy.get("scoring") or {}).get("thresholds"), dict) else {}
            weights = _norm_weights(((self.policy.get("scoring") or {}).get("weights") or {}) if isinstance((self.policy.get("scoring") or {}).get("weights"), dict) else {})
            current_ratio_min = float(_f(thresholds.get("current_ratio_min"), 2.0) or 2.0)
            wc_to_bo_min = float(_f(thresholds.get("working_capital_to_bonds_outstanding_min"), 1.0) or 1.0)
            freshness_max_days = int(_f(self.policy.get("freshness_max_days"), 120) or 120)

            asof_dt: datetime | None = None
            if asof_date:
                try:
                    asof_dt = datetime.fromisoformat(str(asof_date).replace("Z", "+00:00"))
                    if asof_dt.tzinfo is None:
                        asof_dt = asof_dt.replace(tzinfo=timezone.utc)
                    asof_dt = asof_dt.astimezone(timezone.utc)
                except Exception:
                    asof_dt = None
            freshness_days = None if asof_dt is None else max(0, int((_utc_now() - asof_dt).days))

            ca = _f(current_assets, None)
            cl = _f(current_liabilities, None)
            bo = _f(bonds_outstanding, _f(total_debt, None))
            discount_pct = None
            if fair_value is not None and price is not None and float(fair_value) > 0:
                discount_pct = max(0.0, (float(fair_value) - float(price)) / float(fair_value))

            hard_fail = False
            if asof_dt is None:
                hard_fail = True
                explain.append(
                    {
                        "code": "DATA_MISSING_ASOF",
                        "severity": "FAIL",
                        "metric": "asof_date",
                        "value": asof_date,
                        "threshold": f"<= {freshness_max_days} dias",
                        "message": "Falta fecha asof_date para snapshot fundamentals.",
                        "source_ref": source_ref,
                    }
                )
            if freshness_days is not None and freshness_days > freshness_max_days:
                hard_fail = True
                explain.append(
                    {
                        "code": "DATA_STALE",
                        "severity": "FAIL",
                        "metric": "freshness_days",
                        "value": freshness_days,
                        "threshold": freshness_max_days,
                        "message": "Snapshot fundamentals vencido.",
                        "source_ref": source_ref,
                    }
                )

            if instr_n in {"common", "preferred", "bond"} and (ca is None or cl is None):
                hard_fail = True
                explain.append(
                    {
                        "code": "DATA_MISSING_BALANCE",
                        "severity": "FAIL",
                        "metric": "current_assets/current_liabilities",
                        "value": {"current_assets": ca, "current_liabilities": cl},
                        "threshold": "campos obligatorios",
                        "message": "Faltan campos de balance para evaluar liquidez.",
                        "source_ref": source_ref,
                    }
                )

            current_ratio = None
            wc = None
            wc_to_bo = None
            if ca is not None and cl is not None:
                wc = float(ca - cl)
                if cl > 0:
                    current_ratio = float(ca / cl)
            if wc is not None and bo is not None and bo > 0:
                wc_to_bo = float(wc / bo)

            liquidity_score = 0.0
            if current_ratio is not None:
                if current_ratio >= current_ratio_min:
                    liquidity_score = 100.0
                    sev = "INFO"
                    code = "CR_OK"
                elif current_ratio >= 1.0:
                    liquidity_score = 60.0
                    sev = "WARN"
                    code = "CR_WARN"
                else:
                    liquidity_score = 20.0
                    sev = "FAIL"
                    code = "CR_FAIL"
                explain.append(
                    {
                        "code": code,
                        "severity": sev,
                        "metric": "current_ratio",
                        "value": round(current_ratio, 6),
                        "threshold": current_ratio_min,
                        "message": "Current Ratio evaluado.",
                        "source_ref": source_ref,
                    }
                )

            solvency_score = 0.0
            if wc_to_bo is not None:
                if wc_to_bo >= wc_to_bo_min:
                    solvency_score = 100.0
                    sev = "INFO"
                    code = "WC_OK"
                elif wc_to_bo >= 0.8:
                    solvency_score = 60.0
                    sev = "WARN"
                    code = "WC_WARN"
                else:
                    solvency_score = 20.0
                    sev = "FAIL"
                    code = "WC_FAIL"
                explain.append(
                    {
                        "code": code,
                        "severity": sev,
                        "metric": "working_capital_to_bonds_outstanding",
                        "value": round(wc_to_bo, 6),
                        "threshold": wc_to_bo_min,
                        "message": "Cobertura de capital de trabajo vs deuda.",
                        "source_ref": source_ref,
                    }
                )

            mos_score = 50.0
            if discount_pct is not None:
                thr = _f(thresholds.get("discount_pct"), None)
                if thr is not None:
                    mos_score = 100.0 if discount_pct >= float(thr) else (60.0 if discount_pct >= float(thr) * 0.5 else 30.0)
                    explain.append(
                        {
                            "code": "MOS_CHECK",
                            "severity": "INFO" if mos_score >= 60 else "WARN",
                            "metric": "discount_pct",
                            "value": round(discount_pct, 6),
                            "threshold": float(thr),
                            "message": "Margen de seguridad por descuento vs valor justo.",
                            "source_ref": source_ref,
                        }
                    )
                else:
                    explain.append(
                        {
                            "code": "MOS_TODO",
                            "severity": "INFO",
                            "metric": "discount_pct",
                            "value": round(discount_pct, 6),
                            "threshold": None,
                            "message": "discount_pct no definido en policy (TODO).",
                            "source_ref": source_ref,
                        }
                    )

            if instr_n == "preferred":
                preferred_cfg = (((self.policy.get("policy_by_instrument") or {}).get("preferred")) or {}) if isinstance(((self.policy.get("policy_by_instrument") or {}).get("preferred")), dict) else {}
                if bool(preferred_cfg.get("treat_as_speculative_default", True)):
                    explain.append(
                        {
                            "code": "PREFERRED_SPECULATIVE_DEFAULT",
                            "severity": "WARN",
                            "metric": "instrument_type",
                            "value": instr_n,
                            "threshold": "firm_requirements",
                            "message": "Preferred tratada como especulativa por defecto.",
                            "source_ref": source_ref,
                        }
                    )
                    liquidity_score = min(liquidity_score, 50.0)
                    solvency_score = min(solvency_score, 50.0)
                    mos_score = min(mos_score, 50.0)

            if instr_n == "fund_bond":
                cfg_fund = (((self.policy.get("policy_by_instrument") or {}).get("fund_bond")) or {}) if isinstance(((self.policy.get("policy_by_instrument") or {}).get("fund_bond")), dict) else {}
                buffer_pct = float(_f(cfg_fund.get("collateral_buffer_pct"), 0.25) or 0.25)
                pmv = _f(portfolio_market_value, None)
                debt = _f(debt_amount, None)
                if pmv is None or debt is None or debt <= 0:
                    hard_fail = True
                    explain.append(
                        {
                            "code": "FUND_BOND_DATA_MISSING",
                            "severity": "FAIL",
                            "metric": "portfolio_market_value/debt_amount",
                            "value": {"portfolio_market_value": pmv, "debt_amount": debt},
                            "threshold": "campos obligatorios",
                            "message": "Faltan datos de colateral para fund_bond.",
                            "source_ref": source_ref,
                        }
                    )
                else:
                    required = debt * (1.0 + buffer_pct)
                    ok = pmv >= required
                    explain.append(
                        {
                            "code": "COLLATERAL_OK" if ok else "COLLATERAL_BREACH",
                            "severity": "INFO" if ok else "FAIL",
                            "metric": "portfolio_market_value",
                            "value": round(pmv, 6),
                            "threshold": round(required, 6),
                            "message": "Buffer de colateral evaluado.",
                            "source_ref": source_ref,
                        }
                    )
                    if not ok:
                        hard_fail = True
                        mos_score = min(mos_score, 20.0)

            score = (
                weights["liquidity"] * liquidity_score
                + weights["solvency"] * solvency_score
                + weights["margin_of_safety"] * mos_score
            )
            score = round(max(0.0, min(100.0, score)), 6)

            if hard_fail and fail_closed:
                status = "UNKNOWN"
                risk_multiplier = 0.0
            else:
                if score >= 80:
                    status = "STRONG"
                elif score >= 60:
                    status = "BASIC"
                elif score > 0:
                    status = "WEAK"
                else:
                    status = "UNKNOWN"
                risk_multiplier = (
                    1.0
                    if status == "STRONG"
                    else 0.7
                    if status == "BASIC"
                    else 0.4
                    if status == "WEAK"
                    else 0.0
                )

            if waiver_active:
                explain.append(
                    {
                        "code": "COV_WAIVER",
                        "severity": "WARN",
                        "metric": "waiver_active",
                        "value": True,
                        "threshold": False,
                        "message": "Waiver activo detectado en covenants.",
                        "source_ref": source_ref,
                    }
                )

        raw_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        source_ref["raw_payload_hash"] = raw_hash
        fetched_at = _utc_iso()
        expires_at = (_utc_now() + timedelta(hours=max(1, ttl_hours))).isoformat()
        payload = {
            "market": market_n,
            "symbol": symbol_n,
            "instrument_type": instr_n,
            "snapshot_version": snapshot_version,
            "source_ref": source_ref,
            "policy": self.policy,
            "raw": raw,
        }

        # Snapshot guarda solo datos + scoring base; la decisión final se calcula por modo.
        base_allow_trade = _status_rank(status) >= _status_rank("BASIC")
        snapshot: dict[str, Any] = {
            "snapshot_id": None,
            "exchange": str(exchange).lower(),
            "market": market_n,
            "symbol": symbol_n,
            "instrument_type": instr_n,
            "source": str(source_ref.get("source") or "unknown"),
            "source_id": str(source_ref.get("source_id") or ""),
            "asof_date": str(source_ref.get("asof_date") or ""),
            "raw_payload_hash": str(raw_hash),
            "payload": payload,
            "explain": explain,
            "fund_score": float(score),
            "fund_status": str(status),
            "allow_trade": bool(base_allow_trade),
            "risk_multiplier": float(risk_multiplier),
            "fetched_at": fetched_at,
            "expires_at": expires_at,
            "enforced": bool(enforced),
        }
        if persist_snapshots:
            snap = self.catalog.insert_fundamentals_snapshot(
                exchange=str(exchange),
                market=market_n,
                symbol=symbol_n,
                instrument_type=instr_n,
                source=str(source_ref.get("source") or "unknown"),
                source_id=str(source_ref.get("source_id") or ""),
                asof_date=str(source_ref.get("asof_date") or ""),
                raw_payload_hash=str(raw_hash),
                payload=payload,
                explain=explain,
                fund_score=float(score),
                fund_status=str(status),
                allow_trade=bool(base_allow_trade),
                risk_multiplier=float(risk_multiplier),
                fetched_at=fetched_at,
                expires_at=expires_at,
                enforced=bool(enforced),
            )
            if isinstance(snap, dict):
                snapshot = snap

        decision = self.evaluate_credit_policy(
            snapshot=snapshot,
            mode=mode_n,
            min_status_by_mode=min_status_by_mode,
            fail_closed_modes=fail_closed_modes,
        )

        return {
            "enabled": True,
            "enforced": bool(enforced),
            "snapshot_id": snapshot.get("snapshot_id"),
            "allow_trade": bool(decision.get("allow_trade", False)),
            "risk_multiplier": float(snapshot.get("risk_multiplier") or 0.0),
            "fund_score": float(score),
            "fund_status": str(decision.get("fund_status") or "UNKNOWN"),
            "explain": explain,
            "source_ref": source_ref,
            "reasons": decision.get("reasons") if isinstance(decision.get("reasons"), list) else [],
            "required_missing": decision.get("required_missing") if isinstance(decision.get("required_missing"), list) else [],
            "promotion_blocked": bool(decision.get("promotion_blocked", False)),
            "warnings": decision.get("warnings") if isinstance(decision.get("warnings"), list) else [],
            "fundamentals_quality": str(decision.get("fundamentals_quality") or "snapshot"),
        }
