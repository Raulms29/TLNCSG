"""Statistical tests and math for the Metrics Module."""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np
from scipy import stats


def calc_pass_at_k(n: int, c: int, k: int) -> float:
    """Calculate Pass@k: probability of at least one correct solution in k attempts."""
    if n - c < k:
        return 1.0
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k))


def calc_pass_power_k(n: int, c: int, k: int) -> float:
    """Calculate Pass^k: probability of all k attempts being correct."""
    if n == 0:
        return 0.0
    return (c / n) ** k


def calculate_mcnemar(y1: Sequence[int], y2: Sequence[int]) -> tuple[float, float]:
    """Calculate McNemar's test for paired nominal data (e.g. binary Pass@30).
    y1 and y2 must be sequences of 0s and 1s.
    Returns (chi2_statistic, p_value).
    """
    assert len(y1) == len(y2)
    b = 0  # y1 = 0, y2 = 1
    c = 0  # y1 = 1, y2 = 0
    for val1, val2 in zip(y1, y2):
        if val1 == 0 and val2 == 1:
            b += 1
        elif val1 == 1 and val2 == 0:
            c += 1

    if b + c == 0:
        return 0.0, 1.0

    chi2 = ((abs(b - c) - 1.0) ** 2) / (b + c)
    p_value = stats.chi2.sf(chi2, 1)
    return float(chi2), float(p_value)


def calculate_wilcoxon(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """Calculate Wilcoxon signed-rank test for paired continuous data.
    Returns (statistic, p_value).
    """
    diff = np.array(x) - np.array(y)
    # If differences are all zero, p-value is 1.0
    if np.all(diff == 0):
        return 0.0, 1.0

    try:
        res = stats.wilcoxon(x, y)
        return float(getattr(res, "statistic")), float(getattr(res, "pvalue"))
    except ValueError:
        return 0.0, 1.0
