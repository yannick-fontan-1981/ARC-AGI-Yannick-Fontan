# object_analysis.py
import argparse
import os
import sqlite3
import json
import sys

from sympy import false

from constelize.tools.extract_common_attribute import find_minimal_selection_criteria_for_table, \
    find_minimal_selection_criteria_for_table_strict
from constelize.tools.sqlite_loader import load_table_from_sqlite
from solver.dsl import *
import time
from collections import OrderedDict, Counter, defaultdict


def compute_object_analysis(filename: str, trainId: int, testId: int, grid, isInsideInput: bool, global_data, conn):
    """
    Extract objects and their attributes from a grid using DSL functions.

    Returns a list of tuples (obj_row, occ_row) where:
      - obj_row is a dict with the columns to be inserted into the object_analysis table.
      - occ_row is a dict with the columns for the shape_occurrence table (except for object_id, which is added later).

    In addition, this function uses and updates global_data (a dict) that holds:
      - a mapping (shapes_map) for shapes encountered and their programmatically assigned id.
      - a mapping (trans_map) for shape_transformation records.
      - lists of records (to be bulk-inserted) for shape and shape_transformation.
    """
    grid = convert_to_tuple_of_tuples(grid)  # Ensure consistency

    results = []  # List of (obj_row, occ_row) tuples.
    blocks_in = blocks(grid)
    zones_in = zones(grid)

    # Ensure each object appears only once (zones first).
    all_zones = list(zones_in)
    all_blocks = list(blocks_in)
    all_objects = list(OrderedDict.fromkeys(all_zones + [b for b in all_blocks if b not in set(all_zones)]))

    # Get references to the global id managers and record lists.
    shapes_map = global_data["shapes_map"]  # key: json string of shape data, value: shape id.
    shape_records = global_data["shape_records"]  # list of shape records (dicts)
    trans_map = global_data["trans_map"]  # key: (shape_id, color, rotated_90, ..., flipped_horiz_90)
    trans_records = global_data["trans_records"]  # list of transformation records (dicts)

    for obj in all_objects:
        # --- Compute shape information ---
        base_shape = extract_shape(obj)  # the shape (as a set or list of pixel positions)
        heightShape = len(base_shape)
        widthShape = max(c for r, c in base_shape) + 1 if base_shape else 0
        pixel_count = len(base_shape)
        color = color_of(obj)

        # Generate all possible transformations.
        transformations = {
            "original": base_shape,
            "rotated_90": rot90Shape(base_shape),
            "rotated_180": rot180Shape(base_shape),
            "rotated_270": rot270Shape(base_shape),
            "flipped_vert": vmirrorShape(base_shape),
            "flipped_horiz": hmirrorShape(base_shape),
        }

        stored_shape_id = None
        stored_version = None
        is_first_occurrence = False

        shapeData = json.dumps(sorted(base_shape))

        # Instead of querying the database, check our in‑memory shapes_map.
        for variant in transformations.values():
            key = json.dumps(sorted(variant))
            if key in shapes_map:
                stored_shape_id = shapes_map[key]
                stored_version = variant
                break
        if stored_shape_id is None:
            # This shape (or any of its transformations) has not been seen before.
            stored_shape_id = global_data["next_shape_id"]
            global_data["next_shape_id"] += 1
            shapes_map[shapeData] = stored_shape_id
            # Build the shape record.
            shape_record = {
                "id": stored_shape_id,
                "filename": filename,
                "height": heightShape,
                "width": widthShape,
                "pixel_count": pixel_count,
                "data": shapeData
            }
            shape_records.append(shape_record)
            stored_version = base_shape
            is_first_occurrence = True

        is_same_exactly_same = (base_shape == stored_version)

        # Build all candidate transforms of the base shape
        cands = {
            "rot90": rot90Shape(base_shape),
            "rot180": rot180Shape(base_shape),
            "rot270": rot270Shape(base_shape),
            "flipped_vert": vmirrorShape(base_shape),
            "flipped_horiz": hmirrorShape(base_shape),
            "flipped_vert_90": vmirrorShape(rot90Shape(base_shape)),
            "flipped_horiz_90": hmirrorShape(rot90Shape(base_shape)),
        }

        # Determine which transform matches the stored version
        flags = {
            name: (sorted(variant) == sorted(stored_version))
            for name, variant in cands.items()
        }

        # If shape is invariant under any transform, clear all flags
        for name, variant in cands.items():
            if sorted(variant) == sorted(base_shape):
                flags = {n: False for n in flags}
                break

        # Also clear flags for trivial or first occurrence
        if pixel_count == 1 or is_same_exactly_same or is_first_occurrence:
            flags = {n: False for n in flags}

        # Unpack flags
        rotated_90     = flags["rot90"]
        rotated_180    = flags["rot180"]
        rotated_270    = flags["rot270"]
        flipped_vert   = flags["flipped_vert"]
        flipped_horiz  = flags["flipped_horiz"]
        flipped_vert_90 = flags["flipped_vert_90"]
        flipped_horiz_90 = flags["flipped_horiz_90"]


        # --- Manage the shape_transformation record in memory ---
        trans_key = (stored_shape_id, color, rotated_90, rotated_180, rotated_270,
                     flipped_vert, flipped_horiz, flipped_vert_90, flipped_horiz_90)
        if trans_key in trans_map:
            transformation_id = trans_map[trans_key]
        else:
            transformation_id = global_data["next_trans_id"]
            global_data["next_trans_id"] += 1
            trans_map[trans_key] = transformation_id
            trans_record = {
                "id": transformation_id,
                "shape_id": stored_shape_id,
                "color": color,
                "rotated_90": rotated_90,
                "rotated_180": rotated_180,
                "rotated_270": rotated_270,
                "flipped_vert": flipped_vert,
                "flipped_horiz": flipped_horiz,
                "flipped_vert_90": flipped_vert_90,
                "flipped_horiz_90": flipped_horiz_90
            }
            trans_records.append(trans_record)

        # --- Build alignment and positional data ---
        current_align = build_align_data(obj)

        # --- Build the object_analysis row (obj_row) ---
        # Note: The object_analysis table does not include shape_id fields.
        obj_row = {}
        obj_row["filename"] = filename
        obj_row["trainId"] = trainId
        obj_row["testId"] = testId
        obj_row["isInsideInput"] = isInsideInput
        obj_row["isInsideOutput"] = not isInsideInput
        obj_row["isInsideTrain"] = (trainId != -1)
        obj_row["isInsideTest"] = (testId != -1)
        obj_row["isBlock"] = (obj in blocks_in)
        obj_row["isZone"] = (obj in zones_in)
        obj_row["color"] = color
        obj_row["isBlack"]   = (color == 0)
        obj_row["isBlue"]    = (color == 1)
        obj_row["isRed"]     = (color == 2)
        obj_row["isGreen"]   = (color == 3)
        obj_row["isYellow"]  = (color == 4)
        obj_row["isGrey"]    = (color == 5)
        obj_row["isFuchsia"] = (color == 6)
        obj_row["isOrange"]  = (color == 7)
        obj_row["isTeal"]    = (color == 8)
        obj_row["isBrown"]   = (color == 9)

        obj_row["minX"] = current_align["minX"]
        obj_row["minY"] = current_align["minY"]
        obj_row["maxX"] = current_align["maxX"]
        obj_row["maxY"] = current_align["maxY"]

        h = height(obj)
        w = width(obj)
        obj_row["height"] = h
        obj_row["width"] = w
        obj_row["ratioWidthHeight"] = safe_divide(w, h)
        obj_row["area"] = multiply(h, w)
        obj_row["pixelCount"] = len(obj)
        obj_row["hasOddPixelCount"] = not even(len(obj))
        obj_row["hasEvenPixelCount"] = even(len(obj))
        obj_row["areaPerimeter"] = 2 * (h + w)
        obj_row["pixelPerimeter"] = compute_pixel_perimeter(obj)
        obj_row["ratioPixelsArea"] = safe_divide(len(obj), obj_row["area"])

        obj_row["isSquare"] = is_square(obj)
        obj_row["isRectangle"] = is_rectangle(obj)
        obj_row["isLine"] = is_straight_line(obj)
        obj_row["isHorizontal"] = (w > h)
        obj_row["isVertical"] = (h > w)
        obj_row["diagonalLength"] = (h ** 2 + w ** 2) ** 0.5

        obj_row["orthoAdjacentZonesCount"] = sum(1 for o in all_zones if adjacent(obj, o))
        obj_row["diagAdjacentZonesCount"] = sum(
            1 for o in all_zones if any(len(toindices(obj) & ineighbors((r, c))) > 0 for r, c in toindices(o))
        )
        obj_row["adjacentZonesCount"] = obj_row["orthoAdjacentZonesCount"] + obj_row["diagAdjacentZonesCount"]

        obj_row["orthoAdjacentBlocksCount"] = sum(1 for o in all_blocks if adjacent(obj, o))
        obj_row["diagAdjacentBlocksCount"] = sum(
            1 for o in all_blocks if any(len(toindices(obj) & ineighbors((r, c))) > 0 for r, c in toindices(o))
        )
        obj_row["adjacentBlocksCount"] = obj_row["orthoAdjacentBlocksCount"] + obj_row["diagAdjacentBlocksCount"]

        # collect orthogonal neighbor colors, excluding None and the object’s own color
        ortho_counter = Counter(
            col
            for r, c in toindices(obj)
            for n in dneighbors((r, c))
            if (col := index(grid, n)) is not None and col != color
        )
        # sort colors by descending frequency
        ortho_sorted = [col for col, _ in ortho_counter.most_common()]
        obj_row["orthoNeighborColorCount"] = len(ortho_sorted)
        obj_row["orthoNeighborColorList"] = ",".join(map(str, ortho_sorted))
        # collect diagonal neighbor colors with counts, excluding None and the object’s own color
        diag_counter = Counter(
            col
            for r, c in toindices(obj)
            for n in ineighbors((r, c))
            if (col := index(grid, n)) is not None and col != color
        )
        diag_sorted = [col for col, _ in diag_counter.most_common()]
        obj_row["diagNeighborColorCount"] = len(diag_sorted)
        obj_row["diagNeighborColorList"] = ",".join(map(str, diag_sorted))
        # combined neighbor colors with summed counts
        combined_counter = ortho_counter + diag_counter
        combined_sorted = [col for col, _ in combined_counter.most_common()]
        obj_row["neighborColorCount"] = len(combined_sorted)
        obj_row["neighborColorList"] = ",".join(map(str, combined_sorted))

        obj_row["diffGridColorObjectColor"] = colorcount(grid, obj_row["color"]) - len(obj)
        obj_row["sameColorBlocksCount"] = sum(1 for o in blocks_in if color_of(o) == obj_row["color"])
        obj_row["sameColorZonesCount"] = sum(1 for o in zones_in if color_of(o) == obj_row["color"])

        obj_row["distanceFromTopBorder"] = uppermost(obj)
        obj_row["distanceFromBottomBorder"] = height(grid) - lowermost(obj) - 1
        obj_row["distanceFromLeftBorder"] = leftmost(obj)
        obj_row["distanceFromRightBorder"] = width(grid) - rightmost(obj) - 1
        obj_row["minRow"] = uppermost(obj)
        obj_row["minCol"] = leftmost(obj)
        obj_row["maxRow"] = lowermost(obj)
        obj_row["maxCol"] = rightmost(obj)

        obj_row["areaCenterX"] = (obj_row["minCol"] + obj_row["maxCol"]) / 2
        obj_row["areaCenterY"] = (obj_row["minRow"] + obj_row["maxRow"]) / 2
        obj_row["massCenterX"], obj_row["massCenterY"] = centerofmass(obj)
        obj_row["isHorizontallyCentered"] = (obj_row["areaCenterX"] == width(grid) / 2)
        obj_row["isVerticallyCentered"] = (obj_row["areaCenterY"] == height(grid) / 2)
        obj_row["isCentered"] = obj_row["isHorizontallyCentered"] and obj_row["isVerticallyCentered"]

        obj_row["isTouchingTop"] = (obj_row["minRow"] == 0)
        obj_row["isTouchingBottom"] = (obj_row["maxRow"] == height(grid) - 1)
        obj_row["isTouchingLeft"] = (obj_row["minCol"] == 0)
        obj_row["isTouchingRight"] = (obj_row["maxCol"] == width(grid) - 1)
        obj_row["isTouchingBorder"] = (
                    obj_row["isTouchingTop"] or obj_row["isTouchingBottom"] or obj_row["isTouchingLeft"] or obj_row[
                "isTouchingRight"])

        obj_row["isTouchingTopRight"] = obj_row["isTouchingTop"] and obj_row["isTouchingRight"]
        obj_row["isTouchingBottomRight"] = obj_row["isTouchingBottom"] and obj_row["isTouchingRight"]
        obj_row["isTouchingTopLeft"] = obj_row["isTouchingTop"] and obj_row["isTouchingLeft"]
        obj_row["isTouchingBottomLeft"] = obj_row["isTouchingBottom"] and obj_row["isTouchingLeft"]
        obj_row["isTouchingCorner"] = (obj_row["isTouchingTopRight"] or obj_row["isTouchingBottomRight"]
                                       or obj_row["isTouchingTopLeft"] or obj_row["isTouchingBottomLeft"])

        # --- Hole count computations ---
        minRow = obj_row["minRow"]
        minCol = obj_row["minCol"]
        subgrid_obj = crop(grid, (minRow, minCol), (h, w))
        local_obj_indices = frozenset((i - minRow, j - minCol) for (i, j) in toindices(obj))
        binary_inverted = tuple(
            tuple(0 if (i, j) in local_obj_indices else 1 for j in range(w))
            for i in range(h)
        )
        block_components = objects(binary_inverted, True, False, True)
        zone_components = objects(binary_inverted, True, True, True)
        obj_row["blockHoleCountWithBorder"] = len(block_components)
        obj_row["blockHoleCountWithoutBorder"] = sum(1 for comp in block_components if not touches_border(comp, h, w))
        obj_row["zoneHoleCountWithBorder"] = len(zone_components)
        obj_row["zoneHoleCountWithoutBorder"] = sum(1 for comp in zone_components if not touches_border(comp, h, w))
        filler = -1
        hole_grid = tuple(
            tuple(filler if (i, j) in local_obj_indices else subgrid_obj[i][j] for j in range(w))
            for i in range(h)
        )
        block_color_components = objects(hole_grid, True, False, True)
        zone_color_components = objects(hole_grid, True, True, True)
        obj_row["blockCountInsideHolesWithBorder"] = len(block_color_components)
        obj_row["zoneCountInsideHolesWithBorder"] = len(zone_color_components)
        uniform_hole_grid = tuple(
            tuple(1 if cell != filler else 0 for cell in row_data)
            for row_data in hole_grid
        )
        uniform_components = objects(uniform_hole_grid, True, False, True)
        obj_row["blockCountInsideHolesWithoutBorder"] = sum(
            1 for comp in uniform_components if not touches_border(comp, h, w))
        obj_row["zoneCountInsideHolesWithoutBorder"] = sum(
            1 for comp in uniform_components if not touches_border(comp, h, w))

        # --- Alignment data for zones and blocks ---
        zone_align_data = [build_align_data(o) for o in zones_in]
        zone_align_data = [a for a in zone_align_data if a != current_align]
        block_align_data = [build_align_data(o) for o in blocks_in]
        block_align_data = [a for a in block_align_data if a != current_align]
        obj_row["countExactlyAlignZonesHorizontally"] = count_exactly_align_horizontally(current_align, zone_align_data)
        obj_row["countExactlyAlignZonesVertically"] = count_exactly_align_vertically(current_align, zone_align_data)
        obj_row["countExactlyAlignBlocksHorizontally"] = count_exactly_align_horizontally(current_align,
                                                                                          block_align_data)
        obj_row["countExactlyAlignBlocksVertically"] = count_exactly_align_vertically(current_align, block_align_data)
        obj_row["countZonesAtTopLeft"] = count_at_top_left(current_align, zone_align_data)
        obj_row["countZonesAtTop"] = count_at_top(current_align, zone_align_data)
        obj_row["countZonesAtTopRight"] = count_at_top_right(current_align, zone_align_data)
        obj_row["countZonesAtLeft"] = count_at_left(current_align, zone_align_data)
        obj_row["countZonesAtRight"] = count_at_right(current_align, zone_align_data)
        obj_row["countZonesAtBottomLeft"] = count_at_bottom_left(current_align, zone_align_data)
        obj_row["countZonesAtBottom"] = count_at_bottom(current_align, zone_align_data)
        obj_row["countZonesAtBottomRight"] = count_at_bottom_right(current_align, zone_align_data)
        obj_row["countBlocksAtTopLeft"] = count_at_top_left(current_align, block_align_data)
        obj_row["countBlocksAtTop"] = count_at_top(current_align, block_align_data)
        obj_row["countBlocksAtTopRight"] = count_at_top_right(current_align, block_align_data)
        obj_row["countBlocksAtLeft"] = count_at_left(current_align, block_align_data)
        obj_row["countBlocksAtRight"] = count_at_right(current_align, block_align_data)
        obj_row["countBlocksAtBottomLeft"] = count_at_bottom_left(current_align, block_align_data)
        obj_row["countBlocksAtBottom"] = count_at_bottom(current_align, block_align_data)
        obj_row["countBlocksAtBottomRight"] = count_at_bottom_right(current_align, block_align_data)
        obj_row["isObjectRepeated"] = (len(occurrences(grid, obj)) > 1)
        obj_row["hasHorizontalSymmetry"] = (hmirror(obj) == obj)
        obj_row["hasVerticalSymmetry"] = (vmirror(obj) == obj)
        obj_row["hasDiagonalSymmetry"] = (dmirror(obj) == obj)
        obj_row["hasCounterDiagonalSymmetry"] = (cmirror(obj) == obj)
        obj_row["hasRotationalSymmetry"] = (rot180(subgrid(obj, grid)) == subgrid(obj, grid))
        obj_row["isEncapsulatedByBlockAndAloneWithBorder"] = (obj_row["adjacentZonesCount"] == 1)
        obj_row["isEncapsulatedByBlockAndAloneWithoutBorder"] = (
                    obj_row["adjacentZonesCount"] == 1 and not obj_row["isTouchingBorder"])
        obj_row["isEncapsulatedByZoneAndAloneWithBorder"] = (obj_row["orthoAdjacentZonesCount"] == 1)
        obj_row["isEncapsulatedByZoneAndAloneWithoutBorder"] = (
                    obj_row["orthoAdjacentZonesCount"] == 1 and not obj_row["isTouchingBorder"])
        obj_row["isPath"] = is_object_path(obj)
        obj_row["isTree"] = is_object_tree(obj)
        obj_row["data"] = shapeData

        # --- Build the shape_occurrence row (occ_row) ---
        occ_row = {}
        occ_row["shape_id"] = stored_shape_id
        occ_row["shape_transformation_id"] = transformation_id
        occ_row["isInsideInput"] = isInsideInput
        occ_row["isInsideOutput"] = not isInsideInput
        occ_row["isInsideTrain"] = (trainId != -1)
        occ_row["isInsideTest"] = (testId != -1)
        occ_row["trainId"] = trainId
        occ_row["testId"] = testId
        occ_row["minX"] = current_align["minX"]
        occ_row["minY"] = current_align["minY"]
        # The occ_row will later be augmented with the foreign key "object_id".
        results.append((obj_row, occ_row))

    obj_rows = [obj_row for obj_row, occ_row in results]
    sorted_by_size = sorted(obj_rows, key=lambda r: r["pixelCount"], reverse=True)
    for rank, row in enumerate(sorted_by_size, start=1):
        row["sizeOrder"] = rank
    sorted_by_size_asc = sorted(obj_rows, key=lambda r: r["pixelCount"])
    for rank, row in enumerate(sorted_by_size_asc, start=1):
        row["sizeOrderDesc"] = rank

    return results

