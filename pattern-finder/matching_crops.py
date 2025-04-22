from collections import defaultdict, namedtuple
from typing import List, Tuple, Dict, Callable
import time

# Import transformation functions
from constelize.dsl.grid_dsl import rot90, rot180, rot270, hmirror, vmirror

# Type aliases
Coord = Tuple[int, int]
Transform = namedtuple('Transform', ['geometry', 'recolor_map'])

# Define geometric transforms
_GEOMETRY_TRANSFORMS: List[Tuple[str, Callable]] = [
    ('identity', lambda g: g),
    ('rot90', rot90),
    ('rot180', rot180),
    ('rot270', rot270),
    ('flip_h', hmirror),
    ('flip_v', vmirror),
    ('rot90_flip_h', lambda g: hmirror(rot90(g))),
    ('rot90_flip_v', lambda g: vmirror(rot90(g))),
]

# Maximum difference in crop dimensions
MAX_DIFF = 14  # allow up to MAX_DIFF pixels less in width and/or height relative to smallest grid


def _canonicalize_colors(grid: Tuple[Tuple[int, ...], ...]) -> Tuple[Tuple[int, ...], ...]:
    mapping: Dict[int, int] = {}
    next_label = 0
    canon = []
    for row in grid:
        cres = []
        for c in row:
            if c not in mapping:
                mapping[c] = next_label
                next_label += 1
            cres.append(mapping[c])
        canon.append(tuple(cres))
    return tuple(canon)


def find_matching_crops(
    input_grid: Tuple[Tuple[int, ...], ...],
    output_grid: Tuple[Tuple[int, ...], ...],
    allow_rotate: bool = True,
    allow_recolor: bool = True
) -> List[Tuple[Coord, Coord, Transform]]:
    transforms = _GEOMETRY_TRANSFORMS if allow_rotate else [('identity', lambda g: g)]

    in_h, in_w = len(input_grid), len(input_grid[0]) if input_grid else 0
    out_h, out_w = len(output_grid), len(output_grid[0]) if output_grid else 0
    # determine large vs small grid
    if in_h * in_w >= out_h * out_w:
        large_grid, small_grid = input_grid, output_grid
    else:
        large_grid, small_grid = output_grid, input_grid

    lg_h, lg_w = len(large_grid), len(large_grid[0]) if large_grid else 0
    sm_h, sm_w = len(small_grid), len(small_grid[0]) if small_grid else 0

    # allowed crop sizes: between full small size and minus MAX_DIFF
    min_h = max(2, sm_h - MAX_DIFF)
    min_w = max(2, sm_w - MAX_DIFF)
    max_h, max_w = sm_h, sm_w

    # index all small-grid sub-crops
    small_index = defaultdict(lambda: defaultdict(list))
    for i in range(sm_h - min_h + 1):
        for j in range(sm_w - min_w + 1):
            for h in range(min_h, max_h + 1):
                if i + h > sm_h: break
                for w in range(min_w, max_w + 1):
                    if j + w > sm_w: break
                    sub = tuple(row[j:j+w] for row in small_grid[i:i+h])
                    key = _canonicalize_colors(sub) if allow_recolor else sub
                    small_index[(h, w)][key].append((i, j))

    matches = []
    # scan large grid for matching crops
    for li in range(lg_h - min_h + 1):
        for lj in range(lg_w - min_w + 1):
            for h in range(min_h, max_h + 1):
                if li + h > lg_h: break
                for w in range(min_w, max_w + 1):
                    if lj + w > lg_w: break
                    raw = tuple(r[lj:lj+w] for r in large_grid[li:li+h])
                    for geom_name, geom_fn in transforms:
                        th, tw = (w, h) if 'rot90' in geom_name or 'rot270' in geom_name else (h, w)
                        if not (min_h <= th <= max_h and min_w <= tw <= max_w):
                            continue
                        try:
                            trans = geom_fn(raw)
                        except Exception:
                            continue
                        key = _canonicalize_colors(trans) if allow_recolor else trans
                        coords = small_index.get((th, tw), {}).get(key)
                        if not coords:
                            continue
                        si, sj = coords[0]
                        recolor_map = {}
                        if allow_recolor:
                            sub_small = tuple(r[sj:sj+tw] for r in small_grid[si:si+th])
                            for y in range(th):
                                for x in range(tw):
                                    recolor_map[trans[y][x]] = sub_small[y][x]
                        t = Transform(geometry=geom_name, recolor_map=recolor_map)
                        matches.append(((li, lj), (si, sj), t))
    return matches


