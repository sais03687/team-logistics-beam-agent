WIDTH_MM = 50.0
HEIGHT_MM = 80.0
SPAN_MM = 1000.0
STRIP_MM = 10.0

mm = 0.001
L = SPAN_MM * mm
b = WIDTH_MM * mm
h = HEIGHT_MM * mm
s = STRIP_MM * mm
x1 = L / 2.0 - s / 2.0
x2 = L / 2.0 + s / 2.0

# 1. Delete old bodies and named selections so reruns do not stack
part = GetRootPart()
for body in list(part.Bodies):
    body.Delete()
try:
    for grp in list(part.Groups):
        grp.Delete()
except:
    pass

# 2. Build three boxes (left, load strip, right), then merge into one solid
def make_box(xa, ya, za, xb, yb, zb):
    res = BlockBody.Create(Point.Create(xa, ya, za), Point.Create(xb, yb, zb), ExtrudeType.ForceIndependent, None)
    return res.CreatedBody

beam = make_box(0.0, 0.0, -b / 2.0, L, h, b / 2.0)
cutter = make_box(x1, h / 2.0, -b, x2, h + 0.01, b)
beam.Shape.Imprint(cutter.Shape)
cutter.Delete()

body = part.Bodies[0]
print("Faces: %d (need 8)" % body.Faces.Count)
body.Name = "Beam"
print("Bodies: %d" % part.Bodies.Count)

# 3. Find faces and edges by position
tol = 1e-6

def bbox(obj):
    bx = obj.Shape.GetBoundingBox(Matrix.Identity)
    return bx.MinCorner, bx.MaxCorner

def name_sel(items, name):
    sel = Selection.Create(items)
    res = NamedSelection.Create(sel, Selection.Empty())
    res.CreatedNamedSelection.Name = name

strip_faces = []
for f in body.Faces:
    lo, hi = bbox(f)
    on_top = abs(lo.Y - h) < tol and abs(hi.Y - h) < tol
    in_strip = abs(lo.X - x1) < tol and abs(hi.X - x2) < tol
    if on_top and in_strip:
        strip_faces.append(f)

pin_edges = []
roller_edges = []
for e in body.Edges:
    lo, hi = bbox(e)
    bottom = abs(lo.Y) < tol and abs(hi.Y) < tol
    along_z = abs(hi.Z - lo.Z) > b * 0.5
    if bottom and along_z and abs(lo.X) < tol and abs(hi.X) < tol:
        pin_edges.append(e)
    if bottom and along_z and abs(lo.X - L) < tol and abs(hi.X - L) < tol:
        roller_edges.append(e)

print("Load strip faces: %d (need 1)" % len(strip_faces))
print("Pin edges: %d (need 1)" % len(pin_edges))
print("Roller edges: %d (need 1)" % len(roller_edges))

if len(strip_faces) == 1:
    name_sel(strip_faces, "NS_LOAD_STRIP")
if len(pin_edges) == 1:
    name_sel(pin_edges, "NS_PIN_EDGE")
if len(roller_edges) == 1:
    name_sel(roller_edges, "NS_ROLLER_EDGE")

# 4. Keep view useful
ViewHelper.ZoomToEntity()
