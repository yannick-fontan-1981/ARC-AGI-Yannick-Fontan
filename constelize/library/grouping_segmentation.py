from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding
from typing import FrozenSet, Tuple

Grid = Tuple[Tuple[int]]
Object = FrozenSet[Tuple[int, Tuple[int, int]]]
Objects = FrozenSet[Object]

def objects(grid: Grid, univalued: bool, diagonal: bool, without_bg: bool) -> Objects:
    from collections import deque

    h, w = len(grid), len(grid[0])
    visited = set()
    objects = set()
    bg = max(set(v for row in grid for v in row), key=lambda v: sum(r.count(v) for r in grid)) if without_bg else None

    def neighbors(i, j):
        for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            yield i + di, j + dj
        if diagonal:
            for di, dj in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                yield i + di, j + dj

    for i in range(h):
        for j in range(w):
            if (i, j) in visited:
                continue
            val = grid[i][j]
            if without_bg and val == bg:
                continue
            obj = set()
            queue = deque([(i, j)])
            while queue:
                x, y = queue.popleft()
                if (x, y) in visited:
                    continue
                if not (0 <= x < h and 0 <= y < w):
                    continue
                v = grid[x][y]
                if (univalued and v != val) or (without_bg and v == bg):
                    continue
                visited.add((x, y))
                obj.add((v, (x, y)))
                queue.extend(neighbors(x, y))
            if obj:
                objects.add(frozenset(obj))
    return frozenset(objects)

def partition(grid: Grid) -> Objects:
    palette = {v for row in grid for v in row}
    return frozenset(
        frozenset((v, (i, j)) for i, row in enumerate(grid) for j, val in enumerate(row) if val == v)
        for v in palette
    )

def fgpartition(grid: Grid) -> Objects:
    palette = {v for row in grid for v in row}
    bg = max(palette, key=lambda v: sum(r.count(v) for r in grid))
    return frozenset(
        frozenset((v, (i, j)) for i, row in enumerate(grid) for j, val in enumerate(row) if val == v)
        for v in palette if v != bg
    )

def group_by_color(grid: Grid) -> Objects:
    return partition(grid)

ACTIONS = [
    Action(
        id="connected_components",
        name="Connected Components",
        category=ActionCategory.GROUPING_SEGMENTATION,
        function=objects,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid"),
            ArgumentBinding(name="univalued", type="Boolean"),
            ArgumentBinding(name="diagonal", type="Boolean"),
            ArgumentBinding(name="without_bg", type="Boolean")
        ],
        output_type="Objects",
        description="Find connected objects in the grid using connectivity rules."
    ),
    Action(
        id="partition_by_color",
        name="Partition by Color",
        category=ActionCategory.GROUPING_SEGMENTATION,
        function=partition,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Objects",
        description="Partition grid so that each color becomes a separate object."
    ),
    Action(
        id="foreground_partition",
        name="Foreground Partition",
        category=ActionCategory.GROUPING_SEGMENTATION,
        function=fgpartition,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Objects",
        description="Like partition, but excludes background color."
    ),
    Action(
        id="group_by_color",
        name="Group by Color",
        category=ActionCategory.GROUPING_SEGMENTATION,
        function=group_by_color,
        input_arguments=[
            ArgumentBinding(name="grid", type="Grid")
        ],
        output_type="Objects",
        description="Alias for partitioning the grid by color value."
    ),
]