# first_sight_analysis.py
import argparse
import os
import sqlite3
import json
import sys
from collections import Counter

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

    # Color frequency metrics for input
    flat_in = [cell for r in grid_in for cell in r]
    cnt_in = Counter(flat_in)

    # Determine input background: top color, or -1 if tie
    most_common_in = cnt_in.most_common()
    if most_common_in:
        top_count = most_common_in[0][1]
        # tie if second has same count
        bg_in = -1 if len(most_common_in) > 1 and most_common_in[1][1] == top_count else most_common_in[0][0]
    else:
        bg_in = -1
    # count distinct colors excluding background
    countColorsWithoutBgInput = len(set(cnt_in.keys()) - {bg_in})
    # count “alone” pixels (non-bg pixels with no same‐color neighbor)
    countPixelsAloneInput = 0
    for i in range(h_in):
        for j in range(w_in):
            col = grid_in[i][j]
            if col == bg_in:
                continue
            # check 8 neighbors
            has_nb = any(
                0 <= i+di < h_in and 0 <= j+dj < w_in and grid_in[i+di][j+dj] == col
                for di in (-1, 0, 1) for dj in (-1, 0, 1) if not (di == dj == 0)
            )
            if not has_nb:
                countPixelsAloneInput += 1

    most_common_in = cnt_in.most_common()
    if most_common_in:
        firstMostColorInput, countFirstMostColorInput = most_common_in[0]
        if len(most_common_in) > 1:
            secondMostColorInput, countSecondMostColorInput = most_common_in[1]
        else:
            secondMostColorInput, countSecondMostColorInput = None, 0
        diffFirstSecondMostColorInput = (firstMostColorInput - secondMostColorInput) if secondMostColorInput is not None else None
    else:
        firstMostColorInput = countFirstMostColorInput = secondMostColorInput = countSecondMostColorInput = diffFirstSecondMostColorInput = None

    # Least frequent metrics input
    least_common_in = sorted(cnt_in.items(), key=lambda x: x[1])
    if least_common_in:
        firstLeastColorInput, countFirstLeastColorInput = least_common_in[0]
        if len(least_common_in) > 1:
            secondLeastColorInput, countSecondLeastColorInput = least_common_in[1]
        else:
            secondLeastColorInput, countSecondLeastColorInput = None, 0
        diffFirstSecondLeastColorInput = (firstLeastColorInput - secondLeastColorInput) if secondLeastColorInput is not None else None
    else:
        firstLeastColorInput = countFirstLeastColorInput = secondLeastColorInput = countSecondLeastColorInput = diffFirstSecondLeastColorInput = None

    row.update({
        "widthInput": w_in,
        "heightInput": h_in,
        "diffWidthHeightInput": diff(w_in, h_in),
        "ratioWidthHeightInput": safe_divide(w_in, h_in),
        "areaInput": area_in,
        "countBlocksInput": count_blocks_in,
        "countZonesInput": count_zones_in,
        "countColorsInput": count_colors_in,
        "firstMostColorInput": firstMostColorInput,
        "countFirstMostColorInput": countFirstMostColorInput,
        "secondMostColorInput": secondMostColorInput,
        "countSecondMostColorInput": countSecondMostColorInput,
        "diffFirstSecondMostColorInput": diffFirstSecondMostColorInput,
        "firstLeastColorInput": firstLeastColorInput,
        "countFirstLeastColorInput": countFirstLeastColorInput,
        "secondLeastColorInput": secondLeastColorInput,
        "countSecondLeastColorInput": countSecondLeastColorInput,
        "diffFirstSecondLeastColorInput": diffFirstSecondLeastColorInput,
        "countColorsWithoutBgInput": countColorsWithoutBgInput,
        "countPixelsAloneInput": countPixelsAloneInput,
    })

    if grid_out is not None:
        grid_out = convert_to_tuple_of_tuples(grid_out)

        # Dimensions Output
        h_out, w_out = height(grid_out), width(grid_out)
        area_out = multiply(h_out, w_out)
        count_blocks_out = len(blocks(grid_out))
        count_zones_out = len(zones(grid_out))
        count_colors_out = numcolors(grid_out)

        # Color frequency metrics for output
        flat_out = [cell for r in grid_out for cell in r]
        cnt_out = Counter(flat_out)

        # ── Color frequency metrics for output ──────────────────────────────────────
        most_common_out = cnt_out.most_common()
        if most_common_out:
            top_count_o = most_common_out[0][1]
            bg_out = -1 if len(most_common_out) > 1 and most_common_out[1][1] == top_count_o else most_common_out[0][0]
        else:
            bg_out = -1
        countColorsWithoutBgOutput = len(set(cnt_out.keys()) - {bg_out})
        countPixelsAloneOutput = 0
        for i in range(h_out):
            for j in range(w_out):
                col = grid_out[i][j]
                if col == bg_out:
                    continue
                has_nb = any(
                    0 <= i+di < h_out and 0 <= j+dj < w_out and grid_out[i+di][j+dj] == col
                    for di in (-1, 0, 1) for dj in (-1, 0, 1) if not (di == dj == 0)
                )
                if not has_nb:
                    countPixelsAloneOutput += 1

        most_common_out = cnt_out.most_common()
        if most_common_out:
            firstMostColorOutput, countFirstMostColorOutput = most_common_out[0]
            if len(most_common_out) > 1:
                secondMostColorOutput, countSecondMostColorOutput = most_common_out[1]
            else:
                secondMostColorOutput, countSecondMostColorOutput = None, 0
            diffFirstSecondMostColorOutput = (firstMostColorOutput - secondMostColorOutput) if secondMostColorOutput is not None else None
        else:
            firstMostColorOutput = countFirstMostColorOutput = secondMostColorOutput = countSecondMostColorOutput = diffFirstSecondMostColorOutput = None

        least_common_out = sorted(cnt_out.items(), key=lambda x: x[1])
        if least_common_out:
            firstLeastColorOutput, countFirstLeastColorOutput = least_common_out[0]
            if len(least_common_out) > 1:
                secondLeastColorOutput, countSecondLeastColorOutput = least_common_out[1]
            else:
                secondLeastColorOutput, countSecondLeastColorOutput = None, 0
            diffFirstSecondLeastColorOutput = (firstLeastColorOutput - secondLeastColorOutput) if secondLeastColorOutput is not None else None
        else:
            firstLeastColorOutput = countFirstLeastColorOutput = secondLeastColorOutput = countSecondLeastColorOutput = diffFirstSecondLeastColorOutput = None

        # Differences between input and output color values
        diffFirstMostColorInputOutput = (firstMostColorInput - firstMostColorOutput) if None not in (firstMostColorInput, firstMostColorOutput) else None
        diffSecondMostColorInputOutput = (secondMostColorInput - secondMostColorOutput) if None not in (secondMostColorInput, secondMostColorOutput) else None
        diffFirstLeastColorInputOutput = (firstLeastColorInput - firstLeastColorOutput) if None not in (firstLeastColorInput, firstLeastColorOutput) else None
        diffSecondLeastColorInputOutput = (secondLeastColorInput - secondLeastColorOutput) if None not in (secondLeastColorInput, secondLeastColorOutput) else None

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
            "diffColorsInputOutput": diff(count_colors_in, count_colors_out),
            "firstMostColorOutput": firstMostColorOutput,
            "countFirstMostColorOutput": countFirstMostColorOutput,
            "secondMostColorOutput": secondMostColorOutput,
            "countSecondMostColorOutput": countSecondMostColorOutput,
            "diffFirstSecondMostColorOutput": diffFirstSecondMostColorOutput,
            "firstLeastColorOutput": firstLeastColorOutput,
            "countFirstLeastColorOutput": countFirstLeastColorOutput,
            "secondLeastColorOutput": secondLeastColorOutput,
            "countSecondLeastColorOutput": countSecondLeastColorOutput,
            "diffFirstSecondLeastColorOutput": diffFirstSecondLeastColorOutput,
            "diffFirstMostColorInputOutput": diffFirstMostColorInputOutput,
            "diffSecondMostColorInputOutput": diffSecondMostColorInputOutput,
            "diffFirstLeastColorInputOutput": diffFirstLeastColorInputOutput,
            "diffSecondLeastColorInputOutput": diffSecondLeastColorInputOutput,
            "countColorsWithoutBgOutput": countColorsWithoutBgOutput,
            "countPixelsAloneOutput": countPixelsAloneOutput,
        })
    else:
        # Set output-related columns to None
        output_cols = [
            "widthOutput", "ratioWidthInputOutput", "diffWidthInputOutput",
            "heightOutput", "ratioHeightInputOutput", "diffHeightInputOutput",
            "diffWidthHeightOutput", "ratioWidthHeightOutput", "areaOutput",
            "ratioAreaInputOutput", "diffAreaInputOutput", "countBlocksOutput",
            "ratioBlocksInputOutput", "diffBlocksInputOutput", "countZonesOutput",
            "ratioZonesInputOutput", "diffZonesInputOutput", "countColorsOutput",
            "diffColorsInputOutput",
            "firstMostColorOutput", "countFirstMostColorOutput",
            "secondMostColorOutput", "countSecondMostColorOutput",
            "diffFirstSecondMostColorOutput", "firstLeastColorOutput",
            "countFirstLeastColorOutput", "secondLeastColorOutput",
            "countSecondLeastColorOutput", "diffFirstSecondLeastColorOutput",
            "diffFirstMostColorInputOutput", "diffSecondMostColorInputOutput",
            "diffFirstLeastColorInputOutput", "diffSecondLeastColorInputOutput",
            "countColorsWithoutBgOutput", "countPixelsAloneOutput",
        ]
        row.update({col: None for col in output_cols})

    return row