def compute_move_behind_color(input_grid, output_grid, pixels, obj_color, neighbor_colors=None):
    """
    Compute the color left behind when an object moves.

    Returns -1 whenever the output no longer covers the original pixels
    or whenever nothing else can be found.
    """
    if not pixels:
        print("→ No pixels, returning -1")
        return -1

    H = len(output_grid)
    W = len(output_grid[0]) if H else 0

    # 1) Out-of-bounds check
    for r, c in pixels:
        if r < 0 or r >= H or c < 0 or c >= W:
            print(f"→ Pixel {(r,c)} outside output grid, returning -1")
            return -1

    # 2) Gather what’s in those spots now
    behind_colors = [output_grid[r][c] for r, c in pixels]
    print("  behind_colors:", behind_colors)

    # 3) Remove any that still equal the object’s color
    filtered = [col for col in behind_colors if col != obj_color]
    if not filtered:
        print("→ All spots are still obj_color, returning -1")
        return -1

    # 4) Uniform-color?
    first = filtered[0]
    if all(col == first for col in filtered):
        print(f"→ Uniform behind-color = {first}")
        return first

    # 5) Fallback to neighbor_colors if you passed them
    if neighbor_colors:
        print(f"→ Non-uniform but neighbor_colors provided, returning {neighbor_colors[0]}")
        return neighbor_colors[0]

    # 6) Give up → None
    print("→ Non-uniform and no neighbor_colors, returning None")
    return None

