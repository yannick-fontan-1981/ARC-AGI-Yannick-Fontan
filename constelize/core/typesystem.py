from typing import Any, Callable, Tuple, FrozenSet, Union

# --- Canonical symbolic type mapping ---

SymbolicTypes = {
    "Grid": tuple,                          # Tuple[Tuple[int]]
    "Patch": frozenset,                     # Set of indices or object cells
    "Object": frozenset,                    # frozenset of (color, (i, j))
    "Objects": frozenset,                   # set of Objects
    "Indices": frozenset,                   # frozenset of (i, j)
    "Tuple[int, int]": tuple,
    "Boolean": bool,
    "Integer": int,
    "Callable": Callable,
    "Container": (tuple, list, frozenset),
    "Any": object,
}

# --- Type relationships (inference / conversion model) ---

TypeHierarchy = {
    "Object": ["Patch", "Indices"],
    "Patch": ["Indices"],
    "Objects": ["Container"],
    "Indices": ["Container"],
    "Grid": ["Container"],
    "Tuple[int, int]": ["Container"],
    "Integer": [],
    "Boolean": [],
    "Callable": [],
    "Any": []
}


def is_instance_of_type(value: Any, symbolic_type: str) -> bool:
    """Check if a value matches a symbolic type, including flexible list/tuple handling."""
    python_type = SymbolicTypes.get(symbolic_type)
    if python_type is None:
        return False

    if symbolic_type == "Grid":
        # Accepte tuple[tuple[int]] OU list[list[int]]
        if isinstance(value, (list, tuple)):
            return all(isinstance(row, (list, tuple)) and all(isinstance(cell, int) for cell in row) for row in value)
        return False

    if symbolic_type == "FrozenSet":
        return isinstance(value, (set, frozenset))

    if isinstance(python_type, tuple):
        return isinstance(value, python_type)

    return isinstance(value, python_type)


def can_convert(from_type: str, to_type: str) -> bool:
    """Returns True if from_type can be used as to_type via hierarchy inference."""
    if from_type == to_type:
        return True
    visited = set()
    stack = [from_type]
    while stack:
        current = stack.pop()
        if current == to_type:
            return True
        visited.add(current)
        stack.extend(t for t in TypeHierarchy.get(current, []) if t not in visited)
    return False


def common_type(type1: str, type2: str) -> Union[str, None]:
    """Return the lowest common ancestor symbolic type, or None."""
    if type1 == type2:
        return type1
    paths1 = get_ancestor_path(type1)
    paths2 = get_ancestor_path(type2)
    common = set(paths1) & set(paths2)
    return next((t for t in paths1 if t in common), None)


def get_ancestor_path(symbolic_type: str) -> list:
    """Return a flattened path to the root in type hierarchy."""
    path = []
    stack = [symbolic_type]
    visited = set()
    while stack:
        current = stack.pop()
        if current not in visited:
            path.append(current)
            visited.add(current)
            stack.extend(TypeHierarchy.get(current, []))
    return path
