#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from collections import defaultdict
from typing import List, Dict, Tuple, Set

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

def structure_based_anonymization(rule_dicts, base_placeholder=-70, bg=0):
    """
    rule_dicts: List[Dict[Tuple[int,...], int]]  # one dict per train
    bg: the background color (default=0)
    Returns a new list of dicts, one per train, where:
      - positions that vary across trains are “wildcarded” to negative placeholders
      - the output color is always mapped to base_placeholder
      - among the wildcard positions, those that always carried the out‐color get base_placeholder,
        the others get base_placeholder-1, base_placeholder-2, etc.
    """
    from collections import defaultdict

    num_trains = len(rule_dicts)

    # 1) bucket by structural mask of which cells ≠ bg
    buckets = defaultdict(lambda: [None]*num_trains)
    for t, rd in enumerate(rule_dicts):
        for nbr, out in rd.items():
            mask = tuple(1 if nbr[i] != bg else 0 for i in range(9))
            buckets[mask][t] = (nbr, out)

    # 2) keep only masks seen in every train
    valid = {m: ex for m, ex in buckets.items() if None not in ex}

    # 3) prepare empty results
    result = [dict() for _ in range(num_trains)]
    wildcard_map: Dict[Tuple[int, ...], List[int]] = {}

    # 4) for each mask, build its own placeholder maps
    for mask, examples in valid.items():
        # examples[t] = (nbr, out) for train t

        # 4a) which neighbor positions actually vary?
        vals_per_pos = [set() for _ in range(9)]
        for nbr, _ in examples:
            for i, v in enumerate(nbr):
                vals_per_pos[i].add(v)
        wildcard_positions = [i for i,s in enumerate(vals_per_pos) if len(s) > 1]

        # 4b) identify the “primary” wildcard positions:
        #     those where nbr[pos] == out for every train
        primary = []
        for pos in wildcard_positions:
            if all(examples[t][0][pos] == examples[t][1] for t in range(num_trains)):
                primary.append(pos)

        # 4c) build placeholder_map for THIS rule
        placeholder_map = {}
        #  first assign base_placeholder to all primary positions
        for pos in primary:
            placeholder_map[pos] = base_placeholder
        #  then assign base_placeholder-1, -2, … to the other wildcard positions
        ph = base_placeholder - 1
        for pos in wildcard_positions:
            if pos not in placeholder_map:
                placeholder_map[pos] = ph
                ph -= 1

        # 4d) output is always anonymized to base_placeholder
        out_ph = base_placeholder

        # before we write them out, record _which_ colors got wildcarded here:
        orig_colors = set()
        for pos in wildcard_positions:
            for t in range(num_trains):
                orig_colors.add(examples[t][0][pos])

        # 4e) rewrite each train’s (nbr,out) → (new_nbr, out_ph)
        for t in range(num_trains):
            nbr, _ = examples[t]
            new_nbr = tuple(placeholder_map.get(i, nbr[i]) for i in range(9))
            result[t][new_nbr] = out_ph

            wildcard_map[new_nbr] = sorted(orig_colors)

    return result, wildcard_map

# ─── 2) Cellular Automaton detection and extraction ─────────────────────────

def detect_ca(input_grid, output_grid, orientation_invariant=False, bg=0):
    print("🔍 Detecting CA rules between input and output grid...")
    rule = {}
    H, W = len(input_grid), len(input_grid[0])
    for y in range(H):
        for x in range(W):
            nbr = get_neighborhood(input_grid, x, y, bg=bg)
            key = canonical(nbr) if orientation_invariant else nbr

            if not (0 <= y < len(output_grid) and 0 <= x < len(output_grid[0])):
                print(f"⚠️ Skipping out-of-bounds output at ({x}, {y})")
                continue

            new_col = output_grid[y][x]
            if key in rule and rule[key] != new_col:
                print(f"❌ Conflict for neighborhood {key}: {rule[key]} vs {new_col}")
                return None
            if key[4] == new_col:
                continue
            rule[key] = new_col
    print(f"✅ Detected {len(rule)} rules.")
    return rule

