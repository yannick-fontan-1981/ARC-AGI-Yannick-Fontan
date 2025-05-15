# spatial_transformation.py
import copy

from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.dsl.grid_dsl import rot90, rot180, rot270, hmirror, vmirror, rot90_then_hmirror, rot90_then_vmirror, \
    zoom, paint, Grid, crop, unzoom, shift_with_background
from typing import Tuple, Any, List, Dict


def shift(patch: Any, directions: Tuple[int, int]) -> Any:
    di, dj = directions
    if isinstance(next(iter(patch))[1], tuple):
        return frozenset((value, (i + di, j + dj)) for value, (i, j) in patch)
    return frozenset((i + di, j + dj) for i, j in patch)

def normalize(patch: Any) -> Any:
    if not patch:
        return patch
    min_i = min(i for _, (i, j) in patch)
    min_j = min(j for _, (i, j) in patch)
    return shift(patch, (-min_i, -min_j))

def repeated_sprite(output_canvas: Grid, sprite: Grid,
                    input_positions: List[Dict[str, int]],
                    output_positions: List[Dict[str, int]]) -> Grid:
    canvas = copy.deepcopy(output_canvas)
    for pos in output_positions:
        x, y = pos["x"], pos["y"]
        canvas = paint(canvas, sprite, (y, x))  # (row,col) = (y,x)
    return canvas

def canvas_by_ratio_fn(grid, ratio_width: int, ratio_height: int):
    """
    Compute a blank canvas based on the dimensions of an input grid and the given ratios.
    New width  = input width  * ratio_width
    New height = input height * ratio_height
    The canvas is initialized with -8 (or any other default value).
    """
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    new_width = width * ratio_width
    new_height = height * ratio_height
    return tuple(tuple(-8 for _ in range(new_width)) for _ in range(new_height))

def sprite_computation_paint(canvas: Grid, sub_sprites: List[Grid], positions: List[Dict[str, int]]) -> Grid:
    from constelize.dsl.grid_dsl import paint
    result = canvas
    for sprite, pos in zip(sub_sprites, positions):
        if sprite is None:
            print(f"⚠️ Skipping paint: sprite is None at position {pos}")
            continue
        x, y = pos["x"], pos["y"]
        result = paint(result, sprite, (y, x))
    return result

def repaint(base: Grid, patch: Grid, minX: int, minY: int):
    return paint(base, patch, (minY, minX))

def initialize_buffer_fn(initial_grid):
    """
    Pass-through action for initializing the shared buffer.
    Takes the starting grid and makes it available as the buffer.
    """
    return initial_grid

ACTIONS = [
    Action(
        id="shift_patch",
        name="Shift",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=shift,
        input_arguments=[
            ArgumentBinding(name="patch", type="Patch"),
            ArgumentBinding(name="directions", type="IntegerTuple")
        ],
        output_type="Patch",
        description="Shift a patch by a directional vector."
    ),
    Action(
        id="normalize_patch",
        name="Normalize",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=normalize,
        input_arguments=[
            ArgumentBinding(name="patch", type="Patch")
        ],
        output_type="Patch",
        description="Shift a patch so its upper-left corner aligns to (0, 0)."
    ),
    Action(
        id="rotate_90",
        name="Rotate 90",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=rot90,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Rotate grid 90 degrees clockwise."
    ),
    Action(
        id="rotate_180",
        name="Rotate 180",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=rot180,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Rotate grid 180 degrees."
    ),
    Action(
        id="rotate_270",
        name="Rotate 270",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=rot270,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Rotate grid 270 degrees clockwise."
    ),
    Action(
        id="mirror_horizontal",
        name="Mirror Horizontal",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=hmirror,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Flip grid vertically (horizontal mirror)."
    ),
    Action(
        id="mirror_vertical",
        name="Mirror Vertical",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=vmirror,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Flip grid horizontally (vertical mirror)."
    ),
    Action(
        id="flipped_horiz_90",
        name="Flip Horizontally After 90°",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=rot90_then_vmirror,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Flip a grid horizontally after a 90-degree rotation."
    ),
    Action(
        id="flipped_vert_90",
        name="Flip Vertically After 90°",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=rot90_then_hmirror,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Grid",
        description="Flip a grid vertically after a 90-degree rotation."
    ),
    Action(
        id="zoom",
        name="Zoom",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=zoom,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid"),
            ArgumentBinding(name="zoom_x", type="Integer"),
            ArgumentBinding(name="zoom_y", type="Integer")
        ],
        output_type="Grid",
        description="Zoom in on a grid by repeating each cell zoom_x times horizontally and zoom_y times vertically."
    ),
    Action(
        id="repeated_sprite",
        name="Repeated Sprite",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        function=repeated_sprite,
        input_arguments=[
            ArgumentBinding(name="output_canvas", type="Grid"),
            ArgumentBinding(name="sprite", type="Grid"),
            ArgumentBinding(name="input_positions", type="Container"),
            ArgumentBinding(name="output_positions", type="Container"),
        ],
        output_type="Grid",
        description="Paint the same sprite multiple times at given output positions."
    ),
    Action(
        id="canvas_by_ratio",
        name="Canvas by Ratio",
        description="Compute a blank canvas based on the input grid and given width/height ratios.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.INPUT_GRID),
            ArgumentBinding(name="ratio_width", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="ratio_height", type="Integer", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=canvas_by_ratio_fn
    ),
    Action(
        id="crop_sprite",
        name="Crop Sprite",
        description="Crop a grid region defined by minX, minY, width and height.",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.INPUT_GRID),
            ArgumentBinding(name="minX", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="minY", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="width", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="height", type="Integer", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=crop
    ),
    Action(
        id="sprite_computation_paint",
        name="Sprite Computation Paint",
        description="Paint a sprite multiple times at specified (x, y) locations inside a canvas.",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="canvas", type="Grid"),
            ArgumentBinding(name="sub_sprites", type="Array<Grid>"),
            ArgumentBinding(name="positions", type="Array<Coord>")  # List of {x, y}
        ],
        output_type="Grid",
        function=sprite_computation_paint
    ),
    Action(
        id="unzoom",
        name="Unzoom",
        description="Shrink a grid by integer factors zoom_x, zoom_y by sampling the top-left pixel of each block",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="grid",   type="Grid",    binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="zoom_x", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="zoom_y", type="Integer", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=unzoom
    ),
    Action(
        id="repaint",
        name="Repaint",
        description="repaint the given sprite in the canvas at the given position",
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="base",   type="Grid",    binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="patch",  type="Grid",    binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="minX",   type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="minY",   type="Integer", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=repaint
    ),
    Action(
        id="initialize_buffer",
        name="Initialize Buffer",
        description="Pass-through action to initialize the shared buffer with the input grid.",
        category=ActionCategory.ATTRIBUTE_ACCESS,
        input_arguments=[
            ArgumentBinding(name="initial_grid", type="Grid", binding=BindingStatus.VARIABLE)
        ],
        output_type="Grid",
        function=initialize_buffer_fn,
        deterministic=True,
        pure=True
    ),
    Action(
        id="move_object",
        name="Move Object",
        description=(
            "Shifts a specified patch within a grid by given offsets (dy, dx), "
            "and fills the vacated cells with a background color."
        ),
        category=ActionCategory.SPATIAL_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="patch", type="Patch", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="patch_min_x", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="patch_min_y", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="move_rel_x", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="move_rel_y", type="Integer", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="object_color", type="Color", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="background_color", type="Color", binding=BindingStatus.UNRESOLVED),
        ],
        output_type="Grid",
        function=shift_with_background,
        deterministic=True,
        pure=True
    )
]