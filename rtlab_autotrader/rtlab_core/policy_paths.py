from __future__ import annotations

import os
from pathlib import Path


EXPECTED_POLICY_FILENAMES: tuple[str, ...] = (
    "gates.yaml",
    "microstructure.yaml",
    "risk_policy.yaml",
    "beast_mode.yaml",
    "fees.yaml",
    "fundamentals_credit_filter.yaml",
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
