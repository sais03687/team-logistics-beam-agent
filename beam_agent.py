"""AI agent and Python controller for the beam design study (Tasks 3 and 4).

The AI model only proposes candidates. This controller validates every
proposal, enforces tool permissions, bounds and budgets, runs the tools,
and logs one CSV row per tool execution (invalid proposals are kept).
No numerical optimizer generates candidates.

Usage:
    set OPENAI_API_KEY=...            (never commit the key)
    python beam_agent.py --workflow C
    python beam_agent.py --workflow all
"""
import argparse
import csv
import json
import os
import time
from pathlib import Path

import beam_tools as bt

WIDTH_BOUNDS = (20.0, 100.0)
HEIGHT_BOUNDS = (40.0, 120.0)
MAX_DEFLECTION_MM = 1.0
MAX_STRESS_MPA = 120.0
CANDIDATE_ITERATIONS = 10
RESULTS_CSV = Path(__file__).with_name("team_logistics_beam_results.csv")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")

WORKFLOWS = {
    "A": {"name": "ANSYS throughout", "allowed_tools": ["ansys"],
          "search_ansys_budget": CANDIDATE_ITERATIONS, "final_ansys": 1},
    "B": {"name": "Python search + one ANSYS check", "allowed_tools": ["python"],
          "search_ansys_budget": 0, "final_ansys": 1},
    "C": {"name": "Adaptive tool selection", "allowed_tools": ["python", "ansys", "both"],
          "search_ansys_budget": 5, "final_ansys": 1},
}

SYSTEM_PROMPT = """You are a structural design agent. You size a simply supported
rectangular steel beam: span 1000 mm, central downward load 10000 N, E = 200 GPa,
density 7850 kg/m^3. Design variables: width_mm in [20, 100], height_mm in [40, 120].
Goal: minimize mass. Constraints: midspan deflection <= 1.0 mm and nominal midspan
bottom-surface von Mises stress <= 120 MPa.

Two evaluation tools exist:
- "python": fast analytical beam theory (Euler-Bernoulli, no shear deformation).
- "ansys": slow 3D finite-element model (about 4 minutes), includes shear and 3D
  effects; usually gives a few percent larger deflection than "python".
- "both": runs both tools on the same design.

Engineering facts you may use: mass is proportional to b*h; deflection is
proportional to 1/(b*h^3); stress is proportional to 1/(b*h^2). For the same mass,
a narrower and taller section is stiffer and stronger, so explore BOTH variables,
including the bounds. Do not propose a design heavier than the lightest feasible
design already found unless you explain why it is needed. Do not repeat a design
that was already evaluated with the same tool. Use every iteration to learn
something new about where the constraint boundary is.

You only propose designs. A controller validates proposals and enforces the tool
permissions and budgets given in each message. A proposal with a forbidden tool,
an exhausted budget, or out-of-bounds dimensions is rejected and still uses up
one iteration. Use the evaluation history to reason about the next design.

Reply with one JSON object only, with exactly these keys:
{"width_mm": <number>, "height_mm": <number>, "tool": "<python|ansys|both>",
 "reason": "<one or two sentences>"}"""

FINAL_INSTRUCTION = """The search phase is over. Recommend the final design.
The controller confirms it with the one reserved ANSYS evaluation; the "tool"
field is ignored. Pick the lightest design you believe is feasible in ANSYS,
keeping a small margin if only the Python model supports it."""


class OpenAIAgent:
    """Same model and same system prompt for every workflow."""

    def __init__(self, model=MODEL):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model

    def propose(self, user_message):
        t0 = time.time()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user_message}],
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content
        usage = getattr(resp, "usage", None)
        tokens = usage.total_tokens if usage else None
        return text, time.time() - t0, tokens


def history_lines(history):
    if not history:
        return "No evaluations yet."
    lines = []
    for h in history:
        if h["status"] != "ok":
            lines.append("iter %s: %s (%.1f x %.1f) -> %s" % (
                h["iteration"], h["model_source"], h["width_mm"] or 0,
                h["height_mm"] or 0, h["status"]))
            continue
        lines.append("iter %s: %s b=%.2f h=%.2f mass=%.2f kg defl=%.4f mm stress=%.2f MPa feasible=%s" % (
            h["iteration"], h["model_source"], h["width_mm"], h["height_mm"],
            h["mass_kg"], h["deflection_mm"], h["nominal_stress_mpa"], h["feasible"]))
    return "\n".join(lines)


