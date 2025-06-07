# pattern-finder/output_diff_analysis.py

import argparse
import os
import sqlite3

from constelize.dsl.grid_dsl import grid_to_pretty_string, to_concrete_grid
from solver.dsl import *
from collections import OrderedDict

def _make_diff_grid(input_grid, output_grid):
    """
    Return a new grid (same dimensions) where:
      - cell = -1 if input_grid[y][x] == output_grid[y][x]
      - otherwise cell = output_grid[y][x]
    """
    H = len(input_grid)
    W = len(input_grid[0])
    if H != len(output_grid) or any(len(input_grid[y]) != len(output_grid[y]) for y in range(H)):
        return None #raise ValueError("Input and output must have identical shape")
    diff = [[None] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if input_grid[y][x] == output_grid[y][x]:
                diff[y][x] = -1
            else:
                diff[y][x] = output_grid[y][x]
    #print("_make_diff_grid")
    #print(grid_to_pretty_string(to_concrete_grid(diff)))
    return diff


def _make_all_neg1_grid(shape):
    """
    Given a shape tuple (H, W), return a grid of size H×W filled with -1.
    """
    H, W = shape
    return [[-1] * W for _ in range(H)]



def compute_object_analysis(filename: str, trainId: int, grid):
    grid = convert_to_tuple_of_tuples(grid)  # Ensure consistency

    results = []  # List of (obj_row) tuples.
    blocks_in = blocks(grid)
    zones_in = zones(grid)

    # Ensure each object appears only once (zones first).
    all_zones = list(zones_in)
    all_blocks = list(blocks_in)
    all_objects = list(OrderedDict.fromkeys(all_zones + [b for b in all_blocks if b not in set(all_zones)]))

    for obj in all_objects:
        color = color_of(obj)
        if color == -1:
            continue
        # --- Compute shape information ---
        base_shape = extract_shape(obj)  # the shape (as a set or list of pixel positions)



        # --- Build alignment and positional data ---
        current_align = build_align_data(obj)

        # --- Build the object_analysis row (obj_row) ---
        # Note: The object_analysis table does not include shape_id fields.
        obj_row = {}
        obj_row["filename"] = filename
        obj_row["trainId"] = trainId
        obj_row["isBlock"] = (obj in blocks_in)
        obj_row["isZone"] = (obj in zones_in)
        obj_row["color"] = color
        obj_row["isBlack"] = (color == 0)
        obj_row["isBlue"] = (color == 1)
        obj_row["isRed"] = (color == 2)
        obj_row["isGreen"] = (color == 3)
        obj_row["isYellow"] = (color == 4)
        obj_row["isGrey"] = (color == 5)
        obj_row["isFuchsia"] = (color == 6)
        obj_row["isOrange"] = (color == 7)
        obj_row["isTeal"] = (color == 8)
        obj_row["isBrown"] = (color == 9)

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
        obj_row["isTouchingBorder"] = (obj_row["isTouchingTop"] or obj_row["isTouchingBottom"] or obj_row["isTouchingLeft"] or obj_row["isTouchingRight"])

        obj_row["isTouchingTopRight"] = obj_row["isTouchingTop"] and obj_row["isTouchingRight"]
        obj_row["isTouchingBottomRight"] = obj_row["isTouchingBottom"] and obj_row["isTouchingRight"]
        obj_row["isTouchingTopLeft"] = obj_row["isTouchingTop"] and obj_row["isTouchingLeft"]
        obj_row["isTouchingBottomLeft"] = obj_row["isTouchingBottom"] and obj_row["isTouchingLeft"]
        obj_row["isTouchingCorner"] = (obj_row["isTouchingTopRight"] or obj_row["isTouchingBottomRight"]
                                       or obj_row["isTouchingTopLeft"] or obj_row["isTouchingBottomLeft"])

        obj_row["isObjectRepeated"] = (len(occurrences(grid, obj)) > 1)

        obj_row["isPath"] = is_object_path(obj)
        obj_row["isTree"] = is_object_tree(obj)
        obj_row["data"] = json.dumps(sorted(base_shape))

        results.append(obj_row)

    obj_rows = [obj_row for obj_row in results]
    sorted_by_size = sorted(obj_rows, key=lambda r: r["pixelCount"], reverse=True)
    for rank, row in enumerate(sorted_by_size, start=1):
        row["sizeOrder"] = rank
    sorted_by_size_asc = sorted(obj_rows, key=lambda r: r["pixelCount"])
    for rank, row in enumerate(sorted_by_size_asc, start=1):
        row["sizeOrderDesc"] = rank

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

def process_output_diff_from_json(filename, data, conn, clear_table=True):
    if clear_table:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM output_diff_object_analysis;")
        conn.commit()

    all_obj_rows = []  # For object_analysis rows.
    next_object_id = 1  # We assign object_analysis ids programmatically.

    def process_items(items):
        nonlocal next_object_id
        for idx, item in enumerate(items):
            grid_input = item.get("input")
            grid_output = item.get("output")
            grid_diff = _make_diff_grid(grid_input, grid_output)

            if grid_diff is None:
                return

            # Determine train or test index
            train_id = idx

            rows = compute_object_analysis(filename, train_id, grid_diff)
            for obj_row in rows:
                obj_row["id"] = next_object_id
                next_object_id += 1
                all_obj_rows.append(obj_row)

    process_items(data.get("train", []))
    bulk_insert(conn, "output_diff_object_analysis", all_obj_rows)
    conn.commit()

###############################################
# Main function
###############################################
def main(json_source, *, inline=False, name=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.abspath(os.path.join(script_dir, "..", "db", "database.db"))
    conn = sqlite3.connect(db_path)

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

    process_output_diff_from_json(filename, data, conn)
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

