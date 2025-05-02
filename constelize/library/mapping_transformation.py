from typing import List

from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory

def apply(function, container):
    return type(container)(function(e) for e in container)

def rapply(functions, value):
    return type(functions)(function(value) for function in functions)

def mapply(function, container):
    return frozenset(function(e) for e in container)

def papply(function, a, b):
    return tuple(function(i, j) for i, j in zip(a, b))

def mpapply(function, a, b):
    return frozenset(function(i, j) for i, j in zip(a, b))

def as_grid(pixels: List[tuple]) -> List[List[int]]:
    """
    Convert a list of (color, (row, col)) tuples into a 2D grid.
    """
    if not pixels:
        return []

    max_row = max(pos[0] for _, pos in pixels)
    max_col = max(pos[1] for _, pos in pixels)
    grid = [[0 for _ in range(max_col + 1)] for _ in range(max_row + 1)]

    for color, (row, col) in pixels:
        grid[row][col] = color

    return grid





ACTIONS = [
    Action(
        id="apply_function",
        name="Apply Function",
        description="Apply function to each element in a container.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="function", type="Callable", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Container",
        function=apply
    ),
    Action(
        id="rapply_function",
        name="Reverse Apply",
        description="Apply each function in a container to a given value.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="functions", type="Container", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="value", type="Any", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Container",
        function=rapply
    ),
    Action(
        id="mapply_function",
        name="Mapped Apply",
        description="Apply a function to a container and merge results.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="function", type="Callable", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="FrozenSet",
        function=mapply
    ),
    Action(
        id="pairwise_apply",
        name="Pairwise Apply",
        description="Apply function element-wise to two containers (as tuples).",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="function", type="Callable", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="a", type="Tuple", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="b", type="Tuple", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Tuple",
        function=papply
    ),
    Action(
        id="pairwise_merge_apply",
        name="Pairwise Merge Apply",
        description="Apply function element-wise to two containers and merge as set.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="function", type="Callable", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="a", type="Tuple", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="b", type="Tuple", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="FrozenSet",
        function=mpapply
    ),
    Action(
        id="as_grid",
        name="as_grid",
        description="Convert a structured sprite or shape into a 2D grid.",
        category=ActionCategory.MAPPING_TRANSFORMATION,
        input_arguments=[
            ArgumentBinding(name="sprite", value=None, binding=BindingStatus.UNRESOLVED, type="Sprite"),
        ],
        output_type="grid",
        function=as_grid,
    ),
]
