"""
Terminal walk-through of the eight demo scenarios (backup for a live demo with no browser).

    .venv/bin/python demo.py          # all scenarios
    .venv/bin/python demo.py 7 8      # just the PNS pair
"""

import sys
import textwrap

from qkd.scenarios import SCENARIOS, run_scenario

RED, GRN, YEL, CYN, DIM, BLD, RST = "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[2m", "\033[1m", "\033[0m"
VERDICT = {"secure": GRN + "SECURE KEY", "aborted": YEL + "ABORTED", "compromised": RED + "KEY COMPROMISED"}


def bar(bits, eve, scale, width=44):
    n = int(round(width * bits / scale)) if scale else 0
    e = int(round(width * min(eve or 0, bits) / scale)) if scale else 0
    return RED + "█" * e + CYN + "█" * (n - e) + DIM + "·" * (width - n) + RST


def show(i: int, s: dict):
    r = run_scenario(i - 1)
    e = r["estimation"]
    print(f"\n{BLD}{i}. {s['title']}{RST}  {DIM}{s['act']}{RST}")
    print(textwrap.fill(s["story"], 96, initial_indent="   ", subsequent_indent="   "))
    print(f"   QBER {e['e_bit']:.2%}  (Z {e['e_Z']:.2%} · X {e['e_X']:.2%})   phase-error bound {e['e_phase_upper']:.2%}")
    f = r["funnel"]
    print(f"   {r['config']['n_pulses']:,} pulses → {r['detections']:,} detections")
    scale = max(f[0]["bits"], 1)
    for st in f:
        eve = "" if st["eve"] is None else f"   Eve: {st['eve']:,}"
        print(f"   {st['stage']:<16} {bar(st['bits'], st['eve'], scale)} {st['bits']:>7,}{RED if st['eve'] else GRN}{eve}{RST}")
    print(f"   {VERDICT[r['verdict']]}{RST}" + (f"  {DIM}{r['abort_reason']}{RST}" if r["abort_reason"] else ""))
    if r["keys"]:
        print(f"   key: {r['keys']['alice_hex'][:48]}…  Alice = Bob: {r['keys']['match']}")


if __name__ == "__main__":
    picks = [int(a) for a in sys.argv[1:]] or range(1, len(SCENARIOS) + 1)
    for i in picks:
        show(i, SCENARIOS[i - 1])
    print()
