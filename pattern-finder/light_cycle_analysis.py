# pattern-finder/light_cycle_analysis.py
# inspired by the Tron movie  ___O^o     o^O_____

from typing import List, Tuple, Optional, Dict, Any
import collections
import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List
import json
from collections import defaultdict
from typing import Dict, List, Tuple, Any

from output_diff_analysis import process_output_diff_from_json


Grid = List[List[int]]  # each cell is a color index
Pixel = Tuple[int,int]  # (x, y)
Direction = Tuple[int,int]  # (dx, dy) with dx,dy ∈ {-1,0,1}

def _find_connected_components(grid: Grid) -> List[List[Pixel]]:
    """
    Return a list of connected components (8‐way) for all non‐background pixels.
    Each component is a list of (x,y) pixels sharing the same color.
    """
    H, W = len(grid), len(grid[0])
    visited = [[False]*W for _ in range(H)]
    components: List[List[Pixel]] = []

    for y in range(H):
        for x in range(W):
            if grid[y][x] != 0 and not visited[y][x]:  # assume 0 is bg
                color = grid[y][x]
                queue = collections.deque([(x,y)])
                comp = []
                visited[y][x] = True
                while queue:
                    cx, cy = queue.popleft()
                    comp.append((cx, cy))
                    for dx,dy in [(-1,-1), (0,-1), (1,-1),
                                  (-1, 0),         (1, 0),
                                  (-1, 1), (0, 1), (1, 1)]:
                        nx, ny = cx+dx, cy+dy
                        if 0 <= nx < W and 0 <= ny < H and not visited[ny][nx]:
                            if grid[ny][nx] == color:
                                visited[ny][nx] = True
                                queue.append((nx, ny))
                components.append(comp)
    return components


def _analyze_point(pix: Pixel, grid: Grid) -> Optional[Dict[str,Any]]:
    """
    Given a single‐pixel component (x,y), determine if it’s truly an isolated “LightCycle point”:
      - find any neighbor of same color (in 8 directions)
      - compute the direction toward that neighbor (dx,dy)
      - record start & stop actions at the same tick
    Returns a model dict with keys: 'color', 'pixels', 'actions'
    or None if we decide this isn’t a valid LightCycle event.
    """
    x, y = pix
    color = grid[y][x]
    # find any other pixel of same color adjacent in 8‐neighborhood
    for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
        nx, ny = x+dx, y+dy
        if 0 <= nx < len(grid[0]) and 0 <= ny < len(grid):
            if grid[ny][nx] == color:
                # direction of “point” is toward the closest neighbor
                dir_vec = (dx, dy)
                actions = [
                    {'tick': 0, 'type': 'start', 'direction': dir_vec, 'pos': (x,y)},
                    {'tick': 1, 'type': 'stop',  'direction': dir_vec, 'pos': (x,y)},
                ]
                return {
                    'color': color,
                    'pixels': [pix],
                    'actions': actions
                }
    # If no same‐color neighbor found, it might not be a LightCycle “point”
    return None


