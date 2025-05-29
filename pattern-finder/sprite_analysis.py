# sprite_analysis.py
import argparse
import os
import sqlite3
import json
import math
import sys
import time
from collections import defaultdict, Counter
from typing import List, Optional, Tuple, Dict, Any

from constelize.dsl.grid_dsl import to_concrete_grid, zoom, grid_to_pretty_string
from solver.dsl import (
    safe_divide,
    compute_pixel_perimeter,
    toindices,
    asindices,
    asobject,
    is_square,
    is_rectangle,
    is_straight_line,
    centerofmass,
    hmirror,
    vmirror,
    dmirror,
    cmirror,
    dneighbors,
    ineighbors,
    occurrences,
    zones,
    blocks,
    color_of,
    objects,
    touches_border,
    crop,
    norm_coord, objects_with_explicit_bg, rot90, rot270, rot90Sprite, hmirrorSprite, rot270Sprite, vmirrorSprite,
    rot180Sprite,
    safe_asobject
)

def init_sprite_global_data():
    """
    Create and return a dictionary to keep track of new sprite_unique, sprite_transformation,
    and sprite_occurrence records, plus in-memory maps for deduplication.
    """
    return {
        "sprites_map": {},          # key=canonical JSON, val=sprite_unique_id
        "next_sprite_id": 1,
        "sprite_unique_records": [],

        "sprite_trans_map": {},     # key=(sprite_unique_id, inverted, rotated_90, ...)
        "next_sprite_trans_id": 1,
        "sprite_trans_records": [],

        "sprite_occ_records": []    # each occurrence row
    }


def canonical_sprite_representation(sprite_grid):
    """
    Convert a 2D sprite grid into a stable/canonical representation.
    Ensures every element follows (color, (row, col)) format.
    """
    sprite_obj = safe_asobject(sprite_grid)  # Converts grid to frozenset of (color, (row, col))

    formatted_list = []
    for item in sprite_obj:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(f"🚨 Unexpected format: {item} (not a tuple of length 2)")

        color, pos = item
        if not isinstance(pos, tuple) or len(pos) != 2:
            raise ValueError(f"🚨 Unexpected position format: {item} (pos is not (row, col))")

        if not isinstance(color, int):
            raise ValueError(f"🚨 Unexpected color format: {item} (color is not an int)")

        formatted_list.append((color, pos))  # Now we are sure it's correct

    sorted_list = sorted(formatted_list, key=lambda x: (x[0], x[1][0], x[1][1]))
    return json.dumps(sorted_list)

def color_counts_in_sprite(sprite_grid):
    color_names = [
        "Black", "Blue", "Red", "Green", "Yellow",
        "Grey", "Fuchsia", "Orange", "Teal", "Brown"
    ]
    counts = [0] * 10
    for row in sprite_grid:
        for cell in row:
            if 0 <= cell <= 9:
                counts[cell] += 1

    count_dict = {f"nb{color_names[i]}": counts[i] for i in range(10)}

    # Determine presence
    color_present = [i for i, count in enumerate(counts) if count > 0]
    color_absent = [i for i, count in enumerate(counts) if count == 0]

    from collections import defaultdict
    groups = defaultdict(list)
    for i, count in enumerate(counts):
        if count > 0:
            groups[count].append(i)
    color_order = [sorted(groups[k]) for k in sorted(groups)]

    color_most = color_order[-1][-1] if color_order else None
    color_least = color_order[0][0] if color_order else None

    # Convert problematic fields to JSON strings
    count_dict.update({
        "colorPresent": json.dumps(color_present),
        "colorAbsent": json.dumps(color_absent),
        "colorOrder": json.dumps(color_order),
        "colorMost": color_most,
        "colorLeast": color_least
    })

    return count_dict

def find_existing_sprite(sprite_grid, global_data):
    """
    Checks if any transformation of the sprite already exists in
    global_data["sprites_map"]. Returns the existing sprite_unique_id if found,
    else returns None.
    """
    base_canon = canonical_sprite_representation(sprite_grid)
    transformations = {
        "original": base_canon,
        "rotated_90": canonical_sprite_representation(rot90Sprite(sprite_grid)),
        "rotated_180": canonical_sprite_representation(rot180Sprite(sprite_grid)),
        "rotated_270": canonical_sprite_representation(rot270Sprite(sprite_grid)),
        "flipped_vert": canonical_sprite_representation(vmirrorSprite(sprite_grid)),
        "flipped_horiz": canonical_sprite_representation(hmirrorSprite(sprite_grid)),
        "flipped_vert_90": canonical_sprite_representation(vmirrorSprite(rot90Sprite(sprite_grid))),
        "flipped_horiz_90": canonical_sprite_representation(hmirrorSprite(rot90Sprite(sprite_grid))),
    }
    for name, canon in transformations.items():
        if canon in global_data["sprites_map"]:
            return global_data["sprites_map"][canon]
    return None

def detect_transformations(sprite_data, global_data):
    base_canon = canonical_sprite_representation(sprite_data)
    transformations = [
        base_canon,
        canonical_sprite_representation(rot90Sprite(sprite_data)),
        canonical_sprite_representation(rot180Sprite(sprite_data)),
        canonical_sprite_representation(rot270Sprite(sprite_data)),
        canonical_sprite_representation(vmirrorSprite(sprite_data)),
        canonical_sprite_representation(hmirrorSprite(sprite_data)),
        canonical_sprite_representation(vmirrorSprite(rot90Sprite(sprite_data))),
        canonical_sprite_representation(hmirrorSprite(rot90Sprite(sprite_data)))
    ]
    for canon in transformations:
        if canon in global_data["sprites_map"]:
            return global_data["sprites_map"][canon]
    return None

def find_existing_sprite_and_flags(sprite_data, global_data):
    """
    Tries each transformation in turn, computing:
      - The canonical representation (JSON)
      - The matching transformation flags

    If we find a match in global_data["sprites_map"], returns:
      (existing_sprite_id,
       (inverted, r90, r180, r270, fv, fh, fv90, fh90))

    If no match is found, returns:
      (None,
       (inverted, r90, r180, r270, fv, fh, fv90, fh90)
      )
    where the flags correspond to the original sprite_data.
    """
    # Step A: Get the "original" object for computing reference flags
    base_obj = safe_asobject(sprite_data)

    # For "inverted" logic, you might set it to False or compute color-inversion if needed.
    inverted = False

    # We'll store transformations in a list of (canonical_str, flags_tuple).
    transformations_to_test = []

    # 1) Original
    orig_canon = canonical_sprite_representation(base_obj)
    transformations_to_test.append((orig_canon,
        (inverted,
         False,  # r90
         False,  # r180
         False,  # r270
         False,  # flipped_vert
         False,  # flipped_horiz
         False,  # flipped_vert_90
         False   # flipped_horiz_90
        )
    ))

    # 2) rot90
    r90_obj = rot90Sprite(base_obj)
    r90_canon = canonical_sprite_representation(r90_obj)
    transformations_to_test.append((r90_canon,
        (inverted, True, False, False, False, False, False, False)
    ))

    # 3) rot180
    r180_obj = rot180Sprite(base_obj)
    r180_canon = canonical_sprite_representation(r180_obj)
    transformations_to_test.append((r180_canon,
        (inverted, False, True, False, False, False, False, False)
    ))

    # 4) rot270
    r270_obj = rot270Sprite(base_obj)
    r270_canon = canonical_sprite_representation(r270_obj)
    transformations_to_test.append((r270_canon,
        (inverted, False, False, True, False, False, False, False)
    ))

    # 5) flipped_vert
    fv_obj = vmirrorSprite(base_obj)
    fv_canon = canonical_sprite_representation(fv_obj)
    transformations_to_test.append((fv_canon,
        (inverted, False, False, False, True, False, False, False)
    ))

    # 6) flipped_horiz
    fh_obj = hmirrorSprite(base_obj)
    fh_canon = canonical_sprite_representation(fh_obj)
    transformations_to_test.append((fh_canon,
        (inverted, False, False, False, False, True, False, False)
    ))

    # 7) flipped_vert_90
    fv90_obj = vmirrorSprite(r90_obj)
    fv90_canon = canonical_sprite_representation(fv90_obj)
    transformations_to_test.append((fv90_canon,
        (inverted, False, False, False, False, False, False, True)
    ))

    # 8) flipped_horiz_90
    fh90_obj = hmirrorSprite(r90_obj)
    fh90_canon = canonical_sprite_representation(fh90_obj)
    transformations_to_test.append((fh90_canon,
        (inverted, False, False, False, False, False, True, False)
    ))

    # Step B: test each transformation in order
    for canon_str, flags_tuple in transformations_to_test:
        if canon_str in global_data["sprites_map"]:
            existing_sprite_id = global_data["sprites_map"][canon_str]
            return (existing_sprite_id, flags_tuple)

    # If none matched
    # The "original" flags go last.  If you prefer,
    # you could also return the transformation flags for whichever
    # is "original" in your final usage.
    return (None, transformations_to_test[0][1])  # i.e., the original's flags

def compute_recolor_map(from_grid: list[list[int]], to_grid: list[list[int]]) -> list[list[int]] | None:
    if len(from_grid) != len(to_grid) or len(from_grid[0]) != len(to_grid[0]):
        return None

    recolor_map = {}
    reverse_map = {}
    for i in range(len(from_grid)):
        for j in range(len(from_grid[0])):
            a, b = from_grid[i][j], to_grid[i][j]
            if a == -1 or b == -1:
                if a != b:
                    return None
                continue
            if a == b:
                continue
            if a in recolor_map and recolor_map[a] != b:
                return None
            if b in reverse_map and reverse_map[b] != a:
                return None  # 🔁 Prevent two different 'a' mapping to same 'b'
            recolor_map[a] = b
            reverse_map[b] = a
    return sorted([[k, v] for k, v in recolor_map.items()])