def insert_first_sight_row(conn, row):
    columns = list(row.keys())
    placeholders = ', '.join('?' * len(columns))
    sql = f"INSERT INTO first_sight_analysis ({', '.join(columns)}) VALUES ({placeholders})"
    conn.execute(sql, [row[col] for col in columns])


def process_single_file(filename: str, data: dict, conn: sqlite3.Connection):
    """
    Clears and repopulates the first_sight_analysis table
    using the given filename label and already-loaded JSON data.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM first_sight_analysis;")

    # TRAIN rows (output known)
    for trainId, item in enumerate(data.get("train", [])):
        row = compute_first_sight_row(
            filename,
            trainId,
            -1,
            item["input"],
            item["output"],
        )
        insert_first_sight_row(conn, row)

    # TEST rows (no expected output)
    for testId, item in enumerate(data.get("test", [])):
        row = compute_first_sight_row(
            filename,
            -1,
            testId,
            item["input"],
            None,
        )
        insert_first_sight_row(conn, row)

    conn.commit()


def main(json_source: str, *, inline: bool = False, name: str | None = None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path    = os.path.abspath(os.path.join(script_dir, "..", "db", "database.db"))
    conn       = sqlite3.connect(db_path)

    # decide what label we pass as "filename"
    if name:
        filename = name
    elif inline:
        filename = "<in-memory-json>"
    else:
        filename = os.path.basename(json_source)

    # load JSON
    if inline:
        data = json.loads(json_source)
    else:
        with open(json_source, "r") as f:
            data = json.load(f)

    process_single_file(filename, data, conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute first_sight_analysis from an ARC JSON (file or inline)."
    )
    parser.add_argument(
        "json_input",
        help="Path to an ARC JSON file, or (with --inline) a raw JSON string"
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Treat json_input as the full JSON text, not a file path"
    )
    parser.add_argument(
        "--name", "-n",
        help="Override the “filename” label (e.g. 'scenario_with_denoise')"
    )
    args = parser.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)
