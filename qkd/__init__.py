"""
qkd: BB84 implemented step by step from Shor & Preskill (2000),
"Simple Proof of Security of the BB84 Quantum Key Distribution Protocol".

    protocol.py        one full run, step by step (start reading here)
    physics.py         photons, Born-rule measurement, fibre, detectors, Eve's attacks
    estimation.py      error rates, the paper's sampling bound, decoy-state bounds
    reconciliation.py  error correction = the paper's code C1 (LDPC, belief propagation)
    privacy.py         privacy amplification = the paper's code C2 (Toeplitz hashing)
    gf2.py             exact count of how many key bits Eve knows
    scenarios.py       the 8 demo scenarios
    theory.py          reference formulas: 1 − 2H(δ), the 11% threshold, rate vs distance
"""

from .physics import Hardware, Attack, HARDWARE_PRESETS
from .protocol import ProtocolConfig, run_protocol

__all__ = ["Hardware", "Attack", "HARDWARE_PRESETS", "ProtocolConfig", "run_protocol"]
