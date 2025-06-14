# grid_dsl.py
from collections import Counter
from typing import Union, Tuple, List, Sequence, Iterable, Optional, Dict, Any
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

def zoom(grid: Grid, zoom_x: int|float, zoom_y: int|float) -> Grid:
    # ensure our zoom factors are integers
    zoom_x = int(zoom_x)
    zoom_y = int(zoom_y)

    return tuple(
        tuple(pixel for pixel in row for _ in range(zoom_x))
        for row in grid
        for _ in range(zoom_y)
    )

def unzoom(grid: Grid, zoom_x: int|float, zoom_y: int|float) -> Grid:
    # ensure our zoom factors are integers
    zoom_x = int(zoom_x)
    zoom_y = int(zoom_y)

    # guard against zero or negative zooms
    if zoom_x <= 0 or zoom_y <= 0:
        # could also raise a more specific error here,
        # but we'll just treat it as 'no unzoom'
        return grid

    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    orig_rows = rows // zoom_y
    orig_cols = cols // zoom_x

    unzoomed = []
    for y in range(orig_rows):
        row = []
        for x in range(orig_cols):
            # take the top‐left pixel of each zoom‐block
            val = grid[y * zoom_y][x * zoom_x]
            row.append(val)
        unzoomed.append(tuple(row))
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
    new_pos_x: int,
    new_pos_y: int,
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
    if background_color != -1:
        for i_local in range(patch_h):
            for j_local in range(patch_w):
                cell = patch[i_local][j_local]
                if cell == object_color:
                    i = patch_min_y + i_local
                    j = patch_min_x + j_local
                    if 0 <= i < rows and 0 <= j < cols:
                        new_grid[i][j] = background_color

    # 2) Draw moved patch cells at new positions, ignore anonymized
    if background_color == -1:
        # place at absolute new_pos_x, new_pos_y:
        for i_local in range(patch_h):
            for j_local in range(patch_w):
                if patch[i_local][j_local] == object_color:
                    ni = new_pos_y + i_local
                    nj = new_pos_x + j_local
                    if 0 <= ni < rows and 0 <= nj < cols:
                        new_grid[ni][nj] = object_color
    else:
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

def shift_sprite_with_background(
    patch: Grid,
    patch_min_x: int,
    patch_min_y: int,
    move_rel_x: int,
    move_rel_y: int,
    new_pos_x: int,
    new_pos_y: int,
    background_color: int,
    grid: Optional[Grid] = None
) -> Grid:
    """
    Move a sprite patch within `grid` (optional):

    1) If background_color >= 0: erase original patch pixels (at patch_min_x/patch_min_y)
       by filling them with background_color.
    2) Draw each non-(-8) pixel from patch:
       - If background_color < 0 → place absolutely at (new_pos_x + j, new_pos_y + i)
       - Else → place relatively at ((patch_min_x + j) + move_rel_x, (patch_min_y + i) + move_rel_y)
    """
    if grid is None:
        # Use shrinkable canvas and mark for shrinking at the end
        raw_canvas = makeShrinkableCanvas()
        buf: List[List[int]] = [list(row) for row in raw_canvas]
        using_shrinkable = True
    else:
        # Convert provided grid (usually tuple of tuples) into mutable list of lists
        buf: List[List[int]] = [list(row) for row in grid]
        using_shrinkable = False

    rows = len(buf)
    cols = len(buf[0]) if rows else 0
    h = len(patch)
    w = len(patch[0]) if h else 0

    # 1) Erase old footprint if we have a real background
    if background_color >= 0:
        for i in range(h):
            for j in range(w):
                if patch[i][j] != -8:
                    y = patch_min_y + i
                    x = patch_min_x + j
                    if 0 <= y < rows and 0 <= x < cols:
                        buf[y][x] = background_color

    # 2) Draw moved patch
    if background_color < 0:
        # absolute placement
        for i in range(h):
            for j in range(w):
                val = patch[i][j]
                if val != -8:
                    y = new_pos_y + i
                    x = new_pos_x + j
                    if 0 <= y < rows and 0 <= x < cols:
                        buf[y][x] = val
    else:
        # relative placement
        for i in range(h):
            for j in range(w):
                val = patch[i][j]
                if val != -8:
                    y0 = patch_min_y + i
                    x0 = patch_min_x + j
                    y = y0 + move_rel_y
                    x = x0 + move_rel_x
                    if 0 <= y < rows and 0 <= x < cols:
                        buf[y][x] = val

    result = tuple(tuple(row) for row in buf)
    return shrinkCanvas(result) if using_shrinkable else result


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

