"""Small information-theory helpers."""

import numpy as np


def h2(p):
    """Binary Shannon entropy H(p) = -p log2 p - (1-p) log2(1-p). Works on scalars and arrays."""
    p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = -p * np.log2(p) - (1 - p) * np.log2(1 - p)
    out = np.nan_to_num(out, nan=0.0)
    return float(out) if out.ndim == 0 else out