def detect_ca_on_trains(
    trains,
    tests,
    orientation_invariant=False,
    bg=0
):
    # 1) collect per‐train rule‐dicts
    rule_dicts = []
    for I, O in trains:
        rd = detect_ca(I, O, orientation_invariant, bg) or {}
        rule_dicts.append(rd)

    # 2) raw intersection: keep only nbr‐keys present & equal in all trains
    first = rule_dicts[0]
    raw = {
        k: first[k]
        for k in first
        if all(k in rd and rd[k] == first[k] for rd in rule_dicts[1:])
    }

    # 3) now build the output‐dict:
    #    key = neighborhood tuple,
    #    payload = {output_color, wildcard_colors=[]}
    rules = {
        nbr: {"output_color": out, "wildcard_colors": []}
        for nbr, out in raw.items()
    }

    # 4) collect train‐vs‐test colors
    train_colors = {
        c
        for (I, _), _ in zip(trains, trains)
        for row in I
        for c in row
    }
    test_colors = {
        c
        for grid in tests
        for row in grid
        for c in row
    }
    test_only = test_colors - train_colors

    if test_only:
        # group by “structure” = which positions ≠ bg
        mask_to_nbrs = defaultdict(list)
        for nbr in raw:
            mask = tuple(1 if nbr[i] != bg else 0 for i in range(9))
            mask_to_nbrs[mask].append(nbr)

        # for any mask seen ≥2 times, clone one example nbr→each new color
        for mask, nbr_list in mask_to_nbrs.items():
            if len(nbr_list) >= 2:
                example = nbr_list[0]
                for new_c in test_only:
                    # build a clone: same neighbors, center = new_c
                    clone = list(example)
                    clone[4] = new_c
                    clone = tuple(clone)
                    if clone not in rules:
                        rules[clone] = {
                            "output_color": new_c,
                            "wildcard_colors": []
                        }

    return rules

def detect_ca_on_trains_old(trains, orientation_invariant=False, bg=0):
    """
    runs detect_ca on each (I,O) with the given orientation_invariant & bg,
    computes the exact intersection, then wildcard‐anonymizes those same keys,
    and finally merges raw+anon (anon wins on overlap) into a single dict.
    """
    # 1) collect per‐train rule‐dicts
    rule_dicts = []
    for I, O in trains:
        rd = detect_ca(I, O, orientation_invariant, bg)
        rule_dicts.append(rd or {})

    # 2) raw intersection: keep only nbr‐keys present & equal in all trains
    first = rule_dicts[0]
    raw = {
        k: first[k]
        for k in first
        if all(k in rd and rd[k] == first[k] for rd in rule_dicts[1:])
    }

    # 3) anonymous version: wildcard the same per‐train dicts
    #    we use base_placeholder = –70 inside
    anon_lists, wildcard_map = structure_based_anonymization(rule_dicts,
                                               base_placeholder=-70,
                                               bg=bg)
    #    now every key in anon_lists[0] gets output = –70
    anon = { k: -70 for k in anon_lists[0].keys() }

    # 4) merge them (anon overrides raw on any shared keys)
    merged = raw.copy()
    merged.update(anon)

    # 5) package into one dict that carries both the output _and_ its wildcard_colors
    rules: Dict[Tuple[int,...], Dict] = {}
    for nbr, out_col in merged.items():
        rules[nbr] = {
            "output_color": out_col,
            "wildcard_colors": wildcard_map.get(nbr, [])
        }
    return rules


# ─── 3) Apply CA to an input grid ────────────────────────────────────────────

def print_grid(grid):
    for row in grid:
        print(row)
    print()

# ─── 4) Insert rules into database ──────────────────────────────────────────

