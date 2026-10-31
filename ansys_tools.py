import json
import re
import time
import traceback
from pathlib import Path

from ansys.mechanical.core import connect_to_mechanical
from ansys.workbench.core import launch_workbench

import beam_tools as bt

PROJECT_FILE = r"C:\beam_project\beam.wbpj"
CLIENT_WORKDIR = r"C:\beam_project"
GEOMETRY_SCRIPT = Path(__file__).with_name("beam_geometry_spaceclaim.py")
WB_VERSION = "261"
SEARCH_MESH_MM = 8.0
STRIP_MESH_MM = 5.0
MODEL_VERSION = "beam-ansys-v1"
DENSITY_KG_M3 = 7850.0
SPAN_M = 1.0

ANSYS_MESH = {"search_mesh_mm": SEARCH_MESH_MM, "strip_mesh_mm": STRIP_MESH_MM}
ANSYS_LOAD = {"load_n": 10000.0, "span_mm": 1000.0, "strip_mm": 10.0}
ANSYS_MATERIAL = {"e_mpa": 200000.0, "density_kg_m3": DENSITY_KG_M3, "nu": 0.3}

MECHANICAL_SCRIPT = """
import json
material_note = ""
try:
    for ma in list(DataModel.GetObjectsByName("Structural Steel Assignment")):
        ma.Delete()
except Exception as e:
    material_note = "delete assignment failed: " + str(e) + "; "
try:
    for bdy in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
        bdy.Material = "Structural Steel"
    material_note += "assigned: " + str(Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0].Material)
except Exception as e:
    material_note += "material failed: " + str(e)
mesh = Model.Mesh
mesh.ElementSize = Quantity(__MESH__, "mm")
strip = DataModel.GetObjectsByName("Strip Sizing")[0]
strip.ElementSize = Quantity(__STRIP__, "mm")
mesh.GenerateMesh()
probe_note = ""
try:
    nsp = DataModel.GetObjectsByName("NS_NOMINAL_PROBE")[0]
    nsp.Generate()
    probe_note = "probe regenerated; ids: " + str(nsp.Location.Ids.Count)
except Exception as e:
    probe_note = "probe regenerate failed: " + str(e)
analysis = Model.Analyses[0]
analysis.Solve(True)
solution = analysis.Solution
status = str(solution.Status)
first_status = status
retry_note = ""
if "Done" not in status:
    try:
        solution.Solve(True)
        status = str(solution.Status)
        retry_note = "retried solution.Solve; status now " + status
    except Exception as e:
        retry_note = "retry raised: " + str(e)
out = {"solution_status": status}
msgs = []
try:
    for m in ExtAPI.Application.Messages:
        msgs.append(str(m.Severity) + ": " + str(m.DisplayString))
except Exception as e:
    msgs.append("could not read messages: " + str(e))
out["messages"] = msgs[-8:]
out["first_status"] = first_status
out["retry_note"] = retry_note
detail = []
try:
    for m in ExtAPI.Application.Messages:
        if "Error" in str(m.Severity):
            d = {}
            for n in dir(m):
                if n.startswith("_"):
                    continue
                try:
                    v = getattr(m, n)
                    if isinstance(v, (str, int, float, bool)) or "Enum" in type(v).__name__ or "Severity" in type(v).__name__:
                        d[n] = str(v)[:200]
                except Exception:
                    pass
            detail.append(d)
except Exception as e:
    detail.append({"error": str(e)})
out["error_detail"] = detail[-2:]
try:
    si = DataModel.GetObjectsByName("Solution Information")[0]
    out["solution_info_attrs"] = [n for n in dir(si) if "olver" in n or "utput" in n]
except Exception as e:
    out["solution_info_attrs"] = ["error: " + str(e)]
out["analysis_state"] = str(analysis.ObjectState)
out["probe_note"] = probe_note
out["material_note"] = material_note
child_states = {}
try:
    for c in solution.Children:
        child_states[c.Name] = str(c.ObjectState)
except Exception as e:
    child_states["error"] = str(e)
out["solution_children"] = child_states
try:
    import os
    wd = str(analysis.WorkingDir)
    out["working_dir"] = wd
    files = os.listdir(wd)
    out["files"] = files[:40]
    tails = {}
    for fn in files:
        low = fn.lower()
        if low in ("solve.out", "file.err") or low.endswith(".err") or low.endswith(".out"):
            try:
                f = open(os.path.join(wd, fn))
                txt = f.read()
                f.close()
                tails[fn] = txt[-1200:]
            except Exception as e:
                tails[fn] = "read error: " + str(e)
    out["solver_files"] = tails
except Exception as e:
    out["solver_files"] = "error: " + str(e)
states = {}
for nm in ["Pin Support", "Roller Support", "Load 10 kN", "Strip Sizing"]:
    try:
        states[nm] = str(DataModel.GetObjectsByName(nm)[0].ObjectState)
    except Exception as e:
        states[nm] = "error: " + str(e)
out["object_states"] = states
out["mesh_nodes"] = mesh.Nodes
if "Done" in status:
    solution.EvaluateAllResults()
    body = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0]
    deflection = DataModel.GetObjectsByName("Midspan Deflection")[0]
    nominal = DataModel.GetObjectsByName("Nominal Stress Probe")[0]
    pin = DataModel.GetObjectsByName("Pin Reaction")[0]
    roller = DataModel.GetObjectsByName("Roller Reaction")[0]
    out["volume_m3"] = body.Volume.Value
    out["deflection_mm"] = abs(deflection.Minimum.Value) * 1000.0
    out["nominal_stress_mpa"] = nominal.Average.Value / 1.0e6
    out["pin_ry_n"] = pin.YAxis.Value
    out["roller_ry_n"] = roller.YAxis.Value
    out["nodes"] = mesh.Nodes
    out["elements"] = mesh.Elements
json.dumps(out)
"""


