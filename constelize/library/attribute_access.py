#constelize/library/attribute_access.py
import json
from typing import List, Tuple, Any, Optional

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
    criteria: List[Tuple[str, Any]],
    attribute_name: str,
    trainId:    int | None = None,
    testId:     int | None = None
) -> Optional[int]:
    """
    Return the attribute value of the object whose row best matches your criteria,
    giving a big bonus to matching sizeOrder.
    """
    object_tbl = GLOBAL.load_object_analysis_table(scenarioId, ruleId)

    print(f"select_object_and_attribute_fn trainId={trainId} testId={testId}")

    best_row: dict[str, Any] | None = None
    best_score = -1

    # 1) Scan every object_analysis row
    for row in object_tbl.values():
        # 2) Filter by train/test
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue

        # 3) Score it by how many criteria it matches,
        #    but give +10 points for sizeOrder matches
        score = 0
        for attr, val in criteria:
            if row.get(attr) == val:
                if attr == "sizeOrder" or attr == "isColorUnique":
                    score += 5
                else:
                    score += 1

        if score > best_score:
            best_score = score
            best_row   = row

    # 4) If nothing matched, bail out
    if best_row is None or best_score <= 0:
        print("  ⚠️ No object passes any criterion → returning None")
        return None

    # 5) Otherwise return the desired attribute
    result = best_row.get(attribute_name)
    print(f"[BEST MATCH] score={best_score} (of max {10 if any(a=='sizeOrder' for a,_ in criteria) else len(criteria)}) → "
          f"{attribute_name} = {result}")
    return result



def select_sprite_grid_fn(
    scenarioId: str,
    ruleId:     str,
    criteria:   List[Tuple[str, int]],
    trainId:    int | None = None,
    testId:     int | None = None
) -> Grid | None:
    """
    Find the sprite whose row maximizes the number of (attr==val) hits in `criteria`,
    then load its raw pixel-list and convert it to a concrete Grid.
    """
    sprite_tbl = GLOBAL.load_sprite_analysis_table(scenarioId, ruleId)

    best_sid   = None
    best_score = -1
    full_score = len(criteria)

    for sid, row in sprite_tbl.items():
        # filter to the right example
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue

        # count how many criteria this row satisfies
        score = 0
        for attr, val in criteria:
            if row.get(attr) == val:
                score += 1

        # keep the highest‐scoring sprite
        if score > best_score:
            best_score, best_sid = score, sid
            # if we hit a perfect match, we can stop early
            if score == full_score:
                break

    if best_sid is None or best_score <= 0:
        return None

    raw = json.loads(sprite_tbl[best_sid]["data"])
    return to_concrete_grid(raw)


def select_object_grid_fn(
    scenarioId: str,
    ruleId:     str,
    criteria:   List[Tuple[str, Any]],
    trainId:    int | None = None,
    testId:     int | None = None
) -> Optional[Grid]:
    """
    Return the minimal object patch grid for the object_analysis entry that
    best matches the given criteria (highest weighted count of attr==val),
    filtered by trainId/testId. If no row matches at least one criterion,
    return None.
    """
    obj_tbl = GLOBAL.load_object_analysis_table(scenarioId, ruleId)

    best_oid = None
    best_score = -1

    # pick the object with highest weighted match count
    for oid, row in obj_tbl.items():
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId is not None and row.get("testId") != testId:
            continue

        # weighted count: sizeOrder matches count for 10, everything else counts for 1
        score = 0
        for attr, val in criteria:
            if row.get(attr) == val:
                if attr == "sizeOrder" or attr == "isColorUnique":
                    score += 5
                else:
                    score += 1

        if score > best_score:
            best_score = score
            best_oid = oid

    # require at least one (weighted) match
    if best_oid is None or best_score <= 0:
        return None

    # build the patch grid from the chosen row
    row = obj_tbl[best_oid]
    coords_abs = json.loads(row.get("data", "[]"))
    if not coords_abs:
        return None

    rows = [r for r, _ in coords_abs]
    cols = [c for _, c in coords_abs]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    height = max_r - min_r + 1
    width  = max_c - min_c + 1
    color = int(row.get("color", 0))

    patch = [[-1 for _ in range(width)] for __ in range(height)]
    for r, c in coords_abs:
        lr, lc = r - min_r, c - min_c
        patch[lr][lc] = color

    return tuple(tuple(row) for row in patch)

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
    ),
    Action(
        id="select_object_grid",
        name="Select Object Grid",
        description=(
            "Filter a list of objects by (attribute==value) criteria and return "
            "the minimal object patch grid for the first match."
        ),
        category=ActionCategory.SELECTION_FILTERING,
        input_arguments=[
            ArgumentBinding("scenarioId", "String", binding=BindingStatus.INSTANCE),
            ArgumentBinding("ruleId",     "String", binding=BindingStatus.INSTANCE),
            ArgumentBinding("trainId",    "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("testId",     "Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding("criteria",   "List[Tuple[String,Integer]]", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=select_object_grid_fn
    )
]
