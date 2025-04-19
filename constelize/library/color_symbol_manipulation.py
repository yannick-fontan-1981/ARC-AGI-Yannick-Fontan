from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.dsl.grid_dsl import recolor_sprite


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

ACTIONS = [
    Action(
        id="recolor_patch",
        name="Recolor Patch",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        function=recolor,
        input_arguments=[
            ArgumentBinding(name="value", type="Integer"),
            ArgumentBinding(name="patch", type="Patch")
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
        description="Recolor a grid according to a color mapping.",
        category=ActionCategory.COLOR_SYMBOL_MANIPULATION,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="recolor_map", type="List<List<Integer>>", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Grid",
        function=recolor_sprite
    ),
]
