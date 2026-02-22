from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class KnowledgeValidationError(ValueError):
    pass


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
        self.repo_root = _find_repo_root([p for p in starts if p is not None])
        self.knowledge_root = (self.repo_root / "knowledge").resolve()
        self._snapshot: KnowledgeSnapshot | None = None

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

        templates_payload = _yaml_map(self.knowledge_root / "templates" / "strategy_templates.yaml")
        filters_payload = _yaml_map(self.knowledge_root / "templates" / "filters.yaml")
        ranges_payload = _yaml_map(self.knowledge_root / "templates" / "parameter_ranges.yaml")
        gates_payload = _yaml_map(self.knowledge_root / "policies" / "gates.yaml")
        glossary = self._parse_glossary(self.knowledge_root / "glossary" / "metrics.md")

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
