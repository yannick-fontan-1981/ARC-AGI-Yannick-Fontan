from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory

def square(piece) -> bool:
    if isinstance(piece, tuple):
        return len(piece) == len(piece[0])
    h = max(i for _, (i, j) in piece) - min(i for _, (i, j) in piece) + 1
    w = max(j for _, (i, j) in piece) - min(j for _, (i, j) in piece) + 1
    return h == w

def vline(patch) -> bool:
    return all(j == next(iter(patch))[1][1] for _, (i, j) in patch)

def hline(patch) -> bool:
    return all(i == next(iter(patch))[1][0] for _, (i, j) in patch)

def portrait(piece) -> bool:
    if isinstance(piece, tuple):
        return len(piece) > len(piece[0])
    h = max(i for _, (i, j) in piece) - min(i for _, (i, j) in piece) + 1
    w = max(j for _, (i, j) in piece) - min(j for _, (i, j) in piece) + 1
    return h > w

ACTIONS = [
    Action(
        id="is_square",
        name="Is Square",
        description="Check whether the piece is a square.",
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(name="piece", type="Piece", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Boolean",
        function=square
    ),
    Action(
        id="is_vertical_line",
        name="Is Vertical Line",
        description="Check whether the patch forms a vertical line.",
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(name="patch", type="Patch", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Boolean",
        function=vline
    ),
    Action(
        id="is_horizontal_line",
        name="Is Horizontal Line",
        description="Check whether the patch forms a horizontal line.",
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(name="patch", type="Patch", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Boolean",
        function=hline
    ),
    Action(
        id="is_portrait",
        name="Is Portrait",
        description="Check whether the piece is taller than it is wide.",
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(name="piece", type="Piece", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Boolean",
        function=portrait
    )
]