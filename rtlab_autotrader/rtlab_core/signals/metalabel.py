from __future__ import annotations


def confidence_multiplier(probability: float, floor: float = 0.5, cap: float = 1.5) -> float:
    probability = max(0.0, min(1.0, probability))
    scaled = floor + (cap - floor) * probability
    return max(floor, min(cap, scaled))
