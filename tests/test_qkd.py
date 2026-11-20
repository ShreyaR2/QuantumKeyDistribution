"""
Physics and protocol checks.  Run:  .venv/bin/python -m unittest -v
"""

import copy
import math
import unittest

import numpy as np

from qkd import Attack, HARDWARE_PRESETS, ProtocolConfig, run_protocol
from qkd.physics import simulate_channel, measure, state_angle
from qkd.gf2 import gf2_rank, eve_uncertainty
from qkd.reconciliation import reconcile
from qkd.estimation import paper_confidence_gap
from qkd.infotheory import h2
from qkd import theory

LAB = HARDWARE_PRESETS["lab"]
GYS = HARDWARE_PRESETS["gys"]


def eve_final(report):
    return report["funnel"][3]["eve"]


def qber(rec, mask=None):
    s = rec.a_basis == rec.b_basis
    if mask is not None:
        s &= mask
    return float((rec.a_bit != rec.b_bit)[s].mean())


class Physics(unittest.TestCase):
    def test_born_rule(self):
        rng = np.random.default_rng(0)
        n = 200_000
        basis = np.zeros(n, np.int8)
        bits = np.zeros(n, np.int8)
        same, _ = measure(state_angle(basis, bits), basis, rng)
        self.assertEqual(same.sum(), 0)                       # |0> measured in Z is always 0
        other, _ = measure(state_angle(basis, bits), np.ones(n, np.int8), rng)
        self.assertAlmostEqual(other.mean(), 0.5, delta=0.005)  # |0> measured in X is a coin flip

    def test_noise_only_qber(self):
        hw = copy.copy(LAB)
        hw.misalignment = 0.05
        rec = simulate_channel(200_000, hw, Attack(), np.random.default_rng(1))
        self.assertAlmostEqual(qber(rec), 0.05, delta=0.004)

    def test_intercept_resend_gives_25_percent(self):
        hw = copy.copy(LAB)
        hw.misalignment = 0.0
        rec = simulate_channel(200_000, hw, Attack("intercept_resend", 1.0), np.random.default_rng(2))
        self.assertAlmostEqual(qber(rec), 0.25, delta=0.005)
        sift = rec.a_basis == rec.b_basis
        self.assertAlmostEqual(rec.eve_knows[sift].mean(), 0.5, delta=0.005)

    def test_z_only_attack_only_disturbs_x(self):
        hw = copy.copy(LAB)
        hw.misalignment = 0.0
        rec = simulate_channel(200_000, hw, Attack("intercept_resend", 1.0, "Z"), np.random.default_rng(3))
        self.assertEqual(qber(rec, rec.a_basis == 0), 0.0)
        self.assertAlmostEqual(qber(rec, rec.a_basis == 1), 0.5, delta=0.01)

    def test_fibre_gain_matches_formula(self):
        hw = copy.copy(GYS)
        hw.decoy = False
        rec = simulate_channel(50_000_000, hw, Attack(), np.random.default_rng(4))
        expected = hw.dark_count + 1 - math.exp(-hw.transmittance * hw.mu)
        self.assertAlmostEqual(len(rec) / 50_000_000 / expected, 1.0, delta=0.03)

    def test_pns_is_error_free_and_gain_matched(self):
        hw = copy.copy(GYS)
        hw.distance_km = 40
        rng = np.random.default_rng(5)
        honest = simulate_channel(100_000_000, hw, Attack(), rng)
        pns = simulate_channel(100_000_000, hw, Attack("pns"), rng)
        self.assertAlmostEqual(pns.detected[0] / honest.detected[0], 1.0, delta=0.03)   # signal gain hidden
        self.assertAlmostEqual(qber(pns, pns.cls == 0), qber(honest, honest.cls == 0), delta=0.005)
        sift = (pns.a_basis == pns.b_basis) & (pns.cls == 0)
        self.assertGreater(pns.eve_knows[sift].mean(), 0.95)


