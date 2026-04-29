# BB84 QKD Dashboard

A full-stack quantum key distribution simulator with a dark terminal-style dashboard.

```
bb84_dashboard/
├── bb84_simulation.py   ← core physics & protocol (no dependencies)
├── server.py            ← Flask API + static file server
├── dashboard.html       ← single-file dashboard (served by Flask)
└── README.md
```

---

## Quick Start

### 1. Install Flask (only dependency)
```bash
pip install flask
```

### 2. Run the server
```bash
cd bb84_dashboard
python server.py
```

### 3. Open the dashboard
```
http://localhost:5000
```

---

## Dashboard Features

| Panel | What it shows |
|-------|--------------|
| **Metric cards** | Qubits sent, matching bases, QBER, final key length |
| **Channel status** | Live verdict badge, protocol flow diagram, QBER bar |
| **Basis matching chart** | Doughnut — how many bases matched |
| **Bit error chart** | Bar — correct vs error bits in sifted key |
| **Transmission table** | First 30 qubits with Alice/Eve/Bob columns |
| **Sifted key viewer** | Color-coded bit comparison, QBER sample highlighted |
| **Final key** | Binary + hex display |
| **Statistical sweep** | 200-trial QBER histogram (clean vs Eve) |

---

## API Endpoints

### `POST /api/run`
Run a single BB84 simulation.
```json
{ "n_bits": 200, "eve_active": true }
```
Returns: summary stats, transmission table, sifted key, final key.

### `POST /api/sweep`
Run N trials for statistical analysis.
```json
{ "n_trials": 200, "n_bits": 150 }
```
Returns: QBER histograms, mean/std, detection rate for clean and Eve scenarios.

---

## Use as a library

```python
from bb84_simulation import run_bb84

# No attacker
r = run_bb84(n_bits=256, eve_active=False)
print(r.summary())
print("Key:", ''.join(map(str, r.final_key)))

# With Eve
r = run_bb84(n_bits=256, eve_active=True, seed=42)
print(f"QBER: {r.qber:.1%}  |  Secure: {r.secure}")
print(r.to_dict())
```

---

## Why BB84 works

```
  Alice            (Eve)              Bob
    │ ─── qubits ──► │ ─── qubits ──► │
    │                │                │
    │ ◄──── public basis sifting ────► │
    │                                 │
    │ ◄────── QBER on sample ────────► │
    │                                 │
  QBER < 11%  →  extract final key
  QBER ≥ 11%  →  abort (Eve detected)
```

Eve's intercept-resend attack guesses the right basis 50% of the time.
Wrong guesses force Bob to measure a randomly re-sent qubit → 50% error
in that half → **25% overall QBER** — far above the 11% abort threshold.

This is enforced by the **no-cloning theorem**: Eve cannot copy a qubit
without disturbing it.
