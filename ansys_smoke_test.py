from beam_tools import evaluate_python
from ansys_tools import start_ansys, stop_ansys, evaluate_ansys

startup = start_ansys()
print("startup_s:", startup)

for dims in [(50, 80), (60, 100), (50, 80)]:
    py = evaluate_python(*dims)
    an = evaluate_ansys(*dims)
    print(dims)
    print("  python:", py["mass_kg"], py["deflection_mm"], py["nominal_stress_mpa"])
    print("  ansys :", an["status"], an["mass_kg"], an["deflection_mm"],
          an["nominal_stress_mpa"], "cache_hit:", an["cache_hit"],
          "elapsed_s:", an["elapsed_s"])
    if an["status"] != "ok":
        print("  error :", an["error"])

stop_ansys()
