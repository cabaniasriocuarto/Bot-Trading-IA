from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class KnowledgeValidationError(ValueError):
    pass


EMBEDDED_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "trend_pullback_of",
        "name": "Tendencia + Pullback + Order Flow",
        "category": "trend",
        "base_strategy_id": "trend_pullback_orderflow_v2",
        "description": "Fallback embebido para deploys sin carpeta knowledge.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["trend", "pullback", "orderflow", "robust"],
    },
    {
        "id": "breakout_vol_exp",
        "name": "Breakout + Expansión de Volatilidad",
        "category": "breakout",
        "base_strategy_id": "breakout_volatility_v2",
        "description": "Fallback embebido para rupturas con expansión de volatilidad.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["breakout", "volatility", "momentum"],
    },
    {
        "id": "meanrev_range_costaware",
        "name": "Reversión a la Media (Rango) + Cost Aware",
        "category": "range",
        "base_strategy_id": "meanreversion_range_v2",
        "description": "Fallback embebido para regimen lateral.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["range", "mean_reversion", "cost_control"],
    },
    {
        "id": "trend_scan_regime",
        "name": "Trend Scanning + Regímenes",
        "category": "regime",
        "base_strategy_id": "trend_scanning_regime_v2",
        "description": "Fallback embebido para switching por regímenes.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["regime", "trend_scanning", "adaptive"],
    },
    {
        "id": "defensive_quality",
        "name": "Defensiva: Calidad de Ejecución + Liquidez",
        "category": "defensive",
        "base_strategy_id": "defensive_liquidity_v2",
        "description": "Fallback embebido para modo defensivo y control de costos.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["defensive", "liquidity", "low_cost"],
    },
]

EMBEDDED_FILTERS: list[dict[str, Any]] = [
    {"id": "spread_guard", "name": "Guardia de Spread", "description": "Bloquea spread excesivo.", "kind": "cost", "enabled": True},
    {"id": "slippage_guard", "name": "Guardia de Slippage", "description": "Penaliza slippage alto.", "kind": "cost", "enabled": True},
    {"id": "vpin_toxicity_guard", "name": "Guardia de Toxicidad (VPIN)", "description": "Bloquea toxicidad alta.", "kind": "microstructure", "enabled": True},
    {"id": "liquidity_guard", "name": "Guardia de Liquidez", "description": "Exige liquidez minima.", "kind": "risk", "enabled": True},
    {"id": "correlation_guard", "name": "Guardia de Correlación", "description": "Penaliza correlacion alta.", "kind": "risk", "enabled": True},
    {"id": "regime_gate", "name": "Gate de Régimen", "description": "Exige compatibilidad con regimen.", "kind": "regime", "enabled": True},
]

EMBEDDED_RANGES: dict[str, Any] = {
    "trend_pullback_of": {
        "ema_fast": {"min": 15, "max": 30, "step": 1},
        "ema_mid": {"min": 40, "max": 80, "step": 2},
        "ema_slow": {"min": 150, "max": 250, "step": 5},
        "adx_threshold": {"min": 14, "max": 35, "step": 1},
        "atr_stop_mult": {"min": 1.2, "max": 3.0, "step": 0.1},
        "atr_take_mult": {"min": 1.8, "max": 4.5, "step": 0.1},
        "trail_distance_atr": {"min": 0.8, "max": 3.0, "step": 0.1},
        "time_stop_bars": {"min": 6, "max": 30, "step": 1},
    },
    "breakout_vol_exp": {
        "breakout_window": {"min": 10, "max": 60, "step": 1},
        "atr_expansion_z": {"min": 0.5, "max": 2.5, "step": 0.1},
        "volume_zscore_min": {"min": 0.5, "max": 3.0, "step": 0.1},
        "atr_stop_mult": {"min": 1.0, "max": 3.5, "step": 0.1},
        "atr_take_mult": {"min": 1.5, "max": 5.0, "step": 0.1},
        "trail_activate_atr": {"min": 0.8, "max": 2.5, "step": 0.1},
    },
    "meanrev_range_costaware": {
        "rsi_buy_threshold": {"min": 22, "max": 40, "step": 1},
        "rsi_sell_threshold": {"min": 60, "max": 78, "step": 1},
        "atr_stop_mult": {"min": 0.8, "max": 2.0, "step": 0.1},
        "atr_take_mult": {"min": 1.0, "max": 2.8, "step": 0.1},
        "time_stop_bars": {"min": 4, "max": 18, "step": 1},
    },
    "trend_scan_regime": {
        "tscan_lookback": {"min": 50, "max": 250, "step": 10},
        "tscan_min_strength": {"min": 1.0, "max": 4.0, "step": 0.1},
        "adx_threshold": {"min": 16, "max": 32, "step": 1},
        "atr_stop_mult": {"min": 1.4, "max": 2.6, "step": 0.1},
        "atr_take_mult": {"min": 2.0, "max": 4.0, "step": 0.1},
    },
    "defensive_quality": {
        "max_spread_bps": {"min": 4, "max": 18, "step": 1},
        "max_slippage_bps": {"min": 2, "max": 15, "step": 1},
        "vpin_max_pctl": {"min": 0.70, "max": 0.95, "step": 0.01},
        "min_liquidity_score": {"min": 0.60, "max": 0.90, "step": 0.01},
        "atr_stop_mult": {"min": 1.6, "max": 2.8, "step": 0.1},
        "atr_take_mult": {"min": 2.0, "max": 4.0, "step": 0.1},
    },
}

