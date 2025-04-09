from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory

def sort(container, compfunc):
    return tuple(sorted(container, key=compfunc))

def argmax(container, compfunc):
    return max(container, key=compfunc)

def argmin(container, compfunc):
    return min(container, key=compfunc)

def first(container):
    return next(iter(container))

def last(container):
    return list(container)[-1] if container else None

ACTIONS = [
    Action(
        id="sort_by_function",
        name="Sort by Function",
        description="Sort container using a custom comparator.",
        category=ActionCategory.SORTING_ORDERING,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="compfunc", type="Callable", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Tuple",
        function=sort
    ),
    Action(
        id="argmax_by_function",
        name="ArgMax by Function",
        description="Return the element for which the function is maximal.",
        category=ActionCategory.SORTING_ORDERING,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="compfunc", type="Callable", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Any",
        function=argmax
    ),
    Action(
        id="argmin_by_function",
        name="ArgMin by Function",
        description="Return the element for which the function is minimal.",
        category=ActionCategory.SORTING_ORDERING,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED),
            ArgumentBinding(name="compfunc", type="Callable", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Any",
        function=argmin
    ),
    Action(
        id="first_element",
        name="First Element",
        description="Get the first element from a container.",
        category=ActionCategory.SORTING_ORDERING,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Any",
        function=first
    ),
    Action(
        id="last_element",
        name="Last Element",
        description="Get the last element from a container.",
        category=ActionCategory.SORTING_ORDERING,
        input_arguments=[
            ArgumentBinding(name="container", type="Container", binding=BindingStatus.UNRESOLVED)
        ],
        output_type="Any",
        function=last
    ),
]
