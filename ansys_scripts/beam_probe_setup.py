analysis = Model.Analyses[0]
solution = analysis.Solution


def step(name, fn):
    try:
        fn()
        print(name + ": OK")
    except Exception as e:
        print(name + ": FAILED - " + str(e))


def remove_old(name):
    for obj in list(DataModel.GetObjectsByName(name)):
        obj.Delete()


def add_probe_selection():
    remove_old("NS_NOMINAL_PROBE")
    ns = Model.AddNamedSelection()
    ns.Name = "NS_NOMINAL_PROBE"
    ns.ScopingMethod = GeometryDefineByType.Worksheet
    ns.GenerationCriteria.Add(None)
    ns.GenerationCriteria.Add(None)
    ns.GenerationCriteria.Add(None)

    c0 = ns.GenerationCriteria[0]
    c0.EntityType = SelectionType.MeshNode
    c0.Criterion = SelectionCriterionType.LocationX
    c0.Operator = SelectionOperatorType.RangeInclude
    c0.LowerBound = Quantity("0.495 [m]")
    c0.UpperBound = Quantity("0.505 [m]")

    c1 = ns.GenerationCriteria[1]
    c1.Action = SelectionActionType.Filter
    c1.EntityType = SelectionType.MeshNode
    c1.Criterion = SelectionCriterionType.LocationY
    c1.Operator = SelectionOperatorType.RangeInclude
    c1.LowerBound = Quantity("-0.00001 [m]")
    c1.UpperBound = Quantity("0.00001 [m]")

    c2 = ns.GenerationCriteria[2]
    c2.Action = SelectionActionType.Filter
    c2.EntityType = SelectionType.MeshNode
    c2.Criterion = SelectionCriterionType.LocationZ
    c2.Operator = SelectionOperatorType.RangeInclude
    c2.LowerBound = Quantity("-0.005 [m]")
    c2.UpperBound = Quantity("0.005 [m]")

    ns.Generate()


def add_probe_result():
    remove_old("Nominal Stress Probe")
    ns = DataModel.GetObjectsByName("NS_NOMINAL_PROBE")[0]
    eq = solution.AddEquivalentStress()
    eq.Name = "Nominal Stress Probe"
    eq.Location = ns


step("Probe selection", add_probe_selection)
step("Probe result", add_probe_result)
