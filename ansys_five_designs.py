"""Task 1: Python vs ANSYS at the five required designs.

Writes team_logistics_five_design_comparison.csv with signed and absolute percentage
differences relative to ANSYS.
"""
import csv
from pathlib import Path

import beam_tools as bt
from ansys_tools import evaluate_ansys, start_ansys, stop_ansys

DESIGNS = [(50, 80), (20, 40), (20, 120), (100, 40), (100, 120)]
OUT = Path(__file__).with_name("team_logistics_five_design_comparison.csv")


def diff(py, an):
    if py is None or an is None:
        return None, None
    signed = py - an
    return signed, abs(signed) / abs(an) * 100.0


rows = []
print("startup_s: %.1f" % start_ansys(), flush=True)
try:
    for b, h in DESIGNS:
        p = bt.evaluate_python(b, h)
        a = evaluate_ansys(b, h)
        row = {"width_mm": b, "height_mm": h, "ansys_status": a["status"],
               "ansys_error": a.get("error"), "ansys_elapsed_s": round(a["elapsed_s"], 1),
               "ansys_nodes": (a["ansys_mesh"] or {}).get("nodes")}
        for key in ("mass_kg", "deflection_mm", "nominal_stress_mpa"):
            s, pct = diff(p[key], a[key])
            row["python_" + key] = p[key]
            row["ansys_" + key] = a[key]
            row["signed_diff_" + key] = s
            row["abs_pct_diff_" + key] = pct
        row["python_feasible"] = p["feasible"]
        row["ansys_feasible"] = a["feasible"]
        rows.append(row)
        print("(%g, %g) %s  defl py=%.4f an=%s  stress py=%.2f an=%s" % (
            b, h, a["status"], p["deflection_mm"], a["deflection_mm"],
            p["nominal_stress_mpa"], a["nominal_stress_mpa"]), flush=True)
finally:
    stop_ansys()

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("saved", OUT)
