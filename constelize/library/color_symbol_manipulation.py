import json
from typing import List, Dict

from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.dsl.grid_dsl import recolor_sprite, Grid, to_concrete_grid, grid_to_pretty_string


def recolor(value: int, patch) -> frozenset:
    return frozenset((value, index) for index in patch)

def replace(grid, replacee: int, replacer: int):
    return tuple(tuple(replacer if v == replacee else v for v in row) for row in grid)

def switch(grid, a: int, b: int):
    return tuple(tuple(
        v if (v != a and v != b) else (b if v == a else a)
        for v in row
    ) for row in grid)

def color(obj: frozenset) -> int:
    return next(iter(obj))[0] if obj else 0

def mostcolor(element) -> int:
    values = [v for r in element for v in r] if isinstance(element, tuple) else [v for v, _ in element]
    return max(set(values), key=values.count)

def leastcolor(element) -> int:
    values = [v for r in element for v in r] if isinstance(element, tuple) else [v for v, _ in element]
    return min(set(values), key=values.count)

def set_output_bg_color_fn(grid: Grid, bg_color: int) -> Grid:
    """
    Return a new grid where every -1 cell in `grid`
    has been replaced by `bg_color`.
    """
    return tuple(
        tuple(
            bg_color if cell == -1 or cell == -8 else cell
            for cell in row
        )
        for row in grid
    )

def recolor_and_repaint_sprites(
    sprites: List[List[List[int]]],
    repaint_coords: List[Dict[str, int]],
    recolor_maps: List[List[Dict[str, int]]],
    canvas: List[List[int]]
) -> List[List[int]]:
    """
    Applies recoloring and repainting for multiple sprites onto an anonymized canvas,
    where:
      - sprites is a list of grids,
      - repaint_coords is a list of dicts {'minX': x0, 'minY': y0},
      - recolor_maps is a list of lists of dicts [{'From':f,'To':t}, …].
    """
    # copy the canvas so we don't stomp the original
    painted = [list(row) for row in canvas]
    height = len(painted)
    width  = len(painted[0]) if height > 0 else 0

    for idx, (sprite, coords, maps) in enumerate(zip(sprites, repaint_coords, recolor_maps)):
        x0 = coords.get('minX', 0)
        y0 = coords.get('minY', 0)
        print(f"[#{idx}] placing sprite at (x0={x0}, y0={y0})")

        # build the simple list of (from_color, to_color) pairs
        mapping_list = []
        for m in maps:
            f = m.get('From')
            t = m.get('To')
            print(f"    recolor pair: {f} → {t}")
            mapping_list.append((f, t))

        # do the recolor
        recolored = recolor_sprite(sprite, mapping_list)

        # paint into the canvas
        for ry, row in enumerate(recolored):
            for rx, val in enumerate(row):
                y = y0 + ry
                x = x0 + rx
                if 0 <= y < height and 0 <= x < width:
                    painted[y][x] = val

    return painted


ACTIONS = [
    Action(
        id="recolor_patch",
        name="Recolor Patch",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=recolor,
        input_arguments=[
            ArgumentBinding(name="value", type="Integer"),
            ArgumentBinding(name="patch", type="Grid")
        ],
        output_type="Object",
        description="Recolor all cells in a patch to the specified color."
    ),
    Action(
        id="replace_color",
        name="Replace Color",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=replace,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid"),
            ArgumentBinding(name="replacee", type="Integer"),
            ArgumentBinding(name="replacer", type="Integer")
        ],
        output_type="Grid",
        description="Replace all instances of one color with another."
    ),
    Action(
        id="switch_colors",
        name="Switch Colors",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=switch,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid"),
            ArgumentBinding(name="a", type="Integer"),
            ArgumentBinding(name="b", type="Integer")
        ],
        output_type="Grid",
        description="Switch two colors in the grid."
    ),
    Action(
        id="object_color",
        name="Object Color",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=color,
        input_arguments=[
            ArgumentBinding(name="obj", type="Object")
        ],
        output_type="Integer",
        description="Get the color of the object."
    ),
    Action(
        id="most_common_color",
        name="Most Common Color",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=mostcolor,
        input_arguments=[
            ArgumentBinding(name="element", type="Element")
        ],
        output_type="Integer",
        description="Get the most common color in the element."
    ),
    Action(
        id="least_common_color",
        name="Least Common Color",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=leastcolor,
        input_arguments=[
            ArgumentBinding(name="element", type="Element")
        ],
        output_type="Integer",
        description="Get the least common color in the element."
    ),
    Action(
        id="recolor_sprite",
        name="Recolor Sprite",
        description="Recolor and repaint multiple sprites onto a canvas grid.",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        input_arguments=[
            ArgumentBinding(name="sprites", type="List<Sprite>", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="recolor_maps", type="List<List<Pair>>", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="repaint_coords", type="List<Pair<Integer,Integer>>", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="canvas", type="Grid", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=recolor_and_repaint_sprites
    ),
    Action(
        id="set_output_bg_color",
        name="Set Output Background Color",
        description="Replace every '-1' or '-8' hole in a grid with the specified background color.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="grid",    type="Grid",    binding=BindingStatus.VARIABLE),
            ArgumentBinding(name="bg_color", type="Integer", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=set_output_bg_color_fn,
        deterministic=True,
        pure=True
    ),
]
