import os
import sqlite3
import json
import math
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
    """
    Return a dict with nbBlack, nbBlue, nbRed, etc.
    Adjust color indexes as you wish.
    """
    nbBlack    = sum(cell == 0 for row in sprite_grid for cell in row)
    nbBlue     = sum(cell == 1 for row in sprite_grid for cell in row)
    nbRed      = sum(cell == 2 for row in sprite_grid for cell in row)
    nbGreen    = sum(cell == 3 for row in sprite_grid for cell in row)
    nbYellow   = sum(cell == 4 for row in sprite_grid for cell in row)
    nbGrey     = sum(cell == 5 for row in sprite_grid for cell in row)
    nbFuchsia  = sum(cell == 6 for row in sprite_grid for cell in row)
    nbOrange   = sum(cell == 7 for row in sprite_grid for cell in row)
    nbTeal     = sum(cell == 8 for row in sprite_grid for cell in row)
    nbBrown    = sum(cell == 9 for row in sprite_grid for cell in row)
    return {
        "nbBlack": nbBlack,
        "nbBlue": nbBlue,
        "nbRed": nbRed,
        "nbGreen": nbGreen,
        "nbYellow": nbYellow,
        "nbGrey": nbGrey,
        "nbFuchsia": nbFuchsia,
        "nbOrange": nbOrange,
        "nbTeal": nbTeal,
        "nbBrown": nbBrown
    }

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


