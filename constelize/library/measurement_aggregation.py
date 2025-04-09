from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from typing import FrozenSet, Callable, Tuple

def size(container) -> int:
    return len(container)

def colorcount(element, value: int) -> int:
    if isinstance(element, tuple):  # Grid
        return sum(row.count(value) for row in element)
    return sum(v == value for v, _ in element)

def numcolors(element) -> int:
    if isinstance(element, tuple):
        return len(set(v for r in element for v in r))
    return len(set(v for v, _ in element))

def maximum(container: FrozenSet[int]) -> int:
    return max(container, default=0)

def minimum(container: FrozenSet[int]) -> int:
    return min(container, default=0)

def valmax(container, compfunc: Callable) -> int:
    return compfunc(max(container, key=compfunc, default=0))

def valmin(container, compfunc: Callable) -> int:
    return compfunc(min(container, key=compfunc, default=0))

ACTIONS = [
    Action(
        id="size",
        name="Size",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=size,
        input_arguments=[
            ArgumentBinding(name="container", type="Container")
        ],
        output_type="Integer",
        description="Count the number of elements in a container."
    ),
    Action(
        id="color_count",
        name="Color Count",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=colorcount,
        input_arguments=[
            ArgumentBinding(name="element", type="Element"),
            ArgumentBinding(name="value", type="Integer")
        ],
        output_type="Integer",
        description="Count how many times a color appears in a grid or object."
    ),
    Action(
        id="num_colors",
        name="Number of Colors",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=numcolors,
        input_arguments=[
            ArgumentBinding(name="element", type="Element")
        ],
        output_type="Integer",
        description="Count how many different colors appear in a grid or object."
    ),
    Action(
        id="max_value",
        name="Maximum Value",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=maximum,
        input_arguments=[
            ArgumentBinding(name="container", type="IntegerSet")
        ],
        output_type="Integer",
        description="Find the maximum value in a set of integers."
    ),
    Action(
        id="min_value",
        name="Minimum Value",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=minimum,
        input_arguments=[
            ArgumentBinding(name="container", type="IntegerSet")
        ],
        output_type="Integer",
        description="Find the minimum value in a set of integers."
    ),
    Action(
        id="max_by_function",
        name="Max by Function",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=valmax,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="compfunc", type="Callable")
        ],
        output_type="Integer",
        description="Find maximum based on a custom comparison function."
    ),
    Action(
        id="min_by_function",
        name="Min by Function",
        category=ActionCategory.MEASUREMENT_AGGREGATION,
        function=valmin,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="compfunc", type="Callable")
        ],
        output_type="Integer",
        description="Find minimum based on a custom comparison function."
    ),
]