def makeShrinkableCanvas(size: int = 30) -> Grid:
    """
    Generate a square canvas of given size filled with -1 (unpainted).
    """
    return tuple(tuple(-1 for _ in range(size)) for _ in range(size))


def shrinkCanvas(canvas: Grid) -> Grid:
    """
    Remove empty bottom rows and rightmost columns (all -1) from the canvas.
    """
    # Convert to mutable rows
    rows = [list(r) for r in canvas]
    max_row = -1
    max_col = -1
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            if val != -1:
                max_row = max(max_row, i)
                max_col = max(max_col, j)
    # If nothing painted, return a 1x1 canvas of -1
    if max_row < 0 or max_col < 0:
        return ((-1,),)
    # Slice off unused bottom rows and right columns
    cropped = [tuple(row[:max_col + 1]) for row in rows[:max_row + 1]]
    return tuple(cropped)

def most_common_color(grid: Grid) -> int:
    flat = [cell for row in grid for cell in row if cell != -1]
    if not flat:
        return -1
    return Counter(flat).most_common(1)[0][0]

def paint(base: Grid, patch: Grid, top_left: Tuple[int, int], bg_color: int = -1) -> Grid:
    bi, bj = top_left

    if not isinstance(bi, int) or not isinstance(bj, int):
        print(f"⚠️ paint: invalid top_left={top_left!r}, skipping patch")
        return base

    result = [list(row) for row in base]

    for i in range(len(patch)):
        for j in range(len(patch[0])):
            val = patch[i][j]
            paint_val = bg_color if val == -1 else val
            if 0 <= bi + i < len(result) and 0 <= bj + j < len(result[0]):
                result[bi + i][bj + j] = paint_val

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
            # −8 is a wildcard, -1 is out of object or sprite
            if cell1 == -8 or cell2 == -8 or cell1 == -1 or cell2 == -1:
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

def crop(
    grid: tuple[tuple[int, ...], ...],
    minX: int | float,
    minY: int | float,
    width: int | float,
    height: int | float
) -> tuple[tuple[int, ...], ...] | None:
    # first, force everything to integers
    try:
        minX, minY, width, height = map(int, (minX, minY, width, height))
    except (ValueError, TypeError):
        print(f"⚠️ crop parameters not integers: "
              f"minX={minX}, minY={minY}, width={width}, height={height}")
        return None

    max_y = len(grid)
    max_x = len(grid[0]) if max_y > 0 else 0

    if (minX < 0 or minY < 0 or
        minX + width > max_x or
        minY + height > max_y):
        print(f"⚠️ crop bounds out of range: grid={max_y}x{max_x}, "
              f"minX={minX}, minY={minY}, width={width}, height={height}")
        return None

    # build and return a tuple-of-tuples slice
    return tuple(
        tuple(grid[minY + i][minX + j] for j in range(width))
        for i in range(height)
    )

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


