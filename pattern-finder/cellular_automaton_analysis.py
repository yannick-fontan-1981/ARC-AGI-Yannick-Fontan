#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from collections import defaultdict
from typing import List, Dict, Tuple, Set, Optional, Any

from constelize.dsl.grid_dsl import apply_ca

index_map = [6,3,0,7,4,1,8,5,2]

flatten_order = [(dx, dy)
                 for dy in (-1, 0, 1)
                 for dx in (-1, 0, 1)]

def compute_color_sets(
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    tests: List[List[List[int]]],
    facts_by_train: Dict[int, List[Dict[str, Tuple[Tuple[int,...], Tuple[int,...]]]]],
    bg: int = 0
) -> Dict[str, Any]:
    """
    Calcule :
      - mêmes ensembles de couleurs qu'avant (sur trains + tests)
      - centerFactColorsByTrain : { train_idx: [couleurs centrales…], … }
      - centerFactColorsSameByTrain : bool, si toutes les listes sont identiques
    """
    # --- couleurs des grilles ---
    train_inputs   = [{c for row in inp for c in row} for inp, _ in trains]
    train_outputs  = [{c for row in out for c in row} for _, out in trains]
    test_input_sets= [{c for row in inp for c in row} for inp in tests]

    # intersections
    all_train_in   = set.intersection(*train_inputs)   if train_inputs   else set()
    all_train_out  = set.intersection(*train_outputs)  if train_outputs  else set()
    all_test_in    = set.intersection(*test_input_sets) if test_input_sets else set()

    same_input     = all_train_in  & all_test_in
    same_output    = all_train_out
    same_colors    = same_input    & same_output

    # unions
    union_train_in = set.union(*train_inputs)   if train_inputs   else set()
    union_train_out= set.union(*train_outputs)  if train_outputs  else set()
    union_test_in  = set.union(*test_input_sets) if test_input_sets else set()
    union_all      = union_train_in | union_train_out | union_test_in

    diff_colors    = union_all - same_colors
    diff_input     = union_train_in - same_input
    diff_output    = union_train_out - same_output

    common_train_test = union_train_in & union_test_in
    new_by_test       = union_test_in - union_train_in
    new_by_train      = union_train_in - union_test_in

    # --- NOUVEAU : calcul des couleurs centrales par train ---
    # facts_by_train : { train_idx: [ {'nbr_in':…, 'nbr_out':…}, … ], … }
    centerFactColorsByTrain: Dict[int, List[int]] = {}
    for t_idx in range(1, len(trains) + 1):
        facts = facts_by_train.get(t_idx, [])
        # extraire la couleur du centre de chaque fait et dédupliquer
        colors = { fact['nbr_in'][4] for fact in facts }
        centerFactColorsByTrain[t_idx] = sorted(colors)

    # vérifier si toutes les listes sont identiques
    unique_color_sets = { tuple(lst) for lst in centerFactColorsByTrain.values() }
    centerFactColorsSameByTrain = (len(unique_color_sets) == 1)

    # --- retour final ---
    return {
        'sameColorsForAll': same_colors,
        'sameInputColorsForAll': same_input,
        'sameOutputColorsForAll': same_output,
        'differentColorsForAll': diff_colors,
        'differentInputColorsForAll': diff_input,
        'differentOutputColorsForAll': diff_output,
        'commonColorsInTrainAndTest': common_train_test,
        'newColorsByTest': new_by_test,
        'newColorsByTrain': new_by_train,
        'centerFactColorsByTrain': centerFactColorsByTrain,
        'centerFactColorsSameByTrain': centerFactColorsSameByTrain,
    }


