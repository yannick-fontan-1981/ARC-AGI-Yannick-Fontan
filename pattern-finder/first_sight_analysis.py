import os
import sqlite3
import json
from solver.dsl import *
import time

def compute_first_sight_row(filename: str, trainId: int, grid_in, grid_out):
    """
    Compute columns for one (input, output) pair, reusing the DSL
    for geometry, color, and object operations.
    Returns a dict ready to be inserted into 'first_sight_analysis'.
    """

    grid_in = convert_to_tuple_of_tuples(grid_in)
    grid_out = convert_to_tuple_of_tuples(grid_out)

    row = {}
    row["filename"] = filename
    row["trainId"] = trainId

    # --- Dimensions
    h_in = height(grid_in)
    w_in = width(grid_in)
    h_out = height(grid_out)
    w_out = width(grid_out)

    row["widthInput"] = w_in
    row["widthOutput"] = w_out
    # ratioWidthInputOutput is integer division or 0 if w_out=0
    row["ratioWidthInputOutput"] = safe_divide(w_in, w_out)
    row["diffWidthInputOutput"] = diff(w_in, w_out)

    row["heightInput"] = h_in
    row["heightOutput"] = h_out
    row["ratioHeightInputOutput"] = safe_divide(h_in, h_out)
    row["diffHeightInputOutput"] = diff(h_in, h_out)

    # diffWidthHeightInput = widthInput - heightInput
    row["diffWidthHeightInput"] = diff(w_in, h_in)
    row["diffWidthHeightOutput"] = diff(w_out, h_out)

    # ratioWidthHeightInput = w_in // h_in (if h_in != 0)
    row["ratioWidthHeightInput"] = safe_divide(w_in, h_in)
    row["ratioWidthHeightOutput"] = safe_divide(w_out, h_out)

    # --- Area
    area_in = multiply(h_in, w_in)  # DSL multiply
    area_out = multiply(h_out, w_out)
    row["areaInput"] = area_in
    row["areaOutput"] = area_out
    row["ratioAreaInputOutput"] = safe_divide(area_in, area_out)
    row["diffAreaInputOutput"] = diff(area_in, area_out)

    # --- Blocks and Zones (both are defined in DSL as well)
    blocks_in = blocks(grid_in)   # objects(grid_in, True, False, False)
    blocks_out = blocks(grid_out)
    count_blocks_in = len(blocks_in)
    count_blocks_out = len(blocks_out)
    row["countBlocksInput"] = count_blocks_in
    row["countBlocksOutput"] = count_blocks_out
    row["ratioBlocksInputOutput"] = safe_divide(count_blocks_in, count_blocks_out)
    row["diffBlocksInputOutput"] = diff(count_blocks_in, count_blocks_out)

    zones_in = zones(grid_in)  # objects(grid_in, True, True, False)
    zones_out = zones(grid_out)
    count_zones_in = len(zones_in)
    count_zones_out = len(zones_out)
    row["countZonesInput"] = count_zones_in
    row["countZonesOutput"] = count_zones_out
    row["ratioZonesInputOutput"] = safe_divide(count_zones_in, count_zones_out)
    row["diffZonesInputOutput"] = diff(count_zones_in, count_zones_out)

    # ratioBlocksAreaInput = countBlocksInput // areaInput
    row["ratioBlocksAreaInput"] = safe_divide(count_blocks_in, area_in)
    row["ratioBlocksAreaOutput"] = safe_divide(count_blocks_out, area_out)
    row["diffRatioBlocksAreaInputOutput"] = diff(row["ratioBlocksAreaInput"],
                                                 row["ratioBlocksAreaOutput"])

    row["ratioZonesAreaInput"] = safe_divide(count_zones_in, area_in)
    row["ratioZonesAreaOutput"] = safe_divide(count_zones_out, area_out)
    row["diffRatioZonesAreaInputOutput"] = diff(row["ratioZonesAreaInput"],
                                                row["ratioZonesAreaOutput"])

    # --- Color-related
    # numcolors(grid_in) => how many distinct colors
    count_colors_in = numcolors(grid_in)
    count_colors_out = numcolors(grid_out)
    row["countColorsInput"] = count_colors_in
    row["countColorsOutput"] = count_colors_out
    row["diffColorsInputOutput"] = diff(count_colors_in, count_colors_out)

    # sum of distinct colors => sum of palette(grid)
    pal_in = palette(grid_in)      # returns frozenset of distinct colors
    pal_out = palette(grid_out)
    sum_colors_in = sum(pal_in)    # standard Python sum on that frozenset
    sum_colors_out = sum(pal_out)
    row["sumColorsInput"] = sum_colors_in
    row["sumColorsOutput"] = sum_colors_out
    row["diffSumColorsInputOutput"] = diff(sum_colors_in, sum_colors_out)

    # ratioColorsBlocksInput = countColorsInput // countBlocksInput
    row["ratioColorsBlocksInput"] = safe_divide(count_colors_in, count_blocks_in)
    row["ratioColorsBlocksOutput"] = safe_divide(count_colors_out, count_blocks_out)
    # ratioColorsZonesInput = countColorsInput // countZonesInput
    row["ratioColorsZonesInput"] = safe_divide(count_colors_in, count_zones_in)
    row["ratioColorsZonesOutput"] = safe_divide(count_colors_out, count_zones_out)

    row["diffRatioColorsBlocksInputOutput"] = diff(row["ratioColorsBlocksInput"],
                                                   row["ratioColorsBlocksOutput"])
    row["diffRatioColorsZonesInputOutput"] = diff(row["ratioColorsZonesInput"],
                                                  row["ratioColorsZonesOutput"])

    (fmci, cfmci, smci, csmci,
     flci, cflci, slci, cslci) = top_two_and_bottom_two(grid_in)

    # Store them
    row["firstMostColorInput"] = fmci
    row["countFirstMostColorInput"] = cfmci
    row["secondMostColorInput"] = smci
    row["countSecondMostColorInput"] = csmci

    # difference in frequency of first-most vs second-most
    # example: diffFirstSecondMostColorInput = cfmci - csmci
    row["diffFirstSecondMostColorInput"] = subtract(cfmci, csmci)

    row["firstLeastColorInput"] = flci
    row["countFirstLeastColorInput"] = cflci
    row["secondLeastColorInput"] = slci
    row["countSecondLeastColorInput"] = cslci

    # difference in frequency of first-least vs second-least
    row["diffFirstSecondLeastColorInput"] = subtract(cflci, cslci)

    # --- Get color frequencies for OUTPUT
    (fmco, cfmco, smco, csmco,
     flco, cflco, slco, cslco) = top_two_and_bottom_two(grid_out)

    row["firstMostColorOutput"] = fmco
    row["countFirstMostColorOutput"] = cfmco
    row["secondMostColorOutput"] = smco
    row["countSecondMostColorOutput"] = csmco
    row["diffFirstSecondMostColorOutput"] = subtract(cfmco, csmco)

    row["firstLeastColorOutput"] = flco
    row["countFirstLeastColorOutput"] = cflco
    row["secondLeastColorOutput"] = slco
    row["countSecondLeastColorOutput"] = cslco
    row["diffFirstSecondLeastColorOutput"] = subtract(cflco, cslco)

    # --- Additional "diff" columns comparing input vs output:
    #
    #  diffSecondMostColorInputOutput = secondMostColorInput - secondMostColorOutput
    #  diffFirstLeastColorInputOutput = firstLeastColorInput - firstLeastColorOutput
    #  diffSecondLeastColorInputOutput = secondLeastColorInput - secondLeastColorOutput
    #
    # Remember that your specification for e.g.
    # diffFirstMostColorInputOutput was "color value difference"
    # so we do the same style here:
    row["diffFirstMostColorInputOutput"] = subtract(fmci if fmci else 0,
                                                     fmco if fmco else 0)
    row["diffSecondMostColorInputOutput"] = subtract(smci if smci else 0,
                                                     smco if smco else 0)
    row["diffFirstLeastColorInputOutput"] = subtract(flci if flci else 0,
                                                     flco if flco else 0)
    row["diffSecondLeastColorInputOutput"] = subtract(slci if slci else 0,
                                                      slco if slco else 0)

    row["blockColorTouchingAllBordersInput"] = block_color_touching_all_borders(grid_in)
    row["blockColorTouchingAllBordersOutput"] = block_color_touching_all_borders(grid_out)

    row["middleSplitLineColorInput"] = middle_split_line_color(grid_in)
    row["middleSplitLineColorOutput"] = middle_split_line_color(grid_out)

    # --- Example for “one-pixel blocks”
    # A “block” in DSL is a frozenset of (color, (row,col)).
    # Checking if len(obj)==1 means it’s one pixel.
    one_pixel_in = sum(1 for obj in blocks_in if len(obj) == 1)
    one_pixel_out = sum(1 for obj in blocks_out if len(obj) == 1)
    row["countOnePixelBlocksInput"] = one_pixel_in
    row["countOnePixelBlocksOutput"] = one_pixel_out
    row["diffOnePixelBlocksInputOutput"] = diff(one_pixel_in, one_pixel_out)

    blocks_in = blocks(grid_in)
    blocks_out = blocks(grid_out)
    unique_block_shapes_in = count_unique_shapes(blocks_in)
    unique_block_shapes_out = count_unique_shapes(blocks_out)
    row["countUniqueBlockShapesInput"] = unique_block_shapes_in
    row["countUniqueBlockShapesOutput"] = unique_block_shapes_out
    row["diffUniqueBlockShapesInputOutput"] = subtract(unique_block_shapes_in, unique_block_shapes_out)

    # --- Zones
    zones_in = zones(grid_in)
    zones_out = zones(grid_out)
    unique_zone_shapes_in = count_unique_shapes(zones_in)
    unique_zone_shapes_out = count_unique_shapes(zones_out)
    row["countUniqueZoneShapesInput"] = unique_zone_shapes_in
    row["countUniqueZoneShapesOutput"] = unique_zone_shapes_out
    row["diffUniqueZoneShapesInputOutput"] = subtract(unique_zone_shapes_in, unique_zone_shapes_out)

    rect_in = sum(1 for b in blocks_in if is_rectangle(b))
    rect_out = sum(1 for b in blocks_out if is_rectangle(b))
    row["countRectanglesInput"] = rect_in
    row["countRectanglesOutput"] = rect_out
    row["diffRectanglesInputOutput"] = subtract(rect_in, rect_out)

    # --- Squares
    sq_in = sum(1 for b in blocks_in if is_square(b))
    sq_out = sum(1 for b in blocks_out if is_square(b))
    row["countSquaresInput"] = sq_in
    row["countSquaresOutput"] = sq_out
    row["diffSquaresInputOutput"] = subtract(sq_in, sq_out)

    # --- Straight Lines
    line_in = sum(1 for b in blocks_in if is_straight_line(b))
    line_out = sum(1 for b in blocks_out if is_straight_line(b))
    row["countStraightLineInput"] = line_in
    row["countStraightLineOutput"] = line_out
    row["diffStraightLineInputOutput"] = subtract(line_in, line_out)

    # --- Blocks
    in_blocks = blocks(grid_in)  # returns all univalued blocks in input
    out_blocks = blocks(grid_out)  # returns all univalued blocks in output
    same_b, recolored_b = compare_same_vs_recolored(in_blocks, out_blocks)
    row["countSameBlocksInputOutput"] = same_b
    row["countRecoloredBlocksInputOutput"] = recolored_b

    # --- Zones
    in_zones = zones(grid_in)
    out_zones = zones(grid_out)
    same_z, recolored_z = compare_same_vs_recolored(in_zones, out_zones)
    row["countSameZonesInputOutput"] = same_z
    row["countRecoloredZonesInputOutput"] = recolored_z

    # Count how many blocks in input touch a border
    row["countBlockTouchingBorderInput"] = count_blocks_touching_border(grid_in)

    # Count how many blocks in output touch a border
    row["countBlockTouchingBorderOutput"] = count_blocks_touching_border(grid_out)

    return row

