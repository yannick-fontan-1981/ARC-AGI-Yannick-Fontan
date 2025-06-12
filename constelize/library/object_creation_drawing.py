from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory
from constelize.dsl.grid_dsl import fill_grid, apply_all_cycles, apply_ca, select_conditional_object


def canvas(value: int, dimensions: tuple) -> tuple:
    return tuple(tuple(value for _ in range(dimensions[1])) for _ in range(dimensions[0]))

def box(patch) -> frozenset:
    if not patch:
        return frozenset()
    rows = [i for _, (i, j) in patch]
    cols = [j for _, (i, j) in patch]
    si, ei = min(rows), max(rows)
    sj, ej = min(cols), max(cols)
    return frozenset(
        (i, j)
        for i in range(si, ei + 1)
        for j in range(sj, ej + 1)
        if i in {si, ei} or j in {sj, ej}
    )

def fill(grid: tuple, value: int, patch) -> tuple:
    h, w = len(grid), len(grid[0])
    filled = [list(row) for row in grid]
    for i, j in patch:
        if 0 <= i < h and 0 <= j < w:
            filled[i][j] = value
    return tuple(tuple(row) for row in filled)

ACTIONS = [
    Action(
        id="canvas#object_creation",
        name="canvas",
        description="Create a new grid with given dimensions and fill value",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="value", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="dimensions", type="IntegerTuple", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=canvas
    ),
    Action(
        id="box#object_creation",
        name="box",
        description="Return the bounding box outline of a patch or object",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="patch", type="Grid", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Indices",
        function=box
    ),
    Action(
        id="fill#object_creation",
        name="fill",
        description="Fill a grid at given indices with a value",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="value", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="patch", type="Grid", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=fill
    ),
    Action(
        id="create_object",
        name="create_object",
        description="Fill the object mask with its color to produce the output grid.",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="mask", type="Grid", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="color", type="Color", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=fill_grid
    ),
    Action(
        id="apply_light_cycles",
        name="apply_light_cycles",
        description="Apply all detected light cycles to the input grid, producing the output grid.",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="input_grid",    type="Grid",  binding=BindingStatus.INPUT_GRID),
            ArgumentBinding(name="light_cycles",  type="List",  binding=BindingStatus.CONSTANT)
        ],
        output_type="Grid",
        function=apply_all_cycles
    ),
    Action(
        id="apply_cellular_automaton",
        name="apply_cellular_automaton",
        description="Apply all detected cellular automaton rules to the input grid, producing the output grid.",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="input_grid", type="Grid", binding=BindingStatus.INPUT_GRID),
            ArgumentBinding(name="ca_rules",   type="List", binding=BindingStatus.CONSTANT)
        ],
        output_type="Grid",
        function=apply_ca
    ),
    Action(
        id="conditional_objects",
        name="conditional_objects",
        description="Selects the conditional object matching criteria and renders its grid.",
        category=ActionCategory.OBJECT_CREATION_DRAWING,
        input_arguments=[
            ArgumentBinding(name="trainId",            type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="testId",             type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="conditionalObjects", type="List",    binding=BindingStatus.CONSTANT),
            ArgumentBinding(name="tables",             type="Tables",  binding=BindingStatus.CONSTANT)
        ],
        output_type="Grid",
        function=select_conditional_object,
        deterministic=True,
        pure=True,
        reversible=False
    )
]