def build_message(wf, iteration, ansys_left, history, final=False):
    parts = [
        "Workflow %s (%s)." % (wf["key"], wf["name"]),
        "Allowed tools: %s." % ", ".join(wf["allowed_tools"]),
        "ANSYS search evaluations left: %d (one more ANSYS run is reserved for the final check)." % ansys_left,
        "Candidate iteration %d of %d." % (iteration, CANDIDATE_ITERATIONS),
        "Evaluation history:\n" + history_lines(history),
    ]
    if final:
        parts.append(FINAL_INSTRUCTION)
    return "\n".join(parts)


def validate(text, wf, ansys_left, final=False):
    """Return (proposal, error). The controller decides; the agent never does."""
    try:
        p = json.loads(text)
    except Exception:
        return None, "reply is not valid JSON"
    if not isinstance(p, dict):
        return None, "reply is not a JSON object"
    missing = [k for k in ("width_mm", "height_mm", "tool", "reason") if k not in p]
    if missing:
        return p, "missing keys: " + ", ".join(missing)
    try:
        b = float(p["width_mm"])
        h = float(p["height_mm"])
    except (TypeError, ValueError):
        return p, "width_mm/height_mm are not numbers"
    if b != b or h != h:
        return p, "dimension is NaN"
    p["width_mm"], p["height_mm"] = b, h
    if not (WIDTH_BOUNDS[0] <= b <= WIDTH_BOUNDS[1]):
        return p, "width_mm %.3f outside %s" % (b, WIDTH_BOUNDS)
    if not (HEIGHT_BOUNDS[0] <= h <= HEIGHT_BOUNDS[1]):
        return p, "height_mm %.3f outside %s" % (h, HEIGHT_BOUNDS)
    if final:
        p["tool"] = "ansys"
        return p, None
    tool = str(p["tool"]).lower().strip()
    p["tool"] = tool
    if tool not in ("python", "ansys", "both"):
        return p, "unknown tool %r" % tool
    if tool not in wf["allowed_tools"]:
        return p, "tool %r not permitted in workflow %s" % (tool, wf["key"])
    if tool in ("ansys", "both") and ansys_left <= 0:
        return p, "ANSYS search budget exhausted"
    return p, None


CSV_FIELDS = [
    "workflow", "iteration", "phase", "row_type", "proposal_valid", "rejection_reason",
    "proposed_width_mm", "proposed_height_mm", "proposed_tool", "agent_reason",
    "llm_model", "llm_elapsed_s", "llm_tokens",
    "width_mm", "height_mm", "model_source", "mass_kg", "deflection_mm",
    "nominal_stress_mpa", "status", "feasible", "deflection_margin_mm",
    "stress_margin_mpa", "elapsed_s", "cache_hit", "evaluation_id",
    "ansys_mesh", "project_version", "error", "timestamp",
]


