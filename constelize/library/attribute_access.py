#constelize/library/attribute_access.py
import json
from typing import List, Tuple

import constelize.tools.globals as GLOBAL
from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory
from constelize.core.procedure import ActionInstance
from constelize.dsl.grid_dsl import Grid, to_concrete_grid

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

def select_sprite_and_attribute_fn(
    scenarioId: str,
    ruleId: str,
    criteria: List[Tuple[str, int]],
    attribute_name: str,
    trainId: int | None = None,
    testId: int | None = None
) -> int | None:
    """
    Return the attribute value of the sprite whose row best matches your criteria:
    for each sprite, count how many (attr, val) pairs it satisfies, pick the one
    with the highest count, and return its attribute_name. If none match anything,
    or no sprites pass the trainId/testId filter, return None.
    """
    sprite_tbl = GLOBAL.load_sprite_analysis_table(scenarioId, ruleId)

    best_sid = None
    best_score = -1

    for sid, row in sprite_tbl.items():
        # apply your train/test filtering
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId is not None and row.get("testId") != testId:
            continue

        # count how many criteria this row satisfies
        score = sum(1 for attr, val in criteria if row.get(attr) == val)
        if score > best_score:
            best_score = score
            best_sid = sid

    if best_sid is None or best_score <= 0:
        # either no candidate or nobody matched any criterion
        return None

    # debug info
    print(f"[BEST MATCH] sprite {best_sid} matched {best_score}/{len(criteria)} criteria "
          f"→ {attribute_name} = {sprite_tbl[best_sid].get(attribute_name)}")
    return sprite_tbl[best_sid].get(attribute_name)

def select_object_and_attribute_fn(
    scenarioId: str,
    ruleId: str,
    criteria: List[Tuple[str, int]],
    attribute_name: str,
    object_ids: List[int],
    trainId: int | None = None,
    testId: int | None = None
) -> int | None:
    """
    Return the attribute value of the first object matching all (attr, val) in criteria.
    Optionally filter by trainId, testId, or restrict to a given list of object_ids.
    If no match is found, return None.
    """
    object_tbl = GLOBAL.load_object_analysis_table(scenarioId, ruleId)

    print(f"select_object_and_attribute_fn trainId={trainId} testId={testId}")

    if testId == 0:
        print("select_object_and_attribute_fn")

    # 1) Try each single criterion in priority order:
    for single_attr, single_val in criteria:
        print(f"  Trying criterion: {single_attr} == {single_val}")
        for oid, row in object_tbl.items():
            if trainId is not None and row.get("trainId") != trainId:
                continue
            if testId is not None and row.get("testId") != testId:
                continue

            if row.get(single_attr) == single_val:
                print(f"[MATCH] object {oid} meets criterion {(single_attr, single_val)} → "
                      f"{attribute_name} = {row.get(attribute_name)}")
                return row.get(attribute_name)

    return None

def select_sprite_grid_fn(
    scenarioId: str,
    ruleId:     str,
    criteria:   List[Tuple[str, int]],
    trainId:    int | None = None,
    testId:     int | None = None
) -> Grid | None:
    """
    Find the first sprite_unique_id matching all (attr==val) in criteria,
    then load its raw pixel-list and convert it to a concrete Grid.
    """
    sprite_tbl = GLOBAL.load_sprite_analysis_table(scenarioId, ruleId)

    # 1) pick a sprite id
    chosen = None
    for sid, row in sprite_tbl.items():
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue
        if all(row.get(attr) == val for attr, val in criteria):
            chosen = sid
            break

    if chosen is None:
        return None

    # 2) grab its JSON-encoded data and convert
    raw = json.loads(sprite_tbl[chosen]["data"])
    return to_concrete_grid(raw)

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
            ArgumentBinding("trainId",        "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("testId",         "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("attribute_name", "String",  binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Integer",
        function=get_attribute_fn
    ),
    Action(
        id="select_sprite_and_attribute",
        name="Select & Get Sprite Attribute",
        description=(
            "Filter a list of sprites by a set of (attribute == value) criteria, "
            "and return the values of the specified numeric attribute for those sprites."
        ),
        category=ActionCategory.SELECTION_FILTERING,
        input_arguments=[
            ArgumentBinding("scenarioId",     "String", binding=BindingStatus.INSTANCE),
            ArgumentBinding("ruleId",         "String", binding=BindingStatus.INSTANCE),
            ArgumentBinding("trainId",        "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("testId",         "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("criteria",       "List[Tuple<String,Integer>]", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("attribute_name", "String", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("sprite_ids",     "List<Integer>", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Integer",
        function=select_sprite_and_attribute_fn
    ),
    Action(
        id="select_object_and_attribute",
        name="Select & Get Object Attribute",
        description=(
            "Filter a list of objects by a set of (attribute == value) criteria, "
            "and return the values of the specified numeric attribute for those objects."
        ),
        category=ActionCategory.SELECTION_FILTERING,
        input_arguments=[
            ArgumentBinding("scenarioId",     "String",                  binding=BindingStatus.INSTANCE),
            ArgumentBinding("ruleId",         "String",                  binding=BindingStatus.INSTANCE),
            ArgumentBinding("trainId",        "Integer",                 binding=BindingStatus.CONTEXT),
            ArgumentBinding("testId",         "Integer",                 binding=BindingStatus.CONTEXT),
            ArgumentBinding("criteria",       "List[Tuple<String,Integer>]", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("attribute_name", "String",                  binding=BindingStatus.UNRESOLVED),
            ArgumentBinding("object_ids",     "List<Integer>",           binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Integer",
        function=select_object_and_attribute_fn
    ),
    Action(
      id="select_sprite_grid",
      name="Select Sprite Grid",
      description=(
        "Filter a list of sprites by (attribute==value) criteria and return "
        "the full concrete grid of the first matching sprite."
      ),
      category=ActionCategory.SELECTION_FILTERING,
      input_arguments=[
        ArgumentBinding("scenarioId", "String",                       binding=BindingStatus.INSTANCE),
        ArgumentBinding("ruleId",     "String",                       binding=BindingStatus.INSTANCE),
        ArgumentBinding("trainId",    "Integer",                      binding=BindingStatus.CONTEXT),
        ArgumentBinding("testId",     "Integer",                      binding=BindingStatus.CONTEXT),
        ArgumentBinding("criteria",   "List[Tuple[String,Integer]]",  binding=BindingStatus.UNRESOLVED),
      ],
      output_type="Grid",
      function=select_sprite_grid_fn
    )
]
