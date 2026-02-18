from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from rtlab_core.strategy_packs.dsl_parser import parse_expression
from rtlab_core.strategy_packs.dsl_schema import PackSpec


RULE_PATTERN = re.compile(r"^rule\s+([a-zA-Z0-9_]+)\s*:\s*(.+)$")


@dataclass(slots=True)
class PackDocument:
    path: Path
    spec: PackSpec
    rules: dict[str, str]
    raw_frontmatter: dict[str, object]


def _split_frontmatter(raw: str) -> tuple[str, str]:
    raw = raw.lstrip("\ufeff")
    if not raw.startswith("---\n"):
        raise ValueError("Pack must start with YAML frontmatter delimiter '---'")
    parts = raw.split("\n---\n", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Pack must contain closing frontmatter delimiter")
    frontmatter = parts[0][4:]
    body = parts[1].strip()
    return frontmatter, body


def _parse_rules(body: str) -> dict[str, str]:
    rules: dict[str, str] = {}
    for line in body.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        match = RULE_PATTERN.match(clean)
        if not match:
            raise ValueError(f"Invalid DSL rule line: {line}")
        name, expression = match.group(1), match.group(2)
        parse_expression(expression)
        rules[name] = expression
    if not rules:
        raise ValueError("No DSL rules found in pack")
    return rules


def load_pack(path: str | Path) -> PackDocument:
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    frontmatter_str, body = _split_frontmatter(raw)
    frontmatter_obj = yaml.safe_load(frontmatter_str) or {}
    spec = PackSpec.model_validate(frontmatter_obj)
    rules = _parse_rules(body)
    return PackDocument(path=file_path, spec=spec, rules=rules, raw_frontmatter=frontmatter_obj)