def _analyze_open_line(comp: List[Pixel], grid: Grid) -> Optional[Dict[str,Any]]:
    """
    Given a list of pixels forming an open (non‐closed) line segment:
      - find the two endpoints (those with degree=1 in the 8‐connectivity graph)
      - choose one endpoint as “start” (arbitrary: e.g. the one with smallest (y,x))
      - walk along pixels in “line order”, recording direction at each step,
        and assign “tick” indices starting at 0
      - last pixel is where we record ‘stop’
    Returns a model dict or None if something fails.
    """
    # Build adjacency mapping in 8‐neighbors among comp
    neighbor_map: Dict[Pixel, List[Pixel]] = {p: [] for p in comp}
    comp_set = set(comp)
    for (x,y) in comp:
        for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
            nx, ny = x+dx, y+dy
            if (nx,ny) in comp_set:
                neighbor_map[(x,y)].append((nx,ny))

    # endpoints are pixels with exactly one neighbor
    endpoints = [p for p,nbrs in neighbor_map.items() if len(nbrs) == 1]
    if len(endpoints) != 2:
        # if it’s not exactly two endpoints, abort
        return None

    # pick “start” = endpoint with minimal (y, x)
    start = min(endpoints, key=lambda p: (p[1], p[0]))
    # determine “end” as the other endpoint
    end = endpoints[1] if endpoints[0] == start else endpoints[0]

    # walk the line in order from start → end
    ordered_pixels: List[Pixel] = []
    visited = set()
    curr = start
    prev = None
    tick = 0
    actions = []
    while True:
        ordered_pixels.append(curr)
        visited.add(curr)

        # decide direction for this step (from curr→next), except on last pixel
        neighbors = [nbr for nbr in neighbor_map[curr] if nbr not in visited]
        if neighbors:
            # assume exactly one “forward” neighbor
            nxt = neighbors[0]
            dx, dy = (nxt[0] - curr[0], nxt[1] - curr[1])
            if tick == 0:
                # first step: record “start” at tick=0
                actions.append({
                    'tick': 0,
                    'type': 'start',
                    'direction': (dx, dy),
                    'pos': curr
                })
            else:
                # intermediate step (just a “go” in that direction)
                actions.append({
                    'tick': tick,
                    'type': f'go-{_direction_to_str(dx, dy)}',
                    'direction': (dx, dy),
                    'pos': curr
                })
            prev = curr
            curr = nxt
            tick += 1
        else:
            # no unvisited neighbors → curr is “end”
            # record final “stop” at this tick
            # for direction at the end, use the opposite of the last move's direction
            # (i.e. if last dx,dy was (a,b), then stop's direction is (-a, -b))
            if len(ordered_pixels) >= 2:
                last_move = (ordered_pixels[-1][0] - ordered_pixels[-2][0],
                             ordered_pixels[-1][1] - ordered_pixels[-2][1])
                stop_dir = (-last_move[0], -last_move[1])
            else:
                stop_dir = (0, 0)
            actions.append({
                'tick': tick,
                'type': 'stop',
                'direction': stop_dir,
                'pos': curr
            })
            break

    return {
        'color': grid[start[1]][start[0]],
        'pixels': ordered_pixels,
        'actions': actions
    }


def _analyze_closed_loop(comp: List[Pixel], grid: Grid) -> Optional[Dict[str,Any]]:
    """
    Given a closed‐loop component (every pixel has exactly two neighbors in 8‐connectivity):
      - find the “top-left corner” pixel: minimal (y,x) among comp
      - from that corner, choose initial direction = (1, 0) [i.e. “right”]
      - walk clockwise (or counterclockwise) around the loop, recording directions
      - record a “start” at tick=0 (direction=(1,0) at corner), then subsequent “go-right”/“go-down-right”/etc.
      - once you come back to the corner, record “stop” with direction opposite the last move
    Return model dict or None if loop‐walk fails.
    """
    comp_set = set(comp)
    # build adjacency like before
    neighbor_map: Dict[Pixel, List[Pixel]] = {p: [] for p in comp}
    for (x,y) in comp:
        for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
            nxt = (x+dx, y+dy)
            if nxt in comp_set:
                neighbor_map[(x,y)].append(nxt)

    # verify that each pixel has exactly two neighbors
    if any(len(neighbor_map[p]) != 2 for p in comp):
        return None

    # find top-left corner = pixel with minimal (y, x)
    corner = min(comp, key=lambda p: (p[1], p[0]))
    # pick initial “next” neighbor so that (1,0) is our first direction if possible
    # find among corner’s neighbors the one with dx=1,dy=0; else pick lexicographically smallest
    x0, y0 = corner
    preferred = None
    for nbr in neighbor_map[corner]:
        dx, dy = (nbr[0]-x0, nbr[1]-y0)
        if (dx, dy) == (1,0):
            preferred = nbr
            break
    if preferred is None:
        preferred = min(neighbor_map[corner], key=lambda q: (q[1], q[0]))
    # now walk in loop order until we return to corner
    ordered_pixels: List[Pixel] = []
    visited_edges = set()  # track edges (p→q) so we don’t prematurely stop
    curr = corner
    prev = None
    tick = 0
    actions = []

    # first move from corner→preferred
    dx, dy = (preferred[0]-x0, preferred[1]-y0)
    actions.append({
        'tick': 0,
        'type': 'start',
        'direction': (dx, dy),
        'pos': corner
    })
    ordered_pixels.append(corner)
    prev = corner
    curr = preferred
    ordered_pixels.append(curr)
    visited_edges.add((corner, curr))
    visited_edges.add((curr, corner))
    tick = 1

    while curr != corner:
        # from “curr”, pick the neighbor that is not “prev” and not going backwards along a visited edge
        nbrs = neighbor_map[curr]
        next_pix = nbrs[0] if nbrs[0] != prev else nbrs[1]
        dx, dy = (next_pix[0] - curr[0], next_pix[1] - curr[1])
        actions.append({
            'tick': tick,
            'type': f'go-{_direction_to_str(dx, dy)}',
            'direction': (dx, dy),
            'pos': curr
        })
        visited_edges.add((curr, next_pix))
        visited_edges.add((next_pix, curr))
        prev, curr = curr, next_pix
        ordered_pixels.append(curr)
        tick += 1
        if tick > len(comp) + 2:
            # failsafe—shouldn’t loop forever
            return None

    # once back at corner, record “stop” using opposite of last step’s direction
    last_move_dx = ordered_pixels[-1][0] - ordered_pixels[-2][0]
    last_move_dy = ordered_pixels[-1][1] - ordered_pixels[-2][1]
    stop_dir = (-last_move_dx, -last_move_dy)
    actions.append({
        'tick': tick,
        'type': 'stop',
        'direction': stop_dir,
        'pos': corner
    })

    return {
        'color': grid[corner[1]][corner[0]],
        'pixels': ordered_pixels,
        'actions': actions
    }


