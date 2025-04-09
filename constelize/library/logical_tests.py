from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding

def equality(a, b) -> bool:
    return a == b

def greater(a: int, b: int) -> bool:
    return a > b

def less(a: int, b: int) -> bool:
    return a < b

def greater_equal(a: int, b: int) -> bool:
    return a >= b

def less_equal(a: int, b: int) -> bool:
    return a <= b

def flip(b: bool) -> bool:
    return not b

def both(a: bool, b: bool) -> bool:
    return a and b

def either(a: bool, b: bool) -> bool:
    return a or b

ACTIONS = [
    Action(
        id="equality_test",
        name="Equality",
        category=ActionCategory.LOGICAL_TESTS,
        function=equality,
        input_arguments=[
            ArgumentBinding(name="a", type="Any"),
            ArgumentBinding(name="b", type="Any")
        ],
        output_type="Boolean",
        description="Test if two values are equal."
    ),
    Action(
        id="greater_than",
        name="Greater Than",
        category=ActionCategory.LOGICAL_TESTS,
        function=greater,
        input_arguments=[
            ArgumentBinding(name="a", type="Integer"),
            ArgumentBinding(name="b", type="Integer")
        ],
        output_type="Boolean",
        description="Check if a > b."
    ),
    Action(
        id="less_than",
        name="Less Than",
        category=ActionCategory.LOGICAL_TESTS,
        function=less,
        input_arguments=[
            ArgumentBinding(name="a", type="Integer"),
            ArgumentBinding(name="b", type="Integer")
        ],
        output_type="Boolean",
        description="Check if a < b."
    ),
    Action(
        id="greater_equal",
        name="Greater or Equal",
        category=ActionCategory.LOGICAL_TESTS,
        function=greater_equal,
        input_arguments=[
            ArgumentBinding(name="a", type="Integer"),
            ArgumentBinding(name="b", type="Integer")
        ],
        output_type="Boolean",
        description="Check if a >= b."
    ),
    Action(
        id="less_equal",
        name="Less or Equal",
        category=ActionCategory.LOGICAL_TESTS,
        function=less_equal,
        input_arguments=[
            ArgumentBinding(name="a", type="Integer"),
            ArgumentBinding(name="b", type="Integer")
        ],
        output_type="Boolean",
        description="Check if a <= b."
    ),
    Action(
        id="logical_not",
        name="Not",
        category=ActionCategory.LOGICAL_TESTS,
        function=flip,
        input_arguments=[
            ArgumentBinding(name="b", type="Boolean")
        ],
        output_type="Boolean",
        description="Logical NOT."
    ),
    Action(
        id="logical_and",
        name="And",
        category=ActionCategory.LOGICAL_TESTS,
        function=both,
        input_arguments=[
            ArgumentBinding(name="a", type="Boolean"),
            ArgumentBinding(name="b", type="Boolean")
        ],
        output_type="Boolean",
        description="Logical AND."
    ),
    Action(
        id="logical_or",
        name="Or",
        category=ActionCategory.LOGICAL_TESTS,
        function=either,
        input_arguments=[
            ArgumentBinding(name="a", type="Boolean"),
            ArgumentBinding(name="b", type="Boolean")
        ],
        output_type="Boolean",
        description="Logical OR."
    ),
]
