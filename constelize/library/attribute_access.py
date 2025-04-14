from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory

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
    )
]
