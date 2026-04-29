"""
BB84 Quantum Key Distribution — Core Simulation
================================================
Pure Python, no external dependencies required.
"""

import random
import math
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


def measure_qubit(qubit_basis: str, qubit_bit: int, meas_basis: str) -> int:
    if qubit_basis == meas_basis:
        return qubit_bit
    return random.randint(0, 1)


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

    def measure_all(self, qubits):
        self.bases    = [random.choice(BASES) for _ in qubits]
        self.measured = [
            measure_qubit(qb, qv, mb)
            for (qb, qv), mb in zip(qubits, self.bases)
        ]


@dataclass
class Eve:
    active:   bool      = False
    bases:    list[str] = field(default_factory=list)
    measured: list[int] = field(default_factory=list)

    def intercept(self, qubits):
        self.bases    = [random.choice(BASES) for _ in qubits]
        self.measured = []
        resent = []
        for (qb, qv), eb in zip(qubits, self.bases):
            m = measure_qubit(qb, qv, eb)
            self.measured.append(m)
            resent.append((eb, m))
        return resent


@dataclass
class BB84Result:
    n_bits:            int
    alice_bits:        list[int]
    alice_bases:       list[str]
    bob_bases:         list[str]
    bob_measured:      list[int]
    matching_indices:  list[int]
    sifted_alice:      list[int]
    sifted_bob:        list[int]
    qber:              float
    key_length:        int
    final_key:         list[int]
    eve_present:       bool
    eve_bases:         Optional[list[str]] = None
    eve_measured:      Optional[list[int]] = None
    eve_correct_intercepts: int = 0

    @property
    def secure(self) -> bool:
        return self.qber < 0.11

    def to_dict(self) -> dict:
        return {
            "n_bits":           self.n_bits,
            "matching_count":   len(self.matching_indices),
            "matching_pct":     round(100 * len(self.matching_indices) / self.n_bits, 1),
            "sifted_length":    len(self.sifted_alice),
            "qber":             round(self.qber * 100, 2),
            "secure":           self.secure,
            "key_length":       self.key_length,
            "final_key_bin":    ''.join(map(str, self.final_key)),
            "eve_present":      self.eve_present,
        }

    def summary(self) -> str:
        lines = [
            f"{'='*55}",
            f"  BB84 Key Distribution Summary",
            f"{'='*55}",
            f"  Qubits transmitted : {self.n_bits}",
            f"  Matching bases     : {len(self.matching_indices)} ({100*len(self.matching_indices)/self.n_bits:.1f}%)",
            f"  Sifted key length  : {len(self.sifted_alice)}",
            f"  QBER               : {self.qber*100:.2f}%",
            f"  Eve present        : {'YES ⚠' if self.eve_present else 'NO ✓'}",
            f"  Channel secure     : {'YES ✓' if self.secure else 'NO ✗  (ABORT)'}",
            f"  Final key length   : {self.key_length}",
            f"{'='*55}",
        ]
        if self.final_key:
            key_str = ''.join(map(str, self.final_key))
            lines.append(f"  Key (binary)       : {key_str[:64]}{'...' if len(key_str)>64 else ''}")
            if len(key_str) >= 4:
                lines.append(f"  Key (hex)          : 0x{int(key_str,2):0{len(key_str)//4}X}")
        return '\n'.join(lines)


def run_bb84(n_bits: int = 100, eve_active: bool = False, seed: Optional[int] = None) -> BB84Result:
    if seed is not None:
        random.seed(seed)

    alice = Alice(n_bits)
    bob   = Bob()
    eve   = Eve(active=eve_active)

    alice.prepare()
    channel_qubits = alice.qubits()

    if eve.active:
        channel_qubits = eve.intercept(channel_qubits)

    bob.measure_all(channel_qubits)

    matching = [i for i, (ab, bb) in enumerate(zip(alice.bases, bob.bases)) if ab == bb]

    sifted_alice = [alice.bits[i]   for i in matching]
    sifted_bob   = [bob.measured[i] for i in matching]

    sample_size = max(1, len(sifted_alice) // 2)
    errors      = sum(a != b for a, b in zip(sifted_alice[:sample_size], sifted_bob[:sample_size]))
    qber        = errors / sample_size if sample_size else 0.0

    final_key = sifted_alice[sample_size:] if qber < 0.11 else []

    eve_correct = 0
    if eve.active:
        eve_correct = sum(1 for i in matching if eve.measured[i] == alice.bits[i])

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
        key_length=len(final_key),
        final_key=final_key,
        eve_present=eve_active,
        eve_bases=eve.bases    if eve.active else None,
        eve_measured=eve.measured if eve.active else None,
        eve_correct_intercepts=eve_correct,
    )
