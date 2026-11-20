"""
Analytic (asymptotic) key-rate formulas, used for the theory curves in the dashboard
and as reference values the Monte-Carlo results are checked against.
"""

from __future__ import annotations

import math

import numpy as np

from .infotheory import h2
from .estimation import decoy_bounds


# ── Rate vs QBER ──────────────────────────────────────────────────────────────

def shor_preskill_rate(e, f: float = 1.0):
    """Key bits per sifted bit: 1 − f·H(e) − H(e). With f = 1 this is the paper's 1 − 2H(e)."""
    e = np.asarray(e, float)
    return np.maximum(0.0, 1 - f * h2(e) - h2(e))


def optimal_individual_attack_rate(e):
    """Csiszár–Körner rate against the optimal individual (phase-covariant cloning) attack:
       1 − H(e) − I_E,  I_E = 1 − H(½ + √(e(1−e)))   (Fuchs et al. 1997)."""
    e = np.asarray(e, float)
    ie = 1 - h2(0.5 + np.sqrt(e * (1 - e)))
    return np.maximum(0.0, 1 - h2(e) - ie)


def intercept_resend_rate(e):
    """Against plain intercept-resend, Eve learns 2e of each sifted bit (QBER e = f/4, info f/2)."""
    e = np.asarray(e, float)
    return np.maximum(0.0, 1 - h2(e) - np.minimum(1, 2 * e))


def threshold(rate_fn, lo: float = 1e-4, hi: float = 0.5) -> float:
    for _ in range(80):
        mid = (lo + hi) / 2
        if float(rate_fn(mid)) > 0:
            lo = mid
        else:
            hi = mid
    return lo


# ── Rate vs distance (GLLP / decoy) ───────────────────────────────────────────

def channel_stats(mu: float, eta: float, Y0: float, e_d: float, e0: float = 0.5):
    Q = Y0 + 1 - math.exp(-eta * mu)
    E = (e0 * Y0 + e_d * (1 - math.exp(-eta * mu))) / Q if Q > 0 else 0.5
    return Q, E


def rate_single_photon(eta: float, Y0: float, e_d: float, f: float, q: float = 0.5) -> float:
    Y1 = Y0 + eta - Y0 * eta
    e1 = (0.5 * Y0 + e_d * eta) / Y1
    return max(0.0, q * Y1 * (1 - f * h2(e1) - h2(e1)))


def rate_gllp_no_decoy(mu: float, eta: float, Y0: float, e_d: float, f: float, q: float = 0.5) -> float:
    Q, E = channel_stats(mu, eta, Y0, e_d)
    delta = (1 - math.exp(-mu) * (1 + mu)) / Q
    if delta >= 1:
        return 0.0
    return max(0.0, q * Q * ((1 - delta) * (1 - h2(min(0.5, E / (1 - delta)))) - f * h2(E)))


def rate_decoy_infinite(mu: float, eta: float, Y0: float, e_d: float, f: float, q: float = 0.5) -> float:
    Q, E = channel_stats(mu, eta, Y0, e_d)
    Y1 = Y0 + eta - Y0 * eta
    e1 = (0.5 * Y0 + e_d * eta) / Y1
    Q1 = Y1 * mu * math.exp(-mu)
    return max(0.0, q * (Q1 * (1 - h2(e1)) - Q * f * h2(E)))


def rate_decoy_practical(mu: float, nu: float, eta: float, Y0: float, e_d: float, f: float, q: float = 0.5) -> float:
    Q_mu, E_mu = channel_stats(mu, eta, Y0, e_d)
    Q_nu, E_nu = channel_stats(nu, eta, Y0, e_d)
    b = decoy_bounds(mu, nu, Q_mu, Q_nu, E_mu, E_nu, Y0)
    return max(0.0, q * (b["Q1_L"] * (1 - h2(b["e1_U"])) - Q_mu * f * h2(E_mu)))


MU_GRID = np.logspace(-4, 0.2, 140)


def distance_curves(hw, f: float = 1.16, distances=None) -> dict:
    """Key rate (bits per pulse) vs distance for the four standard analyses."""
    if distances is None:
        distances = np.arange(0, 181, 2.0)
    out = {"distance_km": [float(d) for d in distances], "single_photon": [], "gllp_no_decoy": [],
           "decoy_infinite": [], "decoy_practical": [], "opt_mu_no_decoy": [], "opt_mu_decoy": []}
    for L in distances:
        eta = 10 ** (-hw.alpha_db_per_km * L / 10) * hw.eta_bob
        a = (hw.dark_count, hw.misalignment, f)
        out["single_photon"].append(rate_single_photon(eta, *a))
        r_nd = [rate_gllp_no_decoy(m, eta, *a) for m in MU_GRID]
        r_di = [rate_decoy_infinite(m, eta, *a) for m in MU_GRID]
        out["gllp_no_decoy"].append(max(r_nd))
        out["opt_mu_no_decoy"].append(float(MU_GRID[int(np.argmax(r_nd))]))
        out["decoy_infinite"].append(max(r_di))
        out["opt_mu_decoy"].append(float(MU_GRID[int(np.argmax(r_di))]))
        out["decoy_practical"].append(rate_decoy_practical(hw.mu, hw.nu, eta, *a))
    for k in ("single_photon", "gllp_no_decoy", "decoy_infinite", "decoy_practical"):
        rates = out[k]
        pos = [d for d, r in zip(out["distance_km"], rates) if r > 0]
        out[f"max_distance_{k}"] = max(pos) if pos else 0.0
    return out


def pns_hidden_distance(hw) -> float:
    """Shortest distance at which a PNS attacker can hide completely (block every single photon)."""
    from .physics import pns_strategy
    import copy
    h = copy.copy(hw)
    for L in np.arange(0, 300, 0.5):
        h.distance_km = float(L)
        if pns_strategy(h)["fully_hidden"]:
            return float(L)
    return float("inf")