def _to_tuple_grid(grid: List[List[int]]) -> Tuple[Tuple[int, ...], ...]:
    return tuple(tuple(row) for row in grid)


def safe_crop(
    grid: Tuple[Tuple[int, ...], ...],
    top: int, left: int,
    H: int, W: int
) -> List[List[int]]:
    bottom = min(top + H, len(grid))
    right = min(left + W, len(grid[0]))
    return [list(row[left:right]) for row in grid[top:bottom]]


if __name__ == '__main__':
    # sample grids
    # sample grids
    list_input = [
        [3, 3, 3, 5, 4, 3, 3, 2, 3, 2, 4, 1, 4, 3],
        [4, 0, 0, 0, 2, 3, 0, 0, 5, 3, 2, 2, 1, 1],
        [4, 5, 5, 5, 0, 1, 1, 4, 3, 2, 5, 0, 2, 4],
        [5, 0, 0, 0, 0, 2, 4, 5, 1, 4, 5, 5, 2, 0],
        [2, 4, 2, 2, 4, 1, 1, 5, 3, 3, 3, 5, 0, 0],
        [2, 4, 0, 0, 2, 4, 5, 4, 2, 5, 5, 2, 0, 5],
        [2, 1, 1, 5, 1, 4, 4, 3, 4, 1, 3, 3, 2, 4],
        [5, 1, 0, 2, 0, 5, 4, 0, 3, 5, 3, 2, 4, 1],
        [3, 0, 5, 5, 5, 4, 0, 0, 2, 2, 2, 5, 1, 2],
        [1, 4, 1, 4, 0, 0, 0, 3, 1, 3, 0, 4, 3, 0],
        [4, 1, 4, 0, 0, 0, 3, 0, 4, 1, 4, 5, 5, 2],
        [5, 4, 3, 2, 3, 5, 2, 5, 0, 3, 1, 5, 1, 0],
        [5, 1, 5, 4, 4, 4, 0, 5, 0, 5, 0, 1, 5, 4],
        [4, 5, 1, 1, 1, 3, 2, 4, 0, 3, 5, 0, 4, 5]
    ]
    list_output = [
        [1, 2, 3, 2, 2, 1, 1, 0, 1, 1],
        [1, 5, 1, 3, 1, 5, 0, 0, 4, 4],
        [5, 5, 2, 2, 2, 2, 0, 1, 1, 1],
        [5, 5, 3, 3, 3, 3, 5, 5, 0, 0],
        [2, 2, 2, 4, 0, 0, 0, 0, 2, 2],
        [3, 3, 2, 4, 5, 5, 5, 5, 2, 2],
        [2, 2, 4, 5, 0, 0, 0, 0, 1, 1],
        [4, 4, 1, 3, 3, 5, 5, 5, 0, 0],
        [1, 1, 5, 2, 1, 2, 2, 2, 5, 5],
        [2, 2, 4, 4, 5, 5, 5, 5, 1, 1]
    ]

    input_grid = _to_tuple_grid(list_input)
    output_grid = _to_tuple_grid(list_output)

    for name, rot, rec in [
        ('plain', False, False),
        ('rotation-only', True, False),
        ('recolor-only', False, True)
    ]:
        start = time.time()
        matches = find_matching_crops(input_grid, output_grid, allow_rotate=rot, allow_recolor=rec)
        elapsed = time.time() - start
        print(f"Test ({name}): Found {len(matches)} match(es) in {elapsed:.2f} seconds")
        if name == 'plain':
            print("Plain matches and crops (showing exact matching crops):")
            H, W = len(output_grid), len(output_grid[0])
            for (li, lj), (si, sj), _ in matches:
                # extract crops
                crop_in = safe_crop(input_grid, li, lj, H, W)
                crop_out = safe_crop(output_grid, si, sj, H, W)
                # only show exact matches where crops are identical
                if crop_in != crop_out:
                    continue
                print(f"Match at input[{li}:{li+H}][{lj}:{lj+W}] -> output[{si}:{si+H}][{sj}:{sj+W}]")
                print("  Input & Output crop (row-by-row):")
                for rin, rout in zip(crop_in, crop_out):
                    print("   ", rin, "=>", rout)
                print()