def store_in_sprite_unique_and_occurrence(attr_dict, sprite_grid, global_data):
    import json

    # Convert sprite to canonical form
    canon = canonical_sprite_representation(sprite_grid)

    # Assign or retrieve unique ID
    if canon in global_data["sprites_map"]:
        produced_id = global_data["sprites_map"][canon]
    else:
        produced_id = global_data["next_sprite_id"]
        global_data["next_sprite_id"] += 1
        global_data["sprites_map"][canon] = produced_id
        # Record sprite_unique
        h = len(sprite_grid)
        w = len(sprite_grid[0]) if h else 0
        color_count = color_counts_in_sprite(sprite_grid)
        rec = {
            "id": produced_id,
            "sprite_id": attr_dict["id"],
            "trainId": attr_dict["trainId"],
            "testId": attr_dict["testId"],
            "filename": attr_dict.get("filename"),
            "height": h,
            "width": w,
            "pixel_count": h * w,
            **color_count,
            "data": canon
        }
        global_data["sprite_unique_records"].append(rec)

        #if attr_dict["isFromPrevious"]:
            #print("isFromPrevious record")
            #print(rec)

    current_tid = attr_dict["trainId"]
    best_identity = None
    found_any = False

    # Prepare transformations
    rot180_fn = lambda g: rot90(rot90(g))
    transformations = [
        (lambda g: g,                  (0, 0, 0, 0, 0, 0, 0, 0)),
        (rot180_fn,                    (0, 0, 1, 0, 0, 0, 0, 0)),
        (rot90,                        (0, 1, 0, 0, 0, 0, 0, 0)),
        (rot270,                       (0, 0, 0, 1, 0, 0, 0, 0)),
        (hmirror,                      (0, 0, 0, 0, 1, 0, 0, 0)),
        (vmirror,                      (0, 0, 0, 0, 0, 1, 0, 0)),
        (lambda g: vmirror(rot90(g)), (0, 0, 0, 0, 0, 0, 1, 0)),
        (lambda g: hmirror(rot90(g)), (0, 0, 0, 0, 0, 0, 0, 1)),
    ]

    matched_trans_ids = set()

    # For each base sprite, attempt to match
    for other in global_data["sprite_unique_records"]:
        if other["trainId"] != current_tid:
            continue
        base_id = other["id"]
        base_grid = to_concrete_grid(json.loads(other["data"]))

        for fn, flags in transformations:
            inv, r90, r180, r270, fv, fh, fv90, fh90 = flags
            transformed = fn(base_grid)

            # Zoom detection
            zx, zy = detect_zoom_factors(transformed, sprite_grid)
            if zx <= 0 or zy <= 0:
                continue

            try:
                zoomed = (
                    [
                        [transformed[i // zy][j // zx] for j in range(zx * len(transformed[0]))]
                        for i in range(zy * len(transformed))
                    ]
                    if (zx != 1 or zy != 1) else transformed
                )
            except IndexError:
                continue

            if len(zoomed) != len(sprite_grid) or len(zoomed[0]) != len(sprite_grid[0]):
                continue

            pairs = compute_recolor_map(zoomed, sprite_grid)
            if pairs is None:
                continue

            # Apply recolor mapping
            mapping = {frm: to for frm, to in pairs}
            recolored_grid = [[mapping.get(c, c) for c in row] for row in zoomed]
            if recolored_grid != sprite_grid:
                continue

            found_any = True

            # If transform produces exactly the identity sprite, reset all flags
            if transformed == base_grid and zx == 1 and zy == 1 and pairs == []:
                inv = r90 = r180 = r270 = fv = fh = fv90 = fh90 = 0
                zx = zy = 1
                rec_pairs = []
            else:
                rec_pairs = pairs

            # Build transformation key
            tkey = (
                base_id, inv, r90, r180, r270, fv, fh, fv90, fh90,
                zx, zy, tuple(tuple(p) for p in rec_pairs)
            )

            # Insert only if not present
            if (tkey not in global_data["sprite_trans_map"]): # and (base_id != produced_id):
                trans_id = global_data["next_sprite_trans_id"]
                global_data["next_sprite_trans_id"] += 1
                global_data["sprite_trans_map"][tkey] = trans_id
                global_data["sprite_trans_records"].append({
                    "id": trans_id,
                    "sprite_unique_id": base_id,
                    "sprite_produce_id": produced_id,
                    "inverted": inv,
                    "rotated_90": r90,
                    "rotated_180": r180,
                    "rotated_270": r270,
                    "flipped_vert": fv,
                    "flipped_horiz": fh,
                    "flipped_vert_90": fv90,
                    "flipped_horiz_90": fh90,
                    "zoom_x": zx,
                    "zoom_y": zy,
                    "recolored": json.dumps(rec_pairs)
                })
            #if (base_id != produced_id):
            matched_trans_ids.add(global_data["sprite_trans_map"][tkey])
            #matched_trans_ids.add(global_data["sprite_trans_map"][tkey])

    # Ensure default identity if no other found
    if not found_any:
        default_key = (
            produced_id, 0,0,0,0,0,0,0,1,1,()
        )
        if default_key not in global_data["sprite_trans_map"]:
            trans_id = global_data["next_sprite_trans_id"]
            global_data["next_sprite_trans_id"] += 1
            global_data["sprite_trans_map"][default_key] = trans_id
            global_data["sprite_trans_records"].append({
                "id": trans_id,
                "sprite_unique_id": produced_id,
                "sprite_produce_id": produced_id,
                "inverted": 0,
                "rotated_90": 0,
                "rotated_180": 0,
                "rotated_270": 0,
                "flipped_vert": 0,
                "flipped_horiz": 0,
                "flipped_vert_90": 0,
                "flipped_horiz_90": 0,
                "zoom_x": 1,
                "zoom_y": 1,
                "recolored": json.dumps([])
            })
        matched_trans_ids.add(global_data["sprite_trans_map"][default_key])

    # Record occurrences for all matched transforms
    for trans_id in matched_trans_ids:
        global_data["sprite_occ_records"].append({
            "sprite_unique_id": produced_id,
            "sprite_transformation_id": trans_id,
            "isInsideInput": attr_dict.get("isInsideInput"),
            "isInsideOutput": attr_dict.get("isInsideOutput"),
            "isInsideTrain": attr_dict.get("isInsideTrain"),
            "isInsideTest": attr_dict.get("isInsideTest"),
            "trainId": attr_dict.get("trainId", -1),
            "testId": attr_dict.get("testId", -1),
            "sprite_id": attr_dict.get("id"),
            "minX": attr_dict.get("minX"),
            "minY": attr_dict.get("minY"),
        })



###############################################
# Helper functions for color and grid metrics (sprite‐based)
###############################################

def count_colors_sprite(sprite_obj):
    """Return the number of unique colors in the sprite object.
    sprite_obj is a frozenset of (color, (row, col)) pairs.
    """
    colors = set()
    for c, pos in sprite_obj:
        colors.add(c)
    return len(colors)


def background_color_sprite(sprite_obj):
    """Return the most frequent color in the sprite object."""
    freq = {}
    for c, pos in sprite_obj:
        freq[c] = freq.get(c, 0) + 1
    return max(freq, key=freq.get) if freq else None


def count_specific_color_sprite(sprite_obj, color_value):
    """Count the number of cells in the sprite object with the given color."""
    return sum(1 for c, pos in sprite_obj if c == color_value)


###############################################
# Grid-based helper functions (unchanged)
###############################################

def compute_bounding_box(grid):
    """
    For a sprite grid, return its bounding box as a half-open interval.
    (Since the sprite is already cropped, we return (0, 0, width, height).)
    """
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    return (0, 0, width, height)


def count_pixels(grid):
    """Return the total number of cells in the grid."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    return height * width


def compute_area_center(grid):
    """Return the geometric center of the grid as (centerX, centerY)."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    return (width / 2, height / 2)


def compute_mass_center(grid):
    """Assume mass center is the same as area center."""
    return compute_area_center(grid)


def is_sprite_repeated_in_grid(grid, sprite):
    """
    Determine if a sprite (given as a grid) occurs more than once in the larger grid.

    If the total area of the grid is less than twice the area of the sprite,
    then we assume there isn’t room for repetition and return False.
    Otherwise, we search for occurrences of the sprite (pixel-by-pixel) in the grid.

    Parameters:
      grid   : The full grid (2D list or tuple) in which to search.
      sprite : The sprite grid to search for.

    Returns:
      True if the sprite is found more than once; otherwise False.
    """
    grid_area = count_pixels(grid)
    sprite_area = count_pixels(sprite)
    if grid_area < sprite_area * 2:
        return False
    # Convert the sprite grid into an object (a frozenset of (color, (row, col)) pairs)
    sprite_obj = asobject(sprite)
    # Use the DSL occurrences function to find all positions where sprite_obj occurs in grid.
    occs = occurrences(grid, sprite_obj)
    return len(occs) > 1


def rot180(grid):
    """Return the grid rotated 180 degrees."""
    return vmirror(hmirror(grid))


def has_horizontal_symmetry(grid):
    return hmirror(grid) == grid


def has_vertical_symmetry(grid):
    return vmirror(grid) == grid


def has_diagonal_symmetry(grid):
    return dmirror(grid) == grid


def has_counter_diagonal_symmetry(grid):
    return cmirror(grid) == grid


def has_rotational_symmetry(grid):
    return rot180(grid) == grid


###############################################
# Common function to fill sprite attributes
###############################################
import json
import math
import os
import sqlite3
from solver.dsl import (
    safe_divide,
    compute_pixel_perimeter,
    toindices,
    asindices,
    asobject,
    is_square,
    is_rectangle,
    is_straight_line,
    centerofmass,
    hmirror,
    vmirror,
    dmirror,
    cmirror,
    dneighbors,
    ineighbors
)


###############################################
# NEW: Helper to compute the bounding box of a sprite object.
###############################################

def compute_bounding_box_obj(sprite_obj):
    """
    Given a sprite object (a frozenset of (color, (row, col)) pairs),
    compute its bounding box as a half-open interval:
      (min_col, min_row, max_col+1, max_row+1)
    """
    coords = [pos for _, pos in sprite_obj]
    if not coords:
        return (0, 0, 0, 0)
    min_row = min(r for r, c in coords)
    min_col = min(c for r, c in coords)
    max_row = max(r for r, c in coords)
    max_col = max(c for r, c in coords)
    return (min_col, min_row, max_col + 1, max_row + 1)


###############################################
# NEW: Color map (adjust if needed)
###############################################

COLOR_MAP = {
    "black": 0,
    "blue": 1,
    "red": 2,
    "green": 3,
    "yellow": 4,
    "grey": 5,
    "Fuchsia": 6,
    "orange": 7,
    "teal": 8,
    "brown": 9
}


###############################################
# Modify color-based helper functions (for sprite objects)
###############################################

def count_specific_color_sprite(sprite_obj, color_value):
    """Count the number of cells in the sprite object with the given color."""
    return sum(1 for c, pos in sprite_obj if c == color_value)


###############################################
# Updated compute_bounding_box for grid remains as before
###############################################

def compute_bounding_box(grid):
    """
    For a sprite grid, return its bounding box as a half-open interval.
    (Since the sprite is assumed to be cropped, we return (0, 0, width, height).)
    """
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    return (0, 0, width, height)


###############################################
# Updated fill_sprite_attributes
###############################################

def fill_sprite_attributes(grid, filename, trainId, testId, flags, sprite, bbox):
    # Same as your code, but remove any skip lines re: color=0
    # ...
    import json

    sprite_obj = asobject(sprite)  # same
    attr = {}
    # Basic flags
    attr["filename"] = filename
    attr["trainId"] = trainId
    attr["testId"] = testId
    attr["isInsideInput"] = flags.get("isInsideInput", False)
    attr["isInsideOutput"] = flags.get("isInsideOutput", False)
    attr["isInsideTrain"] = flags.get("isInsideTrain", False)
    attr["isInsideTest"] = flags.get("isInsideTest", False)
    attr["isInsideBuffer"] = flags.get("isInsideBuffer", False)
    attr["isGrid"] = flags.get("isGrid", False)
    attr["isFromSplit"] = flags.get("isFromSplit", False)
    attr["isFromHole"] = flags.get("isFromHole", False)
    attr["isFromCut"] = flags.get("isFromCut", False)
    attr["isFromColorZone"] = flags.get("isFromColorZone", False)
    attr["isFromPrevious"] = flags.get("isFromPrevious", False)
    attr["isFromGlued"] = flags.get("isFromGlued", False)

    minX, minY, maxX, maxY = bbox
    attr["minX"] = minX
    attr["minY"] = minY
    attr["maxX"] = maxX
    attr["maxY"] = maxY
    attr["minCol"] = minX
    attr["minRow"] = minY
    attr["maxCol"] = maxX - 1
    attr["maxRow"] = maxY - 1

    # color info
    attr["nbColors"] = count_colors_sprite(sprite_obj)
    if flags.get("isGrid") or flags.get("isFromSplit"):
        attr["bgColor"] = None
    else:
        attr["bgColor"] = background_color_sprite(sprite_obj)

    # — NEW: per‐color counts & presence/absence/etc. —
    # uses the color_counts_in_sprite(grid) helper defined below
    per_color = color_counts_in_sprite(sprite)
    attr.update(per_color)

    # For dimension, we can do:
    h = len(sprite)
    w = len(sprite[0]) if h>0 else 0
    from solver.dsl import compute_pixel_perimeter, asindices
    attr["height"] = h
    attr["width"] = w
    attr["ratioWidthHeight"] = safe_divide(w,h)
    attr["area"] = h*w
    attr["pixelCount"] = sum(
        1
        for row in sprite
        for pix in row
        if pix != attr["bgColor"]
    )
    attr["hasOddPixelCount"] = ((w*h) % 2 != 0)
    attr["hasEvenPixelCount"] = ((w*h) % 2 == 0)
    attr["areaPerimeter"] = 2*(h+w)
    attr["pixelPerimeter"] = compute_pixel_perimeter(asindices(sprite))
    attr["ratioPixelsArea"] = safe_divide(attr["pixelCount"], attr["area"])

    # shape properties
    from solver.dsl import is_square, is_rectangle, is_straight_line, centerofmass
    attr["isSquare"] = is_square(sprite_obj)
    attr["isRectangle"] = is_rectangle(sprite_obj)
    attr["isLine"] = is_straight_line(sprite_obj)
    attr["isHorizontal"] = (w>h)
    attr["isVertical"] = (h>w)
    attr["hasBorder"] = has_constant_border(sprite)
    attr["diagonalLength"] = (h*h + w*w)**0.5

    # Distances from borders
    gridH = len(grid)
    gridW = len(grid[0]) if gridH>0 else 0
    attr["distanceFromTopBorder"] = minY
    attr["distanceFromBottomBorder"] = (gridH - maxY)
    attr["distanceFromLeftBorder"] = minX
    attr["distanceFromRightBorder"] = (gridW - maxX)

    # center
    attr["areaCenterX"], attr["areaCenterY"] = compute_area_center(sprite)
    cx, cy = centerofmass(sprite_obj)
    attr["massCenterX"], attr["massCenterY"] = cx, cy
    attr["isHorizontallyCentered"] = (minX + attr["areaCenterX"] == gridW/2)
    attr["isVerticallyCentered"] = (minY + attr["areaCenterY"] == gridH/2)
    attr["isCentered"] = attr["isHorizontallyCentered"] and attr["isVerticallyCentered"]

    # border touching
    attr["isTouchingTop"] = (minY==0)
    attr["isTouchingBottom"] = (maxY==gridH)
    attr["isTouchingLeft"] = (minX==0)
    attr["isTouchingRight"] = (maxX==gridW)
    attr["isTouchingBorder"] = (attr["isTouchingTop"] or attr["isTouchingBottom"] or
                                attr["isTouchingLeft"] or attr["isTouchingRight"])
    attr["isTouchingTopRight"] = (attr["isTouchingTop"] and attr["isTouchingRight"])
    attr["isTouchingBottomRight"] = (attr["isTouchingBottom"] and attr["isTouchingRight"])
    attr["isTouchingTopLeft"] = (attr["isTouchingTop"] and attr["isTouchingLeft"])
    attr["isTouchingBottomLeft"] = (attr["isTouchingBottom"] and attr["isTouchingLeft"])
    attr["isTouchingCorner"] = (attr["isTouchingTopRight"] or attr["isTouchingBottomRight"] or
                                attr["isTouchingTopLeft"] or attr["isTouchingBottomLeft"])

    # repeated? symmetry?
    def is_sprite_repeated_in_grid(grid, spr):
        # same function as original
        from solver.dsl import asobject, occurrences
        grid_area = len(grid)*len(grid[0])
        sH = len(spr); sW = len(spr[0]) if sH>0 else 0
        sprite_area = sH*sW
        if grid_area < sprite_area*2:
            return False
        spr_obj = asobject(spr)
        occs = occurrences(grid, spr_obj)
        return (len(occs)>1)

    attr["isSpriteRepeated"] = is_sprite_repeated_in_grid(grid,sprite)
    attr["hasHorizontalSymmetry"] = (hmirror(sprite_obj) == sprite_obj)
    attr["hasVerticalSymmetry"]   = (vmirror(sprite_obj) == sprite_obj)
    attr["hasDiagonalSymmetry"]   = (dmirror(sprite_obj) == sprite_obj)
    attr["hasCounterDiagonalSymmetry"] = (cmirror(sprite_obj) == sprite_obj)
    def rot180_obj(spr_obj):
        from solver.dsl import hmirror, vmirror
        return vmirror(hmirror(spr_obj))
    attr["hasRotationalSymmetry"] = (rot180_obj(sprite_obj)==sprite_obj)

    attr["colorUniqueRatio"] = None
    if attr.get("isInsideInput"):
        # 1) Count how many times each color appears *outside* the sprite
        full_flat = [cell for row in grid for cell in row]
        sprite_flat = [cell for row in sprite for cell in row]
        full_cnt = Counter(full_flat)
        sprite_cnt = Counter(sprite_flat)

        # 2) Find colors that appear in sprite but nowhere else
        unique_colors = [c for c in sprite_cnt
                         if full_cnt[c] == sprite_cnt[c]]  # i.e. none left outside

        if unique_colors:
            # total pixels of those unique colors
            unique_pixels = sum(sprite_cnt[c] for c in unique_colors)
            # sprite total pixel count:
            total_pixels = attr["pixelCount"]
            # total pixels in the full grid:
            grid_h = len(grid)
            grid_w = len(grid[0]) if grid_h else 0
            grid_size = grid_h * grid_w
            # ratio as defined
            # scale factor = 1 when sprite tiny, →0 as sprite → full‐grid
            scale = 1 - (total_pixels / grid_size) if grid_size else 0
            attr["colorUniqueRatio"] = (unique_pixels / (total_pixels + 1)) * scale

    # 3) Temporarily store a placeholder for the order; we'll fill it in after
    attr["colorUniqueOrder"] = None

    # data
    attr["data"] = json.dumps(list(sprite_obj))
    return attr


###############################################
# Splitting functions based on input/output ratio
###############################################

def split_grid_by_ratio(input_grid, output_grid):
    """
    Compare the input and output grids and, using the smaller grid as reference,
    split the larger grid into pieces only if the target grid's dimensions are
    exact multiples of the reference grid's dimensions.
    """
    in_height = len(input_grid)
    in_width = len(input_grid[0]) if in_height > 0 else 0
    out_height = len(output_grid)
    out_width = len(output_grid[0]) if out_height > 0 else 0
    in_area = in_height * in_width
    out_area = out_height * out_width

    if in_area == 0 or out_area == 0:
        return []

    if in_area <= out_area:
        ref_width = in_width
        ref_height = in_height
        target_grid = output_grid
        target_width = out_width
        target_height = out_height
    else:
        ref_width = out_width
        ref_height = out_height
        target_grid = input_grid
        target_width = in_width
        target_height = in_height

    # Check for exact divisibility.
    if target_width % ref_width != 0 or target_height % ref_height != 0:
        return []  # Do not split if dimensions are not exact multiples.

    horizontal_splits = target_width // ref_width
    vertical_splits = target_height // ref_height

    subgrids = []
    piece_width = target_width // horizontal_splits
    piece_height = target_height // vertical_splits
    for i in range(vertical_splits):
        for j in range(horizontal_splits):
            minX = j * piece_width
            maxX = target_width if j == horizontal_splits - 1 else (j + 1) * piece_width
            minY = i * piece_height
            maxY = target_height if i == vertical_splits - 1 else (i + 1) * piece_height
            # Slice both rows and columns.
            subgrid = [row[minX:maxX] for row in target_grid[minY:maxY]]
            subgrids.append((subgrid, (minX, minY, maxX, maxY)))
    return subgrids


def compute_split_sprites_by_ratio(input_grid, output_grid, filename, trainId, testId, isInput):
    """
    Given the input and output grids, if one is significantly larger than the other,
    split the larger grid into pieces only if the dimensions of the larger grid are
    exact multiples of the smaller grid's dimensions.
    """
    grid = input_grid if isInput else output_grid
    input_area = count_pixels(input_grid)
    output_area = count_pixels(output_grid)

    # Decide which grid to split.
    if isInput:
        if input_area <= output_area:
            return []  # Do not split the input if it is smaller.
        target_grid = input_grid
        ref_grid = output_grid
    else:
        if output_area <= input_area:
            return []  # Do not split the output if it is smaller.
        target_grid = output_grid
        ref_grid = input_grid

    ref_height = len(ref_grid)
    ref_width = len(ref_grid[0]) if ref_height > 0 else 0
    target_height = len(target_grid)
    target_width = len(target_grid[0]) if target_height > 0 else 0

    # Check for exact divisibility.
    if target_width % ref_width != 0 or target_height % ref_height != 0:
        return []  # Do not split if dimensions are not exact multiples.

    horizontal_splits = target_width // ref_width
    vertical_splits = target_height // ref_height

    subgrids = []
    piece_width = target_width // horizontal_splits
    piece_height = target_height // vertical_splits
    for i in range(vertical_splits):
        for j in range(horizontal_splits):
            minX = j * piece_width
            maxX = target_width if j == horizontal_splits - 1 else (j + 1) * piece_width
            minY = i * piece_height
            maxY = target_height if i == vertical_splits - 1 else (i + 1) * piece_height
            subgrid = [row[minX:maxX] for row in target_grid[minY:maxY]]
            subgrids.append((subgrid, (minX, minY, maxX, maxY)))

    # For each subgrid, compute sprite attributes.
    sprites = []
    for subgrid, bbox in subgrids:
        flags = {
            "isInsideInput": isInput,
            "isInsideOutput": not isInput,
            "isInsideTrain": (trainId != -1),
            "isInsideTest": (testId != -1),
            "isInsideBuffer": False,
            "isGrid": False,
            "isFromSplit": True,
            "isFromHole": False,
            "isFromCut": False,
            "isFromColorZone": False,
            "isFromPrevious": False,
            "isFromGlued": False,
        }
        sprite = fill_sprite_attributes(grid, filename, trainId, testId, flags, subgrid, bbox)
        sprite["minX"], sprite["minY"], sprite["maxX"], sprite["maxY"] = bbox
        sprites.append(sprite)
    return sprites

def compute_split_sprites_by_input_ratio(
    input_grid: list[list[int]],
    w_ratio: float,
    h_ratio: float,
    filename: str,
    trainId: int,
    testId: int,
    isInput: bool
) -> list[dict]:
    """
    Split the input grid into tiles according to the given width/height ratios,
    if—and only if—the computed tile sizes divide the grid exactly.
    """
    H = len(input_grid)
    W = len(input_grid[0]) if H else 0

    # compute target tile dimensions
    tile_w = int(round(W * w_ratio))
    tile_h = int(round(H * h_ratio))

    # sanity: must be positive and divide exactly
    if tile_w <= 0 or tile_h <= 0:
        return []
    if W % tile_w != 0 or H % tile_h != 0:
        return []

    horiz_splits = W // tile_w
    vert_splits  = H // tile_h

    sprites = []
    for i in range(vert_splits):
        for j in range(horiz_splits):
            minX = j * tile_w
            maxX = minX + tile_w
            minY = i * tile_h
            maxY = minY + tile_h

            subgrid = [row[minX:maxX] for row in input_grid[minY:maxY]]
            flags = {
                "isInsideInput":   isInput,
                "isInsideOutput":  not isInput,
                "isInsideTrain":   (trainId != -1),
                "isInsideTest":    (testId  != -1),
                "isInsideBuffer":  False,
                "isGrid":          False,
                "isFromSplit":     True,
                "isFromHole":      False,
                "isFromCut":       False,
                "isFromColorZone": False,
                "isFromPrevious":  False,
                "isFromGlued":  False,
            }

            sprite = fill_sprite_attributes(
                input_grid, filename,
                trainId, testId,
                flags, subgrid,
                (minX, minY, maxX, maxY)
            )
            # override bounding box
            sprite["minX"], sprite["minY"], sprite["maxX"], sprite["maxY"] = (
                minX, minY, maxX, maxY
            )
            sprites.append(sprite)

    return sprites

def find_holes_in_objects(grid):
    """
    Dummy hole detection: returns an empty list.
    Replace with your own logic to detect holes within objects.
    Expected return: list of (subgrid, (minX, minY, maxX, maxY), parent_bg).
    """
    return []


def compute_splitter_sprite(grid, filename, trainId, testId, isInsideInput):
    """
    Detect a splitter in the grid and, if exactly one valid candidate is found,
    create two sprites.

    A valid vertical splitter is defined as:
      - A column (with index in range 1 to width-2) such that:
          1. Every pixel in that column is the same color (candidate_color).
          2. The entire column immediately to the left and the entire column immediately to the right
             do NOT contain candidate_color.

    A valid horizontal splitter is defined as:
      - A row (with index in range 1 to height-2) such that:
          1. Every cell in that row is the same color (candidate_color).
          2. The entire row immediately above and the entire row immediately below do NOT contain candidate_color.

    If more than one candidate is found in either orientation, no split is detected.

    The resulting sprites are:
      - For a vertical splitter:
          * Left sprite contains all columns strictly to the left of the splitter.
          * Right sprite contains all columns strictly to the right of the splitter.
      - For a horizontal splitter:
          * Top sprite contains all rows strictly above the splitter.
          * Bottom sprite contains all rows strictly below the splitter.

    The sprites' background color (bgColor) is set to the splitter's color.
    """
    sprites = []
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0

    # Common flags for sprites from split.
    flags = {
        "isInsideInput": isInsideInput,
        "isInsideOutput": not isInsideInput,
        "isInsideTrain": (trainId != -1),
        "isInsideTest": (testId != -1),
        "isInsideBuffer": False,
        "isGrid": False,
        "isFromSplit": True,
        "isFromHole": False,
        "isFromCut": True,
        "isFromColorZone": False,
        "isFromPrevious": False,
        "isFromGlued": False,
    }

    # --- Try vertical splitter detection ---
    vertical_candidates = []
    # Only consider columns not at the border.
    for col in range(1, width - 1):
        candidate_color = grid[0][col]
        # Check every row in candidate column.
        if all(row[col] == candidate_color for row in grid):
            # Check that the entire adjacent columns do NOT have candidate_color.
            if all(row[col - 1] != candidate_color for row in grid) and all(
                    row[col + 1] != candidate_color for row in grid):
                vertical_candidates.append((col, candidate_color))
    # Only proceed if exactly one vertical candidate is found.
    if len(vertical_candidates) == 1:
        splitter_col, splitter_color = vertical_candidates[0]
        # Left subgrid: columns 0 up to splitter_col (exclusive).
        left_subgrid = [row[:splitter_col] for row in grid]
        # Right subgrid: columns splitter_col+1 to end.
        right_subgrid = [row[splitter_col + 1:] for row in grid]
        # Define bounding boxes in half-open coordinates.
        left_bbox = (0, 0, splitter_col, height)
        right_bbox = (splitter_col + 1, 0, width, height)
        sprite_left = fill_sprite_attributes(left_subgrid, filename, trainId, testId, flags, left_subgrid, left_bbox)
        sprite_left["bgColor"] = splitter_color
        sprite_left["minX"], sprite_left["minY"], sprite_left["maxX"], sprite_left["maxY"] = left_bbox
        sprite_right = fill_sprite_attributes(right_subgrid, filename, trainId, testId, flags, right_subgrid,
                                              right_bbox)
        sprite_right["bgColor"] = splitter_color
        sprite_right["minX"], sprite_right["minY"], sprite_right["maxX"], sprite_right["maxY"] = right_bbox
        sprites.extend([sprite_left, sprite_right])
        return sprites

    # --- Try horizontal splitter detection ---
    horizontal_candidates = []
    # Only consider rows not at the border.
    for row in range(1, height - 1):
        candidate_color = grid[row][0]
        # Check every cell in candidate row.
        if all(cell == candidate_color for cell in grid[row]):
            # Check that the row above and row below do not contain candidate_color.
            if all(cell != candidate_color for cell in grid[row - 1]) and all(
                    cell != candidate_color for cell in grid[row + 1]):
                horizontal_candidates.append((row, candidate_color))
    if len(horizontal_candidates) == 1:
        splitter_row, splitter_color = horizontal_candidates[0]
        # Top subgrid: rows 0 up to splitter_row (exclusive).
        top_subgrid = grid[:splitter_row]
        # Bottom subgrid: rows splitter_row+1 to end.
        bottom_subgrid = grid[splitter_row + 1:]
        top_bbox = (0, 0, width, splitter_row)
        bottom_bbox = (0, splitter_row + 1, width, height)
        sprite_top = fill_sprite_attributes(top_subgrid, filename, trainId, testId, flags, top_subgrid, top_bbox)
        sprite_top["bgColor"] = splitter_color
        sprite_top["minX"], sprite_top["minY"], sprite_top["maxX"], sprite_top["maxY"] = top_bbox
        sprite_bottom = fill_sprite_attributes(bottom_subgrid, filename, trainId, testId, flags, bottom_subgrid,
                                               bottom_bbox)
        sprite_bottom["bgColor"] = splitter_color
        sprite_bottom["minX"], sprite_bottom["minY"], sprite_bottom["maxX"], sprite_bottom["maxY"] = bottom_bbox
        sprites.extend([sprite_top, sprite_bottom])
        return sprites

    # If no unique valid splitter is found, return empty.
    return []

def pad_grid(grid, pad_value, pad_width=1):
    ##print("----------------------")
    ##print("pad_grid")
    ##print("grid", grid)
    ##print("pad_value", pad_value)
    ##print("pad_width", pad_width)
    ##print("----------------------")
    """
    Pads a 2D grid (list of lists) with pad_width layers of pad_value on all sides.
    """
    new_grid = []
    if not grid:
        return new_grid
    row_len = len(grid[0])
    pad_row = [pad_value] * (row_len + 2 * pad_width)
    for _ in range(pad_width):
        new_grid.append(pad_row.copy())
    for row in grid:
        new_grid.append([pad_value] * pad_width + row + [pad_value] * pad_width)
    for _ in range(pad_width):
        new_grid.append(pad_row.copy())
    return new_grid

def pad_mask(mask, pad_value=False, pad_width=1):
    #print("----------------------")
    #print("pad_mask")
    #print("mask", mask)
    #print("pad_value", pad_value)
    #print("pad_width", pad_width)
    #print("----------------------")
    """
    Pads a 2D Boolean mask (list of lists) with pad_width layers of pad_value on all sides.
    """
    new_mask = []
    if not mask:
        return new_mask
    row_len = len(mask[0])
    pad_row = [pad_value] * (row_len + 2 * pad_width)
    for _ in range(pad_width):
        new_mask.append(pad_row.copy())
    for row in mask:
        new_mask.append([pad_value] * pad_width + row + [pad_value] * pad_width)
    for _ in range(pad_width):
        new_mask.append(pad_row.copy())
    return new_mask

def count_gap_groups(line):
    #print("----------------------")
    #print("count_gap_groups")
    #print("line", line)
    #print("----------------------")
    """
    Given a list of booleans (True for object, False for gap),
    count the number of contiguous groups of False.
    """
    groups = 0
    in_gap = False
    for v in line:
        if not v:  # a gap
            if not in_gap:
                groups += 1
                in_gap = True
        else:
            in_gap = False
    return groups

def eligible_border_gap(borders):
    #print("----------------------")
    #print("eligible_border_gap")
    #print("borders", borders)
    #print("----------------------")
    """
    Decide if an object is border-active.
    If it touches a border, check the total gap groups. If exactly 1, we call it border-active.
    Otherwise, it's not.
    """
    if not borders:
        return False
    return True

def get_components(mask):
    """
    Standard 4-connected connected-components on a 2D list of booleans.
    Returns a list of sets, each set is (row,col) coords.
    """
    h = len(mask)
    w = len(mask[0]) if h > 0 else 0
    seen = [[False]*w for _ in range(h)]
    components = []
    for i in range(h):
        for j in range(w):
            if mask[i][j] and not seen[i][j]:
                comp = set()
                stack = [(i,j)]
                while stack:
                    x,y = stack.pop()
                    if seen[x][y]:
                        continue
                    seen[x][y] = True
                    comp.add((x,y))
                    for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nx, ny = x+dx, y+dy
                        if 0 <= nx < h and 0 <= ny < w:
                            if mask[nx][ny] and not seen[nx][ny]:
                                stack.append((nx,ny))
                components.append(comp)
    return components

def remove_border_colored_blocks_subgrid(
    subgrid: list[list[int]],
    obj_bg: int,
    top_internal: bool,
    bottom_internal: bool,
    left_internal: bool,
    right_internal: bool,
    diagonal=False
):
    """
    Remove non-bg connected blocks from specific subgrid edges
    *only* if that edge is flagged as internal.

    If top_internal=True, we remove from row=0 if color != obj_bg
    If bottom_internal=True, we remove from row=h-1 if color != obj_bg
    If left_internal=True, we remove from col=0 if color != obj_bg
    If right_internal=True, we remove from col=w-1 if color != obj_bg
    diagonal => BFS adjacency is 8-connected if True, or 4-connected if False.
    """
    from solver.dsl import dneighbors, neighbors

    h = len(subgrid)
    w = len(subgrid[0]) if h>0 else 0
    if h==0 or w==0:
        return

    adj_fun = neighbors if diagonal else dneighbors

    def in_bounds(r,c):
        return (0<=r<h and 0<=c<w)

    changed = True
    while changed:
        changed = False
        border_positions = []

        # top row
        if top_internal and h>0:
            for c in range(w):
                border_positions.append((0,c))
        # bottom row
        if bottom_internal and h>1:
            for c in range(w):
                border_positions.append((h-1,c))

        # left column
        if left_internal and w>0:
            for r in range(h):
                border_positions.append((r,0))
        # right column
        if right_internal and w>1:
            for r in range(h):
                border_positions.append((r,w-1))

        visited = set()
        for (br,bc) in border_positions:
            if (br,bc) in visited:
                continue
            color = subgrid[br][bc]
            if color == obj_bg:
                continue

            # BFS to remove that region
            stack = [(br,bc)]
            to_overwrite = []
            while stack:
                r,c = stack.pop()
                if (r,c) in visited:
                    continue
                visited.add((r,c))
                if subgrid[r][c] != obj_bg:
                    to_overwrite.append((r,c))
                    # push neighbors
                    for nr,nc in adj_fun((r,c)):
                        if in_bounds(nr,nc) and (nr,nc) not in visited:
                            if subgrid[nr][nc] != obj_bg:
                                stack.append((nr,nc))

            if to_overwrite:
                changed = True
                for (r,c) in to_overwrite:
                    subgrid[r][c] = obj_bg

def detect_sprite_in_holes_by_bg(grid, diagonal=True):
    """
    ─ Find every connected region of != “background” (where background is simply
      the color that appears most often in the whole grid).
    ─ Return a list of dicts: each dict has keys
      { "grid": cropped_grid, "bbox": (minX, minY, maxX, maxY), "bgColor": bg }.
    ─ Automatically drops any duplicate regions (by bbox).
    """
    # 1) pick the background as the most frequent color in grid
    flat = [c for row in grid for c in row]
    bg, _ = Counter(flat).most_common(1)[0]

    # 2) extract every region ≠ bg
    regions = objects_with_explicit_bg(
        grid,
        univalued=False,
        diagonal=diagonal,
        skip_color=bg
    )

    seen = set()
    sprites = []
    for region in regions:
        coords = [pos for (_, pos) in region]
        min_r = min(r for r, _ in coords)
        max_r = max(r for r, _ in coords) + 1
        min_c = min(c for _, c in coords)
        max_c = max(c for _, c in coords) + 1
        bbox = (min_c, min_r, max_c, max_r)
        if bbox in seen:
            continue
        seen.add(bbox)

        # 3) build the little cropped grid
        h = max_r - min_r
        w = max_c - min_c
        sub = crop(grid, (min_r, min_c), (h, w))
        # fill background with bg color if needed
        for i in range(h):
            for j in range(w):
                if sub[i][j] == bg:
                    sub[i][j] = bg

        sprites.append({
            "grid": sub,
            "bbox": bbox,
            "bgColor": bg
        })
    return sprites

def compute_hole_sprites(grid, filename, trainId, testId, isInsideInput):
    """
    - We skip objects < 8 pixels.
    - For each object subgrid, remove non-bg blocks from edges
      only if that edge is not also the grid boundary.
    - Then unify holes (non-bg) via objects_with_explicit_bg.
    """

    print(f"[compute_hole_sprites] START filename={filename} trainId={trainId} testId={testId} isInsideInput={isInsideInput}")
    sprites = []
    seen_bboxes = set()

    # ── 1) bg-based detection first ──
    bg_hits = detect_sprite_in_holes_by_bg(grid)
    for hit in bg_hits:
        bbox = hit["bbox"]
        if bbox in seen_bboxes:
            continue
        seen_bboxes.add(bbox)

        flags = {
            "isInsideInput":    isInsideInput,
            "isInsideOutput":  not isInsideInput,
            "isInsideTrain":   (trainId != -1),
            "isInsideTest":    (testId  != -1),
            "isInsideBuffer":  False,
            "isGrid":          False,
            "isFromSplit":     False,
            "isFromHole":      True,
            "isFromCut":       False,
            "isFromColorZone": False,
            "isFromPrevious":  False,
            "isFromGlued":  False,
        }
        spr = fill_sprite_attributes(
            grid, filename, trainId, testId,
            flags, hit["grid"], hit["bbox"]
        )
        spr["bgColor"] = hit["bgColor"]

        # re-compute data & nbColors exactly as below
        hole_obj = asobject(hit["grid"])
        final = frozenset((c,pos) for (c,pos) in hole_obj if c != hit["bgColor"])
        spr["data"]     = json.dumps(list(final))
        spr["nbColors"] = len({c for c,_ in final})

        sprites.append(spr)
    # ── end bg-based

    # grid dimensions
    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0
    print(f"[compute_hole_sprites] grid size: height={grid_h}, width={grid_w}")

    all_objects = zones(grid)
    print(f"[compute_hole_sprites] found {len(all_objects)} object(s) in grid")

    for obj_idx, obj in enumerate(all_objects, start=1):
        print(f"\n[compute_hole_sprites] processing object #{obj_idx}")
        indices = list(toindices(obj))
        print(f"  - total pixels in object: {len(indices)}")
        if not indices:
            #print("  -> skip: no indices")
            continue
        if len(indices) < 8:
            #print("  -> skip: object too small (<8 pixels)")
            continue

        # bounding box in grid coordinates
        min_row = min(r for r, c in indices)
        max_row = max(r for r, c in indices) + 1
        min_col = min(c for r, c in indices)
        max_col = max(c for r, c in indices) + 1
        obj_h = max_row - min_row
        obj_w = max_col - min_col
        print(f"  - bounding box rows {min_row}:{max_row}, cols {min_col}:{max_col} => size {obj_h}×{obj_w}")

        subgrid_obj = crop(grid, (min_row, min_col), (obj_h, obj_w))
        obj_bg = color_of(obj)
        print(f"  - object background color: {obj_bg}")

        # decide which edges are internal to the grid
        top_internal = min_row > 0
        bottom_internal = max_row < grid_h
        left_internal = min_col > 0
        right_internal = max_col < grid_w
        print(f"  - edges internal? top={top_internal}, bottom={bottom_internal}, left={left_internal}, right={right_internal}")

        # remove non-bg blocks from internal edges
        remove_border_colored_blocks_subgrid(
            subgrid_obj, obj_bg,
            top_internal=top_internal,
            bottom_internal=bottom_internal,
            left_internal=left_internal,
            right_internal=right_internal,
            diagonal=False
        )
        #print("  - removed non-bg border blocks on internal edges")

        # detect holes in the cleaned subgrid
        holes = objects_with_explicit_bg(
            subgrid_obj,
            univalued=False,
            diagonal=True,
            skip_color=obj_bg
        )
        print(f"  - detected {len(holes)} hole region(s)")

        for hole_idx, region in enumerate(holes, start=1):
            print(f"    [hole #{hole_idx}] region pixel entries: {len(region)}")
            coords = [pos for (_, pos) in region]
            sub_min_i = min(r for r, c in coords)
            sub_max_i = max(r for r, c in coords) + 1
            sub_min_j = min(c for r, c in coords)
            sub_max_j = max(c for r, c in coords) + 1
            hole_h = sub_max_i - sub_min_i
            hole_w = sub_max_j - sub_min_j
            print(f"      - subgrid hole bbox rows {sub_min_i}:{sub_max_i}, cols {sub_min_j}:{sub_max_j} => size {hole_h}×{hole_w}")

            # build the hole's own grid
            region_set = {pos for (_, pos) in region}
            hole_grid = []
            for i in range(sub_min_i, sub_max_i):
                row_data = []
                for j in range(sub_min_j, sub_max_j):
                    if (i, j) in region_set:
                        row_data.append(subgrid_obj[i][j])
                    else:
                        row_data.append(obj_bg)
                hole_grid.append(row_data)

            # compute global bounding box
            global_minX = min_col + sub_min_j
            global_maxX = min_col + sub_max_j
            global_minY = min_row + sub_min_i
            global_maxY = min_row + sub_max_i
            bbox = (global_minX, global_minY, global_maxX, global_maxY)
            print(f"      - global bbox: {bbox}")

            # prepare sprite flags
            flags = {
                "isInsideInput": isInsideInput,
                "isInsideOutput": not isInsideInput,
                "isInsideTrain": (trainId != -1),
                "isInsideTest": (testId != -1),
                "isInsideBuffer": False,
                "isGrid": False,
                "isFromSplit": False,
                "isFromHole": True,
                "isFromCut": False,
                "isFromColorZone": False,
                "isFromPrevious": False,
                "isFromGlued": False,
            }
            spr = fill_sprite_attributes(grid, filename, trainId, testId, flags, hole_grid, bbox)
            hole_obj = asobject(hole_grid)
            final_obj = frozenset((c, pos) for (c, pos) in hole_obj if c != obj_bg)
            num_colors = len({c for c, _ in final_obj})
            print(f"      - final object has {num_colors} distinct color(s)")

            # only keep sprites with at least 2 distinct colors
            if num_colors >= 2:
                # dedupe against bg-based hits and prior holes
                if bbox in seen_bboxes:
                    print(f"      -> duplicate bbox {bbox}, skipping")
                    continue
                seen_bboxes.add(bbox)

                spr["data"] = json.dumps(list(final_obj))
                spr["nbColors"] = num_colors
                spr["bgColor"] = obj_bg
                sprites.append(spr)
                #print("      -> sprite accepted and added")
            #else:
                #print("      -> sprite rejected (fewer than 2 colors)")

    #print(f"[compute_hole_sprites] END, total sprites found: {len(sprites)}")
    return sprites


def compute_sprites_color_zone(grid, filename, trainId, testId, isInsideInput):
    """
    Extract sprites from interior regions where a single color occupies at least
    40% of its bounding box, and that bounding box does NOT touch the grid edge.
    """
    #print("[ compute_sprites_color_zone ]")
    sprites = []

    height = len(grid)
    width  = len(grid[0]) if height else 0

    for color_name, color_value in COLOR_MAP.items():
        # collect all coords of this color
        coords = [(x, y)
                  for y, row in enumerate(grid)
                  for x, v in enumerate(row)
                  if v == color_value]
        if not coords:
            continue

        xs, ys = zip(*coords)
        minX, maxX = min(xs), max(xs) + 1
        minY, maxY = min(ys), max(ys) + 1
        w, h = maxX - minX, maxY - minY
        area = w * h

        # size checks: area ≥ 9, both dims > 1
        if area < 9 or w == 1 or h == 1:
            continue

        # reject if bbox touches any grid border
        if minX == 0 and minY == 0 and maxX == width and maxY == height:
            continue

        # require ≥40% of pixels in box be this color
        count_in_box = sum(
            1
            for row in grid[minY:maxY]
            for v in row[minX:maxX]
            if v == color_value
        )
        if count_in_box < 0.4 * area:
            continue

        # slice out subgrid
        subgrid = [row[minX:maxX] for row in grid[minY:maxY]]

        # prepare flags (including new isFromColorZone)
        flags = {
            "isInsideInput":    isInsideInput,
            "isInsideOutput":   not isInsideInput,
            "isInsideTrain":    (trainId != -1),
            "isInsideTest":     (testId  != -1),
            "isInsideBuffer":   False,
            "isGrid":           False,
            "isFromSplit":      False,
            "isFromHole":       False,
            "isFromCut":        False,
            "isFromColorZone":  True,
            "isFromPrevious":   False,
            "isFromGlued":   False,
        }

        # build the sprite record
        spr = fill_sprite_attributes(
            grid, filename, trainId, testId, flags,
            subgrid, (minX, minY, maxX, maxY)
        )
        # ensure the new flag persists
        spr["isFromColorZone"] = True

        sprites.append(spr)

    return sprites

###############################################
# Processing JSON data to insert sprite_analysis records
###############################################

def bulk_insert(conn, table, rows):
    if not rows:
        return
    cursor = conn.cursor()
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    data = [tuple(row[col] for col in columns) for row in rows]
    cursor.executemany(sql, data)




def process_sprites_from_json(filename, data, conn, clear_table=True):
    """
    Process a JSON file containing ARC tasks to compute and insert sprite_analysis records.

    For each ARC item:
      - Create a sprite for the entire grid.
      - If both input and output grids exist and one is significantly larger than the other,
        split the larger grid into pieces (using the smaller as reference).
      - If a splitter is detected, compute a sprite from that region.
      - If holes are detected, compute sprites for those holes.

    For TRAIN data, both input and output grids are processed.
    For TEST data, only the input grid is processed.
    """
    sprite_global_data = init_sprite_global_data()
    if clear_table:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sprite_analysis;")
        cursor.execute("DELETE FROM sprite_unique;")
        cursor.execute("DELETE FROM sprite_transformation;")
        cursor.execute("DELETE FROM sprite_occurrence;")
        cursor.execute("DELETE FROM sprite_analysis;")
        conn.commit()

    all_sprite_rows = []
    all_sprite_analysis_rows = []
    next_sprite_analysis_id = 1

    _train_split_ratios = set()
    _train_output_dims = set()

    def process_item(item, is_input, index, isTrain):
        nonlocal next_sprite_analysis_id
        # 0. Basic info
        grid = item["input"] if is_input else item["output"]
        if isTrain:
            trainId = index
            testId = -1
        else:
            trainId = -1
            testId = index

        # 1. Entire grid sprite (unchanged)
        flags = {
            "isInsideInput": is_input,
            "isInsideOutput": not is_input,
            "isInsideTrain": (trainId != -1),
            "isInsideTest": (testId != -1),
            "isInsideBuffer": False,
            "isGrid": True,
            "isFromSplit": False,
            "isFromHole": False,
            "isFromCut": False,
            "isFromColorZone": False,
            "isFromPrevious": False,
            "isFromGlued": False,
        }

        bbox = compute_bounding_box(grid)
        sprite_entire = fill_sprite_attributes(grid, filename, trainId, testId, flags, grid, bbox)
        all_sprite_rows.append(sprite_entire)
        # -> Assign an ID for sprite_analysis
        sprite_entire["id"] = next_sprite_analysis_id
        next_sprite_analysis_id += 1
        store_in_sprite_unique_and_occurrence(sprite_entire, grid, sprite_global_data)
        all_sprite_analysis_rows.append(sprite_entire)

        # 2. Possibly do dimension-based splits (compute_split_sprites_by_ratio)
        split_sprites = []
        if "output" in item:
            in_h = len(item["input"])
            in_w = len(item["input"][0]) if in_h else 0
            out_h = len(item["output"])
            out_w = len(item["output"][0]) if out_h else 0

            if isTrain:
                # record the constant output‐dims across TRAIN cases
                _train_output_dims.add((out_w, out_h))
                ratio_w = out_w / in_w if in_w else 0
                ratio_h = out_h / in_h if in_h else 0
                _train_split_ratios.add((ratio_w, ratio_h))
                # split the TRAIN as before
                split_sprites = compute_split_sprites_by_ratio(
                    item["input"], item["output"],
                    filename, trainId, testId, is_input
                )

            else:
                # TEST: first try the original ratio‐based split
                if len(_train_split_ratios) == 1:
                    w_ratio, h_ratio = next(iter(_train_split_ratios))
                    split_sprites = compute_split_sprites_by_input_ratio(
                        item["input"],
                        w_ratio, h_ratio,
                        filename, trainId, testId, is_input
                    )
                # if no single ratio but output dims WERE constant, use a dummy ref‐grid
                elif len(_train_output_dims) == 1:
                    const_w, const_h = next(iter(_train_output_dims))
                    # make any grid of the same size (values don't matter for slicing)
                    fake_ref = [[0]*const_w for _ in range(const_h)]
                    split_sprites = compute_split_sprites_by_ratio(
                        item["input"], fake_ref,
                        filename, trainId, testId, is_input
                    )
                else:
                    print(f"⏭ skipping test‐split; ratios={_train_split_ratios}, dims={_train_output_dims}")
        all_sprite_rows.extend(split_sprites)

        # Now also fill the new tables.
        # For each splitted sprite, we need the subgrid that was used.
        for spl in split_sprites:
            spl["id"] = next_sprite_analysis_id
            next_sprite_analysis_id += 1
            all_sprite_analysis_rows.append(spl)
            # The dictionary 'spl' has .["minX"], ["minY"], etc.
            minX, minY = spl["minX"], spl["minY"]
            maxX, maxY = spl["maxX"], spl["maxY"]
            # Re-slice the original `grid` used for that sprite:
            subgrid = [row[minX:maxX] for row in grid[minY:maxY]]
            store_in_sprite_unique_and_occurrence(spl, subgrid, sprite_global_data)

        # 3. Check for line-based splitter:
        splitter_sprites = compute_splitter_sprite(grid, filename, trainId, testId, is_input)
        # If the code finds exactly one valid split line, it typically returns 2 sub-sprites (left/right or top/bottom).

        if len(splitter_sprites) == 2:
            all_sprite_analysis_rows.extend(splitter_sprites)
            # => We found a valid single splitter. So skip hole detection on the entire grid
            #    and do hole detection only on each of the two sub-sprites.

            all_sprite_rows.extend(splitter_sprites)

            for split_sprite in splitter_sprites:
                split_sprite["id"] = next_sprite_analysis_id
                next_sprite_analysis_id += 1
                # each 'split_sprite' is one half of the grid.
                # We must build the subgrid from (split_sprite["minX"] .. split_sprite["maxX"], etc.)
                subgrid_minX = split_sprite["minX"]
                subgrid_minY = split_sprite["minY"]
                subgrid_maxX = split_sprite["maxX"]
                subgrid_maxY = split_sprite["maxY"]
                # slice from the full 'grid'
                subgrid = [
                    row[subgrid_minX: subgrid_maxX]
                    for row in grid[subgrid_minY: subgrid_maxY]
                ]
                store_in_sprite_unique_and_occurrence(split_sprite, subgrid, sprite_global_data)

                # Now do hole detection on that subgrid:
                # We can call compute_hole_sprites,
                # but we must pass the subgrid + we might need special logic to shift coordinates
                # so that hole detection knows the subgrid’s top-left is (0,0).
                # We'll do:
                subgrid_sprites_hole = compute_hole_sprites(
                    subgrid, filename, trainId, testId, is_input
                )

                # Then we must fix bounding boxes or shift them if they are local to subgrid
                # A simple approach is to patch each resulting sprite's minX/minY etc. by adding subgrid_minX, subgrid_minY:
                for sh in subgrid_sprites_hole:
                    # shift the bounding box from local subgrid coords to global coords
                    old_minX = sh["minX"]
                    old_minY = sh["minY"]
                    old_maxX = sh["maxX"]
                    old_maxY = sh["maxY"]
                    sh["minX"] = old_minX + subgrid_minX
                    sh["maxX"] = old_maxX + subgrid_minX
                    sh["minY"] = old_minY + subgrid_minY
                    sh["maxY"] = old_maxY + subgrid_minY
                    # optionally shift "data" if needed, or if your code uses global coords in them

                all_sprite_rows.extend(subgrid_sprites_hole)

                for hole_attr in subgrid_sprites_hole:
                    hole_attr["id"] = next_sprite_analysis_id
                    next_sprite_analysis_id += 1
                    all_sprite_analysis_rows.append(hole_attr)
                    hx0, hy0 = hole_attr["minX"], hole_attr["minY"]
                    hx1, hy1 = hole_attr["maxX"], hole_attr["maxY"]
                    hole_grid = [row[hx0:hx1] for row in grid[hy0:hy1]]
                    store_in_sprite_unique_and_occurrence(hole_attr, hole_grid, sprite_global_data)

        else:
            # => No valid single-line splitter, so we do normal hole detection on the entire grid
            sprites_hole = compute_hole_sprites(grid, filename, trainId, testId, is_input)
            all_sprite_rows.extend(sprites_hole)

            for hs in sprites_hole:
                hs["id"] = next_sprite_analysis_id
                next_sprite_analysis_id += 1
                all_sprite_analysis_rows.append(hs)
                hx0, hy0 = hs["minX"], hs["minY"]
                hx1, hy1 = hs["maxX"], hs["maxY"]
                hole_grid = [row[hx0:hx1] for row in grid[hy0:hy1]]
                store_in_sprite_unique_and_occurrence(hs, hole_grid, sprite_global_data)

        sprites_color_zone = compute_sprites_color_zone(grid, filename, trainId, testId, is_input)
        # 0) prepare a set of all bounding‐boxes we’ve already seen
        existing_boxes = {
            (r["minX"], r["minY"], r["maxX"], r["maxY"])
            for r in all_sprite_rows
        }

        # 1) filter out any color-zone sprites whose bbox is already in all_sprite_rows
        new_color_zone_sprites = [
            cz for cz in sprites_color_zone
            if (cz["minX"], cz["minY"], cz["maxX"], cz["maxY"]) not in existing_boxes
        ]

        # 2) now add only the truly new ones
        all_sprite_rows.extend(sprites_color_zone)

        # Now assign IDs, register for analysis, slice out their subgrids, and store
        for cz in sprites_color_zone:
            cz["id"] = next_sprite_analysis_id
            next_sprite_analysis_id += 1

            # 4a) Add to the sprite_analysis staging list
            all_sprite_analysis_rows.append(cz)
            # all_sprite_analysis_rows was initialized at the top of process_sprites_from_json :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}

            # 4b) Re-slice the exact subgrid for this color‐zone
            cx0, cy0 = cz["minX"], cz["minY"]
            cx1, cy1 = cz["maxX"], cz["maxY"]
            cz_grid = [row[cx0:cx1] for row in grid[cy0:cy1]]

            # 4c) Finally, record it in sprite_unique / sprite_occurrence
            store_in_sprite_unique_and_occurrence(
                cz,  # your attribute dict
                cz_grid,  # the extracted subgrid
                sprite_global_data
            )

    new_sprites = data.get("new_sprites", {})

    for key, grids in new_sprites.items():
        trainId, testId = map(int, key.split("#"))
        # pick the full grid either from train or test
        if trainId >= 0:
            full_grid = data["train"][trainId]["input"]
        else:
            full_grid = data["test"][testId]["input"]

        for sprite_grid in grids:
            # compute sprite size
            h, w = len(sprite_grid), len(sprite_grid[0])
            # slide‐match to find its exact location
            found = False
            minX, minY, maxX, maxY = 0, 0, w, h
            for minY in range(len(full_grid) - h + 1):
                for minX in range(len(full_grid[0]) - w + 1):
                    if all(
                            full_grid[minY + y][minX + x] == sprite_grid[y][x]
                            for y in range(h) for x in range(w)
                    ):
                        maxY, maxX = minY + h, minX + w
                        found = True
                        break
                if found: break
            if not found:
                minX, minY, maxX, maxY = 0, 0, w, h

            # build your flags exactly as before (here I added your "isFromPrevious")
            flags = {
                "isInsideInput": True,
                "isInsideOutput": False,
                "isInsideTrain": (trainId != -1),
                "isInsideTest": (testId != -1),
                "isInsideBuffer": False,
                "isGrid": False,
                "isFromSplit": False,
                "isFromHole": False,
                "isFromCut": False,
                "isFromColorZone": False,
                "isFromPrevious": True,
                "isFromGlued": False,
            }

            # **this** single call does all the work of fill_sprite_attributes for you:
            spr = fill_sprite_attributes(
                full_grid,  # the big input grid
                filename,
                trainId,
                testId,
                flags,
                sprite_grid,  # the small sprite itself
                (minX, minY, maxX, maxY)
            )  # ← signature is def fill_sprite_attributes(grid, filename, trainId, testId, flags, sprite, bbox): :contentReference[oaicite:0]{index=0}

            # now stash it just like you did:
            spr["id"] = next_sprite_analysis_id
            next_sprite_analysis_id += 1
            all_sprite_analysis_rows.append(spr)
            store_in_sprite_unique_and_occurrence(spr, sprite_grid, sprite_global_data)

    for index, item in enumerate(data.get("train", [])):
        process_item(item, True, index, True)  # Process input grid.
        process_item(item, False, index, True)  # Process output grid.

    for index, item in enumerate(data.get("test", [])):
        process_item(item, True, index, False)

    # 1. Group by trainId and testId
    grouped_by_id = defaultdict(list)
    for row in all_sprite_rows:
        if row.get("isInsideTrain"):
            key = f"train#{row['trainId']}"
        elif row.get("isInsideTest"):
            key = f"test#{row['testId']}"
        else:
            continue  # Skip rows not in train or test
        grouped_by_id[key].append(row)

    # 2. Compute sizeOrder and sizeOrderDesc for each group
    for group_key, rows in grouped_by_id.items():
        sorted_desc = sorted(rows, key=lambda r: r["pixelCount"], reverse=True)
        for rank, row in enumerate(sorted_desc, start=1):
            row["sizeOrder"] = rank

        sorted_asc = sorted(rows, key=lambda r: r["pixelCount"])
        for rank, row in enumerate(sorted_asc, start=1):
            row["sizeOrderDesc"] = rank

    # ── NEW: compute colorUniqueOrder by descending colorUniqueRatio ──
    for rows in grouped_by_id.values():
        # only sprites with a non-null ratio
        sprites_with_ratio = [r for r in rows if r["colorUniqueRatio"] is not None]
        # sort highest ratio first
        sorted_by_ratio = sorted(
            sprites_with_ratio,
            key=lambda r: r["colorUniqueRatio"],
            reverse=True
        )
        for rank, r in enumerate(sorted_by_ratio, start=1):
            r["colorUniqueOrder"] = rank

    # 3. Copy these values into the rows that will be inserted into the DB
    id_to_sprite_row = {r["id"]: r for r in all_sprite_rows if "id" in r}
    for row in all_sprite_analysis_rows:
        src = id_to_sprite_row.get(row.get("id"))
        if src:
            row["sizeOrder"] = src.get("sizeOrder", -1)
            row["sizeOrderDesc"] = src.get("sizeOrderDesc", -1)
            row["colorUniqueOrder"] = src.get("colorUniqueOrder")
        else:
            row["sizeOrder"] = -1
            row["sizeOrderDesc"] = -1

    bulk_insert(conn, "sprite_analysis", all_sprite_analysis_rows)
    bulk_insert(conn, "sprite_unique", sprite_global_data["sprite_unique_records"])
    bulk_insert(conn, "sprite_transformation", sprite_global_data["sprite_trans_records"])
    bulk_insert(conn, "sprite_occurrence", sprite_global_data["sprite_occ_records"])
    conn.commit()

    cur = conn.cursor()
    cur.executescript("""
    -- 1) isSpriteUnique
    UPDATE sprite_analysis AS sa
    SET isSpriteUnique = CASE
      WHEN sa.testId = -1 AND sa.isInsideInput = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM sprite_analysis i
         WHERE i.trainId = sa.trainId
           AND i.testId = -1
           AND i.isInsideInput = 1
           AND i.data = sa.data)
      ELSE NULL END;

    -- 2) isTargetSpritePresent
    UPDATE sprite_analysis AS sa
    SET isTargetSpritePresent = CASE
      WHEN sa.testId = -1 THEN
        (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END
         FROM sprite_analysis o
         WHERE o.trainId = sa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = sa.data)
      ELSE NULL END;

    -- 3) isTargetSpriteUnique
    UPDATE sprite_analysis AS sa
    SET isTargetSpriteUnique = CASE
      WHEN sa.testId = -1 AND sa.isTargetSpritePresent = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM sprite_analysis o
         WHERE o.trainId = sa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = sa.data)
      ELSE NULL END;

    -- 4) One-to-one / one-to-many / many-to-one / many-to-many
    UPDATE sprite_analysis
    SET
      isSpriteOneToOne   = CASE WHEN isSpriteUnique=1 AND isTargetSpriteUnique=1 THEN 1 ELSE 0 END,
      isSpriteOneToMany  = CASE WHEN isSpriteUnique=1 AND isTargetSpriteUnique=0 AND isTargetSpritePresent=1 THEN 1 ELSE 0 END,
      isSpriteManyToOne  = CASE WHEN isSpriteUnique=0 AND isTargetSpriteUnique=1 THEN 1 ELSE 0 END,
      isSpriteManyToMany = CASE WHEN isSpriteUnique=0 AND isTargetSpriteUnique=0 AND isTargetSpritePresent=1 THEN 1 ELSE 0 END;

    -- 5) target_sprite_id (only for one-to-one input sprites)
    UPDATE sprite_analysis AS sa
    SET target_sprite_id = (
      SELECT o.id
      FROM sprite_analysis o
      WHERE o.trainId = sa.trainId
        AND o.testId = -1
        AND o.isInsideOutput = 1
        AND o.data = sa.data
      LIMIT 1
    )
    WHERE sa.testId = -1
      AND sa.isInsideInput = 1
      AND sa.isSpriteOneToOne = 1;

    -- 6) isSpriteDeleted
    UPDATE sprite_analysis
    SET isSpriteDeleted = CASE WHEN isTargetSpritePresent=0 THEN 1 ELSE 0 END;

    -- 7) isMoved
    UPDATE sprite_analysis AS sa
    SET isMoved = CASE
      WHEN sa.isSpriteOneToOne=1 AND EXISTS (
             SELECT 1 FROM sprite_analysis t
              WHERE t.id = sa.target_sprite_id
                AND (t.minX != sa.minX OR t.minY != sa.minY)
           ) THEN 1
      ELSE 0 END;

    -- 8) isRotatedOrFlipped
    UPDATE sprite_analysis AS sa
    SET isRotatedOrFlipped = CASE
      WHEN EXISTS (
        SELECT 1
        FROM sprite_occurrence so
        JOIN sprite_transformation st
          ON so.sprite_transformation_id = st.id
        WHERE so.sprite_id = sa.id
          AND (st.rotated_90=1 OR st.rotated_180=1 OR st.rotated_270=1
               OR st.flipped_vert=1 OR st.flipped_horiz=1
               OR st.flipped_vert_90=1 OR st.flipped_horiz_90=1)
      ) THEN 1
      ELSE 0 END;

    -- 9) isRecolored
    UPDATE sprite_analysis AS sa
    SET isRecolored = CASE
      WHEN EXISTS (
        SELECT 1
        FROM sprite_occurrence so
        JOIN sprite_transformation st
          ON so.sprite_transformation_id = st.id
        WHERE so.sprite_id = sa.id
          AND st.recolored != '[]'
      ) THEN 1
      ELSE 0 END;

    -- 10) isZoomed
    UPDATE sprite_analysis AS sa
    SET isZoomed = CASE
      WHEN EXISTS (
        SELECT 1
        FROM sprite_occurrence so
        JOIN sprite_transformation st
          ON so.sprite_transformation_id = st.id
        WHERE so.sprite_id = sa.id
          AND (st.zoom_x > 1 OR st.zoom_y > 1)
      ) THEN 1
      ELSE 0 END;

    -- 11) isGlued
    UPDATE sprite_analysis
    SET isGlued = CASE WHEN isSpriteDeleted=1 AND isRecolored=1 THEN 1 ELSE 0 END;

    -- 12) moveRelX / moveRelY / newPosX / newPosY
    UPDATE sprite_analysis AS sa
    SET moveRelX = (
      SELECT t.minX - sa.minX
      FROM sprite_analysis t
      WHERE t.id = sa.target_sprite_id
    )
    WHERE sa.target_sprite_id IS NOT NULL;
    UPDATE sprite_analysis AS sa
    SET moveRelY = (
      SELECT t.minY - sa.minY
      FROM sprite_analysis t
      WHERE t.id = sa.target_sprite_id
    )
    WHERE sa.target_sprite_id IS NOT NULL;
    UPDATE sprite_analysis AS sa
    SET newPosX = (
      SELECT t.minX
      FROM sprite_analysis t
      WHERE t.id = sa.target_sprite_id
    )
    WHERE sa.target_sprite_id IS NOT NULL;
    UPDATE sprite_analysis AS sa
    SET newPosY = (
      SELECT t.minY
      FROM sprite_analysis t
      WHERE t.id = sa.target_sprite_id
    )
    WHERE sa.target_sprite_id IS NOT NULL;

    -- 13) moveBehindColor (placeholder; compute via Python helper if you want)
    UPDATE sprite_analysis
    SET moveBehindColor = NULL;

    -- 14) rotateOrFlip (concatenate variant names)
    UPDATE sprite_analysis AS sa
    SET rotateOrFlip = (
      SELECT rtrim(
        (CASE WHEN st.rotated_90     = 1 THEN 'rot90,'     ELSE '' END)
      || (CASE WHEN st.rotated_180    = 1 THEN 'rot180,'    ELSE '' END)
      || (CASE WHEN st.rotated_270    = 1 THEN 'rot270,'    ELSE '' END)
      || (CASE WHEN st.flipped_horiz  = 1 THEN 'flipH,'     ELSE '' END)
      || (CASE WHEN st.flipped_vert   = 1 THEN 'flipV,'     ELSE '' END)
      || (CASE WHEN st.flipped_horiz_90 = 1 THEN 'flipH90,'  ELSE '' END)
      || (CASE WHEN st.flipped_vert_90  = 1 THEN 'flipV90,'  ELSE '' END)
      , ','
      )
      FROM sprite_occurrence so
      JOIN sprite_transformation st
        ON so.sprite_transformation_id = st.id
      WHERE so.sprite_id = sa.id
      LIMIT 1
    );

    -- 15) recolored TEXT
    UPDATE sprite_analysis AS sa
    SET recolored = (
      SELECT st.recolored
      FROM sprite_occurrence so
      JOIN sprite_transformation st
        ON so.sprite_transformation_id = st.id
      WHERE so.sprite_id = sa.id
        AND st.recolored != '[]'
      LIMIT 1
    );

    -- 16) zoomX / zoomY
    UPDATE sprite_analysis AS sa
    SET zoomX = (
      SELECT st.zoom_x
      FROM sprite_occurrence so
      JOIN sprite_transformation st
        ON so.sprite_transformation_id = st.id
      WHERE so.sprite_id = sa.id
        AND st.zoom_x > 1
      LIMIT 1
    );
    UPDATE sprite_analysis AS sa
    SET zoomY = (
      SELECT st.zoom_y
      FROM sprite_occurrence so
      JOIN sprite_transformation st
        ON so.sprite_transformation_id = st.id
      WHERE so.sprite_id = sa.id
        AND st.zoom_y > 1
      LIMIT 1
    );
    """)
    conn.commit()

    # --- 1) load all train-case grids for easy lookup by trainId ---
    # assumes data["train"] is a list of dicts with keys "input" and "output"
    input_grids = [case["input"] for case in data["train"]]
    output_grids = [case["output"] for case in data["train"]]

    # --- 2) build a map sprite_id -> list of (row,col) in the original grid ---
    sprite_pixels: dict[int, list[tuple[int, int]]] = {}
    cur = conn.cursor()

    # We need: id, trainId (to index input/output lists),
    #         minX/minY (bbox offset), data (sprite subgrid), bgColor
    for sprite_id, trainId, minX, minY, data_json, bgColor in cur.execute("""
        SELECT id, trainId, minX, minY, data, bgColor
        FROM sprite_analysis
    """):
        # parse the sprite’s 2D array
        sprite_array = json.loads(data_json)
        coords: list[tuple[int, int]] = []

        # walk every cell in that subgrid;
        # if it’s not the background color, it’s part of the sprite
        for dy, row_vals in enumerate(sprite_array):
            for dx, pixel in enumerate(row_vals):
                if pixel != bgColor:
                    # translate local (dy,dx) back into full-grid coordinates
                    coords.append((minY + dy, minX + dx))

        sprite_pixels[sprite_id] = coords

    # 1) select only those sprites that actually moved
    moved_rows = cur.execute("""
           SELECT sa.id, sa.trainId, sa.bgColor
           FROM sprite_analysis AS sa
           WHERE testId = -1
             AND (
               (sa.moveRelX IS NOT NULL AND sa.moveRelX != 0)
               OR
               (sa.moveRelY IS NOT NULL AND sa.moveRelY != 0)
             )
       """).fetchall()

    # 2) for each moved sprite, compute the "background" left behind
    for sprite_id, trainId, sprite_color in moved_rows:
        ig = input_grids[trainId]  # original input grid
        og = output_grids[trainId]  # resulting output grid
        pixels = sprite_pixels[sprite_id]
        # sprites typically don’t have a neighbor‐color list, so we skip that fallback
        behind = compute_move_behind_color(
            ig,
            og,
            pixels,
            sprite_color
        )
        cur.execute(
            "UPDATE sprite_analysis SET moveBehindColor = ? WHERE id = ?",
            (behind, sprite_id)
        )

    # 3) commit once
    conn.commit()

    detect_and_store_glued_and_new(conn, data, filename)
    detect_and_store_sprite_computation(conn)

def compute_move_behind_color(input_grid, output_grid, pixels, sprite_color):
    """
    Compute the color left behind when a sprite moves.

    Returns -1 whenever the output no longer covers the original pixels
    or whenever nothing else can be found.

    Adapted from object_analysis.compute_move_behind_color :contentReference[oaicite:0]{index=0}.
    """
    # 0) guard: no pixels → nothing to fill
    if not pixels:
        #print("→ No sprite pixels, returning -1")
        return -1

    # 1) bounds check against the output grid
    H = len(output_grid)
    W = len(output_grid[0]) if H else 0
    for r, c in pixels:
        if r < 0 or r >= H or c < 0 or c >= W:
            print(f"→ Sprite pixel {(r, c)} outside output grid, returning -1")
            return -1

    # 2) collect whatever’s now in those original spots
    behind_colors = [output_grid[r][c] for r, c in pixels]
    #print("  sprite behind_colors:", behind_colors)

    # 3) drop any that are still the sprite’s own color
    filtered = [col for col in behind_colors if col != sprite_color]
    if not filtered:
        #print("→ All sprite spots still sprite_color, returning -1")
        return -1

    # 4) if they’re all the same, that’s your background
    first = filtered[0]
    if all(col == first for col in filtered):
        print(f"→ Uniform sprite behind-color = {first}")
        return first

    # 5) non-uniform → give up
    #print("→ Non-uniform and no neighbor_colors for sprite, returning None")
    return None

# --- GLUED DETECTION PATCH for sprite_analysis.py ---
# Offsets for eight neighbors
NEIGHBORS = [(-1,-1),(-1,0),(-1,1),
             ( 0,-1),        ( 0,1),
             ( 1,-1),( 1,0),( 1,1)]

# Predefined rotation+flip combinations (no zoom, no recolor)
VARIANTS = [
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': True,  'rotated_180': False, 'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': True,  'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': True,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': False,
     'flipped_vert': True,  'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': True,
     'flipped_vert_90': False, 'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': True,  'flipped_horiz_90': False},
    {'rotated_90': False, 'rotated_180': False, 'rotated_270': False,
     'flipped_vert': False, 'flipped_horiz': False,
     'flipped_vert_90': False, 'flipped_horiz_90': True}
]


def reconstruct_sprite_grid(base_pixels_json, flags):
    grid = to_concrete_grid(json.loads(base_pixels_json))
    # no zoom or recolor at this phase
    if flags['rotated_90']:
        grid = rot90(grid)
    if flags['rotated_180']:
        grid = rot180(grid)
    if flags['rotated_270']:
        grid = rot270(grid)
    if flags['flipped_vert']:
        grid = vmirror(grid)
    if flags['flipped_horiz']:
        grid = hmirror(grid)
    if flags['flipped_vert_90']:
        grid = vmirror(rot90(grid))
    if flags['flipped_horiz_90']:
        grid = hmirror(rot90(grid))
    return grid


def is_glued(canvas, mask, y0, x0):
    H, W = len(canvas), len(canvas[0])
    for (y, x) in mask:
        base_color = canvas[y0 + y][x0 + x]
        for dy, dx in NEIGHBORS:
            ny, nx = y0 + y + dy, x0 + x + dx
            if 0 <= ny < H and 0 <= nx < W:
                if (ny - y0, nx - x0) not in mask and canvas[ny][nx] == base_color:
                    return True
    return False

def detect_and_store_glued_and_new(conn, data, filename):
    """
    Scan both directions of glued sprites:
      – OUTPUT-side sprites in sprite_analysis → search in TRAIN inputs
      – INPUT-side  sprites in sprite_analysis → search in TRAIN outputs
    For each rotated/ﬂipped/zoomed/recolored match:
      • ensure a sprite_analysis row exists (insert or UPDATE isGlued=1)
      • upsert a sprite_transformation
      • insert a sprite_occurrence
    """

    # ── build train canvases ──────────────────────────────────────────────────
    train_items   = data.get("train", [])
    train_inputs  = {i: itm["input"]  for i, itm in enumerate(train_items)}
    train_outputs = {i: itm["output"] for i, itm in enumerate(train_items) if "output" in itm}
    print(f"[GLUED] TRAIN count={len(train_items)}; inputs={len(train_inputs)}, outputs={len(train_outputs)}")

    # ── helpers ────────────────────────────────────────────────────────────────
    def sprite_to_grid(sprite_obj: frozenset, bg: int):
        coords = [pos for _, pos in sprite_obj]
        min_r = min(r for r,_ in coords); min_c = min(c for _,c in coords)
        max_r = max(r for r,_ in coords); max_c = max(c for _,c in coords)
        H, W = max_r-min_r+1, max_c-min_c+1
        grid = [[bg]*W for _ in range(H)]
        for color,(r,c) in sprite_obj:
            grid[r-min_r][c-min_c] = color
        return grid

    def generate_geo_variants(g, bg):
        variants = [(g, {})]
        r90  = rot90(tuple(tuple(r) for r in g))
        r270 = rot270(tuple(tuple(r) for r in g))
        variants.append(([list(r) for r in r90],   {"rotated_90": True}))
        variants.append(([list(r) for r in r270],  {"rotated_270": True}))
        spr = asobject(g)
        for fn, flag in [(rot180Sprite, "rotated_180"),
                         (vmirrorSprite, "flipped_vert"),
                         (hmirrorSprite, "flipped_horiz"),
                         (lambda s: rot90Sprite(vmirrorSprite(s)), "flipped_vert_90"),
                         (lambda s: rot90Sprite(hmirrorSprite(s)), "flipped_horiz_90")]:
            so = fn(spr)
            variants.append((sprite_to_grid(so, bg), {flag: True}))
        return variants

    def zoom_variants(g, canvas, skip: bool = False):
        """
        Yield (zoomed_grid, zx, zy) for every zx,zy in 1..5 that fits inside canvas.
        If skip=True, only yields the identity variant (g,1,1).
        """
        H = len(canvas)
        W = len(canvas[0]) if H > 0 else 0

        if skip:
            # only the geo‐variant, no zoom
            yield g, 1, 1
            return

        # try zooms from 1×1 up to 5×5
        for zx in range(1, 6):
            for zy in range(1, 6):
                z = zoom(g, zx, zy)
                if not z:
                    continue
                h = len(z)
                w = len(z[0]) if h > 0 else 0
                # only if it still fits in the canvas
                if h <= H and w <= W:
                    yield z, zx, zy

    def find_matches_with_recolor(cv, pat, skip_recolor=False):
        H, W = len(cv), len(cv[0])
        h, w = len(pat), len(pat[0])
        out = []
        for y0 in range(H - h + 1):
            for x0 in range(W - w + 1):
                cmap = {}
                ok = True
                for dy in range(h):
                    for dx in range(w):
                        pc, gc = pat[dy][dx], cv[y0 + dy][x0 + dx]
                        if skip_recolor:
                            # exact‐match mode:
                            if pc != gc:
                                ok = False
                                break
                        else:
                            # original recolor‐allowed mode:
                            if pc not in cmap:
                                cmap[pc] = gc
                            elif cmap[pc] != gc:
                                ok = False
                                break
                    if not ok:
                        break
                if ok:
                    out.append(((x0, y0, x0 + w, y0 + h), cmap))
        return out

    # ── scan modes ─────────────────────────────────────────────────────────────
    modes = [
        {
          "flag":          "isInsideOutput",
          "filter":        "isInsideOutput=1 AND isInsideTrain=1",
          "pick_canvas":   lambda tr: train_inputs[tr]
        },
        {
          "flag":          "isInsideInput",
          "filter":        "isInsideInput=1 AND isInsideTrain=1",
          "pick_canvas":   lambda tr: train_outputs.get(tr)
        },
    ]

    seen = set()

    for mode in modes:
        sql = f"""
          SELECT id, trainId, testId,
                 data, bgColor, minX, minY, maxX, maxY, isFromGlued
            FROM sprite_analysis
           WHERE pixelCount > 3 AND {mode['filter']}
        """
        for (uid, trainId, testId, data_str, bg,
             minX, minY, maxX, maxY, glued_flag) in conn.execute(sql):

            # pick the canvas first
            canvas = mode["pick_canvas"](trainId)
            if canvas is None:
                continue
            canvas_H = len(canvas)
            canvas_W = len(canvas[0])

            # compute sub‐sprite dims
            H = maxY - minY
            W = maxX - minX

            # skip any sub‐sprite that's bigger than its canvas
            if H > canvas_H or W > canvas_W:
                print(f"⏭ Skipping UID#{uid} – sub‐sprite {H}×{W} exceeds canvas {canvas_H}×{canvas_W}")
                continue

            pxs = json.loads(data_str)  # list of [color, [r, c]]
            base = [[bg] * W for _ in range(H)]
            for color, (r, c) in pxs:
                if 0 <= r < H and 0 <= c < W:
                    base[r][c] = color
                #else:
                    #print(f"⚠️ pixel ({r},{c}) outside local bbox size {H}×{W}")
            #print(f"base ({H}×{W}):")
            #for row in base:
                #print(" ", row)

            for gv, gv_flags in generate_geo_variants(base, bg):
                # gv is the variant grid, gv_flags tells you which geo‐transform it is
                #print(f"[GEO VARIANT] flags = {gv_flags}")
                #print("Variant grid:")
                #for row in gv:
                    #print("  " + "".join(f"{c:2}" for c in row))

                for zv, zx, zy in zoom_variants(gv, canvas, True):
                    # zv is the zoomed grid, zx/zy are the zoom factors
                    #print(f"  [ZOOM] zx={zx}, zy={zy}")
                    #print("  Zoomed grid:")
                    #for row in zv:
                        #print("    " + "".join(f"{c:2}" for c in row))

                    # build the sprite‐object for exact matching
                    so = asobject(zv)
                    h, w = len(zv), len(zv[0])
                    #print(f"    sprite size: {h}×{w}")

                    # look for every match in the full canvas
                    occs = list(occurrences(canvas, so))
                    if not occs:
                        #print("    → no occurrences found on this canvas")
                        continue

                    for y0, x0 in occs:
                        bbox = (x0, y0, x0 + w, y0 + h)
                        #print(f"    [OCCURRENCE] at canvas coords y0={y0}, x0={x0} → bbox={bbox}")

                        cmap = {}  # exact‐match, so no recolor
                        key = (
                            uid,
                            tuple(sorted(gv_flags.items())),
                            zx, zy,
                            tuple(sorted(cmap.items())),
                            bbox
                        )
                        if key in seen:
                            #print("      → already seen, skipping")
                            continue

                        #print("      → new occurrence, processing...")
                        seen.add(key)

                        x0, y0, x1, y1 = bbox

                        # ── A) upsert sprite_analysis with isFromGlued=1 ────────────
                        lookup = conn.execute("""
                          SELECT id, isFromGlued
                            FROM sprite_analysis
                           WHERE trainId=? AND testId=?
                             AND minX=? AND minY=? AND maxX=? AND maxY=?
                             AND isInsideInput=? AND isInsideOutput=?
                        """, [
                          trainId, testId,
                          x0, y0, x1, y1,
                          int(mode["flag"]=="isInsideOutput"),
                          int(mode["flag"]=="isInsideInput")
                        ]).fetchone()
                        #print(f"lookup : trainId: {trainId}")
                        #print(f"lookup : testId: {testId}")
                        #print(f"lookup : x0: {x0}")
                        #print(f"lookup : y0: {y0}")
                        #print(f"lookup : x1: {x1}")
                        #print(f"lookup : y1: {y1}")
                        #print(f"lookup : isInsideInput: {mode['flag']=='isInsideOutput'}")
                        #print(f"lookup : isInsideOutput: {mode['flag']=='isInsideInput'}")
                        #print(f"SELECT id, isFromGlued FROM sprite_analysis WHERE trainId={trainId} AND testId={testId} AND minX={x0} AND minY={y0} AND maxX={x1} AND maxY={y1} AND isInsideInput={mode['flag']=='isInsideOutput'} AND isInsideOutput={mode['flag']=='isInsideInput'}")
                        if lookup:
                            #print("lookup found !")
                            sprite_row_id, existing_glued = lookup
                            if not existing_glued:
                                conn.execute(
                                    "UPDATE sprite_analysis SET isFromGlued=1 WHERE id=?",
                                    [sprite_row_id]
                                )
                        else:
                            flags = {
                              "isInsideInput":   int(mode["flag"]=="isInsideOutput"),
                              "isInsideOutput":  int(mode["flag"]=="isInsideInput"),
                              "isInsideTrain":   1,
                              "isInsideTest":    0,
                              "isInsideBuffer":  0,
                              "isGrid":          0,
                              "isFromSplit":     0,
                              "isFromHole":      0,
                              "isFromCut":       0,
                              "isFromColorZone": 0,
                              "isFromPrevious":  0,
                              "isFromGlued":     1,
                            }
                            spr_def = fill_sprite_attributes(
                                canvas, filename,
                                trainId, testId,
                                flags, zv, bbox
                            )
                            cols = ",".join(spr_def.keys())
                            vals = list(spr_def.values())
                            ph   = ",".join("?" for _ in vals)
                            cur  = conn.execute(
                                f"INSERT INTO sprite_analysis ({cols}) VALUES ({ph})",
                                vals
                            )
                            sprite_row_id = cur.lastrowid

                        # lookup the sprite_unique.id for this sprite_analysis row
                        su_row = conn.execute("""
                                              SELECT id
                                                FROM sprite_unique
                                               WHERE sprite_id=? AND trainId=? AND testId=?
                                            """, [
                            uid, trainId, testId
                        ]).fetchone()
                        if not su_row:
                            # no matching unique → skip this occurrence
                            print(f"[glued] skip occurrence, no sprite_unique for sprite_analysis.id={sprite_row_id}")
                            continue
                        sprite_unique_id = su_row[0]

                        # ── B) upsert sprite_transformation ──────────────────────
                        recolors     = sorted((p,c) for p,c in cmap.items() if p!=c)
                        recolor_json = json.dumps(recolors)
                        trow = conn.execute("""
                          SELECT id
                            FROM sprite_transformation
                           WHERE sprite_unique_id=? AND zoom_x=? AND zoom_y=? 
                             AND recolored=? AND rotated_90=? AND rotated_180=? 
                             AND rotated_270=? AND flipped_vert=? AND flipped_horiz=? 
                             AND flipped_vert_90=? AND flipped_horiz_90=?
                        """, [
                          uid, zx, zy, recolor_json,
                          gv_flags.get("rotated_90",False),
                          gv_flags.get("rotated_180",False),
                          gv_flags.get("rotated_270",False),
                          gv_flags.get("flipped_vert",False),
                          gv_flags.get("flipped_horiz",False),
                          gv_flags.get("flipped_vert_90",False),
                          gv_flags.get("flipped_horiz_90",False),
                        ]).fetchone()
                        if trow:
                            trans_id = trow[0]
                        else:
                            res = conn.execute("""
                              INSERT INTO sprite_transformation
                                (sprite_unique_id,sprite_produce_id,
                                 zoom_x,zoom_y,recolored,
                                 rotated_90,rotated_180,rotated_270,
                                 flipped_vert,flipped_horiz,
                                 flipped_vert_90,flipped_horiz_90)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                            """, [
                              sprite_unique_id, sprite_unique_id,
                              zx, zy, recolor_json,
                              gv_flags.get("rotated_90",False),
                              gv_flags.get("rotated_180",False),
                              gv_flags.get("rotated_270",False),
                              gv_flags.get("flipped_vert",False),
                              gv_flags.get("flipped_horiz",False),
                              gv_flags.get("flipped_vert_90",False),
                              gv_flags.get("flipped_horiz_90",False),
                            ])
                            trans_id = res.lastrowid

                        # ── C) insert sprite_occurrence ─────────────────────────
                        conn.execute("""
                          INSERT INTO sprite_occurrence
                            (sprite_unique_id,
                             sprite_transformation_id,
                             isInsideInput,
                             isInsideOutput,
                             isInsideTrain,
                             isInsideTest,
                             trainId,
                             testId,
                             sprite_id,
                             minX,
                             minY)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, [
                            sprite_unique_id,
                            trans_id,
                            int(mode["flag"]=="isInsideOutput"),
                            int(mode["flag"]=="isInsideInput"),
                            1, 0,
                            trainId,
                            testId,
                            sprite_row_id,
                            x0,
                            y0
                        ])

    conn.commit()


# At end of process_sprites_from_json():
#     detect_and_store_glued_and_new(conn, data)

def detect_zoom_factors(from_sprite, to_sprite):
    h1, w1 = len(from_sprite), len(from_sprite[0])
    h2, w2 = len(to_sprite), len(to_sprite[0])

    #print(f"🧩 Detecting zoom factors:")
    #print(f"   → from_sprite size: {h1}x{w1}")
    #print(f"   → to_sprite size:   {h2}x{w2}")

    # Normal orientation
    if h2 % h1 == 0 and w2 % w1 == 0:
        zx, zy = w2 // w1, h2 // h1
        #print(f"   ✅ Detected zoom (no rotation): x{zx}, y{zy}")
        return (zx, zy)

    # Rotated 90° or 270°
    if w2 % h1 == 0 and h2 % w1 == 0:
        zx, zy = h2 // w1, w2 // h1
        #print(f"   ✅ Detected zoom (rotated): x{zx}, y{zy}")
        return (zx, zy)

    #print(f"   ❌ No valid zoom factor found, returning (1,1)")
    return (1, 1)


###############################################
# sprite_computation function
###############################################

def clear_sprite_computation_table(conn):
    """
    Delete all rows from the sprite_computation table.
    """
    #print("[clear_sprite_computation_table] Deleting all existing rows...")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sprite_computation")
    conn.commit()
    #print("✅ Table cleared.")

def insert_sprite_computation_records(conn, computation_results: list[dict]):
    """
    Insert only computation groups that contain more than one distinct sub_sprite_id for a given (trainId, sprite_id, computation_id).
    """
    print(f"[insert_sprite_computation_records] Filtering {len(computation_results)} records...")
    cursor = conn.cursor()

    # Group results by (trainId, sprite_id, computation_id)
    grouped = defaultdict(list)
    for r in computation_results:
        key = (r["trainId"], r["sprite_id"], r["computation_id"])
        grouped[key].append(r)

    # Only keep groups with multiple distinct sub_sprite_ids
    filtered_rows = [
        r for key, group in grouped.items()
        if len({entry["sub_sprite_id"] for entry in group}) > 1
        for r in group
    ]
    #print(f"✅ Retained {len(filtered_rows)} rows after filtering on unique sub_sprite_id.")

    if not filtered_rows:
        #print("⚠️ No rows to insert.")
        return

    insert_sql = """
    INSERT INTO sprite_computation (
        trainId,
        sprite_id,
        computation_id,
        sub_sprite_id,
        sub_rel_min_x,
        sub_rel_min_y,
        sub_min_x,
        sub_min_y,
        sub_width,
        sub_height,
        sprite_occurrence_id,
        sprite_transformation_id,
        sprite_unique_id,
        sprite_origin_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = [
        (
            r["trainId"],
            r["sprite_id"],
            r["computation_id"],
            r["sub_sprite_id"],
            r["sub_rel_min_x"],
            r["sub_rel_min_y"],
            r["sub_min_x"],
            r["sub_min_y"],
            r["sub_width"],
            r["sub_height"],
            r["sprite_occurrence_id"],
            r["sprite_transformation_id"],
            r["sprite_unique_id"],
            r["sprite_origin_id"]
        )
        for r in filtered_rows
    ]

    cursor.executemany(insert_sql, values)
    conn.commit()
    #print("✅ Insert completed.")

def get_all_sprites_grouped_by_train(conn) -> dict[int, list[dict]]:
    """
    Retrieve all sprites from sprite_analysis, grouped by trainId,
    with each list ordered by descending area (width * height).
    """
    query = """
    SELECT *
    FROM sprite_analysis
    WHERE trainId != -1
    ORDER BY trainId, (width * height) DESC
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]

    sprite_map = defaultdict(list)
    for row in cursor.fetchall():
        row_dict = dict(zip(columns, row))
        train_id = row_dict["trainId"]
        sprite_map[train_id].append(row_dict)

    return dict(sprite_map)

def is_fully_inside(sub, main_bbox, main_mask):
    """
    Check if all pixels of the sub sprite are inside the main sprite's bounding box
    and do not overlap -1 regions in the main_mask.
    """
    min_x, min_y, max_x, max_y = main_bbox
    for val, (i, j) in json.loads(sub["data"]):
        abs_x = sub["minX"] + j
        abs_y = sub["minY"] + i
        rel_x = abs_x - min_x
        rel_y = abs_y - min_y

        if not (min_x <= abs_x < max_x and min_y <= abs_y < max_y):
            return False
        if not (0 <= rel_y < len(main_mask) and 0 <= rel_x < len(main_mask[0])):
            return False
        if main_mask[rel_y][rel_x] == -1:
            return False
    return True

def can_place_subsprite(mask, sub, offset_x, offset_y, main_sprite):
    """
    Check if all sub sprite pixels can be placed in the mask without
    overlapping existing pixels, and that each pixel value matches the corresponding
    pixel in the main_sprite.
    """
    height = main_sprite["height"]
    width = main_sprite["width"]
    main_grid = [[-1 for _ in range(width)] for _ in range(height)]

    for val, (i, j) in json.loads(main_sprite["data"]):
        if 0 <= i < height and 0 <= j < width:
            main_grid[i][j] = val
        else:
            #print(f"⚠️ Skipping out-of-bounds main_sprite pixel at ({i}, {j})")
            continue

    for val, (i, j) in json.loads(sub["data"]):
        abs_y = sub["minY"] + i
        abs_x = sub["minX"] + j
        rel_y = abs_y - offset_y
        rel_x = abs_x - offset_x

        try:
            if mask[rel_y][rel_x] != -8:
                return False
            if not (0 <= abs_y < height and 0 <= abs_x < width):
                return False
            if main_grid[abs_y][abs_x] != val:
                return False
        except IndexError:
            return False

    return True

def place_subsprite(mask, sub, offset_x, offset_y):
    """Write the sub sprite into the given mask."""
    for val, (i, j) in json.loads(sub["data"]):
        mask_i = i + (sub["minY"] - offset_y)
        mask_j = j + (sub["minX"] - offset_x)
        mask[mask_i][mask_j] = val

def is_fully_filled(mask):
    """Return True if there is no -8 or -1 left."""
    return all((cell != -8 and cell != -1) for row in mask for cell in row)

def build_empty_mask_from_data(main_sprite):
    """Create a mask grid from the sprite data, with -8 where pixels are expected, and -1 elsewhere."""
    w, h = main_sprite["width"], main_sprite["height"]
    mask = [[-1 for _ in range(w)] for _ in range(h)]
    for val, (i, j) in json.loads(main_sprite["data"]):
        if 0 <= i < h and 0 <= j < w:
            mask[i][j] = -8
    return mask

import json

import json

import json

def detect_and_store_sprite_computation(conn, data=None):
    """
    For each train, find “main” output sprites and see which smaller output sprites
    fit inside them. Then pick a single, consistent transformation (by flags)
    for each (main, sub) pair—namely the one whose flag-tuple appears in every train
    and which maps back to an input-side sprite. Finally record the computation results.
    """
    #print("[detect_and_store_sprite_computation] Starting")
    clear_sprite_computation_table(conn)

    # 1) Load all OUTPUT-side sprites, grouped by trainId
    sprites_by_train = get_all_sprites_grouped_by_train(conn)

    # 2) FIRST PASS: collect, for each (main_id, sub_id), the set of flag-tuples seen
    transform_candidates: dict[tuple[int,int], set[tuple]] = {}

    for trainId, sprite_list in sprites_by_train.items():
        mains = [s for s in sprite_list if s["isInsideOutput"]]
        print(f"\n[PASS1] TRAIN {trainId}: found {len(mains)} mains")
        for main in mains:
            mid = main["id"]
            mbbox = (main["minX"], main["minY"], main["maxX"], main["maxY"])
            main_mask = build_empty_mask_from_data(main)

            for sub in mains:
                sid = sub["id"]
                if sid == mid or not is_fully_inside(sub, mbbox, main_mask):
                    continue

                # fetch all matching transformations for this sub-sprite,
                # but only those that map back to an input-side sprite
                rows = conn.execute("""
                    SELECT 
                      st.id                            AS trans_id,
                      st.inverted, st.rotated_90, st.rotated_180, st.rotated_270,
                      st.flipped_vert, st.flipped_horiz,
                      st.flipped_vert_90, st.flipped_horiz_90,
                      st.zoom_x, st.zoom_y,
                      st.recolored
                    FROM sprite_occurrence AS occ
                    JOIN sprite_transformation AS st
                      ON occ.sprite_transformation_id = st.id
                    JOIN sprite_unique      AS su
                      ON st.sprite_unique_id = su.id
                    JOIN sprite_analysis    AS sa
                      ON su.sprite_id = sa.id
                      AND sa.isInsideInput = 1
                    WHERE occ.sprite_id      = ?
                      AND occ.isInsideOutput = 1
                      AND occ.trainId        = ?
                """, (sid, trainId)).fetchall()

                flag_list = []
                for (_trans_id,
                     inv, r90, r180, r270,
                     fv, fh, fv90, fh90,
                     zx, zy, recolored_json) in rows:
                    raw = json.loads(recolored_json)
                    # convert inner lists to tuples so the whole thing is hashable
                    pairs = tuple(tuple(p) for p in raw)
                    fl = (inv, r90, r180, r270, fv, fh, fv90, fh90, zx, zy, pairs)
                    flag_list.append(fl)

                print(f"  MAIN#{mid} SUB#{sid} TRAIN#{trainId} flags found:")
                for fl in flag_list:
                    print(f"    {fl}")

                key = (mid, sid)
                if key not in transform_candidates:
                    transform_candidates[key] = set(flag_list)
                else:
                    transform_candidates[key] &= set(flag_list)

                print(f"  → candidates now for MAIN#{mid} SUB#{sid}:")
                for fl in sorted(transform_candidates[key]):
                    print(f"     {fl}")

    # 3) Pick one flag-tuple per (main, sub): lexicographically smallest
    chosen_flags: dict[tuple[int,int], tuple|None] = {}
    for key, flags in transform_candidates.items():
        if not flags:
            print(f"[CHOICE] MAIN#{key[0]} SUB#{key[1]} → NO common transform")
            chosen_flags[key] = None
        else:
            choice = sorted(flags)[0]
            print(f"[CHOICE] MAIN#{key[0]} SUB#{key[1]} → chosen {choice}")
            chosen_flags[key] = choice

    # 4) SECOND PASS: record computations using chosen_flags
    computation_results = []

    for trainId, sprite_list in sprites_by_train.items():
        mains = [s for s in sprite_list if s["isInsideOutput"]]
        print(f"\n[PASS2] TRAIN {trainId}: recording computations")
        for main in mains:
            mid = main["id"]
            mbbox = (main["minX"], main["minY"], main["maxX"], main["maxY"])
            main_mask = build_empty_mask_from_data(main)

            masks: list[list[list[int]]] = []
            mask_maps: list[list[dict]] = []

            # assemble “fills”
            for sub in mains:
                sid = sub["id"]
                if sid == mid or not is_fully_inside(sub, mbbox, main_mask):
                    continue

                placed = False
                for mask, subs in zip(masks, mask_maps):
                    if can_place_subsprite(mask, sub, mbbox[0], mbbox[1], main):
                        place_subsprite(mask, sub, mbbox[0], mbbox[1])
                        subs.append(sub)
                        placed = True
                        break

                if not placed:
                    new_mask = build_empty_mask_from_data(main)
                    if can_place_subsprite(new_mask, sub, mbbox[0], mbbox[1], main):
                        place_subsprite(new_mask, sub, mbbox[0], mbbox[1])
                        masks.append(new_mask)
                        mask_maps.append([sub])

            comp_id = 1
            for mask, subs in zip(masks, mask_maps):
                if not is_fully_filled(mask):
                    print(f"  MAIN#{mid} fill#{comp_id} incomplete, skipping")
                    comp_id += 1
                    continue

                print(f"  MAIN#{mid} fill#{comp_id} COMPLETE with {len(subs)} subs")
                print(grid_to_pretty_string(mask))
                for sub in subs:
                    print(grid_to_pretty_string(to_concrete_grid(json.loads(sub["data"]))))
                    sid = sub["id"]
                    key = (mid, sid)
                    flags = chosen_flags[key]

                    sprite_occurrence_id = None
                    sprite_transformation_id = None
                    sprite_unique_id = None
                    sprite_origin_id = None

                    if flags is not None:
                        (inv, r90, r180, r270,
                         fv, fh, fv90, fh90,
                         zx, zy, pairs) = flags
                        recolored_json = json.dumps([list(p) for p in pairs])

                        occ = conn.execute("""
                            SELECT
                              occ.id                   AS sprite_occurrence_id,
                              occ.sprite_unique_id,
                              occ.sprite_transformation_id,
                              su.sprite_id             AS sprite_origin_id
                            FROM sprite_occurrence AS occ
                            JOIN sprite_transformation AS st
                              ON occ.sprite_transformation_id = st.id
                            JOIN sprite_unique      AS su
                              ON st.sprite_unique_id = su.id
                            JOIN sprite_analysis    AS sa
                              ON su.sprite_id = sa.id
                              AND sa.isInsideInput = 1
                            WHERE occ.sprite_id = ?
                              AND occ.trainId     = ?
                              AND st.inverted     = ?
                              AND st.rotated_90   = ?
                              AND st.rotated_180  = ?
                              AND st.rotated_270  = ?
                              AND st.flipped_vert = ?
                              AND st.flipped_horiz= ?
                              AND st.flipped_vert_90 = ?
                              AND st.flipped_horiz_90= ?
                              AND st.zoom_x       = ?
                              AND st.zoom_y       = ?
                              AND st.recolored    = ?
                        """, (
                            sid, trainId,
                            inv, r90, r180, r270,
                            fv, fh, fv90, fh90,
                            zx, zy, recolored_json
                        )).fetchone()

                        if occ:
                            (sprite_occurrence_id,
                             sprite_unique_id,
                             sprite_transformation_id,
                             sprite_origin_id) = occ
                            print(f"    SUB#{sid} → TRANS#{sprite_transformation_id} flags={flags}")
                        else:
                            print(f"    WARNING: SUB#{sid} no match for chosen flags {flags}")
                    else:
                        print(f"    SUB#{sid} has no common transform; leaving IDs null")

                    rel_x = sub["minX"] - main["minX"]
                    rel_y = sub["minY"] - main["minY"]
                    computation_results.append({
                        "trainId":                   trainId,
                        "sprite_id":                 mid,
                        "computation_id":            comp_id,
                        "sub_sprite_id":             sid,
                        "sub_rel_min_x":             rel_x,
                        "sub_rel_min_y":             rel_y,
                        "sub_min_x":                 sub["minX"],
                        "sub_min_y":                 sub["minY"],
                        "sub_width":                 sub["width"],
                        "sub_height":                sub["height"],
                        "sprite_occurrence_id":      sprite_occurrence_id,
                        "sprite_transformation_id":  sprite_transformation_id,
                        "sprite_unique_id":          sprite_unique_id,
                        "sprite_origin_id":          sprite_origin_id
                    })

                comp_id += 1

    computation_results = prune_overlapping_by_train(computation_results)
    #print("\nAll computation results:", computation_results)
    insert_sprite_computation_records(conn, computation_results)
    return computation_results

def prune_overlapping_by_train(
    computation_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Remove any ‘minor’ computation (group of subs with the same computation_id)
    whose absolute bounding‐box overlaps a larger one, per trainId.
    """
    pruned: List[Dict[str,Any]] = []
    # 1) group by trainId
    by_train: Dict[int, List[Dict[str,Any]]] = defaultdict(list)
    for entry in computation_results:
        by_train[entry["trainId"]].append(entry)

    # 2) process each train independently
    for trainId, entries in by_train.items():
        # cluster entries by computation_id
        comps: Dict[int, List[Dict[str,Any]]] = defaultdict(list)
        for e in entries:
            comps[e["computation_id"]].append(e)

        # if only one computation in this train, keep it wholesale
        if len(comps) == 1:
            pruned.extend(entries)
            continue

        # 3) compute each computation's absolute bbox and area
        boxes: Dict[int, Tuple[int,int,int,int]] = {}
        areas: Dict[int, int] = {}
        for cid, subs in comps.items():
            xs   = [ s["sub_min_x"] for s in subs ]
            ys   = [ s["sub_min_y"] for s in subs ]
            x1s  = [ s["sub_min_x"] + s["sub_width"]  for s in subs ]
            y1s  = [ s["sub_min_y"] + s["sub_height"] for s in subs ]
            minx, miny = min(xs), min(ys)
            maxx, maxy = max(x1s), max(y1s)
            boxes[cid] = (minx, miny, maxx, maxy)
            areas[cid] = (maxx-minx) * (maxy-miny)

        # 4) sort cids by descending area
        sorted_cids = sorted(boxes.keys(), key=lambda c: areas[c], reverse=True)

        # 5) pick non-overlapping ones
        accepted = []
        occupied: List[Tuple[int,int,int,int]] = []
        for cid in sorted_cids:
            bx = boxes[cid]
            # check overlap with any previously accepted
            overlap = any(
                not (bx[2] <= ob[0] or bx[0] >= ob[2] or bx[3] <= ob[1] or bx[1] >= ob[3])
                for ob in occupied
            )
            if not overlap:
                accepted.append(cid)
                occupied.append(bx)

        # 6) collect all subs for accepted cids
        for cid in accepted:
            pruned.extend(comps[cid])

    return pruned

def has_constant_border(grid):
    if not grid or not grid[0]:
        #print("❌ Grid is empty or malformed")
        return False

    height = len(grid)
    width = len(grid[0])
    #print(f"✔️ Grid dimensions: height={height}, width={width}")
    if height < 3 or width < 3:
        #print("❌ Grid too small to have border + inner content")
        return False

    # Check that all borders are the same color and constant
    top = grid[0]
    bottom = grid[-1]
    left = [row[0] for row in grid]
    right = [row[-1] for row in grid]

    #print(f"Top border: {top}")
    #print(f"Bottom border: {bottom}")
    #print(f"Left border: {left}")
    #print(f"Right border: {right}")

    if not (all(c == top[0] for c in top) and
            all(c == bottom[0] for c in bottom) and
            all(c == left[0] for c in left) and
            all(c == right[0] for c in right)):
        #print("❌ Not all border lines are constant")
        return False

    border_color = top[0]
    if not (border_color == bottom[0] == left[0] == right[0]):
        #print("❌ Border colors are not consistent")
        return False

    #print(f"✔️ Border color: {border_color}")

    # Extract inner lines adjacent to the border
    inner_top = grid[1][1:-1]
    inner_bottom = grid[-2][1:-1]
    inner_left = [grid[y][1] for y in range(1, height - 1)]
    inner_right = [grid[y][-2] for y in range(1, height - 1)]

    #print(f"Inner top line: {inner_top}")
    #print(f"Inner bottom line: {inner_bottom}")
    #print(f"Inner left line: {inner_left}")
    #print(f"Inner right line: {inner_right}")

    def is_different(line): return any(c != border_color for c in line)

    if not (is_different(inner_top) and
            is_different(inner_bottom) and
            is_different(inner_left) and
            is_different(inner_right)):
        #print("❌ One or more inner lines are not different from border")
        return False

    #print("✅ Grid has a valid constant border with distinct inner lines")
    return True


###############################################
# Main function
###############################################
def main(json_source, *, inline=False, name=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path    = os.path.abspath(os.path.join(script_dir, "..", "db", "database.db"))
    conn       = sqlite3.connect(db_path)

    # Determine the “filename” label for the run:
    if name:
        filename = name
    elif inline:
        filename = "<in-memory-json>"
    else:
        filename = os.path.basename(json_source)

    # Load the JSON data
    if inline:
        data = json.loads(json_source)
    else:
        with open(json_source, "r") as f:
            data = json.load(f)

    process_sprites_from_json(filename, data, conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute sprite_analysis from an ARC JSON — either by file or by raw JSON string."
    )
    parser.add_argument(
        "json_input",
        help="Path to an ARC JSON file, or (with --inline) a raw JSON string"
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Treat json_input as raw JSON text rather than a file path"
    )
    parser.add_argument(
        "--name", "-n",
        help="If provided, use this as the scenario name instead of the file basename"
    )
    args = parser.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)