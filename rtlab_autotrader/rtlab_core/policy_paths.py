from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


EXPECTED_POLICY_FILENAMES: tuple[str, ...] = (
    "gates.yaml",
    "microstructure.yaml",
    "risk_policy.yaml",
    "beast_mode.yaml",
    "fees.yaml",
    "fundamentals_credit_filter.yaml",
    "runtime_controls.yaml",
    "instrument_registry.yaml",
    "universes.yaml",
    "cost_stack.yaml",
    "reporting_exports.yaml",
    "execution_safety.yaml",
    "execution_router.yaml",
)


def _normalize_policy_root(path: Path) -> Path:
    target = path.resolve()
    if target.is_file():
        return target.parent.resolve()
    return target


def policy_root_candidates(repo_root: Path, *, explicit: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    env_root = str(os.getenv("RTLAB_CONFIG_POLICIES_ROOT", "")).strip()
    if env_root:
        roots.append(_normalize_policy_root(Path(env_root)))
    if explicit is not None:
        roots.append(_normalize_policy_root(explicit))

    repo_root = repo_root.resolve()
    roots.append((repo_root / "config" / "policies").resolve())
    roots.append((repo_root / "rtlab_autotrader" / "config" / "policies").resolve())
    if repo_root.name.lower() == "rtlab_autotrader":
        roots.append((repo_root.parent / "config" / "policies").resolve())

    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _policy_score(path: Path, *, expected_files: tuple[str, ...]) -> tuple[int, int]:
    if not path.exists():
        return (-1, 0)
    matches = sum(1 for name in expected_files if (path / name).exists())
    return (matches, len(expected_files))


def _policy_file_digest(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_root_role(repo_root: Path, candidate: Path, *, explicit: Path | None = None) -> str:
    env_root = str(os.getenv("RTLAB_CONFIG_POLICIES_ROOT", "")).strip()
    normalized_candidate = _normalize_policy_root(candidate)
    repo_root = repo_root.resolve()

    if env_root and normalized_candidate == _normalize_policy_root(Path(env_root)):
        return "env_override"
    if explicit is not None and normalized_candidate == _normalize_policy_root(explicit):
        if normalized_candidate == (repo_root / "config" / "policies").resolve():
            return "monorepo_root"
        return "explicit"
    if normalized_candidate == (repo_root / "config" / "policies").resolve():
        return "monorepo_root"
    if normalized_candidate == (repo_root / "rtlab_autotrader" / "config" / "policies").resolve():
        return "nested_backend_compat"
    if repo_root.name.lower() == "rtlab_autotrader" and normalized_candidate == (repo_root.parent / "config" / "policies").resolve():
        return "monorepo_parent_root"
    return "candidate"


def describe_policy_root_resolution(
    repo_root: Path,
    *,
    explicit: Path | None = None,
    expected_files: tuple[str, ...] = EXPECTED_POLICY_FILENAMES,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    candidates = policy_root_candidates(repo_root, explicit=explicit)
    selected_root = resolve_policy_root(repo_root, explicit=explicit, expected_files=expected_files).resolve()
    canonical_root = candidates[0].resolve() if candidates else _normalize_policy_root(explicit or repo_root)
    warnings: list[str] = []
    candidate_payloads: list[dict[str, Any]] = []
    divergent_candidates: list[dict[str, Any]] = []

    for candidate in candidates:
        normalized = candidate.resolve()
        matches, total = _policy_score(normalized, expected_files=expected_files)
        row = {
            "path": str(normalized),
            "role": _policy_root_role(repo_root, normalized, explicit=explicit),
            "selected": normalized == selected_root,
            "exists": normalized.exists(),
            "expected_files_present": max(matches, 0),
            "expected_files_total": total,
        }

        differing_files: list[str] = []
        if normalized.exists() and normalized != selected_root:
            for filename in expected_files:
                selected_file = selected_root / filename
                candidate_file = normalized / filename
                if not selected_file.exists() or not candidate_file.exists():
                    continue
                if _policy_file_digest(selected_file) != _policy_file_digest(candidate_file):
                    differing_files.append(filename)
        if differing_files:
            row["differing_files_vs_selected"] = differing_files
            divergent_candidates.append(
                {
                    "path": str(normalized),
                    "role": row["role"],
                    "differing_files_vs_selected": differing_files,
                }
            )
            warnings.append(
                "Se detectaron YAML divergentes entre "
                f"{selected_root} y {normalized}: {', '.join(differing_files)}"
            )
        candidate_payloads.append(row)

    if selected_root != canonical_root:
        warnings.append(
            "El runtime no usa la raiz canonica esperada de config/policies; "
            f"cayo en compatibilidad sobre {selected_root}."
        )

    return {
        "selected_root": str(selected_root),
        "selected_role": _policy_root_role(repo_root, selected_root, explicit=explicit),
        "canonical_root": str(canonical_root),
        "canonical_role": _policy_root_role(repo_root, canonical_root, explicit=explicit),
        "fallback_used": selected_root != canonical_root,
        "candidates": candidate_payloads,
        "divergent_candidates": divergent_candidates,
        "warnings": warnings,
    }


def resolve_policy_root(
    repo_root: Path,
    *,
    explicit: Path | None = None,
    expected_files: tuple[str, ...] = EXPECTED_POLICY_FILENAMES,
) -> Path:
    candidates = policy_root_candidates(repo_root, explicit=explicit)
    if not candidates:
        return _normalize_policy_root(explicit or repo_root)

    best = candidates[0]
    best_score = _policy_score(best, expected_files=expected_files)
    for candidate in candidates[1:]:
        score = _policy_score(candidate, expected_files=expected_files)
        if score[0] > best_score[0]:
            best = candidate
            best_score = score
    return best
