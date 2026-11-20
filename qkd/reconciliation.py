"""
Error correction = the classical code C1 of the CSS construction.

In Protocol 3 Alice announces u + v (v = her key bits, u a random codeword of C1)
and Bob "corrects the result to a codeword in C1". Announcing u + v for a random
u ∈ C1 reveals exactly the coset of v, i.e. its syndrome H1·v. So the practical
form of step 8–9 is syndrome decoding:

    Alice  ── s_A = H·x_A ──►  Bob
    Bob finds the most likely error e with  H·e = s_A ⊕ H·x_B,  sets x_B ⊕ e.

C1 here is a random low-density parity-check (LDPC) code decoded by belief
propagation (sum-product), the standard choice in deployed QKD systems. Its
size is set from the estimated QBER, and if decoding fails Alice sends more parity
checks (rate-adaptive reconciliation). Every bit sent is counted as leakage, which
privacy amplification later subtracts.

Reconciliation efficiency  f = leak / (n · H(QBER))  ≥ 1. The Shannon limit is f = 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .infotheory import h2
from .privacy import toeplitz_hash_matrix, gf2_matvec


@dataclass
class LDPCCode:
    n: int
    m: int
    var_idx: np.ndarray  # edge -> variable
    chk_idx: np.ndarray  # edge -> check

    def dense(self) -> np.ndarray:
        H = np.zeros((self.m, self.n), np.uint8)
        H[self.chk_idx, self.var_idx] ^= 1
        return H

    def syndrome(self, x: np.ndarray) -> np.ndarray:
        return (np.bincount(self.chk_idx, weights=x[self.var_idx], minlength=self.m) % 2).astype(np.uint8)


def _random_edges(n: int, m: int, col_weight: int, rng: np.random.Generator, chk_offset: int = 0):
    var = np.repeat(np.arange(n), col_weight)
    chk = rng.permutation(np.arange(var.size) % m) + chk_offset
    key = np.unique(var.astype(np.int64) * (m + chk_offset + 1) + chk)  # drop double edges
    return (key // (m + chk_offset + 1)).astype(np.int64), (key % (m + chk_offset + 1)).astype(np.int64)


def make_ldpc(n: int, m: int, rng: np.random.Generator, col_weight: int = 3) -> LDPCCode:
    m = max(1, min(m, n))
    v, c = _random_edges(n, m, col_weight, rng)
    return LDPCCode(n, m, v, c)


def extend_ldpc(code: LDPCCode, extra: int, rng: np.random.Generator) -> LDPCCode:
    """Append `extra` new parity checks with the code's average row weight."""
    extra = max(1, min(extra, code.n - code.m))
    w = max(4, int(round(code.var_idx.size / code.m)))
    v = rng.integers(0, code.n, extra * w)
    c = np.repeat(np.arange(extra), w) + code.m
    key = np.unique(c.astype(np.int64) * code.n + v)
    v, c = key % code.n, key // code.n
    return LDPCCode(code.n, code.m + extra,
                    np.concatenate([code.var_idx, v]), np.concatenate([code.chk_idx, c]))


def bp_decode(code: LDPCCode, target_syndrome: np.ndarray, p: float, max_iter: int = 80):
    """
    Sum-product belief propagation for the error pattern e with H·e = target.
    Returns (e_hat, success, unsatisfied-checks-per-iteration).
    """
    p = min(max(p, 1e-6), 0.499)
    prior = math.log((1 - p) / p)
    v, c = code.var_idx, code.chk_idx
    n, m = code.n, code.m
    syn_sign = 1.0 - 2.0 * target_syndrome[c].astype(float)  # (-1)^s per edge
    msg_cv = np.zeros(v.size)
    history = []
    e_hat = np.zeros(n, np.uint8)
    for _ in range(max_iter):
        total = prior + np.bincount(v, weights=msg_cv, minlength=n)
        e_hat = (total < 0).astype(np.uint8)
        unsat = int(np.count_nonzero(code.syndrome(e_hat) != target_syndrome))
        history.append(unsat)
        if unsat == 0:
            return e_hat, True, history
        msg_vc = total[v] - msg_cv
        t = np.tanh(np.clip(msg_vc, -40, 40) / 2)
        a = np.clip(np.abs(t), 1e-15, 1.0)
        log_a = np.log(a)
        neg = (t < 0).astype(float)
        sum_log = np.bincount(c, weights=log_a, minlength=m)
        sum_neg = np.bincount(c, weights=neg, minlength=m)
        mag = np.exp(sum_log[c] - log_a)
        sgn = 1.0 - 2.0 * ((sum_neg[c] - neg) % 2)
        prod = np.clip(sgn * mag * syn_sign, -1 + 1e-12, 1 - 1e-12)
        msg_cv = 2 * np.arctanh(prod)
    return e_hat, False, history


@dataclass
class ReconciliationResult:
    success: bool
    bob_corrected: np.ndarray
    leak_bits: int              # syndrome bits sent publicly
    tag_bits: int               # verification-hash bits sent publicly
    code: LDPCCode
    verify_matrix: np.ndarray
    rounds: list = field(default_factory=list)   # [{m, iterations, success, history}]
    errors_before: int = 0
    errors_after: int = 0
    qber_used: float = 0.0

    @property
    def efficiency(self) -> float | None:
        n = self.code.n
        hq = h2(max(self.errors_before / n, 1e-9)) if n else 0
        return (self.leak_bits / (n * hq)) if n and hq > 1e-6 else None


def reconcile(x_alice: np.ndarray, x_bob: np.ndarray, qber_est: float, rng: np.random.Generator,
              f_start: float = 1.2, max_rounds: int = 12, tag_bits: int = 32) -> ReconciliationResult:
    n = int(x_alice.size)
    errors_before = int(np.count_nonzero(x_alice != x_bob))
    p = min(max(qber_est, 1.0 / max(n, 1), 0.002), 0.2)
    m0 = max(16, int(math.ceil(f_start * n * h2(p))))
    code = make_ldpc(n, m0, rng)
    V = toeplitz_hash_matrix(n, tag_bits, rng)
    rounds = []
    x_hat = x_bob.copy()
    success = False
    for _ in range(max_rounds):
        s_a = code.syndrome(x_alice)                       # Alice -> Bob (public)
        target = s_a ^ code.syndrome(x_bob)
        e_hat, ok, hist = bp_decode(code, target, p)
        x_hat = x_bob ^ e_hat
        # Verification: compare a 2-universal hash (catches a wrong codeword)
        ok = ok and np.array_equal(gf2_matvec(V, x_alice), gf2_matvec(V, x_hat))
        rounds.append({"m": code.m, "iterations": len(hist), "success": bool(ok), "history": hist})
        if ok:
            success = True
            break
        if code.m >= n:
            break
        code = extend_ldpc(code, max(16, int(0.08 * m0)), rng)  # send more parity
    return ReconciliationResult(
        success=success, bob_corrected=x_hat, leak_bits=code.m, tag_bits=tag_bits, code=code,
        verify_matrix=V, rounds=rounds, errors_before=errors_before,
        errors_after=int(np.count_nonzero(x_alice != x_hat)), qber_used=p)