def bulk_insert(conn, table, rows):
    """
    Performs a bulk insertion of a list of dictionaries (rows) into the specified table.
    """
    if not rows:
        return
    cursor = conn.cursor()
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    data = [tuple(row[col] for col in columns) for row in rows]
    cursor.executemany(sql, data)


def process_objects_from_json(filename, data, conn, clear_table=True):

    if clear_table:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM object_analysis;")
        cursor.execute("DELETE FROM shape;")
        cursor.execute("DELETE FROM shape_occurrence;")
        cursor.execute("DELETE FROM shape_transformation;")
        conn.commit()

    # Global data to manage shapes and transformations.
    global_data = {
        "shapes_map": {},  # Maps shape data (json string) to id.
        "next_shape_id": 1,
        "shape_records": [],  # List of shape records to insert.
        "trans_map": {},  # Maps transformation key tuple to id.
        "next_trans_id": 1,
        "trans_records": []  # List of shape_transformation records to insert.
    }
    all_obj_rows = []  # For object_analysis rows.
    all_occ_rows = []  # For shape_occurrence rows.
    next_object_id = 1  # We assign object_analysis ids programmatically.

    input_grids = {}
    output_grids = {}
    object_pixels = {}

    def process_items(items, is_input, isTrain):
        nonlocal next_object_id
        for idx, item in enumerate(items):
            if is_input:
                grid = item.get("input")
                if isTrain:
                    input_grids[idx] = grid
            else:
                grid = item.get("output")
                if isTrain:
                    output_grids[idx] = grid
                if grid is None:
                    print(f"⚠️ Skipping test[{idx}] output: no 'output' field.")
                    continue  # skip this item if no output

            # Determine train or test index
            train_id = idx if isTrain else -1
            test_id = idx if isTrain is False else -1

            rows = compute_object_analysis(filename, train_id, test_id, grid, is_input, global_data, conn)
            for obj_row, occ_row in rows:
                obj_row["id"] = next_object_id
                occ_row["object_id"] = next_object_id
                pixel_list = json.loads(obj_row["data"])
                coords = [tuple(coord) for coord in pixel_list]
                object_pixels[next_object_id] = coords
                next_object_id += 1
                all_obj_rows.append(obj_row)
                all_occ_rows.append(occ_row)

    # Process train and test items, both for input and output.
    process_items(data.get("train", []), True, True)
    process_items(data.get("train", []), False, True)
    process_items(data.get("test", []), True, False)
    # process_items(data.get("test", []), False, False)

    # Bulk insert in the order: shape, shape_transformation, object_analysis, shape_occurrence.
    bulk_insert(conn, "shape", global_data["shape_records"])
    bulk_insert(conn, "shape_transformation", global_data["trans_records"])
    bulk_insert(conn, "object_analysis", all_obj_rows)
    bulk_insert(conn, "shape_occurrence", all_occ_rows)

    # now populate the relational flags & fields uniqueness in input vs output
    cur = conn.cursor()
    cur.executescript("""
    -- 1) isObjectUnique
    UPDATE object_analysis AS oa
    SET isObjectUnique = CASE
      WHEN oa.testId = -1 AND oa.isInsideInput = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM object_analysis i
         WHERE i.trainId = oa.trainId
           AND i.testId = -1
           AND i.isInsideInput = 1
           AND i.data = oa.data
           AND i.color = oa.color)
      ELSE NULL END;

    -- 2) isTargetObjectPresent
    UPDATE object_analysis AS oa
    SET isTargetObjectPresent = CASE
      WHEN oa.testId = -1 THEN
        (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END
         FROM object_analysis o
         WHERE o.trainId = oa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = oa.data)
      ELSE NULL END;

    -- 3) isTargetObjectUnique
    UPDATE object_analysis AS oa
    SET isTargetObjectUnique = CASE
      WHEN oa.testId = -1 AND oa.isTargetObjectPresent = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM object_analysis o
         WHERE o.trainId = oa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = oa.data
           AND o.color = oa.color)
      ELSE NULL END;

    -- 4) isShapeUnique
    UPDATE object_analysis AS oa
    SET isShapeUnique = CASE
      WHEN oa.testId = -1 AND oa.isInsideInput = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM object_analysis i
         WHERE i.trainId = oa.trainId
           AND i.testId = -1
           AND i.isInsideInput = 1
           AND i.data = oa.data)
      ELSE NULL END;
    
    -- 4b) isColorUnique: among input‐objects in the same train, does this color occur exactly once?
    UPDATE object_analysis AS oa
    SET isColorUnique = CASE
      WHEN oa.testId = -1 AND oa.isInsideInput = 1 THEN
        (
          SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
          FROM object_analysis AS i
          WHERE i.trainId = oa.trainId
            AND i.testId = -1
            AND i.isInsideInput = 1
            AND i.color = oa.color
        )
      ELSE NULL
    END;
    
    -- 5) isTargetShapePresent
    UPDATE object_analysis AS oa
    SET isTargetShapePresent = CASE
      WHEN oa.testId = -1 THEN
        (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END
         FROM object_analysis o
         WHERE o.trainId = oa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = oa.data)
      ELSE NULL END;

    -- 6) isTargetShapeUnique
    UPDATE object_analysis AS oa
    SET isTargetShapeUnique = CASE
      WHEN oa.testId = -1 AND oa.isTargetShapePresent = 1 THEN
        (SELECT CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END
         FROM object_analysis o
         WHERE o.trainId = oa.trainId
           AND o.testId = -1
           AND o.isInsideOutput = 1
           AND o.data = oa.data)
      ELSE NULL END;

    -- 7–10) isObjectOneToOne / OneToMany / ManyToOne / ManyToMany
    UPDATE object_analysis
    SET
      isObjectOneToOne   = CASE WHEN isObjectUnique=1 AND isTargetObjectUnique=1 THEN 1 ELSE 0 END,
      isObjectOneToMany  = CASE WHEN isObjectUnique=1 AND isTargetObjectUnique=0 AND isTargetObjectPresent=1 THEN 1 ELSE 0 END,
      isObjectManyToOne  = CASE WHEN isObjectUnique=0 AND isTargetObjectUnique=1 THEN 1 ELSE 0 END,
      isObjectManyToMany = CASE WHEN isObjectUnique=0 AND isTargetObjectUnique=0 AND isTargetObjectPresent=1 THEN 1 ELSE 0 END;

    -- 11–14) isShapeOneToOne / OneToMany / ManyToOne / ManyToMany
    UPDATE object_analysis
    SET
      isShapeOneToOne    = CASE WHEN isShapeUnique=1 AND isTargetShapeUnique=1 THEN 1 ELSE 0 END,
      isShapeOneToMany   = CASE WHEN isShapeUnique=1 AND isTargetShapeUnique=0 AND isTargetShapePresent=1 THEN 1 ELSE 0 END,
      isShapeManyToOne   = CASE WHEN isShapeUnique=0 AND isTargetShapeUnique=1 THEN 1 ELSE 0 END,
      isShapeManyToMany  = CASE WHEN isShapeUnique=0 AND isTargetShapeUnique=0 AND isTargetShapePresent=1 THEN 1 ELSE 0 END;

    -- 15) target_object_id
    UPDATE object_analysis AS oa
    SET target_object_id = (
      SELECT o.id
      FROM object_analysis o
      WHERE o.trainId = oa.trainId
        AND o.testId = -1
        AND o.isInsideOutput = 1
        AND o.data = oa.data
        AND o.color = oa.color
      LIMIT 1
    )
    WHERE oa.testId = -1
      AND oa.isInsideInput = 1
      AND oa.isObjectOneToOne = 1;

    -- 16) isObjectDeleted
    UPDATE object_analysis
    SET isObjectDeleted = CASE WHEN isTargetObjectPresent=0 THEN 1 ELSE 0 END;

    -- 17) isShapeDeleted
    UPDATE object_analysis
    SET isShapeDeleted  = CASE WHEN isTargetShapePresent=0 THEN 1 ELSE 0 END;

    -- 18) isMoved
    UPDATE object_analysis AS oa
    SET isMoved = CASE
      WHEN (oa.isObjectOneToOne=1 OR oa.isShapeOneToOne=1) AND EXISTS (
            SELECT 1 FROM object_analysis t
            WHERE t.id = oa.target_object_id
              AND (t.minX != oa.minX OR t.minY != oa.minY)
          ) THEN 1
      ELSE 0 END;

    -- 19) isRotatedOrFlipped
    UPDATE object_analysis AS oa
    SET isRotatedOrFlipped = CASE
      WHEN EXISTS (
        SELECT 1
        FROM shape_occurrence so
        JOIN shape_transformation st ON so.shape_transformation_id = st.id
        WHERE so.object_id = oa.id
          AND (st.rotated_90=1 OR st.rotated_180=1 OR st.rotated_270=1
               OR st.flipped_vert=1 OR st.flipped_horiz=1
               OR st.flipped_vert_90=1 OR st.flipped_horiz_90=1)
      ) THEN 1
      ELSE 0 END;

    -- 20) isRecolored
    UPDATE object_analysis AS oa
    SET isRecolored = CASE
      WHEN EXISTS (
        SELECT 1
        FROM shape_occurrence so
        JOIN shape_transformation st ON so.shape_transformation_id = st.id
        WHERE so.object_id = oa.id
          AND st.color != oa.color
      ) THEN 1
      ELSE 0 END;

    -- 21) isZoomed
    UPDATE object_analysis AS oa
    SET isZoomed = CASE
      WHEN EXISTS (
        SELECT 1
        FROM shape_occurrence so
        JOIN shape_transformation st ON so.shape_transformation_id = st.id
        WHERE so.object_id = oa.id
          AND (st.zoom_x > 1 OR st.zoom_y > 1)
      ) THEN 1
      ELSE 0 END;

    -- 22) isGlued
    UPDATE object_analysis
    SET isGlued = CASE
      WHEN isObjectDeleted=1 AND isShapeDeleted=1 THEN 1 ELSE 0 END;

    -- 23) moveRelX
    UPDATE object_analysis AS oa
    SET moveRelX = (
      SELECT t.minX - oa.minX
      FROM object_analysis t
      WHERE t.id = oa.target_object_id
    )
    WHERE oa.target_object_id IS NOT NULL;

    -- 24) moveRelY
    UPDATE object_analysis AS oa
    SET moveRelY = (
      SELECT t.minY - oa.minY
      FROM object_analysis t
      WHERE t.id = oa.target_object_id
    )
    WHERE oa.target_object_id IS NOT NULL;
    
    -- 23b) newPosX
    UPDATE object_analysis AS oa
    SET newPosX = (
      SELECT t.minX
      FROM object_analysis t
      WHERE t.id = oa.target_object_id
    )
    WHERE oa.target_object_id IS NOT NULL;

    -- 24b) newPosY
    UPDATE object_analysis AS oa
    SET newPosY = (
      SELECT t.minY
      FROM object_analysis t
      WHERE t.id = oa.target_object_id
    )
    WHERE oa.target_object_id IS NOT NULL;

    -- 25) moveBehindColor  (placeholder: leave NULL or implement in Python/SQL as needed)
    UPDATE object_analysis
    SET moveBehindColor = NULL;

    -- 26) rotateOrFlip  (concatenate transformation names)
    -- Done below

    -- 27) recolored  (store the new color)
    UPDATE object_analysis AS oa
    SET recolored = (
      SELECT CAST(st.color AS TEXT)
      FROM shape_occurrence so
      JOIN shape_transformation st ON so.shape_transformation_id = st.id
      WHERE so.object_id = oa.id
        AND st.color != oa.color
      LIMIT 1
    );

    -- 28) zoomX
    UPDATE object_analysis AS oa
    SET zoomX = (
      SELECT st.zoom_x
      FROM shape_occurrence so
      JOIN shape_transformation st ON so.shape_transformation_id = st.id
      WHERE so.object_id = oa.id
        AND st.zoom_x > 1
      LIMIT 1
    );

    -- 29) zoomY
    UPDATE object_analysis AS oa
    SET zoomY = (
      SELECT st.zoom_y
      FROM shape_occurrence so
      JOIN shape_transformation st ON so.shape_transformation_id = st.id
      WHERE so.object_id = oa.id
        AND st.zoom_y > 1
      LIMIT 1
    );
    """)
    cur.execute("""
    UPDATE object_analysis
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
      FROM shape_occurrence so
      JOIN shape_transformation st
        ON so.shape_transformation_id = st.id
      WHERE so.object_id = object_analysis.id
      LIMIT 1
    );
    """)

    moved_rows = cur.execute("""
        SELECT oa.id, oa.trainId, oa.color, oa.neighborColorList
        FROM object_analysis AS oa
        WHERE testId=-1 AND ((oa.moveRelX IS NOT NULL AND oa.moveRelX != 0)
           OR (oa.moveRelY IS NOT NULL AND oa.moveRelY != 0))
    """).fetchall()

    for obj_id, trainId, obj_color, neighborColorList in moved_rows:
        ig = input_grids[trainId]
        og = output_grids[trainId]
        pixels = object_pixels[obj_id]
        neighbor_colors = [int(c) for c in (neighborColorList or "").split(",") if c]
        # Compute the background color left behind, with fallback to neighbor_colors[0]
        behind = compute_move_behind_color(
            ig, og, pixels,
            obj_color,
            neighbor_colors
        )
        cur.execute(
            "UPDATE object_analysis SET moveBehindColor = ? WHERE id = ?",
            (behind, obj_id)
        )

    # 4) finally, commit all of it in one go
    conn.commit()