def gather_facts(
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    bg: int = 0
) -> Tuple[    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],    Dict[int, List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]]]]:
    """
    Returns:
      1) facts_5_nbrs_ticked: 5-neighbor mask facts + center-variant
      2) facts_without_orphan
      3) facts_without_border
      4) facts_without_outside
      5) final_facts
      6) facts_by_train
    """
    # 3×3 offsets
    offs = [(-1,-1),(0,-1),(1,-1),
            (-1, 0),(0, 0),(1, 0),
            (-1, 1),(0, 1),(1, 1)]
    # eight 5-neighbor masks
    masks = [
      [[1,1,1],[1,1,1],[0,0,0]],
      [[1,1,1],[0,1,1],[0,0,1]],
      [[0,1,1],[0,1,1],[0,1,1]],
      [[0,0,1],[0,1,1],[1,1,1]],
      [[0,0,0],[1,1,1],[1,1,1]],
      [[1,0,0],[1,1,0],[1,1,1]],
      [[1,1,0],[1,1,0],[1,1,0]],
      [[1,1,1],[1,1,0],[1,0,0]],
    ]

    facts_5_nbrs_ticked: List[Dict[str, Tuple]] = []

    # --- build facts_5_nbrs_ticked ---
    for t_idx, (inp, out) in enumerate(trains, start=1):
        H, W = len(inp), len(inp[0])
        for y in range(H):
            for x in range(W):
                if inp[y][x] == out[y][x]:
                    continue
                for mask in masks:
                    # 1) mask-only
                    nin, nout = [], []
                    for (dx, dy), mrow in zip(offs, [mask[dy+1][dx+1] for dx,dy in offs]):
                        if mrow == 1:
                            if 0 <= y+dy < H and 0 <= x+dx < W:
                                nin.append(inp[y+dy][x+dx])
                                nout.append(out[y+dy][x+dx])
                            else:
                                nin.append(-2); nout.append(-2)
                        else:
                            nin.append(None); nout.append(None)
                    facts_5_nbrs_ticked.append({'nbr_in':tuple(nin),'nbr_out':tuple(nout)})

                    # 2) all→out except center
                    nin2, nout2 = [], []
                    for i, ((dx, dy), mrow) in enumerate(zip(offs, [mask[dy+1][dx+1] for dx,dy in offs])):
                        if mrow == 1:
                            if i==4:
                                # center stays old input
                                nin2.append(inp[y][x])
                            else:
                                if 0 <= y+dy < H and 0 <= x+dx < W:
                                    nin2.append(out[y+dy][x+dx])
                                else:
                                    nin2.append(-2)
                            # always output
                            if 0 <= y+dy < H and 0 <= x+dx < W:
                                nout2.append(out[y+dy][x+dx])
                            else:
                                nout2.append(-2)
                        else:
                            nin2.append(None); nout2.append(None)
                    facts_5_nbrs_ticked.append({'nbr_in':tuple(nin2),'nbr_out':tuple(nout2)})

    # --- now original gather_facts pipeline ---

    # 1) collect raw_facts with -2 padding
    raw_facts = []
    for t_idx, (inp, out) in enumerate(trains, start=1):
        H, W = len(inp), len(inp[0])
        def extract(cx: int, cy: int):
            in_vals, out_vals = [], []
            for dx, dy in offs:
                x2, y2 = cx + dx, cy + dy
                if 0 <= y2 < H and 0 <= x2 < W:
                    in_vals.append(inp[y2][x2])
                    out_vals.append(out[y2][x2])
                else:
                    in_vals.append(-2)
                    out_vals.append(-2)
            return tuple(in_vals), tuple(out_vals)

    for t_idx, (inp, out) in enumerate(trains, start=1):
        H, W = len(inp), len(inp[0])
        for y in range(H):
            for x in range(W):
                nin, nout = extract(x, y)
                if nin != nout and not (inp[y][x] == bg and out[y][x] == bg):
                    raw_facts.append({
                        'train_idx': t_idx,
                        'center': (x, y),
                        'nbr_in': nin,
                        'nbr_out': nout
                    })
                for dx, dy in offs:
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < W and 0 <= ny < H):
                        continue
                    if inp[ny][nx] == bg:
                        continue
                    nin2, nout2 = extract(nx, ny)
                    if nin2 != nout2:
                        raw_facts.append({
                            'train_idx': t_idx,
                            'center': (nx, ny),
                            'nbr_in': nin2,
                            'nbr_out': nout2
                        })

    # 2) group by (nbr_in, nbr_out)
    raw_by_fact = defaultdict(list)
    for f in raw_facts:
        key = (f['nbr_in'], f['nbr_out'])
        raw_by_fact[key].append(f)

    # 3) filter unique facts (your existing logic)
    final_facts = []
    for (nin, nout), instances in raw_by_fact.items():
        center_color = nin[4]
        if center_color == bg:
            final_facts.append({'nbr_in': nin, 'nbr_out': nout})
            continue

        keep = False
        for inst in instances:
            cx, cy = inst['center']
            union_other = set()
            for (on, _), others in raw_by_fact.items():
                if on[4] in (center_color, bg):
                    continue
                for other in others:
                    ox, oy = other['center']
                    if abs(ox - cx) <= 1 and abs(oy - cy) <= 1:
                        continue
                    for i, (dx, dy) in enumerate(offs):
                        if other['nbr_in'][i] != other['nbr_out'][i]:
                            union_other.add((ox + dx, oy + dy))

            changed = [
                (cx + offs[i][0], cy + offs[i][1])
                for i in range(9) if nin[i] != nout[i]
            ]
            if any(pos not in union_other for pos in changed):
                keep = True
                break

        if keep:
            final_facts.append({'nbr_in': nin, 'nbr_out': nout})

    # 4) build facts_by_train
    facts_by_train: Dict[int, List[Dict]] = {i: [] for i in range(1, len(trains) + 1)}
    for fact in final_facts:
        key = (fact['nbr_in'], fact['nbr_out'])
        for inst in raw_by_fact[key]:
            facts_by_train[inst['train_idx']].append(fact)

    # 5) facts_without_orphan: patterns with >1 raw occurrence
    facts_without_orphan = [
        fact for fact in final_facts
        if len(raw_by_fact[(fact['nbr_in'], fact['nbr_out'])]) > 1
    ]

    # 6) facts_without_border
    facts_without_border = []
    for fact in final_facts:
        instances = raw_by_fact[(fact['nbr_in'], fact['nbr_out'])]
        interior = True
        for inst in instances:
            x, y = inst['center']
            inp, _ = trains[inst['train_idx'] - 1]
            H, W = len(inp), len(inp[0])
            if x == 0 or y == 0 or x == W - 1 or y == H - 1:
                interior = False
                break
        if interior:
            facts_without_border.append(fact)
    facts_without_border = [
        fact for fact in facts_without_border
        if len(raw_by_fact[(fact['nbr_in'], fact['nbr_out'])]) > 1
    ]

    # 7) facts_without_outside
    facts_without_outside = [
        {
            'nbr_in':  tuple(bg if v == -2 else v for v in fact['nbr_in']),
            'nbr_out': tuple(bg if v == -2 else v for v in fact['nbr_out'])
        }
        for fact in final_facts
    ]

    # 8) dedupe helper
    def dedupe(facts: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for f in facts:
            key = (f['nbr_in'], f['nbr_out'])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    return (
        dedupe(facts_5_nbrs_ticked),
        dedupe(facts_without_orphan),
        dedupe(facts_without_border),
        dedupe(facts_without_outside),
        dedupe(final_facts),
        facts_by_train
    )


def detect_and_insert_ca_pipeline(
    conn: sqlite3.Connection,
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    tests: List[List[List[int]]],
    bg: int = 0,
    tick: int = 0,
    prev_post: Optional[List[Tuple[int,int,int,Tuple[int,...],Dict[str,Tuple],bool]]] = None
) -> bool:
    """
    Pipeline with robust rotational alignment based on neighbor‐color positions.

    Arguments:
      conn            -- SQLite connection
      trains          -- list of (input_grid, expected_output) pairs
      tests           -- list of test grids
      bg              -- background color ID
      tick            -- recursion depth / rule version
      prev_post       -- previously inserted/merged rules (to accumulate)

    Returns:
      True if at least one rule was inserted; False otherwise
    """
    # ── 1) Gather 3×3 facts from the current trains
    facts_5_nbrs_ticked, facts_without_orphan, facts_without_border, facts_without_outside, final_facts, facts_by_train = gather_facts(trains, bg)

    #print("5-Nbrs-Ticked Facts (nbr_in -> nbr_out):")
    #for idx, fact in enumerate(facts_5_nbrs_ticked, start=1):
    #    in_vals = fact['nbr_in']
    #    out_vals = fact['nbr_out']
    #    print(f" Fact #{idx:>3}:")
    #    print(f"   nbr_in : {in_vals}")
    #    print(f"   nbr_out: {out_vals}")

    # ── 2) Compute color sets for duplication logic
    color_sets = compute_color_sets(trains, tests, facts_by_train, bg)

    # ── 3) Generate candidate rule‐sets
    post_5_nbrs_ticked   = generate_rules_simple(bg, facts_5_nbrs_ticked, tick)
    post_forced_rot  = generate_rules_to_insert(bg, facts_without_orphan, tick, 1)
    post_wo_border   = generate_rules_to_insert(bg, facts_without_border, tick)
    post_wo_outside  = generate_rules_to_insert(bg, facts_without_outside, tick)
    post_final       = generate_rules_to_insert(bg, final_facts, tick)

    # ── 4) Test each set on all trains
    post_5_nbrs_ticked   = test_each_rule_one_by_one(post_5_nbrs_ticked,   trains, bg)
    post_forced_rot  = test_each_rule_one_by_one(post_forced_rot,  trains, bg)
    post_wo_border   = test_each_rule_one_by_one(post_wo_border,   trains, bg)
    post_wo_outside  = test_each_rule_one_by_one(post_wo_outside,  trains, bg)
    post_final       = test_each_rule_one_by_one(post_final,       trains, bg)

    ## ── Nicely print the filtered 5-nbrs-ticked rules ─────────────────────
    #print("\nPost 5-Nbrs-Ticked Rules to Insert:")
    #for idx, (c0, c1, col, sk, fact, is_rot) in enumerate(post_5_nbrs_ticked, start=1):
    #    tag = "rotational" if is_rot else "non-rotational"
    #    print(f" Rule #{idx:>3}: Center {c0}→{c1} | neighbor {col} | {tag}")
    #    print(f"    struct : {sk}")
    #    print(f"    nbr_in : {fact['nbr_in']}")
    #    print(f"    nbr_out: {fact['nbr_out']}")

    # ── 5) Pick the best rule‐set via try_differents_set_of_rules
    new_post, info = try_differents_set_of_rules(bg, post_wo_border,  trains, tick)
    if not new_post:
        new_post, info = try_differents_set_of_rules(bg, post_wo_outside, trains, tick)
    if not new_post:
        new_post, info = try_differents_set_of_rules(bg, post_forced_rot, trains, tick)
    if not new_post:
        new_post, info = try_differents_set_of_rules(bg, post_final,      trains, tick)

    #tick = 1
    #all = post_final + post_5_nbrs_ticked
    #new_post, info = try_differents_set_of_rules(bg, post_final, trains, tick)

    #exit(0)

    #new_post, info = try_differents_set_of_rules(bg, post_forced_rot, trains, tick)

    # use the found new_post or fall back to post_final
    post = new_post or post_final

    # ── 5a) Attach current tick to each rule entry
    post = [
        (c0, c1, col, sk, fact, is_rot, tick)
        for (c0, c1, col, sk, fact, is_rot, ptick) in post
    ]

    # ── 6) Merge with any previous posts to accumulate
    if prev_post:
        merged = []
        seen = set()
        for entry in prev_post + post:
            key = (
                entry[0], entry[1], entry[2], entry[3],
                entry[4]['nbr_in'], entry[4]['nbr_out'], entry[5], entry[6]
            )
            if key not in seen:
                seen.add(key)
                merged.append(entry)
        post = merged

    # ── 7) If no new rules but we got train_results, recurse with updated inputs
    if not new_post and info.get('train_results') is not None and tick < 10 and len(info.get('colors_unexpected')) == 0:
        new_inputs = info['train_results']
        orig_inputs = [inp for inp, _ in trains]
        if new_inputs == orig_inputs:
            print("↻ No change in CA outputs; stopping recursion.")
            return False

        new_trains = [(new_inputs[i], trains[i][1]) for i in range(len(trains))]
        print(f"↻ Recursing to tick {tick+1} with updated train inputs…")
        return detect_and_insert_ca_pipeline(
            conn,
            new_trains,
            tests,
            bg,
            tick + 1,
            prev_post=post
        )

    # ── 8) If still no new_post, abort
    if not new_post:
        print("✗ No CA rule‐set perfectly covers all trains; aborting.")
        return False

    if tick > 0:
        post_5_nbrs_ticked = [
            (c0, c1, col, sk, fact, is_rot, tick+1)
            for (c0, c1, col, sk, fact, is_rot, ptick) in post_5_nbrs_ticked
        ]
        post = post + post_5_nbrs_ticked

    # ── 9) Duplicate rules for missing colors if needed
    diff_cols = color_sets.get('differentColorsForAll', set())
    newColorsByTest = color_sets.get('newColorsByTest', {})
    sameByTrain = color_sets.get('centerFactColorsSameByTrain', False)
    if newColorsByTest and not sameByTrain:
        print("[ newColorsByTest and not sameByTrain ]")
        present = {c0 for c0, *_ in post} | {c1 for _, c1, *_ in post}
        missing = diff_cols - present
        new_entries = []
        for new_col in missing:
            for c0, c1, col, sk, fact, is_rot, ptick in post:
                if c0 in diff_cols or c1 in diff_cols:
                    nc0 = new_col if c0 in diff_cols else c0
                    nc1 = new_col if c1 in diff_cols else c1
                    nin = tuple(new_col if v in diff_cols else v for v in fact['nbr_in'])
                    nout = tuple(new_col if v in diff_cols else v for v in fact['nbr_out'])
                    new_entries.append((nc0, nc1, col, sk, {'nbr_in': nin, 'nbr_out': nout}, is_rot, ptick))
        print(f"Added {len(new_entries)} rules for missing colors")
        post.extend(new_entries)
#
    # ── 10) Final deduplication
    unique_post = []
    seen_keys = set()
    for e in post:
        key = (e[0], e[1], e[2], e[3], tuple(e[4]['nbr_in']), tuple(e[4]['nbr_out']), e[5])
        if key not in seen_keys:
            seen_keys.add(key)
            unique_post.append(e)
    post = unique_post
    print(f"After duplication/dedupe: {len(post)} rules remain")

    # ── 11) Insert into DB
    flatten_order = [(-1,-1),(0,-1),(1,-1),(-1,0),(0,0),(1,0),(-1,1),(0,1),(1,1)]
    cur = conn.cursor()
    for entry in post:
        c0, c1, col, sk, fact, is_rot, ptick = entry
        cur.execute(
            """
            INSERT INTO cellular_automaton
              (input_color, output_color, neighbor_count, wildcard_colors, tick)
            VALUES (?,?,?,?,?);
            """,
            (c0, c1, len(sk), json.dumps([]), ptick)
        )
        rid = cur.lastrowid
        for idx, inp_col in enumerate(fact['nbr_in']):
            dx, dy = flatten_order[idx]
            out_col = fact['nbr_out'][idx]
            cur.execute(
                """
                INSERT INTO cellular_automaton_cells
                  (rule_id, posRelX, posRelY, color, output)
                VALUES (?,?,?,?,?);
                """,
                (rid, dx, dy, inp_col, out_col)
            )
    conn.commit()
    return bool(post)

def generate_rules_simple(bg, facts, tick):
    """
    Generate one non-rotational rule per raw fact without modifying neighborhoods.

    Args:
        bg: background color
        facts: list of dicts with 'nbr_in' and 'nbr_out' tuples

    Returns:
        List of rules (c0, c1, col, struct_key, fact, is_rot=False)
    """
    post = []
    for fact in facts:
        nin = fact['nbr_in']
        nout = fact['nbr_out']
        c0 = nin[4]
        c1 = nout[4]
        # skip trivial background transitions
        if c0 == c1 == bg:
            continue
        # struct_key: all positions where nbr_in is not None (excluding center)
        struct_key = tuple(i for i in range(9) if i != 4 and nin[i] is not None)
        # emit rule for each neighbor color in struct_key
        for col in sorted({nin[i] for i in struct_key}):
            post.append((
                c0,
                c1,
                col,
                struct_key,
                {'nbr_in': nin, 'nbr_out': nout},
                False,  # non-rotational
                tick
            ))
    return post

def group_facts_by_center(
    facts: List[Dict[str, Tuple[Tuple[int,...], Tuple[int,...]]]]
) -> Dict[Tuple[int,int], List[Dict]]:
    """
    Group facts by center color transform (nbr_in[4]→nbr_out[4]).
    """
    groups: Dict[Tuple[int,int], List[Dict]] = defaultdict(list)
    for f in facts:
        c0, c1 = f['nbr_in'][4], f['nbr_out'][4]
        groups[(c0, c1)].append(f)
    return groups

def extract_structure_subgroups(
    facts: List[Dict],
    col: int
) -> Dict[Tuple[int,...], List[Dict]]:
    """
    Group facts by the set of neighbor-offset indices where nbr_in equals col.
    Returns a map: structure_key -> list of facts.
    """
    struct_map: Dict[Tuple[int,...], List[Dict]] = {}
    for f in facts:
        offs = tuple(sorted(
            i for i in range(9)
            if i != 4 and f['nbr_in'][i] == col
        ))
        struct_map.setdefault(offs, []).append(f)
    return struct_map

def rotate90_nosort_struct(struct):
    return tuple(index_map[i] for i in struct)

def rotate90(nbr):
    return tuple(nbr[i] for i in index_map)

def all_struct_rotations_sorted(sk):
    rots = set()
    cur = sk
    for _ in range(4):
        rots.add(cur)
        # rotate then sort
        nosort = rotate90_nosort_struct(cur)
        cur = tuple(sorted(nosort))
    return rots

def align_fact_to_positions(nbr_in, nbr_out, target_color, base_positions):
    """
    Rotate nbr_in/nbr_out in 90° steps until the set of indices in base_positions
    where nbr_in == target_color exactly matches base_positions. Returns aligned pair.
    """
    for _ in range(4):
        # only consider positions within the original base_positions
        positions = [i for i in base_positions if nbr_in[i] == target_color]
        if set(positions) == set(base_positions):
            return nbr_in, nbr_out
        nbr_in = rotate90(nbr_in)
        nbr_out = rotate90(nbr_out)
    # fallback: return last rotation
    return nbr_in, nbr_out

def generate_rules_to_insert(bg, facts, tick, rotation_threshold=3):
    """
    bg: background color
    facts: list of {'nbr_in': tuple, 'nbr_out': tuple, ...}
    rotation_threshold: minimum distinct facts needed to emit 4 rotations
    """
    print("[ generate_rules_to_insert ]")

    # 1) Group by center color transition
    center_groups = group_facts_by_center(facts)
    center_groups.pop((bg, bg), None)

    # 2) Build initial “pre” list by neighbor color & structure
    pre = []
    for (c0, c1), grp in center_groups.items():
        neigh_cols = sorted({f['nbr_in'][i] for f in grp for i in range(9) if i != 4 and f['nbr_in'][i] is not None})
        if len(neigh_cols) == 2 and bg in neigh_cols:
            neigh_cols.remove(bg)
        for col in neigh_cols:
            struct_map = extract_structure_subgroups(grp, col)
            for sk, flist in struct_map.items():
                print(f"Pre Center {c0}->{c1} | neighbor {col} | struct {sk} | facts={len(flist)}")
                pre.append((c0, c1, col, sk, flist))

    # 3) Regroup into rotational families
    grouped_pre = []
    for c0, c1, col, sk, flist in pre:
        placed = False
        for rep_sk, entries in grouped_pre:
            if sk in all_struct_rotations_sorted(rep_sk):
                entries.append((c0, c1, col, sk, flist))
                placed = True
                break
        if not placed:
            grouped_pre.append((sk, [(c0, c1, col, sk, flist)]))

    # 4) Deduplicate each subgroup’s flist
    for rep_sk, entries in grouped_pre:
        for idx, (c0, c1, col, sk, flist) in enumerate(entries):
            seen = set()
            unique = []
            for f in flist:
                key = (f['nbr_in'], f['nbr_out'])
                if key not in seen:
                    seen.add(key)
                    unique.append(f)
            entries[idx] = (c0, c1, col, sk, unique)

    # 5) Merge only truly-observed 3+ rotations
    new_pre = []
    for rep_sk, entries in grouped_pre:
        if len(entries) < 3:
            print(f"Skipping struct {rep_sk}: only {len(entries)} observed variants (need ≥3)")
            continue
        c0, c1, col = entries[0][0], entries[0][1], entries[0][2]
        if col == bg or not rep_sk:
            continue

        merged = [f for *_, fl in entries for f in fl]
        counts = [len(fl) for *_, fl in entries]
        print(f"Merging struct {rep_sk}: {len(entries)} rotations → {len(merged)} facts ({'+'.join(map(str,counts))})")
        new_pre.append((c0, c1, col, rep_sk, merged))

    if new_pre:
        pre.extend(new_pre)
        print(f"  → Added {len(new_pre)} merged entries (pre now {len(pre)})")
    else:
        print("  → No 3-way rotational groups merged; pre unchanged")

    # 6) Collapse & emit rules, using the single rotation_threshold
    post = []
    for c0, c1, col, struct_key, flist in pre:
        # a) dedupe again for distinct facts
        seen = set()
        unique_facts = []
        for f in flist:
            key = (f['nbr_in'], f['nbr_out'])
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)
        print(f"Center {c0}->{c1}, struct {struct_key}: {len(flist)} raw, {len(unique_facts)} unique")

        # b) align & collapse
        base = unique_facts[0]['nbr_in']
        base_pos = [i for i in struct_key if base[i] == col]
        aligned = []
        for f in unique_facts:
            ain, aout = align_fact_to_positions(f['nbr_in'], f['nbr_out'], col, base_pos)
            aligned.append({'nbr_in': ain, 'nbr_out': aout})

        out_i = [i for i in range(9) if len({f['nbr_out'][i] for f in aligned}) == 1]
        in_i  = [i for i in range(9) if len({f['nbr_in'][i]  for f in aligned}) == 1]

        rep = aligned[0]
        in_vals  = list(rep['nbr_in'])
        out_vals = list(rep['nbr_out'])

        for i in range(9):
            if i != 4:
                if i not in in_i:
                    in_vals[i] = None
                if i not in out_i:
                    out_vals[i] = None

        # wildcard bg-only neighbors
        neigh = {in_vals[i] for i in range(9) if i != 4}
        if len(neigh) == 2 and bg in neigh:
            for i in range(9):
                if i != 4 and in_vals[i] == bg:
                    in_vals[i] = None
                    if out_vals[i] == bg:
                        out_vals[i] = None

        # wildcard no-change
        for i in range(9):
            if i != 4 and in_vals[i] is not None and in_vals[i] == out_vals[i]:
                out_vals[i] = None

        collapsed = {'nbr_in': tuple(in_vals), 'nbr_out': tuple(out_vals)}
        print(f"Collapsed fact: nbr_in={collapsed['nbr_in']} nbr_out={collapsed['nbr_out']}")

        # c) emit rotations or single rule based on rotation_threshold
        if len(unique_facts) >= rotation_threshold:
            print(f"Emitting 4 rotation variants for struct {struct_key}")
            nin, nout = collapsed['nbr_in'], collapsed['nbr_out']
            sk = tuple(sorted(out_i))
            for _ in range(4):
                post.append((c0, c1, col, sk, {'nbr_in': nin, 'nbr_out': nout}, True, tick))
                nin  = rotate90(nin)
                nout = rotate90(nout)
                sk    = tuple(sorted(index_map[i] for i in sk))
        else:
            print(f"Emitting single non-rotational rule ({len(unique_facts)} < {rotation_threshold})")
            post.append((c0, c1, col, struct_key, collapsed, False, tick))

    # 7) Final dedupe of all generated rules
    unique, seen = [], set()
    for entry in post:
        key = (
            entry[0], entry[1], entry[2], entry[3],
            entry[4]['nbr_in'], entry[4]['nbr_out'], entry[5]
        )
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    return unique

