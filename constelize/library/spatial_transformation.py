# spatial_transformation.py

from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from constelize.dsl.grid_dsl import rot90, rot180, rot270, hmirror, vmirror, rot90_then_hmirror, rot90_then_vmirror, \
    zoom
from typing import Tuple, Any

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
    )
]