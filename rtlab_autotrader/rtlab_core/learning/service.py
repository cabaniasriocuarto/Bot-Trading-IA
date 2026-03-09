from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from .brain import (
    MEDIUM_RISK_PROFILE,
    StrategySelector,
    blend_bot_policy_scores,
    compute_normalized_reward,
    deflated_sharpe_ratio,
    detect_drift,
    effective_weight_from_components,
    pbo_cscv,
)
from .knowledge import KnowledgeLoader


BacktestEvalFn = Callable[[dict[str, Any]], dict[str, Any]]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies" / "risk_policy.yaml").exists():
            return parent
    return None


def _default_learning_risk_profile() -> dict[str, Any]:
    repo_root = _resolve_repo_root_for_policy()
    if repo_root is None:
        return dict(MEDIUM_RISK_PROFILE)
    policy_path = (repo_root / "config" / "policies" / "risk_policy.yaml").resolve()
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        root = payload.get("risk_policy") if isinstance(payload.get("risk_policy"), dict) else {}
        triggers = root.get("triggers") if isinstance(root.get("triggers"), dict) else {}
        daily_cfg = triggers.get("daily_loss_pct") if isinstance(triggers.get("daily_loss_pct"), dict) else {}
        dd_cfg = triggers.get("max_drawdown_pct") if isinstance(triggers.get("max_drawdown_pct"), dict) else {}

        soft_daily = abs(float(daily_cfg.get("soft_kill_bot_at", 0.0))) if bool(daily_cfg.get("enabled", False)) else 0.0
        hard_daily = abs(float(daily_cfg.get("hard_kill_bot_at", 0.0))) if bool(daily_cfg.get("enabled", False)) else 0.0
        hard_dd = abs(float(dd_cfg.get("hard_kill_bot_at", 0.0))) if bool(dd_cfg.get("enabled", False)) else 0.0
        base = dict(MEDIUM_RISK_PROFILE)
        return {
            **base,
            "risk_profile": "policy_medium",
            "source": "config/policies/risk_policy.yaml",
            "paper": {
                **(base.get("paper") if isinstance(base.get("paper"), dict) else {}),
                "max_daily_loss_pct": soft_daily if soft_daily > 0 else float((base.get("paper") or {}).get("max_daily_loss_pct", 3.0)),
                "max_drawdown_pct": hard_dd if hard_dd > 0 else float((base.get("paper") or {}).get("max_drawdown_pct", 15.0)),
            },
            "live_initial": {
                **(base.get("live_initial") if isinstance(base.get("live_initial"), dict) else {}),
                "max_daily_loss_pct": hard_daily if hard_daily > 0 else float((base.get("live_initial") or {}).get("max_daily_loss_pct", 2.0)),
                "max_drawdown_pct": hard_dd if hard_dd > 0 else float((base.get("live_initial") or {}).get("max_drawdown_pct", 10.0)),
            },
        }
    except Exception:
        return dict(MEDIUM_RISK_PROFILE)