def insert_first_sight_row(conn, row):
    """
    Insert one row (a dictionary) into first_sight_analysis.
    We'll build a parameterized INSERT statement.
    """
    columns = list(row.keys())
    placeholders = ", ".join(["?"] * len(columns))
    colnames = ", ".join(columns)
    sql = f"INSERT INTO first_sight_analysis ({colnames}) VALUES ({placeholders})"
    values = [row[col] for col in columns]
    cur = conn.cursor()
    cur.execute(sql, values)


def fill_first_sight_analysis(conn, filename, data):
    """
    data is the JSON object for one 'file',
    which has 'train' and 'test' arrays,
    each array containing {input, output}.

    We'll loop over 'train' (and possibly 'test' if desired).
    We'll assume 'trainId' enumerates each item in 'train'.
    """
    # If you want to also process 'test', adapt accordingly.
    # Typically, 'trainId' might not apply to 'test' or might differ.

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM first_sight_analysis WHERE filename = ?", (filename,))
    if cur.fetchone()[0] > 0:
        print(f"Skipping first_sight_analysis for {filename}, already exists.")
        return  # Skip computation

    for idx, item in enumerate(data["train"]):
        grid_in = item["input"]
        grid_out = item["output"]
        row_dict = compute_first_sight_row(
            filename=filename,
            trainId=idx,
            grid_in=grid_in,
            grid_out=grid_out
        )
        insert_first_sight_row(conn, row_dict)

    conn.commit()
    print(f"Inserted data into first_sight_analysis for {filename}.")

