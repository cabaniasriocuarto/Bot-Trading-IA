from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class KnowledgeValidationError(ValueError):
    pass


EMBEDDED_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "trend_pullback",
        "name": "Trend Pullback",
        "category": "trend",
        "base_strategy_id": "trend_pullback_orderflow_confirm_v1",
        "description": "Fallback embebido para deploys sin carpeta knowledge.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["trend", "pullback", "momentum"],
    },
    {
        "id": "mean_reversion_range",
        "name": "Mean Reversion Range",
        "category": "range",
        "base_strategy_id": "trend_pullback_orderflow_confirm_v1",
        "description": "Fallback embebido para regimen lateral.",
        "allowed_markets": ["crypto", "forex", "equities"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["range", "mean_reversion"],
    },
    {
        "id": "breakout_volatility",
        "name": "Breakout Volatility",
        "category": "high_vol",
        "base_strategy_id": "trend_pullback_orderflow_confirm_v1",
        "description": "Fallback embebido para rupturas en volatilidad.",
        "allowed_markets": ["crypto", "forex"],
        "allowed_timeframes": ["5m", "10m", "15m"],
        "tags": ["breakout", "volatility"],
    },
]

EMBEDDED_FILTERS: list[dict[str, Any]] = [
    {"id": "spread_guard", "name": "Spread Guard", "description": "Bloquea spread excesivo.", "kind": "cost", "enabled": True},
    {"id": "slippage_guard", "name": "Slippage Guard", "description": "Penaliza slippage alto.", "kind": "cost", "enabled": True},
    {"id": "correlation_guard", "name": "Correlation Guard", "description": "Penaliza correlacion alta.", "kind": "risk", "enabled": True},
    {"id": "regime_gate", "name": "Regime Gate", "description": "Exige compatibilidad con regimen.", "kind": "regime", "enabled": True},
]

EMBEDDED_RANGES: dict[str, Any] = {
    "trend_pullback": {
        "adx_threshold": {"min": 14, "max": 35, "step": 1},
        "atr_stop_mult": {"min": 1.2, "max": 3.0, "step": 0.1},
        "atr_take_mult": {"min": 1.8, "max": 4.5, "step": 0.1},
        "trail_distance_atr": {"min": 0.8, "max": 3.0, "step": 0.1},
        "time_stop_bars": {"min": 6, "max": 30, "step": 1},
    },
    "mean_reversion_range": {
        "rsi_buy_threshold": {"min": 22, "max": 40, "step": 1},
        "rsi_sell_threshold": {"min": 60, "max": 78, "step": 1},
        "atr_stop_mult": {"min": 0.8, "max": 2.0, "step": 0.1},
        "atr_take_mult": {"min": 1.0, "max": 2.8, "step": 0.1},
        "time_stop_bars": {"min": 4, "max": 18, "step": 1},
    },
    "breakout_volatility": {
        "breakout_window": {"min": 10, "max": 60, "step": 1},
        "volume_zscore_min": {"min": 0.5, "max": 3.0, "step": 0.1},
        "atr_stop_mult": {"min": 1.0, "max": 3.5, "step": 0.1},
        "atr_take_mult": {"min": 1.5, "max": 5.0, "step": 0.1},
        "trail_activate_atr": {"min": 0.8, "max": 2.5, "step": 0.1},
    },
}

EMBEDDED_GATES: dict[str, Any] = {
    "pbo": {"enabled": True, "max_allowed": 0.55, "reject_reason": "PBO alto (riesgo de sobreajuste)."},
    "dsr": {"enabled": True, "min_allowed": 0.10, "reject_reason": "DSR bajo (Sharpe no robusto tras correccion)."},
    "live_auto_apply": {"enabled": False, "reject_reason": "No permitido por Opcion B (solo recomendaciones)."},
    "cpcv": {"enabled": False, "enforce": False, "note": "Hook listo; implementacion parcial permitida."},
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
            templates=[dict(row) for row in EMBEDDED_TEMPLATES],
            filters=[dict(row) for row in EMBEDDED_FILTERS],
            ranges={k: dict(v) for k, v in EMBEDDED_RANGES.items()},
            gates=dict(EMBEDDED_GATES),
            glossary=dict(EMBEDDED_GLOSSARY),
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

        if not isinstance(templates, list) or not all(isinstance(row, dict) and row.get("id") for row in templates):
            raise KnowledgeValidationError("templates/strategy_templates.yaml invalid or missing template ids")
        if not isinstance(filters, list) or not all(isinstance(row, dict) and row.get("id") for row in filters):
            raise KnowledgeValidationError("templates/filters.yaml invalid or missing filter ids")
        if not isinstance(ranges, dict):
            raise KnowledgeValidationError("templates/parameter_ranges.yaml ranges must be map")
        if not isinstance(gates, dict):
            raise KnowledgeValidationError("policies/gates.yaml gates must be map")
        for template in templates:
            template_id = str(template.get("id"))
            if template_id not in ranges:
                raise KnowledgeValidationError(f"Missing parameter ranges for template: {template_id}")
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