def insert_rules(conn, rule_dict, orientation_invariant=True):
    """
    conn:        sqlite3.Connection
    rule_dict:   Dict[Tuple[int,...], int]   # your canonical rules
    orientation_invariant: bool
      if True → we expand each rule into all 4 rotations so the CA engine
      will match under any orientation
      if False → we insert exactly the neighborhood as given (no rotations)
    """
    print(f"\n💾 Inserting {len(rule_dict)} rules into the database (orientation_invariant={orientation_invariant})…")
    cur = conn.cursor()
    seen = set()
    # relative positions (w/o the center)
    positions = [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]
    count = 0

    for nbr, payload in rule_dict.items():
        out_col = payload["output_color"]
        wildcard_list = payload["wildcard_colors"]
        in_col = nbr[4]
        # skip “no‐op” rules
        if in_col == out_col:
            continue

        # if invariant, generate all rotations; otherwise just use the raw neighborhood
        variants = all_rotations(nbr) if orientation_invariant else [nbr]

        for variant in variants:
            key = (variant, out_col)
            if key in seen:
                continue
            seen.add(key)

            # build the list of neighbor‐colors (excluding center)
            neighbor_vals = [variant[i] for i in range(9) if i != 4]

            # insert the “center → out_col” rule
            cur.execute(
                "INSERT INTO cellular_automaton "
                "(input_color, output_color, wildcard_colors, tick) "
                "VALUES (?,?,?,?);",
                (
                    variant[4],
                    out_col,
                    json.dumps(wildcard_list),
                    0
                )
            )
            rule_id = cur.lastrowid

            # now insert each neighbor cell
            for (dx, dy), val in zip(positions, neighbor_vals):
                cur.execute(
                    "INSERT INTO cellular_automaton_cells (rule_id, posRelX, posRelY, color, output) VALUES (?,?,?,?,NULL);",
                    (rule_id, dx, dy, val)
                )

            count += 1

    conn.commit()
    print(f"✅ Inserted {count} unique rule variants.")

def detect_centric_ca_on_trains(
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    tests:  List[List[List[int]]],
    bg: int = 0
) -> Dict[int, Dict[Tuple[int,int], int]]:
    """
    Detect centric‐CA rules on `trains`, then *synthesize* additional rules
    for any color that appears only in `tests` if that rule‐structure occurs
    at least twice among the true centric rules.

    Returns:
      { center_color: { (dx,dy): new_neighbor_color, … }, … }
    """
    neighbor_offsets = [
        (-1, -1), (0, -1), (1, -1),
        (-1,  0),          (1,  0),
        (-1,  1), (0,  1), (1,  1),
    ]

    print(f"🔍 Starting centric‐CA detection over {len(trains)} train(s), bg={bg}")

    # ── 1) build per-train centric maps ────────────────────────────────────────
    per_train: List[Dict[int, Dict[Tuple[int,int], int]]] = []
    for ti, (inp, out) in enumerate(trains):
        H, W = len(inp), len(inp[0])
        print(f"\n▶️ Train #{ti} (size {W}×{H})")
        cmap: Dict[int, Dict[Tuple[int,int],int]] = {}

        for y in range(H):
            for x in range(W):
                center = inp[y][x]
                if center == bg:
                    continue
                # gather all neighbor‐changes
                changes: Dict[Tuple[int,int],int] = {}
                for dx, dy in neighbor_offsets:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W:
                        before, after = inp[ny][nx], out[ny][nx]
                        if after != before:
                            changes[(dx,dy)] = after
                if not changes:
                    continue

                print(f"   ● Found changes around center {center} @({x},{y}): {changes}")
                if center not in cmap:
                    cmap[center] = changes.copy()
                    print(f"     ↳ initial pattern for {center}")
                else:
                    prev = cmap[center]
                    # intersect offsets & require same target color
                    common = {}
                    for off in prev.keys() & changes.keys():
                        if prev[off] == changes[off]:
                            common[off] = prev[off]
                    cmap[center] = common
                    print(f"     ↳ merged → now for {center}: {common}")

        print(f"🏁 Train #{ti} map: {cmap}")
        per_train.append(cmap)

    if not per_train:
        print("⚠️ No training data → returning empty")
        return {}

    # ── 2) intersect center‐colors across all trains ──────────────────────────
    common_centers = set(per_train[0].keys())
    for ti, cmap in enumerate(per_train[1:], start=1):
        print(f"   intersect with train #{ti} centers {set(cmap.keys())}")
        common_centers &= set(cmap.keys())
        print(f"   → now common_centers = {common_centers}")

    # ── 3) for each common center, intersect its neighbor‐maps ───────────────
    result: Dict[int, Dict[Tuple[int,int],int]] = {}
    for c in sorted(common_centers):
        print(f"\n🔎 Processing center‐color {c}")
        base = per_train[0][c]
        print(f"  base pattern: {base}")
        offs = set(base.keys())
        # intersect offsets across all trains
        for ti in range(1, len(per_train)):
            offs &= set(per_train[ti][c].keys())
        print(f"  common offsets: {offs}")

        final_map: Dict[Tuple[int,int],int] = {}
        for off in offs:
            tgt = base[off]
            if all(per_train[ti][c][off] == tgt for ti in range(1, len(per_train))):
                final_map[off] = tgt
            else:
                print(f"   ⚠️ Mismatch at offset {off}, dropping")

        if final_map:
            print(f"  ✅ Keeping centric rule for {c}: {final_map}")
            result[c] = final_map
        else:
            print(f"  ❌ No stable neighbor‐changes for center {c}, dropping")

    # ── 4) find colors only in tests, not in trains ─────────────────────────
    train_colors = {cell for inp,_ in trains for row in inp for cell in row}
    test_colors  = {cell for inp  in tests   for row in inp for cell in row}
    test_only_colors = test_colors - train_colors
    print(f"\n🎯 Test‐only colors: {test_only_colors}")

    # ── 5) group existing rules by their “structure” ────────────────────────────
    struct_to_centers: Dict[frozenset, List[int]] = defaultdict(list)

    print("\n🔖 Grouping centric rules by their neighbor‐offset structure (ignoring replacement colors):")
    for center, mapping in result.items():
        offsets_only = frozenset(mapping.keys())
        print(f"   • Center {center} → offsets {set(offsets_only)}")
        struct_to_centers[offsets_only].append(center)

    print("\n📦 Structures detected:")
    for offsets, centers in struct_to_centers.items():
        print(f"   → Offsets {set(offsets)} shared by centers {centers}")

    # ── 6) clone for any test‐only colors when a structure is “common” ─────────
    print("\n🎯 Now cloning structures shared by ≥ 2 centers for test‐only colors:")
    for offsets, centers in struct_to_centers.items():
        if len(centers) >= 2:
            print(f"   • Structure {set(offsets)} is common to centers {centers}")
            for c_test in test_only_colors:
                # only add if not already in result:
                if c_test not in result:
                    new_map = {off: c_test for off in offsets}
                    result[c_test] = new_map
                    print(f"     ➕ Added centric rule for test‐only center {c_test}: {new_map}")

    print(f"\n✅ Final centric‐CA rules ({len(result)} total):")
    for c, mapping in result.items():
        print(f"   • Center {c}: {mapping}")

    return result