def apply_all_cycles(input_grid: List[List[int]], light_cycles: List[Dict[str, Any]]) -> Grid:
    """
    Verbose version of _apply_all_cycles. Prints every intermediate check.

    1) Group actions by order_idx.
    2) For each 'start' action:
         For each (x,y) in grid, check:
           (a) pixel_rel
           (b) neighbors with strict -8 logic
           (c) row/column contexts with strict -8 logic
         Print each comparison and reason for failure or success.
    3) Simulate ticks: for each tick, show which actions apply and how each cycle moves/paints.
    """

    H = len(input_grid)
    W = len(input_grid[0]) if H > 0 else 0

    # Definition of a Cycle instance
    class CycleInst:
        def __init__(self, sx, sy, dx, dy, color, start_tick):
            self.x = sx
            self.y = sy
            self.start = (sx, sy)
            self.dx = dx
            self.dy = dy
            self.color = color
            self.active = True
            self.start_tick = start_tick

    instances: List[CycleInst] = []
    actions_by_tick: Dict[int, List[Dict[str, Any]]] = {}

    # --------------------
    # 1) Group actions by tick
    # --------------------
    #print("=== Grouping actions by 'order_idx' ===")
    for row in light_cycles:
        tick = row.get("order_idx", 0)
        if tick not in actions_by_tick:
            actions_by_tick[tick] = []
        actions_by_tick[tick].append(row)
    #for t, rows in actions_by_tick.items():
    #    print(f" Tick {t}: {len(rows)} action(s)")

    # --------------------
    # 2) Find all 'start' positions
    # --------------------
    #print("\n=== Searching for 'start' matches ===")
    for row in light_cycles:
        if row.get("action") != "start":
            continue

        # Extract row‐specific data
        pixel_rel: frozenset = row.get("common_pixel_rel", frozenset())
        common_neighbors: Dict[str, frozenset] = row.get("common_neighbors", {})
        common_rowcol:   Dict[str, frozenset] = row.get("common_rowcol", {})
        dx = row.get("direction_x", 0)
        dy = row.get("direction_y", 0)
        color_val = row.get("color")
        start_tick = row.get("order_idx", 0)

        #print(f"\n--- Processing START action at tick {start_tick}, color={color_val}, dir=({dx},{dy}) ---")
        #print(f" pixel_rel (size {len(pixel_rel)}):", pixel_rel)
        #print(f" common_neighbors:", common_neighbors)
        #print(f" common_rowcol:", common_rowcol)

        # Iterate every cell in the grid
        for y in range(H):
            for x in range(W):
                #print(f"\nChecking candidate (x={x}, y={y}):")
                ok = True

                # ---- a) Pixel_rel check ----
                #print("  (a) pixel_rel:")
                for (cval, (dx_r, dy_r)) in pixel_rel:
                    xx = x + dx_r
                    yy = y + dy_r
                    if 0 <= xx < W and 0 <= yy < H:
                        actual_c = input_grid[yy][xx]
                        #print(f"    Offset ({dx_r},{dy_r}) → position ({xx},{yy}), actual={actual_c}, required={cval}")
                        if actual_c != cval:
                            #print(f"      fail: actual {actual_c} ≠ required {cval}")
                            ok = False
                            break
                    else:
                        #print(f"    Offset ({dx_r},{dy_r}) → OOB, treat as -2, required={cval}")
                        if cval != -2:
                            #print(f"      fail: required {cval} but OOB")
                            ok = False
                            break
                if not ok:
                    continue
                #print("    pixel_rel passed")

                # ---- b) Neighbor checks (full‐ray, treat first-­step‐OOB as {-2}) ----
                #print("  (b) neighbor checks (scanning entire ray):")
                for key, (dx_n, dy_n) in {
                    'north': (0, -1),
                    'north_east': (1, -1),
                    'east': (1, 0),
                    'south_east': (1, 1),
                    'south': (0, 1),
                    'south_west': (-1, 1),
                    'west': (-1, 0),
                    'north_west': (-1, -1)
                }.items():
                    nbr_set = common_neighbors.get(key, frozenset())
                    #print(f"    Direction '{key}': expected set = {nbr_set}")

                    # (b.i) If empty set, skip constraint
                    if not nbr_set:
                        #print("      → empty set: skip entire-ray constraint")
                        continue

                    # (b.ii) If exactly {-8}, skip (wildcard for whole ray)
                    if nbr_set == {-8}:
                        #print("      → set == {-8}: skip entire-ray (wildcard)")
                        continue

                    # Otherwise, build actual_set along the ray.

                    # First, check if the very first step is OOB:
                    xx1 = x + dx_n
                    yy1 = y + dy_n
                    if not (0 <= xx1 < W and 0 <= yy1 < H):
                        # First neighbor is out-of-bounds → treat actual_set = {-2}
                        actual_set = {-2}
                        #print(f"      → first step to ({xx1},{yy1}) is OOB → actual_set = {{-2}}")
                    else:
                        # At least one in-bounds cell; collect along the ray
                        actual_set = set()
                        k = 1
                        while True:
                            xxk = x + k * dx_n
                            yyk = y + k * dy_n
                            if 0 <= xxk < W and 0 <= yyk < H:
                                c = input_grid[yyk][xxk]
                                actual_set.add(c)
                                #print(f"      → at k={k}, pos=({xxk},{yyk}), color={c}")
                                k += 1
                            else:
                                #print(f"      → reached OOB at k={k}, pos=({xxk},{yyk}); stop scanning ray")
                                break

                    # (b.iii) If -8 ∈ nbr_set (and |nbr_set| > 1),
                    #           let R = nbr_set \ {-8}, require R ⊆ actual_set
                    if -8 in nbr_set:
                        R = set(nbr_set)
                        R.discard(-8)
                        #print(f"      → -8 ∈ set, required colors R = {R} (extras allowed)")
                        if not R.issubset(actual_set):
                            missing = R - actual_set
                            #print(f"        fail: missing {missing} from actual_set {actual_set}")
                            ok = False
                            break
                        #print(f"        OK: all required {R} appear in {actual_set}")
                    else:
                        # (b.iv) No -8 at all: require exact match
                        #print(f"      → require exact match: actual_set == {nbr_set}")
                        if actual_set != set(nbr_set):
                            #print(f"        fail: actual_set {actual_set} ≠ {nbr_set}")
                            ok = False
                            break
                        #print("        OK: entire-ray exactly matches")

                if not ok:
                    continue
                #print("    All full-ray neighbor checks passed")

                # ---- c) Row/column checks ----
                def actual_row_set(ridx):
                    if 0 <= ridx < H:
                        return set(input_grid[ridx])
                    else:
                        return {-2}

                def actual_col_set(cidx):
                    if 0 <= cidx < W:
                        return {input_grid[r][cidx] for r in range(H)}
                    else:
                        return {-2}

                #print("  (c) row/column checks:")

                # prev_row
                pr_set = common_rowcol.get('prev_row', frozenset())
                #print(f"    prev_row set = {pr_set}")
                if pr_set:
                    if pr_set == {-8}:
                        actual = actual_row_set(y - 1)
                        #print(f"      → must be all OOB. actual prev_row = {actual}")
                        if actual != {-2}:
                            #print("        fail: prev_row not entirely OOB")
                            continue
                        #else:
                            #print("        OK: prev_row is OOB")
                    else:
                        actual = actual_row_set(y - 1)
                        #print(f"      → actual prev_row = {actual}")
                        if -8 in pr_set:
                            R = set(pr_set)
                            R.discard(-8)
                            #print(f"      → require R={R} ⊆ actual (extras allowed)")
                            if not R.issubset(actual):
                                #print(f"        fail: not all R appear in actual")
                                continue
                            #print("        OK: prev_row matches -8+R logic")
                        else:
                            #print(f"      → require actual == {pr_set}")
                            if actual != set(pr_set):
                                #print(f"        fail: actual {actual} ≠ {pr_set}")
                                continue
                            #print("        OK: prev_row matches exactly")

                # next_row
                nr_set = common_rowcol.get('next_row', frozenset())
                #print(f"    next_row set = {nr_set}")
                if nr_set:
                    if nr_set == {-8}:
                        actual = actual_row_set(y + 1)
                        #print(f"      → must be all OOB. actual next_row = {actual}")
                        if actual != {-2}:
                            #print("        fail: next_row not entirely OOB")
                            continue
                        #else:
                        #    print("        OK: next_row is OOB")
                    else:
                        actual = actual_row_set(y + 1)
                        #print(f"      → actual next_row = {actual}")
                        if -8 in nr_set:
                            R = set(nr_set)
                            R.discard(-8)
                            #print(f"      → require R={R} ⊆ actual (extras allowed)")
                            if not R.issubset(actual):
                                #print(f"        fail: not all R appear in actual")
                                continue
                            #print("        OK: next_row matches -8+R logic")
                        else:
                            #print(f"      → require actual == {nr_set}")
                            if actual != set(nr_set):
                                #print(f"        fail: actual {actual} ≠ {nr_set}")
                                continue
                            #print("        OK: next_row matches exactly")

                # prev_col
                pc_set = common_rowcol.get('prev_col', frozenset())
                #print(f"    prev_col set = {pc_set}")
                if pc_set:
                    if pc_set == {-8}:
                        actual = actual_col_set(x - 1)
                        #print(f"      → must be all OOB. actual prev_col = {actual}")
                        if actual != {-2}:
                            #print("        fail: prev_col not entirely OOB")
                            continue
                        #else:
                        #    print("        OK: prev_col is OOB")
                    else:
                        actual = actual_col_set(x - 1)
                        #print(f"      → actual prev_col = {actual}")
                        if -8 in pc_set:
                            R = set(pc_set)
                            R.discard(-8)
                            #print(f"      → require R={R} ⊆ actual (extras allowed)")
                            if not R.issubset(actual):
                                #print(f"        fail: not all R appear in actual")
                                continue
                            #print("        OK: prev_col matches -8+R logic")
                        else:
                            #print(f"      → require actual == {pc_set}")
                            if actual != set(pc_set):
                                #print(f"        fail: actual {actual} ≠ {pc_set}")
                                continue
                            #print("        OK: prev_col matches exactly")

                # next_col
                nc_set = common_rowcol.get('next_col', frozenset())
                #print(f"    next_col set = {nc_set}")
                if nc_set:
                    if nc_set == {-8}:
                        actual = actual_col_set(x + 1)
                        #print(f"      → must be all OOB. actual next_col = {actual}")
                        if actual != {-2}:
                            #print("        fail: next_col not entirely OOB")
                            continue
                        #else:
                        #    print("        OK: next_col is OOB")
                    else:
                        actual = actual_col_set(x + 1)
                        #print(f"      → actual next_col = {actual}")
                        if -8 in nc_set:
                            R = set(nc_set)
                            R.discard(-8)
                            #print(f"      → require R={R} ⊆ actual (extras allowed)")
                            if not R.issubset(actual):
                                #print(f"        fail: not all R appear in actual")
                                continue
                            #print("        OK: next_col matches -8+R logic")
                        else:
                            #print(f"      → require actual == {nc_set}")
                            if actual != set(nc_set):
                                #print(f"        fail: actual {actual} ≠ {nc_set}")
                                continue
                            #print("        OK: next_col matches exactly")

                # If we reach here, all conditions (a), (b), (c) passed
                #print(f"*** Found START at (x={x}, y={y}), color={color_val}, dir=({dx},{dy}) ***")
                instances.append(CycleInst(x, y, dx, dy, color_val, start_tick))

    # --------------------
    # 3) Simulate ticks, showing every move
    # --------------------
    #print("\n=== Simulating ticks ===")
    current_tick = 0
    max_tick = max(actions_by_tick.keys(), default=0)
    while True:
        #print(f"\n-- Tick {current_tick} --")
        # a) apply non-"start" actions
        tick_actions = actions_by_tick.get(current_tick, [])
        #print(f" Applying {len(tick_actions)} action(s) at this tick")
        for action_row in tick_actions:
            act = action_row.get("action")
            if act == "start":
                #print("  Skipping 'start' at tick")
                continue
            sx = action_row.get("start_x")
            sy = action_row.get("start_y")
            #print(f"  Action '{act}' for start at ({sx},{sy})")
            for inst in instances:
                if inst.start != (sx, sy):
                    continue
                #print(f"    → Found instance at {inst.start}, active={inst.active}")
                if act in ("stop", "land"):
                    inst.active = False
                    #print("      → deactivated")
                elif act == "take-off":
                    inst.active = True
                    #print("      → activated")
                elif act == "rot-left-90":
                    old = (inst.dx, inst.dy)
                    inst.dx, inst.dy = -inst.dy, inst.dx
                    #print(f"      → rotated left 90° from {old} to ({inst.dx},{inst.dy})")
                elif act == "rot-right-90":
                    old = (inst.dx, inst.dy)
                    inst.dx, inst.dy = inst.dy, -inst.dx
                    #print(f"      → rotated right 90° from {old} to ({inst.dx},{inst.dy})")
                elif act == "rot-left-45":
                    old = (inst.dx, inst.dy)
                    ndx, ndy = inst.dx - inst.dy, inst.dx + inst.dy
                    mag = max(abs(ndx), abs(ndy)) or 1
                    inst.dx, inst.dy = ndx // mag, ndy // mag
                    #print(f"      → rotated left 45° from {old} to ({inst.dx},{inst.dy})")
                elif act == "rot-right-45":
                    old = (inst.dx, inst.dy)
                    ndx, ndy = inst.dx + inst.dy, -inst.dx + inst.dy
                    mag = max(abs(ndx), abs(ndy)) or 1
                    inst.dx, inst.dy = ndx // mag, ndy // mag
                    #print(f"      → rotated right 45° from {old} to ({inst.dx},{inst.dy})")
                #else:
                #    print(f"      → (unhandled action '{act}')")

        # b) Move each active instance
        any_active = False
        for idx, inst in enumerate(instances):
            if not inst.active:
                #print(f"  Instance #{idx} at {inst.start} is inactive; skipping")
                continue
            #print(f"  Moving instance #{idx} from ({inst.x},{inst.y}) dir=({inst.dx},{inst.dy})")
            nx = inst.x + inst.dx
            ny = inst.y + inst.dy
            # OOB?
            if not (0 <= nx < W and 0 <= ny < H):
                #print(f"    → Next ({nx},{ny}) is OOB; deactivate")
                inst.active = False
                continue
            # Loops back to start?
            if (nx, ny) == inst.start:
                #print(f"    → Next ({nx},{ny}) equals start {inst.start}; deactivate")
                inst.active = False
                continue
            # Paint & move
            #print(f"    → Painting at ({nx},{ny}) with color={inst.color}")
            input_grid[ny][nx] = inst.color
            inst.x, inst.y = nx, ny
            any_active = True

        # c) Termination check
        if not any_active and current_tick >= max_tick:
            #print("  No active instances and no future actions → ending simulation")
            break

        current_tick += 1

    #print("\n=== Final grid after light cycles ===")
    #for row in input_grid:
    #    print(" ", row)
    return input_grid