class Logger:
    def __init__(self, path):
        self.path = Path(path)
        new = not self.path.exists()
        self.f = open(self.path, "a", newline="")
        self.w = csv.DictWriter(self.f, fieldnames=CSV_FIELDS)
        if new:
            self.w.writeheader()

    def row(self, **kw):
        kw["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(kw.get("ansys_mesh"), dict):
            kw["ansys_mesh"] = json.dumps(kw["ansys_mesh"])
        self.w.writerow({k: kw.get(k) for k in CSV_FIELDS})
        self.f.flush()

    def close(self):
        self.f.close()


def run_workflow(key, agent, evaluate_ansys, logger, model_name=MODEL):
    wf = dict(WORKFLOWS[key], key=key)
    ansys_left = wf["search_ansys_budget"]
    history = []
    counts = {"python": 0, "ansys": 0, "invalid": 0}
    t_start = time.time()

    def execute(tool_name, b, h, iteration, phase, base):
        fn = bt.evaluate_python if tool_name == "python" else evaluate_ansys
        r = fn(b, h)
        if r["model_source"] != tool_name:
            raise RuntimeError("tool mislabel: asked %s got %s" % (tool_name, r["model_source"]))
        counts[tool_name] += 1
        logger.row(row_type="tool_execution", **base, **r)
        history.append(dict(r, iteration=iteration))
        return r

    for it in range(1, CANDIDATE_ITERATIONS + 1):
        msg = build_message(wf, it, ansys_left, history)
        try:
            text, llm_s, tokens = agent.propose(msg)
        except Exception as exc:
            text, llm_s, tokens = "", 0.0, None
            prop, err = None, "agent call failed: %s" % exc
        else:
            prop, err = validate(text, wf, ansys_left)
        base = dict(workflow=key, iteration=it, phase="search", llm_model=model_name,
                    llm_elapsed_s=round(llm_s, 3), llm_tokens=tokens,
                    proposed_width_mm=(prop or {}).get("width_mm"),
                    proposed_height_mm=(prop or {}).get("height_mm"),
                    proposed_tool=(prop or {}).get("tool"),
                    agent_reason=(prop or {}).get("reason", text[:300] if err else None))
        if err:
            counts["invalid"] += 1
            logger.row(row_type="invalid_proposal", proposal_valid=False,
                       rejection_reason=err, status="rejected", **base)
            history.append({"iteration": it, "model_source": "rejected",
                            "width_mm": base["proposed_width_mm"] if isinstance(base["proposed_width_mm"], float) else None,
                            "height_mm": base["proposed_height_mm"] if isinstance(base["proposed_height_mm"], float) else None,
                            "status": "rejected: " + err})
            print("[%s %2d] REJECTED: %s" % (key, it, err), flush=True)
            continue
        base["proposal_valid"] = True
        tools = ["python", "ansys"] if prop["tool"] == "both" else [prop["tool"]]
        if "ansys" in tools:
            ansys_left -= 1
        for t in tools:
            r = execute(t, prop["width_mm"], prop["height_mm"], it, "search", base)
            print("[%s %2d] %-6s b=%6.2f h=%6.2f mass=%s defl=%s stress=%s feas=%s" % (
                key, it, t, prop["width_mm"], prop["height_mm"], r["mass_kg"],
                r["deflection_mm"], r["nominal_stress_mpa"], r["feasible"]), flush=True)

    # Final recommendation, confirmed with the reserved ANSYS evaluation.
    msg = build_message(wf, CANDIDATE_ITERATIONS, ansys_left, history, final=True)
    final = None
    try:
        text, llm_s, tokens = agent.propose(msg)
        prop, err = validate(text, wf, ansys_left, final=True)
    except Exception as exc:
        text, llm_s, tokens, prop, err = "", 0.0, None, None, "agent call failed: %s" % exc
    base = dict(workflow=key, iteration=CANDIDATE_ITERATIONS + 1, phase="final",
                llm_model=model_name, llm_elapsed_s=round(llm_s, 3), llm_tokens=tokens,
                proposed_width_mm=(prop or {}).get("width_mm"),
                proposed_height_mm=(prop or {}).get("height_mm"),
                proposed_tool="ansys", agent_reason=(prop or {}).get("reason"))
    if err:
        counts["invalid"] += 1
        logger.row(row_type="invalid_proposal", proposal_valid=False,
                   rejection_reason=err, status="rejected", **base)
        print("[%s final] REJECTED: %s" % (key, err), flush=True)
    else:
        base["proposal_valid"] = True
        final = execute("ansys", prop["width_mm"], prop["height_mm"],
                        CANDIDATE_ITERATIONS + 1, "final", base)
        print("[%s final] ANSYS b=%.2f h=%.2f mass=%s defl=%s stress=%s feas=%s" % (
            key, prop["width_mm"], prop["height_mm"], final["mass_kg"],
            final["deflection_mm"], final["nominal_stress_mpa"], final["feasible"]), flush=True)

    return {"workflow": key, "name": wf["name"], "final": final, "counts": counts,
            "wall_s": time.time() - t_start}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", default="all", choices=["A", "B", "C", "all"])
    ap.add_argument("--csv", default=str(RESULTS_CSV))
    args = ap.parse_args()
    import ansys_tools as at
    agent = OpenAIAgent()
    logger = Logger(args.csv)
    summaries = []
    try:
        startup = at.start_ansys()
        print("ANSYS startup_s: %.1f (not counted in tool elapsed times)" % startup)
        keys = ["A", "B", "C"] if args.workflow == "all" else [args.workflow]
        for k in keys:
            bt.reset_cache()   # each workflow starts with an empty cache: fair comparison
            summaries.append(run_workflow(k, agent, at.evaluate_ansys, logger))
    finally:
        logger.close()
        at.stop_ansys()
    out = Path(args.csv).with_name("team_logistics_workflow_summary.json")
    old = json.loads(out.read_text()) if out.exists() else {}
    for s in summaries:
        old[s["workflow"]] = s
    out.write_text(json.dumps(old, indent=1, default=str))
    print("summary written to", out)


if __name__ == "__main__":
    main()
