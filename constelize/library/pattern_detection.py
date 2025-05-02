from collections import defaultdict

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
    )
]