class ClassicalPostProcessing(unittest.TestCase):
    def test_gf2_rank(self):
        rng = np.random.default_rng(6)
        A = rng.integers(0, 2, (40, 60))
        B = rng.integers(0, 2, (60, 25))
        self.assertEqual(gf2_rank((A @ B) % 2), 25)
        self.assertEqual(gf2_rank(np.eye(130, dtype=np.uint8)), 130)
        self.assertEqual(gf2_rank(np.zeros((5, 9), np.uint8)), 0)

    def test_eve_uncertainty_simple(self):
        # key = x0 ^ x1, public = x0 ^ x2. Eve knows x2 -> learns x0 -> key still hides x1
        public = np.array([[1, 0, 1]], np.uint8)
        key = np.array([[1, 1, 0]], np.uint8)
        self.assertEqual(eve_uncertainty(public, key, np.array([True, True, False])), 1)
        # Eve also knows x1 -> key fully determined
        self.assertEqual(eve_uncertainty(public, key, np.array([True, False, False])), 0)

    def test_ldpc_corrects(self):
        rng = np.random.default_rng(7)
        for p in (0.01, 0.05, 0.09):
            xa = rng.integers(0, 2, 3000).astype(np.uint8)
            xb = xa ^ (rng.random(3000) < p).astype(np.uint8)
            r = reconcile(xa, xb, p, rng)
            self.assertTrue(r.success)
            self.assertEqual(r.errors_after, 0)
            self.assertLess(r.efficiency, 1.6)

    def test_paper_bound(self):
        gap = paper_confidence_gap(0.05, 5000, 1e-10)
        d = 0.05 + gap
        self.assertAlmostEqual(math.exp(-gap ** 2 * 5000 / (4 * d * (1 - d))), 1e-10, delta=1e-11)


class Theory(unittest.TestCase):
    def test_thresholds(self):
        self.assertAlmostEqual(theory.threshold(theory.shor_preskill_rate), 0.110, delta=0.001)
        self.assertAlmostEqual(theory.threshold(theory.optimal_individual_attack_rate), 0.1464, delta=0.001)

    def test_decoy_reaches_far_further_than_no_decoy(self):
        d = theory.distance_curves(GYS)
        self.assertGreater(d["max_distance_decoy_practical"], 120)
        self.assertLess(d["max_distance_gllp_no_decoy"], 60)


class Protocol(unittest.TestCase):
    def test_honest_run_gives_identical_secret_keys(self):
        r = run_protocol(ProtocolConfig(hardware=LAB, seed=1))
        self.assertEqual(r["verdict"], "secure")
        self.assertTrue(r["keys"]["match"])
        self.assertGreater(r["keys"]["length"], 1000)
        self.assertEqual(eve_final(r), 0)

    def test_full_intercept_aborts(self):
        r = run_protocol(ProtocolConfig(hardware=LAB, attack=Attack("intercept_resend", 1.0), seed=1))
        self.assertEqual(r["verdict"], "aborted")
        self.assertIsNone(r["keys"])

    def test_privacy_amplification_erases_eves_knowledge(self):
        atk = Attack("intercept_resend", 0.1)
        r = run_protocol(ProtocolConfig(hardware=LAB, attack=atk, seed=1))
        self.assertEqual(r["verdict"], "secure")
        self.assertGreater(r["funnel"][1]["eve"], 100)       # Eve knows sifted key bits...
        self.assertEqual(eve_final(r), 0)                     # ...but nothing of the final key
        no_pa = run_protocol(ProtocolConfig(hardware=LAB, attack=atk, seed=1, privacy_amplification=False))
        self.assertEqual(no_pa["verdict"], "compromised")
        self.assertGreater(eve_final(no_pa), 1000)

    def test_pns_breaks_naive_and_decoy_detects_it(self):
        hw = copy.copy(GYS)
        hw.distance_km = 40
        naive = run_protocol(ProtocolConfig(n_pulses=4_000_000, hardware=hw, attack=Attack("pns"),
                                            analysis="naive", seed=2))
        self.assertEqual(naive["verdict"], "compromised")
        self.assertEqual(eve_final(naive), naive["keys"]["length"])
        decoy = run_protocol(ProtocolConfig(n_pulses=4_000_000, hardware=hw, attack=Attack("pns"),
                                            analysis="decoy", seed=2))
        self.assertEqual(decoy["verdict"], "aborted")
        honest = run_protocol(ProtocolConfig(n_pulses=4_000_000, hardware=hw, analysis="decoy", seed=2))
        self.assertEqual(honest["verdict"], "secure")


if __name__ == "__main__":
    unittest.main()
