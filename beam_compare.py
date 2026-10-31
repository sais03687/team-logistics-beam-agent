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
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for wf, g in df.groupby("workflow"):
        ex = g[(g.row_type == "tool_execution") & (g.phase == "search")]
        best, xs, ys = np.inf, [], []
        for it in range(1, 11):
            sub = ex[(ex.iteration == it) & (ex.feasible == True)]
            # in workflow C a design counts once ANSYS agrees, if ANSYS ran on it
            for _, r in sub.iterrows():
                same = ex[(ex.iteration == it) & (ex.model_source == "ansys")]
                if r.model_source == "python" and len(same) and not bool(same.iloc[0].feasible):
                    continue
                best = min(best, r.mass_kg)
            xs.append(it)
            ys.append(best if np.isfinite(best) else np.nan)
        ax.step(xs, ys, where="post", marker="o", color=COLORS.get(wf), label="Workflow " + wf)
        fin = g[(g.row_type == "tool_execution") & (g.phase == "final")]
        if len(fin):
            ax.scatter([11], [fin.iloc[-1].mass_kg], marker="*", s=180, color=COLORS.get(wf),
                       edgecolor="k", zorder=5)
    ax.set_xlabel("Candidate iteration (11 = final ANSYS confirmation)")
    ax.set_ylabel("Best feasible mass so far [kg]")
    ax.set_xticks(range(1, 12))
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Search progress by workflow")
    fig.tight_layout()
    fig.savefig(HERE / "team_logistics_plot_progress.png", dpi=200)


def plot_design_space(df):
    fig, ax = plt.subplots(figsize=(7, 5))
    b = np.linspace(20, 100, 200)
    h_defl = (P * L ** 3 * 12 / (48 * E * b * 1.0)) ** (1 / 3)
    h_stress = np.sqrt(3 * P * L / (2 * b * 120.0))
    ax.plot(b, h_defl, "k-", label="Python deflection limit (1.0 mm)")
    ax.plot(b, h_stress, "k--", label="Python stress limit (120 MPa)")
    ax.fill_between(b, np.maximum(h_defl, h_stress), 120, color="0.9", label="Python-feasible region")
    for m in [10, 20, 30, 40]:
        ax.plot(b, m / (7.85e-6 * L * b), ":", color="0.6", lw=0.8)
        bx = m / (7.85e-6 * L * 44.0)
        if 20 <= bx <= 100:
            ax.text(bx, 44.0, " %d kg" % m, fontsize=7, color="0.4")
    for wf, g in df.groupby("workflow"):
        v = g[g.proposal_valid == True].drop_duplicates(["iteration", "phase"])
        s = v[v.phase == "search"]
        ax.plot(s.proposed_width_mm, s.proposed_height_mm, "o-", ms=5, lw=0.8,
                color=COLORS.get(wf), alpha=0.8, label="Workflow %s proposals" % wf)
        f = v[v.phase == "final"]
        ax.scatter(f.proposed_width_mm, f.proposed_height_mm, marker="*", s=220,
                   color=COLORS.get(wf), edgecolor="k", zorder=5)
    ax.set_xlim(20, 100)
    ax.set_ylim(40, 120)
    ax.set_xlabel("Width b [mm]")
    ax.set_ylabel("Height h [mm]")
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title("Proposed designs (star = final recommendation)")
    fig.tight_layout()
    fig.savefig(HERE / "team_logistics_plot_design_space.png", dpi=200)


if __name__ == "__main__":
    d = load()
    comparison_table(d)
    plot_progress(d)
    plot_design_space(d)
    print("saved team_logistics_comparison_table.csv, team_logistics_plot_progress.png, team_logistics_plot_design_space.png")
