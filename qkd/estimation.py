"""
Parameter estimation: what Alice and Bob may conclude from the check bits.

Two ideas from Shor–Preskill drive this module.

1. Bit errors and phase errors are different, and both must be bounded.
   On the Bell basis, the check-bit identities in the paper

       |Ψ+⟩⟨Ψ+| + |Ψ−⟩⟨Ψ−| = |01⟩⟨01| + |10⟩⟨10|      (bit flips  -> seen in Z)
       |Φ−⟩⟨Φ−| + |Ψ−⟩⟨Ψ−| = |+−⟩⟨+−| + |−+⟩⟨−+|      (phase flips -> seen in X)

   mean the *phase* error rate on key bits encoded in Z is measured by the error
   rate of X-basis check bits, and vice versa. Phase errors are what leak
   information to Eve, so they set how much privacy amplification is needed.

2. Check bits are a random sample. Eve doesn't know which qubits will be checks,
   so the paper's classical sampling bound applies:

       Pr[ code errors > δn  and  check errors < (δ − ε)n ]  <  exp(−ε² n / (4(δ − δ²)))

   We invert it to get an upper confidence bound on the true error rate.

For weak-coherent sources (which the paper does not cover) the decoy-state method
of Hwang (2003) and Lo–Ma–Chen (2005) bounds the single-photon yield Y1 and
error rate e1, using the practical vacuum + weak-decoy formulas of Ma, Qi, Zhao
and Lo, PRA 72, 012326 (2005).
"""

from __future__ import annotations

import math


def paper_confidence_gap(observed: float, n_check: int, eps: float = 1e-10) -> float:
    """Smallest ε with exp(−ε² n / (4 δ(1−δ))) ≤ eps, δ = observed + ε (fixed-point iteration)."""
    if n_check <= 0:
        return 0.5
    gap = 0.0
    for _ in range(50):
        d = min(max(observed + gap, 1e-4), 0.5)
        new = math.sqrt(4 * d * (1 - d) * math.log(1 / eps) / n_check)
        if abs(new - gap) < 1e-12:
            break
        gap = new
    return gap


def decoy_bounds(mu: float, nu: float, Q_mu: float, Q_nu: float, E_mu: float, E_nu: float,
                 Y0: float, e0: float = 0.5) -> dict:
    """Vacuum + weak decoy lower bound on Y1 and upper bound on e1 (Ma et al. 2005, eqs. 34 & 37)."""
    if not (0 < nu < mu) or Q_mu <= 0 or Q_nu <= 0:
        return {"Y1_L": 0.0, "e1_U": 0.5, "Q1_L": 0.0, "single_photon_fraction": 0.0, "valid": False}
    Y1_L = (mu / (mu * nu - nu ** 2)) * (Q_nu * math.exp(nu) - Q_mu * math.exp(mu) * nu ** 2 / mu ** 2
                                          - (mu ** 2 - nu ** 2) / mu ** 2 * Y0)
    Y1_L = max(Y1_L, 0.0)
    e1_U = min(0.5, (E_nu * Q_nu * math.exp(nu) - e0 * Y0) / (Y1_L * nu)) if Y1_L > 0 else 0.5
    e1_U = max(e1_U, 0.0)
    Q1_L = Y1_L * mu * math.exp(-mu)
    return {"Y1_L": Y1_L, "e1_U": e1_U, "Q1_L": Q1_L,
            "single_photon_fraction": min(1.0, Q1_L / Q_mu), "valid": Y1_L > 0}

