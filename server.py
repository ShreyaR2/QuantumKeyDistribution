"""
Demo server: serves the dashboard and runs one scenario per request.

    .venv/bin/python server.py   ->   http://localhost:5050
    (port 5000 is taken by AirPlay on macOS)
"""

import os

from flask import Flask, abort, jsonify, send_from_directory

from qkd.scenarios import SCENARIOS, run_scenario

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


@app.route("/api/scenarios")
def scenarios():
    """Titles and talking points for the demo steps."""
    return jsonify([{k: s[k] for k in ("act", "title", "story", "look")} for s in SCENARIOS])


@app.route("/api/run/<int:i>")
def run(i):
    """Run demo step i (0-based) and return the full protocol report."""
    if not 0 <= i < len(SCENARIOS):
        abort(404)
    return jsonify(run_scenario(i))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  BB84 demo  →  http://localhost:{port}\n")
    app.run(port=port)