def apply_ca(input_grid: List[List[int]], ca_rules: List[Dict]) -> List[List[int]]:
    def get_neighborhood(grid, x, y, bg=0):
        """
        Return the 3×3 neighborhood around (x,y) as a length-9 tuple in row-major order:
          (nw, n, ne, w, center, e, sw, s, se).
        Out-of-bounds cells are filled with `bg`.
        """
        H, W = len(grid), len(grid[0])
        nbr = []
        for dy in (-1, 0, +1):
            for dx in (-1, 0, +1):
                ny, nx = y + dy, x + dx
                nbr.append(grid[ny][nx] if 0 <= ny < H and 0 <= nx < W else bg)
        return tuple(nbr)

    def canonical(nbr):
        """
        If orientation_invariant, pick the lexicographically smallest of
        all 8 dihedral variants (4 rotations + 4 horizontal flips).
        """
        rots = all_rotations(nbr)
        flips = [tuple(r[i] for i in [2, 1, 0, 5, 4, 3, 8, 7, 6]) for r in rots]
        return min(rots + flips)

    def rotate90(nbr):
        """Rotate a flattened 3×3 neighborhood 90° clockwise."""
        mapping = [6, 3, 0, 7, 4, 1, 8, 5, 2]
        return tuple(nbr[i] for i in mapping)

    def all_rotations(nbr):
        r0 = nbr
        r1 = rotate90(r0)
        r2 = rotate90(r1)
        r3 = rotate90(r2)
        return [r0, r1, r2, r3]

    # Reconstruct rule_dict
    rule_dict: Dict[Tuple[int,...], int] = {}
    for rule in ca_rules:
        center = rule['input_color']
        out_col = rule['output_color']
        # build neighborhood tuple
        nbr = [0]*9
        nbr[4] = center
        for dx, dy, color in rule['neighbors']:
            idx = (dy+1)*3 + (dx+1)
            nbr[idx] = color
        # canonical form
        key = canonical(tuple(nbr))
        rule_dict[key] = out_col
    # apply
    H, W = len(input_grid), len(input_grid[0])
    result = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            nbr = get_neighborhood(input_grid, x, y, bg=0)
            key = canonical(nbr)
            result[y][x] = rule_dict.get(key, input_grid[y][x])
    return result


