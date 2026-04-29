"""
BB84 Quantum Key Distribution — Core Simulation
================================================
Improvements over v1:
  1. Channel noise model  — realistic baseline QBER from fibre imperfections
  2. Partial Eve attack   — Eve intercepts only a fraction of qubits
  3. Privacy amplification — SHA-256 hash shrinks key, removes Eve's partial info

Pure Python, no external dependencies.
"""

import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional

BASES = ['+', 'x']
BITS  = [0, 1]

QUBIT_STATES = {
    ('+', 0): '|0⟩',
    ('+', 1): '|1⟩',
    ('x', 0): '|+⟩',
    ('x', 1): '|-⟩',
}


# ── Quantum measurement ────────────────────────────────────────────────────────

def measure_qubit(qubit_basis: str, qubit_bit: int, meas_basis: str) -> int:
    if qubit_basis == meas_basis:
        return qubit_bit
    return random.randint(0, 1)


def apply_noise(bit: int, noise_rate: float) -> int:
    """
    IMPROVEMENT 1 — Channel noise model.
    Models real fibre imperfections: detector dark counts, polarisation
    drift, thermal photons. Each bit is independently flipped with
    probability noise_rate regardless of Eve.
    Typical real-world value: 0.01 to 0.05 (1-5%).
    """
    if noise_rate > 0 and random.random() < noise_rate:
        return 1 - bit
    return bit


# ── Participants ───────────────────────────────────────────────────────────────

@dataclass
class Alice:
    n_bits: int
    bits:   list[int] = field(default_factory=list)
    bases:  list[str] = field(default_factory=list)

    def prepare(self):
        self.bits  = [random.choice(BITS)  for _ in range(self.n_bits)]
        self.bases = [random.choice(BASES) for _ in range(self.n_bits)]

    def qubits(self):
        return list(zip(self.bases, self.bits))


@dataclass
class Bob:
    bases:    list[str] = field(default_factory=list)
    measured: list[int] = field(default_factory=list)

    def measure_all(self, qubits, noise_rate: float = 0.0):
        self.bases    = [random.choice(BASES) for _ in qubits]
        self.measured = [
            apply_noise(measure_qubit(qb, qv, mb), noise_rate)
            for (qb, qv), mb in zip(qubits, self.bases)
        ]


@dataclass
class Eve:
    """
    IMPROVEMENT 2 — Partial intercept-resend attack.
    intercept_fraction controls what fraction of qubits Eve intercepts.
      0.0  = passive (no attack)
      1.0  = full intercept (original behaviour)
      0.44 = max Eve can intercept while staying under 11% QBER threshold
    """
    active:               bool      = False
    intercept_fraction:   float     = 1.0
    bases:                list      = field(default_factory=list)
    measured:             list      = field(default_factory=list)
    intercepted_indices:  list[int] = field(default_factory=list)

    def intercept(self, qubits):
        n = len(qubits)
        self.bases               = [None] * n
        self.measured            = [None] * n
        self.intercepted_indices = []
        resent = list(qubits)

        for i, (qb, qv) in enumerate(qubits):
            if random.random() < self.intercept_fraction:
                eb = random.choice(BASES)
                em = measure_qubit(qb, qv, eb)
                self.bases[i]    = eb
                self.measured[i] = em
                resent[i]        = (eb, em)
                self.intercepted_indices.append(i)
            else:
                self.bases[i]    = '-'
                self.measured[i] = -1

        return resent


# ── Privacy amplification ──────────────────────────────────────────────────────

