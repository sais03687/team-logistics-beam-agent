SEARCH_MESH_MM = 10.0
STRIP_MESH_MM = 5.0

analysis = Model.Analyses[0]
solution = analysis.Solution


def step(name, fn):
    try:
        fn()
        print(name + ": OK")
    except Exception as e:
        print(name + ": FAILED - " + str(e))


def get_ns(name):
    found = DataModel.GetObjectsByName(name)
    if found.Count == 0:
        raise Exception("named selection not found: " + name)
    return found[0]


def remove_old(name):
    for obj in list(DataModel.GetObjectsByName(name)):
        obj.Delete()


def set_material():
    bodies = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)
    for body in bodies:
        body.Material = "Structural Steel"


def add_pin():
    remove_old("Pin Support")
    d = analysis.AddDisplacement()
    d.Name = "Pin Support"
    d.Location = get_ns("NS_PIN_EDGE")
    d.XComponent.Output.DiscreteValues = [Quantity("0 [mm]")]
    d.YComponent.Output.DiscreteValues = [Quantity("0 [mm]")]
    d.ZComponent.Output.DiscreteValues = [Quantity("0 [mm]")]


def add_roller():
    remove_old("Roller Support")
    d = analysis.AddDisplacement()
    d.Name = "Roller Support"
    d.Location = get_ns("NS_ROLLER_EDGE")
    d.YComponent.Output.DiscreteValues = [Quantity("0 [mm]")]


def add_load():
    remove_old("Load 10 kN")
    f = analysis.AddForce()
    f.Name = "Load 10 kN"
    f.Location = get_ns("NS_LOAD_STRIP")
    f.DefineBy = LoadDefineBy.Components
    f.YComponent.Output.DiscreteValues = [Quantity("-10000 [N]")]


def set_mesh():
    mesh = Model.Mesh
    remove_old("Strip Sizing")
    mesh.ElementSize = Quantity(SEARCH_MESH_MM, "mm")
    sizing = mesh.AddSizing()
    sizing.Name = "Strip Sizing"
    sizing.Location = get_ns("NS_LOAD_STRIP")
    sizing.ElementSize = Quantity(STRIP_MESH_MM, "mm")
    mesh.GenerateMesh()
    print("Nodes: %d  Elements: %d" % (mesh.Nodes, mesh.Elements))


def add_results():
    remove_old("Midspan Deflection")
    remove_old("Global Equivalent Stress")
    dd = solution.AddDirectionalDeformation()
    dd.Name = "Midspan Deflection"
    dd.NormalOrientation = NormalOrientationType.YAxis
    eq = solution.AddEquivalentStress()
    eq.Name = "Global Equivalent Stress"


step("Material", set_material)
step("Pin support", add_pin)
step("Roller support", add_roller)
step("Load", add_load)
step("Mesh", set_mesh)
step("Results", add_results)
