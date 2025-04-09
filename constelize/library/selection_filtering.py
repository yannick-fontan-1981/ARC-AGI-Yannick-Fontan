from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from typing import Callable, FrozenSet, Any

def sfilter(container: Any, condition: Callable) -> Any:
    return type(container)(e for e in container if condition(e))

def mfilter(container: Any, condition: Callable) -> FrozenSet:
    return frozenset(e for e in container if condition(e))

def extract(container: Any, condition: Callable) -> Any:
    return next((e for e in container if condition(e)), None)

def sizefilter(container: Any, n: int) -> FrozenSet:
    return frozenset(item for item in container if len(item) == n)

def colorfilter(objs: FrozenSet, value: int) -> FrozenSet:
    return frozenset(obj for obj in objs if next(iter(obj))[0] == value)

ACTIONS = [
    Action(
        id="sfilter",
        name="Simple Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=sfilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="Container",
        description="Filter elements in container based on condition."
    ),
    Action(
        id="mfilter",
        name="Merge Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=mfilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="FrozenSet",
        description="Filter elements and return merged set."
    ),
    Action(
        id="extract_first_match",
        name="Extract First Match",
        category=ActionCategory.SELECTION_FILTERING,
        function=extract,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="Any",
        description="Extract first element that satisfies condition."
    ),
    Action(
        id="size_filter",
        name="Size Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=sizefilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="n", type="Integer")
        ],
        output_type="FrozenSet",
        description="Filter container items by size."
    ),
    Action(
        id="color_filter",
        name="Color Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=colorfilter,
        input_arguments=[
            ArgumentBinding(name="objs", type="Objects"),
            ArgumentBinding(name="value", type="Integer")
        ],
        output_type="FrozenSet",
        description="Filter objects by color value."
    ),
]
