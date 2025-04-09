# Declare the global variable _bg
_bg = None

def get_vertical_line_candidates(grid):
    """
    Return a dict: color -> set of column indices
    where each col (1..w-2) is uniform in that color from top to bottom,
    and grid[0][col] == grid[h-1][col].
    (No adjacency check yet—just uniform color and matching top/bottom.)
    """
    h = len(grid)
    w = len(grid[0])
    vertical = {}
    # We skip the outermost columns (0 and w-1), based on your tests.
    for col in range(1, w - 1):
        c = grid[0][col]
        if c == grid[h - 1][col]:
            # Check if entire column is color c
            if all(grid[r][col] == c for r in range(h)):
                vertical.setdefault(c, set()).add(col)
    return vertical


def get_horizontal_line_candidates(grid):
    """
    Return a dict: color -> set of row indices
    where each row (1..h-2) is uniform in that color from left to right,
    and grid[row][0] == grid[row][w-1].
    (No adjacency check yet—just uniform color and matching left/right.)
    """
    h = len(grid)
    w = len(grid[0])
    horizontal = {}
    # We skip the outermost rows (0 and h-1), based on your tests.
    for row in range(1, h - 1):
        c = grid[row][0]
        if c == grid[row][w - 1]:
            # Check if entire row is color c
            if all(grid[row][col] == c for col in range(w)):
                horizontal.setdefault(c, set()).add(row)
    return horizontal


def is_thin_vertical_line_ignoring_horizontal_lines(grid, col, color, horizontal_rows_same_color):
    """
    For a vertical candidate line at column `col` (already known uniform in `color`),
    check single-pixel-wide adjacency except where it intersects any horizontal
    line of the same color.

    - For each row r, if r is NOT in horizontal_rows_same_color, then
      grid[r][col-1] and grid[r][col+1] must differ from `color`.
    - If r IS in horizontal_rows_same_color, skip adjacency checks there
      (it's the intersection).
    """
    h = len(grid)
    w = len(grid[0])
    for r in range(h):
        # Must remain uniform color
        if grid[r][col] != color:
            return False

        if r in horizontal_rows_same_color:
            # Intersection with a horizontal line of same color => skip adjacency checks
            continue

        # Otherwise, must be single-pixel-wide => neighbors differ
        if grid[r][col - 1] == color:
            return False
        if grid[r][col + 1] == color:
            return False

    return True


def is_thin_horizontal_line_ignoring_vertical_lines(grid, row, color, vertical_cols_same_color):
    """
    For a horizontal candidate line at row `row` (already known uniform in `color`),
    check single-pixel-wide adjacency except where it intersects any vertical
    line of the same color.

    - For each column c, if c is NOT in vertical_cols_same_color, then
      grid[row-1][c] and grid[row+1][c] must differ from `color`.
    - If c IS in vertical_cols_same_color, skip adjacency checks for that cell.
    """
    h = len(grid)
    w = len(grid[0])
    for c in range(w):
        # Must remain uniform color
        if grid[row][c] != color:
            return False

        if c in vertical_cols_same_color:
            # Intersection => skip adjacency checks
            continue

        # Otherwise, check neighbors differ
        if grid[row - 1][c] == color:
            return False
        if grid[row + 1][c] == color:
            return False

    return True


def has_thin_separating_lines(grid):
    """
    Return True if there is at least one thin line (vertical or horizontal),
    and ALL such lines share exactly one color. Sets _bg to that color.
    Otherwise, return False.

    "Thin" means single-pixel-wide adjacency, allowing intersection
    among lines of the same color (we skip adjacency checks at intersection).
    """
    global _bg

    # 1) Gather uniform-line candidates by color (no adjacency check yet)
    vert_candidates = get_vertical_line_candidates(grid)
    horiz_candidates = get_horizontal_line_candidates(grid)

    # 2) Collect all colors that appear as at least one candidate line
    all_colors = set(vert_candidates.keys()) | set(horiz_candidates.keys())
    if not all_colors:
        return False  # No lines at all

    # If more than one color => your tests say "False"
    if len(all_colors) > 1:
        return False

    # Exactly one color
    (unique_color,) = all_colors
    vertical_cols = vert_candidates.get(unique_color, set())
    horizontal_rows = horiz_candidates.get(unique_color, set())

    # Must have at least one line in that color
    if not vertical_cols and not horizontal_rows:
        return False

    # 3) Check adjacency ignoring intersections among lines of the same color
    #    For each vertical line, skip adjacency checks at rows that are horizontal lines of the same color
    for col in vertical_cols:
        if not is_thin_vertical_line_ignoring_horizontal_lines(
            grid, col, unique_color, horizontal_rows
        ):
            return False

    #    For each horizontal line, skip adjacency checks at columns that are vertical lines of the same color
    for row in horizontal_rows:
        if not is_thin_horizontal_line_ignoring_vertical_lines(
            grid, row, unique_color, vertical_cols
        ):
            return False

    # If all lines pass adjacency, success
    _bg = unique_color
    return True


