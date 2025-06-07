#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from collections import defaultdict

from constelize.dsl.grid_dsl import apply_ca


# ─── 1) Neighborhood utilities ───────────────────────────────────────────────

def get_neighborhood(grid, x, y, bg=0):
    """
    Return the 3×3 neighborhood around (x,y) as a length-9 tuple in row-major order:
      (nw, n, ne, w, center, e, sw, s, se).
    Out-of-bounds cells are filled with `bg`.
    """
    H, W = len(grid), len(grid[0])
    nbr = []
    for dy in (-1, 0, +1):
        for dx in (-1, 0, +1):
            ny, nx = y + dy, x + dx
            nbr.append(grid[ny][nx] if 0 <= ny < H and 0 <= nx < W else bg)
    return tuple(nbr)


def rotate90(nbr):
    """Rotate a flattened 3×3 neighborhood 90° clockwise."""
    mapping = [6, 3, 0, 7, 4, 1, 8, 5, 2]
    return tuple(nbr[i] for i in mapping)


def all_rotations(nbr):
    r0 = nbr
    r1 = rotate90(r0)
    r2 = rotate90(r1)
    r3 = rotate90(r2)
    return [r0, r1, r2, r3]


def canonical(nbr):
    """
    If orientation_invariant, pick the lexicographically smallest of
    all 8 dihedral variants (4 rotations + 4 horizontal flips).
    """
    rots = all_rotations(nbr)
    flips = [tuple(r[i] for i in [2,1,0,5,4,3,8,7,6]) for r in rots]
    return min(rots + flips)

# ─── 2) Cellular Automaton detection and extraction ─────────────────────────

def detect_ca(input_grid, output_grid, orientation_invariant=False, bg=0):
    rule = {}
    H, W = len(input_grid), len(input_grid[0])
    for y in range(H):
        for x in range(W):
            nbr = get_neighborhood(input_grid, x, y, bg=bg)
            key = canonical(nbr) if orientation_invariant else nbr
            new_col = output_grid[y][x]
            if key in rule and rule[key] != new_col:
                return None
            rule[key] = new_col
    return rule


def detect_ca_on_trains(trains, orientation_invariant=False, bg=0):
    rule_dicts = []
    for idx, (I, O) in enumerate(trains):
        rd = detect_ca(I, O, orientation_invariant, bg)
        if rd is None:
            print(f"Warning: train {idx} has conflicting mappings; skipping its rules.")
            rd = {}
        rule_dicts.append(rd)
    if not rule_dicts:
        return {}
    common = set(rule_dicts[0].keys())
    for rd in rule_dicts[1:]:
        common &= set(rd.keys())
    intersection = {k: rule_dicts[0][k] for k in common
                    if all(rd[k] == rule_dicts[0][k] for rd in rule_dicts)}
    return intersection

# ─── 3) Apply CA to an input grid ────────────────────────────────────────────

def print_grid(grid):
    for row in grid:
        print(row)
    print()

# ─── 4) Insert rules into database ──────────────────────────────────────────

def insert_rules(conn, rule_dict):
    cur = conn.cursor()
    seen = set()
    positions = [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]
    for nbr, out_col in rule_dict.items():
        in_col = nbr[4]
        if in_col == out_col:
            continue
        for rot in all_rotations(nbr):
            if (rot, out_col) in seen:
                continue
            seen.add((rot, out_col))
            neighbor_vals = [rot[i] for i in range(9) if i != 4]
            cumulative = sum(neighbor_vals)
            cur.execute(
                "INSERT INTO cellular_automaton"
                " (input_color, output_color, cumulative_color)"
                " VALUES (?,?,?);",
                (rot[4], out_col, cumulative)
            )
            rule_id = cur.lastrowid
            for (dx, dy), val in zip(positions, neighbor_vals):
                cur.execute(
                    "INSERT INTO cellular_automaton_cells"
                    " (rule_id, posRelX, posRelY, color)"
                    " VALUES (?,?,?,?);",
                    (rule_id, dx, dy, val)
                )
    conn.commit()


# ─── 5) Main ───────────────────────────────────────────────────────────────