EMBEDDED_GATES: dict[str, Any] = {
    "pbo": {"enabled": True, "max_allowed": 0.30, "reject_reason": "PBO alto: riesgo de overfitting."},
    "dsr": {"enabled": True, "min_allowed": 1.20, "reject_reason": "DSR bajo: Sharpe no robusto tras corrección."},
    "psr": {"enabled": False, "min_allowed": 0.75, "reject_reason": "PSR bajo."},
    "live_auto_apply": {"enabled": False, "reject_reason": "Opción B: requiere aprobación humana para promover a LIVE."},
}

EMBEDDED_LEARNING_ENGINES: dict[str, Any] = {
    "version": 2,
    "learning_mode": {"option": "B", "enabled_default": True, "auto_apply_live": False, "require_human_approval": True},
    "drift_detection": {
        "enabled": True,
        "detectors": [
            {"id": "cusum_returns", "name": "CUSUM en retornos", "enabled": True, "params": {"window_bars": 200, "threshold_sigma": 5.0}},
            {"id": "volatility_shift", "name": "Cambio de volatilidad (ATR/realizada)", "enabled": True, "params": {"window_bars": 200, "trigger_ratio": 1.6}},
        ],
    },
    "engines": [
        {"id": "fixed_rules", "name": "Reglas fijas (sin aprendizaje)", "enabled_default": True, "ui_help": "Control total / baseline."},
        {"id": "bandit_thompson", "name": "Bandit (Thompson)", "enabled_default": True, "ui_help": "Explora/explota por régimen."},
        {"id": "meta_rf_selector", "name": "Meta-modelo Random Forest", "enabled_default": False, "ui_help": "Offline, requiere pipeline estable."},
        {"id": "dqn_offline_experimental", "name": "RL (DQN offline) [EXPERIMENTAL]", "enabled_default": False, "ui_help": "No recomendado para live."},
    ],
    "safe_update": {"enabled": True, "gates_file": "knowledge/policies/gates.yaml", "canary_schedule_pct": [0, 5, 15, 35, 60, 100], "rollback_auto": True},
}

EMBEDDED_VISUAL_CUES: dict[str, Any] = {
    "version": 2,
    "palette": {
        "muy_malo": "#7C3AED",
        "malo": "#EF4444",
        "aceptable": "#F97316",
        "bueno": "#FACC15",
        "excelente": "#22C55E",
    },
    "thresholds": {
        "Sharpe": {"muy_malo": 0.0, "malo": 0.5, "aceptable": 1.0, "bueno": 1.5, "excelente": 2.0},
        "Sortino": {"muy_malo": 0.0, "malo": 0.7, "aceptable": 1.3, "bueno": 2.0, "excelente": 3.0},
        "Calmar": {"muy_malo": 0.0, "malo": 0.5, "aceptable": 1.0, "bueno": 1.5, "excelente": 2.5},
    },
    "ui": {"apply_to_backtest_kpi_cards": True, "apply_to_table_cells": True, "show_grade_label": True},
}

EMBEDDED_STRATEGIES_V2: dict[str, Any] = {
    "version": 2,
    "agresividad": "media",
    "global_defaults": {"timeframes": ["5m", "10m", "15m"]},
    "strategies": [
        {"id": "trend_pullback_orderflow_v2", "name": "Tendencia + Pullback + Order Flow"},
        {"id": "breakout_volatility_v2", "name": "Breakout + Expansión de Volatilidad"},
        {"id": "meanreversion_range_v2", "name": "Mean Reversion (Rango) + Cost Aware"},
        {"id": "trend_scanning_regime_v2", "name": "Trend Scanning + Regímenes"},
        {"id": "defensive_liquidity_v2", "name": "Defensiva: Calidad de Ejecución + Liquidez"},
    ],
}

