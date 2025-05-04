#constelize/library/attribute_access.py

import constelize.tools.globals as GLOBAL
from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory
from constelize.core.procedure import ActionInstance

_values_by_input = {}
_attributes_by_input_and_values = {}
_colors_by_input = {}
_attributes_by_input_and_colors = {}

def height(piece) -> int:
    if isinstance(piece, tuple):
        return len(piece)
    return max(i for _, (i, j) in piece) - min(i for _, (i, j) in piece) + 1

def width(piece) -> int:
    if isinstance(piece, tuple):
        return len(piece[0])
    return max(j for _, (i, j) in piece) - min(j for _, (i, j) in piece) + 1

def shape(piece) -> tuple:
    return (height(piece), width(piece))

def color(obj) -> int:
    return next(iter(obj))[0] if obj else 0

def size(container) -> int:
    return len(container)

def get_start_input_fn(**kwargs):
    # In evaluation, if the grid is injected via a keyword (because its binding is INPUT_GRID),
    # simply return that value. Otherwise, fall back to the ActionInstance’s output_value.
    # (You may choose to prefer the externally injected grid over the stored output_value.)
    return kwargs.get("grid") or kwargs.get("output_value")

def get_attribute_fn(scenarioId: str, ruleId: str, binding_type: str, trainId: int, testId: int, attribute_name: str) -> int:
    """
    Retrieve a numeric attribute by trainId/testId
    using the pre‑computed attrs map in attribute_access.
    """
    key = f"{trainId}#{testId}"
    if binding_type == "Color":
        values_by_input = GLOBAL.get_colors_by_scenario_rule(scenarioId, ruleId)
    else:
        values_by_input = GLOBAL.get_values_by_scenario_rule(scenarioId, ruleId)
    return values_by_input.get(key, {}).get(attribute_name)
    #if(attribute_name == "first_sight_analysis.widthInput"):
    #    print("[ get_attribute_fn ]")
    #    print(f"scenarioId: {scenarioId}")
    #    print(f"ruleId: {ruleId}")
    #    print(f"trainId: {trainId}")
    #    print(f"testId: {testId}")
    #    print(f"attribute_name: {attribute_name}")
    #    print(f"return: {values_by_input.get(key, {}).get(attribute_name)}")

ACTIONS = [
    Action(
        id="get_start_input",
        name="Get Input Grid",
        description="Pass-through action for the input grid.",
        category=ActionCategory.ATTRIBUTE_ACCESS,  # or another appropriate category
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.INPUT_GRID)
        ],
        output_type="Grid",
        function=get_start_input_fn,
        deterministic=True,
        pure=True
    ),
    Action(
        id="get_height",
        name="Get Height",
        description="Returns the height of a grid or object.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="piece", type="Piece", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=height
    ),
    Action(
        id="get_width",
        name="Get Width",
        description="Returns the width of a grid or object.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="piece", type="Piece", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=width
    ),
    Action(
        id="get_shape",
        name="Get Shape",
        description="Returns the (height, width) of a grid or object.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="piece", type="Piece", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="IntegerTuple",
        function=shape
    ),
    Action(
        id="get_color",
        name="Get Color",
        description="Returns the color of an object.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="obj", type="Object", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=color
    ),
    Action(
        id="get_size",
        name="Get Size",
        description="Returns the number of elements in a container.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=size
    ),
    Action(
        id="get_attribute",
        name="Get Attribute",
        description="Retrieve a single numeric attribute by trainId/testId from first_sight_analysis.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding("scenarioId",     "String",  binding=BindingStatus.INSTANCE),
            ArgumentBinding("ruleId",         "String",  binding=BindingStatus.INSTANCE),
            ArgumentBinding("binding_type",   "String",  binding=BindingStatus.INSTANCE),
            ArgumentBinding("trainId",        "Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("testId",         "Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("attribute_name", "String",  binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=get_attribute_fn
    )
]
