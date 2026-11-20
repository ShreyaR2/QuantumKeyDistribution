"""
Linear algebra over GF(2), used to compute *exactly* how much Eve knows.

Every classical post-processing step in the Shor–Preskill protocol is linear over
GF(2): the error-correction syndrome is H·v, the verification tag is V·v, and the
final key is T·v (Toeplitz hashing). If Eve knows the key bits at positions S
exactly and nothing about the rest (U), the remaining key is uniform on an affine
subspace, and her uncertainty about the final key is

    H(K | Eve) = rank([H_U; V_U; T_U]) − rank([H_U; V_U])      bits.

So her information is  I(K; Eve) = len(K) − H(K | Eve),  computed exactly instead
of estimated.
"""

from __future__ import annotations

import numpy as np


def gf2_rank(M: np.ndarray) -> int:
    """Rank over GF(2) of a 0/1 matrix, via bit-packed Gaussian elimination."""
    M = np.asarray(M, dtype=np.uint8)
    if M.size == 0:
        return 0
    rows, cols = M.shape
    packed = np.packbits(M, axis=1)
    pad = (-packed.shape[1]) % 8
    if pad:
        packed = np.concatenate([packed, np.zeros((rows, pad), np.uint8)], axis=1)
    packed = np.ascontiguousarray(packed)
    p8 = packed                       # byte view, for testing one column
    p64 = packed.view(np.uint64)      # word view, for XOR-ing rows
    rank = 0
    for col in range(cols):
        if rank == rows:
            break
        byte, mask = col >> 3, np.uint8(0x80 >> (col & 7))
        hits = np.nonzero(p8[rank:, byte] & mask)[0]
        if hits.size == 0:
            continue
        piv = rank + hits[0]
        if piv != rank:
            p64[[rank, piv]] = p64[[piv, rank]]
        below = rank + 1 + np.nonzero(p8[rank + 1:, byte] & mask)[0]
        if below.size:
            # the pivot row is zero in every column < col, so only later words need XOR-ing
            w0 = col >> 6
            p64[below, w0:] ^= p64[rank, w0:]
        rank += 1
    return rank


def eve_uncertainty(public_rows: np.ndarray, key_rows: np.ndarray, unknown: np.ndarray) -> int:
    """
    Bits of the output (key_rows · v) that remain uniformly random to Eve, given that
    she knows v outside `unknown` and has seen public_rows · v.
    """
    unknown = np.asarray(unknown, dtype=bool)
    if key_rows.shape[0] == 0 or not unknown.any():
        return 0
    pu = public_rows[:, unknown] if public_rows.size else np.zeros((0, int(unknown.sum())), np.uint8)
    ku = key_rows[:, unknown]
    return gf2_rank(np.vstack([pu, ku])) - gf2_rank(pu)
