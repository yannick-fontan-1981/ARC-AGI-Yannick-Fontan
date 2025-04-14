# grid_dsl.py

from typing import Union, Tuple, List
import json

from typing import Tuple, List, Union

Grid = tuple[tuple[int, ...], ...]

def rot90(grid: Grid) -> Grid:
    return tuple(tuple(grid[i][j] for i in range(len(grid) - 1, -1, -1)) for j in range(len(grid[0])))

def rot180(grid: Grid) -> Grid:
    return tuple(tuple(cell for cell in row[::-1]) for row in grid[::-1])

def rot270(grid: Grid) -> Grid:
    return tuple(tuple(grid[i][j] for i in range(len(grid))) for j in range(len(grid[0]) - 1, -1, -1))

def hmirror(grid: Grid) -> Grid:
    return grid[::-1]

def vmirror(grid: Grid) -> Grid:
    return tuple(tuple(row[::-1]) for row in grid)

def rot90_then_hmirror(grid: Grid) -> Grid:
    return rot90(hmirror(grid))

def rot90_then_vmirror(grid: Grid) -> Grid:
    return rot90(vmirror(grid))

def zoom(grid: Grid, zoom_x: int, zoom_y: int) -> Grid:
    return tuple(
        tuple(pixel for pixel in row for _ in range(zoom_x))
        for row in grid
        for _ in range(zoom_y)
    )

def unzoom(grid: Grid, zoom_x: int, zoom_y: int) -> Grid:
    rows = len(grid)
    cols = len(grid[0])
    orig_rows = rows // zoom_y
    orig_cols = cols // zoom_x

    unzoomed = []
    for y in range(orig_rows):
        row = []
        for x in range(orig_cols):
            # prendre le pixel en haut à gauche du bloc comme représentant
            val = grid[y * zoom_y][x * zoom_x]
            row.append(val)
        unzoomed.append(tuple(row))  # ou list(row) selon format
    return tuple(unzoomed)

def shift(grid: Grid, di: int, dj: int) -> Grid:
    rows, cols = len(grid), len(grid[0])
    new_grid = [[-1 for _ in range(cols)] for _ in range(rows)]

    for i in range(rows):
        for j in range(cols):
            ni, nj = i + di, j + dj
            if 0 <= ni < rows and 0 <= nj < cols:
                new_grid[ni][nj] = grid[i][j]

    return tuple(tuple(row) for row in new_grid)


def normalize(grid: Grid) -> Grid:
    rows, cols = len(grid), len(grid[0])
    min_i, min_j = rows, cols
    active_pixels = []

    for i in range(rows):
        for j in range(cols):
            if grid[i][j] >= 0 or grid[i][j] == -8:
                active_pixels.append((i, j))
                if i < min_i:
                    min_i = i
                if j < min_j:
                    min_j = j

    if not active_pixels:
        return grid

    new_rows = max(i - min_i for i, _ in active_pixels) + 1
    new_cols = max(j - min_j for _, j in active_pixels) + 1
    new_grid = [[-1 for _ in range(new_cols)] for _ in range(new_rows)]

    for i, j in active_pixels:
        new_grid[i - min_i][j - min_j] = grid[i][j]

    return tuple(tuple(row) for row in new_grid)


def paint(base: Grid, patch: Grid, top_left: Tuple[int, int]) -> Grid:
    bi, bj = top_left
    result = [list(row) for row in base]

    for i in range(len(patch)):
        for j in range(len(patch[0])):
            val = patch[i][j]
            if val != -1:
                if 0 <= bi + i < len(result) and 0 <= bj + j < len(result[0]):
                    result[bi + i][bj + j] = val

    return tuple(tuple(row) for row in result)


def to_object(grid: Grid) -> frozenset:
    return frozenset((val, (i, j)) for i, row in enumerate(grid) for j, val in enumerate(row) if val >= 0)


def to_shape(grid: Grid) -> frozenset:
    return frozenset((i, j) for i, row in enumerate(grid) for j, val in enumerate(row) if val != -1)

def to_concrete_grid(data) -> Tuple[Tuple[int]]:
    """
    Convertit un Object, Patch, Shape, Grid ou JSON string vers une grille concrète d'entiers :
    - couleurs réelles : ≥ 0
    - pixel absent      : -1
    - pixel de forme    : -8
    """
    if isinstance(data, str):
        data = json.loads(data)

    if isinstance(data, list):
        data = frozenset((x[0], tuple(x[1])) for x in data)

    if isinstance(data, frozenset):
        try:
            sample = next(iter(data))
        except StopIteration:
            return tuple()

        if isinstance(sample, tuple):
            if isinstance(sample[0], int):
                # Objet coloré : (val, (i, j))
                pixels = {(i, j): val for val, (i, j) in data}
            elif isinstance(sample[0], tuple):
                # Shape : ((i, j))
                pixels = {(i, j): -8 for (i, j) in data}
            else:
                raise ValueError("Unsupported tuple format in frozenset.")
        else:
            raise ValueError("Unsupported frozenset content.")

        rows = [i for (i, _) in pixels]
        cols = [j for (_, j) in pixels]
        min_i, max_i = min(rows), max(rows)
        min_j, max_j = min(cols), max(cols)

        grid = []
        for i in range(min_i, max_i + 1):
            row = []
            for j in range(min_j, max_j + 1):
                row.append(pixels.get((i, j), -1))
            grid.append(tuple(row))
        return tuple(grid)

    elif isinstance(data, (tuple, list)) and all(isinstance(row, (tuple, list)) for row in data):
        return tuple(tuple(int(cell) for cell in row) for row in data)

    raise ValueError(f"Unsupported input format for to_concrete_grid: {type(data)}")

def grid_to_pretty_string(grid: Grid) -> str:
    lines = []
    for row in grid:
        line = "  [ " + ", ".join(f"{cell:>2}" for cell in row) + " ]"
        lines.append(line)
    return "[\n" + ",\n".join(lines) + "\n]"


def grids_equal(grid1, grid2) -> bool:
    # Convert both grids to nested lists.
    def to_nested_list(g):
        return [list(row) for row in g]

    list1 = to_nested_list(grid1)
    list2 = to_nested_list(grid2)

    if len(list1) != len(list2):
        return False
    for row1, row2 in zip(list1, list2):
        if len(row1) != len(row2):
            return False
        for cell1, cell2 in zip(row1, row2):
            # If either cell is -8, we treat it as a wildcard that always "matches"
            if cell1 == -8 or cell2 == -8:
                continue
            if cell1 != cell2:
                return False
    return True