def compute_transformation_flags(sprite_grid):
    """
    Compute and return a tuple of eight booleans for the sprite:
      (inverted, rotated_90, rotated_180, rotated_270,
       flipped_vert, flipped_horiz, flipped_vert_90, flipped_horiz_90)

    Here, for simplicity, "inverted" could be defined as a sprite that remains the same
    after inverting its colors (if that makes sense) or you may set it to False if not used.
    Adjust this logic as needed.
    """
    base_obj = safe_asobject(sprite_grid)

    # For the rotations and mirrors, we use our sprite-specific functions
    r90 = safe_asobject(rot90Sprite(sprite_grid))
    r180 = safe_asobject(rot180Sprite(sprite_grid))
    r270 = safe_asobject(rot270Sprite(sprite_grid))
    fv = safe_asobject(vmirrorSprite(sprite_grid))
    fh = safe_asobject(hmirrorSprite(sprite_grid))
    fv90 = safe_asobject(vmirrorSprite(rot90Sprite(sprite_grid)))
    fh90 = safe_asobject(hmirrorSprite(rot90Sprite(sprite_grid)))

    # Here, we set "inverted" to False (or you can implement your own inversion check)
    inverted = False

    return (inverted,
            base_obj == r90,
            base_obj == r180,
            base_obj == r270,
            base_obj == fv,
            base_obj == fh,
            base_obj == fv90,
            base_obj == fh90)


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
        (inverted, False, False, False, False, False, True, False)
    ))

    # 8) flipped_horiz_90
    fh90_obj = hmirrorSprite(r90_obj)
    fh90_canon = canonical_sprite_representation(fh90_obj)
    transformations_to_test.append((fh90_canon,
        (inverted, False, False, False, False, False, False, True)
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



def store_in_sprite_unique_and_occurrence(attr_dict, sprite_grid, global_data):
    """
    Insert a sprite into sprite_unique and sprite_occurrence tables,
    avoiding duplicates. Use a unified function that both detects duplicates
    and computes transformation flags, so we know exactly which transformation matched.
    """

    # 1) Use a unified function that returns (existing_sprite_id, flags),
    #    e.g. find_existing_sprite_and_flags(sprite_grid, global_data).
    #    If no existing sprite is found, existing_sprite_id = None, but we still get flags
    #    for the *original* sprite (or whichever transformation we choose as default).
    existing_sprite_id, flags = find_existing_sprite_and_flags(sprite_grid, global_data)
    (inverted, r90, r180, r270, fv, fh, fv90, fh90) = flags

    # 2) If we found an existing sprite, reuse its ID. Otherwise create a new sprite_unique entry.
    if existing_sprite_id is not None:
        sprite_unique_id = existing_sprite_id
    else:
        sprite_unique_id = global_data["next_sprite_id"]
        global_data["next_sprite_id"] += 1

        # Use canonical representation for the original (or whichever base transform we want).
        canon = canonical_sprite_representation(sprite_grid)
        global_data["sprites_map"][canon] = sprite_unique_id

        # Build sprite_unique record
        h = len(sprite_grid)
        w = len(sprite_grid[0]) if h > 0 else 0
        pixel_count = h * w
        color_count = color_counts_in_sprite(sprite_grid)
        rec = {
            "id": sprite_unique_id,
            "filename": attr_dict["filename"],
            "height": h,
            "width": w,
            "pixel_count": pixel_count,
            "nbBlack": color_count["nbBlack"],
            "nbBlue": color_count["nbBlue"],
            "nbRed": color_count["nbRed"],
            "nbGreen": color_count["nbGreen"],
            "nbYellow": color_count["nbYellow"],
            "nbGrey": color_count["nbGrey"],
            "nbFuchsia": color_count["nbFuchsia"],
            "nbOrange": color_count["nbOrange"],
            "nbTeal": color_count["nbTeal"],
            "nbBrown": color_count["nbBrown"],
            "data": canon
        }
        global_data["sprite_unique_records"].append(rec)

    # 3) Manage the sprite_transformation record
    tkey = (sprite_unique_id, inverted, r90, r180, r270, fv, fh, fv90, fh90)

    if tkey in global_data["sprite_trans_map"]:
        # If it’s already recorded, reuse that ID
        sprite_transformation_id = global_data["sprite_trans_map"][tkey]
    else:
        # Create a new sprite_transformation record
        sprite_transformation_id = global_data["next_sprite_trans_id"]
        global_data["next_sprite_trans_id"] += 1
        global_data["sprite_trans_map"][tkey] = sprite_transformation_id

        trec = {
            "id": sprite_transformation_id,
            "sprite_unique_id": sprite_unique_id,
            "inverted": inverted,
            "rotated_90": r90,
            "rotated_180": r180,
            "rotated_270": r270,
            "flipped_vert": fv,
            "flipped_horiz": fh,
            "flipped_vert_90": fv90,
            "flipped_horiz_90": fh90
        }
        global_data["sprite_trans_records"].append(trec)

    # 4) Build the occurrence record
    occ = {
        "sprite_unique_id": sprite_unique_id,
        "sprite_transformation_id": sprite_transformation_id,
        "isInsideInput":  attr_dict["isInsideInput"],
        "isInsideOutput": attr_dict["isInsideOutput"],
        "isInsideTrain":  attr_dict["isInsideTrain"],
        "isInsideTest":   attr_dict["isInsideTest"],
        "trainId": attr_dict["trainId"] if attr_dict["isInsideTrain"] else -1,
        "testId":  attr_dict["testId"]  if attr_dict["isInsideTest"]  else -1,
        "sprite_id": attr_dict["id"],  # If linking to some "sprite_analysis" row
        "minX": attr_dict["minX"],
        "minY": attr_dict["minY"]
    }
    global_data["sprite_occ_records"].append(occ)



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

    # For dimension, we can do:
    h = len(sprite)
    w = len(sprite[0]) if h>0 else 0
    from solver.dsl import compute_pixel_perimeter, asindices
    attr["height"] = h
    attr["width"] = w
    attr["ratioWidthHeight"] = safe_divide(w,h)
    attr["area"] = h*w
    attr["pixelCount"] = w*h
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
            "isFromCut": False
        }
        sprite = fill_sprite_attributes(grid, filename, trainId, testId, flags, subgrid, bbox)
        sprite["minX"], sprite["minY"], sprite["maxX"], sprite["maxY"] = bbox
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
        "isFromCut": True
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
    print("----------------------")
    print("pad_grid")
    print("grid", grid)
    print("pad_value", pad_value)
    print("pad_width", pad_width)
    print("----------------------")
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
    print("----------------------")
    print("pad_mask")
    print("mask", mask)
    print("pad_value", pad_value)
    print("pad_width", pad_width)
    print("----------------------")
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
    print("----------------------")
    print("count_gap_groups")
    print("line", line)
    print("----------------------")
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
    print("----------------------")
    print("eligible_border_gap")
    print("borders", borders)
    print("----------------------")
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


def compute_hole_sprites(grid, filename, trainId, testId, isInsideInput):
    """
    - We skip objects < 8 pixels.
    - For each object subgrid, remove non-bg blocks from edges
      only if that edge is not also the grid boundary.
    - Then unify holes (non-bg) via objects_with_explicit_bg.
    """
    import json
    from solver.dsl import color_of, toindices, crop, asobject

    sprites = []
    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h>0 else 0

    all_objects = zones(grid)  # or your DSL
    for obj in all_objects:
        indices = list(toindices(obj))
        if not indices:
            continue

        # skip if <8 pixels
        if len(indices)<8:
            continue

        # bounding box
        min_row = min(r for r,c in indices)
        max_row = max(r for r,c in indices)+1
        min_col = min(c for r,c in indices)
        max_col = max(c for r,c in indices)+1
        obj_h = max_row - min_row
        obj_w = max_col - min_col

        subgrid_obj = crop(grid, (min_row, min_col), (obj_h, obj_w))
        obj_bg = color_of(obj)

        # Decide for each side if it's internal to the grid
        # top_internal => True if min_row>0
        top_internal = (min_row>0)
        bottom_internal = (max_row<grid_h)
        left_internal = (min_col>0)
        right_internal= (max_col<grid_w)

        # remove non-bg blocks from these edges if the side is internal
        remove_border_colored_blocks_subgrid(
            subgrid_obj,
            obj_bg,
            top_internal=top_internal,
            bottom_internal=bottom_internal,
            left_internal=left_internal,
            right_internal=right_internal,
            diagonal=False
        )

        # Now unify all subgrid pixels != obj_bg => hole detection
        holes = objects_with_explicit_bg(
            subgrid_obj,
            univalued=False,
            diagonal=True,
            skip_color=obj_bg
        )

        for region in holes:
            coords = [pos for (clr,pos) in region]
            sub_min_i = min(r for r,c in coords)
            sub_max_i = max(r for r,c in coords)+1
            sub_min_j = min(c for r,c in coords)
            sub_max_j = max(c for r,c in coords)+1

            # Build hole grid
            region_set = {pos for (clr,pos) in region}
            hole_h = sub_max_i - sub_min_i
            hole_w = sub_max_j - sub_min_j
            hole_grid = []
            for i in range(sub_min_i, sub_max_i):
                row_data=[]
                for j in range(sub_min_j, sub_max_j):
                    if (i,j) in region_set:
                        row_data.append(subgrid_obj[i][j])
                    else:
                        row_data.append(obj_bg)
                hole_grid.append(row_data)

            # bounding box in global coords
            global_minX = min_col+sub_min_j
            global_maxX = min_col+sub_max_j
            global_minY = min_row+sub_min_i
            global_maxY = min_row+sub_max_i
            bbox = (global_minX, global_minY, global_maxX, global_maxY)

            flags = {
                "isInsideInput": isInsideInput,
                "isInsideOutput": not isInsideInput,
                "isInsideTrain": (trainId!=-1),
                "isInsideTest": (testId!=-1),
                "isInsideBuffer":False,
                "isGrid":False,
                "isFromSplit":False,
                "isFromHole":True,
                "isFromCut":False
            }
            spr = fill_sprite_attributes(grid, filename, trainId, testId, flags, hole_grid, bbox)
            hole_obj = asobject(hole_grid)
            final_obj = frozenset((c,pos) for (c,pos) in hole_obj if c!=obj_bg)
            # If at least 2 distinct colors remain:
            if len({c for c,_ in final_obj})>=2:
                spr["data"]=json.dumps(list(final_obj))
                spr["nbColors"] = len({c for c,_ in final_obj})
                spr["bgColor"] = obj_bg
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

    def process_item(item, is_input, index):
        nonlocal next_sprite_analysis_id
        # 0. Basic info
        grid = item["input"] if is_input else item["output"]
        if "train" in data:
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
            "isFromCut": False
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
        split_sprites = compute_split_sprites_by_ratio(item["input"], item["output"], filename, trainId, testId, is_input)
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

    for index, item in enumerate(data.get("train", [])):
        if index < 30:
            process_item(item, True, index)  # Process input grid.
            process_item(item, False, index)  # Process output grid.

    #for index, item in enumerate(data.get("test", [])):
    #    process_item(item, True, index)

    bulk_insert(conn, "sprite_analysis", all_sprite_analysis_rows)
    bulk_insert(conn, "sprite_unique", sprite_global_data["sprite_unique_records"])
    bulk_insert(conn, "sprite_transformation", sprite_global_data["sprite_trans_records"])
    bulk_insert(conn, "sprite_occurrence", sprite_global_data["sprite_occ_records"])
    conn.commit()


###############################################
# Main function
###############################################

def main(json_filepath):
    conn = sqlite3.connect("../db/database.db")
    with open(json_filepath, "r") as file:
        data = json.load(file)
    process_sprites_from_json(os.path.basename(json_filepath), data, conn)
    conn.close()


if __name__ == "__main__":
    main("./data/training-1/3c9b0459.json")
#   main("./data/tests/test_sprites_1.json")