def detect_and_persist_conditional_shapes(conn):
    cur = conn.cursor()
    #print("\n=== detect_and_persist_conditional_shapes_verbose ===")
    #print("Clearing existing rows in 'shape_conditional'...")
    cur.execute("DELETE FROM shape_conditional")

    # 1) Load analysis tables via helper
    #print("Loading first_sight_analysis into memory...")
    fsa_raw = load_table_from_sqlite(conn, "first_sight_analysis", "id")
    fsa_table = {int(k): v for k, v in fsa_raw.items()}
    #print(f"  → Loaded {len(fsa_table)} rows from first_sight_analysis")

    #print("Loading sprite_analysis into memory...")
    sa_raw = load_table_from_sqlite(conn, "sprite_analysis", "id")
    sa_table = {int(k): v for k, v in sa_raw.items()}
    sa_cols = list(next(iter(sa_table.values())).keys())
    #print(f"  → Loaded {len(sa_table)} rows from sprite_analysis")

    # Prepare for minimal-criteria calls
    all_fsa_ids = [rid for rid, row in fsa_table.items() if row.get('testId') == -1]
    all_sa_ids = [rid for rid, row in sa_table.items() if row.get('isInsideInput') == 1 and row.get('isGrid') == 1 and row.get('testId') == -1]
    tables = {
        'first_sight_analysis': fsa_table,
        'sprite_analysis': sa_table
    }
    #print(f"All FSA IDs (testId=-1): {all_fsa_ids}")
    #print(f"All SA input-grid IDs: {all_sa_ids}\n")

    # 2) Collect training IDs
    cur.execute("""
      SELECT DISTINCT trainId
        FROM shape_occurrence
       WHERE isInsideTrain=1 AND testId=-1
    """)
    train_ids = [r[0] for r in cur.fetchall()]
    total_trains = len(train_ids)
    #print(f"Train IDs: {train_ids} (total={total_trains})\n")

    # 3) Map each transformation to trains in which it's in output
    cur.execute("""
      SELECT shape_transformation_id, trainId
        FROM shape_occurrence
       WHERE isInsideOutput=1 AND isInsideTrain=1 AND testId=-1
    """)
    trains_per_trans = defaultdict(set)
    for trans_id, tid in cur.fetchall():
        trains_per_trans[trans_id].add(tid)
    #print(f"Transformation → train-occurrence map: {dict(trains_per_trans)}\n")

    # 4) Helper to find sprite_analysis IDs per train & flag
    def find_sa_id(tid):
        cur.execute(f"""
          SELECT id
            FROM sprite_analysis
           WHERE isGrid = 1
             AND trainId              = {tid}
             AND isInsideInput        = 1
             AND testId               = -1
           LIMIT 1
        """)
        r = cur.fetchone()
        sid = r[0] if r else None
        #print(f"    find_sa_id(train={tid}) -> {sid}")
        return sid

    skip_cols = {'id','filename','trainId','testId','minX','minY','maxX','maxY'}

    # 5) Iterate over each transformation candidate
    for trans_id, seen_trains in trains_per_trans.items():
        #print(f"\nProcessing transformation {trans_id}, seen in trains={seen_trains}")
        if not (1 < len(seen_trains) < total_trains):
            #print("  → Not conditional (doesn't meet >1 and <total trains), skipping.")
            continue

        # Get shape_id & color for insertion
        cur.execute("SELECT shape_id, color FROM shape_transformation WHERE id=?", (trans_id,))
        shape_id, color = cur.fetchone()
        #print(f"  shape_id={shape_id}, color={color}")

        # --- Compute criteria_first_sight via minimal selection ---
        all_fsa_ids = [
            fsa_id
            for fsa_id, row in tables['first_sight_analysis'].items()
            if row.get("testId") == -1
        ]

        # 2) for each train in seen_trains, pick its one FSA ID (or None)
        group_fsa: List[int | None] = []
        for tid in seen_trains:
            fsa_id = next(
                (fid for fid, row in tables['first_sight_analysis'].items()
                 if row.get("trainId") == tid and row.get("testId") == -1),
                None
            )
            group_fsa.append(fsa_id)
            #print(f"Train {tid} → first_sight_analysis ID {fsa_id}")

        #crit_fsa = find_minimal_selection_criteria_for_table_strict(
        crit_fsa = find_minimal_selection_criteria_for_table(
            group=tuple(group_fsa),
            all_ids=all_fsa_ids,
            tables=tables,
            table_key='first_sight_analysis'
        ) or []
        #print(f"  → criteria_first_sight: {crit_fsa}\n")

        # --- Compute criteria_sprite_grid via minimal selection ---
        group_sa = []
        for tid in seen_trains:
            sid = find_sa_id(tid)
            group_sa.append(sid)
        #print(f"    SA group for minimal selection: {group_sa}")
        #crit_sprite = find_minimal_selection_criteria_for_table_strict(
        crit_sprite = find_minimal_selection_criteria_for_table(
            group=tuple(group_sa),
            all_ids=all_sa_ids,
            tables=tables,
            table_key='sprite_analysis'
        ) or []
        #print(f"  → criteria_sprite_grid: {crit_sprite}\n")

        # --- Compute else_transformation_id if applicable ---
        other_trains = set(train_ids) - seen_trains
        else_trans = None
        if other_trains:
            placeholders = ",".join("?" for _ in other_trains)
            cur.execute(f"""
              SELECT DISTINCT shape_transformation_id
                FROM shape_occurrence
               WHERE isInsideOutput=1 AND isInsideTrain=1
                 AND trainId IN ({placeholders})
            """, tuple(other_trains))
            alts = {r[0] for r in cur.fetchall()}
            #print(f"  Other transformations in other trains: {alts}")
            if len(alts) == 1:
                else_trans = alts.pop()
                #print(f"    → else_transformation_id={else_trans}")

        # --- Insert record into shape_conditional ---
        #print(f"Inserting record for transformation {trans_id} into shape_conditional...\n")
        cur.execute("""
          INSERT INTO shape_conditional
            (shape_transformation_id, shape_id, color,
             criteria_first_sight, criteria_sprite_grid,
             else_transformation_id)
          VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trans_id,
            shape_id,
            color,
            json.dumps(crit_fsa),
            json.dumps(crit_sprite),
            else_trans
        ))

    conn.commit()
    #print("=== Completed detect_and_persist_conditional_shapes_verbose ===\n")


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

    process_objects_from_json(filename, data, conn)
    detect_and_persist_conditional_shapes(conn)
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