def select_conditional_object(
    trainId: int,
    testId:  int,
    conditionalObjects: List[Dict[str, Any]],
    tables:   Dict[str, Dict[int, Dict[str, Any]]]
) -> List[List[int]]:
    """
    Given trainId/testId and a list of candidate dicts (with
    'criteria_first_sight', 'criteria_sprite_grid', and 'object_data'),
    use the in-memory tables from current_rule.tables to fetch the
    corresponding first_sight_analysis and sprite_analysis rows,
    then score and return the best-matching object_data grid.
    """
    if len(conditionalObjects) == 0:
        return None

    # pull the in-memory tables
    fsa_table = tables["first_sight_analysis"]
    sa_table  = tables["sprite_analysis"]

    # 1) find the single FSA row for this train/test
    fsa_row = next(
        row for row in fsa_table.values()
        if row.get("trainId")==trainId and row.get("testId")==testId
    )

    # 2) find the single SA row (input-grid only) for this train/test
    sa_row = next(
        row for row in sa_table.values()
        if row.get("trainId")==trainId
           and row.get("testId")==testId
           and row.get("isInsideInput")==1
           and row.get("isGrid")==1
    )

    # 3) score each candidate
    best_score  = -1
    best_object = None
    for cand in conditionalObjects:
        score = 0
        for col, val in cand["criteria_first_sight"]:
            if fsa_row.get(col) == val:
                score += 1
        for col, val in cand["criteria_sprite_grid"]:
            if sa_row.get(col) == val:
                score += 1
        if score > best_score:
            best_score  = score
            best_object = cand

    # fallback
    if best_object is None:
        best_object = conditionalObjects[0]

    # 3) compute bounding box of the object’s pixels
    obj_pixels = best_object["object_data"]  # list of [x,y]
    xs = [x for x, y in obj_pixels]
    ys = [y for x, y in obj_pixels]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x + 1
    height = max_y - min_y + 1

    # 4) render a new grid of that size
    color = best_object["color"]
    result = [[-1 for _ in range(width)] for _ in range(height)]
    for x, y in obj_pixels:
        if 0 <= x < width and 0 <= y < height:
            result[y][x] = color

    # todo : apply rotation / flip

    return result



