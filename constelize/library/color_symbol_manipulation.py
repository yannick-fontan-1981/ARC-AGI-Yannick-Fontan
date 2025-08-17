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
    origin_coords: List[Dict[str, int]],
    recolor_maps: List[List[Dict[str, int]]],
    canvas: List[List[int]]
) -> List[List[int]]:
    """
    Applies recoloring and repainting for multiple sprites onto an anonymized canvas,
    erasing each sprite's last origin position (if it moved) by filling with the
    most frequent color in the original canvas:
      - sprites: list of sprite‐grids
      - repaint_coords: list of {'minX': x_new, 'minY': y_new}
      - origin_coords: list of {'minX': x_old, 'minY': y_old}
      - recolor_maps: list of lists of {'From':f,'To':t}
      - canvas: the anonymized background grid
    """
    from collections import Counter

    # make a mutable copy of the canvas
    painted = [ list(row) for row in canvas ]
    height = len(painted)
    width  = len(painted[0]) if height else 0

    # determine the background color as the most frequent value in the canvas
    flat_pixels = [pix for row in canvas for pix in row]
    bg_color = Counter(flat_pixels).most_common(1)[0][0] if flat_pixels else 0
    print(f"🖌️ detected bg_color = {bg_color}")

    for idx, (sprite, rp, orig, maps) in enumerate(zip(
        sprites, repaint_coords, origin_coords, recolor_maps
    )):
        x_new = rp.get('minX', 0)
        y_new = rp.get('minY', 0)
        x_old = orig.get('minX', 0)
        y_old = orig.get('minY', 0)
        print(f"[#{idx}] sprite moved from ({x_old},{y_old}) to ({x_new},{y_new})")

        # 1) erase old origin if it moved
        if (x_old, y_old) != (x_new, y_new):
            print(f"    erasing old origin at ({x_old},{y_old}) with bg_color")
            for ry, row in enumerate(sprite):
                for rx, _ in enumerate(row):
                    yy = y_old + ry
                    xx = x_old + rx
                    if 0 <= yy < height and 0 <= xx < width:
                        painted[yy][xx] = bg_color

        # 2) build recolor mapping list
        mapping_list = []
        for m in maps:
            f = m.get('From')
            t = m.get('To')
            print(f"    recolor pair: {f} → {t}")
            if t != -1:
                mapping_list.append((f, t))

        # 3) recolor the sprite
        recolored = recolor_sprite(sprite, mapping_list)

        # 4) paint recolored sprite at new coords
        print(f"    placing recolored sprite at ({x_new},{y_new})")
        for ry, row in enumerate(recolored):
            for rx, val in enumerate(row):
                yy = y_new + ry
                xx = x_new + rx
                if 0 <= yy < height and 0 <= xx < width and val != -1:
                    painted[yy][xx] = val

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
            ArgumentBinding(name="sprites", type="List<Sprite>", binding=BindingStatus.PRODUCE),
            ArgumentBinding(name="repaint_coords", type="List<Dict<String,Integer>>", binding=BindingStatus.PRODUCE),
            ArgumentBinding(name="origin_coords", type="List<Dict<String,Integer>>", binding=BindingStatus.PRODUCE),
            ArgumentBinding(name="recolor_maps", type="List<List<Dict<String,Integer>>>", binding=BindingStatus.PRODUCE),
            ArgumentBinding(name="canvas", type="Grid", binding=BindingStatus.INPUT_GRID)
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
