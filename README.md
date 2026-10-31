# Team Logistics — Beam Design with ANSYS and AI Agents (Part 1)

Minimum-mass design of a simply supported rectangular steel beam (L = 1000 mm, P = 10 kN at
midspan) with an AI agent that chooses designs and evaluation tools (fast Python beam theory or
a 3D ANSYS Mechanical model), under a Python controller that enforces bounds, permissions and
budgets.

## Team

- **Sai Suram**: code (Python–ANSYS integration, agent and controller, workflows, notebook, repository)
- **Alex**: ANSYS models (geometry, supports, load, mesh, probe, mesh study, screenshots)
- **Jaxson**: graphs (comparison plots and result figures)

Report: `team_logistics_beam_report.pdf`

## Requirements

- Windows, ANSYS 2026 R1 (Student is enough; the largest model used has about 117k nodes)
- Python 3.11+ and the packages in `requirements.txt`
- An OpenAI API key for the agent workflows only

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY = "sk-..."      # set in the shell only; never commit it
```

`PROJECT_FILE` and `CLIENT_WORKDIR` at the top of `ansys_tools.py` point to
`C:\beam_project\beam.wbpj`. Change them if the project is somewhere else.
The archive `team_logistics_beam.wbpz` restores the project (Workbench: File > Restore Archive).

## Before every ANSYS run

Workbench must be closed and the project unlocked:

```powershell
Get-Process | Where-Object { $_.Name -match "Ansys|AnsysFW|SpaceClaim|AnsysWBU|Mechanical|MAPDL" } | Stop-Process -Force
Get-ChildItem C:\beam_project -Recurse -Force -Filter "*.lock" | Remove-Item -Force
```

## Run order

| Step | Command | Time | Output |
|---|---|---|---|
| Task 1 model (one time, GUI) | SpaceClaim: run `beam_geometry_spaceclaim.py`; Mechanical: run `ansys_scripts/beam_mechanical_setup.py`, `ansys_scripts/beam_probe_setup.py` | – | `beam.wbpj` |
| Task 1 mesh study (GUI) | Mechanical: run `ansys_scripts/beam_mesh_study.py` | 2 min | `beam_mesh_study.csv` |
| Task 1 five designs | `python ansys_five_designs.py` | 20 min | `team_logistics_five_design_comparison.csv` |
| Task 2 smoke test | `python ansys_smoke_test.py` | 10 min | console log |
| Task 2 failure test | `python ansys_failure_test.py` | seconds (no ANSYS) | console log |
| Task 3/4 workflows | `python beam_agent.py --workflow A` (then `B`, `C`, or `all`) | A 45 min, B 6 min, C 25 min | `team_logistics_beam_results.csv`, `team_logistics_workflow_summary.json` |
| Task 4 comparison | `python beam_compare.py` | seconds | `team_logistics_comparison_table.csv`, `team_logistics_plot_progress.png`, `team_logistics_plot_design_space.png` |
| Task 4 mesh check | `python ansys_final_mesh_check.py` | 10–25 min | `team_logistics_final_mesh_check.csv` |
| Everything, from saved results | `team_logistics_beam_agent.ipynb` | seconds | tables and plots |

## Files

| File | Purpose |
|---|---|
| `beam_model.py` | Analytical model, provided, unchanged |
| `beam_tools.py` | `evaluate_python`, common result format, cache |
| `ansys_tools.py` | `evaluate_ansys`: persistent Workbench session, SpaceClaim geometry update, Mechanical mesh/solve/extract, checks |
| `beam_geometry_spaceclaim.py` | Parametric SpaceClaim geometry and named selections (also used by `ansys_tools.py`) |
| `ansys_scripts/` | Mechanical scripts run once in the GUI: `beam_mechanical_setup.py`, `beam_probe_setup.py`, `beam_mesh_study.py` |
| `screenshots/` | Task 1 screenshots (geometry, named selections, load, supports, mesh, results, reactions) |
| `logs/` | Smoke test and failure test console logs |
| `team_logistics_beam.wbpz` | Archived Workbench project |
| `beam_agent.py` | OpenAI agent, controller, budgets, CSV logging |
| `beam_compare.py` | Comparison table and two plots |
| `ansys_five_designs.py`, `ansys_smoke_test.py`, `ansys_failure_test.py`, `ansys_final_mesh_check.py` | Verification scripts |

## Design decisions

- **Common result format.** Both tools return `width_mm, height_mm, model_source, mass_kg,
  deflection_mm, nominal_stress_mpa, status, feasible, deflection_margin_mm, stress_margin_mpa,
  elapsed_s, cache_hit, evaluation_id, ansys_mesh, project_version, error`.
- **No stale or mislabelled results.** An ANSYS result is accepted only if the solve status is
  Done, the solved volume equals b·h·L (proves the geometry updated) and the reactions balance
  the load. Otherwise `status = "error"` and all numbers are `None`. Failures are not cached.
  There is no Python fallback inside `evaluate_ansys`.
- **Cache key** = tool, b, h, model version, mesh sizes, load case, material. Each workflow
  starts with an empty cache, for a fair comparison.
- **Startup time** (about 60 s) is reported separately and is not part of `elapsed_s`.
- **Geometry update** rebuilds the body in SpaceClaim. Mechanical then loses the body link of
  the material assignment, so the solve script deletes any stale "Structural Steel Assignment"
  object and assigns Structural Steel to the body before each solve.
- **Agent**: same model and prompt in all workflows; the workflow rules are given as data. A
  rejected proposal costs one iteration. One ANSYS run is reserved for the final check.

## Security

No API keys, `.env` files or virtual environments are in this repository (see `.gitignore`).
