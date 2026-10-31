"""Task 4 comparison: table and two plots from team_logistics_beam_results.csv."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "team_logistics_beam_results.csv"
P, L, E = 10000.0, 1000.0, 200000.0
COLORS = {"A": "#1f77b4", "B": "#ff7f0e", "C": "#2ca02c"}


def load():
    df = pd.read_csv(CSV)
    # one row per workflow: use the latest run of each workflow only
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def comparison_table(df):
    rows = []
    for wf, g in df.groupby("workflow"):
        ex = g[g.row_type == "tool_execution"]
        fin = ex[ex.phase == "final"]
        f = fin.iloc[-1] if len(fin) else None
        rows.append({
            "workflow": wf,
            "final_b_mm": None if f is None else round(f.width_mm, 2),
            "final_h_mm": None if f is None else round(f.height_mm, 2),
            "ansys_mass_kg": None if f is None else round(f.mass_kg, 3),
            "ansys_deflection_mm": None if f is None else round(f.deflection_mm, 4),
            "ansys_stress_mpa": None if f is None else round(f.nominal_stress_mpa, 2),
            "ansys_feasible": None if f is None else f.feasible,
            "ansys_requests": int((ex.model_source == "ansys").sum()),
            "ansys_new_solves": int(((ex.model_source == "ansys") & (ex.cache_hit != True)).sum()),
            "python_runs": int((ex.model_source == "python").sum()),
            "invalid_proposals": int((g.row_type == "invalid_proposal").sum()),
            "tool_time_s": round(ex.elapsed_s.sum(), 1),
            "llm_time_s": round(g.drop_duplicates("iteration").llm_elapsed_s.sum(), 1),
        })
    t = pd.DataFrame(rows)
    t.to_csv(HERE / "team_logistics_comparison_table.csv", index=False)
    print(t.to_string(index=False))
    return t


def plot_progress(df):
    """Best mass so far that is feasible in the tool that evaluated it.
    If ANSYS evaluated a design, the ANSYS verdict overrides Python."""
    fig, ax = plt.subplots(figsize=(7, 4.3))
    for wf, g in df.groupby("workflow"):
        ex = g[(g.row_type == "tool_execution") & (g.phase == "search")]
        an = ex[ex.model_source == "ansys"]
        bad_in_ansys = {(r.width_mm, r.height_mm) for _, r in an.iterrows() if not bool(r.feasible)}
        best, xs, ys = np.inf, [], []
        for it in range(1, 11):
            for _, r in ex[(ex.iteration == it) & (ex.feasible == True)].iterrows():
                if r.model_source == "python" and (r.width_mm, r.height_mm) in bad_in_ansys:
                    continue
                best = min(best, r.mass_kg)
            xs.append(it)
            ys.append(best if np.isfinite(best) else np.nan)
        ax.step(xs, ys, where="post", marker="o", color=COLORS.get(wf), label="Workflow " + wf)
        fin = g[(g.row_type == "tool_execution") & (g.phase == "final")]
        if len(fin):
            f = fin.iloc[-1]
            ok = bool(f.feasible)
            xf = 11 + {"A": -0.3, "B": 0.3, "C": 0.0}.get(wf, 0)
            ax.scatter([xf], [f.mass_kg], marker="*" if ok else "X", s=200,
                       color=COLORS.get(wf) if ok else "white", edgecolor=COLORS.get(wf) if not ok else "k",
                       linewidth=1.5, zorder=5)
            ax.annotate("%s: %.2f kg, %s" % (wf, f.mass_kg, "ANSYS-feasible" if ok else "ANSYS-INFEASIBLE"),
                        (xf, f.mass_kg), xytext=({"A": -10, "B": 12, "C": 12}.get(wf, 0), {"A": 12, "B": -10, "C": 6}.get(wf, 0)),
                        textcoords="offset points", ha="right" if wf == "A" else "left", va="center", fontsize=7.5, color=COLORS.get(wf))
    ax.set_xlabel("Candidate iteration (11 = final recommendation, checked with the reserved ANSYS run)")
    ax.set_ylabel("Best feasible mass so far [kg]")
    ax.set_xticks(range(1, 12))
    ax.set_ylim(13.0, 19.2)
    ax.set_xlim(0.5, 13.6)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    ax.set_title("Search progress (ANSYS verdict overrides Python where both ran)")
    fig.tight_layout()
    fig.savefig(HERE / "team_logistics_plot_progress.png", dpi=200)


def plot_design_space(df):
    fig, (ax, az) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
    b = np.linspace(20, 100, 300)
    h_defl = (P * L ** 3 * 12 / (48 * E * b * 1.0)) ** (1 / 3)
    h_stress = np.sqrt(3 * P * L / (2 * b * 120.0))
    for a in (ax, az):
        a.plot(b, h_defl, "k-", lw=1.2, label="Python deflection limit")
        a.plot(b, h_stress, "k--", lw=1.0, label="Python stress limit")
        a.fill_between(b, np.maximum(h_defl, h_stress), 120, color="0.92")
        for m in [10, 13.5, 14, 20, 30, 40]:
            a.plot(b, m / (7.85e-6 * L * b), ":", color="0.65", lw=0.8)
    for m in [10, 20, 30]:
        ax.text(m / (7.85e-6 * L * 44.0), 44.0, " %d kg" % m, fontsize=7, color="0.4")
    for m, y in [(13.5, 84.4), (14, 84.4)]:
        az.text(m / (7.85e-6 * L * y), y, "%.1f kg" % m, fontsize=7, color="0.4", rotation=-60)
    # ANSYS deflection limit at b = 20 mm, from the A/C runs (linear between 86.2 and 86.5 mm)
    az.plot([19.88, 20.12], [86.40, 86.40], color="r", lw=2, zorder=2)
    az.text(20.13, 86.25, "ANSYS limit at b = 20\n(h ≈ 86.4 mm)", color="r", fontsize=7, va="center")
    offs = {"A": -0.06, "B": 0.0, "C": 0.06}
    ex = df[df.row_type == "tool_execution"]
    for wf, g in ex.groupby("workflow"):
        c = COLORS.get(wf)
        s = g[g.phase == "search"].drop_duplicates(["iteration", "model_source"])
        ax.scatter(s.width_mm, s.height_mm, s=18, color=c, label="Workflow %s" % wf, zorder=3)
        for src, mk in (("python", "o"), ("ansys", "s")):
            t = s[s.model_source == src]
            ok = t[t.feasible == True]
            nok = t[t.feasible != True]
            az.scatter(ok.width_mm + offs[wf], ok.height_mm, marker=mk, s=40, color=c, zorder=3)
            az.scatter(nok.width_mm + offs[wf], nok.height_mm, marker=mk, s=40, facecolor="white",
                       edgecolor=c, linewidth=1.3, zorder=3)
        f = g[g.phase == "final"]
        for a, o in ((ax, 0), (az, offs[wf])):
            a.scatter(f.width_mm + o, f.height_mm, marker="*", s=260, color=c, edgecolor="k", zorder=5)
    ax.set_xlim(19, 100); ax.set_ylim(40, 120)
    ax.set_xlabel("Width b [mm]"); ax.set_ylabel("Height h [mm]")
    ax.set_title("(a) Whole design space (grey = Python-feasible)")
    ax.legend(fontsize=7, loc="upper right")
    az.set_xlim(19.86, 21.25); az.set_ylim(84, 92.5)
    az.set_xlabel("Width b [mm]  (workflows offset ±0.06 mm for clarity)")
    az.set_ylabel("Height h [mm]")
    az.set_title("(b) Zoom at the optimum: circle = Python, square = ANSYS,\nfilled = feasible, hollow = infeasible, star = final")
    from matplotlib.lines import Line2D
    az.legend(handles=[Line2D([], [], color=COLORS[k], marker="s", ls="", label="Workflow " + k) for k in "ABC"],
              fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(HERE / "team_logistics_plot_design_space.png", dpi=200)


if __name__ == "__main__":
    d = load()
    comparison_table(d)
    plot_progress(d)
    plot_design_space(d)
    print("saved team_logistics_comparison_table.csv, team_logistics_plot_progress.png, team_logistics_plot_design_space.png")