def _geometry_script_text(width_mm, height_mm):
    text = GEOMETRY_SCRIPT.read_text()
    text = re.sub(r"^WIDTH_MM = .*$", "WIDTH_MM = %r" % float(width_mm), text, flags=re.M)
    text = re.sub(r"^HEIGHT_MM = .*$", "HEIGHT_MM = %r" % float(height_mm), text, flags=re.M)
    text = re.sub(r"^ViewHelper\..*$", "", text, flags=re.M)
    return text


class AnsysSession:
    def __init__(self):
        self.wb = None
        self.mech = None
        self.geom_dims = None
        self.startup_s = None

    def start(self):
        if self.wb is not None:
            return
        t0 = time.time()
        self.wb = launch_workbench(show_gui=False, version=WB_VERSION,
                                   client_workdir=CLIENT_WORKDIR)
        self.wb.run_script_string('Open(FilePath=r"%s")' % PROJECT_FILE)
        self.startup_s = time.time() - t0

    def reset(self):
        self.wb = None
        self.mech = None
        self.geom_dims = None

    def stop(self):
        if self.wb is None:
            return
        try:
            self.wb.run_script_string("Save(Overwrite=True)")
        except Exception as exc:
            print("  save failed: %s" % exc, flush=True)
        try:
            self.wb.exit()
        except Exception as exc:
            print("  exit failed: %s" % exc, flush=True)
        self.reset()

    def update_geometry(self, width_mm, height_mm):
        script = _geometry_script_text(width_mm, height_mm)
        journal = (
            'system1 = GetSystem(Name="SYS")\n'
            'geometry1 = system1.GetContainer(ComponentName="Geometry")\n'
            'geometry1.Edit(IsSpaceClaimGeometry=True)\n'
            "geometry1.SendCommand(Language=\"Python\", Command='''" + script + "''')\n"
            'geometry1.Exit()\n'
            'model1 = system1.GetComponent(Name="Model")\n'
            'model1.Refresh()\n'
        )
        self.wb.run_script_string(journal)

    def mechanical(self):
        if self.mech is None:
            port = self.wb.start_mechanical_server(system_name="SYS")
            self.mech = connect_to_mechanical(ip="localhost", port=port)
        return self.mech

    def solve_in_mechanical(self, mesh_mm=SEARCH_MESH_MM, strip_mm=STRIP_MESH_MM):
        script = (MECHANICAL_SCRIPT
                  .replace("__MESH__", repr(float(mesh_mm)))
                  .replace("__STRIP__", repr(float(strip_mm))))
        try:
            raw = self.mechanical().run_python_script(script)
        except Exception as exc:
            if "UNAVAILABLE" not in str(exc):
                raise
            print("  Mechanical closed after geometry update; reconnecting", flush=True)
            self.mech = None
            raw = self.mechanical().run_python_script(script)
        short = json.loads(raw)
        short.pop("solver_files", None)
        print("  mechanical returned: " + json.dumps(short)[:800], flush=True)
        return json.loads(raw)


