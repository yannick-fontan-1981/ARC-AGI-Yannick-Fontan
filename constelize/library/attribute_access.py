#constelize/library/attribute_access.py
import json
from typing import List, Tuple, Any, Optional

import constelize.tools.globals as GLOBAL
from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory
from constelize.core.procedure import ActionInstance
from constelize.dsl.grid_dsl import Grid, to_concrete_grid, zoom, rot90, rot270, recolor_sprite, rot180, hmirror, \
    vmirror, rot90_then_hmirror, rot90_then_vmirror

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
    criteria: List[Tuple[str, Any, int]],  # (colonne, valeur_attendue, strict_weight)
    attribute_name: str,
    trainId: int | None = None,
    testId: int | None = None
) -> int | None:
    """
    Pour chaque critère (col, val, strict_w), on calcule:
      score += weight(col) * strict_w

    On renvoie l'attribut du sprite qui maximise ce score.
    """

    sprite_tbl = GLOBAL.load_sprite_analysis_table(scenarioId, ruleId)

    # fonction de poids statique
    def weight(attr: str) -> int:
        if attr in ("isFromSplit", "isFromGlued"):
            return 20
        if attr in ("sizeOrder", "nbColors", "isColorUnique", "colorUniqueOrder", "hasBorder"):
            return 10
        if attr.startswith("isTouching"):
            return 5
        return 1

    # score maximal possible (pour debug)
    total_possible = sum(weight(col) * strict_w for col, _, strict_w in criteria)

    best_sid = None
    best_score = -1

    for sid, row in sprite_tbl.items():
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue
        if not row.get("isInsideInput", False):
            continue

        # calcul du score en combinant weight() et strict_w
        score = 0
        for col, expected_val, strict_w in criteria:
            if row.get(col) == expected_val:
                score += weight(col) * strict_w

        if score > best_score:
            best_score = score
            best_sid   = sid

    if best_sid is None or best_score <= 0:
        return None

    # debug
    print(
        f"[BEST MATCH] sprite={best_sid} score={best_score}/{total_possible} "
        f"→ {attribute_name} = {sprite_tbl[best_sid].get(attribute_name)}"
    )

    return sprite_tbl[best_sid].get(attribute_name)

def select_object_and_attribute_fn(
    scenarioId: str,
    ruleId: str,
    criteria: List[Tuple[str, Any, int]],  # (colonne, valeur_attendue, strict_weight)
    attribute_name: str,
    trainId:    int | None = None,
    testId:     int | None = None
) -> Optional[int]:
    """
    Pour chaque critère (col, val, strict_w), on calcule:
      score += weight(col) * strict_w

    Puis on choisit l'objet dont le score est maximal.
    """
    object_tbl = GLOBAL.load_object_analysis_table(scenarioId, ruleId)

    # même logique de poids que pour les sprites
    def weight(attr: str) -> int:
        if attr in ("isFromSplit", "isFromGlued"):
            return 20
        if attr in ("sizeOrder", "nbColors", "isColorUnique", "colorUniqueOrder", "hasBorder", "width", "height"):
            return 10
        if attr.startswith("isTouching") or attr.startswith("distance"):
            return 5
        return 1

    best_row = None
    best_score = -1
    # pour debug
    total_possible = sum(weight(col) * strict_w for col, _, strict_w in criteria)

    for row in object_tbl.values():
        # filtrer selon train/test et présence en entrée
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue
        if not row.get("isInsideInput", False):
            continue

        # calcul du score
        score = 0
        for col, expected_val, strict_w in criteria:
            if row.get(col) == expected_val:
                score += weight(col) * strict_w

        if score > best_score:
            best_score = score
            best_row   = row

    if best_row is None or best_score <= 0:
        print("  ⚠️ Aucun objet ne satisfait les critères → None")
        return None

    result = best_row.get(attribute_name)
    print(
        f"[BEST MATCH] object_id={best_row.get('id')} "
        f"score={best_score}/{total_possible} → {attribute_name} = {result}"
    )
    return result

def apply_transform_to_grid(
    grid: Grid,
    transform: dict
) -> Grid:
    """
    Given a dense grid and a transform spec, apply:
      1) one of the geometric ops (rotate or flip)
      2) zoom
      3) recolor
    """
    if transform.get("rotated_90"):
        grid = rot90(grid)
    elif transform.get("rotated_180"):
        grid = rot180(grid)
    elif transform.get("rotated_270"):
        grid = rot270(grid)
    elif transform.get("flipped_vert"):
        grid = hmirror(grid)
    elif transform.get("flipped_horiz"):
        grid = vmirror(grid)
    elif transform.get("flipped_vert_90"):
        grid = rot90_then_hmirror(grid)
    elif transform.get("flipped_horiz_90"):
        grid = rot90_then_vmirror(grid)

    # 2) zoom
    zx = transform.get("zoom_x", 1)
    zy = transform.get("zoom_y", 1)
    if zx != 1 or zy != 1:
        grid = zoom(grid, zx, zy)

    # 3) recolor
    recolor_pairs = transform.get("recolored", [])
    if recolor_pairs:
        grid = recolor_sprite(grid, recolor_pairs)

    return grid
