# BB84, provably secure: a Shor–Preskill security demo

An implementation of **Protocol 3** from Shor & Preskill, *"Simple Proof of Security of the BB84 Quantum Key
Distribution Protocol"* (2000; `Proof of Security of the BB84.pdf`), extended to the case the paper says it can't cover: weak laser
pulses, the **photon-number-splitting attack**, and the **decoy-state** fix.

Every classical step of the protocol is linear over GF(2), so the simulator computes **exactly how many bits of the
final key Eve knows**. You can watch the security claim hold, and watch it fail when an assumption breaks.



## Run it

```bash
python3 -m venv .venv                       # one time
.venv/bin/pip install -r requirements.txt   # one time
.venv/bin/python server.py                  # then open http://localhost:5050
```

| Also | Command |
|---|---|
| Same demo in the terminal | `.venv/bin/python demo.py` (or `demo.py 7 8`) |
| Tests (16, ~2 s) | `.venv/bin/python -m unittest -v` |

Use the venv: on this Mac the system Python's numpy is an Intel build and won't import. Port 5050 because macOS AirPlay
uses 5000.

## The demo

One page, eight steps (click the numbers or press ← / →). Each section on the page has a one-line explanation.

| Step | Scenario | Result |
|---|---|---|
| **I. The protocol** | | |
| 1 | Honest channel | 2,002-bit key, Alice = Bob, Eve knows 0 bits |
| 2 | Eve measures everything | 25% errors, protocol stops |
| **II. Why privacy amplification** | | |
| 3 | Eve taps 10% of photons | Eve knows 249 key bits, then **0 after hashing** |
| 4 | Same, hashing switched off | Eve knows 2,028 bits of the key |
| 5 | Eve measures only in Z | Errors show up only in X checks (bit vs phase errors) |
| **III. Real hardware** | | |
| 6 | 40 km fibre, weak laser | Secure key; decoy click rates look honest |
| 7 | Photon-splitting attack, naive analysis | 3% errors, 387-bit key, **Eve knows all 387 bits** |
| 8 | Same attack, decoy analysis | Click rates don't fit, so the attack is detected and the protocol stops |

## Code map: start with `qkd/protocol.py`

`run_protocol()` reads top to bottom like the paper, one short function per step:

| Step | Function | Module | Paper |
|---|---|---|---|
| 1. Send & measure | `simulate_channel` | `physics.py` | steps 1–4 |
| 2. Sift | `sift` | `protocol.py` | steps 5–6 (random check bits) |
| 3. Estimate errors | `estimate_errors` | `protocol.py`, `estimation.py` | step 7 + sampling bound |
| 4. Secret fraction | `secret_fraction` | `protocol.py`, `estimation.py` | 1 − H(phase error); decoy bounds |
| 5. Error correction | `reconcile` | `reconciliation.py` | steps 8–9, code C₁ (LDPC) |
| 6. Privacy amplification | `toeplitz_hash_matrix` | `privacy.py` | step 10, code C₂ |
| 7. Eve's exact knowledge | `measure_eve` | `gf2.py` | the security claim, checked |

Other files: `scenarios.py` (the 8 demo steps), `theory.py` (reference formulas: 1 − 2H(δ), 11% threshold,
rate vs distance), `server.py` (2 endpoints), `dashboard.html` (one page), `demo.py`, `tests/`.

## Limitations
* The simulation checks security only against the attacks implemented (intercept–resend, photon splitting); the
  paper's proof covers all attacks.
* Decoy bounds assume large samples (finite-size decoy analysis is the next step).