def _is_closed_loop(comp: List[Pixel]) -> bool:
    """
    Return True if every pixel in comp has exactly two neighbors in 8‐connectivity.
    """
    comp_set = set(comp)
    for (x,y) in comp:
        count = 0
        for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
            if (x+dx, y+dy) in comp_set:
                count += 1
        if count != 2:
            return False
    return True


def _direction_to_str(dx: int, dy: int) -> str:
    """
    Convert a direction vector (dx,dy) with dx,dy ∈ {-1,0,1} into a string:
      (0,-1) → 'up'
      (1,-1) → 'up-right'
      (1, 0) → 'right'
      (1, 1) → 'down-right'
      (0, 1) → 'down'
      (-1,1) → 'down-left'
      (-1,0) → 'left'
      (-1,-1)→ 'up-left'
    """
    if dx == 0 and dy == -1:   return 'up'
    if dx == 1 and dy == -1:   return 'up-right'
    if dx == 1 and dy == 0:    return 'right'
    if dx == 1 and dy == 1:    return 'down-right'
    if dx == 0 and dy == 1:    return 'down'
    if dx == -1 and dy == 1:   return 'down-left'
    if dx == -1 and dy == 0:   return 'left'
    if dx == -1 and dy == -1:  return 'up-left'
    return 'none'


def get_surrounding_colors(grid: Grid, x: int, y: int, radius: int = 1) -> Dict[str, List[int]]:
    """
    Return a dict of color‐lists around (x,y). For radius=1, checks the 8 neighbors:
      'north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'.
    You can extend radius to 2 or 3 by scanning out to radius in each direction.
    """
    H, W = len(grid), len(grid[0])
    result = {
        'north': [], 'north-east': [], 'east': [], 'south-east': [],
        'south': [], 'south-west': [], 'west': [], 'north-west': []
    }
    directions = {
        'north':        (0, -1),
        'north-east':   (1, -1),
        'east':         (1,  0),
        'south-east':   (1,  1),
        'south':        (0,  1),
        'south-west':   (-1, 1),
        'west':         (-1, 0),
        'north-west':   (-1, -1)
    }
    for name, (dx, dy) in directions.items():
        for r in range(1, radius + 1):
            nx, ny = x + dx*r, y + dy*r
            if 0 <= nx < W and 0 <= ny < H:
                result[name].append(grid[ny][nx])
            else:
                # out‐of‐bounds can be treated as “background” or a sentinel
                pass
    return result


def get_row_col_colors(grid: Grid, x: int, y: int) -> Dict[str,List[int]]:
    """
    Return lists of all colors in the immediate next/previous row or column:
      'in_next_row', 'in_prev_row', 'in_next_col', 'in_prev_col'.
    If next/prev row or column is out of bounds, return empty list.
    """
    H, W = len(grid), len(grid[0])
    result = {'in_next_row': [], 'in_prev_row': [], 'in_next_col': [], 'in_prev_col': []}

    # next row (y+1)
    if y+1 < H:
        result['in_next_row'] = list(grid[y+1])
    # prev row (y-1)
    if y-1 >= 0:
        result['in_prev_row'] = list(grid[y-1])
    # next col (x+1)
    if x+1 < W:
        result['in_next_col'] = [grid[row][x+1] for row in range(H)]
    # prev col (x-1)
    if x-1 >= 0:
        result['in_prev_col'] = [grid[row][x-1] for row in range(H)]

    return result