def build_ca_rule(
        c0: int,
        c1: int,
        fact: Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]
) -> Dict:
    """
    Build a single-CA-rule dict from your collapsed 3×3 fact.
    - c0 is the center input color
    - c1 is the center output color
    - fact['nbr_in'] and fact['nbr_out'] are length-9 tuples (or None)
    """
    nbr_in, nbr_out = fact['nbr_in'], fact['nbr_out']

    # 1) Center
    rule = {
        "input_color": c0,
        # only specify an output_color if it really changes
        "output_color": (c1 if c1 != c0 else None),
        "neighbors": []
    }

    # 2) Every neighbor (and wildcard) at positions ≠ center
    for idx, (dx, dy) in enumerate(flatten_order):
        if idx == 4:
            continue
        in_col = nbr_in[idx]
        out_col = nbr_out[idx]
        # record the input (even if None) and the output (even if None)
        rule["neighbors"].append((dx, dy, in_col, out_col))

    return rule

def test_each_rule_one_by_one(post, trains, bg):
    # ── X) Filter out any rule that, when applied alone, makes changes
    #        not present in the original train outputs ───────────────────────
    print("🔍 Testing each candidate rule on the train examples…")
    # reproduce the exact flatten order you used to build your 3×3 keys:
    flatten_order = [(dx, dy)
                     for dy in (-1, 0, 1)
                     for dx in (-1, 0, 1)]

    def rule_preserves_ground_truth(ca_rule):
        """Return False as soon as the rule makes any unexpected change."""
        for inp_grid, expected_out in trains:
            # apply _only_ this single rule:
            result = apply_ca(inp_grid, [ca_rule], bg)
            H, W = len(inp_grid), len(inp_grid[0])
            for y in range(H):
                for x in range(W):
                    # if the CA changed this cell...
                    if result[y][x] != inp_grid[y][x]:
                        # ...it must exactly match the expected output
                        if result[y][x] != expected_out[y][x]:
                            return False
        return True

    filtered = []
    for (c0, c1, col, sk, fact, is_rot, ptick) in post:
        ca_rule = build_ca_rule(c0, c1, fact)
        print("--- (c0, c1, col, sk, fact, is_rot) ---")
        print((c0, c1, col, sk, fact, is_rot, ptick))
        print("--- ca_rule 4->4 ---")
        print(ca_rule)
        if rule_preserves_ground_truth(ca_rule):
            filtered.append((c0, c1, col, sk, fact, is_rot, ptick))
        else:
            print(f"  ❌ Dropping rule Center {c0}->{c1}, struct {sk}: "
                  "it makes unexpected changes on the trains.")
    post = filtered
    print(f"✅ {len(post)} rules remain after ground-truth filtering.\n")
    return post