def insert_centric_rules(conn: sqlite3.Connection,
                         centric_rules: Dict[int, Dict[Tuple[int, int], int]]):
    """
    conn:          an open sqlite3.Connection
    centric_rules: { center_color: { (dx,dy): new_neighbor_color, … }, … }

    For each center_color we:
      • INSERT a row into cellular_automaton with centric=1
      • INSERT one cellular_automaton_cells row per neighbor‐offset, writing only .output
    """
    cur = conn.cursor()
    count = 0

    for center_col, nbr_changes in centric_rules.items():
        # 1) insert the parent rule
        #    input_color & output_color both = center_col (center pixel doesn’t move)
        #    neighbor_count = number of changed neighbors
        cur.execute("""
        INSERT INTO cellular_automaton
          (input_color, output_color, neighbor_count, wildcard_colors, centric)
        VALUES (?,           ?,            ?,              NULL,            1);
        """, (center_col, center_col, len(nbr_changes)))
        rule_id = cur.lastrowid

        # 2) insert each neighbor‐change row
        #    leave the old `color` NULL, write the new color into the new `output` column
        for (dx, dy), new_col in nbr_changes.items():
            cur.execute("""
            INSERT INTO cellular_automaton_cells
              (rule_id, posRelX, posRelY, color, output)
            VALUES (?,       ?,       ?,        NULL,   ?);
            """, (rule_id, dx, dy, new_col))
            count += 1

    conn.commit()
    print(f"✅ Inserted {len(centric_rules)} centric rules, {count} neighbor‐cells total.")