def insert_start_features_common(
    conn: sqlite3.Connection,
    run_id: int,
    start_features_common: Dict[Tuple[int, Tuple[int,int]], Dict[str, Any]]
) -> None:
    """
    Insert “start” actions into the light_cycle table for each (color, direction) group
    in start_features_common. Uses:
      - action = "start"
      - direction_x, direction_y from the group key
      - pixel_rel = common_pixel_rel (as JSON [[color,[dx,dy]],...])
      - colors_at_<dir> from common_neighbors (as JSON lists)
      - colors_in_next_row, colors_in_previous_row, colors_in_next_col, colors_in_previous_col
        from common_rowcol (as JSON lists)
      - floor: by default [group_color], plus the color at relative (0,0) if that differs
      - wall = [], cloud = []
      - tracing = True
      - order_idx = 0
      - state = "suggested"
    """
    sql = """
    INSERT INTO light_cycle (
        light_cycle_id,
        action,
        direction_x,
        direction_y,
        pixel_rel,
        colors_at_north,
        colors_at_north_east,
        colors_at_east,
        colors_at_south_east,
        colors_at_south,
        colors_at_south_west,
        colors_at_west,
        colors_at_north_west,
        colors_in_next_row,
        colors_in_previous_row,
        colors_in_next_col,
        colors_in_previous_col,
        picked_color_type,
        picked_color_pos_rel_x,
        picked_color_pos_rel_y,
        picked_color_pos_dir_rel_x,
        picked_color_pos_dir_rel_y,
        color,
        floor,
        wall,
        cloud,
        tracing,
        order_idx,
        state
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
    )
    """
    cur = conn.cursor()

    for (group_color, (dx, dy)), feats in start_features_common.items():
        # 1) Build pixel_rel JSON: list of [color, [dx_r, dy_r]]
        common_pr: frozenset = feats['common_pixel_rel']
        pr_list = [
            [color_val, [dx_r, dy_r]]
            for (color_val, (dx_r, dy_r)) in sorted(
                common_pr, key=lambda t: (t[1][1], t[1][0])
            )
        ]
        pixel_rel_json = json.dumps(pr_list)

        # 2) Build neighbor JSONs from common_neighbors (each is a frozenset of ints)
        cn = feats['common_neighbors']
        north_json       = json.dumps(sorted(cn.get('north',   [])))
        north_east_json  = json.dumps(sorted(cn.get('north_east', [])))
        east_json        = json.dumps(sorted(cn.get('east',    [])))
        south_east_json  = json.dumps(sorted(cn.get('south_east', [])))
        south_json       = json.dumps(sorted(cn.get('south',   [])))
        south_west_json  = json.dumps(sorted(cn.get('south_west', [])))
        west_json        = json.dumps(sorted(cn.get('west',    [])))
        north_west_json  = json.dumps(sorted(cn.get('north_west', [])))

        # 3) Build row/col JSONs from common_rowcol (each is a frozenset of ints)
        crc = feats['common_rowcol']
        next_row_json = json.dumps(sorted(crc.get('next_row', [])))
        prev_row_json = json.dumps(sorted(crc.get('prev_row', [])))
        next_col_json = json.dumps(sorted(crc.get('next_col', [])))
        prev_col_json = json.dumps(sorted(crc.get('prev_col', [])))

        # 4) Determine floor: [group_color], plus any color at (0,0) in pixel_rel if different
        floor_set = {group_color}
        # Look for an entry in common_pr where (dx_r,dy_r) == (0,0)
        for color_val, (dx_r, dy_r) in common_pr:
            if dx_r == 0 and dy_r == 0 and color_val != group_color:
                floor_set.add(color_val)
                break
        floor_json = json.dumps(sorted(floor_set))

        wall_json = json.dumps([])   # default empty
        cloud_json = json.dumps([])  # default empty

        tracing_flag = True
        order_idx = 0
        state_str = "suggested"

        cur.execute(sql, [
            run_id,
            "start",          # action
            dx,               # direction_x
            dy,               # direction_y
            pixel_rel_json,
            north_json,
            north_east_json,
            east_json,
            south_east_json,
            south_json,
            south_west_json,
            west_json,
            north_west_json,
            next_row_json,
            prev_row_json,
            next_col_json,
            prev_col_json,
            None,  # picked_color_type
            None,  # picked_color_pos_rel_x
            None,  # picked_color_pos_rel_y
            None,  # picked_color_pos_dir_rel_x
            None,  # picked_color_pos_dir_rel_y
            group_color,
            floor_json,
            wall_json,
            cloud_json,
            tracing_flag,
            order_idx,
            state_str
        ])

    conn.commit()

