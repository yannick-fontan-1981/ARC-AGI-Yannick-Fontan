# object_analysis.py
import argparse
import os
import sqlite3
import json
import sys

from sympy import false
from solver.dsl import *
import time
from collections import OrderedDict


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

        if pixel_count == 1 or is_same_exactly_same or is_first_occurrence:
            rotated_90 = rotated_180 = rotated_270 = False
            flipped_vert = flipped_horiz = flipped_vert_90 = flipped_horiz_90 = False
        else:
            rotated_90 = (sorted(stored_version) == sorted(rot90Shape(base_shape)))
            rotated_180 = (sorted(stored_version) == sorted(rot180Shape(base_shape)))
            rotated_270 = (sorted(stored_version) == sorted(rot270Shape(base_shape)))
            flipped_vert = (sorted(stored_version) == sorted(vmirrorShape(base_shape)))
            flipped_horiz = (sorted(stored_version) == sorted(hmirrorShape(base_shape)))
            flipped_vert_90 = (sorted(stored_version) == sorted(vmirrorShape(rot90Shape(base_shape))))
            flipped_horiz_90 = (sorted(stored_version) == sorted(hmirrorShape(rot90Shape(base_shape))))

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

        ortho_neighbors = {index(grid, n) for r, c in toindices(obj)
                           for n in dneighbors((r, c))
                           if index(grid, n) is not None}
        obj_row["orthoNeighborColorCount"] = len(ortho_neighbors)
        obj_row["orthoNeighborColorList"] = ",".join(map(str, sorted(ortho_neighbors)))

        diag_neighbors = {index(grid, n) for r, c in toindices(obj)
                          for n in ineighbors((r, c))
                          if index(grid, n) is not None}
        obj_row["diagNeighborColorCount"] = len(diag_neighbors)
        obj_row["diagNeighborColorList"] = ",".join(map(str, sorted(diag_neighbors)))

        all_neighbors = ortho_neighbors | diag_neighbors
        obj_row["neighborColorCount"] = len(all_neighbors)
        obj_row["neighborColorList"] = ",".join(map(str, sorted(all_neighbors)))

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

    obj_rows = [obj_row for obj_row, _ in results]
    sorted_by_size = sorted(obj_rows, key=lambda r: r["pixelCount"], reverse=True)
    for rank, row in enumerate(sorted_by_size, start=1):
        row["sizeOrder"] = rank

    return results


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

    def process_items(items, is_input, isTrain):
        nonlocal next_object_id
        for idx, item in enumerate(items):
            if is_input:
                grid = item.get("input")
            else:
                grid = item.get("output")
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
    conn.commit()


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