EMBEDDED_GLOSSARY: dict[str, str] = {
    "PBO": "Probability of Backtest Overfitting. Estima sobreajuste entre IS/OOS.",
    "DSR": "Deflated Sharpe Ratio. Ajusta Sharpe por sesgo de seleccion y numero de pruebas.",
    "Sharpe": "Retorno medio ajustado por volatilidad.",
    "Sortino": "Variante del Sharpe que penaliza volatilidad bajista.",
    "Calmar": "Relacion entre CAGR y max drawdown.",
    "Robustness Score": "Score agregado para comparar estabilidad y sensibilidad del backtest.",
}


def _yaml_map(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise
    except Exception as exc:  # pragma: no cover
        raise KnowledgeValidationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgeValidationError(f"YAML root must be map: {path}")
    return payload


def _find_repo_root(start_points: list[Path]) -> Path:
    for base in start_points:
        for candidate in [base, *base.parents]:
            if (candidate / "knowledge").exists():
                return candidate.resolve()
    raise KnowledgeValidationError("knowledge/ directory not found from provided roots")


@dataclass(slots=True)
class KnowledgeSnapshot:
    repo_root: Path
    templates: list[dict[str, Any]]
    filters: list[dict[str, Any]]
    ranges: dict[str, Any]
    gates: dict[str, Any]
    glossary: dict[str, str]
    learning_engines: dict[str, Any]
    visual_cues: dict[str, Any]
    strategies_v2: dict[str, Any]


class KnowledgeLoader:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        explicit = Path(repo_root).resolve() if repo_root else None
        starts = [explicit] if explicit else [Path.cwd(), Path(__file__).resolve()]
        self._fallback_mode = False
        self._fallback_reason = ""
        try:
            self.repo_root = _find_repo_root([p for p in starts if p is not None])
            self.knowledge_root = (self.repo_root / "knowledge").resolve()
        except KnowledgeValidationError as exc:
            self.repo_root = (explicit or Path.cwd()).resolve()
            self.knowledge_root = (self.repo_root / "knowledge").resolve()
            self._fallback_mode = True
            self._fallback_reason = str(exc)
        self._snapshot: KnowledgeSnapshot | None = None

    def _embedded_snapshot(self) -> KnowledgeSnapshot:
        return KnowledgeSnapshot(
            repo_root=self.repo_root,
            templates=copy.deepcopy(EMBEDDED_TEMPLATES),
            filters=copy.deepcopy(EMBEDDED_FILTERS),
            ranges=copy.deepcopy(EMBEDDED_RANGES),
            gates=copy.deepcopy(EMBEDDED_GATES),
            glossary=copy.deepcopy(EMBEDDED_GLOSSARY),
            learning_engines=copy.deepcopy(EMBEDDED_LEARNING_ENGINES),
            visual_cues=copy.deepcopy(EMBEDDED_VISUAL_CUES),
            strategies_v2=copy.deepcopy(EMBEDDED_STRATEGIES_V2),
        )

    def _parse_glossary(self, path: Path) -> dict[str, str]:
        text = path.read_text(encoding="utf-8")
        out: dict[str, str] = {}
        current: str | None = None
        buf: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                if current and buf:
                    out[current] = " ".join(x for x in buf if x).strip()
                current = line[3:].strip()
                buf = []
                continue
            if current is not None and line and not line.startswith("#"):
                buf.append(line)
        if current and buf:
            out[current] = " ".join(x for x in buf if x).strip()
        return out

    def load(self, force: bool = False) -> KnowledgeSnapshot:
        if self._snapshot and not force:
            return self._snapshot

        if self._fallback_mode:
            self._snapshot = self._embedded_snapshot()
            return self._snapshot

        try:
            templates_payload = _yaml_map(self.knowledge_root / "templates" / "strategy_templates.yaml")
            filters_payload = _yaml_map(self.knowledge_root / "templates" / "filters.yaml")
            ranges_payload = _yaml_map(self.knowledge_root / "templates" / "parameter_ranges.yaml")
            gates_payload = _yaml_map(self.knowledge_root / "policies" / "gates.yaml")
            learning_engines_payload = _yaml_map(self.knowledge_root / "templates" / "learning_engines.yaml")
            visual_cues_payload = _yaml_map(self.knowledge_root / "templates" / "visual_cues.yaml")
            strategies_v2_payload = _yaml_map(self.knowledge_root / "strategies" / "strategies_v2.yaml")
            glossary = self._parse_glossary(self.knowledge_root / "glossary" / "metrics.md")
        except FileNotFoundError:
            self._fallback_mode = True
            self._fallback_reason = f"knowledge files missing under {self.knowledge_root}"
            self._snapshot = self._embedded_snapshot()
            return self._snapshot

        templates = templates_payload.get("templates") or []
        filters = filters_payload.get("filters") or []
        ranges = ranges_payload.get("ranges") or {}
        gates = gates_payload.get("gates") or {}
        learning_engines = learning_engines_payload
        visual_cues = visual_cues_payload
        strategies_v2 = strategies_v2_payload

        if not isinstance(templates, list) or not all(isinstance(row, dict) and row.get("id") for row in templates):
            raise KnowledgeValidationError("templates/strategy_templates.yaml invalid or missing template ids")
        if not isinstance(filters, list) or not all(isinstance(row, dict) and row.get("id") for row in filters):
            raise KnowledgeValidationError("templates/filters.yaml invalid or missing filter ids")
        if not isinstance(ranges, dict):
            raise KnowledgeValidationError("templates/parameter_ranges.yaml ranges must be map")
        if not isinstance(gates, dict):
            raise KnowledgeValidationError("policies/gates.yaml gates must be map")
        if not isinstance(learning_engines, dict):
            raise KnowledgeValidationError("templates/learning_engines.yaml root must be map")
        if not isinstance(visual_cues, dict):
            raise KnowledgeValidationError("templates/visual_cues.yaml root must be map")
        if not isinstance(strategies_v2, dict):
            raise KnowledgeValidationError("strategies/strategies_v2.yaml root must be map")
        for template in templates:
            template_id = str(template.get("id"))
            if template_id not in ranges:
                raise KnowledgeValidationError(f"Missing parameter ranges for template: {template_id}")
        engines = learning_engines.get("engines") or []
        if not isinstance(engines, list) or not all(isinstance(row, dict) and row.get("id") for row in engines):
            raise KnowledgeValidationError("templates/learning_engines.yaml invalid or missing engine ids")
        palette = visual_cues.get("palette")
        thresholds = visual_cues.get("thresholds")
        if not isinstance(palette, dict) or not isinstance(thresholds, dict):
            raise KnowledgeValidationError("templates/visual_cues.yaml must include palette and thresholds maps")
        strategy_specs = strategies_v2.get("strategies") or []
        if not isinstance(strategy_specs, list) or not all(isinstance(row, dict) and row.get("id") for row in strategy_specs):
            raise KnowledgeValidationError("strategies/strategies_v2.yaml invalid or missing strategy ids")
        strategy_ids = {str(row.get("id")) for row in strategy_specs}
        missing_bases = sorted(
            str(t.get("base_strategy_id"))
            for t in templates
            if str(t.get("base_strategy_id")) and str(t.get("base_strategy_id")) not in strategy_ids
        )
        if missing_bases:
            raise KnowledgeValidationError(f"strategy_templates.yaml base_strategy_id missing in strategies_v2.yaml: {', '.join(missing_bases)}")
        required_glossary = {"PBO", "DSR", "Sharpe", "Robustness Score"}
        if not required_glossary.issubset(set(glossary.keys())):
            missing = sorted(required_glossary - set(glossary.keys()))
            raise KnowledgeValidationError(f"Missing glossary sections: {', '.join(missing)}")

        self._snapshot = KnowledgeSnapshot(
            repo_root=self.repo_root,
            templates=templates,
            filters=filters,
            ranges=ranges,
            gates=gates,
            glossary=glossary,
            learning_engines=learning_engines,
            visual_cues=visual_cues,
            strategies_v2=strategies_v2,
        )
        return self._snapshot

    def list_templates(self) -> list[dict[str, Any]]:
        return list(self.load().templates)

    def list_filters(self) -> list[dict[str, Any]]:
        return list(self.load().filters)

    def get_ranges(self, template_id: str) -> dict[str, Any]:
        snapshot = self.load()
        return dict(snapshot.ranges.get(template_id, {}))

    def get_gates(self) -> dict[str, Any]:
        return dict(self.load().gates)

    def get_learning_engines(self) -> dict[str, Any]:
        return copy.deepcopy(self.load().learning_engines)

    def get_visual_cues(self) -> dict[str, Any]:
        return copy.deepcopy(self.load().visual_cues)

    def get_strategies_v2(self) -> dict[str, Any]:
        return copy.deepcopy(self.load().strategies_v2)

    def explain_candidate(self, candidate_id: str) -> dict[str, Any]:
        snapshot = self.load()
        glossary = snapshot.glossary
        return {
            "candidate_id": candidate_id,
            "highlights": {
                "PBO": glossary.get("PBO", ""),
                "DSR": glossary.get("DSR", ""),
                "Robustness Score": glossary.get("Robustness Score", ""),
            },
            "note": "La evaluacion usa PBO/DSR y score de robustez antes de recomendar.",
        }