def compute_start_features_common_verbose(
    grouped: Dict[Tuple[int, Tuple[int,int]], List[Dict[str, Any]]],
    data: Dict[str, Any]
) -> Dict[Tuple[int, Tuple[int,int]], Dict[str, Any]]:
    """
    Verbose computation of “start” features for each (color, direction) group of endpoints.
    For each endpoint, we extract:
      - pixel_rel: 5×5 window around (x,y), omitting −2 entries if |dx_r|>1 or |dy_r|>1
      - colors_at_<dir>: color at each of the 8 neighboring offsets (or −2 if out-of-bounds)
      - colors_in_next_row: the full row at y+1 (or [] if y+1 is out-of-bounds)
      - colors_in_previous_row: the full row at y-1 (or [] if y-1 is out-of-bounds)
      - colors_in_next_col: the full column at x+1 (or [] if x+1 is out-of-bounds)
      - colors_in_previous_col: the full column at x-1 (or [] if x-1 is out-of-bounds)

    Then we intersect across all endpoints in the same group:
      - common_pixel_rel: frozenset of (color, (dx,dy)) pairs present in every endpoint
      - common_neighbors: dict of each neighbor direction → frozenset of colors appearing in all endpoints,
          with -8 added if any color was excluded from intersection
      - common_rowcol: dict of 'next_row','prev_row','next_col','prev_col' → frozenset of colors appearing
          in every endpoint, with -8 added if any color was excluded from intersection

    Prints every step verbosely.
    """
    # Build trainId → input grid mapping
    input_grids = {idx: ex['input'] for idx, ex in enumerate(data.get('train', []))}
    #print("Loaded input grids for train IDs:", list(input_grids.keys()))

    # Define neighbor offsets
    neighbor_offsets = {
        'north':        (0, -1),
        'north_east':   (1, -1),
        'east':         (1,  0),
        'south_east':   (1,  1),
        'south':        (0,  1),
        'south_west':   (-1, 1),
        'west':         (-1, 0),
        'north_west':   (-1, -1)
    }

    result: Dict[Tuple[int, Tuple[int,int]], Dict[str, Any]] = {}

    for (color, dir_vec), endpoint_list in grouped.items():
        #print(f"\n=== Processing group: Color={color}, Direction={dir_vec} ===")
        if not endpoint_list:
            #print("  No endpoints in this group; skipping.\n")
            result[(color, dir_vec)] = {
                'common_pixel_rel': frozenset(),
                'common_neighbors': {k: frozenset() for k in neighbor_offsets},
                'common_rowcol': {
                    'next_row': frozenset(),
                    'prev_row': frozenset(),
                    'next_col': frozenset(),
                    'prev_col': frozenset()
                }
            }
            continue

        # Collect per-endpoint data
        pixel_rel_sets: List[frozenset] = []
        neighbor_color_lists = {k: [] for k in neighbor_offsets}
        row_lists = {'next_row': [], 'prev_row': []}
        col_lists = {'next_col': [], 'prev_col': []}

        for idx, rec in enumerate(endpoint_list):
            train_id = rec['trainId']
            x, y = rec['x'], rec['y']
            #print(f"\n  Endpoint #{idx+1}: trainId={train_id}, x={x}, y={y}")
            grid = input_grids.get(train_id)
            if grid is None:
                #print("    No input grid for this trainId; skipping endpoint.")
                continue

            H, W = len(grid), len(grid[0])
            #print(f"    Grid size: width={W}, height={H}")

            # 1) Build pixel_rel window (5×5), skipping −2 if |dx_r|>1 or |dy_r|>1
            one_window = set()
            for dy_r in range(-2, 3):
                for dx_r in range(-2, 3):
                    xx = x + dx_r
                    yy = y + dy_r
                    if 0 <= xx < W and 0 <= yy < H:
                        pixel_color = grid[yy][xx]
                        #print(f"      In-bounds offset ({dx_r},{dy_r}) → color {pixel_color}")
                        one_window.add((pixel_color, (dx_r, dy_r)))
                    else:
                        pixel_color = -2
                        # Keep only if on inner 3×3 border: |dx_r|≤1 and |dy_r|≤1
                        if abs(dx_r) <= 1 and abs(dy_r) <= 1:
                            #print(f"      Out-of-bounds offset ({dx_r},{dy_r}) → color -2 (kept)")
                            one_window.add((pixel_color, (dx_r, dy_r)))
                        #else:
                        #    print(f"      Out-of-bounds offset ({dx_r},{dy_r}) → color -2 (skipped)")
            fz = frozenset(one_window)
            pixel_rel_sets.append(fz)

            #print("    Collected pixel_rel frozenset:")
            #for (pc, (dx_r, dy_r)) in sorted(fz, key=lambda t: (t[1][1], t[1][0])):
            #    print(f"      ({dx_r},{dy_r}) → {pc}")

            # 2) Collect neighbor colors
            for nbr_key, (dx_n, dy_n) in neighbor_offsets.items():
                xx = x + dx_n
                yy = y + dy_n
                if 0 <= xx < W and 0 <= yy < H:
                    c = grid[yy][xx]
                    #print(f"    Neighbor {nbr_key} at ({dx_n},{dy_n}) in-bounds → color {c}")
                    neighbor_color_lists[nbr_key].append(c)
                else:
                    #print(f"    Neighbor {nbr_key} at ({dx_n},{dy_n}) out-of-bounds → color -2")
                    neighbor_color_lists[nbr_key].append(-2)

            # 3) Collect previous_row / next_row: full rows
            if 0 <= y - 1 < H:
                prev_row_vals = grid[y - 1].copy()
                #print(f"    Previous row (y-1={y-1}): {prev_row_vals}")
                row_lists['prev_row'].append(tuple(prev_row_vals))
            else:
                #print(f"    Previous row (y-1={y-1}) out-of-bounds → []")
                row_lists['prev_row'].append(tuple())

            if 0 <= y + 1 < H:
                next_row_vals = grid[y + 1].copy()
                #print(f"    Next row (y+1={y+1}): {next_row_vals}")
                row_lists['next_row'].append(tuple(next_row_vals))
            else:
                #print(f"    Next row (y+1={y+1}) out-of-bounds → []")
                row_lists['next_row'].append(tuple())

            # 4) Collect previous_col / next_col: full columns
            if 0 <= x - 1 < W:
                prev_col_vals = [grid[r][x - 1] for r in range(H)]
                #print(f"    Previous column (x-1={x-1}): {prev_col_vals}")
                col_lists['prev_col'].append(tuple(prev_col_vals))
            else:
                #print(f"    Previous column (x-1={x-1}) out-of-bounds → []")
                col_lists['prev_col'].append(tuple())

            if 0 <= x + 1 < W:
                next_col_vals = [grid[r][x + 1] for r in range(H)]
                #print(f"    Next column (x+1={x+1}): {next_col_vals}")
                col_lists['next_col'].append(tuple(next_col_vals))
            else:
                #print(f"    Next column (x+1={x+1}) out-of-bounds → []")
                col_lists['next_col'].append(tuple())

        # 5) Intersect pixel_rel sets
        #print("\n  Intersecting pixel_rel sets…")
        if pixel_rel_sets:
            sets_for_pr = [set(fz) for fz in pixel_rel_sets]
            #print(f"    Converting {len(pixel_rel_sets)} frozensets to sets.")
            #for i, s in enumerate(sets_for_pr):
            #    print(f"      Set #{i+1} length: {len(s)}")
            common_pr_set = set.intersection(*sets_for_pr)
            #print(f"    Intersection size: {len(common_pr_set)}")
            #for (pc, (dx_r, dy_r)) in sorted(common_pr_set, key=lambda t: (t[1][1], t[1][0])):
            #    print(f"      Common pixel_rel: offset ({dx_r},{dy_r}) → color {pc}")
            common_pixel_rel = frozenset(common_pr_set)
        else:
            #print("    No pixel_rel sets collected; common_pixel_rel = ∅")
            common_pixel_rel = frozenset()

        # 6) Intersect neighbor colors, adding -8 if intersection excludes any seen color
        common_neighbors: Dict[str, frozenset] = {}
        #print("\n  Computing common neighbor colors:")
        for nbr_key, color_list in neighbor_color_lists.items():
            if color_list:
                freq = {c: color_list.count(c) for c in color_list}
                intersection = {c for c, cnt in freq.items() if cnt == len(color_list)}
                union = set(color_list)
                if intersection != union:
                    intersection.add(-8)
                    #print(f"    {nbr_key}: values={color_list} → intersection={intersection} (added -8)")
                #else:
                #    print(f"    {nbr_key}: values={color_list} → intersection={intersection}")
                common_neighbors[nbr_key] = frozenset(intersection)
            else:
                #print(f"    {nbr_key}: no values → common = ∅")
                common_neighbors[nbr_key] = frozenset()

        # 7) Intersect full rows / columns, adding -8 if intersection excludes any seen color
        common_rowcol: Dict[str, frozenset] = {}
        #print("\n  Computing common full-row/column contexts:")
        for rc_key, slice_list in {**row_lists, **col_lists}.items():
            if slice_list:
                # Build union of all slice colors
                union_all = set().union(*slice_list)
                # Build intersection across slice sets
                sets_to_int = [set(s) for s in slice_list]
                intersection = set.intersection(*sets_to_int)
                if intersection != union_all:
                    intersection.add(-8)
                    #print(f"    {rc_key}: union={union_all}, intersection={intersection} (added -8)")
                #else:
                #    print(f"    {rc_key}: union={union_all}, intersection={intersection}")
                common_rowcol[rc_key] = frozenset(intersection)
            else:
                #print(f"    {rc_key}: no slices → common = ∅")
                common_rowcol[rc_key] = frozenset()

        result[(color, dir_vec)] = {
            'common_pixel_rel': common_pixel_rel,
            'common_neighbors': common_neighbors,
            'common_rowcol': common_rowcol
        }

    #print("\n=== Finished computing all common start features ===\n")
    return result