def select_sprite_grid_fn(
    scenarioId: str,
    ruleId:     str,
    criteria:   List[Tuple[str, int, int]],  # (colonne, valeur_attendue, strict_w)
    trainId:    int | None = None,
    testId:     int | None = None,
    transform:  dict | None = None
) -> Grid | None:
    """
    On parcourt les lignes de sprite_analysis, on calcule pour chacune :
      score += weight(col) * strict_w
    et on choisit le sprite à score max.
    """
    print("trainId")
    print(trainId)
    print("testId")
    print(testId)
    print("transform")
    print(transform)
    print("criteria")
    print(criteria)
    sprite_tbl = GLOBAL.load_sprite_analysis_table(scenarioId, ruleId)

    # barème fixe
    def weight(attr: str) -> int:
        if attr in ("isFromSplit", "isFromGlued", "isGrid", "hasBorder"):
            return 20
        if attr in ("nbColors", "colorUniqueOrder"):
            return 10
        if attr in ("sizeOrder", "isColorUnique"):
            return 5
        if attr.startswith("isTouching"):
            return 2
        return 1

    best_sid   = None
    best_score = -1
    # utile pour debug
    total_possible = sum(weight(col) * strict_w for col, _, strict_w in criteria)

    for sid, row in sprite_tbl.items():
        # filtrage par train/test
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue
        if not row.get("isInsideInput", False):
            continue

        # calcul du score
        score = 0
        for col, expected_val, strict_w in criteria:
            if row.get(col) == expected_val:
                score += weight(col) * strict_w

        if score > best_score:
            best_score, best_sid = score, sid
            # early-exit s’il atteint le maximum théorique
            if best_score == total_possible:
                break

    if best_sid is None or best_score <= 0:
        return None

    # reconstruire la grille
    raw = json.loads(sprite_tbl[best_sid]["data"])
    grid = to_concrete_grid(raw)

    # appliquer la transformation suggérée
    if transform:
        grid = apply_transform_to_grid(grid, transform)

    # debug
    print(f"[BEST MATCH] sprite_id={best_sid} score={best_score}/{total_possible}")

    return grid

def select_object_grid_fn(
    scenarioId: str,
    ruleId:     str,
    criteria:   List[Tuple[str, Any, int]],  # (colonne, valeur_attendue, strict_w)
    trainId:    int | None = None,
    testId:     int | None = None
) -> Optional[Grid]:
    """
    Retourne la grille du patch d’objet qui maximise le score pondéré :
      score = Σ weight(col) * strict_w   pour chaque critère vérifié.
    """
    obj_tbl = GLOBAL.load_object_analysis_table(scenarioId, ruleId)

    # barème identique à celui des sprites
    def weight(attr: str) -> int:
        if attr in ("isFromSplit", "isFromGlued"):
            return 20
        if attr in ("sizeOrder", "nbColors", "isColorUnique", "colorUniqueOrder", "hasBorder"):
            return 10
        if attr.startswith("isTouching"):
            return 5
        return 1

    best_oid   = None
    best_score = -1
    # (pour debug) score maximal possible
    total_possible = sum(weight(col) * strict_w for col, _, strict_w in criteria)

    for oid, row in obj_tbl.items():
        # filtrage par train/test
        if trainId is not None and row.get("trainId") != trainId:
            continue
        if testId  is not None and row.get("testId")  != testId:
            continue
        if not row.get("isInsideInput", False):
            continue

        # calcul du score pondéré
        score = 0
        for col, expected_val, strict_w in criteria:
            if row.get(col) == expected_val:
                score += weight(col) * strict_w

        if score > best_score:
            best_score, best_oid = score, oid
            if best_score == total_possible:
                break

    # s’il n’y a pas au moins une correspondance
    if best_oid is None or best_score <= 0:
        return None

    # construction du patch minimal
    row = obj_tbl[best_oid]
    coords_abs = json.loads(row.get("data", "[]"))
    if not coords_abs:
        return None

    rows = [r for r, _ in coords_abs]
    cols = [c for _, c in coords_abs]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    h = max_r - min_r + 1
    w = max_c - min_c + 1
    color = int(row.get("color", 0))

    patch = [[-1 for _ in range(w)] for __ in range(h)]
    for r, c in coords_abs:
        patch[r - min_r][c - min_c] = color

    # debug
    print(f"[BEST MATCH OBJECT] oid={best_oid} score={best_score}/{total_possible}")

    return tuple(tuple(r) for r in patch)

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
        ArgumentBinding("criteria",   "List[Tuple[String,Integer]]",  binding=BindingStatus.CONSTANT),
        ArgumentBinding("transform",  "Dict",                         binding=BindingStatus.CONSTANT),
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