def detect_and_insert_unified_ca(
    conn: sqlite3.Connection,
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    tests: List[List[List[int]]],
    orientation_invariant: bool = True,
    bg: int = 0
) -> bool:
    """
    Verbose unified CA detection & insertion, without any DELETE calls.
    - Detects both center-color changes and neighbor changes
    - Intersects across training examples
    - Clones for test-only colors
    - Filters out trivial identity rules
    - Inserts into `cellular_automaton` and `cellular_automaton_cells`
    Returns True if at least one nontrivial rule was inserted.
    """
    print(f"🔍 Starting unified‐CA detection over {len(trains)} train(s), {len(tests)} test(s), bg={bg}, orientation_invariant={orientation_invariant}")

    # ── Helpers ──────────────────────────────────────────────────────────
    def get_nbr(grid, x, y):
        H, W = len(grid), len(grid[0])
        nbr = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                nbr.append(grid[ny][nx] if 0 <= ny < H and 0 <= nx < W else bg)
        return tuple(nbr)

    def rot90(n):
        mapping = [6,3,0,7,4,1,8,5,2]
        return tuple(n[i] for i in mapping)

    def all_rots(n):
        r0 = n
        r1 = rot90(r0)
        r2 = rot90(r1)
        r3 = rot90(r2)
        return [r0, r1, r2, r3]

    def canonical(n):
        rots = all_rots(n)
        flips = [tuple(r[i] for i in [2,1,0,5,4,3,8,7,6]) for r in rots]
        return min(rots + flips)

    neighbor_offsets = [(-1,-1),(0,-1),(1,-1),(-1,0),(0,0),(1,0),(-1,1),(0,1),(1,1)]
    per_train: List[Dict[Tuple[int,int], set]] = []

    # ── 1) Build per-train transition → neighbor-pattern sets ────────────
    for ti, (inp, out) in enumerate(trains):
        H, W = len(inp), len(inp[0])
        print(f"\n▶️ Train #{ti} (size {W}×{H})")
        cmap: Dict[Tuple[int,int], set] = defaultdict(set)
        for y in range(H):
            for x in range(W):
                c0, c1 = inp[y][x], out[y][x]
                if c0 == c1 == bg:
                    continue
                if c0 != c1:
                    print(f"   ● Change of center @({x},{y}): {c0}→{c1}")
                nb0 = get_nbr(inp, x, y)
                if orientation_invariant:
                    nb0 = canonical(nb0)
                cmap[(c0, c1)].add(nb0)
        print(f"🏁 Train #{ti} transitions: {{ {', '.join(f'{k}: {len(v)}' for k,v in cmap.items())} }}")
        per_train.append(cmap)

    # ── 2) Intersect transitions across all trains ───────────────────────
    common_keys = set(per_train[0].keys())
    for cmap in per_train[1:]:
        common_keys &= set(cmap.keys())
    print(f"\n🔎 Common center-transitions: {common_keys}")

    # ── 3) For each common transition, intersect neighbor-pattern sets ────
    unified: Dict[Tuple[int,int], set] = {}
    for key in sorted(common_keys):
        patterns = per_train[0][key].copy()
        for cmap in per_train[1:]:
            patterns &= cmap[key]
        if patterns:
            unified[key] = patterns
            print(f"   ✅ Kept {key}: {len(patterns)} patterns")
        else:
            print(f"   ❌ Dropped {key}: no stable patterns")

    if not unified:
        print("\n⚠️ No nontrivial rules → aborting.")
        return False

    # ── 4) Clone for test-only colors if ≥2 rules exist ────────────────
    train_colors = {k[0] for cmap in per_train for k in cmap.keys()}
    test_colors  = {c for grid in tests for row in grid for c in row}
    clones = 0
    if len(unified) >= 2:
        for tc in sorted(test_colors - train_colors):
            pattern = canonical((tc,)*9) if orientation_invariant else (tc,)*9
            unified[(tc, tc)] = {pattern}
            print(f"   ➕ Cloned center-only {tc}→{tc}")
            clones += 1
    print(f"    Total clones: {clones}")

    # ── 5) Filter out identity-only rules ───────────────────────────────
    final: Dict[Tuple[int,int], set] = {}
    for (c0, c1), pats in unified.items():
        # identity-only: no center change and single uniform pattern
        if c0 == c1 and all(pat == ((c0,)*9) for pat in pats):
            print(f"   ⚠️ Removing identity rule {c0}→{c1}")
        else:
            final[(c0, c1)] = pats
    if not final:
        print("\n⚠️ Only identity rules remain → aborting.")
        return False

    print(f"\n✅ Final rules to insert: {list(final.keys())}")

    # ── 6) Insert into database (no DELETEs) ──────────────────────────
    cur = conn.cursor()
    inserted = 0
    seen = set()
    for (c0, c1), patterns in final.items():
        for pat in patterns:
            key = (c0, c1, pat)
            if key in seen:
                continue
            seen.add(key)
            print(f"   • Inserting {c0}→{c1}, neighborhood={pat}")
            # parent rule
            cur.execute(
                """
                INSERT INTO cellular_automaton
                  (input_color, output_color, neighbor_count, wildcard_colors, centric)
                VALUES (?,?,?,?,?);
                """,
                (c0, c1, len(pat), json.dumps([]), True)
            )
            rid = cur.lastrowid
            # individual neighbor cells
            for idx, val in enumerate(pat):
                dx = (idx % 3) - 1
                dy = (idx // 3) - 1
                cur.execute(
                    """
                    INSERT INTO cellular_automaton_cells
                      (rule_id, posRelX, posRelY, color, output)
                    VALUES (?,?,?,?,?);
                    """,
                    (rid, dx, dy, val, val)
                )
            inserted += 1
    conn.commit()
    print(f"💾 Inserted {inserted} rule variants.")
    return True



# ─── 5) Main ───────────────────────────────────────────────────────────────

def main(json_source: str, inline: bool = False, name: str | None = None):
    print("🚀 Starting CA rule extractor")
    if inline:
        data = json.loads(json_source)
        fname = name or "__INLINE__"
        print(f"📎 Using inline JSON")
    else:
        with open(json_source) as f:
            data = json.load(f)
        fname = name or os.path.basename(json_source)
        print(f"📂 Loaded JSON from file: {fname}")

    train = data.get("train", [])
    test = data.get("test", [])
    trains = [(t["input"], t["output"]) for t in train]
    tests = [(t["input"]) for t in test]
    print(f"🧪 Training examples: {len(trains)}, Testing examples: {len(tests)}")



    # ── Include any new color seen in the TEST inputs but never in TRAIN inputs ──
    # collect all colors present in train‐inputs
    train_colors = set(
        c
        for grid,_ in trains
        for row in grid
        for c in row
    )
    # collect all colors present in test‐inputs
    test_colors = set(
        c
        for grid in tests
        for row in grid
        for c in row
    )
    # any truly “new” colors?
    #new_colors = test_colors - train_colors
    #if new_colors:
    #    for payload in rules.values():
    #        if not payload["wildcard_colors"]:
    #            continue
    #        for c in new_colors:
    #            if c not in payload["wildcard_colors"]:
    #                payload["wildcard_colors"].append(c)

    db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "database.db"))
    print(f"📦 Using database at: {db}")
    conn = sqlite3.connect(db)

    conn.execute("DELETE FROM cellular_automaton;")
    conn.execute("DELETE FROM cellular_automaton_cells;")
    conn.commit()
    print("🧹 Cleared existing CA rules from database")

    invariant = True
    found = detect_and_insert_unified_ca(conn, trains, tests, orientation_invariant=invariant, bg=0)

    # fallback if empty
    if not found:
        invariant = False
        detect_and_insert_unified_ca(conn, trains, tests, orientation_invariant=invariant, bg=0)

    #insert_rules(conn, rules, invariant)

    #centric_rules = detect_centric_ca_on_trains(trains, tests, bg=0)
    #insert_centric_rules(conn, centric_rules)

    conn.close()

    #print(f"\n✅ Done! Stored {len(rules)} canonical CA rules for task: {fname}")

    # Optionally test application
    # for idx, (inp, exp) in enumerate(tests):
    #     print(f"--- Test {idx} ---")
    #     pred = apply_ca(inp, rules)
    #     print("Predicted:")
    #     print_grid(pred)
    #     print("Expected:")
    #     print_grid(exp)
    #     print("Match?", pred == exp)

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
