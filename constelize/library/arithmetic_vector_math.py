from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from typing import Union, Tuple

Numerical = Union[int, Tuple[int, int]]

def add(a: Numerical, b: Numerical) -> Numerical:
    if isinstance(a, int) and isinstance(b, int):
        return a + b
    if isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] + b[0], a[1] + b[1])
    if isinstance(a, int):
        return (a + b[0], a + b[1])
    return (a[0] + b, a[1] + b)

def subtract(a: Numerical, b: Numerical) -> Numerical:
    if isinstance(a, int) and isinstance(b, int):
        return a - b
    if isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] - b[0], a[1] - b[1])
    if isinstance(a, int):
        return (a - b[0], a - b[1])
    return (a[0] - b, a[1] - b)

def multiply(a: Numerical, b: Numerical) -> Numerical:
    if isinstance(a, int) and isinstance(b, int):
        return a * b
    if isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] * b[0], a[1] * b[1])
    if isinstance(a, int):
        return (a * b[0], a * b[1])
    return (a[0] * b, a[1] * b)

def divide(a: Numerical, b: Numerical) -> Numerical:
    if isinstance(a, int) and isinstance(b, int):
        return a // b
    if isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] // b[0], a[1] // b[1])
    if isinstance(a, int):
        return (a // b[0], a // b[1])
    return (a[0] // b, a[1] // b)

def negate(n: Numerical) -> Numerical:
    return -n if isinstance(n, int) else (-n[0], -n[1])

ACTIONS = [
    Action(
        id="add",
        name="Add",
        category=ActionCategory.ARITHMETIC_VECTOR_MATH,
        function=add,
        input_arguments=[
            ArgumentBinding(name="a", type="Numerical"),
            ArgumentBinding(name="b", type="Numerical")
        ],
        output_type="Numerical",
        description="Add two numbers or vectors."
    ),
    Action(
        id="subtract",
        name="Subtract",
        category=ActionCategory.ARITHMETIC_VECTOR_MATH,
        function=subtract,
        input_arguments=[
            ArgumentBinding(name="a", type="Numerical"),
            ArgumentBinding(name="b", type="Numerical")
        ],
        output_type="Numerical",
        description="Subtract two numbers or vectors."
    ),
    Action(
        id="multiply",
        name="Multiply",
        category=ActionCategory.ARITHMETIC_VECTOR_MATH,
        function=multiply,
        input_arguments=[
            ArgumentBinding(name="a", type="Numerical"),
            ArgumentBinding(name="b", type="Numerical")
        ],
        output_type="Numerical",
        description="Multiply two numbers or vectors."
    ),
    Action(
        id="divide",
        name="Divide",
        category=ActionCategory.ARITHMETIC_VECTOR_MATH,
        function=divide,
        input_arguments=[
            ArgumentBinding(name="a", type="Numerical"),
            ArgumentBinding(name="b", type="Numerical")
        ],
        output_type="Numerical",
        description="Divide two numbers or vectors using floor division."
    ),
    Action(
        id="negate",
        name="Negate",
        category=ActionCategory.ARITHMETIC_VECTOR_MATH,
        function=negate,
        input_arguments=[
            ArgumentBinding(name="n", type="Numerical")
        ],
        output_type="Numerical",
        description="Negate a number or a vector."
    ),
]
