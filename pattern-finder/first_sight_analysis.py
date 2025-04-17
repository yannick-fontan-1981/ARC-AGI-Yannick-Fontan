# first_sight_analysis.py

import os
import sqlite3
import json
import sys
from solver.dsl import *


def compute_first_sight_row(filename: str, trainId: int, testId: int, grid_in, grid_out=None):
    grid_in = convert_to_tuple_of_tuples(grid_in)
    row = {"filename": filename, "trainId": trainId, "testId": testId}

    # Dimensions Input
    h_in, w_in = height(grid_in), width(grid_in)
    area_in = multiply(h_in, w_in)
    count_blocks_in = len(blocks(grid_in))
    count_zones_in = len(zones(grid_in))
    count_colors_in = numcolors(grid_in)

    row.update({
        "widthInput": w_in,
        "heightInput": h_in,
        "diffWidthHeightInput": diff(w_in, h_in),
        "ratioWidthHeightInput": safe_divide(w_in, h_in),
        "areaInput": area_in,
        "countBlocksInput": count_blocks_in,
        "countZonesInput": count_zones_in,
        "countColorsInput": count_colors_in
    })

    if grid_out is not None:
        grid_out = convert_to_tuple_of_tuples(grid_out)

        # Dimensions Output
        h_out, w_out = height(grid_out), width(grid_out)
        area_out = multiply(h_out, w_out)
        count_blocks_out = len(blocks(grid_out))
        count_zones_out = len(zones(grid_out))
        count_colors_out = numcolors(grid_out)

        row.update({
            "widthOutput": w_out,
            "ratioWidthInputOutput": safe_divide(w_in, w_out),
            "diffWidthInputOutput": diff(w_in, w_out),
            "heightOutput": h_out,
            "ratioHeightInputOutput": safe_divide(h_in, h_out),
            "diffHeightInputOutput": diff(h_in, h_out),
            "diffWidthHeightOutput": diff(w_out, h_out),
            "ratioWidthHeightOutput": safe_divide(w_out, h_out),
            "areaOutput": area_out,
            "ratioAreaInputOutput": safe_divide(area_in, area_out),
            "diffAreaInputOutput": diff(area_in, area_out),
            "countBlocksOutput": count_blocks_out,
            "ratioBlocksInputOutput": safe_divide(count_blocks_in, count_blocks_out),
            "diffBlocksInputOutput": diff(count_blocks_in, count_blocks_out),
            "countZonesOutput": count_zones_out,
            "ratioZonesInputOutput": safe_divide(count_zones_in, count_zones_out),
            "diffZonesInputOutput": diff(count_zones_in, count_zones_out),
            "countColorsOutput": count_colors_out,
            "diffColorsInputOutput": diff(count_colors_in, count_colors_out)
        })
    else:
        # Set output-related columns to None
        output_columns = [
            "widthOutput", "ratioWidthInputOutput", "diffWidthInputOutput",
            "heightOutput", "ratioHeightInputOutput", "diffHeightInputOutput",
            "diffWidthHeightOutput", "ratioWidthHeightOutput", "areaOutput",
            "ratioAreaInputOutput", "diffAreaInputOutput", "countBlocksOutput",
            "ratioBlocksInputOutput", "diffBlocksInputOutput", "countZonesOutput",
            "ratioZonesInputOutput", "diffZonesInputOutput", "countColorsOutput",
            "diffColorsInputOutput"
        ]
        row.update({col: None for col in output_columns})

    return row


def insert_first_sight_row(conn, row):
    columns = list(row.keys())
    placeholders = ', '.join('?' * len(columns))
    sql = f"INSERT INTO first_sight_analysis ({', '.join(columns)}) VALUES ({placeholders})"
    conn.execute(sql, [row[col] for col in columns])


def process_single_file(json_filepath, db_path="../db/database.db"):
    filename = os.path.basename(json_filepath)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Clear table
    cursor.execute("DELETE FROM first_sight_analysis;")

    with open(json_filepath, 'r') as file:
        data = json.load(file)

    # Process train
    for trainId, item in enumerate(data.get("train", [])):
        row = compute_first_sight_row(filename, trainId, -1, item["input"], item["output"])
        insert_first_sight_row(conn, row)

    # Process test (output is None)
    for testId, item in enumerate(data.get("test", [])):
        row = compute_first_sight_row(filename, -1, testId, item["input"], None)
        insert_first_sight_row(conn, row)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Please provide a path to a JSON file.")
    else:
        process_single_file(sys.argv[1])