"""
One full BB84 run, following Protocol 3 of Shor & Preskill step by step.

    run_protocol()
      1. send_and_measure()   Alice sends photons, (Eve interferes), Bob measures     physics.py
      2. sift()               keep matching bases, pick random check bits
      3. estimate_errors()    Z and X error rates + the paper's confidence bound       estimation.py
      4. secret_fraction()    what share of the key can be secret (depends on source)
      5. correct_errors()     LDPC syndrome decoding = the paper's code C1            reconciliation.py
      6. amplify_privacy()    Toeplitz hash to the secure length = code C2            privacy.py
      7. measure_eve()        exact bits of the final key Eve knows                  gf2.py

Every function is short and returns plain values, so you can read it top to bottom
like the protocol itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .physics import Hardware, Attack, simulate_channel, Z, X
from .estimation import paper_confidence_gap, decoy_bounds
from .reconciliation import reconcile
from .privacy import toeplitz_hash_matrix, gf2_matvec, pa_security_margin
from .gf2 import eve_uncertainty, gf2_rank
from .infotheory import h2

EPS = 1e-10            # security parameter: chance the sampling bound / hashing fails
QBER_ABORT = 0.15      # don't even try error correction above this


@dataclass
class ProtocolConfig:
    n_pulses: int = 20000
    hardware: Hardware = field(default_factory=Hardware)
    attack: Attack = field(default_factory=Attack)
    analysis: str = "auto"              # 'single' (Shor–Preskill), 'naive', or 'decoy'
    privacy_amplification: bool = True
    check_fraction: float = 0.5         # paper: n check bits out of 2n
    seed: int | None = None


# ── Step 2: sifting ────────────────────────────────────────────────────────────

def sift(rec, check_fraction, rng):
    """Keep signal pulses where Alice's and Bob's bases matched; a random subset become check bits."""
    sifted = np.nonzero((rec.a_basis == rec.b_basis) & (rec.cls == 0))[0]
    shuffled = rng.permutation(sifted)                  # random, so Eve can't predict the checks
    n_check = int(round(check_fraction * sifted.size))
    return sifted, np.sort(shuffled[:n_check]), np.sort(shuffled[n_check:])


# ── Step 3: error estimation ───────────────────────────────────────────────────

def estimate_errors(rec, check_idx, key_idx):
    """
    Bit errors are measured directly. Phase errors (Eve's information) on Z-key bits
    show up as X-check errors, and vice versa, so we estimate each basis separately,
    then add the paper's finite-sample margin.
    """
    err = rec.a_bit != rec.b_bit
    zc, xc = check_idx[rec.a_basis[check_idx] == Z], check_idx[rec.a_basis[check_idx] == X]
    e_Z = float(err[zc].mean()) if zc.size else 0.0
    e_X = float(err[xc].mean()) if xc.size else 0.0
    gap_Z, gap_X = paper_confidence_gap(e_Z, zc.size, EPS), paper_confidence_gap(e_X, xc.size, EPS)

    n_key = key_idx.size
    n_key_Z = int(np.count_nonzero(rec.a_basis[key_idx] == Z))
    e_phase = ((n_key_Z * min(0.5, e_X + gap_X) + (n_key - n_key_Z) * min(0.5, e_Z + gap_Z)) / n_key
               if n_key else 0.5)
    return {"e_Z": e_Z, "e_X": e_X, "e_bit": float(err[check_idx].mean()) if check_idx.size else 0.0,
            "gap_Z": gap_Z, "gap_X": gap_X, "n_check_Z": int(zc.size), "n_check_X": int(xc.size),
            "e_phase_upper": e_phase}


# ── Step 4: how much of the key can be secret ──────────────────────────────────

def pulse_classes(rec, hw):
    """Click rate (gain) and error rate for each pulse type, next to what an honest fibre would give."""
    sifted, err = rec.a_basis == rec.b_basis, rec.a_bit != rec.b_bit
    out = []
    for ci, name in enumerate(rec.class_names):
        mu = rec.intensities[ci]
        honest = hw.dark_count + (hw.transmittance if hw.source == "single" else 1 - math.exp(-hw.transmittance * mu))
        m = sifted & (rec.cls == ci)
        out.append({"name": name, "mu": mu, "sent": rec.sent[ci], "clicks": rec.detected[ci],
                    "gain": rec.detected[ci] / max(rec.sent[ci], 1), "honest_gain": honest,
                    "qber": float(err[m].mean()) if m.any() else None})
    return out


def secret_fraction(analysis, est, classes, hw):
    """Fraction of key bits that survive privacy amplification (before paying for error correction)."""
    if analysis in ("single", "naive"):
        # Shor–Preskill: give up H(e_phase) per bit. 'naive' wrongly applies this to laser pulses.
        return 1 - h2(est["e_phase_upper"]), None
    # decoy: only clicks from single-photon pulses can be secret
    sig, dec, vac = classes
    b = decoy_bounds(hw.mu, hw.nu, sig["gain"], dec["gain"], est["e_bit"], dec["qber"] or 0.0, vac["gain"])
    b["Y1_honest"] = hw.dark_count + hw.transmittance
    frac = b["single_photon_fraction"] * (1 - h2(b["e1_U"])) if b["valid"] else 0.0
    return frac, b


NOTES = {
    "single": "Shor–Preskill: single photons, so each key bit costs H(phase error) in privacy amplification.",
    "naive": "Naive: laser pulses treated as single photons. This is the assumption the paper warns about.",
    "decoy": "Decoy states: only clicks from single-photon pulses count toward the secret key.",
}


# ── Step 7: Eve's exact knowledge ──────────────────────────────────────────────

def measure_eve(eve_known, public, hash_matrix, pa_on):
    """Bits Eve knows after error correction (direct knowledge + public syndrome) and in the final key."""
    unknown = ~eve_known
    after_ec = int(eve_known.size - (unknown.sum() - gf2_rank(public[:, unknown])))
    if not pa_on:
        return after_ec, after_ec
    return after_ec, int(hash_matrix.shape[0] - eve_uncertainty(public, hash_matrix, unknown))


# ── The whole run ──────────────────────────────────────────────────────────────

def run_protocol(cfg: ProtocolConfig) -> dict:
    rng = np.random.default_rng(cfg.seed)
    hw, attack = cfg.hardware, cfg.attack
    analysis = cfg.analysis
    if analysis == "auto":
        analysis = "single" if hw.source == "single" else ("decoy" if hw.decoy else "naive")

    # 1. send and measure
    rec = simulate_channel(int(cfg.n_pulses), hw, attack, rng)
    # 2. sift
    sifted, check_idx, key_idx = sift(rec, cfg.check_fraction, rng)
    # 3. estimate errors
    est = estimate_errors(rec, check_idx, key_idx)
    # 4. secret fraction
    classes = pulse_classes(rec, hw)
    frac, decoy = secret_fraction(analysis, est, classes, hw)

    n_key = int(key_idx.size)
    x_alice = rec.a_bit[key_idx].astype(np.uint8)
    x_bob = rec.b_bit[key_idx].astype(np.uint8)
    eve_known = rec.eve_knows[key_idx]
    secret_bits = n_key * max(frac, 0.0)
    margin = pa_security_margin(EPS)

    # Abort before error correction if there is clearly no key to be had
    abort = None
    if est["e_bit"] > QBER_ABORT:
        abort = f"QBER {est['e_bit']:.1%} is far above the 11% threshold, so an eavesdropper is detected."
    elif cfg.privacy_amplification and decoy and decoy["single_photon_fraction"] < 0.05:
        abort = ("Decoy check failed: the click rates of signal, decoy and vacuum pulses don't fit an honest "
                 "fibre, which is the signature of a photon-number-splitting attack.")
    elif cfg.privacy_amplification and secret_bits - 1.2 * n_key * h2(est["e_bit"]) - margin <= 0:
        abort = (f"Too much possible leakage (QBER {est['e_bit']:.1%}, phase-error bound "
                 f"{est['e_phase_upper']:.1%}): nothing would be left after privacy amplification.")

    # 5. error correction
    ec = None
    if abort is None:
        ec = reconcile(x_alice, x_bob, est["e_bit"], rng)
        if not ec.success:
            abort = "Error correction did not converge."

    # 6. privacy amplification
    keys = privacy = None
    eve_after_ec = eve_final = None
    if abort is None:
        leak = ec.leak_bits + ec.tag_bits
        length = int(secret_bits - leak - margin) if cfg.privacy_amplification else n_key
        if length <= 0:
            abort = "After paying for error correction, no secret bits remain."
        else:
            T = toeplitz_hash_matrix(n_key, length, rng) if cfg.privacy_amplification else np.eye(n_key, dtype=np.uint8)
            k_alice, k_bob = gf2_matvec(T, x_alice), gf2_matvec(T, ec.bob_corrected)
            keys = {"length": length, "alice_hex": _hex(k_alice), "bob_hex": _hex(k_bob),
                    "match": bool(np.array_equal(k_alice, k_bob))}
            privacy = {"n_key": n_key, "phase_cost": round(n_key - secret_bits) if cfg.privacy_amplification else 0,
                       "ec_leak": ec.leak_bits,
                       "tag_and_margin": ec.tag_bits + margin if cfg.privacy_amplification else 0, "final": length}
            # 7. Eve's exact knowledge
            public = np.vstack([ec.code.dense(), ec.verify_matrix])
            eve_after_ec, eve_final = measure_eve(eve_known, public, T, cfg.privacy_amplification)

    if abort:
        verdict = "aborted"
    elif eve_final:
        verdict = "compromised"
    else:
        verdict = "secure"

    return {
        "config": {"n_pulses": int(cfg.n_pulses), "hardware": hw.to_dict(), "attack": attack.to_dict(),
                   "analysis": analysis, "privacy_amplification": cfg.privacy_amplification},
        "verdict": verdict,
        "abort_reason": abort,
        "analysis_note": NOTES[analysis],
        "detections": len(rec),
        "funnel": [
            {"stage": "Sifted", "bits": int(sifted.size), "eve": int(rec.eve_knows[sifted].sum())},
            {"stage": "Key bits", "bits": n_key, "eve": int(eve_known.sum())},
            {"stage": "Error-corrected", "bits": n_key if ec else 0, "eve": eve_after_ec},
            {"stage": "Final key", "bits": keys["length"] if keys else 0, "eve": eve_final},
        ],
        "estimation": est,
        "reconciliation": None if ec is None else {
            "n": ec.code.n, "syndrome_bits": ec.leak_bits, "tag_bits": ec.tag_bits, "rounds": len(ec.rounds),
            "errors_before": ec.errors_before, "errors_after": ec.errors_after, "efficiency": ec.efficiency},
        "privacy": privacy,
        "keys": keys,
        "classes": classes if hw.source == "wcp" else None,
        "decoy": decoy,
        "pns": rec.eve_info or None,
        "table": _table(rec, check_idx, key_idx),
    }


# ── Helpers for display ────────────────────────────────────────────────────────

def _hex(bits: np.ndarray, max_bits: int = 256) -> str:
    b = bits[:max_bits]
    b = np.concatenate([b, np.zeros((-b.size) % 4, np.uint8)])
    return "".join("0123456789abcdef"[int(v)] for v in (b.reshape(-1, 4) @ np.array([8, 4, 2, 1])))


def _table(rec, check_idx, key_idx, rows: int = 12):
    """First few detections, one row each, for the transmission log."""
    role = {i: "decoy" for i in range(min(rows, len(rec)))
            if rec.cls[i] != 0 and rec.a_basis[i] == rec.b_basis[i]}
    role.update({int(i): "check" for i in check_idx[check_idx < rows]})
    role.update({int(i): "key" for i in key_idx[key_idx < rows]})
    pns = bool(rec.eve_info)
    B = "+x"
    out = []
    for i in range(min(rows, len(rec))):
        if not rec.eve_touched[i]:
            eve = ""
        elif pns:
            eve = "kept a photon" if rec.eve_knows[i] else "forwarded"
        else:
            eve = f"{B[rec.eve_basis[i]]} → {int(rec.eve_bit[i])}"
        out.append({"photons": int(rec.n_photons[i]),
                    "alice": f"{B[rec.a_basis[i]]} {int(rec.a_bit[i])}",
                    "eve": eve, "eve_knows": bool(rec.eve_knows[i]),
                    "bob": f"{B[rec.b_basis[i]]} {int(rec.b_bit[i])}",
                    "role": role.get(i, ""),
                    "error": bool(rec.a_basis[i] == rec.b_basis[i] and rec.a_bit[i] != rec.b_bit[i])})
    return out