def is_column_consistent(values):
    """
    Check if a column's values are consistent across all trainId rows for a filename.

    - If all values are None → return True.
    - If there are different non-None values → return False.
    - If all non-None values are identical but at least one None exists → return False.
    - If all non-None values are identical → return True.
    """
    unique_values = set(values)  # Get unique values

    # If all values are None, consider it consistent
    if unique_values == {None}:
        return True

        # If there are multiple distinct non-None values, return False
    filtered_values = {v for v in unique_values if v is not None}
    if len(filtered_values) > 1:
        return False

    # If there's at least one None mixed with identical non-None values, return False
    if None in unique_values:
        return False

    # If all remaining values are identical (no None), return True
    return True

def build_consistency_table(conn):
    """
    Populates first_sight_consistency, skipping filenames that already exist.
    """
    cur = conn.cursor()

    # 1) Get filenames that need consistency checking
    cur.execute("SELECT DISTINCT filename FROM first_sight_analysis")
    analysis_filenames = {row[0] for row in cur.fetchall()}

    cur.execute("SELECT DISTINCT filename FROM first_sight_consistency")
    consistency_filenames = {row[0] for row in cur.fetchall()}

    filenames_to_process = analysis_filenames - consistency_filenames  # Only new filenames

    if not filenames_to_process:
        print("No new files to process for first_sight_consistency.")
        return  # Skip computation if all files are already processed

    # 2) Get column names (excluding filename, trainId)
    cur.execute("PRAGMA table_info(first_sight_analysis)")
    all_columns = [row[1] for row in cur.fetchall()]

    exclude_cols = {"filename", "trainId"}
    numeric_cols = [c for c in all_columns if c not in exclude_cols]

    # 3) Prepare SQL for inserting into first_sight_consistency
    consistency_insert_cols = ["filename"] + numeric_cols
    placeholders = ", ".join(["?"] * len(consistency_insert_cols))
    colnames_str = ", ".join(consistency_insert_cols)
    insert_sql = f"INSERT INTO first_sight_consistency ({colnames_str}) VALUES ({placeholders})"

    for fname in filenames_to_process:
        # Get all rows for this filename
        cur.execute(f"SELECT {', '.join(numeric_cols)} FROM first_sight_analysis WHERE filename = ?", (fname,))
        rows = cur.fetchall()

        # Check consistency for each numeric column
        bool_row = {col: is_column_consistent([r[i] for r in rows]) for i, col in enumerate(numeric_cols)}

        # Insert the computed consistency row
        consistency_values = [fname] + [bool_row[c] for c in numeric_cols]
        cur.execute(insert_sql, consistency_values)

    conn.commit()
    print(f"Inserted data into first_sight_consistency for {len(filenames_to_process)} new files.")

