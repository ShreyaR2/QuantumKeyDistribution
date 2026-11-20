"""
Physical layer: photon sources, polarisation qubits, fibre, detectors, and Eve.

Qubits are linear-polarisation states  |θ⟩ = cos θ |0⟩ + sin θ |1⟩.
The four BB84 states sit at

    Z basis:  bit 0 -> θ = 0      (|0⟩)      bit 1 -> θ = π/2   (|1⟩)
    X basis:  bit 0 -> θ = π/4    (|+⟩)      bit 1 -> θ = 3π/4  (|−⟩)

and a measurement in the basis at angle φ returns outcome 0 with the Born-rule
probability  P(0) = |⟨φ|θ⟩|² = cos²(θ − φ),  collapsing the photon to φ or φ+π/2.
Everything (including Eve's disturbance) falls out of that one rule rather than
being hard-coded as "50% random if the bases differ".

Weak-coherent (laser) sources emit a Poisson number of photons per pulse. That is
the loophole the paper flags in its last paragraph, and what the photon-number-
splitting (PNS) attack here exploits.

The simulator samples by photon-number class, so 10^9 pulses over 100 km of fibre
cost about as much as the few thousand detections they produce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

Z, X = 0, 1
BASIS_ANGLE = np.array([0.0, np.pi / 4])
N_MAX = 30  # photon-number cutoff for Poisson sources


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class Hardware:
    source: str = "single"        # 'single' (ideal single photons) | 'wcp' (attenuated laser)
    mu: float = 0.5               # mean photon number of signal pulses (wcp)
    nu: float = 0.1               # mean photon number of weak decoy pulses (wcp + decoy)
    decoy: bool = False           # interleave decoy + vacuum pulses (Hwang / Lo-Ma-Chen)
    p_signal: float = 0.8         # fraction of pulses that are signal (rest split decoy/vacuum)
    distance_km: float = 0.0
    alpha_db_per_km: float = 0.21  # fibre attenuation
    eta_bob: float = 1.0          # Bob's detector efficiency x internal loss
    dark_count: float = 0.0       # Y0: background click probability per pulse
    misalignment: float = 0.02    # e_d: probability a photon hits the wrong detector

    @property
    def transmittance(self) -> float:
        """Total single-photon transmittance η = 10^(−αL/10) · η_Bob."""
        return 10 ** (-self.alpha_db_per_km * self.distance_km / 10) * self.eta_bob

    def classes(self) -> list[tuple[str, float, float]]:
        """(name, intensity, probability) for each pulse class."""
        if self.source == "single":
            return [("signal", 1.0, 1.0)]
        if not self.decoy:
            return [("signal", self.mu, 1.0)]
        rest = (1 - self.p_signal) / 2
        return [("signal", self.mu, self.p_signal), ("decoy", self.nu, rest), ("vacuum", 0.0, rest)]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transmittance"] = self.transmittance
        return d


HARDWARE_PRESETS = {
    # Ideal single-photon source on a short, lossless link (the textbook setting of the paper)
    "lab": Hardware(source="single", distance_km=0.0, eta_bob=1.0, dark_count=0.0, misalignment=0.02),
    # Gobby, Yuan & Shields, APL 84, 3762 (2004) — the parameter set used by Lo, Ma & Chen (PRL 2005)
    "gys": Hardware(source="wcp", mu=0.48, nu=0.05, decoy=True, p_signal=0.8, distance_km=50.0,
                    alpha_db_per_km=0.21, eta_bob=0.045, dark_count=1.7e-6, misalignment=0.033),
}


@dataclass
class Attack:
    kind: str = "none"            # 'none' | 'intercept_resend' | 'pns'
    fraction: float = 1.0         # intercept-resend: fraction of pulses Eve measures
    basis: str = "random"         # intercept-resend: 'random' (Z/X) or 'Z' (always Z)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Born rule ──────────────────────────────────────────────────────────────────

def state_angle(basis: np.ndarray, bit: np.ndarray) -> np.ndarray:
    return BASIS_ANGLE[basis] + bit * (np.pi / 2)


def measure(theta: np.ndarray, basis: np.ndarray, rng: np.random.Generator):
    """Projective measurement of |θ⟩ in `basis`. Returns (outcome bits, post-measurement angle)."""
    phi = BASIS_ANGLE[basis]
    p0 = np.cos(theta - phi) ** 2
    out = (rng.random(theta.shape[0]) >= p0).astype(np.int8)
    return out, phi + out * (np.pi / 2)


# ── Events ─────────────────────────────────────────────────────────────────────

@dataclass
class ChannelRecord:
    """Per-detection arrays (one entry per Bob click) plus per-class aggregate counts."""
    cls: np.ndarray            # pulse class index into `class_names`
    n_photons: np.ndarray      # photons Alice emitted in that pulse
    a_basis: np.ndarray
    a_bit: np.ndarray
    b_basis: np.ndarray
    b_bit: np.ndarray
    eve_touched: np.ndarray    # Eve interacted with this pulse
    eve_basis: np.ndarray      # -1 = Eve did not measure
    eve_bit: np.ndarray        # -1 = Eve has no result
    eve_knows: np.ndarray      # Eve knows Alice's bit with certainty (after basis announcement)
    dark: np.ndarray           # click came from a dark count, not a signal photon
    class_names: list[str]
    intensities: list[float]
    sent: list[int]            # pulses sent per class
    detected: list[int]        # clicks per class
    eve_info: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.a_bit.shape[0])


def _photon_pmf(source: str, intensity: float) -> np.ndarray:
    pmf = np.zeros(N_MAX + 1)
    if source == "single":
        pmf[1 if intensity > 0 else 0] = 1.0
        return pmf
    if intensity <= 0:
        pmf[0] = 1.0
        return pmf
    n = np.arange(N_MAX + 1)
    pmf = np.exp(-intensity + n * math.log(intensity) - np.array([math.lgamma(k + 1) for k in n]))
    pmf[-1] += max(0.0, 1.0 - pmf.sum())
    return pmf / pmf.sum()


def pns_strategy(hw: Hardware) -> dict:
    """
    Photon-number-splitting attack (Brassard, Lütkenhaus, Mor & Sanders 2000).

    Eve sits at Alice's door with a quantum non-demolition photon counter and a
    lossless fibre. For pulses with n ≥ 2 photons she keeps one photon in memory and
    forwards the other n−1 to Bob losslessly; once the bases are announced she
    measures her copy and knows the bit perfectly, while causing *zero* errors.
    Single-photon pulses she mostly blocks. She tunes the blocking so Bob sees exactly
    the click rate he expects from an honest fibre of this length, so the signal gain
    and the QBER both look perfect.
    """
    mu = hw.mu if hw.source == "wcp" else 1.0
    pmf = _photon_pmf(hw.source, mu)
    eta, eta_b = hw.transmittance, hw.eta_bob
    n = np.arange(N_MAX + 1)
    honest_gain = float(np.sum(pmf * (1 - (1 - eta) ** n)))
    multi_gain = float(np.sum(pmf[2:] * (1 - (1 - eta_b) ** (n[2:] - 1))))
    single_gain = float(pmf[1] * eta_b)
    if multi_gain >= honest_gain:
        s, t_m = 0.0, honest_gain / multi_gain if multi_gain > 0 else 0.0
    else:
        t_m = 1.0
        s = min(1.0, (honest_gain - multi_gain) / single_gain) if single_gain > 0 else 0.0
    return {"forward_single": s, "forward_multi": t_m,
            "honest_signal_gain": honest_gain, "eve_signal_gain": t_m * multi_gain + s * single_gain,
            "fully_hidden": bool(s == 0.0)}


def simulate_channel(n_pulses: int, hw: Hardware, attack: Attack, rng: np.random.Generator) -> ChannelRecord:
    classes = hw.classes()
    names = [c[0] for c in classes]
    intens = [c[1] for c in classes]
    sent = rng.multinomial(n_pulses, [c[2] for c in classes])
    eta, eta_b, y0 = hw.transmittance, hw.eta_bob, hw.dark_count
    delta = math.asin(math.sqrt(min(max(hw.misalignment, 0.0), 1.0)))
    pns = pns_strategy(hw) if attack.kind == "pns" else None

    chunks: list[dict] = []
    detected = [0] * len(classes)

    def emit(ci: int, n_ph: int, count: int, p_sig: float, mode: str):
        """Sample clicks for `count` identical pulses; mode in {'honest','ir','pns_multi','pns_single'}."""
        if count <= 0:
            return
        k_sig = int(rng.binomial(count, min(max(p_sig, 0.0), 1.0)))
        k_dark = int(rng.binomial(count - k_sig, y0)) if y0 > 0 else 0
        k = k_sig + k_dark
        if k == 0:
            return
        detected[ci] += k
        a_basis = rng.integers(0, 2, k).astype(np.int8)
        a_bit = rng.integers(0, 2, k).astype(np.int8)
        theta = state_angle(a_basis, a_bit)
        eve_basis = np.full(k, -1, np.int8)
        eve_bit = np.full(k, -1, np.int8)
        eve_knows = np.zeros(k, bool)
        touched = np.zeros(k, bool)

        if mode == "ir" and n_ph >= 1:
            touched[:] = True
            eve_basis = (np.zeros(k, np.int8) if attack.basis == "Z" else rng.integers(0, 2, k).astype(np.int8))
            eve_bit, theta = measure(theta, eve_basis, rng)
            eve_knows = eve_basis == a_basis
        elif mode == "pns_multi":
            touched[:] = True
            eve_basis, eve_bit, eve_knows = a_basis.copy(), a_bit.copy(), np.ones(k, bool)
        elif mode == "pns_single":
            touched[:] = True

        b_basis = rng.integers(0, 2, k).astype(np.int8)
        sign = np.where(rng.random(k) < 0.5, -1.0, 1.0)
        b_bit, _ = measure(theta + sign * delta, b_basis, rng)
        is_dark = np.zeros(k, bool)
        is_dark[k_sig:] = True
        b_bit[is_dark] = rng.integers(0, 2, k_dark).astype(np.int8)

        chunks.append(dict(cls=np.full(k, ci, np.int8), n_photons=np.full(k, n_ph, np.int16),
                           a_basis=a_basis, a_bit=a_bit, b_basis=b_basis, b_bit=b_bit,
                           eve_touched=touched, eve_basis=eve_basis, eve_bit=eve_bit,
                           eve_knows=eve_knows, dark=is_dark))

    for ci, (name, intensity, _) in enumerate(classes):
        pmf = _photon_pmf(hw.source, intensity)
        counts = rng.multinomial(int(sent[ci]), pmf)
        for n_ph, count in enumerate(counts):
            if count == 0:
                continue
            honest_p = 1 - (1 - eta) ** n_ph
            if attack.kind == "intercept_resend" and n_ph >= 1:
                n_int = int(rng.binomial(count, min(max(attack.fraction, 0.0), 1.0)))
                emit(ci, n_ph, n_int, eta, "ir")              # Eve resends one photon in her state
                emit(ci, n_ph, count - n_int, honest_p, "honest")
            elif attack.kind == "pns" and n_ph >= 2:
                emit(ci, n_ph, count, pns["forward_multi"] * (1 - (1 - eta_b) ** (n_ph - 1)), "pns_multi")
            elif attack.kind == "pns" and n_ph == 1:
                emit(ci, n_ph, count, pns["forward_single"] * eta_b, "pns_single")
            else:
                emit(ci, n_ph, count, honest_p, "honest")

    keys = ["cls", "n_photons", "a_basis", "a_bit", "b_basis", "b_bit", "eve_touched",
            "eve_basis", "eve_bit", "eve_knows", "dark"]
    if chunks:
        arrs = {key: np.concatenate([c[key] for c in chunks]) for key in keys}
        order = rng.permutation(arrs["cls"].shape[0])   # restore time ordering
        arrs = {key: v[order] for key, v in arrs.items()}
    else:
        dtypes = dict(cls=np.int8, n_photons=np.int16, eve_touched=bool, eve_knows=bool, dark=bool)
        arrs = {key: np.zeros(0, dtypes.get(key, np.int8)) for key in keys}

    return ChannelRecord(**arrs, class_names=names, intensities=intens,
                         sent=[int(s) for s in sent], detected=detected,
                         eve_info=pns or {})