def group_endpoints_by_color_direction(path_info):
    """
    Given the nested dict returned by analyze_paths(), group all endpoints
    across trains by (color, direction) and return a mapping:
      {
        (color, (dx, dy)): [
            {'trainId': train_id, 'objectId': obj_id, 'x': x, 'y': y},
            ...
        ],
        ...
      }
    """
    grouped = collections.defaultdict(list)

    for train_id, objects in path_info.items():
        for obj_id, info in objects.items():
            for x, y, color, (dx, dy) in info['endpoints']:
                grouped[(color, (dx, dy))].append({
                    'trainId': train_id,
                    'objectId': obj_id,
                    'x': x,
                    'y': y
                })
    return grouped

def analyze_paths(db_path: str) -> Dict[int, Dict[int, Dict[str, List[Any]]]]:
    """
    Connect to SQLite at db_path, select all rows where isPath=1 from
    output_diff_object_analysis, retrieving (id, trainId, color, data, minX, minY).

    Here, `data` is a JSON‐encoded list of [row_rel, col_rel] pairs (relative to the object's bounding box).
    We add (minX, minY) to each to get absolute (x_abs, y_abs).

    Then, for each absolute pixel, we classify:
      - endpoint: exactly 1 neighbor in pixel_set,
                 OR exactly 3 neighbors that lie on a straight line (“C” case).
      - path:     exactly 2 neighbors.
      - intersection: 3+ neighbors not on a straight line, or 4+ neighbors.

    For each endpoint, we record:
      - color
      - absolute direction (dx_abs, dy_abs) toward its neighbor
      - absolute coords (x_abs, y_abs)

    Returns a nested dictionary:
      {
        trainId1: {
          objectId1: {
            'endpoints':     [ (x_abs, y_abs, color, (dx_abs,dy_abs)), … ],
            'paths':         [ (x_abs, y_abs), … ],
            'intersections': [ (x_abs, y_abs), … ]
          },
          objectId2: { … },
          …
        },
        trainId2: { … },
        …
      }
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, trainId, color, data, minX, minY
        FROM output_diff_object_analysis
        WHERE isPath = 1
    """)
    rows = cursor.fetchall()
    conn.close()

    results: Dict[int, Dict[int, Dict[str, List[Any]]]] = {}

    for obj_id, train_id, color, data_json, minX, minY in rows:
        # 1) Parse pixel list; each entry is [row_rel, col_rel].
        raw_pixels: List[List[int]] = json.loads(data_json)

        # 2) Build pixel_set of absolute coordinates by adding minX/minY:
        pixel_set = set(
            (col_rel + minX, row_rel + minY)
            for row_rel, col_rel in raw_pixels
        )

        endpoints: List[Tuple[int,int,int,Tuple[int,int]]] = []
        paths: List[Tuple[int,int]] = []
        intersections: List[Tuple[int,int]] = []

        for x_abs, y_abs in pixel_set:
            # 3) Collect neighbors in the 8‐neighborhood (absolute coords)
            neighbors = []
            for dx, dy in [(-1, -1), (0, -1), (1, -1),
                           (-1,  0),          (1,  0),
                           (-1,  1), (0,  1), (1,  1)]:
                nx, ny = x_abs + dx, y_abs + dy
                if (nx, ny) in pixel_set:
                    neighbors.append((nx, ny))

            count = len(neighbors)
            if count == 1:
                # Simple endpoint
                nx, ny = neighbors[0]
                dx_abs, dy_abs = (nx - x_abs, ny - y_abs)
                endpoints.append((x_abs, y_abs, color, (dx_abs, dy_abs)))

            elif count == 2:
                # Middle of a path
                paths.append((x_abs, y_abs))

            elif count == 3:
                # Check special “C” pattern: do all three neighbors lie on a straight line?
                rels = [(nx - x_abs, ny - y_abs) for nx, ny in neighbors]
                dx_vals = {dx for dx, dy in rels}
                dy_vals = {dy for dx, dy in rels}
                is_straight = False
                endpoint_dir: Tuple[int,int] = (0, 0)

                # Vertical: all dx same ∈ {±1}, dy_vals == {-1,0,1}
                if len(dx_vals) == 1 and dx_vals.issubset({-1, 1}) and dy_vals == {-1, 0, 1}:
                    is_straight = True
                    for rdx, rdy in rels:
                        if (rdx, rdy) == (list(dx_vals)[0], 0):
                            endpoint_dir = (rdx, rdy)
                            break

                # Horizontal: all dy same ∈ {±1}, dx_vals == {-1,0,1}
                if not is_straight and len(dy_vals) == 1 and dy_vals.issubset({-1, 1}) and dx_vals == {-1, 0, 1}:
                    is_straight = True
                    for rdx, rdy in rels:
                        if (rdx, rdy) == (0, list(dy_vals)[0]):
                            endpoint_dir = (rdx, rdy)
                            break

                # Diagonal slope +1: all rdx == rdy ∈ {-1,0,1}
                if not is_straight and all(rdx == rdy for rdx, rdy in rels) and dx_vals == {-1, 0, 1}:
                    is_straight = True
                    for rdx, rdy in rels:
                        if abs(rdx) == 1:
                            endpoint_dir = (rdx, rdy)
                            break

                # Diagonal slope -1: all rdx == -rdy ∈ {-1,0,1}
                if not is_straight and all(rdx == -rdy for rdx, rdy in rels) and dx_vals == {-1, 0, 1}:
                    is_straight = True
                    for rdx, rdy in rels:
                        if (rdx, rdy) in [(-1, 1), (1, -1)]:
                            endpoint_dir = (rdx, rdy)
                            break

                if is_straight:
                    dx_abs, dy_abs = endpoint_dir
                    endpoints.append((x_abs, y_abs, color, (dx_abs, dy_abs)))
                else:
                    intersections.append((x_abs, y_abs))

            else:
                # count >= 4: intersection
                intersections.append((x_abs, y_abs))

        # 4) Store results
        if train_id not in results:
            results[train_id] = {}
        results[train_id][obj_id] = {
            'endpoints':     endpoints,
            'paths':         paths,
            'intersections': intersections
        }

    return results


