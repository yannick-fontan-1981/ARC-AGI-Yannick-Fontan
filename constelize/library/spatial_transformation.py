# spatial_transformation.py

from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from constelize.dsl.grid_dsl import rot90, rot180, rot270, hmirror, vmirror
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

#def rot90(grid: Tuple[Tuple[int]]) -> Tuple[Tuple[int]]:
#    return tuple(zip(*grid[::-1]))
#
#def rot180(grid: Tuple[Tuple[int]]) -> Tuple[Tuple[int]]:
#    return tuple(tuple(row[::-1]) for row in grid[::-1])
#
#def rot270(grid: Tuple[Tuple[int]]) -> Tuple[Tuple[int]]:
#    return tuple(tuple(row[::-1]) for row in zip(*grid[::-1]))[::-1]
#
#def hmirror(grid: Tuple[Tuple[int]]) -> Tuple[Tuple[int]]:
#    return grid[::-1]
#
#def vmirror(grid: Tuple[Tuple[int]]) -> Tuple[Tuple[int]]:
#    return tuple(row[::-1] for row in grid)

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
]