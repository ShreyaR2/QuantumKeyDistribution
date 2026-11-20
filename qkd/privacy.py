"""
Privacy amplification = the code C2 of the CSS construction.

In Protocol 3 the final key is "the coset of u + C2", i.e. the image of the
reconciled string under a linear map whose kernel is C2. A random linear map with
that property is a 2-universal hash, and the standard efficient choice is a random
binary Toeplitz matrix T (n_out × n_in), defined by n_in + n_out − 1 public seed bits.

How much to compress (the size of C2) is the main quantitative result of the
paper: per key bit you must give up H(e_phase) for phase errors (Eve's possible
information) on top of what error correction disclosed, so

    ℓ  =  n·[1 − H(e_ph^U)]  −  leak_EC  −  tag  −  2·log2(1/ε_PA)

which with an ideal code (leak = n·H(e_bit)) and e_bit = e_ph = δ is n·[1 − 2H(δ)],
the Shor–Preskill rate. It hits zero at δ ≈ 11.0%.

The paper's comment, "it is better to only require that random errors are corrected
with high probability", is why the rate uses H(δ) and not the Gilbert–Varshamov
H(2δ).
"""

from __future__ import annotations

import math

import numpy as np


def toeplitz_hash_matrix(n_in: int, n_out: int, rng: np.random.Generator) -> np.ndarray:
    """Random binary Toeplitz matrix (n_out × n_in), defined by n_in + n_out − 1 seed bits."""
    if n_out <= 0 or n_in <= 0:
        return np.zeros((max(n_out, 0), max(n_in, 0)), np.uint8)
    seed = rng.integers(0, 2, n_in + n_out - 1).astype(np.uint8)
    i = np.arange(n_out)[:, None]
    j = np.arange(n_in)[None, :]
    return seed[i - j + n_in - 1]


def gf2_matvec(M: np.ndarray, x: np.ndarray) -> np.ndarray:
    if M.shape[0] == 0:
        return np.zeros(0, np.uint8)
    return ((M.astype(np.int32) @ x.astype(np.int32)) % 2).astype(np.uint8)


def pa_security_margin(eps_pa: float) -> int:
    return int(math.ceil(2 * math.log2(1 / eps_pa)))