def has_thin_crossing_lines(grid):
    """
    Return True if there is at least one vertical line and at least one horizontal line
    of the SAME color that are each single-pixel-wide (allowing them to intersect).
    Sets _bg to that color if found. Otherwise return False.
    """
    global _bg

    vert_candidates = get_vertical_line_candidates(grid)
    horiz_candidates = get_horizontal_line_candidates(grid)

    # We only succeed if there's at least one color in common
    crossing_colors = set(vert_candidates.keys()) & set(horiz_candidates.keys())
    if not crossing_colors:
        return False

    # For each color in the intersection, try pairing each vertical col with each horizontal row
    for color in crossing_colors:
        vertical_cols = vert_candidates[color]
        horizontal_rows = horiz_candidates[color]
        for col in vertical_cols:
            for row in horizontal_rows:
                # Check adjacency ignoring intersection (row, col)
                # Actually we skip adjacency at *all* rows in horizontal_rows
                # for that vertical line, and skip adjacency at *all* cols in vertical_cols
                # for that horizontal line => that definitely covers the intersection cell.
                v_ok = is_thin_vertical_line_ignoring_horizontal_lines(
                    grid, col, color, horizontal_rows
                )
                h_ok = is_thin_horizontal_line_ignoring_vertical_lines(
                    grid, row, color, vertical_cols
                )
                if v_ok and h_ok:
                    # Found at least one crossing pair that is truly thin
                    _bg = color
                    return True

    return False


def verify_has_thin_lines():
    global _bg  # Use the global variable

    test_cases = [
        {
            "grid": [
                [0, 1, 0, 0],
                [0, 1, 0, 0],
                [0, 1, 0, 0],
                [0, 1, 0, 0]
            ],
            "expected_separating": True,
            "expected_crossing": False,
            "expected_bg": 1,
            "description": "Vertical 1-pixel wide line, no crossing"
        },
        {
            "grid": [
                [0, 1, 0, 0],
                [0, 1, 0, 0],
                [1, 1, 1, 1],  # Horizontal line at bottom
                [0, 1, 0, 0]
            ],
            "expected_separating": True,
            "expected_crossing": True,
            "expected_bg": 1,
            "description": "Crossing lines with same color"
        },
        {
            "grid": [
                [0, 3, 0, 0],
                [0, 3, 0, 0],
                [0, 3, 0, 0],
                [0, 3, 0, 0]
            ],
            "expected_separating": True,
            "expected_crossing": False,
            "expected_bg": 3,
            "description": "Vertical line only, color 3"
        },
        {
            "grid": [
                [0, 2, 0, 0],
                [0, 2, 0, 0],
                [3, 3, 3, 3],  # Horizontal line (color 3)
                [0, 2, 0, 0]
            ],
            "expected_separating": True,  # Two different colors (2 and 3)
            "expected_crossing": False,
            "expected_bg": 3,
            "description": "crossing of two different color"
        },
        {
            "grid": [
                [4, 4, 4, 4],
                [4, 0, 0, 4],
                [4, 0, 0, 4],
                [4, 4, 4, 4]
            ],
            "expected_separating": False,
            "expected_crossing": False,
            "expected_bg": None,
            "description": "no separation, all lines at border"
        },
        {
            "grid": [
                [1, 1, 1, 1],
                [1, 0, 0, 1],
                [1, 0, 0, 1],
                [1, 1, 1, 1]
            ],
            "expected_separating": False,
            "expected_crossing": False,
            "expected_bg": None,
            "description": "Perfect cross with color 1"
        },
        {
            "grid": [
                [5, 5, 5, 5],
                [5, 0, 5, 5],
                [5, 0, 5, 5],
                [5, 5, 5, 5]
            ],
            "expected_separating": False,
            "expected_crossing": False,
            "expected_bg": None,
            "description": "Gaps in the vertical line (should fail)"
        }
    ]

    for i, case in enumerate(test_cases):
        # Reset _bg before each test
        _bg = None

        result_separating = has_thin_separating_lines(case["grid"])
        result_crossing = has_thin_crossing_lines(case["grid"])
        result_bg = _bg

        print(f"Test {i}: {case['description']}")
        if result_separating == case["expected_separating"]:
            print("  ✅ has_thin_separating_lines passed")
        else:
            print(f"  ❌ has_thin_separating_lines failed "
                  f"(expected {case['expected_separating']}, got {result_separating})")

        if result_crossing == case["expected_crossing"]:
            print("  ✅ has_thin_crossing_lines passed")
        else:
            print(f"  ❌ has_thin_crossing_lines failed "
                  f"(expected {case['expected_crossing']}, got {result_crossing})")

        if result_bg == case["expected_bg"]:
            print(f"  ✅ _bg correctly set to {result_bg}")
        else:
            print(f"  ❌ _bg incorrect (expected {case['expected_bg']}, got {result_bg})")

        print()  # Blank line for readability


if __name__ == "__main__":
    verify_has_thin_lines()