if __name__ == '__main__':
    print(grid_to_pretty_string(to_concrete_grid(
        [[0, [1, 9]], [4, [0, 11]], [2, [1, 3]], [4, [1, 0]], [4, [1, 6]], [0, [0, 2]], [2, [1, 2]], [0, [1, 4]],
         [4, [0, 6]], [4, [1, 1]], [2, [0, 8]], [4, [0, 5]], [2, [1, 8]], [2, [0, 3]], [4, [0, 0]], [0, [0, 9]],
         [4, [1, 11]], [2, [1, 7]], [0, [0, 4]], [4, [1, 10]], [4, [0, 1]], [4, [0, 10]], [4, [1, 5]], [0, [0, 7]]]
    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[1, [0, 1]], [0, [1, 9]], [1, [0, 10]], [2, [1, 3]], [0, [1, 2]], [1, [1, 10]], [0, [0, 2]], [1, [1, 5]],
         [0, [1, 4]], [1, [1, 0]], [2, [0, 8]], [1, [0, 11]], [1, [1, 6]], [2, [0, 3]], [1, [0, 6]], [1, [1, 1]],
         [2, [0, 9]], [0, [1, 7]], [1, [0, 5]], [2, [0, 4]], [1, [0, 0]], [2, [1, 8]], [1, [1, 11]], [0, [0, 7]]]
    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[1, [2, 0]], [0, [0, 0]], [1, [1, 1]], [0, [1, 2]], [1, [1, 0]], [0, [2, 2]], [1, [2, 1]]]
    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[0, [4, 5]], [0, [0, 3]], [0, [1, 5]], [0, [4, 0]], [4, [0, 2]], [1, [4, 3]], [0, [1, 0]], [1, [4, 4]],
         [0, [2, 2]], [0, [0, 5]], [0, [0, 0]], [0, [3, 5]], [0, [2, 3]], [0, [3, 0]], [4, [1, 1]], [1, [3, 3]],
         [4, [1, 2]], [0, [4, 2]], [1, [3, 4]], [4, [0, 1]]]
    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[4, [1, 2]], [0, [0, 0]], [4, [0, 2]], [0, [1, 0]], [4, [0, 1]], [4, [1, 1]], [0, [2, 2]]]
    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[0, [4, 5]], [0, [0, 3]], [0, [1, 5]], [0, [4, 0]], [4, [0, 2]], [1, [4, 3]], [0, [1, 0]], [1, [4, 4]], [0, [2, 2]], [0, [0, 5]], [0, [0, 0]], [0, [3, 5]], [0, [2, 3]], [0, [3, 0]], [4, [1, 1]], [1, [3, 3]], [4, [1, 2]], [0, [4, 2]], [1, [3, 4]], [4, [0, 1]]]

    )))
    print(grid_to_pretty_string(to_concrete_grid(
        [[1, [4, 6]], [0, [4, 4]], [4, [1, 13]], [0, [0, 2]], [1, [3, 6]], [0, [3, 7]], [4, [1, 8]], [4, [1, 14]], [0, [4, 14]], [2, [3, 13]], [2, [1, 10]], [4, [1, 3]], [2, [3, 8]], [2, [2, 6]], [4, [0, 8]], [2, [1, 6]], [4, [0, 14]], [0, [0, 5]], [2, [1, 1]], [2, [3, 4]], [2, [2, 2]], [2, [2, 13]], [1, [4, 5]], [4, [0, 4]], [1, [4, 0]], [0, [4, 12]], [1, [4, 1]], [0, [4, 2]], [0, [1, 7]], [0, [3, 2]], [2, [0, 11]], [0, [2, 14]], [2, [4, 8]], [1, [3, 5]], [0, [4, 9]], [0, [0, 12]], [2, [4, 3]], [1, [3, 0]], [0, [3, 12]], [0, [2, 10]], [1, [3, 1]], [4, [1, 9]], [2, [2, 11]], [2, [1, 5]], [1, [3, 11]], [4, [0, 13]], [2, [3, 14]], [4, [1, 4]], [2, [2, 12]], [2, [3, 3]], [2, [1, 0]], [2, [2, 1]], [4, [0, 3]], [2, [3, 9]], [2, [2, 7]], [4, [0, 9]], [0, [0, 0]], [0, [1, 2]], [2, [2, 8]], [2, [1, 11]], [0, [2, 9]], [2, [2, 3]], [0, [0, 10]], [2, [0, 1]], [0, [2, 4]], [0, [4, 7]], [0, [1, 12]], [1, [4, 10]], [2, [4, 13]], [0, [2, 5]], [1, [3, 10]], [1, [4, 11]], [2, [0, 6]], [0, [2, 0]], [0, [0, 7]]]

    )))








