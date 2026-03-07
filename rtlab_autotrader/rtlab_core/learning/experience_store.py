from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from rtlab_core.learning.brain import deflated_sharpe_ratio
from rtlab_core.strategy_packs.registry_db import RegistryDB


VALID_SOURCES = {"backtest", "shadow", "paper", "testnet"}
VALID_REGIMES = {"trend", "range", "high_vol", "toxic", "unknown"}
SOURCE_WEIGHTS = {
    "shadow": 1.00,
    "testnet": 0.90,
    "paper": 0.80,
    "backtest": 0.60,
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_key(value: Any) -> str:
    dt = _parse_iso(value)
    return dt.date().isoformat() if dt is not None else ""


def _profit_factor(values: list[float]) -> float:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    if gross_loss <= 1e-12:
        return float(gross_profit > 0) * max(gross_profit, 0.0)
    return gross_profit / gross_loss


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += float(value)
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return abs(max_dd)


def _simple_sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    sigma = pstdev(values)
    if sigma <= 1e-12:
        return 0.0
    return (mean(values) / sigma) * math.sqrt(len(values))


def _simple_sortino(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    downside = [min(0.0, v) for v in values]
    sigma = pstdev(downside)
    if sigma <= 1e-12:
        return 0.0
    return (mean(values) / sigma) * math.sqrt(len(values))


def _psr(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    sharpe = _simple_sharpe(values)
    sigma = pstdev(values)
    if sigma <= 1e-12:
        return None
    sr_std = math.sqrt((1.0 + 0.5 * (sharpe**2)) / max(1.0, len(values) - 1.0))
    if sr_std <= 1e-12:
        return None
    return _normal_cdf(sharpe / sr_std)


class ExperienceStore:
    def __init__(self, registry: RegistryDB) -> None:
        self.registry = registry

    @staticmethod
    def source_from_run(run: dict[str, Any], *, override: str | None = None) -> str | None:
        if override:
            source = str(override).strip().lower()
        else:
            mode = str(run.get("mode") or "").strip().lower()
            if mode == "backtest":
                source = "backtest"
            elif mode in VALID_SOURCES:
                source = mode
            else:
                source = None
        return source if source in VALID_SOURCES else None

    @staticmethod
    def source_weight(source: str) -> float:
        return float(SOURCE_WEIGHTS.get(str(source or "").strip().lower(), 0.5))

    @staticmethod
    def _costs_profile_id(run: dict[str, Any]) -> str:
        costs = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
        fee_snapshot = str(run.get("fee_snapshot_id") or "")
        funding_snapshot = str(run.get("funding_snapshot_id") or "")
        if fee_snapshot or funding_snapshot:
            return f"{fee_snapshot}:{funding_snapshot}".strip(":")
        raw = "|".join(
            [
                f"fees={_safe_float(costs.get('fees_bps')):.6f}",
                f"spread={_safe_float(costs.get('spread_bps')):.6f}",
                f"slippage={_safe_float(costs.get('slippage_bps')):.6f}",
                f"funding={_safe_float(costs.get('funding_bps')):.6f}",
                f"rollover={_safe_float(costs.get('rollover_bps')):.6f}",
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _validation_quality(run: dict[str, Any], *, source: str) -> str:
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        dataset_source = str(run.get("data_source") or ((run.get("provenance") or {}).get("dataset_source") if isinstance(run.get("provenance"), dict) else "") or "").lower()
        validation_mode = str(run.get("validation_mode") or "").strip().lower()
        pbo = metrics.get("pbo")
        dsr = metrics.get("dsr")
        if source == "shadow":
            return "shadow_live_market_data"
        if source in {"paper", "testnet"}:
            return "runtime_sandbox"
        if dataset_source in {"dataset", "binance_public", "binance_public_klines"}:
            if validation_mode in {"walk-forward", "purged-cv", "cpcv"}:
                return "research_oos_real_dataset"
            return "research_real_dataset"
        if isinstance(pbo, (int, float)) or isinstance(dsr, (int, float)):
            return "research_validated"
        return "synthetic_or_bootstrap"

    @staticmethod
    def _cost_fidelity_level(run: dict[str, Any], *, source: str) -> str:
        dataset_source = str(run.get("data_source") or ((run.get("provenance") or {}).get("dataset_source") if isinstance(run.get("provenance"), dict) else "") or "").lower()
        if source == "shadow":
            return "runtime_simulated_live_data"
        if source in {"paper", "testnet"}:
            return "sandbox_exchange_costs"
        if dataset_source in {"dataset", "auto", "binance_public"}:
            return "historical_real_dataset"
        return "synthetic_seeded"

    @staticmethod
    def _infer_regime(run: dict[str, Any], trade: dict[str, Any] | None = None) -> str:
        if isinstance(trade, dict):
            raw = str(trade.get("regime_label") or "").strip().lower()
            if raw in VALID_REGIMES:
                return raw
        costs = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        spread_bps = _safe_float(costs.get("spread_bps"))
        slippage_bps = _safe_float(costs.get("slippage_bps"))
        max_dd = abs(_safe_float(metrics.get("max_dd")))
        sharpe = _safe_float(metrics.get("sharpe"))
        vpin = None
        if isinstance(trade, dict):
            vpin = _safe_float(((trade.get("features") or {}) if isinstance(trade.get("features"), dict) else {}).get("vpin"), 0.0)
        if (vpin is not None and vpin >= 0.75) or spread_bps >= 10.0 or slippage_bps >= 8.0:
            return "toxic"
        if max_dd >= 0.15:
            return "high_vol"
        if sharpe >= 0.75:
            return "trend"
        return "range"

    @staticmethod
    def _episode_id(*, run_id: str, source: str, strategy_id: str, asset: str, timeframe: str, dataset_hash: str, feature_set: str) -> str:
        raw = "|".join([run_id, source, strategy_id, asset, timeframe, dataset_hash, feature_set])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _event_id(*, episode_id: str, action: str, ts: str, side: str, ordinal: int) -> str:
        raw = "|".join([episode_id, action, ts, side, str(ordinal)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def record_run(self, run: dict[str, Any], *, source_override: str | None = None, bot_id: str | None = None) -> dict[str, Any] | None:
        source = self.source_from_run(run, override=source_override)
        if source is None:
            return None
        strategy_id = str(run.get("strategy_id") or "").strip()
        run_id = str(run.get("id") or run.get("run_id") or "").strip()
        if not strategy_id or not run_id:
            return None
        asset = str(run.get("symbol") or ((run.get("universe") or [""])[:1][0]) or "").strip().upper()
        timeframe = str(run.get("timeframe") or "5m").strip()
        period = run.get("period") if isinstance(run.get("period"), dict) else {}
        start_ts = str(period.get("start") or run.get("started_at") or run.get("created_at") or "")
        end_ts = str(period.get("end") or run.get("finished_at") or run.get("created_at") or "")
        dataset_source = str(run.get("data_source") or ((run.get("provenance") or {}).get("dataset_source") if isinstance(run.get("provenance"), dict) else "") or "")
        dataset_hash = str(run.get("dataset_hash") or ((run.get("provenance") or {}).get("dataset_hash") if isinstance(run.get("provenance"), dict) else "") or "")
        commit_hash = str(run.get("git_commit") or ((run.get("provenance") or {}).get("commit_hash") if isinstance(run.get("provenance"), dict) else "") or "")
        feature_set = str(run.get("feature_set") or ((run.get("provenance") or {}).get("orderflow_feature_set") if isinstance(run.get("provenance"), dict) else "") or "unknown")
        source_weight = self.source_weight(source)
        episode_id = self._episode_id(
            run_id=run_id,
            source=source,
            strategy_id=strategy_id,
            asset=asset or "UNKNOWN",
            timeframe=timeframe or "unknown",
            dataset_hash=dataset_hash or "na",
            feature_set=feature_set or "unknown",
        )
        trades = run.get("trades") if isinstance(run.get("trades"), list) else []
        summary_metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        summary_costs = run.get("costs_breakdown") if isinstance(run.get("costs_breakdown"), dict) else {}
        summary = {
            "metrics": summary_metrics,
            "costs_breakdown": summary_costs,
            "mode": str(run.get("mode") or ""),
            "bot_id": str(bot_id or ""),
            "feature_set": feature_set,
            "validation_mode": str(run.get("validation_mode") or ""),
            "dataset_source": dataset_source,
            "source_weight": source_weight,
            "trade_count": int(summary_metrics.get("trade_count") or summary_metrics.get("roundtrips") or len(trades)),
            "run_count": 1,
            "orderflow_enabled": bool(run.get("use_orderflow_data", False)),
            "tags": run.get("tags") if isinstance(run.get("tags"), list) else [],
        }
        self.registry.upsert_experience_episode(
            episode_id=episode_id,
            run_id=run_id,
            source=source,
            source_weight=source_weight,
            strategy_id=strategy_id,
            bot_id=str(bot_id or "").strip() or None,
            asset=asset or "UNKNOWN",
            timeframe=timeframe or "unknown",
            start_ts=start_ts or None,
            end_ts=end_ts or None,
            dataset_source=dataset_source or None,
            dataset_hash=dataset_hash or None,
            commit_hash=commit_hash or None,
            costs_profile_id=self._costs_profile_id(run),
            validation_quality=self._validation_quality(run, source=source),
            cost_fidelity_level=self._cost_fidelity_level(run, source=source),
            feature_set=feature_set,
            notes=str(run.get("notes") or ""),
            summary=summary,
            created_at=str(run.get("created_at") or None) if run.get("created_at") else None,
        )
        events = self._build_trade_events(episode_id=episode_id, run=run)
        self.registry.replace_experience_events(episode_id, events)
        self._refresh_regime_kpis(strategy_id)
        self._refresh_strategy_guidance(strategy_id)
        return {
            "episode_id": episode_id,
            "events_count": len(events),
            "source": source,
            "strategy_id": strategy_id,
            "asset": asset,
            "timeframe": timeframe,
        }

    def _build_trade_events(self, *, episode_id: str, run: dict[str, Any]) -> list[dict[str, Any]]:
        trades = run.get("trades") if isinstance(run.get("trades"), list) else []
        decision_events = run.get("decision_events") if isinstance(run.get("decision_events"), list) else []
        events: list[dict[str, Any]] = []
        ordinal = 0
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            regime_label = self._infer_regime(run, trade)
            features = {
                "symbol": str(trade.get("symbol") or run.get("symbol") or ""),
                "timeframe": str(trade.get("timeframe") or run.get("timeframe") or ""),
                "returns": _safe_float(trade.get("pnl_net")),
                "returns_gross": _safe_float(trade.get("pnl")),
                "mfe": _safe_float(trade.get("mfe")),
                "mae": _safe_float(trade.get("mae")),
                "rsi": _safe_float(trade.get("rsi"), default=float("nan")),
                "adx": _safe_float(trade.get("adx"), default=float("nan")),
                "atr": _safe_float(trade.get("atr"), default=float("nan")),
                "vpin": _safe_float(((trade.get("features") or {}) if isinstance(trade.get("features"), dict) else {}).get("vpin"), default=float("nan")),
                "imbalance": _safe_float(((trade.get("features") or {}) if isinstance(trade.get("features"), dict) else {}).get("imbalance"), default=float("nan")),
            }
            features = {k: v for k, v in features.items() if not (isinstance(v, float) and math.isnan(v))}
            side = str(trade.get("side") or "flat").strip().lower()
            entry_ts = str(trade.get("entry_time") or "")
            exit_ts = str(trade.get("exit_time") or "")
            ordinal += 1
            if entry_ts:
                events.append(
                    {
                        "id": self._event_id(episode_id=episode_id, action="enter", ts=entry_ts, side=side, ordinal=ordinal),
                        "ts": entry_ts,
                        "regime_label": regime_label,
                        "features_json": features,
                        "action": "enter",
                        "side": side if side in {"long", "short"} else "flat",
                        "predicted_edge": _safe_float(trade.get("mfe"), 0.0),
                        "realized_pnl_gross": None,
                        "realized_pnl_net": None,
                        "fee": _safe_float(trade.get("fees")),
                        "spread_cost": _safe_float(trade.get("spread_cost")),
                        "slippage_cost": _safe_float(trade.get("slippage_cost")),
                        "funding_cost": _safe_float(trade.get("funding_cost")),
                        "latency_ms": _safe_float(trade.get("latency_ms"), default=0.0) or None,
                        "spread_bps": _safe_float(trade.get("spread_bps"), default=0.0) or None,
                        "vpin_value": _safe_float(((trade.get("features") or {}) if isinstance(trade.get("features"), dict) else {}).get("vpin"), default=0.0) or None,
                        "notes": str(trade.get("reason_code") or "entry"),
                    }
                )
            ordinal += 1
            if exit_ts:
                events.append(
                    {
                        "id": self._event_id(episode_id=episode_id, action="exit", ts=exit_ts, side=side, ordinal=ordinal),
                        "ts": exit_ts,
                        "regime_label": regime_label,
                        "features_json": features,
                        "action": "exit",
                        "side": side if side in {"long", "short"} else "flat",
                        "predicted_edge": None,
                        "realized_pnl_gross": _safe_float(trade.get("pnl")),
                        "realized_pnl_net": _safe_float(trade.get("pnl_net")),
                        "fee": _safe_float(trade.get("fees")),
                        "spread_cost": _safe_float(trade.get("spread_cost")),
                        "slippage_cost": _safe_float(trade.get("slippage_cost")),
                        "funding_cost": _safe_float(trade.get("funding_cost")),
                        "latency_ms": _safe_float(trade.get("latency_ms"), default=0.0) or None,
                        "spread_bps": _safe_float(trade.get("spread_bps"), default=0.0) or None,
                        "vpin_value": _safe_float(((trade.get("features") or {}) if isinstance(trade.get("features"), dict) else {}).get("vpin"), default=0.0) or None,
                        "notes": str(trade.get("exit_reason") or "exit"),
                    }
                )
            raw_events = trade.get("events") if isinstance(trade.get("events"), list) else []
            for raw_event in raw_events:
                if not isinstance(raw_event, dict):
                    continue
                raw_type = str(raw_event.get("type") or "").strip().lower()
                if raw_type not in {"skip", "signal_rejected", "reject"}:
                    continue
                ts = str(raw_event.get("ts") or entry_ts or exit_ts or "")
                ordinal += 1
                events.append(
                    {
                        "id": self._event_id(episode_id=episode_id, action="skip", ts=ts, side=side, ordinal=ordinal),
                        "ts": ts or _utc_iso(),
                        "regime_label": regime_label,
                        "features_json": features,
                        "action": "skip",
                        "side": "flat",
                        "predicted_edge": None,
                        "realized_pnl_gross": None,
                        "realized_pnl_net": None,
                        "fee": 0.0,
                        "spread_cost": 0.0,
                        "slippage_cost": 0.0,
                        "funding_cost": 0.0,
                        "latency_ms": None,
                        "spread_bps": None,
                        "vpin_value": _safe_float(features.get("vpin"), default=0.0) or None,
                        "notes": str(raw_event.get("detail") or raw_type),
                    }
                )
        for raw_event in decision_events:
            if not isinstance(raw_event, dict):
                continue
            action = str(raw_event.get("action") or raw_event.get("type") or "").strip().lower()
            if action not in {"enter", "exit", "hold", "reduce", "add", "skip"}:
                continue
            ts = str(raw_event.get("ts") or raw_event.get("time") or _utc_iso())
            regime_label = str(raw_event.get("regime_label") or "unknown").strip().lower()
            if regime_label not in VALID_REGIMES:
                regime_label = "unknown"
            side = str(raw_event.get("side") or "flat").strip().lower()
            if side not in {"long", "short", "flat"}:
                side = "flat"
            ordinal += 1
            events.append(
                {
                    "id": self._event_id(episode_id=episode_id, action=action, ts=ts, side=side, ordinal=ordinal),
                    "ts": ts,
                    "regime_label": regime_label,
                    "features_json": raw_event.get("features_json") if isinstance(raw_event.get("features_json"), dict) else {},
                    "action": action,
                    "side": side,
                    "predicted_edge": _safe_float(raw_event.get("predicted_edge"), 0.0) if raw_event.get("predicted_edge") is not None else None,
                    "realized_pnl_gross": _safe_float(raw_event.get("realized_pnl_gross"), 0.0) if raw_event.get("realized_pnl_gross") is not None else None,
                    "realized_pnl_net": _safe_float(raw_event.get("realized_pnl_net"), 0.0) if raw_event.get("realized_pnl_net") is not None else None,
                    "fee": _safe_float(raw_event.get("fee")),
                    "spread_cost": _safe_float(raw_event.get("spread_cost")),
                    "slippage_cost": _safe_float(raw_event.get("slippage_cost")),
                    "funding_cost": _safe_float(raw_event.get("funding_cost")),
                    "latency_ms": _safe_float(raw_event.get("latency_ms"), default=0.0) or None,
                    "spread_bps": _safe_float(raw_event.get("spread_bps"), default=0.0) or None,
                    "vpin_value": _safe_float(raw_event.get("vpin_value"), default=0.0) or None,
                    "notes": str(raw_event.get("notes") or raw_event.get("detail") or action),
                }
            )
        return events

    def _refresh_regime_kpis(self, strategy_id: str) -> None:
        episodes = self.registry.list_experience_episodes(strategy_ids=[strategy_id], sources=["backtest", "shadow", "paper", "testnet"])
        if not episodes:
            self.registry.replace_regime_kpis(strategy_id, [])
            return
        episode_ids = [str(row.get("id") or "") for row in episodes if str(row.get("id") or "")]
        events = self.registry.list_experience_events(episode_ids=episode_ids)
        rows_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        pbo_by_group: dict[tuple[str, str, str], list[float]] = {}
        feature_sets: dict[tuple[str, str, str], set[str]] = {}
        for event in events:
            if str(event.get("action") or "") != "exit":
                continue
            regime = str(event.get("regime_label") or "unknown")
            if regime not in VALID_REGIMES:
                regime = "unknown"
            episode = next((row for row in episodes if str(row.get("id") or "") == str(event.get("episode_id") or "")), None)
            asset = str((episode or {}).get("asset") or "")
            timeframe = str((episode or {}).get("timeframe") or "")
            key = (asset, timeframe, regime)
            rows_by_group.setdefault(key, []).append(event)
            summary = (episode or {}).get("summary") if isinstance((episode or {}).get("summary"), dict) else {}
            if isinstance(summary, dict):
                feature_set = str(summary.get("feature_set") or (episode or {}).get("feature_set") or "")
                if feature_set:
                    feature_sets.setdefault(key, set()).add(feature_set)
        for episode in episodes:
            asset = str(episode.get("asset") or "")
            timeframe = str(episode.get("timeframe") or "")
            regime_candidates = []
            for event in events:
                if str(event.get("episode_id") or "") != str(episode.get("id") or "") or str(event.get("action") or "") != "exit":
                    continue
                regime = str(event.get("regime_label") or "unknown")
                regime_candidates.append(regime if regime in VALID_REGIMES else "unknown")
            summary = episode.get("summary") if isinstance(episode.get("summary"), dict) else {}
            pbo_value = (summary.get("metrics") or {}).get("pbo") if isinstance(summary.get("metrics"), dict) else None
            if isinstance(pbo_value, (int, float)):
                for regime in set(regime_candidates or ["unknown"]):
                    key = (asset, timeframe, regime)
                    pbo_by_group.setdefault(key, []).append(float(pbo_value))
        out: list[dict[str, Any]] = []
        for (asset, timeframe, regime), rows in rows_by_group.items():
            pnls = [_safe_float(row.get("realized_pnl_net")) for row in rows if row.get("realized_pnl_net") is not None]
            gross_pnls = [_safe_float(row.get("realized_pnl_gross")) for row in rows if row.get("realized_pnl_gross") is not None]
            if not pnls:
                continue
            ts_values = [str(row.get("ts") or "") for row in rows if str(row.get("ts") or "")]
            days = {key for key in (_day_key(ts) for ts in ts_values) if key}
            pbo_values = pbo_by_group.get((asset, timeframe, regime), [])
            dsr_payload = deflated_sharpe_ratio(pnls, trials=max(1, len(pnls)))
            total_costs = sum(
                _safe_float(row.get("fee"))
                + _safe_float(row.get("spread_cost"))
                + _safe_float(row.get("slippage_cost"))
                + _safe_float(row.get("funding_cost"))
                for row in rows
            )
            gross_abs = abs(sum(gross_pnls)) if gross_pnls else 0.0
            durations = []
            for row in rows:
                notes = str(row.get("notes") or "")
                if notes:
                    pass
            turnover = float(len(rows))
            out.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "regime_label": regime,
                    "period_start": min(ts_values) if ts_values else "",
                    "period_end": max(ts_values) if ts_values else "",
                    "n_trades": len(pnls),
                    "n_days": len(days),
                    "expectancy_net": mean(pnls),
                    "expectancy_gross": mean(gross_pnls) if gross_pnls else 0.0,
                    "profit_factor": _profit_factor(pnls),
                    "sharpe": _simple_sharpe(pnls),
                    "sortino": _simple_sortino(pnls),
                    "max_dd": _max_drawdown(pnls),
                    "hit_rate": sum(1 for pnl in pnls if pnl > 0) / max(1, len(pnls)),
                    "turnover": turnover,
                    "avg_trade_duration": mean(durations) if durations else 0.0,
                    "cost_ratio": 0.0 if gross_abs <= 1e-12 else total_costs / gross_abs,
                    "pbo": mean(pbo_values) if pbo_values else None,
                    "dsr": dsr_payload.get("dsr"),
                    "psr": _psr(pnls),
                    "last_updated": _utc_iso(),
                }
            )
        self.registry.replace_regime_kpis(strategy_id, out)

    def _refresh_strategy_guidance(self, strategy_id: str) -> None:
        rows = self.registry.list_regime_kpis(strategy_id=strategy_id)
        if not rows:
            self.registry.upsert_strategy_policy_guidance(strategy_id=strategy_id, notes="Sin experiencia suficiente.")
            return
        preferred: list[tuple[str, float]] = []
        avoid: list[str] = []
        spreads: list[float] = []
        vpins: list[float] = []
        events = self.registry.list_experience_events(
            episode_ids=[str(row.get("id") or "") for row in self.registry.list_experience_episodes(strategy_ids=[strategy_id])]
        )
        for event in events:
            if isinstance(event.get("spread_bps"), (int, float)):
                spreads.append(float(event["spread_bps"]))
            if isinstance(event.get("vpin_value"), (int, float)):
                vpins.append(float(event["vpin_value"]))
        for row in rows:
            regime = str(row.get("regime_label") or "unknown")
            expectancy_net = _safe_float(row.get("expectancy_net"))
            cost_ratio = _safe_float(row.get("cost_ratio"))
            max_dd = _safe_float(row.get("max_dd"))
            if expectancy_net > 0 and cost_ratio <= 1.0:
                preferred.append((regime, expectancy_net))
            if expectancy_net <= 0 or max_dd >= 0.15:
                avoid.append(regime)
        preferred.sort(key=lambda item: item[1], reverse=True)
        preferred_regimes = [regime for regime, _score in preferred[:3]]
        avoid_regimes = sorted(set(avoid))
        self.registry.upsert_strategy_policy_guidance(
            strategy_id=strategy_id,
            preferred_regimes=preferred_regimes,
            avoid_regimes=avoid_regimes,
            min_confidence_to_recommend=0.35,
            max_risk_multiplier=1.0 if not avoid_regimes else 0.75,
            max_spread_bps_allowed=(mean(spreads) * 1.25) if spreads else None,
            max_vpin_allowed=min(0.95, mean(vpins) * 1.1) if vpins else None,
            cost_stress_result="fail" if any(_safe_float(row.get("expectancy_net")) - (1.5 * _safe_float(row.get("cost_ratio"))) < 0 for row in rows) else "pass",
            notes="Guidance derivada de experiencia neta por régimen (Opción B, no auto-aplica).",
        )
