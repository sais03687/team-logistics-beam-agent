"""Task 4: mesh check of each workflow's final design (3 meshes).

Pass criteria (same as Task 1): between the two finest meshes,
deflection change < 2 % and nominal stress change < 5 %.
Writes team_logistics_final_mesh_check.csv.
"""
import csv
from pathlib import Path

import pandas as pd

from ansys_tools import evaluate_ansys, start_ansys, stop_ansys

HERE = Path(__file__).parent
MESHES_MM = [10.0, 8.0, 6.0]
OUT = HERE / "team_logistics_final_mesh_check.csv"

df = pd.read_csv(HERE / "team_logistics_beam_results.csv")
fin = df[(df.row_type == "tool_execution") & (df.phase == "final")]
designs = {}
for _, r in fin.iterrows():
    designs.setdefault((float(r.width_mm), float(r.height_mm)), []).append(r.workflow)
print("final designs:", designs)

rows = []
print("startup_s: %.1f" % start_ansys(), flush=True)
try:
    for (b, h), wfs in designs.items():
        res = []
        for m in MESHES_MM:
            r = evaluate_ansys(b, h, mesh_mm=m)
            res.append(r)
            print("  (%g, %g) mesh %.0f mm: %s defl=%s stress=%s nodes=%s" % (
                b, h, m, r["status"], r["deflection_mm"], r["nominal_stress_mpa"],
                (r["ansys_mesh"] or {}).get("nodes")), flush=True)
        ok = all(r["status"] == "ok" for r in res)
        d_chg = abs(res[-1]["deflection_mm"] - res[-2]["deflection_mm"]) / res[-1]["deflection_mm"] * 100 if ok else None
        s_chg = abs(res[-1]["nominal_stress_mpa"] - res[-2]["nominal_stress_mpa"]) / res[-1]["nominal_stress_mpa"] * 100 if ok else None
        for m, r in zip(MESHES_MM, res):
            rows.append({
                "workflows": "+".join(wfs), "width_mm": b, "height_mm": h, "mesh_mm": m,
                "strip_mm": min(5.0, m), "nodes": (r["ansys_mesh"] or {}).get("nodes"),
                "elements": (r["ansys_mesh"] or {}).get("elements"), "status": r["status"],
                "deflection_mm": r["deflection_mm"], "nominal_stress_mpa": r["nominal_stress_mpa"],
                "feasible": r["feasible"],
                "defl_change_two_finest_pct": d_chg, "stress_change_two_finest_pct": s_chg,
                "converged": (d_chg < 2.0 and s_chg < 5.0) if ok else None,
                "error": r.get("error"),
            })
        if ok:
            print("  -> defl change %.3f %%, stress change %.3f %%, converged=%s, feasible on finest=%s"
                  % (d_chg, s_chg, d_chg < 2.0 and s_chg < 5.0, res[-1]["feasible"]), flush=True)
finally:
    stop_ansys()

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("saved", OUT)
