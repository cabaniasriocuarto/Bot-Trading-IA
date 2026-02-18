from __future__ import annotations

from itertools import combinations


def purged_cv_splits(n_samples: int, n_splits: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    if n_splits <= 1:
        raise ValueError("n_splits must be > 1")
    fold_size = n_samples // n_splits
    splits: list[tuple[list[int], list[int]]] = []

    for fold in range(n_splits):
        test_start = fold * fold_size
        test_end = n_samples if fold == n_splits - 1 else (fold + 1) * fold_size
        test_idx = list(range(test_start, test_end))

        train_idx = [i for i in range(n_samples) if i < test_start - embargo or i >= test_end + embargo]
        splits.append((train_idx, test_idx))
    return splits


def cpcv_paths(n_splits: int, n_test_paths: int = 2) -> list[tuple[int, ...]]:
    if n_test_paths >= n_splits:
        raise ValueError("n_test_paths must be < n_splits")
    return list(combinations(range(n_splits), n_test_paths))


def walk_forward_splits(
    n_samples: int,
    train_size: int,
    test_size: int,
    step: int,
) -> list[tuple[list[int], list[int]]]:
    splits: list[tuple[list[int], list[int]]] = []
    start = 0
    while start + train_size + test_size <= n_samples:
        train_idx = list(range(start, start + train_size))
        test_idx = list(range(start + train_size, start + train_size + test_size))
        splits.append((train_idx, test_idx))
        start += step
    return splits


def is_promotable(metrics: dict[str, float], stressed: dict[str, float], oos_positive_segments: int, min_oos_segments: int) -> bool:
    if metrics.get("expectancy", 0.0) <= 0:
        return False
    if metrics.get("max_drawdown", 1.0) > 0.22:
        return False
    if not stressed.get("stress_pass", False):
        return False
    if oos_positive_segments < min_oos_segments:
        return False
    return True