def main(json_source: str, inline: bool = False, name: str | None = None):
    # load JSON
    if inline:
        data = json.loads(json_source)
        fname = name or "__INLINE__"
    else:
        with open(json_source) as f:
            data = json.load(f)
        fname = name or os.path.basename(json_source)

    train = data.get("train", [])
    test = data.get("test", [])
    trains = [(t["input"], t["output"]) for t in train]
    tests = [(t["input"], t["output"]) for t in test]

    # detect rules
    rules = detect_ca_on_trains(trains, orientation_invariant=True, bg=0)

    # setup DB
    db = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "db", "database.db"))
    conn = sqlite3.connect(db)
    # clear previous entries
    conn.execute("DELETE FROM cellular_automaton;")
    conn.execute("DELETE FROM cellular_automaton_cells;")
    conn.commit()

    # insert
    insert_rules(conn, rules)
    conn.close()
    print(f"[{fname}] Stored {len(rules)} CA rules.")

    # apply and compare on test
    #for idx, (inp, exp) in enumerate(tests):
    #    print(f"--- Test {idx} ---")
    #    pred = apply_ca(inp, rules)
    #    print("Predicted:")
    #    print_grid(pred)
    #    print("Expected:")
    #    print_grid(exp)
    #    print("Match?", pred == exp)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Detect & store cellular automaton rules.")
    p.add_argument("json_input", help="ARC JSON file or raw JSON if --inline")
    p.add_argument("--inline", action="store_true", help="Raw JSON mode")
    p.add_argument("--name", type=str, help="Override filename/task_id")
    args = p.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)






















def main_test(train_pairs, db_path="ca_rules.db", orientation_invariant=False, bg=0):
    rules = detect_ca_on_trains(train_pairs, orientation_invariant, bg)
    if not rules:
        print("No consistent CA rules found across all trains.")
        return
    conn = sqlite3.connect(db_path)
    insert_rules(conn, rules)
    conn.close()
    print(f"Stored {len(rules)} CA rules (with rotations) into '{db_path}'")

if __name__ == "__main_test__":
    # Real train/test from ARC-like JSON
    data = {
        "train": [
            {"input": [
                [0,0,0,0,0,0,0],
                [0,8,0,0,0,0,0],
                [0,8,8,0,0,0,0],
                [0,0,0,0,8,8,0],
                [0,0,0,0,0,8,0],
                [0,0,0,0,0,0,0],
                [0,0,0,0,0,0,0]
            ], "output": [
                [0,0,0,0,0,0,0],
                [0,8,1,0,0,0,0],
                [0,8,8,0,0,0,0],
                [0,0,0,0,8,8,0],
                [0,0,0,0,1,8,0],
                [0,0,0,0,0,0,0],
                [0,0,0,0,0,0,0]
            ]},
            {"input": [
                [0,0,0,0,8,8,0],
                [0,0,0,0,0,8,0],
                [0,0,8,0,0,0,0],
                [0,0,8,8,0,0,0],
                [0,0,0,0,0,0,0],
                [0,0,0,0,8,0,0],
                [0,0,0,8,8,0,0]
            ], "output": [
                [0,0,0,0,8,8,0],
                [0,0,0,0,1,8,0],
                [0,0,8,1,0,0,0],
                [0,0,8,8,0,0,0],
                [0,0,0,0,0,0,0],
                [0,0,0,1,8,0,0],
                [0,0,0,8,8,0,0]
            ]}
        ],
        "test": [
            {"input": [
                [0,0,0,0,0,8,8],
                [8,8,0,0,0,0,8],
                [8,0,0,0,0,0,0],
                [0,0,0,8,0,0,0],
                [0,0,0,8,8,0,0],
                [0,8,0,0,0,0,0],
                [8,8,0,0,0,0,0]
            ], "output": [
                [0,0,0,0,0,8,8],
                [8,8,0,0,0,1,8],
                [8,1,0,0,0,0,0],
                [0,0,0,8,1,0,0],
                [0,0,0,8,8,0,0],
                [1,8,0,0,0,0,0],
                [8,8,0,0,0,0,0]
            ]}
        ]
    }
    train_pairs = [(item["input"], item["output"]) for item in data["train"]]
    test_pairs = [(item["input"], item["output"]) for item in data["test"]]

    # 5.1) Detect and store rules
    rules = detect_ca_on_trains(train_pairs, orientation_invariant=True, bg=0)
    db_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "db", "database.db"))
    conn = sqlite3.connect(db_path)
    insert_rules(conn, rules)
    conn.close()
    print(f"Stored {len(rules)} CA rules into '{db_path}'.")

    # 5.2) Apply rules to test inputs and compare
    for idx, (inp, expected) in enumerate(test_pairs):
        print(f"--- Test {idx} ---")
        pred = apply_ca(inp, rules, orientation_invariant=True, bg=0)
        print("Predicted:")
        print_grid(pred)
        print("Expected:")
        print_grid(expected)
        match = pred == expected
        print(f"Match? {match}\n")
