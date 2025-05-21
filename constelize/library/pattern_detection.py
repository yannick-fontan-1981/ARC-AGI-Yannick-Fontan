from collections import defaultdict, Counter

from constelize.core.action import Action
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.categories import ActionCategory
from constelize.tools import globals as GLOBAL

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


def group_similar(lines, min_group_size=3, similarity_threshold=0.7):
    """
    Groups similar lines (rows/columns) based on pixel similarity.
    Returns a list of groups, each containing indices of similar lines.
    """
    groups = []
    n = len(lines)
    visited = set()

    for i in range(n):
        if i in visited:
            continue
        current_group = [i]
        for j in range(i + 1, n):
            if j in visited:
                continue
            matches = sum(1 for a, b in zip(lines[i], lines[j]) if a == b)
            similarity = matches / len(lines[i])
            if similarity >= similarity_threshold:
                current_group.append(j)
                visited.add(j)
        if len(current_group) >= min_group_size:
            groups.append(current_group)
            visited.update(current_group)
    return groups

def detect_noise(grid):
    """
    Identifies noisy pixels and their intended correct color using row/column groups.
    Returns a dictionary: {(i, j): correct_color}.
    """
    # ── dimension guard ────────────────────────────────────────────────────────
    if len(grid) < 9 or not grid or len(grid[0]) < 9:
        return {}

    rows = grid
    cols = list(zip(*grid))  # Transpose to get columns

    noise_map = {}

    # Detect noise from row groups
    row_groups = group_similar(rows)
    for group in row_groups:
        for col_idx in range(len(rows[0])):
            # Get all values in this column across the grouped rows
            values = [rows[row_idx][col_idx] for row_idx in group]
            freq = defaultdict(int)
            for v in values:
                freq[v] += 1
            max_freq = max(freq.values(), default=0)
            # Determine the correct color (mode)
            correct_color = None
            candidates = [k for k, v in freq.items() if v == max_freq]
            if candidates:
                correct_color = min(candidates)  # Tiebreaker: smallest value
            # Mark deviating pixels as noise with the correct color
            for row_idx in group:
                if rows[row_idx][col_idx] != correct_color:
                    noise_map[(row_idx, col_idx)] = correct_color

    # Detect noise from column groups
    col_groups = group_similar(cols)
    for group in col_groups:
        for row_idx in range(len(cols[0])):
            # Get all values in this row across the grouped columns
            values = [cols[col_idx][row_idx] for col_idx in group]
            freq = defaultdict(int)
            for v in values:
                freq[v] += 1
            max_freq = max(freq.values(), default=0)
            # Determine the correct color (mode)
            correct_color = None
            candidates = [k for k, v in freq.items() if v == max_freq]
            if candidates:
                correct_color = min(candidates)
            # Mark deviating pixels as noise with the correct color
            for col_idx in group:
                if cols[col_idx][row_idx] != correct_color:
                    noise_map[(row_idx, col_idx)] = correct_color

    return noise_map

def denoise_grid(grid, noise_map):
    """
    Corrects noisy pixels using the noise_map.
    """
    corrected_grid = [row.copy() for row in grid]
    for (i, j), correct_color in noise_map.items():
        corrected_grid[i][j] = correct_color
    return corrected_grid

def denoise(grid):
    noise_map = detect_noise(grid)
    return denoise_grid(grid, noise_map)


def apply_symmetry_fill(grid, isH, isV, holes):
    """
    Fill only the specified hole coordinates in `grid` by reflecting across
    the horizontal axis if `isH`, or vertical axis if `isV`. When the
    horizontal source itself is a hole, fallback to vertical, and vice versa.
    Verbose logs each fill operation.
    """
    h = len(grid)
    w = len(grid[0]) if h else 0
    new = [list(row) for row in grid]
    print(f"   🧩 Applying symmetry fill: isHorizontal={isH}, isVertical={isV}, holes={holes}")
    holes_set = set(holes)
    for (i, j) in holes:
        hsrc = (i, w - 1 - j)
        vsrc = (h - 1 - i, j)
        # horizontal mirror with fallback
        if isH:
            if hsrc not in holes_set:
                fill_val = grid[hsrc[0]][hsrc[1]]
                #print(f"     ↔️ Horizontal fill at ({i},{j}) from {hsrc} = {fill_val}")
                new[i][j] = fill_val
            else:
                fill_val = grid[vsrc[0]][vsrc[1]]
                #print(f"     ↕️ Fallback to Vertical fill at ({i},{j}) from {vsrc} = {fill_val}")
                new[i][j] = fill_val
        # vertical mirror with fallback
        if isV:
            if vsrc not in holes_set:
                fill_val = grid[vsrc[0]][vsrc[1]]
                #print(f"     ↕️ Vertical fill at ({i},{j}) from {vsrc} = {fill_val}")
                new[i][j] = fill_val
            else:
                fill_val = grid[hsrc[0]][hsrc[1]]
                #print(f"     ↔️ Fallback to Horizontal fill at ({i},{j}) from {hsrc} = {fill_val}")
                new[i][j] = fill_val
    filled = tuple(tuple(r) for r in new)
    return filled


