import time
import os

MESH_SIZES_MM = [12.0, 8.0, 6.0]
STRIP_MESH_MM = 5.0

analysis = Model.Analyses[0]
solution = analysis.Solution


def get_one(name):
    found = DataModel.GetObjectsByName(name)
    if found.Count == 0:
        raise Exception("not found: " + name)
    return found[0]


def remove_old(name):
    for obj in list(DataModel.GetObjectsByName(name)):
        obj.Delete()


def add_reaction(name, support_name):
    remove_old(name)
    r = solution.AddForceReaction()
    r.Name = name
    r.LocationMethod = LocationDefinitionMethod.BoundaryCondition
    r.BoundaryConditionSelection = get_one(support_name)
    return r


pin_reaction = add_reaction("Pin Reaction", "Pin Support")
roller_reaction = add_reaction("Roller Reaction", "Roller Support")

deflection = get_one("Midspan Deflection")
nominal = get_one("Nominal Stress Probe")
global_stress = get_one("Global Equivalent Stress")
mesh = Model.Mesh
strip_sizing = get_one("Strip Sizing")

rows = []
header = "size_mm,strip_mm,nodes,elements,deflection_mm,nominal_stress_mpa,global_peak_mpa,pin_ry_n,roller_ry_n,solve_s"
print(header)

for size in MESH_SIZES_MM:
    strip = min(STRIP_MESH_MM, size)
    mesh.ElementSize = Quantity(size, "mm")
    strip_sizing.ElementSize = Quantity(strip, "mm")
    mesh.GenerateMesh()
    t0 = time.time()
    analysis.Solve(True)
    elapsed = time.time() - t0
    solution.EvaluateAllResults()
    defl_mm = abs(deflection.Minimum.Value) * 1000.0
    nominal_mpa = nominal.Average.Value / 1.0e6
    peak_mpa = global_stress.Maximum.Value / 1.0e6
    pin_ry = pin_reaction.YAxis.Value
    roller_ry = roller_reaction.YAxis.Value
    row = "%.1f,%.1f,%d,%d,%.5f,%.4f,%.4f,%.2f,%.2f,%.1f" % (
        size, strip, mesh.Nodes, mesh.Elements, defl_mm, nominal_mpa,
        peak_mpa, pin_ry, roller_ry, elapsed)
    rows.append(row)
    print(row)

path = os.path.join(os.path.expanduser("~"), "beam_mesh_study.csv")
f = open(path, "w")
f.write(header + "\n")
for row in rows:
    f.write(row + "\n")
f.close()
print("Saved: " + path)
