"""Task 2: failure handling test. Runs in seconds; ANSYS is NOT started.

Checks:
1. Out-of-bounds input -> status "error", no numbers, not cached.
2. A simulated ANSYS crash -> status "error", no numbers, labelled "ansys"
   (never a Python fallback), and nothing is cached.
3. After the crash, the same design is NOT served from the cache
   (no stale result): the next call tries ANSYS again.
4. A cached success is never returned for a different design.
"""
import ansys_tools as at
import beam_tools as bt

bt.reset_cache()
NUMS = ("mass_kg", "deflection_mm", "nominal_stress_mpa", "feasible")


def show(tag, r):
    print("%-28s status=%-6s source=%-6s cache_hit=%s numbers=%s error=%s" % (
        tag, r["status"], r["model_source"], r["cache_hit"],
        [r[k] for k in NUMS], (r.get("error") or "")[:70]))


# 1. Out of bounds
r = at.evaluate_ansys(150.0, 80.0)
show("1. out of bounds", r)
assert r["status"] == "error" and all(r[k] is None for k in NUMS)
assert len(bt._cache) == 0

# 2. Simulated crash: Workbench "starts", geometry update raises
calls = {"n": 0}


def fake_start():
    at._session.wb = object()


def crash(*a, **k):
    calls["n"] += 1
    raise RuntimeError("simulated ANSYS crash (UNAVAILABLE)")


at._session.start = fake_start
at._session.update_geometry = crash
r = at.evaluate_ansys(40.0, 90.0)
show("2. simulated crash", r)
assert r["status"] == "error" and r["model_source"] == "ansys"
assert all(r[k] is None for k in NUMS)
assert len(bt._cache) == 0, "failed result must not be cached"

# 3. Same design again: must try ANSYS again, not return a cached value
r = at.evaluate_ansys(40.0, 90.0)
show("3. retry same design", r)
assert calls["n"] == 2 and r["cache_hit"] is False

# 4. A cached success for one design is not reused for another design
good = bt.make_result("ansys", 50.0, 80.0, "ok", 1.0, False, mass_kg=31.4,
                      deflection_mm=0.501, nominal_stress_mpa=46.1,
                      ansys_mesh=at.ANSYS_MESH, project_version="test")
bt._cache[bt.cache_key("ansys", 50.0, 80.0, at.MODEL_VERSION, at.ANSYS_MESH,
                       at.ANSYS_LOAD, at.ANSYS_MATERIAL)] = good
r1 = at.evaluate_ansys(50.0, 80.0)
r2 = at.evaluate_ansys(50.0, 81.0)
show("4a. cached design", r1)
show("4b. different design", r2)
assert r1["cache_hit"] is True and r2["cache_hit"] is False and r2["mass_kg"] is None

print("\nALL FAILURE-HANDLING CHECKS PASSED")