def extract_connected_components(grid, seeds):
    """
    From the seeds marking corrected holes, cluster positions
    and extract a single sprite containing all connected seeds of same color.
    Returns a list with one sprite grid. Verbose logs cluster steps.
    """
    print(f"   🗂️ Extracting connected components from seeds={seeds}")
    if not seeds:
        print("   ⚠️ No seeds provided, returning empty list")
        return []
    comp = set()
    hull = list(seeds)
    while hull:
        i, j = hull.pop()
        if (i, j) in comp:
            continue
        comp.add((i, j))
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
            ni, nj = i + di, j + dj
            if (ni, nj) in seeds and (ni, nj) not in comp:
                hull.append((ni, nj))
    print(f"   ✅ Clustered {len(comp)} seed positions into component")
    rows = [i for i, _ in comp]
    cols = [j for _, j in comp]
    min_i, max_i = min(rows), max(rows)
    min_j, max_j = min(cols), max(cols)
    print(f"   📐 Bounding box rows {min_i}-{max_i}, cols {min_j}-{max_j}")
    sprite = []
    for i in range(min_i, max_i + 1):
        row = []
        for j in range(min_j, max_j + 1):
            val = grid[i][j] if (i, j) in comp else -1
            row.append(val)
        sprite.append(tuple(row))
    sprite_grid = tuple(sprite)
    #print("   🖼️ Extracted sprite:")
    #print(grid_to_pretty_string(sprite_grid))
    return [sprite_grid]

def auto_fix_symmetry(grid, scenarioId, trainId, testId):
    """
    Detects ≥75% horizontal or vertical symmetry in `grid`.
    If found, collects mismatched pixels (holes), filters to the dominant hole‐color,
    fills them by mirroring, extracts the corrected hole‐sprites (new_sprites),
    stores them in GLOBAL.all_scenarios[scenarioId].new_sprites under key “{trainId}#{testId}”,
    and returns the filled grid. Otherwise returns the original.
    """
    h = len(grid)
    w = len(grid[0]) if h else 0

    # 1) symmetry percentages
    sym_rows = sum(all(row[j] == row[w-1-j] for j in range(w)) for row in grid)
    sym_cols = sum(all(grid[i][j] == grid[h-1-i][j] for i in range(h)) for j in range(w))
    pct_rows = sym_rows / h if h else 0
    pct_cols = sym_cols / w if w else 0
    isH, isV = pct_rows >= 0.75, pct_cols >= 0.75
    if not (isH or isV):
        return grid

    # 2) collect mismatches
    holes_H = [(i, j) for i in range(h) for j in range(w)
               if isH and grid[i][j] != grid[i][w-1-j]]
    holes_V = [(i, j) for i in range(h) for j in range(w)
               if isV and grid[i][j] != grid[h-1-i][j]]
    merged = holes_H + holes_V
    if not merged:
        return grid

    # 3) filter to dominant hole-color
    colors = [grid[i][j] for (i, j) in merged]
    mode_color, _ = Counter(colors).most_common(1)[0]
    holes = [(i, j) for (i, j) in merged if grid[i][j] == mode_color]
    if not holes:
        return grid

    # 4) fill holes
    fixed = apply_symmetry_fill(grid, isH, isV, holes)

    # 5) extract corrected hole‐sprites and record as new_sprites
    new_sprites = extract_connected_components(fixed, holes)
    sc = next((s for s in GLOBAL.all_scenarios if s.id == scenarioId), None)
    if sc is not None:
        sc.new_sprites[f"{trainId}#{testId}"] = new_sprites

    return fixed


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
    ),
    Action(
        id="denoise",
        name="Denoise Grid",
        description=(
            "Detect and correct noisy pixels by grouping similar rows/columns "
            "and replacing outliers with the majority color."
        ),
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(
                name="grid",
                type="Grid",
                binding=BindingStatus.INPUT_GRID
            )
        ],
        output_type="Grid",
        function=denoise  # calls detect_noise + denoise_grid internally
    ),
    Action(
        id="fix_symmetry",
        name="Fix Symmetry",
        description=(
            "Detects and fills missing pixels (holes) in a grid to restore "
            "horizontal and/or vertical symmetry around the given axes."
        ),
        category=ActionCategory.PATTERN_DETECTION,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.INPUT_GRID),
            ArgumentBinding(name="scenarioId", type="String", binding=BindingStatus.INSTANCE),
            ArgumentBinding(name="trainId", type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="testId", type="Integer", binding=BindingStatus.CONTEXT),
        ],
        output_type="Grid",
        function=auto_fix_symmetry,
        deterministic=True,
        pure=True,
    )
]