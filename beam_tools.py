import itertools
import time

from beam_model import (
    evaluate_beam,
    MAX_DEFLECTION_MM,
    MAX_VON_MISES_STRESS_MPA,
    LOAD_N,
    ELASTIC_MODULUS_MPA,
)

PYTHON_MODEL_VERSION = "beam_model.py-v1"
LOAD_CASE = {"load_n": LOAD_N, "span_mm": 1000.0, "strip_mm": 0.0}
MATERIAL = {"e_mpa": ELASTIC_MODULUS_MPA, "density_kg_m3": 7850.0}

_cache = {}
_counter = itertools.count(1)


def reset_cache():
    _cache.clear()


def cache_key(model_source, width_mm, height_mm, model_version, mesh, load, material):
    return (
        model_source,
        round(float(width_mm), 6),
        round(float(height_mm), 6),
        model_version,
        tuple(sorted(mesh.items())),
        tuple(sorted(load.items())),
        tuple(sorted(material.items())),
    )


def make_result(model_source, width_mm, height_mm, status, elapsed_s, cache_hit,
                mass_kg=None, deflection_mm=None, nominal_stress_mpa=None,
                ansys_mesh=None, project_version=None, error=None):
    ok = status == "ok"
    return {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "model_source": model_source,
        "mass_kg": mass_kg if ok else None,
        "deflection_mm": deflection_mm if ok else None,
        "nominal_stress_mpa": nominal_stress_mpa if ok else None,
        "status": status,
        "feasible": (
            deflection_mm <= MAX_DEFLECTION_MM
            and nominal_stress_mpa <= MAX_VON_MISES_STRESS_MPA
        ) if ok else None,
        "deflection_margin_mm": (MAX_DEFLECTION_MM - deflection_mm) if ok else None,
        "stress_margin_mpa": (MAX_VON_MISES_STRESS_MPA - nominal_stress_mpa) if ok else None,
        "elapsed_s": elapsed_s,
        "cache_hit": cache_hit,
        "evaluation_id": next(_counter),
        "ansys_mesh": ansys_mesh,
        "project_version": project_version,
        "error": error,
    }


def evaluate_python(width_mm, height_mm):
    key = cache_key("python", width_mm, height_mm, PYTHON_MODEL_VERSION, {}, LOAD_CASE, MATERIAL)
    t0 = time.time()
    if key in _cache:
        cached = dict(_cache[key])
        cached["cache_hit"] = True
        cached["elapsed_s"] = time.time() - t0
        cached["evaluation_id"] = next(_counter)
        return cached
    try:
        out = evaluate_beam(width_mm, height_mm)
    except Exception as exc:
        return make_result("python", width_mm, height_mm, "error",
                           time.time() - t0, False, error=str(exc))
    result = make_result(
        "python", width_mm, height_mm, "ok", time.time() - t0, False,
        mass_kg=out["mass_kg"],
        deflection_mm=out["max_deflection_mm"],
        nominal_stress_mpa=out["max_von_mises_stress_MPa"],
    )
    _cache[key] = dict(result)
    return result