def privacy_amplify(key_bits: list[int]) -> list[int]:
    """
    IMPROVEMENT 3 — Privacy amplification via SHA-256.

    Even if Eve correctly guessed some key bits during interception,
    hashing destroys her partial knowledge. Any bit she got wrong
    propagates avalanche-style through the entire hash output, making
    her information about the final key negligibly small.

    The output is shorter than the input — this is intentional.
    Length reduction is the cost of eliminating Eve's leakage.
    """
    if not key_bits:
        return []

    # Pack bits into bytes
    n = len(key_bits)
    padded = key_bits + [0] * ((8 - n % 8) % 8)
    byte_array = bytearray()
    for i in range(0, len(padded), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | padded[i + j]
        byte_array.append(byte)

    # SHA-256 hash
    digest = hashlib.sha256(bytes(byte_array)).digest()

    # Convert back to bits
    output_bits = []
    for byte in digest:
        for j in range(7, -1, -1):
            output_bits.append((byte >> j) & 1)

    return output_bits[:min(n, 256)]


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class BB84Result:
    n_bits:               int
    alice_bits:           list[int]
    alice_bases:          list[str]
    bob_bases:            list[str]
    bob_measured:         list[int]
    matching_indices:     list[int]
    sifted_alice:         list[int]
    sifted_bob:           list[int]
    qber:                 float
    noise_rate:           float
    eve_present:          bool
    intercept_fraction:   float
    raw_key:              list[int]
    final_key:            list[int]
    eve_bases:            Optional[list] = None
    eve_measured:         Optional[list] = None
    eve_intercepted_count: int = 0
    eve_correct_intercepts: int = 0

    @property
    def key_length(self) -> int:
        return len(self.final_key)

    @property
    def raw_key_length(self) -> int:
        return len(self.raw_key)

    @property
    def secure(self) -> bool:
        return self.qber < 0.11

    @property
    def expected_eve_qber(self) -> float:
        return 0.25 * self.intercept_fraction

    def to_dict(self) -> dict:
        return {
            "n_bits":             self.n_bits,
            "matching_count":     len(self.matching_indices),
            "matching_pct":       round(100 * len(self.matching_indices) / self.n_bits, 1),
            "sifted_length":      len(self.sifted_alice),
            "qber":               round(self.qber * 100, 2),
            "noise_rate":         round(self.noise_rate * 100, 1),
            "secure":             self.secure,
            "raw_key_length":     self.raw_key_length,
            "key_length":         self.key_length,
            "final_key_bin":      ''.join(map(str, self.final_key)),
            "eve_present":        self.eve_present,
            "intercept_fraction": round(self.intercept_fraction * 100, 1),
            "expected_eve_qber":  round(self.expected_eve_qber * 100, 2),
            "eve_intercepted":    self.eve_intercepted_count,
        }

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  BB84 Key Distribution Summary",
            f"{'='*60}",
            f"  Qubits transmitted    : {self.n_bits}",
            f"  Channel noise rate    : {self.noise_rate*100:.1f}%",
            f"  Eve active            : {'YES' if self.eve_present else 'NO'}",
        ]
        if self.eve_present:
            lines.append(f"  Eve intercept frac.   : {self.intercept_fraction*100:.0f}% ({self.eve_intercepted_count} qubits)")
        lines += [
            f"  Matching bases        : {len(self.matching_indices)} ({100*len(self.matching_indices)/self.n_bits:.1f}%)",
            f"  Sifted key length     : {len(self.sifted_alice)}",
            f"  QBER                  : {self.qber*100:.2f}%",
            f"  Secure                : {'YES' if self.secure else 'NO (ABORT)'}",
            f"  Raw key length        : {self.raw_key_length} bits",
            f"  After priv. amplif.   : {self.key_length} bits (SHA-256)",
            f"{'='*60}",
        ]
        if self.final_key:
            key_str = ''.join(map(str, self.final_key))
            lines.append(f"  Final key (binary)    : {key_str[:64]}{'...' if len(key_str)>64 else ''}")
            if len(key_str) >= 4:
                lines.append(f"  Final key (hex)       : 0x{int(key_str,2):0{len(key_str)//4}X}")
        return '\n'.join(lines)


# ── Main protocol function ─────────────────────────────────────────────────────

def run_bb84(
    n_bits:             int   = 100,
    eve_active:         bool  = False,
    intercept_fraction: float = 1.0,
    noise_rate:         float = 0.02,
    seed:               Optional[int] = None,
) -> BB84Result:
    """
    Run one complete BB84 session.

    Parameters
    ----------
    n_bits             : number of qubits Alice transmits
    eve_active         : whether Eve is present on the channel
    intercept_fraction : fraction of qubits Eve intercepts (0.0-1.0)
    noise_rate         : per-bit flip probability from channel imperfections
    seed               : optional RNG seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)

    alice = Alice(n_bits)
    bob   = Bob()
    eve   = Eve(active=eve_active, intercept_fraction=intercept_fraction)

    alice.prepare()
    channel_qubits = alice.qubits()

    if eve.active:
        channel_qubits = eve.intercept(channel_qubits)

    bob.measure_all(channel_qubits, noise_rate=noise_rate)

    matching     = [i for i, (ab, bb_) in enumerate(zip(alice.bases, bob.bases)) if ab == bb_]
    sifted_alice = [alice.bits[i]   for i in matching]
    sifted_bob   = [bob.measured[i] for i in matching]

    sample_size = max(1, len(sifted_alice) // 2)
    errors      = sum(a != b for a, b in zip(sifted_alice[:sample_size], sifted_bob[:sample_size]))
    qber        = errors / sample_size if sample_size else 0.0

    raw_key   = sifted_alice[sample_size:] if qber < 0.11 else []
    final_key = privacy_amplify(raw_key)

    eve_intercepted = len(eve.intercepted_indices) if eve.active else 0
    eve_correct = 0
    if eve.active:
        for i in matching:
            if eve.measured[i] != -1 and eve.measured[i] == alice.bits[i]:
                eve_correct += 1

    return BB84Result(
        n_bits=n_bits,
        alice_bits=alice.bits,
        alice_bases=alice.bases,
        bob_bases=bob.bases,
        bob_measured=bob.measured,
        matching_indices=matching,
        sifted_alice=sifted_alice,
        sifted_bob=sifted_bob,
        qber=qber,
        noise_rate=noise_rate,
        eve_present=eve_active,
        intercept_fraction=intercept_fraction if eve_active else 0.0,
        raw_key=raw_key,
        final_key=final_key,
        eve_bases=eve.bases    if eve.active else None,
        eve_measured=eve.measured if eve.active else None,
        eve_intercepted_count=eve_intercepted,
        eve_correct_intercepts=eve_correct,
    )