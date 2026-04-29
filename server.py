"""
BB84 Dashboard API Server
=========================
Serves the dashboard HTML and provides a REST API for simulation runs.

Install:  pip install flask
Run:      python server.py
Open:     http://localhost:5000
"""

import json
import statistics
from flask import Flask, jsonify, request, send_from_directory
import os

from bb84_simulation import run_bb84

app = Flask(__name__, static_folder='static')


@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')


@app.route('/api/run', methods=['POST'])
def api_run():
    """
    POST /api/run
    Body: { "n_bits": 200, "eve_active": false }
    Returns full simulation result JSON.
    """
    data      = request.get_json(force=True)
    n_bits    = int(data.get('n_bits', 100))
    eve       = bool(data.get('eve_active', False))
    n_bits    = max(20, min(10000, n_bits))

    result    = run_bb84(n_bits=n_bits, eve_active=eve)

    # Build transmission table (first 30 rows)
    table = []
    matching_set = set(result.matching_indices)
    for i in range(min(30, n_bits)):
        ab = result.alice_bases[i]
        av = result.alice_bits[i]
        bb = result.bob_bases[i]
        bv = result.bob_measured[i]
        is_match = i in matching_set
        is_error = is_match and (av != bv)
        row = {
            'i': i,
            'alice_bit':   av,
            'alice_basis': ab,
            'qubit':       {'++': '|0⟩', '+−': '|0⟩',
                            '+0': '|0⟩', '+1': '|1⟩',
                            'x0': '|+⟩', 'x1': '|-⟩'}.get(ab+str(av), '?'),
            'bob_basis':   bb,
            'bob_bit':     bv,
            'match':       is_match,
            'error':       is_error,
        }
        if result.eve_present:
            row['eve_basis'] = result.eve_bases[i]
            row['eve_bit']   = result.eve_measured[i]
        table.append(row)

    # Sifted key (first 64 bits)
    sifted = [
        {'alice': a, 'bob': b, 'sample': i < result.key_length // 2}
        for i, (a, b) in enumerate(zip(result.sifted_alice[:64], result.sifted_bob[:64]))
    ]

    return jsonify({
        'summary':     result.to_dict(),
        'table':       table,
        'sifted':      sifted,
        'final_key':   result.final_key[:64],
        'alice_bases': result.alice_bases[:64],
        'bob_bases':   result.bob_bases[:64],
    })


@app.route('/api/sweep', methods=['POST'])
def api_sweep():
    """
    POST /api/sweep
    Body: { "n_trials": 200, "n_bits": 150 }
    Runs N trials with and without Eve, returns QBER distributions.
    """
    data     = request.get_json(force=True)
    n_trials = int(data.get('n_trials', 200))
    n_bits   = int(data.get('n_bits', 150))
    n_trials = max(10, min(500, n_trials))
    n_bits   = max(20, min(10000, n_bits))

    clean_qbers, clean_keys = [], []
    eve_qbers,   eve_keys   = [], []

    for _ in range(n_trials):
        r = run_bb84(n_bits=n_bits, eve_active=False)
        clean_qbers.append(round(r.qber * 100, 2))
        clean_keys.append(r.key_length)

        r = run_bb84(n_bits=n_bits, eve_active=True)
        eve_qbers.append(round(r.qber * 100, 2))
        eve_keys.append(r.key_length)

    def histogram(values, bins=20):
        mn, mx = min(values), max(values)
        if mx == mn:
            return [{'x': round(mn, 2), 'y': len(values)}]
        w = (mx - mn) / bins
        counts = [0] * bins
        for v in values:
            idx = min(int((v - mn) / w), bins - 1)
            counts[idx] += 1
        return [{'x': round(mn + i * w, 2), 'y': c} for i, c in enumerate(counts)]

    return jsonify({
        'n_trials':          n_trials,
        'n_bits':            n_bits,
        'clean': {
            'qbers':         clean_qbers,
            'histogram':     histogram(clean_qbers),
            'mean_qber':     round(statistics.mean(clean_qbers), 2),
            'std_qber':      round(statistics.stdev(clean_qbers) if len(clean_qbers)>1 else 0, 2),
            'detection_pct': 0.0,
            'mean_key_len':  round(statistics.mean(clean_keys), 1),
        },
        'eve': {
            'qbers':         eve_qbers,
            'histogram':     histogram(eve_qbers),
            'mean_qber':     round(statistics.mean(eve_qbers), 2),
            'std_qber':      round(statistics.stdev(eve_qbers) if len(eve_qbers)>1 else 0, 2),
            'detection_pct': round(100 * sum(1 for q in eve_qbers if q >= 11) / n_trials, 1),
            'mean_key_len':  round(statistics.mean(eve_keys), 1),
        },
    })


if __name__ == '__main__':
    print("\n  BB84 Dashboard running at http://localhost:5000\n")
    app.run(debug=True, port=5000)