def main(json_source: str, inline: bool = False, name: str | None = None):
    """
    1) Load the ARC JSON (from file or raw string).
    2) For each example (“train” and “test”), run analyze_output(...) on its output grid.
    3) Insert all detected LightCycle actions into SQLite.
    """
    # 1) Load JSON
    if inline:
        data = json.loads(json_source)
        current_filename = name or "__INLINE__"
    else:
        with open(json_source, "r") as f:
            data = json.load(f)
        current_filename = name or os.path.basename(json_source)

    # 2) Open SQLite connection (adjust path if needed)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.abspath(os.path.join(script_dir, "..", "db", "database.db"))
    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM light_cycle;")
    conn.commit()

    process_output_diff_from_json(name, data, conn)

    path_info = analyze_paths(db_path)

    #for train_id, objects in path_info.items():
        #print(f"Train {train_id}:")
        #for obj_id, info in objects.items():
            #endpoints = info['endpoints']
            #if endpoints:
                #print(f"  Object {obj_id} endpoints:")
                #for (x_abs, y_abs, color, (dx, dy)) in endpoints:
                #    print(f"    (x={x_abs}, y={y_abs}), color={color}, direction=({dx},{dy})")
            #else:
            #    print(f"  Object {obj_id} has no endpoints.")
        #print()

    grouped = group_endpoints_by_color_direction(path_info)

    #print(grouped)

    start_features_common = compute_start_features_common_verbose(grouped, data)

    #print(start_features_common)

    insert_start_features_common(conn, 0, start_features_common)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect LightCycle traces in ARC output and store them in SQLite."
    )
    parser.add_argument("json_input", help="Path to ARC JSON file, or raw JSON if --inline")
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Treat json_input as a raw JSON string instead of a file path"
    )
    parser.add_argument(
        "--name",
        type=str,
        help="Optional override for the filename (used as task_id if needed)"
    )

    args = parser.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)