def try_differents_set_of_rules(bg, post, trains, tick):
    #ok, info = test_all_rules_on_all_trains(post, trains, bg, tick)
    #if ok:
    #    print(f"✅ post rules cover every train transformation—using them. {tick}")
    #    return post, info
    #else:
    #    print(f"❌ post rules are not sufficient: {tick}")
    #    print("  Missing transformations per train:", info['train_failures'])
    #    print("  Colors missing overall:", info['colors_missing'])
    #    print("  Colors unexpected overall:", info['colors_unexpected'])
    #    print("  Count unicolor_extras:", len(post))
    #return None, info

    # ── 1) Test “orthogonal-only” rules ────────────────────────────────────
    orthogonal_rules = []
    # diagonal indices in a 3×3 patch
    diagonals = (0, 2, 6, 8)

    for (c0, c1, col, sk, fact, is_rot, ptick) in post:
        # copy the 3×3 neighborhood
        nin = list(fact['nbr_in'])
        nout = list(fact['nbr_out'])
        # wildcard all diagonals
        for idx in diagonals:
            nin[idx] = None
            nout[idx] = None
        new_fact = {'nbr_in': tuple(nin), 'nbr_out': tuple(nout)}
        orthogonal_rules.append((c0, c1, col, sk, new_fact, is_rot, ptick))

    ok, info = test_all_rules_on_all_trains(orthogonal_rules, trains, bg, tick)
    if ok:
        print(f"✅ Orthogonal-only rules cover every train transformation—using them. tick {tick}")
        return orthogonal_rules, info
    else:
        print(f"❌ Orthogonal-only rules are not sufficient: {tick}")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count orthogonal_rules:", len(orthogonal_rules))

    # ── 6a) Expand “unicolor” rules ────────────────────────────────────
    unicolor_extras = []
    for (c0, c1, col, sk, fact, is_rot, ptick) in post:
        if c0 == c1:
            # build a wildcarded copy of the 3×3 fact
            nin = list(fact['nbr_in'])
            nout = list(fact['nbr_out'])
            for idx in range(9):
                if idx == 4:
                    continue  # keep center
                # if the neighbor isn’t the center color, wildcard it
                if nin[idx] != c0:
                    nin[idx] = None
                if nout[idx] != c0:
                    nout[idx] = None
            new_fact = {'nbr_in': tuple(nin), 'nbr_out': tuple(nout)}
            # duplicate the rule (keep same c0,c1,sk,is_rot)
            print("duplicate unicolor rule")
            print((c0, c1, col, sk, new_fact, is_rot, ptick))
            unicolor_extras.append((c0, c1, col, sk, new_fact, is_rot, ptick))
    ok, info = test_all_rules_on_all_trains(unicolor_extras, trains, bg, tick)
    if ok:
        print(f"✅ Unicolor rules alone cover every train transformation—using them. {tick}")
        return unicolor_extras, info
    else:
        print(f"❌ Unicolor rules are not sufficient: {tick}")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(unicolor_extras))
        print(unicolor_extras)

    fixed_center = []
    for (c0, c1, col, sk, fact, is_rot, ptick) in post:
        if c0 == c1:
            fixed_center.append((c0, c1, col, sk, fact, is_rot, ptick))
    ok, info = test_all_rules_on_all_trains(fixed_center, trains, bg, tick)
    if ok:
        print(f"✅ fixed_center rules alone cover every train transformation—using them. {tick}")
        return fixed_center, info
    else:
        print(f"❌ fixed_center rules are not sufficient: {tick}")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(fixed_center))
        print(fixed_center)

    all = post + unicolor_extras
    ok, info = test_all_rules_on_all_trains(all, trains, bg, tick)
    if ok:
        print(f"✅ all (post + unicolor_extras) rules cover every train transformation—using them. {tick}")
        return all, info
    else:
        print(f"❌ all (post + unicolor_extras) rules are not sufficient: {tick}")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(all))

    ok, info = test_all_rules_on_all_trains(post, trains, bg, tick)
    if ok:
        print(f"✅ post rules cover every train transformation—using them. {tick}")
        return post, info
    else:
        print(f"❌ post rules are not sufficient: {tick}")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(post))

    return None, info