def main_fill_db(directory_path, db_path="../db/database.db"):
    """
    Process all JSON files in the given directory and update the database.
    Skips files that have already been processed.
    """

    start_time = time.time()  # ⏳ Start measuring time

    # 1) Connect to DB
    conn = sqlite3.connect(db_path)

    # 2) List all JSON files in the directory
    json_files = [f for f in os.listdir(directory_path) if f.endswith(".json")]

    if not json_files:
        print(f"No JSON files found in {directory_path}.")
        conn.close()
        return

    print(f"Found {len(json_files)} JSON files in {directory_path}. Processing...")

    for json_filename in json_files:
        json_path = os.path.join(directory_path, json_filename)
        filename = os.path.splitext(json_filename)[0]  # Extract filename without extension

        # 3) Check if this file is already processed
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM first_sight_analysis WHERE filename = ?", (filename,))
        if cur.fetchone()[0] > 0:
            print(f"Skipping {filename}, already processed.")
            continue  # Skip this file

        # 4) Load JSON and process
        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            print(f"Processing {filename}...")
            fill_first_sight_analysis(conn, filename, data)

        except Exception as e:
            print(f"Error processing {filename}: {e}")
            continue  # Skip file if there's an error

    # 5) After processing all files, update first_sight_consistency
    print("Updating first_sight_consistency...")
    build_consistency_table(conn)

    # 6) Commit and close
    conn.commit()
    conn.close()

    # ⏳ Log total execution time
    end_time = time.time()
    total_time = end_time - start_time  # Total elapsed time in seconds
    minutes, seconds = divmod(total_time, 60)  # Convert to minutes and seconds

    print(f"✅ Processing complete. Total time: {int(minutes)} min {seconds:.2f} sec.")

if __name__ == "__main__":
    main_fill_db("./data/training")