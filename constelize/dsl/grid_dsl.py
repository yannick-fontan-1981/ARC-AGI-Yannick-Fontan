# grid_dsl.py

from typing import Union, Tuple, List, Sequence, Iterable
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

def shift_with_background(
    grid: Grid,
    patch: Grid,
    patch_min_x: int,
    patch_min_y: int,
    move_rel_x: int,
    move_rel_y: int,
    object_color: int,
    background_color: int
) -> Grid:
    """
    Shift a subgrid patch within the provided grid, ignoring anonymized (-8) pixels.

    Parameters:
      grid: the base grid to modify (e.g., anonymized output grid).
      patch: the extracted object subgrid, with -8 for anonymized cells.
      patch_min_x, patch_min_y: top-left coordinates of patch in the base grid.
      move_rel_x, move_rel_y: the (dx, dy) offsets to move the patch.
      obj_color: the color of the object cells in the patch.
      background_color: color to fill in vacated cells.

    Returns a new Grid with the patch moved and vacated cells filled.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    # Copy the base grid to a mutable buffer
    new_grid = [list(row) for row in grid]

    patch_h = len(patch)
    patch_w = len(patch[0]) if patch_h else 0

    # 1) Erase original patch cells, but only actual object pixels (ignore -8)
    for i_local in range(patch_h):
        for j_local in range(patch_w):
            cell = patch[i_local][j_local]
            if cell == object_color:
                i = patch_min_y + i_local
                j = patch_min_x + j_local
                if 0 <= i < rows and 0 <= j < cols:
                    new_grid[i][j] = background_color

    # 2) Draw moved patch cells at new positions, ignore anonymized
    for i_local in range(patch_h):
        for j_local in range(patch_w):
            cell = patch[i_local][j_local]
            if cell == object_color:
                i = patch_min_y + i_local
                j = patch_min_x + j_local
                ni = i + move_rel_y
                nj = j + move_rel_x
                if 0 <= ni < rows and 0 <= nj < cols:
                    new_grid[ni][nj] = object_color

    # 3) Return new grid frozen
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
    #print("base")
    #print(base)
    #print("patch")
    #print(patch)
    #print("top_left")
    #print(top_left)

    bi, bj = top_left

    # If either coordinate is None (or not an int), just skip painting:
    if not isinstance(bi, int) or not isinstance(bj, int):
        print(f"⚠️ paint: invalid top_left={top_left!r}, skipping patch")
        return base

    result = [list(row) for row in base]

    for i in range(len(patch)):
        for j in range(len(patch[0])):
            val = patch[i][j]
            if val != -1:
                if 0 <= bi + i < len(result) and 0 <= bj + j < len(result[0]):
                    result[bi + i][bj + j] = val

    return tuple(tuple(row) for row in result)

def recolor_sprite(grid: Grid, recolor_map: List[List[int]]) -> Grid:
    """
    Recolor a grid according to a mapping list of [fromColor, toColor] pairs.
    Pixels not in the map remain unchanged.
    """
    # Build mapping dict
    map_dict = {frm: to for frm, to in recolor_map}
    return tuple(
        tuple(map_dict.get(cell, cell) for cell in row)
        for row in grid
    )

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

    if isinstance(data, list) and all(isinstance(x, (list, tuple))
        and len(x) == 2
        and isinstance(x[0], int)
        and isinstance(x[1], (list, tuple))
        for x in data):
            data = frozenset((x[0], tuple(x[1])) for x in data)

    if isinstance(data, frozenset):
        try:
            sample = next(iter(data))
        except StopIteration:
            return tuple()

        if isinstance(sample, tuple):
            if isinstance(sample[0], int):
                pixels = {(i, j): val for val, (i, j) in data}
            elif isinstance(sample[0], tuple):
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
    """
    Compare two grids for equality, treating None or non‑grids as always unequal.
    """
    # If either is None, they can't be equal
    if grid1 is None or grid2 is None:
        return False

    def to_nested_list(g):
        # If g isn't iterable (or its rows aren’t), this will raise TypeError
        return [list(row) for row in g]

    try:
        list1 = to_nested_list(grid1)
        list2 = to_nested_list(grid2)
    except TypeError:
        # grid1 or grid2 wasn’t a proper 2D iterable
        return False

    if len(list1) != len(list2):
        return False
    for row1, row2 in zip(list1, list2):
        if len(row1) != len(row2):
            return False
        for cell1, cell2 in zip(row1, row2):
            # −8 is a wildcard
            if cell1 == -8 or cell2 == -8:
                continue
            if cell1 != cell2:
                return False
    return True

def concrete_grids_equal(g1: Grid, g2: Grid) -> bool:
    """
    Compares two grids including -8 (transparent) values.
    """
    try:
        if g1 is None or g2 is None:
            return False
        if len(g1) != len(g2):
            return False
        for row1, row2 in zip(g1, g2):
            if len(row1) != len(row2):
                return False
            for val1, val2 in zip(row1, row2):
                if val1 != val2:
                    return False
        return True
    except TypeError:
        success = False

def crop(grid: tuple[tuple[int, ...], ...], minX: int, minY: int, width: int, height: int) -> tuple[tuple[int, ...], ...] | None:
    max_y = len(grid)
    max_x = len(grid[0]) if max_y > 0 else 0

    if minX < 0 or minY < 0 or minX + width > max_x or minY + height > max_y:
        print(f"⚠️ crop bounds out of range: grid={len(grid)}x{max_x}, "
              f"minX={minX}, minY={minY}, width={width}, height={height}")
        return None

    return [
        [grid[minY + i][minX + j] for j in range(width)]
        for i in range(height)
    ]

def fill_grid(mask: Grid, color: int) -> Grid:
    """
    Given a mask grid where object pixels are marked with -5 and background with -1,
    return a new grid where all -5 entries are replaced by the specified color,
    and all other entries (background) remain unchanged (-1).

    Args:
        mask: Grid of ints, with -5 for object mask, -1 for background
        color: Integer color value to fill into the mask locations

    Returns:
        A new Grid where each -5 is replaced by `color`, others unchanged.
    """
    # Collect each filled row in a list
    filled_rows: List[Tuple[int, ...]] = []
    for row in mask:
        filled_row = tuple(
            (color if cell == -5 else cell)
            for cell in row
        )
        filled_rows.append(filled_row)
    # Convert list of rows to a Grid (tuple of tuples)
    return tuple(filled_rows)