def test_all_rules_on_all_trains(
    post: List[Tuple[int,int,int,Tuple[int,...],Dict[str,Tuple],bool,int]],
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    bg: int,
    tick: int = 0
) -> Tuple[bool, Dict[str, Any]]:
    """
    Apply the ENTIRE set of rules (post) to each train input:
      - if tick == 0: exactly one pass of apply_ca;
      - if tick  > 0: keep applying until stable (no further change).
    Compare final result to expected_out. Return (True, {}) if perfect;
    otherwise (False, info) where info includes train_results, failures, etc.
    """
    # build CA-rule objects
    ca_rules = [
        build_ca_rule(c0, c1, fact)
        for (c0, c1, col, sk, fact, is_rot, ptick) in post
    ]

    failures = []
    all_missing = set()
    all_unexpected = set()
    all_results = []

    for t_idx, (inp_grid, expected_out) in enumerate(trains):
        # decide how to iterate
        if tick > 0:
            prev = inp_grid
            indice = 0
            while True:
                indice = indice + 1
                curr = apply_ca(prev, ca_rules, bg)
                if curr == prev:
                    #print(ca_rules)
                    print(f"curr = apply_ca(prev, ca_rules, bg) indice: {indice}, tick: {tick}")
                    break
                prev = curr
            result = curr
        else:
            # single pass
            result = apply_ca(inp_grid, ca_rules, bg)

        all_results.append(result)

        H, W = len(result), len(result[0])
        missing = []
        unexpected = []

        for y in range(H):
            for x in range(W):
                orig = inp_grid[y][x]
                res  = result[y][x]
                exp  = expected_out[y][x]
                if res != exp:
                    if res == orig:
                        missing.append((x, y, exp))
                        all_missing.add(exp)
                    else:
                        unexpected.append((x, y, res))
                        all_unexpected.add(res)

        if missing or unexpected:
            failures.append({
                'train_index': t_idx,
                'missing':     missing,
                'unexpected':  unexpected
            })

    if failures:
        return False, {
            'train_failures':    failures,
            'colors_missing':    all_missing,
            'colors_unexpected': all_unexpected,
            'train_results':     all_results
        }

    return True, {}

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

    db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "database.db"))
    print(f"📦 Using database at: {db}")
    conn = sqlite3.connect(db)

    conn.execute("DELETE FROM cellular_automaton;")
    conn.execute("DELETE FROM cellular_automaton_cells;")
    conn.commit()
    print("🧹 Cleared existing CA rules from database")

    success = detect_and_insert_ca_pipeline(conn, trains, tests, bg=0)
    print("Pipeline success?", success)

    conn.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Detect & store cellular automaton rules.")
    p.add_argument("json_input", help="ARC JSON file or raw JSON if --inline")
    p.add_argument("--inline", action="store_true", help="Raw JSON mode")
    p.add_argument("--name", type=str, help="Override filename/task_id")
    args = p.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)
