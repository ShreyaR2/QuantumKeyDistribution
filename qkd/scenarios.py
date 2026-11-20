"""
The guided demo: eight scenarios that walk from textbook BB84 to the attack the
paper's proof doesn't cover, and its fix. Used by the dashboard and `demo.py`.
"""

LAB = {"source": "single", "distance_km": 0, "eta_bob": 1.0, "dark_count": 0.0, "misalignment": 0.02}
FIBRE = {"source": "wcp", "mu": 0.48, "nu": 0.05, "decoy": True, "p_signal": 0.8, "distance_km": 40,
         "alpha_db_per_km": 0.21, "eta_bob": 0.045, "dark_count": 1.7e-6, "misalignment": 0.033}

SCENARIOS = [
    {
        "id": "clean", "act": "I. The protocol", "title": "Honest channel",
        "params": {"n_pulses": 20000, "hardware": LAB, "attack": {"kind": "none"}, "seed": 1},
        "story": "Single photons, 2% channel noise, no Eve. Half the sifted bits are random check bits "
                 "(Z and X estimated separately). LDPC belief propagation fixes Bob's errors, and a Toeplitz hash "
                 "compresses to the Shor–Preskill length. Alice and Bob finish with identical keys.",
        "look": "The red sliver at 'Error-corrected' is the public syndrome: error correction itself leaks "
                "information. Privacy amplification removes it, and Eve's exact knowledge of the final key is 0 bits.",
    },
    {
        "id": "full_ir", "act": "I. The protocol", "title": "Eve measures everything",
        "params": {"n_pulses": 20000, "hardware": LAB, "attack": {"kind": "intercept_resend", "fraction": 1.0},
                   "seed": 1},
        "story": "Eve intercepts every photon, measures in a random basis and resends. She guesses the basis wrong "
                 "half the time, and those photons then give Bob a random result: 25% QBER.",
        "look": "Eve knows ~50% of the sifted key, but the check bits catch her and the protocol aborts before "
                "any key is produced.",
    },
    {
        "id": "stealth", "act": "II. Why privacy amplification", "title": "Stealthy Eve (10%)",
        "params": {"n_pulses": 20000, "hardware": LAB, "attack": {"kind": "intercept_resend", "fraction": 0.1},
                   "seed": 1},
        "story": "Eve only taps 10% of photons, staying well under the 11% threshold. The QBER rises to ~4.5% and "
                 "the protocol continues, but now Eve really does know some key bits.",
        "look": "Follow the red bar: Eve knows ~250 sifted bits plus the syndrome, yet after hashing to the "
                "length the paper allows she knows exactly 0 bits of the final key (exact GF(2) rank).",
    },
    {
        "id": "no_pa", "act": "II. Why privacy amplification", "title": "Same Eve, no privacy amplification",
        "params": {"n_pulses": 20000, "hardware": LAB, "attack": {"kind": "intercept_resend", "fraction": 0.1},
                   "privacy_amplification": False, "seed": 1},
        "story": "Same attack, but skip step 10 (the 'coset of C2'). This is what the original prototype did: "
                 "Alice and Bob would happily use the corrected string as their key.",
        "look": "Eve's information about the key is now thousands of bits: her direct knowledge plus everything "
                "the error-correction syndrome revealed.",
    },
    {
        "id": "z_only", "act": "II. Why privacy amplification", "title": "Bit vs phase errors",
        "params": {"n_pulses": 20000, "hardware": LAB,
                   "attack": {"kind": "intercept_resend", "fraction": 0.15, "basis": "Z"}, "seed": 1},
        "story": "Eve always measures in Z. Z-encoded bits come through without errors, so a check on Z alone "
                 "would see nothing. Her disturbance shows up only as X-basis errors.",
        "look": "Compare the Z and X error rates. As in the paper's Bell-basis identities, X-check errors bound "
                "the *phase* errors on Z-key bits, which is exactly where Eve's information sits.",
    },
    {
        "id": "fibre", "act": "III. Real hardware", "title": "40 km of fibre, weak laser",
        "params": {"n_pulses": 4000000, "hardware": FIBRE, "attack": {"kind": "none"}, "seed": 2},
        "story": "Real systems use attenuated laser pulses (Poisson photon number, μ = 0.48) over lossy fibre "
                 "with imperfect detectors (Gobby–Yuan–Shields 2004 parameters). Only ~0.25% of pulses click.",
        "look": "The paper's last paragraph says no known proof covers weak coherent sources. The decoy-state "
                "panel shows the fix: decoy and vacuum pulses bound the single-photon contribution.",
    },
    {
        "id": "pns_naive", "act": "III. Real hardware", "title": "PNS attack vs naive BB84",
        "params": {"n_pulses": 4000000, "hardware": FIBRE, "attack": {"kind": "pns"}, "analysis": "naive",
                   "seed": 2},
        "story": "Eve splits one photon off every multi-photon pulse and blocks the single-photon ones, forwarding "
                 "the rest over a lossless line so Bob's click rate looks exactly like 40 km of fibre. "
                 "The analysis treats each pulse as one photon.",
        "look": "QBER ≈ 3%, and the protocol happily outputs a key. Eve knows every single bit of it.",
    },
    {
        "id": "pns_decoy", "act": "III. Real hardware", "title": "PNS attack vs decoy states",
        "params": {"n_pulses": 4000000, "hardware": FIBRE, "attack": {"kind": "pns"}, "analysis": "decoy",
                   "seed": 2},
        "story": "Same attack, but Alice randomly mixes in weak decoy (ν = 0.05) and vacuum pulses. Eve can't tell "
                 "them apart from signal pulses, so she can't match all three click rates at once.",
        "look": "The decoy gain doesn't fit an honest channel, the single-photon yield bound collapses to 0, and "
                "the protocol aborts. Attack detected.",
    },
]


def run_scenario(index: int) -> dict:
    """Run scenario number `index` (0-based) and return the protocol report."""
    from .physics import Hardware, Attack
    from .protocol import ProtocolConfig, run_protocol
    p = SCENARIOS[index]["params"]
    return run_protocol(ProtocolConfig(
        n_pulses=p["n_pulses"], hardware=Hardware(**p["hardware"]), attack=Attack(**p["attack"]),
        analysis=p.get("analysis", "auto"), privacy_amplification=p.get("privacy_amplification", True),
        seed=p.get("seed")))
