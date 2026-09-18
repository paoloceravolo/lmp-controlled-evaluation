from __future__ import annotations

import math
from collections.abc import Iterable

from scipy.special import zeta


Trace = tuple[str, ...]


def lambda_from_median_length(median_length: float) -> float:
    if median_length < 0:
        raise ValueError("median_length must be non-negative")
    return 2.0 ** (-1.0 / (median_length + 1.0))


def power_law_length_cdf(k: int, alpha: float) -> float:
    if alpha <= 1.0:
        raise ValueError("alpha must be greater than 1")
    if k < 0:
        return 0.0
    return sum((n + 1) ** (-alpha) for n in range(k + 1)) / float(zeta(alpha, 1.0))


def alpha_from_median_length(median_length: float) -> float:
    if median_length < 0:
        raise ValueError("median_length must be non-negative")
    k = int(round(median_length))
    low, high = 1.000001, 100.0
    for _ in range(120):
        mid = 0.5 * (low + high)
        if power_law_length_cdf(k, mid) < 0.5:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def trace_mass(trace: Trace, alphabet_size: int, prior: str, parameter: float) -> float:
    if alphabet_size <= 0:
        raise ValueError("alphabet_size must be positive")
    length = len(trace)
    if prior == "geometric":
        if not 0.0 < parameter < 1.0:
            raise ValueError("geometric lambda must be in (0, 1)")
        return (1.0 - parameter) * parameter**length / alphabet_size**length
    if prior == "power_law":
        if parameter <= 1.0:
            raise ValueError("power-law alpha must be greater than 1")
        return (length + 1) ** (-parameter) / (float(zeta(parameter, 1.0)) * alphabet_size**length)
    raise ValueError(f"Unknown prior: {prior}")


def trace_log_mass(trace: Trace, alphabet_size: int, prior: str, parameter: float) -> float:
    """Natural-log trace mass, stable for long traces where `trace_mass` underflows."""
    if alphabet_size <= 0:
        raise ValueError("alphabet_size must be positive")
    length = len(trace)
    if prior == "geometric":
        if not 0.0 < parameter < 1.0:
            raise ValueError("geometric lambda must be in (0, 1)")
        return math.log1p(-parameter) + length * (math.log(parameter) - math.log(alphabet_size))
    if prior == "power_law":
        if parameter <= 1.0:
            raise ValueError("power-law alpha must be greater than 1")
        return (
            -parameter * math.log(length + 1)
            - math.log(float(zeta(parameter, 1.0)))
            - length * math.log(alphabet_size)
        )
    raise ValueError(f"Unknown prior: {prior}")


def language_mass(traces: Iterable[Trace], alphabet_size: int, prior: str, parameter: float) -> float:
    return math.fsum(trace_mass(trace, alphabet_size, prior, parameter) for trace in traces)


def length_tail_mass(k: int, prior: str, parameter: float) -> float:
    """Return total trace-space mass at lengths strictly greater than k."""
    if k < 0:
        return 1.0
    if prior == "geometric":
        if not 0.0 < parameter < 1.0:
            raise ValueError("geometric lambda must be in (0, 1)")
        return parameter ** (k + 1)
    if prior == "power_law":
        if parameter <= 1.0:
            raise ValueError("power-law alpha must be greater than 1")
        return float(zeta(parameter, k + 2) / zeta(parameter, 1.0))
    raise ValueError(f"Unknown prior: {prior}")


def horizon_grid(median_length: float, factors: Iterable[float] = (0.5, 0.75, 1.0, 1.5, 2.0)) -> list[float]:
    """Section 7 RQ2 relative-horizon grid: target median lengths h = factor * m."""
    if median_length < 0:
        raise ValueError("median_length must be non-negative")
    return [factor * median_length for factor in factors]