_session = AnsysSession()


def start_ansys():
    _session.start()
    return _session.startup_s


def stop_ansys():
    _session.stop()


def evaluate_ansys(width_mm, height_mm, mesh_mm=None):
    """Evaluate one design in ANSYS. mesh_mm=None uses the search mesh (8 mm)."""
    mesh_mm = float(mesh_mm or SEARCH_MESH_MM)
    strip_mm = min(STRIP_MESH_MM, mesh_mm)
    mesh_info = {"search_mesh_mm": mesh_mm, "strip_mesh_mm": strip_mm}
    key = bt.cache_key("ansys", width_mm, height_mm, MODEL_VERSION,
                       mesh_info, ANSYS_LOAD, ANSYS_MATERIAL)
    t0 = time.time()
    if key in bt._cache:
        cached = dict(bt._cache[key])
        cached["cache_hit"] = True
        cached["elapsed_s"] = time.time() - t0
        cached["evaluation_id"] = next(bt._counter)
        return cached
    project_version = "Workbench " + WB_VERSION
    try:
        if not (20.0 <= width_mm <= 100.0 and 40.0 <= height_mm <= 120.0):
            raise ValueError("dimensions outside design bounds")
        print("  [1/3] starting or reusing Workbench session", flush=True)
        _session.start()
        if _session.geom_dims == (float(width_mm), float(height_mm)):
            print("  [2/3] geometry already %g x %g mm; no rebuild" % (width_mm, height_mm), flush=True)
        else:
            print("  [2/3] rebuilding geometry in SpaceClaim and refreshing model", flush=True)
            _session.geom_dims = None
            _session.update_geometry(width_mm, height_mm)
        print("  [3/3] meshing (%.1f mm, strip %.1f mm) and solving in Mechanical" % (mesh_mm, strip_mm), flush=True)
        out = _session.solve_in_mechanical(mesh_mm, strip_mm)
        print("  solve finished in %.0f s" % (time.time() - t0), flush=True)
        if "Done" not in out.get("solution_status", ""):
            raise RuntimeError("solve not done: " + out.get("solution_status", "unknown"))
        expected_volume = (width_mm / 1000.0) * (height_mm / 1000.0) * SPAN_M
        if abs(out["volume_m3"] - expected_volume) / expected_volume > 1e-3:
            raise RuntimeError("geometry did not update: volume %.6g vs expected %.6g"
                               % (out["volume_m3"], expected_volume))
        if abs(out["pin_ry_n"] + out["roller_ry_n"] - 10000.0) > 100.0:
            raise RuntimeError("reactions do not balance the load")
        mass_kg = out["volume_m3"] * DENSITY_KG_M3
        _session.geom_dims = (float(width_mm), float(height_mm))
    except Exception as exc:
        _session.geom_dims = None
        if "UNAVAILABLE" in str(exc) or "Connection" in str(exc):
            print("  ANSYS connection lost; session will restart on next call", flush=True)
            _session.reset()
        return bt.make_result("ansys", width_mm, height_mm, "error",
                              time.time() - t0, False,
                              ansys_mesh=mesh_info, project_version=project_version,
                              error="%s: %s" % (type(exc).__name__, exc))
    result = bt.make_result(
        "ansys", width_mm, height_mm, "ok", time.time() - t0, False,
        mass_kg=mass_kg,
        deflection_mm=out["deflection_mm"],
        nominal_stress_mpa=out["nominal_stress_mpa"],
        ansys_mesh=dict(mesh_info, nodes=out["nodes"], elements=out["elements"]),
        project_version=project_version,
    )
    bt._cache[key] = dict(result)
    return result