class LearningService:
    def __init__(self, *, user_data_dir: Path, repo_root: Path, registry: Any | None = None) -> None:
        self.root = (user_data_dir / "learning").resolve()
        self.status_path = self.root / "status.json"
        self.drift_path = self.root / "drift.json"
        self.recommendations_path = self.root / "recommendations.json"
        self.recommend_runtime_path = self.root / "recommend_runtime.json"
        self.repo_root = repo_root
        self.registry = registry
        self.knowledge = KnowledgeLoader(repo_root=repo_root)

    @staticmethod
    def default_learning_settings() -> dict[str, Any]:
        return {
            "enabled": False,
            "mode": "OFF",
            "engine_id": "bandit_thompson",
            "selector_algo": "thompson",
            "drift_algo": "adwin",
            "max_candidates": 30,
            "top_n": 5,
            "validation": {
                "walk_forward": True,
                "train_days": 252,
                "test_days": 126,
                "enforce_pbo": True,
                "enforce_dsr": True,
                "enforce_cpcv": False,
            },
            "promotion": {
                "allow_auto_apply": False,
                "allow_live": False,
            },
            "risk_profile": _default_learning_risk_profile(),
        }

    def ensure_settings_shape(self, settings: dict[str, Any]) -> dict[str, Any]:
        base = self.default_learning_settings()
        cur = settings.get("learning")
        if not isinstance(cur, dict):
            settings["learning"] = base
            return settings
        settings["learning"] = {
            **base,
            **cur,
            "validation": {**base["validation"], **(cur.get("validation") if isinstance(cur.get("validation"), dict) else {})},
            "promotion": {**base["promotion"], **(cur.get("promotion") if isinstance(cur.get("promotion"), dict) else {})},
            "risk_profile": {**base["risk_profile"], **(cur.get("risk_profile") if isinstance(cur.get("risk_profile"), dict) else {})},
        }
        settings["learning"]["promotion"]["allow_auto_apply"] = False
        settings["learning"]["promotion"]["allow_live"] = False
        if not settings["learning"].get("engine_id"):
            settings["learning"]["engine_id"] = {
                "thompson": "bandit_thompson",
                "ucb1": "bandit_ucb1",
                "regime_rules": "fixed_rules",
            }.get(str(settings["learning"].get("selector_algo", "thompson")), "bandit_thompson")
        return settings

    def _load_engine_catalog(self) -> list[dict[str, Any]]:
        payload = self.knowledge.get_learning_engines()
        engines = payload.get("engines") if isinstance(payload, dict) else []
        return [row for row in engines if isinstance(row, dict) and row.get("id")] if isinstance(engines, list) else []

    def _selected_engine(self, settings: dict[str, Any]) -> dict[str, Any] | None:
        cfg = self.ensure_settings_shape(dict(settings))
        engine_id = str((cfg.get("learning") or {}).get("engine_id") or "")
        engines = self._load_engine_catalog()
        selected = next((row for row in engines if str(row.get("id")) == engine_id), None)
        if selected:
            return selected
        selector_algo = str((cfg.get("learning") or {}).get("selector_algo") or "thompson")
        fallback_id = {
            "thompson": "bandit_thompson",
            "ucb1": "bandit_ucb1",
            "regime_rules": "fixed_rules",
        }.get(selector_algo, "bandit_thompson")
        return next((row for row in engines if str(row.get("id")) == fallback_id), None)

    def _canonical_gates_thresholds(self) -> dict[str, Any]:
        default_fail_closed = {
            "source": "config/policies/gates.yaml:default_fail_closed",
            "pbo_max": 0.05,
            "dsr_min": 0.95,
        }
        config_path = (self.knowledge.repo_root / "config" / "policies" / "gates.yaml").resolve()
        if config_path.exists():
            try:
                payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                gates_root = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}
                if isinstance(gates_root, dict) and gates_root:
                    pbo_cfg = gates_root.get("pbo") if isinstance(gates_root.get("pbo"), dict) else {}
                    dsr_cfg = gates_root.get("dsr") if isinstance(gates_root.get("dsr"), dict) else {}
                    return {
                        "source": "config/policies/gates.yaml",
                        "pbo_max": float(pbo_cfg.get("reject_if_gt", 0.05) or 0.05),
                        "dsr_min": float(dsr_cfg.get("min_dsr", 0.95) or 0.95),
                    }
            except Exception:
                return dict(default_fail_closed)
        return dict(default_fail_closed)

    def _require_registry(self) -> Any:
        if self.registry is None:
            raise RuntimeError("LearningService requires registry-backed ledgers")
        return self.registry

    def _load_gates_policy(self) -> dict[str, Any]:
        defaults = {
            "source_weights": {
                "legacy_untrusted": 0.0,
                "backtest": 0.60,
                "shadow": 1.00,
                "paper": 0.80,
                "testnet": 0.90,
                "live": 1.00,
            },
            "freshness_half_life_days": {
                "backtest": 90,
                "shadow": 45,
                "paper": 60,
                "testnet": 75,
                "live": 180,
            },
            "brain_policy": {
                "exact_bot_threshold_trades": 50,
                "exact_bot_threshold_effective_weight": 5.0,
                "blend_if_sufficient": {"exact_bot": 0.55, "pool_context": 0.25, "global_truth": 0.20},
                "blend_if_insufficient": {"exact_bot": 0.25, "pool_context": 0.35, "global_truth": 0.40},
            },
        }
        path = (self.repo_root / "config" / "policies" / "gates.yaml").resolve()
        if not path.exists():
            return defaults
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            gates = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}
            return {
                **defaults,
                **gates,
                "source_weights": {**defaults["source_weights"], **(gates.get("source_weights") or {})},
                "freshness_half_life_days": {**defaults["freshness_half_life_days"], **(gates.get("freshness_half_life_days") or {})},
                "brain_policy": {**defaults["brain_policy"], **(gates.get("brain_policy") or {})},
            }
        except Exception:
            return defaults

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _parse_ts(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _normalize_validation_quality(self, value: Any, *, source_type: str) -> float:
        if isinstance(value, (int, float)):
            return self._clamp(float(value))
        text = str(value or "").strip().lower()
        if not text:
            return 1.0 if source_type == "live" else 0.8
        if "live" in text:
            return 1.0
        if "shadow" in text:
            return 0.95
        if "sandbox" in text or "testnet" in text:
            return 0.90
        if "real_dataset" in text or "runtime" in text:
            return 0.85
        if "oos" in text or "walk" in text:
            return 0.75
        if "synthetic" in text:
            return 0.35
        return 0.70

    def _cost_realism_factor_from_row(self, row: dict[str, Any]) -> float:
        values = [
            row.get("fees_bps"),
            row.get("spread_bps"),
            row.get("slippage_bps"),
            row.get("funding_bps"),
        ]
        present = sum(1 for value in values if value is not None)
        if present == len(values):
            return 1.0
        if present > 0:
            return 0.5
        return 0.0

    def _freshness_decay_from_row(self, row: dict[str, Any], *, source_type: str, policy: dict[str, Any]) -> float:
        explicit = row.get("freshness_decay")
        if isinstance(explicit, (int, float)) and float(explicit) > 0:
            return self._clamp(float(explicit))
        anchor = self._parse_ts(row.get("as_of")) or self._parse_ts(row.get("created_at"))
        if anchor is None:
            return 1.0
        half_lives = policy.get("freshness_half_life_days") if isinstance(policy.get("freshness_half_life_days"), dict) else {}
        half_life = float(half_lives.get(source_type, 90) or 90)
        age_days = max(0.0, (datetime.now(timezone.utc) - anchor).total_seconds() / 86400.0)
        if half_life <= 0:
            return 1.0
        return self._clamp(pow(2.718281828, -(age_days / half_life)))

    @staticmethod
    def _is_excluded_row(row: dict[str, Any]) -> bool:
        return any(
            bool(row.get(field))
            for field in (
                "legacy_untrusted",
                "excluded_from_learning",
                "excluded_from_rankings",
                "excluded_from_guidance",
                "excluded_from_brain_scores",
                "stale",
            )
        )

    def _effective_weight_for_row(self, row: dict[str, Any], *, source_type: str, policy: dict[str, Any]) -> float:
        explicit = row.get("effective_weight")
        if isinstance(explicit, (int, float)) and float(explicit) > 0:
            return float(explicit)
        weights = policy.get("source_weights") if isinstance(policy.get("source_weights"), dict) else {}
        source_weight = float(row.get("source_weight") or weights.get(source_type, 0.0) or 0.0)
        validation_quality = self._normalize_validation_quality(row.get("validation_quality"), source_type=source_type)
        freshness_decay = self._freshness_decay_from_row(row, source_type=source_type, policy=policy)
        return effective_weight_from_components(
            source_weight=source_weight,
            validation_quality=validation_quality,
            freshness_decay=freshness_decay,
            trades=row.get("trades") or 0,
            attribution_type=row.get("attribution_type"),
            attribution_confidence=row.get("attribution_confidence"),
            cost_realism_factor=self._cost_realism_factor_from_row(row),
            data_integrity_factor=1.0 if row.get("dataset_hash") and row.get("dataset_source") else 0.5,
        )

    def _run_bot_link_map(self) -> dict[str, list[dict[str, Any]]]:
        registry = self._require_registry()
        out: dict[str, list[dict[str, Any]]] = {}
        for row in registry.list_run_bot_links():
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            out.setdefault(run_id, []).append(row)
        return out

    def _attach_bot_attribution(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        link_map = self._run_bot_link_map()
        out: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            if row.get("bot_id"):
                out.append(row)
                continue
            run_id = str(row.get("run_id") or "")
            links = link_map.get(run_id) or []
            if len(links) == 1:
                row["bot_id"] = links[0].get("bot_id")
                row["attribution_type"] = row.get("attribution_type") or links[0].get("attribution_type")
                row["attribution_confidence"] = row.get("attribution_confidence") or links[0].get("attribution_confidence")
            out.append(row)
        return out

    def _ensure_strategy_truth(self, strategy: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
        registry = self._require_registry()
        strategy_id = str(strategy.get("id") or "")
        current = registry.get_strategy_truth(strategy_id)
        if current:
            return current
        strat_runs = [row for row in runs if str(row.get("strategy_id") or "") == strategy_id]
        latest = strat_runs[0] if strat_runs else {}
        tags = [str(tag) for tag in (strategy.get("tags") or []) if tag]
        payload = {
            "strategy_id": strategy_id,
            "strategy_version": str(strategy.get("version") or strategy.get("version_tag") or "0.0.0"),
            "family": str(strategy.get("family") or strategy.get("origin") or "desconocida"),
            "market": str(strategy.get("market") or latest.get("market") or latest.get("symbol") or "desconocido"),
            "asset_class": str(strategy.get("asset_class") or latest.get("asset_class") or "desconocida"),
            "timeframe": str(strategy.get("timeframe") or latest.get("timeframe") or "-"),
            "thesis_summary": str(strategy.get("name") or strategy_id),
            "thesis_detail": str(strategy.get("notes") or strategy.get("description") or "NO EVIDENCIA"),
            "intended_regimes": tags,
            "forbidden_regimes": [],
            "microstructure_constraints": {
                "feature_set": latest.get("feature_set") or latest.get("orderflow_feature_set") or "desconocido",
                "use_orderflow_data": bool(latest.get("use_orderflow_data", False)),
            },
            "capacity_constraints": {},
            "cost_limits": {},
            "invalidation_rules": {},
            "current_status": "active" if str(strategy.get("status") or "active") != "archived" else "archived",
            "current_confidence": 0.50,
        }
        registry.upsert_strategy_truth(**payload)
        created = registry.get_strategy_truth(strategy_id)
        return created or payload

    def _aggregate_evidence_scope(self, rows: list[dict[str, Any]], *, source_type: str | None = None) -> dict[str, Any]:
        policy = self._load_gates_policy()
        scoped = [
            row for row in rows
            if not self._is_excluded_row(row)
            and (source_type is None or str(row.get("source_type") or "").lower() == source_type.lower())
        ]
        if not scoped:
            return {
                "rows": [],
                "trades_total": 0,
                "weight_sum": 0.0,
                "source_breakdown": {},
                "metrics": {},
            }
        weights: list[float] = []
        source_breakdown: dict[str, dict[str, float]] = {}
        weighted_fields = ("expectancy_net", "profit_factor", "sharpe", "sortino", "psr", "dsr", "max_dd", "win_rate")
        sums: dict[str, float] = {field: 0.0 for field in weighted_fields}
        trades_total = 0
        for row in scoped:
            source = str(row.get("source_type") or "unknown").lower()
            weight = self._effective_weight_for_row(row, source_type=source, policy=policy)
            weights.append(weight)
            trades_total += int(row.get("trades") or 0)
            src = source_breakdown.setdefault(source, {"count": 0.0, "weight_sum": 0.0})
            src["count"] += 1.0
            src["weight_sum"] += weight
            for field in weighted_fields:
                value = row.get(field)
                if isinstance(value, (int, float)):
                    sums[field] += float(value) * weight
        weight_sum = sum(weights)
        metrics = {
            field: (sums[field] / weight_sum if weight_sum > 0 else 0.0)
            for field in weighted_fields
        }
        metrics["max_dd_abs"] = abs(float(metrics.get("max_dd", 0.0) or 0.0))
        return {
            "rows": scoped,
            "trades_total": trades_total,
            "weight_sum": weight_sum,
            "source_breakdown": source_breakdown,
            "metrics": metrics,
        }

    def _scaled_metric(self, value: float, universe: list[float], *, invert: bool = False) -> float:
        if not universe:
            return 0.0
        lo = min(universe)
        hi = max(universe)
        if hi == lo:
            if invert:
                return 1.0 if value <= hi else 0.0
            return 1.0 if value >= lo and value > 0 else 0.0
        scaled = (value - lo) / (hi - lo)
        return self._clamp(1.0 - scaled if invert else scaled)

    def _compose_scope_scores(self, aggregates: list[dict[str, Any]], key: str) -> dict[str, float]:
        universes: dict[str, list[float]] = {
            "expectancy_net": [],
            "profit_factor": [],
            "sharpe": [],
            "psr": [],
            "dsr": [],
            "max_dd_abs": [],
            "win_rate": [],
        }
        for aggregate in aggregates:
            metrics = ((aggregate.get(key) or {}).get("metrics") if isinstance(aggregate.get(key), dict) else {}) or {}
            for field in universes:
                value = metrics.get(field)
                if isinstance(value, (int, float)):
                    universes[field].append(float(value))
        scores: dict[str, float] = {}
        for aggregate in aggregates:
            metrics = ((aggregate.get(key) or {}).get("metrics") if isinstance(aggregate.get(key), dict) else {}) or {}
            strategy_id = str(aggregate.get("strategy_id") or "")
            scores[strategy_id] = (
                0.40 * self._scaled_metric(float(metrics.get("expectancy_net", 0.0) or 0.0), universes["expectancy_net"])
                + 0.15 * self._scaled_metric(float(metrics.get("profit_factor", 0.0) or 0.0), universes["profit_factor"])
                + 0.10 * self._scaled_metric(float(metrics.get("sharpe", 0.0) or 0.0), universes["sharpe"])
                + 0.10 * self._scaled_metric(float(metrics.get("psr", 0.0) or 0.0), universes["psr"])
                + 0.05 * self._scaled_metric(float(metrics.get("dsr", 0.0) or 0.0), universes["dsr"])
                + 0.10 * self._scaled_metric(float(metrics.get("win_rate", 0.0) or 0.0), universes["win_rate"])
                + 0.10 * self._scaled_metric(float(metrics.get("max_dd_abs", 0.0) or 0.0), universes["max_dd_abs"], invert=True)
            )
        return scores

    def _summarize_sources(
        self,
        evidence_by_strategy: dict[str, list[dict[str, Any]]],
        *,
        policy: dict[str, Any],
        bot_id: str | None = None,
    ) -> dict[str, dict[str, float]]:
        summary: dict[str, dict[str, float]] = {}
        seen: set[tuple[Any, ...]] = set()
        for rows in evidence_by_strategy.values():
            for row in rows:
                marker = (
                    row.get("evidence_id") or row.get("id") or row.get("run_id"),
                    row.get("strategy_id"),
                    row.get("source_type") or row.get("source"),
                    row.get("dataset_hash"),
                )
                if marker in seen:
                    continue
                seen.add(marker)
                source = str(row.get("source_type") or row.get("source") or "unknown")
                current = summary.setdefault(
                    source,
                    {
                        "count": 0.0,
                        "weight_sum": 0.0,
                        "trades": 0.0,
                        "exact_bot_count": 0.0,
                        "pool_context_count": 0.0,
                        "exact_bot_trades": 0.0,
                        "pool_context_trades": 0.0,
                    },
                )
                trades = float(row.get("trades") or row.get("trade_count") or 0.0)
                is_exact_bot = bool(bot_id) and str(row.get("bot_id") or "") == str(bot_id)
                current["count"] += 1.0
                current["trades"] += trades
                current["weight_sum"] += float(
                    self._effective_weight_for_row(row, source_type=source, policy=policy)
                )
                if is_exact_bot:
                    current["exact_bot_count"] += 1.0
                    current["exact_bot_trades"] += trades
                else:
                    current["pool_context_count"] += 1.0
                    current["pool_context_trades"] += trades
        return summary

    def build_bot_brain(
        self,
        *,
        bot_id: str,
        bots: list[dict[str, Any]],
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        persist: bool = True,
    ) -> dict[str, Any]:
        registry = self._require_registry()
        registry.backfill_bot_attribution_from_run_links()
        bot = next((row for row in bots if str(row.get("id") or "") == str(bot_id)), None)
        if not bot:
            raise ValueError("Bot no encontrado")
        pool_ids = [str(item) for item in (bot.get("pool_strategy_ids") or []) if str(item or "").strip()]
        if not pool_ids and isinstance(bot.get("pool_strategies"), list):
            pool_ids = [str(item.get("id") or item.get("strategy_id") or "") for item in (bot.get("pool_strategies") or []) if isinstance(item, dict)]
        pool_ids = [item for item in pool_ids if item]
        if not pool_ids:
            return {
                "bot_id": bot_id,
                "regime_label": self._infer_regime(runs),
                "selected_strategy_id": None,
                "items": [],
                "source_summary": {"sources": {}, "trades_total": 0, "weight_sum_total": 0.0},
                "warnings": ["Pool vacio: el bot no tiene estrategias atribuibles para el cerebro."],
            }
        strategies_by_id = {str(row.get("id") or ""): row for row in strategies if isinstance(row, dict)}
        regime_label = str(bot.get("regime_label") or self._infer_regime(runs))
        policy = self._load_gates_policy()
        all_evidence: dict[str, list[dict[str, Any]]] = {}
        for strategy_id in pool_ids:
            rows = registry.list_strategy_evidence(strategy_id=strategy_id)
            all_evidence[strategy_id] = self._attach_bot_attribution(rows)
        aggregates: list[dict[str, Any]] = []
        for strategy_id in pool_ids:
            strategy = strategies_by_id.get(strategy_id, {"id": strategy_id, "name": strategy_id})
            truth = self._ensure_strategy_truth(strategy, runs)
            rows = all_evidence.get(strategy_id, [])
            exact_rows = [row for row in rows if str(row.get("bot_id") or "") == str(bot_id)]
            pool_rows = [row for row in rows if str(row.get("bot_id") or "") != str(bot_id)]
            global_rows = list(rows)
            aggregates.append(
                {
                    "strategy_id": strategy_id,
                    "strategy_name": str(strategy.get("name") or strategy_id),
                    "truth": truth,
                    "exact_bot": self._aggregate_evidence_scope(exact_rows),
                    "pool_context": self._aggregate_evidence_scope(pool_rows),
                    "global_truth": self._aggregate_evidence_scope(global_rows),
                }
            )
        exact_scores = self._compose_scope_scores(aggregates, "exact_bot")
        pool_scores = self._compose_scope_scores(aggregates, "pool_context")
        global_scores = self._compose_scope_scores(aggregates, "global_truth")
        brain_policy = policy.get("brain_policy") if isinstance(policy.get("brain_policy"), dict) else {}
        items: list[dict[str, Any]] = []
        for aggregate in aggregates:
            strategy_id = str(aggregate.get("strategy_id") or "")
            exact = aggregate["exact_bot"]
            blended = blend_bot_policy_scores(
                exact_bot_score=exact_scores.get(strategy_id, 0.0),
                pool_context_score=pool_scores.get(strategy_id, 0.0),
                global_truth_score=global_scores.get(strategy_id, 0.0),
                exact_bot_trades=exact.get("trades_total", 0),
                exact_bot_weight_sum=exact.get("weight_sum", 0.0),
                exact_bot_threshold_trades=brain_policy.get("exact_bot_threshold_trades", 50),
                exact_bot_threshold_effective_weight=brain_policy.get("exact_bot_threshold_effective_weight", 5.0),
                sufficient_weights=brain_policy.get("blend_if_sufficient"),
                insufficient_weights=brain_policy.get("blend_if_insufficient"),
            )
            confidence = self._clamp(
                max(
                    aggregate["global_truth"].get("weight_sum", 0.0),
                    aggregate["pool_context"].get("weight_sum", 0.0),
                    exact.get("weight_sum", 0.0),
                ) / 10.0
            )
            items.append(
                {
                    "strategy_id": strategy_id,
                    "strategy_name": aggregate.get("strategy_name"),
                    "score_exact_bot": round(exact_scores.get(strategy_id, 0.0), 6),
                    "score_pool_context": round(pool_scores.get(strategy_id, 0.0), 6),
                    "score_global_truth": round(global_scores.get(strategy_id, 0.0), 6),
                    "score_final": round(float(blended["score_final"]), 6),
                    "exact_history_sufficient": bool(blended["exact_history_sufficient"]),
                    "weights_used": blended["weights_used"],
                    "weight_target": 0.0,
                    "weight_live": 0.0,
                    "confidence": round(confidence, 6),
                    "source_scope": "exact_bot+pool_context+global_truth",
                    "truth": aggregate["truth"],
                    "exact_bot": exact,
                    "pool_context": aggregate["pool_context"],
                    "global_truth": aggregate["global_truth"],
                }
            )
        items.sort(key=lambda row: (float(row.get("score_final") or 0.0), float(row.get("confidence") or 0.0)), reverse=True)
        if items:
            total_positive = sum(max(0.0, float(item.get("score_final") or 0.0)) for item in items) or 1.0
            for item in items:
                item["weight_target"] = round(max(0.0, float(item.get("score_final") or 0.0)) / total_positive, 4)
                item["weight_live"] = item["weight_target"]
                if persist:
                    registry.upsert_bot_policy_state(
                        bot_id=bot_id,
                        strategy_id=str(item["strategy_id"]),
                        regime_label=regime_label,
                        score_current=float(item["score_final"]),
                        weight_target=float(item["weight_target"]),
                        weight_live=float(item["weight_live"]),
                        confidence=float(item["confidence"]),
                        source_scope=str(item["source_scope"]),
                    )
        selected_strategy_id = str(items[0]["strategy_id"]) if items else None
        candidate_rows = [
            {
                "strategy_id": item["strategy_id"],
                "score_final": item["score_final"],
                "score_exact_bot": item["score_exact_bot"],
                "score_pool_context": item["score_pool_context"],
                "score_global_truth": item["score_global_truth"],
                "confidence": item["confidence"],
            }
            for item in items
        ]
        if persist:
            registry.append_bot_decision_log(
                decision_id=f"brain_{bot_id}_{hashlib.sha256(f'{bot_id}:{_utc_iso()}'.encode('utf-8')).hexdigest()[:10]}",
                bot_id=bot_id,
                timestamp=_utc_iso(),
                regime_label=regime_label,
                candidate_strategies=candidate_rows,
                selected_strategy_id=selected_strategy_id,
                rejected_strategies=[row for row in candidate_rows if str(row["strategy_id"]) != selected_strategy_id],
                reason={
                    "selected_by": "bot_first_with_global_prior",
                    "selected_strategy_id": selected_strategy_id,
                    "exact_bot_threshold_trades": brain_policy.get("exact_bot_threshold_trades", 50),
                    "exact_bot_threshold_effective_weight": brain_policy.get("exact_bot_threshold_effective_weight", 5.0),
                },
                evidence_scope={
                    "source_weights": policy.get("source_weights") or {},
                    "pool_size": len(pool_ids),
                },
                risk_overrides={"live_enabled": False},
                execution_constraints={"requires_human_approval_for_live": True},
            )
        source_summary = self._summarize_sources(all_evidence, policy=policy, bot_id=bot_id)
        return {
            "bot_id": bot_id,
            "regime_label": regime_label,
            "selected_strategy_id": selected_strategy_id,
            "items": items,
            "source_summary": {
                "sources": source_summary,
                "trades_total": sum(int((item.get("global_truth") or {}).get("trades_total", 0) or 0) for item in items),
                "weight_sum_total": round(sum(float((item.get("global_truth") or {}).get("weight_sum", 0.0) or 0.0) for item in items), 6),
            },
            "persisted": bool(persist),
        }

    def get_bot_decision_log_payload(self, bot_id: str, *, limit: int = 50) -> dict[str, Any]:
        registry = self._require_registry()
        rows = registry.list_bot_decision_log(bot_id=bot_id)
        limited_rows = rows[: max(1, int(limit or 50))]
        regime_breakdown: dict[str, int] = {}
        selected_breakdown: dict[str, int] = {}
        with_selection = 0
        hold_or_skip = 0
        candidate_total = 0
        rejected_total = 0
        latest_timestamp = None
        for row in limited_rows:
            regime = str(row.get("regime_label") or "unknown")
            regime_breakdown[regime] = regime_breakdown.get(regime, 0) + 1
            selected_strategy_id = str(row.get("selected_strategy_id") or "").strip()
            if selected_strategy_id:
                with_selection += 1
                selected_breakdown[selected_strategy_id] = selected_breakdown.get(selected_strategy_id, 0) + 1
            else:
                hold_or_skip += 1
            candidate_total += len(row.get("candidate_strategies") or [])
            rejected_total += len(row.get("rejected_strategies") or [])
            if not latest_timestamp and row.get("timestamp"):
                latest_timestamp = row.get("timestamp")
        return {
            "bot_id": bot_id,
            "items": limited_rows,
            "summary": {
                "count": len(limited_rows),
                "with_selection": with_selection,
                "hold_or_skip": hold_or_skip,
                "candidate_total": candidate_total,
                "rejected_total": rejected_total,
                "latest_timestamp": latest_timestamp,
                "regime_breakdown": regime_breakdown,
                "selected_breakdown": selected_breakdown,
            },
        }

    def get_strategy_truth_payload(
        self,
        strategy_id: str,
        *,
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        strategy = next((row for row in strategies if str(row.get("id") or "") == str(strategy_id)), None)
        if not strategy:
            raise ValueError("Strategy not found")
        truth = self._ensure_strategy_truth(strategy, runs)
        evidence = self.get_strategy_evidence_payload(strategy_id)
        return {
            "strategy_id": strategy_id,
            "truth": truth,
            "evidence_summary": evidence.get("summary") or {},
        }

    def get_strategy_evidence_payload(self, strategy_id: str) -> dict[str, Any]:
        registry = self._require_registry()
        registry.backfill_bot_attribution_from_run_links()
        rows = self._attach_bot_attribution(registry.list_strategy_evidence(strategy_id=strategy_id))
        rows.sort(key=lambda row: str(row.get("created_at") or row.get("as_of") or ""), reverse=True)
        summary: dict[str, dict[str, float]] = {}
        for row in rows:
            source = str(row.get("source_type") or "unknown")
            current = summary.setdefault(source, {"count": 0.0, "effective_weight": 0.0, "trades": 0.0})
            current["count"] += 1.0
            current["effective_weight"] += float(row.get("effective_weight") or 0.0)
            current["trades"] += float(row.get("trades") or 0.0)
        return {"strategy_id": strategy_id, "items": rows, "summary": summary}

    def get_bot_experience_payload(self, bot_id: str, *, limit: int = 25) -> dict[str, Any]:
        registry = self._require_registry()
        registry.backfill_bot_attribution_from_run_links()
        policy = self._load_gates_policy()
        rows = registry.list_experience_episodes(bot_ids=[bot_id])
        rows.sort(key=lambda row: str(row.get("end_ts") or row.get("created_at") or ""), reverse=True)

        source_breakdown: dict[str, dict[str, float]] = {}
        strategy_breakdown: dict[str, dict[str, float]] = {}
        attribution_breakdown = {"exact": 0, "strong": 0, "approx": 0, "unknown": 0}
        excluded_count = 0
        stale_count = 0
        legacy_count = 0
        trades_total = 0
        effective_weight_total = 0.0
        latest_end_ts = None

        for row in rows:
            source = str(row.get("source") or "unknown")
            source_item = source_breakdown.setdefault(source, {"episodes": 0.0, "trades": 0.0, "effective_weight": 0.0})
            strategy_id = str(row.get("strategy_id") or "unknown")
            strategy_item = strategy_breakdown.setdefault(
                strategy_id,
                {"episodes": 0.0, "trades": 0.0, "effective_weight": 0.0},
            )

            trades = int(row.get("trades_count") or 0)
            effective_weight = float(
                row.get("effective_weight")
                or self._effective_weight_for_row(dict(row, source_type=row.get("source")), source_type=source, policy=policy)
                or 0.0
            )
            attribution = str(row.get("attribution_type") or "unknown").strip().lower()
            if attribution.startswith("exact"):
                attribution_breakdown["exact"] += 1
            elif attribution.startswith("strong"):
                attribution_breakdown["strong"] += 1
            elif attribution.startswith("approx"):
                attribution_breakdown["approx"] += 1
            else:
                attribution_breakdown["unknown"] += 1

            source_item["episodes"] += 1.0
            source_item["trades"] += float(trades)
            source_item["effective_weight"] += effective_weight
            strategy_item["episodes"] += 1.0
            strategy_item["trades"] += float(trades)
            strategy_item["effective_weight"] += effective_weight

            trades_total += trades
            effective_weight_total += effective_weight
            excluded_count += 1 if self._is_excluded_row(row) else 0
            stale_count += 1 if bool(row.get("stale")) else 0
            legacy_count += 1 if bool(row.get("legacy_untrusted")) else 0
            if latest_end_ts is None and (row.get("end_ts") or row.get("created_at")):
                latest_end_ts = row.get("end_ts") or row.get("created_at")

        top_strategies = sorted(
            (
                {
                    "strategy_id": strategy_id,
                    "episodes": int(values.get("episodes") or 0),
                    "trades": int(values.get("trades") or 0),
                    "effective_weight": round(float(values.get("effective_weight") or 0.0), 6),
                }
                for strategy_id, values in strategy_breakdown.items()
            ),
            key=lambda item: (float(item.get("effective_weight") or 0.0), int(item.get("trades") or 0)),
            reverse=True,
        )[:5]

        return {
            "bot_id": bot_id,
            "items": rows[: max(1, int(limit or 25))],
            "summary": {
                "count": len(rows),
                "eligible_count": max(0, len(rows) - excluded_count),
                "excluded_count": excluded_count,
                "stale_count": stale_count,
                "legacy_count": legacy_count,
                "trades_total": trades_total,
                "effective_weight_total": round(effective_weight_total, 6),
                "latest_end_ts": latest_end_ts,
                "attribution_breakdown": attribution_breakdown,
                "sources": {
                    key: {
                        "episodes": int(value.get("episodes") or 0),
                        "trades": int(value.get("trades") or 0),
                        "effective_weight": round(float(value.get("effective_weight") or 0.0), 6),
                    }
                    for key, value in sorted(
                        source_breakdown.items(),
                        key=lambda item: float((item[1] or {}).get("effective_weight") or 0.0),
                        reverse=True,
                    )
                },
                "top_strategies": top_strategies,
            },
        }

    def get_execution_reality_payload(
        self,
        *,
        bot_id: str | None = None,
        strategy_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        registry = self._require_registry()
        rows = registry.list_execution_reality(bot_id=bot_id, strategy_id=strategy_id, limit=limit)
        if rows:
            avg_slippage = sum(float(row.get("realized_slippage_bps") or 0.0) for row in rows) / len(rows)
            avg_latency = sum(float(row.get("latency_ms") or 0.0) for row in rows) / len(rows)
            avg_spread = sum(float(row.get("spread_bps") or 0.0) for row in rows) / len(rows)
            avg_impact = sum(float(row.get("impact_bps_est") or 0.0) for row in rows) / len(rows)
            avg_partial_fill_ratio = sum(float(row.get("partial_fill_ratio") or 0.0) for row in rows) / len(rows)
        else:
            avg_slippage = avg_latency = avg_spread = avg_impact = avg_partial_fill_ratio = 0.0
        maker_count = sum(1 for row in rows if str(row.get("maker_taker") or "").lower() == "maker")
        taker_count = sum(1 for row in rows if str(row.get("maker_taker") or "").lower() == "taker")
        maker_taker_total = maker_count + taker_count
        reconciliation_breakdown: dict[str, int] = {}
        symbols = {
            str(row.get("symbol") or "").upper()
            for row in rows
            if str(row.get("symbol") or "").strip()
        }
        latest_timestamp = None
        for row in rows:
            status = str(row.get("reconciliation_status") or "unknown")
            reconciliation_breakdown[status] = reconciliation_breakdown.get(status, 0) + 1
            if not latest_timestamp and row.get("timestamp"):
                latest_timestamp = row.get("timestamp")
        return {
            "bot_id": bot_id,
            "strategy_id": strategy_id,
            "items": rows,
            "summary": {
                "count": len(rows),
                "avg_realized_slippage_bps": round(avg_slippage, 6),
                "avg_latency_ms": round(avg_latency, 6),
                "avg_spread_bps": round(avg_spread, 6),
                "avg_impact_bps_est": round(avg_impact, 6),
                "avg_partial_fill_ratio": round(avg_partial_fill_ratio, 6),
                "maker_ratio": round(maker_count / maker_taker_total, 6) if maker_taker_total else 0.0,
                "taker_ratio": round(taker_count / maker_taker_total, 6) if maker_taker_total else 0.0,
                "symbols_count": len(symbols),
                "latest_timestamp": latest_timestamp,
                "reconciliation_breakdown": reconciliation_breakdown,
            },
        }

    def get_bot_live_eligibility_payload(
        self,
        *,
        bot_id: str,
        bots: list[dict[str, Any]],
        strategies: list[dict[str, Any]],
        settings: dict[str, Any],
        health: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        registry = self._require_registry()
        bot = next((row for row in bots if str(row.get("id") or "") == str(bot_id)), None)
        if not bot:
            raise ValueError("Bot no encontrado")

        settings_payload = self.ensure_settings_shape(dict(settings or {}))
        runtime_mode = str(settings_payload.get("mode") or "PAPER").strip().lower()
        strategy_map = {str(row.get("id") or ""): row for row in strategies if isinstance(row, dict)}
        pool_ids = [str(item) for item in (bot.get("pool_strategy_ids") or []) if str(item)]
        if not pool_ids and isinstance(bot.get("pool_strategies"), list):
            pool_ids = [str((row or {}).get("id") or "") for row in bot.get("pool_strategies") or [] if str((row or {}).get("id") or "")]

        policy_rows = registry.list_bot_policy_state(bot_id=bot_id)
        latest_policy_by_strategy: dict[str, dict[str, Any]] = {}
        for row in policy_rows:
            strategy_id = str(row.get("strategy_id") or "")
            if strategy_id and strategy_id not in latest_policy_by_strategy:
                latest_policy_by_strategy[strategy_id] = row

        strategy_items: list[dict[str, Any]] = []
        for strategy_id in pool_ids:
            meta = strategy_map.get(strategy_id, {})
            policy = latest_policy_by_strategy.get(strategy_id, {})
            strategy_items.append(
                {
                    "strategy_id": strategy_id,
                    "strategy_name": str(meta.get("name") or strategy_id),
                    "score_current": float(policy.get("score_current") or 0.0),
                    "weight_target": float(policy.get("weight_target") or 0.0),
                    "weight_live": float(policy.get("weight_live") or 0.0),
                    "confidence": float(policy.get("confidence") or 0.0),
                    "source_scope": str(policy.get("source_scope") or "sin_evidencia"),
                    "veto_until": policy.get("veto_until"),
                    "veto_reason": policy.get("veto_reason"),
                }
            )
        strategy_items.sort(key=lambda row: (float(row.get("score_current") or 0.0), float(row.get("confidence") or 0.0)), reverse=True)

        parity_rows = registry.list_live_parity_state(limit=2000)
        parity_by_instrument = {str(row.get("instrument_id") or ""): row for row in parity_rows if str(row.get("instrument_id") or "")}
        parity_by_symbol = {
            (str(row.get("provider_market") or "").lower(), str(row.get("symbol") or "").upper()): row
            for row in parity_rows
        }

        instrument_rows = registry.list_instrument_registry(provider="binance")
        bot_universe = {str(item).upper() for item in (bot.get("universe") or []) if str(item)}
        eligible_instruments: list[dict[str, Any]] = []
        blocked_instruments = 0
        parity_ready = 0
        for instrument in instrument_rows:
            if not bool(instrument.get("is_active_snapshot", True)):
                continue
            instrument_symbol = str(instrument.get("normalized_symbol") or instrument.get("provider_symbol") or "").upper()
            if bot_universe and instrument_symbol not in bot_universe and str(instrument.get("instrument_id") or "").upper() not in bot_universe:
                continue
            parity = parity_by_instrument.get(str(instrument.get("instrument_id") or "")) or parity_by_symbol.get(
                (str(instrument.get("provider_market") or "").lower(), instrument_symbol)
            ) or {}
            warnings = list(parity.get("warnings") or [])
            live_capable = bool((instrument.get("mode_capabilities") or {}).get("allowed_in_live", instrument.get("live_enabled")))
            parity_ok = bool(parity.get("has_reference_data")) and bool(parity.get("has_recent_market_state"))
            if str(instrument.get("provider_market") or "") in {"usdm_futures", "coinm_futures"}:
                parity_ok = parity_ok and bool(parity.get("has_recent_mark_price"))
            if live_capable and bool(instrument.get("tradable")) and parity_ok:
                parity_ready += 1
            else:
                blocked_instruments += 1
            eligible_instruments.append(
                {
                    "instrument_id": str(instrument.get("instrument_id") or ""),
                    "provider_market": str(instrument.get("provider_market") or ""),
                    "provider_symbol": str(instrument.get("provider_symbol") or ""),
                    "normalized_symbol": instrument_symbol,
                    "status": str(instrument.get("status") or ""),
                    "tradable": bool(instrument.get("tradable")),
                    "live_enabled": bool(instrument.get("live_enabled")),
                    "mode_capabilities": instrument.get("mode_capabilities") or {},
                    "parity_status": str(parity.get("status") or "sin_parity"),
                    "parity_warnings": warnings,
                    "eligible_live": bool(live_capable and bool(instrument.get("tradable")) and parity_ok),
                    "tick_size": instrument.get("tick_size"),
                    "step_size": instrument.get("step_size"),
                    "min_qty": instrument.get("min_qty"),
                    "min_notional": instrument.get("min_notional"),
                }
            )

        eligible_instruments.sort(
            key=lambda row: (
                0 if bool(row.get("eligible_live")) else 1,
                0 if bool(row.get("tradable")) else 1,
                str(row.get("provider_market") or ""),
                str(row.get("normalized_symbol") or ""),
            )
        )
        blocked_reasons: list[str] = []
        warnings: list[str] = []
        if not pool_ids:
            blocked_reasons.append("pool_vacio")
        if str(bot.get("status") or "") == "archived":
            blocked_reasons.append("bot_archivado")
        elif str(bot.get("status") or "") == "paused":
            warnings.append("bot_pausado")
        if not parity_ready:
            blocked_reasons.append("sin_instrumentos_elegibles_live")
        if runtime_mode != "live":
            warnings.append(f"runtime_actual_{runtime_mode}")
        if health and not bool((health or {}).get("ok", True)):
            warnings.append("health_backend_no_ok")

        return {
            "bot_id": bot_id,
            "bot_name": str(bot.get("name") or bot_id),
            "bot_mode": str(bot.get("mode") or ""),
            "bot_status": str(bot.get("status") or ""),
            "runtime_mode": runtime_mode,
            "pool_size": len(pool_ids),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
            "summary": {
                "eligible_instruments": sum(1 for row in eligible_instruments if bool(row.get("eligible_live"))),
                "blocked_instruments": blocked_instruments,
                "parity_ready": parity_ready,
            },
            "strategies": strategy_items,
            "eligible_instruments": eligible_instruments[:20],
        }

    def validate_execution_preflight(
        self,
        *,
        bot_id: str,
        instrument_id: str | None,
        symbol: str | None,
        provider_market: str | None,
        side: str | None,
        qty: float | None,
        mode: str,
        bots: list[dict[str, Any]],
        strategies: list[dict[str, Any]],
        settings: dict[str, Any],
        health: dict[str, Any] | None = None,
        live_trading_enabled: bool = False,
    ) -> dict[str, Any]:
        registry = self._require_registry()
        normalized_mode = str(mode or "live").strip().lower()
        capability_key = {
            "mock": "allowed_in_mock",
            "shadow": "allowed_in_mock",
            "paper": "allowed_in_paper",
            "test": "allowed_in_testnet",
            "testnet": "allowed_in_testnet",
            "demo": "allowed_in_demo",
            "live": "allowed_in_live",
        }.get(normalized_mode, "allowed_in_live")
        eligibility = self.get_bot_live_eligibility_payload(
            bot_id=bot_id,
            bots=bots,
            strategies=strategies,
            settings=settings,
            health=health,
        )
        bot = next((row for row in bots if str(row.get("id") or "") == str(bot_id)), None)
        if not bot:
            raise ValueError("Bot no encontrado")

        instrument_rows = registry.list_instrument_registry(provider="binance")
        parity_rows = registry.list_live_parity_state(limit=2000)
        parity_by_instrument = {str(row.get("instrument_id") or ""): row for row in parity_rows if str(row.get("instrument_id") or "")}
        parity_by_symbol = {
            (str(row.get("provider_market") or "").lower(), str(row.get("symbol") or "").upper()): row
            for row in parity_rows
        }

        selected_instrument: dict[str, Any] | None = None
        normalized_symbol = str(symbol or "").upper()
        normalized_market = str(provider_market or "").lower()
        for row in instrument_rows:
            row_id = str(row.get("instrument_id") or "")
            row_symbol = str(row.get("normalized_symbol") or row.get("provider_symbol") or "").upper()
            row_market = str(row.get("provider_market") or "").lower()
            if instrument_id and row_id == str(instrument_id):
                selected_instrument = row
                break
            if normalized_symbol and row_symbol == normalized_symbol and (not normalized_market or row_market == normalized_market):
                selected_instrument = row
                break
        if selected_instrument is None:
            selected_instrument = next((row for row in eligibility.get("eligible_instruments", []) if bool(row.get("eligible_live"))), None)
        parity = {}
        if selected_instrument:
            parity = parity_by_instrument.get(str(selected_instrument.get("instrument_id") or "")) or parity_by_symbol.get(
                (
                    str(selected_instrument.get("provider_market") or "").lower(),
                    str(selected_instrument.get("normalized_symbol") or selected_instrument.get("provider_symbol") or "").upper(),
                )
            ) or {}

        checks: list[dict[str, Any]] = []
        blocked_reasons: list[str] = []
        warnings: list[str] = list(eligibility.get("warnings") or [])

        def _add_check(check_id: str, label: str, ok: bool, detail: str, *, blocking: bool = True) -> None:
            checks.append({"id": check_id, "label": label, "ok": bool(ok), "detail": detail})
            if blocking and not ok:
                blocked_reasons.append(check_id)

        bot_status = str(bot.get("status") or "")
        pool_size = int(eligibility.get("pool_size") or 0)
        _add_check("bot_exists", "Bot encontrado", True, f"Bot {bot_id} disponible.")
        _add_check("pool_not_empty", "Pool con estrategias", pool_size > 0, f"Pool actual: {pool_size} estrategia(s).")
        _add_check("bot_not_archived", "Bot no archivado", bot_status != "archived", f"Estado del bot: {bot_status or 'desconocido'}.")
        _add_check(
            "bot_mode_matches",
            "Modo del bot compatible",
            normalized_mode != "live" or str(bot.get("mode") or "").lower() == "live",
            f"Modo del bot: {str(bot.get('mode') or '').lower() or 'sin_modo'}. Validación solicitada para {normalized_mode}.",
        )
        _add_check("instrument_found", "Instrumento resuelto", selected_instrument is not None, "Se seleccionó instrumento elegible." if selected_instrument else "No hay instrumento elegible para validar.")

        if selected_instrument:
            capabilities = selected_instrument.get("mode_capabilities") or {}
            instrument_market = str(selected_instrument.get("provider_market") or "")
            instrument_symbol = str(selected_instrument.get("normalized_symbol") or selected_instrument.get("provider_symbol") or "")
            _add_check(
                "instrument_tradable",
                "Instrumento tradable",
                bool(selected_instrument.get("tradable")),
                f"{instrument_symbol} / {instrument_market} tradable={bool(selected_instrument.get('tradable'))}.",
            )
            _add_check(
                "instrument_mode_enabled",
                "Modo habilitado para el instrumento",
                bool(capabilities.get(capability_key, False)),
                f"{instrument_symbol} permite {normalized_mode}={bool(capabilities.get(capability_key, False))}.",
            )
            if normalized_mode == "live":
                _add_check(
                    "live_runtime_enabled",
                    "LIVE habilitado en runtime",
                    bool(live_trading_enabled),
                    "LIVE_TRADING_ENABLED debe estar activo para enrutar órdenes reales.",
                )
            else:
                _add_check(
                    "mode_runtime_declared",
                    "Modo operativo declarado",
                    True,
                    f"Validación sobre modo {normalized_mode}; no usa dinero real.",
                    blocking=False,
                )
            _add_check(
                "parity_reference",
                "Referencia de mercado disponible",
                bool(parity.get("has_reference_data")),
                f"Paridad status={str(parity.get('status') or 'sin_parity')}.",
            )
            _add_check(
                "parity_market_state",
                "Estado de mercado reciente",
                bool(parity.get("has_recent_market_state")),
                "Se requiere dataset/market state reciente para validar ejecución.",
            )
            if instrument_market in {"usdm_futures", "coinm_futures"}:
                _add_check(
                    "parity_mark_price",
                    "Mark price reciente",
                    bool(parity.get("has_recent_mark_price")),
                    "Derivados requieren mark price reciente para live/testnet.",
                )
            else:
                _add_check(
                    "parity_mark_price",
                    "Mark price no requerido",
                    True,
                    "Spot/margin no requieren mark price dedicado.",
                    blocking=False,
                )
            _add_check(
                "qty_positive",
                "Cantidad válida",
                qty is None or float(qty) > 0.0,
                f"qty={qty if qty is not None else 'auto/no provista'}.",
            )
            _add_check(
                "side_declared",
                "Lado declarado",
                str(side or "").upper() in {"BUY", "SELL"},
                f"side={str(side or '').upper() or 'NO_DECLARADO'}.",
            )
            instrument_payload = {
                "instrument_id": str(selected_instrument.get("instrument_id") or ""),
                "provider_market": instrument_market,
                "provider_symbol": str(selected_instrument.get("provider_symbol") or ""),
                "normalized_symbol": instrument_symbol,
                "status": str(selected_instrument.get("status") or ""),
                "tradable": bool(selected_instrument.get("tradable")),
                "live_enabled": bool(selected_instrument.get("live_enabled")),
                "mode_capabilities": capabilities,
                "parity_status": str(parity.get("status") or "sin_parity"),
                "parity_warnings": list(parity.get("warnings") or []),
            }
        else:
            instrument_payload = None

        reason_codes = list(dict.fromkeys(blocked_reasons))
        return {
            "ok": len(reason_codes) == 0,
            "mode": normalized_mode,
            "bot_id": bot_id,
            "blocked_reasons": reason_codes,
            "reason_codes": reason_codes,
            "warnings": warnings,
            "checks": checks,
            "instrument": instrument_payload,
        }

    def _streams_from_runs(self, runs: list[dict[str, Any]]) -> dict[str, list[float]]:
        latest = runs[:50]
        return {
            "returns": [float((r.get("metrics") or {}).get("return_total", 0.0)) for r in latest],
            "realized_vol": [abs(float((r.get("metrics") or {}).get("sortino", 0.0))) / 10.0 for r in latest],
            "atr": [abs(float((r.get("metrics") or {}).get("max_dd", 0.0))) + 0.001 for r in latest],
            "spread_bps": [float((r.get("costs_model") or {}).get("spread_bps", 0.0)) for r in latest],
            "slippage_bps": [float((r.get("costs_model") or {}).get("slippage_bps", 0.0)) for r in latest],
            "expectancy_usd": [float((r.get("metrics") or {}).get("expectancy_usd_per_trade", (r.get("metrics") or {}).get("expectancy", 0.0))) for r in latest],
            "max_dd": [float((r.get("metrics") or {}).get("max_dd", 0.0)) for r in latest],
        }

    def _eligible_learning_pool(self, strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for strategy in strategies:
            if not isinstance(strategy, dict):
                continue
            if str(strategy.get("status") or "active") == "archived":
                continue
            if bool(strategy.get("allow_learning", True)):
                out.append(strategy)
        return out

    def compute_drift(self, *, settings: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        drift = detect_drift(self._streams_from_runs(runs), algo=str(cfg["learning"].get("drift_algo", "adwin")))
        payload = {
            **drift,
            "updated_at": _utc_iso(),
            "research_loop_triggered": bool(drift.get("drift")),
            "live_auto_change": False,
        }
        _json_save(self.drift_path, payload)
        return payload

    def _infer_regime(self, runs: list[dict[str, Any]]) -> str:
        if not runs:
            return "range"
        recent = runs[:10]
        avg_sharpe = sum(float((r.get("metrics") or {}).get("sharpe", 0.0)) for r in recent) / max(1, len(recent))
        avg_dd = sum(abs(float((r.get("metrics") or {}).get("max_dd", 0.0))) for r in recent) / max(1, len(recent))
        avg_spread = sum(float((r.get("costs_model") or {}).get("spread_bps", 0.0)) for r in recent) / max(1, len(recent))
        if avg_spread > 12:
            return "toxic_flow"
        if avg_dd > 0.22:
            return "high_vol"
        if avg_sharpe > 1.0:
            return "trend"
        return "range"

    def _candidate_seed(self, template_id: str, idx: int) -> int:
        return int(hashlib.sha256(f"{template_id}:{idx}".encode("utf-8")).hexdigest()[:8], 16)

    def _pick_from_range(self, rng: random.Random, spec: Any) -> Any:
        if not isinstance(spec, dict):
            return spec
        vmin = spec.get("min")
        vmax = spec.get("max")
        step = spec.get("step")
        if not isinstance(vmin, (int, float)) or not isinstance(vmax, (int, float)):
            return spec
        if isinstance(step, (int, float)) and float(step) > 0:
            count = int(round((float(vmax) - float(vmin)) / float(step)))
            value = float(vmin) + float(step) * rng.randint(0, max(0, count))
            return int(round(value)) if float(step).is_integer() else round(value, 6)
        return round(rng.uniform(float(vmin), float(vmax)), 6)

    def generate_candidates(self, *, settings: dict[str, Any], runs: list[dict[str, Any]], strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cfg = self.ensure_settings_shape(dict(settings))
        max_candidates = int(cfg["learning"].get("max_candidates", 30) or 30)
        knowledge = self.knowledge.load()
        filters = [row for row in knowledge.filters if bool(row.get("enabled", True))]
        by_strategy = {str(s.get("id")) for s in strategies}
        out: list[dict[str, Any]] = []
        per_template = max(1, max_candidates // max(1, len(knowledge.templates)))
        for template in knowledge.templates:
            template_id = str(template.get("id"))
            ranges = knowledge.ranges.get(template_id, {})
            for idx in range(per_template):
                if len(out) >= max_candidates:
                    break
                rng = random.Random(self._candidate_seed(template_id, idx))
                params: dict[str, Any] = {}
                if isinstance(ranges, dict):
                    for key, spec in ranges.items():
                        params[str(key)] = self._pick_from_range(rng, spec)
                base_strategy_id = str(template.get("base_strategy_id") or "trend_pullback_orderflow_confirm_v1")
                if base_strategy_id not in by_strategy and strategies:
                    base_strategy_id = str(strategies[0].get("id"))
                out.append(
                    {
                        "id": f"cand_{template_id}_{idx+1:03d}",
                        "template_id": template_id,
                        "name": f"{template.get('name', template_id)} #{idx+1}",
                        "base_strategy_id": base_strategy_id,
                        "params": params,
                        "tags": list(template.get("tags") or []),
                        "filters": [str(f.get("id")) for f in filters],
                        "regime_target": str(template.get("category") or "range"),
                    }
                )
        return out[:max_candidates]

    def build_status(self, *, settings: dict[str, Any], strategies: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        regime = self._infer_regime(runs)
        drift = self.compute_drift(settings=cfg, runs=runs)
        learning_pool = self._eligible_learning_pool(strategies)

        selector_candidates: list[dict[str, Any]] = []
        for strategy in learning_pool:
            run = next((r for r in runs if r.get("strategy_id") == strategy.get("id")), None)
            metrics = (run or {}).get("metrics") or {}
            costs = (run or {}).get("costs_breakdown") or {}
            reward = compute_normalized_reward(
                pnl_net=float(metrics.get("return_total", 0.0)) * 10000.0,
                total_costs=float(costs.get("total_cost", 0.0)),
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0))) * 100.0,
                atr=abs(float(metrics.get("max_dd", 0.0))) + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0))) / 10.0 + 0.001,
            )
            selector_candidates.append(
                {
                    "id": str(strategy.get("id")),
                    "tags": list(strategy.get("tags") or []),
                    "reward": reward,
                    "stats": {
                        "wins": 2 if float(metrics.get("sharpe", 0.0)) > 0 else 1,
                        "losses": 2 if float(metrics.get("sharpe", 0.0)) <= 0 else 1,
                        "pulls": 3,
                        "reward_mean": reward,
                        "regime_fit": 1.0 if regime in {str(x) for x in (strategy.get("tags") or [])} else 0.35,
                        "cost_penalty": float(((run or {}).get("costs_model") or {}).get("spread_bps", 0.0)) / 10.0,
                        "risk_penalty": abs(float(metrics.get("max_dd", 0.0))) * 4.0,
                    },
                }
            )
        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        decision = selector.select(selector_candidates, context={"regime": regime})

        snapshot = self.knowledge.load()
        payload = {
            "enabled": bool(learning.get("enabled", False)),
            "mode": str(learning.get("mode", "OFF")).upper(),
            "selector_algo": str(learning.get("selector_algo", "thompson")),
            "drift_algo": str(learning.get("drift_algo", "adwin")),
            "regime": regime,
            "selector": decision,
            "drift": drift,
            "option_b": {"allow_auto_apply": False, "allow_live": False},
            "learning_pool": {
                "count": len(learning_pool),
                "strategy_ids": [str(s.get("id")) for s in learning_pool],
                "empty_block_recommend": len(learning_pool) == 0 and bool(learning.get("enabled", False)),
            },
            "warnings": (
                ["Pool de aprendizaje vacio: marcar estrategias con 'Incluida en Aprendizaje' para recomendar."]
                if len(learning_pool) == 0 and bool(learning.get("enabled", False))
                else []
            ),
            "risk_profile": learning.get("risk_profile") or MEDIUM_RISK_PROFILE,
            "knowledge": {
                "loaded": True,
                "repo_root": str(snapshot.repo_root),
                "template_count": len(snapshot.templates),
                "filter_count": len(snapshot.filters),
            },
            "updated_at": _utc_iso(),
        }
        _json_save(self.status_path, payload)
        return payload

    def load_recommendations(self) -> list[dict[str, Any]]:
        rows = _json_load(self.recommendations_path, [])
        return rows if isinstance(rows, list) else []

    def get_recommendation(self, candidate_id: str) -> dict[str, Any] | None:
        for row in self.load_recommendations():
            if row.get("id") == candidate_id:
                return row
        return None

    def load_all_recommendations(self) -> list[dict[str, Any]]:
        research = [dict(row, recommendation_source="research") for row in self.load_recommendations()]
        runtime = [dict(row, recommendation_source="runtime") for row in self.load_runtime_recommendations()]
        merged: dict[str, dict[str, Any]] = {}
        for row in research:
            rid = str(row.get("id") or "")
            if rid:
                merged[rid] = row
        for row in runtime:
            rid = str(row.get("id") or "")
            if rid:
                merged[rid] = row
        def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
            return (str(item.get("created_at") or item.get("reviewed_at") or ""), str(item.get("id") or ""))
        return sorted(merged.values(), key=_sort_key, reverse=True)

    def get_any_recommendation(self, recommendation_id: str) -> dict[str, Any] | None:
        for row in self.load_all_recommendations():
            if str(row.get("id")) == recommendation_id:
                return row
        return None

    def run_research(
        self,
        *,
        settings: dict[str, Any],
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        backtest_eval: BacktestEvalFn,
    ) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        if not bool(learning.get("enabled")) or str(learning.get("mode", "OFF")).upper() != "RESEARCH":
            raise ValueError("Learning disabled or mode != RESEARCH")
        strategies = self._eligible_learning_pool(strategies)
        if not strategies:
            raise ValueError("Pool de aprendizaje vacio (allow_learning=false en todas las estrategias)")

        drift = self.compute_drift(settings=cfg, runs=runs)
        regime = self._infer_regime(runs)
        candidates = self.generate_candidates(settings=cfg, runs=runs, strategies=strategies)
        evaluated: list[dict[str, Any]] = []
        returns_map: dict[str, list[float]] = {}

        for candidate in candidates:
            result = backtest_eval(candidate)
            metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
            costs = result.get("costs_breakdown", {}) if isinstance(result.get("costs_breakdown"), dict) else {}
            eq = result.get("equity_curve", []) if isinstance(result.get("equity_curve"), list) else []
            eq_vals = [float(p.get("equity", 0.0)) for p in eq if isinstance(p, dict) and "equity" in p]
            ret_series: list[float] = []
            for i in range(1, len(eq_vals)):
                if eq_vals[i - 1]:
                    ret_series.append((eq_vals[i] - eq_vals[i - 1]) / eq_vals[i - 1])
            returns_map[candidate["id"]] = ret_series

            gross = float(costs.get("gross_pnl_total", 0.0))
            total_cost = float(costs.get("total_cost", 0.0))
            reward = compute_normalized_reward(
                pnl_net=gross - total_cost,
                total_costs=total_cost,
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0))) * 100.0,
                atr=abs(float(metrics.get("expectancy_usd_per_trade", metrics.get("expectancy", 0.0)))) / 100.0 + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0))) / 10.0 + 0.001,
            )
            regime_fit = 1.0 if str(candidate.get("regime_target")) == regime else 0.35
            cost_penalty = float(((result.get("costs_model") or {}).get("spread_bps", 0.0))) / 10.0
            risk_penalty = abs(float(metrics.get("max_dd", 0.0))) * (1.3 if regime_fit < 1.0 else 1.0)

            evaluated.append(
                {
                    **candidate,
                    "backtest": {
                        "data_source": result.get("data_source", "unknown"),
                        "dataset_hash": result.get("dataset_hash", ""),
                        "metrics": metrics,
                        "costs_breakdown": costs,
                    },
                    "reward": round(reward, 6),
                    "stats": {
                        "wins": 2 if float(metrics.get("sharpe", 0.0)) > 0 else 1,
                        "losses": 2 if float(metrics.get("sharpe", 0.0)) <= 0 else 1,
                        "pulls": 3,
                        "reward_mean": reward,
                        "regime_fit": regime_fit,
                        "cost_penalty": round(cost_penalty, 6),
                        "risk_penalty": round(risk_penalty, 6),
                    },
                }
            )

        pbo_payload = pbo_cscv(returns_map)
        gates_thresholds = self._canonical_gates_thresholds()
        pbo_max = float(gates_thresholds.get("pbo_max", 0.05))
        dsr_min = float(gates_thresholds.get("dsr_min", 0.95))
        enforce_pbo = bool((learning.get("validation") or {}).get("enforce_pbo", True))
        enforce_dsr = bool((learning.get("validation") or {}).get("enforce_dsr", True))

        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        selector_decision = selector.select(evaluated, context={"regime": regime})

        for row in evaluated:
            dsr_payload = deflated_sharpe_ratio(returns_map.get(str(row["id"]), []), trials=max(1, len(evaluated)))
            reasons: list[str] = []
            accepted = True
            pbo_value = pbo_payload.get("pbo")
            dsr_value = dsr_payload.get("dsr")
            if enforce_pbo and isinstance(pbo_value, (int, float)) and float(pbo_value) > pbo_max:
                accepted = False
                reasons.append(f"PBO alto ({float(pbo_value):.3f} > {pbo_max:.3f})")
            if enforce_dsr and isinstance(dsr_value, (int, float)) and float(dsr_value) < dsr_min:
                accepted = False
                reasons.append(f"DSR bajo ({float(dsr_value):.3f} < {dsr_min:.3f})")
            row["validation"] = {
                "walk_forward": bool((learning.get("validation") or {}).get("walk_forward", True)),
                "pbo": pbo_value,
                "dsr": dsr_value,
                "gates_source": str(gates_thresholds.get("source") or "config/policies/gates.yaml"),
                "cpcv": {
                    "implemented": True,
                    "enforce": bool((learning.get("validation") or {}).get("enforce_cpcv", False)),
                    "note": "backtest_engine_cpcv",
                },
                "purged_cv": {
                    "implemented": True,
                    "enforce": bool((learning.get("validation") or {}).get("enforce_purged_cv", False)),
                    "note": "backtest_engine_purged_cv",
                },
            }
            row["status"] = "APPROVED" if accepted else "REJECTED"
            row["status_reason"] = "; ".join(reasons) if reasons else "Validacion OK"
            row["selector_context"] = {"regime": regime, "drift": bool(drift.get("drift"))}
            row["option_b"] = {"applied_live": False, "requires_admin_adoption": True}

        evaluated.sort(key=lambda r: (r.get("status") == "APPROVED", float(r.get("reward", 0.0))), reverse=True)
        top_n = max(1, int(learning.get("top_n", 5) or 5))
        top = evaluated[:top_n]
        for idx, row in enumerate(top, start=1):
            row["rank"] = idx
            row["explanation"] = self.knowledge.explain_candidate(str(row["id"]))
            row["adoptable_modes"] = ["paper", "testnet"]
            row["generated_params_yaml"] = yaml.safe_dump(row.get("params") or {}, sort_keys=False)
            row["version"] = f"0.1.{idx}"
            row["created_at"] = _utc_iso()

        _json_save(self.recommendations_path, top)
        status_payload = {
            "ok": True,
            "generated": len(candidates),
            "evaluated": len(evaluated),
            "saved_top_n": len(top),
            "drift": drift,
            "selector": selector_decision,
            "option_b": {"allow_auto_apply": False, "allow_live": False},
            "updated_at": _utc_iso(),
        }
        _json_save(self.status_path, {"last_run": status_payload, "mode": str(learning.get("mode", "OFF")).upper()})
        return status_payload

    def load_runtime_recommendations(self) -> list[dict[str, Any]]:
        rows = _json_load(self.recommend_runtime_path, [])
        return rows if isinstance(rows, list) else []

    def _save_runtime_recommendations(self, rows: list[dict[str, Any]]) -> None:
        _json_save(self.recommend_runtime_path, rows[-200:])

    def weights_history(self, *, from_ts: str | None = None, to_ts: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.load_runtime_recommendations():
            ts = str(row.get("created_at") or "")
            if mode and str(row.get("mode") or "").lower() != str(mode).lower():
                continue
            if from_ts and ts and ts < from_ts:
                continue
            if to_ts and ts and ts > to_ts:
                continue
            weights = row.get("weights_sugeridos") if isinstance(row.get("weights_sugeridos"), dict) else {}
            for strategy_id, weight in weights.items():
                out.append(
                    {
                        "ts": ts,
                        "recommendation_id": str(row.get("id") or ""),
                        "mode": str(row.get("mode") or ""),
                        "strategy_id": str(strategy_id),
                        "weight": float(weight or 0.0),
                        "regime": str(row.get("regime") or ""),
                    }
                )
        out.sort(key=lambda x: (x["ts"], x["strategy_id"]))
        return out

    def recommend_from_pool(
        self,
        *,
        settings: dict[str, Any],
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        mode: str = "paper",
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        if not bool(learning.get("enabled")):
            raise ValueError("Aprendizaje deshabilitado")
        selected_engine = self._selected_engine(cfg)
        engine_params = selected_engine.get("params") if isinstance(selected_engine, dict) and isinstance(selected_engine.get("params"), dict) else {}
        engine_id = str(selected_engine.get("id")) if isinstance(selected_engine, dict) else str(learning.get("engine_id") or "")
        pool = self._eligible_learning_pool(strategies)
        if not pool:
            raise ValueError("Pool de aprendizaje vacio (tildá 'Incluida en Aprendizaje')")
        regime = self._infer_regime(runs)
        selector_candidates: list[dict[str, Any]] = []
        ranking: list[dict[str, Any]] = []
        for strategy in pool:
            strategy_id = str(strategy.get("id"))
            strat_runs = [r for r in runs if str(r.get("strategy_id")) == strategy_id and str(r.get("mode") or "backtest").lower() in {"backtest", mode.lower()}]
            latest = strat_runs[0] if strat_runs else None
            metrics = (latest or {}).get("metrics") or {}
            costs = (latest or {}).get("costs_breakdown") or {}
            reward = compute_normalized_reward(
                pnl_net=float(costs.get("net_pnl_total", costs.get("net_pnl", 0.0)) or 0.0),
                total_costs=float(costs.get("total_cost", 0.0) or 0.0),
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0) or 0.0)) * 100.0,
                atr=abs(float(metrics.get("avg_trade", metrics.get("expectancy", 0.0)) or 0.0)) / 100.0 + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0) or 0.0)) / 10.0 + 0.001,
            )
            regime_fit = 1.0 if regime in {str(x) for x in (strategy.get("tags") or [])} else 0.4
            candidate = {
                "id": strategy_id,
                "reward": reward,
                "tags": list(strategy.get("tags") or []),
                "stats": {
                    "wins": max(1, int(round(float(metrics.get("winrate", 0.5)) * 10))),
                    "losses": max(1, int(round((1.0 - float(metrics.get("winrate", 0.5))) * 10))),
                    "pulls": max(2, int(metrics.get("trade_count", metrics.get("roundtrips", 2)) or 2)),
                    "reward_mean": reward,
                    "regime_fit": regime_fit,
                    "cost_penalty": float(((latest or {}).get("costs_model") or {}).get("spread_bps", 0.0)) / 10.0,
                    "risk_penalty": abs(float(metrics.get("max_dd", 0.0) or 0.0)) * 4.0,
                },
            }
            selector_candidates.append(candidate)
            ranking.append(
                {
                    "strategy_id": strategy_id,
                    "name": strategy.get("name", strategy_id),
                    "reward": round(float(reward), 6),
                    "winrate": float(metrics.get("winrate", 0.0) or 0.0),
                    "trade_count": int(metrics.get("trade_count", metrics.get("roundtrips", 0)) or 0),
                    "expectancy": float(metrics.get("expectancy_usd_per_trade", metrics.get("expectancy", 0.0)) or 0.0),
                    "expectancy_unit": str(metrics.get("expectancy_unit") or "usd_por_trade"),
                    "max_dd": float(metrics.get("max_dd", 0.0) or 0.0),
                    "sharpe": float(metrics.get("sharpe", 0.0) or 0.0),
                    "sortino": float(metrics.get("sortino", 0.0) or 0.0),
                    "calmar": float(metrics.get("calmar", 0.0) or 0.0),
                }
            )
        runtime_rows = self.load_runtime_recommendations()
        guardrail_warnings: list[str] = []
        min_trades_per_arm = int(engine_params.get("min_trades_per_arm", 0) or 0)
        if min_trades_per_arm > 0:
            filtered = [row for row in ranking if int(row.get("trade_count", 0) or 0) >= min_trades_per_arm]
            if not filtered:
                # Bootstrap seguro: si no hay evidencia suficiente todavía, permitimos recomendar
                # pero dejamos warning explícito para que no se interprete como señal fuerte.
                bootstrap_ok = (len(selector_candidates) <= 1) or (len(runtime_rows) == 0)
                if not bootstrap_ok:
                    raise ValueError(f"Bloqueado (anti performance-chasing): ninguna estrategia cumple min_trades_per_arm={min_trades_per_arm}")
                guardrail_warnings.append(
                    f"Bootstrap sin evidencia suficiente: ninguna estrategia cumple min_trades_per_arm={min_trades_per_arm}. "
                    "La recomendacion es de baja confianza (Opcion B, requiere aprobacion)."
                )
            else:
                allowed_ids = {row["strategy_id"] for row in filtered}
                selector_candidates = [row for row in selector_candidates if str(row.get("id")) in allowed_ids]
                ranking = filtered
        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        decision = selector.select(selector_candidates, context={"regime": regime})
        ranking.sort(key=lambda r: r["reward"], reverse=True)
        top = ranking[: max(1, int(learning.get("top_n", 5) or 5))]
        if decision.get("active_strategy_id"):
            total_positive = sum(max(0.0, float(r["reward"])) for r in top) or 1.0
            weights = {
                r["strategy_id"]: round(max(0.0, float(r["reward"])) / total_positive, 4)
                for r in top
            }
        else:
            weights = {}
        max_switch_per_day = int(engine_params.get("max_switch_per_day", 0) or 0)
        if max_switch_per_day > 0:
            now_dt = datetime.now(timezone.utc)
            start_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_rows = []
            for row in runtime_rows:
                try:
                    ts = datetime.fromisoformat(str(row.get("created_at")).replace("Z", "+00:00"))
                except Exception:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts = ts.astimezone(timezone.utc)
                if ts >= start_day and str(row.get("mode") or "").lower() == str(mode).lower():
                    daily_rows.append(row)
            switches = 0
            last_active = None
            for row in sorted(daily_rows, key=lambda x: str(x.get("created_at") or "")):
                active = str(row.get("active_strategy_id") or "")
                if active and last_active and active != last_active:
                    switches += 1
                if active:
                    last_active = active
            proposed_active = str(decision.get("active_strategy_id") or "")
            if last_active and proposed_active and proposed_active != last_active and switches >= max_switch_per_day:
                raise ValueError(f"Bloqueado por cooldown: max_switch_per_day={max_switch_per_day} alcanzado")
        max_weight_change_pct = float(engine_params.get("max_weight_change_pct", 0.0) or 0.0)
        if max_weight_change_pct > 0 and runtime_rows and weights:
            prev = next((row for row in reversed(runtime_rows) if str(row.get("mode") or "").lower() == str(mode).lower()), None)
            prev_weights = prev.get("weights_sugeridos") if isinstance(prev, dict) and isinstance(prev.get("weights_sugeridos"), dict) else {}
            if prev_weights:
                clamped: dict[str, float] = {}
                keys = set(prev_weights.keys()) | set(weights.keys())
                for key in keys:
                    prev_w = float(prev_weights.get(key, 0.0) or 0.0)
                    cur_w = float(weights.get(key, 0.0) or 0.0)
                    delta = max(-max_weight_change_pct, min(max_weight_change_pct, cur_w - prev_w))
                    clamped[key] = max(0.0, round(prev_w + delta, 4))
                total = sum(clamped.values()) or 1.0
                weights = {k: round(v / total, 4) for k, v in clamped.items()}
        recommendation = {
            "id": f"rec_{hashlib.sha256(f'{mode}:{regime}:{_utc_iso()}'.encode('utf-8')).hexdigest()[:10]}",
            "status": "PENDING_REVIEW",
            "mode": str(mode).lower(),
            "from_ts": from_ts,
            "to_ts": to_ts,
            "regime": regime,
            "selector_algo": str(learning.get("selector_algo", "thompson")),
            "engine_id": engine_id,
            "active_strategy_id": decision.get("active_strategy_id"),
            "weights_sugeridos": weights,
            "ranking": top,
            "option_b": {"allow_auto_apply": False, "allow_live": False, "requires_human_approval": True},
            "guardrails": {
                "warnings": guardrail_warnings,
                "min_trades_per_arm": min_trades_per_arm,
                "max_switch_per_day": max_switch_per_day,
                "max_weight_change_pct": max_weight_change_pct,
            },
            "created_at": _utc_iso(),
        }
        rows = self.load_runtime_recommendations()
        rows.append(recommendation)
        self._save_runtime_recommendations(rows)
        return recommendation

    def update_runtime_recommendation_status(self, recommendation_id: str, *, status: str, note: str | None = None) -> dict[str, Any] | None:
        rows = self.load_runtime_recommendations()
        found: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("id")) == recommendation_id:
                row["status"] = status
                row["reviewed_at"] = _utc_iso()
                if note:
                    row["note"] = note
                found = row
                break
        if found is not None:
            self._save_runtime_recommendations(rows)
        return found
