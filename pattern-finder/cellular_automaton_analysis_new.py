import os
from typing import List, Dict, Tuple, Set, Callable, Any
from collections import defaultdict, Counter, OrderedDict
import json
import sqlite3

# reproduce the exact flatten order you used for single-rule tests:
flatten_order = [(dx, dy)
                 for dy in (-1, 0, 1)
                 for dx in (-1, 0, 1)]

# from constelize.dsl.grid_dsl import apply_ca




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
) -> Tuple[
    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  # facts_without_orphan
    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  # facts_without_border
    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  # facts_without_outside
    List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  # final_facts
    Dict[int, List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]]]  # facts_by_train
]:
    """
    Returns:
      - facts_without_orphan: final_facts whose pattern occurred >1 time
      - facts_without_border: final_facts whose center isn't on grid border
      - facts_without_outside: final_facts with all -2 replaced by bg
      - final_facts: the filtered facts, possibly containing -2 and border ones
      - facts_by_train: mapping train_idx -> list of final_facts dicts
    """
    offs = [(-1, -1), (0, -1), (1, -1),
            (-1,  0), (0,  0), (1,  0),
            (-1,  1), (0,  1), (1,  1)]

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
        dedupe(facts_without_orphan),
        dedupe(facts_without_border),
        dedupe(facts_without_outside),
        dedupe(final_facts),
        facts_by_train
    )

def gather_facts_old(
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    bg: int = 0
) -> Tuple[List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]],  Dict[int, List[Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]]]]]:
    """
    Returns:
      - facts_without_border: final_facts whose center isn't on grid border
      - facts_without_outside: final_facts with all -2 replaced by bg
      - final_facts: the filtered facts, possibly containing -2 and border ones
      - facts_by_train: mapping train_idx -> list of final_facts dicts
    """
    offs = [(-1, -1), (0, -1), (1, -1),
            (-1,  0), (0,  0), (1,  0),
            (-1,  1), (0,  1), (1,  1)]

    # 1) collect raw_facts with bg padding
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
                    # outside pixel marker
                    in_vals.append(-2)
                    out_vals.append(-2)
            return tuple(in_vals), tuple(out_vals)

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

    # 3) group by (nbr_in, nbr_out)
    raw_by_fact = defaultdict(list)
    for f in raw_facts:
        key = (f['nbr_in'], f['nbr_out'])
        raw_by_fact[key].append(f)

    # 4) filter unique facts (rotational logic, etc.)
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
                            union_other.add((ox+dx, oy+dy))

            changed = [
                (cx + offs[i][0], cy + offs[i][1])
                for i in range(9) if nin[i] != nout[i]
            ]
            if any(pos not in union_other for pos in changed):
                keep = True
                break

        if keep:
            final_facts.append({'nbr_in': nin, 'nbr_out': nout})

    # 5) build facts_by_train from final_facts
    facts_by_train: Dict[int, List[Dict]] = {i: [] for i in range(1, len(trains)+1)}
    for fact in final_facts:
        key = (fact['nbr_in'], fact['nbr_out'])
        for inst in raw_by_fact[key]:
            facts_by_train[inst['train_idx']].append(fact)

    # 6) compute facts_without_border
    facts_without_border = []
    for fact in final_facts:
        # pick any instance to test center coords
        instances = raw_by_fact[(fact['nbr_in'], fact['nbr_out'])]
        # if all instances' center are interior, keep
        interior = True
        for inst in instances:
            x,y = inst['center']
            inp,_ = trains[inst['train_idx']-1]
            H, W = len(inp), len(inp[0])
            if x==0 or y==0 or x==W-1 or y==H-1:
                interior = False
                break
        if interior:
            facts_without_border.append(fact)

    # 7) compute facts_without_outside
    facts_without_outside = []
    for fact in final_facts:
        nin = tuple(bg if v==-2 else v for v in fact['nbr_in'])
        nout= tuple(bg if v==-2 else v for v in fact['nbr_out'])
        facts_without_outside.append({'nbr_in': nin, 'nbr_out': nout})

    return facts_without_border, facts_without_outside, final_facts, facts_by_train

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

def apply_ca(
    input_grid: List[List[int]],
    ca_rules: List[Dict],
    bg: int = 0
) -> List[List[int]]:
    import pprint
    from typing import Tuple, Dict, List

    idx_map = {
        (-1, -1): 0, (0, -1): 1, (1, -1): 2,
        (-1,  0): 3, (0,  0): 4, (1,  0): 5,
        (-1,  1): 6, (0,  1): 7, (1,  1): 8,
    }
    offs = list(idx_map.keys())

    H, W = len(input_grid), len(input_grid[0])
    print(f"⚙️ Starting apply_ca on grid {H}×{W} with {len(ca_rules)} rules, bg={bg}")

    # ── Detect if any rule actually uses -2 as a neighborhood value ──
    use_border_marker = False
    for rule in ca_rules:
        if rule.get("input_color") == -2:
            use_border_marker = True
            break
        for dx, dy, color, _ in rule["neighbors"]:
            if color == -2:
                use_border_marker = True
                break
        if use_border_marker:
            break

    pad_value = -2 if use_border_marker else bg
    if use_border_marker:
        print("Detected -2 in rules → padding out‐of‐bounds with -2")
    else:
        print("No -2 in rules → padding out‐of‐bounds with bg")

    # 1) Build rule_map exactly as before (still using bg!)
    rule_map: Dict[Tuple[int,...], List[Tuple[int,int,int]]] = {}
    for idx, rule in enumerate(ca_rules):
        nbr = [bg] * 9
        nbr[4] = rule["input_color"]
        for dx, dy, color, _ in rule["neighbors"]:
            nbr[idx_map[(dx,dy)]] = color
        key = tuple(nbr)

        # collect outputs
        outputs = []
        oc = rule.get("output_color")
        ic = rule["input_color"]
        if oc is not None and oc != ic:
            outputs.append((0, 0, oc))
        for dx, dy, _, out in rule["neighbors"]:
            if out is not None and not (dx == 0 and dy == 0):
                outputs.append((dx, dy, out))

        # dedupe
        seen = set(); deduped = []
        for dx, dy, c in outputs:
            if (dx,dy,c) not in seen:
                seen.add((dx,dy,c))
                deduped.append((dx,dy,c))

        rule_map[key] = deduped
        print(f"Rule #{idx}: key={key} -> outputs={deduped}")

    # 2) Prepare result grid
    result = [row.copy() for row in input_grid]
    print("🔍 Rule map built. Beginning grid scan...")

    # 3) extract uses pad_value
    def extract(x: int, y: int) -> Tuple[int,...]:
        vals = []
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                xi, yi = x + dx, y + dy
                if 0 <= xi < W and 0 <= yi < H:
                    vals.append(input_grid[yi][xi])
                else:
                    vals.append(pad_value)
        return tuple(vals)

    # 4) match & apply
    def matches(rule_key: Tuple[int,...], block: Tuple[int,...]) -> bool:
        for rk, bk in zip(rule_key, block):
            if rk is None: continue
            if rk != bk: return False
        return True

    for y in range(H):
        for x in range(W):
            block = extract(x, y)
            for key, updates in rule_map.items():
                if matches(key, block):
                    print(f"  Matched {key} at ({x},{y}), updates={updates}")
                    for dx, dy, new in updates:
                        tx, ty = x+dx, y+dy
                        if 0 <= tx < W and 0 <= ty < H:
                            old = result[ty][tx]
                            result[ty][tx] = new
                            print(f"    ({tx},{ty}): {old}→{new}")
                        else:
                            print(f"    skip out‐of‐bounds update at ({tx},{ty})")
                    break

    print("✅ Finished apply_ca; final grid:")
    for row in result:
        print(row)
    return result

def apply_ca_old(
    input_grid: List[List[int]],
    ca_rules: List[Dict],
    bg: int = 0
) -> List[List[int]]:
    """
    Apply CA rules by exact 3×3 neighborhood match in verbose mode.
    Each rule may specify:
      - a center-pixel change via rule["output_color"]
      - any number of neighbor-pixel changes via rule["neighbors"], each (dx,dy,color,out).

    This function prints detailed logs of:
      1) Rule map construction,
      2) Grid scanning,
      3) Neighborhood matching,
      4) Individual pixel updates,
      5) Final resulting grid.
    """
    # Imports
    import pprint

    # Map relative positions to flat index in 3×3 tuple
    idx_map = {
        (-1, -1): 0, (0, -1): 1, (1, -1): 2,
        (-1,  0): 3, (0,  0): 4, (1,  0): 5,
        (-1,  1): 6, (0,  1): 7, (1,  1): 8,
    }

    H, W = len(input_grid), len(input_grid[0])
    print(f"⚙️ Starting apply_ca on grid {H}×{W} with {len(ca_rules)} rules, bg={bg}")

    # 1) Build rule_map: 3×3 input tuple -> list of (dx,dy,new_color)
    rule_map: Dict[Tuple[int,...], List[Tuple[int,int,int]]] = {}
    for idx, rule in enumerate(ca_rules):
        # Build neighborhood key
        nbr = [bg] * 9
        nbr[4] = rule['input_color']
        for dx, dy, color, _ in rule['neighbors']:
            pos = idx_map[(dx,dy)]
            nbr[pos] = color
        key = tuple(nbr)
        # Collect outputs
        outputs: List[Tuple[int,int,int]] = []
        # Center update
        oc = rule.get('output_color')
        ic = rule['input_color']
        if oc is not None and oc != ic:
            outputs.append((0, 0, oc))
        # Neighbor updates
        for dx, dy, _, out in rule['neighbors']:
            if out is not None and not (dx == 0 and dy == 0):
                outputs.append((dx, dy, out))
        # Deduplicate duplicates
        seen = set(); deduped = []
        for dx, dy, c in outputs:
            if (dx,dy,c) not in seen:
                seen.add((dx,dy,c)); deduped.append((dx,dy,c))
        rule_map[key] = deduped
        print(f"Rule #{idx}: key={key}")
        print(f"  -> outputs: {deduped}")

    # 2) Prepare result grid
    result = [row.copy() for row in input_grid]
    print("🔍 Rule map built. Beginning grid scan...")

    # Helper to extract 3×3 tuple at (x,y)
    def extract(x: int, y: int) -> Tuple[int,...]:
        vals = []
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                xi, yi = x + dx, y + dy
                if 0 <= xi < W and 0 <= yi < H:
                    vals.append(input_grid[yi][xi])
                else:
                    vals.append(bg)
        return tuple(vals)

    # 3) Scan and apply with wildcard support for None in rule keys
    def matches(rule_key: Tuple[int,...], block: Tuple[int,...]) -> bool:
        # None in rule_key acts as wildcard matching any input
        for rk, bk in zip(rule_key, block):
            if rk is None:
                continue
            if rk != bk:
                return False
        return True

    for y in range(H):
        for x in range(W):
            block = extract(x, y)
            #print(f"Checking cell ({x},{y}): neighborhood= {block}")
            # find first matching rule key (with wildcards)
            matched_updates = None
            matched_key = None
            for key, updates in rule_map.items():
                if matches(key, block):
                    matched_key = key
                    matched_updates = updates
                    break
            if matched_updates is None:
                #print("  No matching rule (even with wildcards).")
                continue
            print(f"  Matched rule key={matched_key} with {len(matched_updates)} updates: {matched_updates}")
            for dx, dy, new_color in matched_updates:
                tx, ty = x + dx, y + dy
                if 0 <= tx < W and 0 <= ty < H:
                    old = result[ty][tx]
                    result[ty][tx] = new_color
                    print(f"    -> updating result[{tx},{ty}]: {old} -> {new_color}")
                else:
                    print(f"    -> skip out-of-bounds ({tx},{ty})")

    # 4) Done
    print("✅ Finished apply_ca; final grid:")
    for row in result:
        print(row)
    return result

# ── Helpers ────────────────────────────────────────────────────────────
index_map = [6,3,0,7,4,1,8,5,2]

def rotate90(nbr):
    return tuple(nbr[i] for i in index_map)

# ── 4,5) helper: all rotations of a struct_key
def rotate90_nosort_struct(struct):
    return tuple(index_map[i] for i in struct)

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


def detect_and_insert_ca_pipeline(
    conn: sqlite3.Connection,
    trains: List[Tuple[List[List[int]], List[List[int]]]],
    tests: List[List[List[int]]],
    bg: int = 0
) -> bool:
    """
    Pipeline with robust rotational alignment based on target neighbor color positions.

    Steps:
    1) Gather 3×3 facts from trains.
    2) Group facts by center input→output color.
    3) Filter to groups with >1 fact.
    4) Subgroup each by targeted neighbor color.
    5) For each subgroup:
       - Identify base_positions from first fact's neighbor color indices.
       - Align all facts so those positions match via rotate90.
       - Intersect outputs on surviving offsets; collapse variations to None.
       - Generate 4 rotational variants of collapsed fact.
       - Log each step clearly.
    6) Insert all resulting facts into the DB as separate rules.
    """

    # ── 1) Gather facts
    facts_without_orphan, facts_without_border, facts_without_outside, final_facts, facts_by_train = gather_facts(trains, bg)

    facts = final_facts
    print("facts")
    print(facts)
    print("facts_by_train")
    print(facts_by_train)

    #exit(0)

    color_sets = compute_color_sets(trains, tests, facts_by_train, bg)

    print("color_sets")
    print(color_sets)

    post_without_orphan = generate_rules_to_insert(bg, facts_without_orphan)

    exit(0)

    post_without_border = generate_rules_to_insert(bg, facts_without_border)
    post_without_outside = generate_rules_to_insert(bg, facts_without_outside)
    post = generate_rules_to_insert(bg, final_facts)

    post_without_border = test_each_rule_one_by_one(post_without_border, trains, bg)
    post_without_outside = test_each_rule_one_by_one(post_without_outside, trains, bg)
    post = test_each_rule_one_by_one(post, trains, bg)

    # ──────────────────────────────────────
    new_post = try_differents_set_of_rules(bg, post_without_orphan, trains)
    print("post_without_orphan done !")
    if not new_post:
        print("post_without_outside failed")
        new_post = try_differents_set_of_rules(bg, post_without_border, trains)
        print("post post_without_border !")
    if not new_post:
        print("post_without_orphan failed")
        new_post = try_differents_set_of_rules(bg, post_without_outside, trains)
        print("post post_without_outside !")
    if not new_post:
        print("post_without_border failed")
        new_post = try_differents_set_of_rules(bg, post, trains)
        print("post done !")
    if not new_post:
        print("post failed")
        new_post = post
        print("go back to post")
    post = new_post

    #new_post = try_differents_set_of_rules(bg, post_without_orphan, trains)
    #print("post_without_orphan done !")
    #if not new_post:
    #   print("post_without_orphan failed")
    #new_post = post_without_orphan

    print(len(post_without_orphan))
    print(len(post_without_border))
    print(len(post_without_outside))
    print(len(post))

    #exit(0)

    # ── 6) List final rules ───────────────────────────────────────────────
    print("Final rules to insert:")
    for c0, c1, col, sk, fact, is_rot in post:
        tag = "rotational" if is_rot else "non-rotational"
        print(f"Center {c0}->{c1} | neighbor {col} | {tag} | struct {sk} | fact: nbr_in={fact['nbr_in']} nbr_out={fact['nbr_out']}")

    #exit(0)

    # 6b) If there are any “different” colors, duplicate rules for the missing ones
    diff_cols = color_sets['differentColorsForAll']
    newColorsByTest = color_sets['newColorsByTest']
    centerFactColorsSameByTrain = color_sets['centerFactColorsSameByTrain']
    if newColorsByTest and centerFactColorsSameByTrain == False:
        print("DifferentColorsForAll:", diff_cols)
        # which diff_cols already appear in our c0 or c1?
        present = {c0 for c0, _, _, _, _, _ in post} | {c1 for _, c1, _, _, _, _ in post}
        missing = diff_cols - present
        print("Missing colors that need rule copies:", missing)

        new_entries = []
        for new_col in missing:
            for c0, c1, col, sk, fact, is_rot in post:
                # only copy rules that touch any diff_col
                if c0 in diff_cols or c1 in diff_cols:
                    nc0 = new_col if c0 in diff_cols else c0
                    nc1 = new_col if c1 in diff_cols else c1
                    # neighbor‐color (`col`) stays the same
                    # remap the 9‐tuple facts: replace old diff_cols → new_col
                    nin = tuple(new_col if v in diff_cols else v for v in fact['nbr_in'])
                    nout = tuple(new_col if v in diff_cols else v for v in fact['nbr_out'])
                    new_entries.append((nc0, nc1, col, sk, {'nbr_in': nin, 'nbr_out': nout}, is_rot))
        print(f"Generated {len(new_entries)} additional rules for missing colors")
        post.extend(new_entries)

    # 6c) Now dedupe exactly as before
    unique = []
    seen = set()
    for e in post:
        key = (e[0], e[1], e[2], e[3], e[4]['nbr_in'], e[4]['nbr_out'], e[5])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    post = unique
    print(f"After color‐duplication and dedupe, {len(post)} rules remain")

    #post = test_each_rule_one_by_one(post, trains, bg)

    # ── 7) Insert into DB ────────────────────────────────────────────────
    cur = conn.cursor()

    # flatten_order[0] == (-1,-1), … flatten_order[4] == (0,0), … flatten_order[8] == (1,1)

    for c0, c1, col, sk, fact, is_rot in post:
        # insert the rule row
        cur.execute(
            """
            INSERT INTO cellular_automaton
              (input_color, output_color, neighbor_count, wildcard_colors, centric)
            VALUES (?,?,?,?,?);
            """,
            (c0, c1, len(sk), json.dumps([]), True)
        )
        rid = cur.lastrowid

        # insert one cell per non-None output
        for idx, inp_color in enumerate(fact['nbr_in']):
            out_color = fact['nbr_out'][idx]
            dx, dy = flatten_order[idx]
            cur.execute(
                """
                INSERT INTO cellular_automaton_cells
                  (rule_id, posRelX, posRelY, color, output)
                VALUES (?,?,?,?,?);
                """,
                (rid, dx, dy, inp_color, out_color)
            )

    conn.commit()
    return bool(post)

def generate_rules_to_insert(bg, facts):
    print("[ generate_rules_to_insert ]")
    # ── 2) Group by center color transition
    center_groups = group_facts_by_center(facts)
    # remove trivial bg→bg rules
    center_groups.pop((bg, bg), None)
    # ── 3) Keep only multi-fact groups
    filtered = {k: v for k, v in center_groups.items() if len(v) > 1}
    # ── 4) Subgroup by neighbor color
    pre = []  # tuples of (c0, c1, col, struct_key, facts_list)
    for (c0, c1), grp in center_groups.items():
        # which colors appear in neighbors (excluding center idx 4)
        neigh_cols = sorted({f['nbr_in'][i] for f in grp for i in range(9) if i != 4})
        # if exactly 2 neighbor-colors and one is the bg, drop the bg
        if len(neigh_cols) == 2 and bg in neigh_cols:
            neigh_cols.remove(bg)
        for col in neigh_cols:
            struct_map = extract_structure_subgroups(grp, col)
            for sk, flist in struct_map.items():
                # log initial subgroup
                print(f"Pre Center {c0}->{c1} | neighbor {col} | struct {sk} | facts={len(flist)}")
                for f in flist:
                    print(f"    fact: nbr_in={f['nbr_in']} nbr_out={f['nbr_out']}")
                pre.append((c0, c1, col, sk, flist))

    # regroup pre entries into rotational families using sorted rotations
    grouped_pre = []  # list of (rep_sk, list of entries)
    for c0, c1, col, sk, flist in pre:
        placed = False
        for rep_sk, entries in grouped_pre:
            if sk in all_struct_rotations_sorted(rep_sk):
                entries.append((c0, c1, col, sk, flist))
                placed = True
                break
        if not placed:
            grouped_pre.append((sk, [(c0, c1, col, sk, flist)]))

    # --- puis, juste après : suppression des doublons dans chaque flist ---
    for rep_sk, entries in grouped_pre:
        for idx, (c0, c1, col, sk, flist) in enumerate(entries):
            seen_keys = set()
            new_flist = []
            for item in flist:
                # transforme le dict en tuple trié de (clé, valeur)
                key = tuple(sorted(item.items()))
                if key not in seen_keys:
                    seen_keys.add(key)
                    new_flist.append(item)
            # on remplace l'ancien tuple par un nouveau avec flist nettoyé
            entries[idx] = (c0, c1, col, sk, new_flist)
    # print("pre")
    # print(pre)
    # print("grouped_pre")
    # print(grouped_pre)
    # exit(0)
    # rebuild pre: merge facts under each representative struct
    # ── 4.5) Rebuild pre: only actually‐observed 3+-way rotations get merged ──
    new_pre = []
    for rep_sk, entries in grouped_pre:
        observed = len(entries)
        if observed < 3:
            print(f"Skipping struct {rep_sk}: only {observed} observed variants (need ≥3)")
            continue
        if entries[0][2] == bg:
            print(f"Skipping neighbor color == bg")
            continue
        if len(rep_sk) == 0:
            print(f"Skipping Empty neighbors detection")
            continue

        print(f"Merging struct {rep_sk}: {observed} observed rotations")
        c0, c1, col = entries[0][0], entries[0][1], entries[0][2]
        merged_counts = [len(e[4]) for e in entries]
        merged_flist = [f for e in entries for f in e[4]]
        print(
            f"  → Center {c0}->{c1}, neighbor {col}, "
            f"merged {len(merged_flist)} facts ({'+'.join(map(str, merged_counts))})"
        )
        new_pre.append((c0, c1, col, rep_sk, merged_flist))
    # exit(0)
    # only tack on the merged ones if there were any
    if new_pre:
        pre.extend(new_pre)
        print(f"  → Added {len(new_pre)} merged entries into pre (total pre now {len(pre)})")
    else:
        print("  → No 3-way rotational groups found; pre remains unchanged")
    # ── 5) Process subgroups with rotation logic ──────────────────────────
    post = []  # results: (c0, c1, col, struct_key, fact_dict, is_rotational)
    for c0, c1, col, struct_key, flist in pre:
        # determine base positions of target color from first fact
        base_nbr = flist[0]['nbr_in']
        base_positions = [i for i in struct_key if base_nbr[i] == col]
        # align all facts to match base_positions
        aligned = []
        for fact in flist:
            ain, aout = align_fact_to_positions(
                fact['nbr_in'], fact['nbr_out'], col, base_positions
            )
            aligned.append({'nbr_in': ain, 'nbr_out': aout})
        # log aligned facts
        print(f"Aligned facts for Center {c0}->{c1}, neighbor {col}:")
        for af in aligned:
            print(f"    fact: nbr_in={af['nbr_in']} nbr_out={af['nbr_out']}")
            # intersect separately on all positions for output and input
        output_intersected = [i for i in range(9) if len({f['nbr_out'][i] for f in aligned}) == 1]
        input_intersected = [i for i in range(9) if len({f['nbr_in'][i] for f in aligned}) == 1]
        print(f"Output intersection offsets: {output_intersected}")
        print(f"Input intersection offsets: {input_intersected}")
        # collapse to single representative fact
        rep = aligned[0]
        in_vals = list(rep['nbr_in'])
        out_vals = list(rep['nbr_out'])
        # nullify positions without consensus separately
        null_input = [i for i in range(9) if i not in input_intersected]
        null_output = [i for i in range(9) if i not in output_intersected]
        for i in null_input:
            if i != 4:
                in_vals[i] = None

        # ── if exactly two neighbor colors and one is bg, wildcard all bg neighbors ──
        # i.e. if only two distinct values in the 8 surrounding cells, and bg is one of them,
        # then for every bg‐position among those 8, force input to None.
        neighbor_vals = {in_vals[i] for i in range(9) if i != 4}
        if len(neighbor_vals) == 2 and bg in neighbor_vals:
            bg_positions = [i for i in range(9) if i != 4 and in_vals[i] == bg]
            for i in bg_positions:
                in_vals[i] = None
                if out_vals[i] == bg and i != 4:
                    out_vals[i] = None
            print(f"Wildcarded all bg neighbors at positions: {bg_positions}")

        for i in null_output:
            if i != 4:
                out_vals[i] = None
        print(f"Nullified input offsets: {null_input}")
        print(f"Nullified output offsets: {null_output}")
        # wildcard no-change positions: where input equals output, null output
        no_change = [i for i in range(9) if in_vals[i] is not None and in_vals[i] == out_vals[i]]
        for i in no_change:
            if i != 4:
                out_vals[i] = None
        print(f"No-change wildcard positions (output set None): {no_change}")
        collapsed = {'nbr_in': tuple(in_vals), 'nbr_out': tuple(out_vals)}
        print(f"Collapsed fact: nbr_in={collapsed['nbr_in']} nbr_out={collapsed['nbr_out']}")
        # generate 4 rotational variants
        variants = []
        sk = tuple(output_intersected)  # use output intersection offsets for struct
        nin, nout = collapsed['nbr_in'], collapsed['nbr_out']
        for _ in range(4):
            print(f"Variant struct {sk}: nbr_in={nin} nbr_out={nout}")
            variants.append((sk, {'nbr_in': nin, 'nbr_out': nout}))
            nin = rotate90(nin)
            nout = rotate90(nout)
            sk = tuple(sorted(index_map[i] for i in sk))
        # record all variants
        is_rot = True
        for skey, fact in variants:
            post.append((c0, c1, col, skey, fact, is_rot))
    # ── 6) Deduplicate collected rules to remove any runtime duplicates
    unique = []
    seen = set()
    for entry in post:
        key = (entry[0], entry[1], entry[2], entry[3], entry[4]['nbr_in'], entry[4]['nbr_out'], entry[5])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    post = unique
    return post

def try_differents_set_of_rules(bg, post, trains):
    # ── 1) Test “orthogonal-only” rules ────────────────────────────────────
    orthogonal_rules = []
    # diagonal indices in a 3×3 patch
    diagonals = (0, 2, 6, 8)

    for (c0, c1, col, sk, fact, is_rot) in post:
        # copy the 3×3 neighborhood
        nin = list(fact['nbr_in'])
        nout = list(fact['nbr_out'])
        # wildcard all diagonals
        for idx in diagonals:
            nin[idx] = None
            nout[idx] = None
        new_fact = {'nbr_in': tuple(nin), 'nbr_out': tuple(nout)}
        orthogonal_rules.append((c0, c1, col, sk, new_fact, is_rot))

    ok, info = test_all_rules_on_all_trains(orthogonal_rules, trains, bg)
    if ok:
        print("✅ Orthogonal-only rules cover every train transformation—using them.")
        return orthogonal_rules
    else:
        print("❌ Orthogonal-only rules are not sufficient:")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count orthogonal_rules:", len(orthogonal_rules))

    # ── 6a) Expand “unicolor” rules ────────────────────────────────────
    unicolor_extras = []
    for (c0, c1, col, sk, fact, is_rot) in post:
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
            print((c0, c1, col, sk, new_fact, is_rot))
            unicolor_extras.append((c0, c1, col, sk, new_fact, is_rot))
    ok, info = test_all_rules_on_all_trains(unicolor_extras, trains, bg)
    if ok:
        print("✅ Unicolor rules alone cover every train transformation—using them.")
        return unicolor_extras
    else:
        print("❌ Unicolor rules are not sufficient:")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(unicolor_extras))
        print(unicolor_extras)

    fixed_center = []
    for (c0, c1, col, sk, fact, is_rot) in post:
        if c0 == c1:
            fixed_center.append((c0, c1, col, sk, fact, is_rot))
    ok, info = test_all_rules_on_all_trains(fixed_center, trains, bg)
    if ok:
        print("✅ fixed_center rules alone cover every train transformation—using them.")
        return fixed_center
    else:
        print("❌ fixed_center rules are not sufficient:")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(fixed_center))
        print(fixed_center)

    all = post + unicolor_extras
    ok, info = test_all_rules_on_all_trains(all, trains, bg)
    if ok:
        print("✅ all (post + unicolor_extras) rules cover every train transformation—using them.")
        return all
    else:
        print("❌ fixed_center rules are not sufficient:")
        print("  Missing transformations per train:", info['train_failures'])
        print("  Colors missing overall:", info['colors_missing'])
        print("  Colors unexpected overall:", info['colors_unexpected'])
        print("  Count unicolor_extras:", len(fixed_center))
        print(fixed_center)

    return None

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

def test_all_rules_on_all_trains(post, trains, bg):
    """
    Apply the ENTIRE set of rules (post) to each train input and compare
    to its train output. Return (True, {}) if perfect; otherwise (False, info).
    """

    # build all CA rules at once
    ca_rules = [ build_ca_rule(c0, c1, fact)
                 for (c0, c1, col, sk, fact, is_rot) in post ]

    failures = []
    all_missing_colors = set()
    all_unexpected_colors = set()

    for t_idx, (inp_grid, expected_out) in enumerate(trains):
        result = apply_ca(inp_grid, ca_rules, bg)
        H, W = len(inp_grid), len(inp_grid[0])

        missing = []
        unexpected = []
        for y in range(H):
            for x in range(W):
                orig = inp_grid[y][x]
                res  = result[y][x]
                exp  = expected_out[y][x]
                if res != exp:
                    if res == orig:
                        # we failed to change this pixel when we should have
                        missing.append((x, y, exp))
                        all_missing_colors.add(exp)
                    else:
                        # we changed it to something unexpected
                        unexpected.append((x, y, res))
                        all_unexpected_colors.add(res)

        if missing or unexpected:
            failures.append({
                'train_index': t_idx,
                'missing': missing,
                'unexpected': unexpected
            })

    if failures:
        info = {
            'train_failures': failures,
            'colors_missing': all_missing_colors,
            'colors_unexpected': all_unexpected_colors
        }
        return False, info

    return True, {}

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
    for (c0, c1, col, sk, fact, is_rot) in post:
        #if c0 != 4 :
        #    continue
        #if  c1 != 4:
        #    continue
        ca_rule = build_ca_rule(c0, c1, fact)
        print("--- (c0, c1, col, sk, fact, is_rot) ---")
        print((c0, c1, col, sk, fact, is_rot))
        print("--- ca_rule 4->4 ---")
        print(ca_rule)
        if rule_preserves_ground_truth(ca_rule):
            filtered.append((c0, c1, col, sk, fact, is_rot))
        else:
            print(f"  ❌ Dropping rule Center {c0}->{c1}, struct {sk}: "
                  "it makes unexpected changes on the trains.")
    post = filtered
    print(f"✅ {len(post)} rules remain after ground-truth filtering.\n")
    return post


if __name__ == "__main__":
    # Real train/test from ARC-like JSON3
    data_0 = {"train": [{"input": [[0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0], [8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 8, 0, 0, 8, 0, 8, 0], [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 0, 0, 0, 0, 8, 0, 0], [0, 0, 8, 0, 0, 0, 8, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 8, 0, 0, 0, 0, 8], [0, 0, 0, 0, 0, 8, 8, 0, 0, 0, 0], [0, 8, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 8, 0, 0, 8, 0], [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 8, 0, 0]], "output": [[0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0], [8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0], [0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 8, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 8, 8, 0, 0, 0, 0], [0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0, 6, 0, 0, 0, 6, 0, 0, 6, 0, 6, 0, 0, 0, 6, 0, 0, 0], [0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0], [0, 6, 0, 0, 0, 0, 0, 0, 0, 6, 0, 6, 0, 0, 6, 0, 0, 6], [0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 6, 0, 0, 0], [0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 6, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 6, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 6]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 6, 0, 0, 0], [0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0], [0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 6, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 6]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 5, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 5, 0, 0, 0, 0, 0, 5, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 5, 0, 0, 0, 5, 0, 0], [0, 5, 0, 0, 5, 0, 5, 0, 0, 0, 0, 0, 0, 5, 0, 5, 5, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 5, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5], [5, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 0, 0, 5, 0, 0], [5, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 0, 0, 0, 0, 5, 5, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 5, 0, 0, 0, 0, 5]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 5, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 5, 0, 0, 0, 5, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 5, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5], [5, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 5, 0, 0], [5, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 5, 0, 0, 0, 0, 5, 5, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 5]]}, {"input": [[0, 0, 0, 0, 0, 4, 0, 4, 0], [0, 0, 0, 0, 4, 0, 0, 0, 0], [0, 4, 0, 0, 0, 0, 4, 0, 0], [0, 0, 0, 4, 4, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 0, 4, 0, 4, 0, 0, 4, 4], [4, 0, 4, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 4, 0, 0], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 4, 0, 0, 0, 0, 4, 0, 4], [4, 0, 4, 0, 4, 0, 0, 4, 0], [0, 4, 0, 0, 0, 0, 0, 4, 0], [0, 0, 0, 0, 0, 4, 0, 0, 0], [0, 0, 0, 0, 4, 4, 0, 0, 0], [4, 0, 4, 0, 4, 0, 0, 4, 4], [0, 0, 4, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 4, 0, 0, 0], [0, 0, 0, 0, 4, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 4, 4, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 0, 4, 4], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 0, 4, 0, 0, 0, 0, 0, 0], [0, 4, 0, 0, 0, 0, 4, 0, 4], [4, 0, 4, 0, 0, 0, 0, 4, 0], [0, 4, 0, 0, 0, 0, 0, 4, 0], [0, 0, 0, 0, 0, 4, 0, 0, 0], [0, 0, 0, 0, 4, 4, 0, 0, 0], [0, 0, 4, 0, 4, 0, 0, 4, 4], [0, 0, 4, 0, 0, 0, 0, 0, 0]]}], "test": [{"input": [[0, 3, 0, 0, 3, 0, 0, 0, 0, 0, 3, 0, 0, 3], [3, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 0, 3], [3, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0], [0, 0, 3, 0, 3, 0, 0, 0, 0, 3, 3, 3, 0, 0], [3, 0, 3, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 3], [0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0], [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0], [0, 0, 0, 0, 3, 3, 0, 0, 3, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 0, 0], [0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3], [0, 0, 0, 0, 3, 0, 3, 0, 0, 0, 3, 0, 0, 0], [0, 0, 0, 3, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 3, 3, 3, 0, 3, 3, 0, 0, 0, 0, 0], [3, 0, 0, 3, 0, 0, 3, 0, 0, 0, 0, 0, 3, 0], [3, 0, 3, 0, 0, 0, 0, 0, 3, 0, 0, 3, 0, 0], [3, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 3, 3, 0, 0, 3, 0, 0, 0, 0, 0, 3, 3]], "output": [[0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 3], [3, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 0, 3], [3, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0], [0, 0, 3, 0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0], [0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 3, 3, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 3, 0, 3, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 3, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 3, 3, 3, 0, 3, 3, 0, 0, 0, 0, 0], [3, 0, 0, 3, 0, 0, 3, 0, 0, 0, 0, 0, 3, 0], [3, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0], [3, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 3, 3, 0, 0, 3, 0, 0, 0, 0, 0, 3, 3]]}]}

    data_1 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 5, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]],
                "output": [[0, 0, 0, 0, 0, 1, 1, 1, 0], [0, 0, 0, 0, 0, 1, 5, 1, 0], [0, 0, 0, 0, 0, 1, 1, 1, 0],
                           [0, 0, 1, 1, 1, 0, 0, 0, 0], [0, 0, 1, 5, 1, 0, 0, 0, 0], [0, 0, 1, 1, 1, 0, 0, 0, 0],
                           [1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 5, 1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0, 0]]}, {
                   "input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0],
                             [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0],
                             [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]],
                   "output": [[0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 1, 1, 1, 0, 1, 5, 1], [0, 0, 1, 5, 1, 0, 1, 1, 1],
                              [0, 0, 1, 1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 5, 1],
                              [0, 0, 1, 1, 1, 0, 1, 1, 1], [0, 0, 1, 5, 1, 0, 0, 0, 0], [0, 0, 1, 1, 1, 0, 0, 0, 0]]}],
     "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 5, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]],
               "output": [[1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 5, 1, 0, 0, 0, 1, 1, 1], [1, 1, 1, 0, 0, 0, 1, 5, 1],
                          [0, 0, 1, 1, 1, 0, 1, 1, 1], [0, 0, 1, 5, 1, 0, 0, 0, 0], [0, 0, 1, 1, 1, 0, 0, 0, 0],
                          [1, 1, 1, 0, 1, 1, 1, 0, 0], [1, 5, 1, 0, 1, 5, 1, 0, 0], [1, 1, 1, 0, 1, 1, 1, 0, 0]]}]}
    data_2 = {
        "train": [
            {"input": [
                [0, 0, 0, 0, 0, 0, 0],
                [0, 8, 0, 0, 0, 0, 0],
                [0, 8, 8, 0, 0, 0, 0],
                [0, 0, 0, 0, 8, 8, 0],
                [0, 0, 0, 0, 0, 8, 0],
                [0, 8, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0]
            ], "output": [
                [0, 0, 0, 0, 0, 0, 0],
                [0, 8, 1, 0, 0, 0, 0],
                [0, 8, 8, 0, 0, 0, 0],
                [0, 0, 0, 0, 8, 8, 0],
                [1, 1, 1, 0, 1, 8, 0],
                [1, 8, 1, 0, 0, 0, 0],
                [1, 1, 1, 0, 0, 0, 0]
            ]},
            {"input": [
                [0, 0, 0, 0, 8, 8, 0],
                [0, 0, 0, 0, 0, 8, 0],
                [8, 0, 0, 0, 0, 0, 0],
                [8, 8, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 8, 0],
                [0, 0, 8, 0, 0, 0, 0],
                [0, 8, 8, 0, 0, 0, 0]
            ], "output": [
                [0, 0, 0, 0, 8, 8, 0],
                [0, 0, 0, 0, 1, 8, 0],
                [8, 1, 0, 0, 0, 0, 0],
                [8, 8, 0, 0, 1, 1, 1],
                [0, 0, 0, 0, 1, 8, 1],
                [0, 1, 8, 0, 1, 1, 1],
                [0, 8, 8, 0, 0, 0, 0]
            ]}
        ],
        "test": [
            {"input": [
                [0, 0, 0, 0, 0, 8, 8],
                [8, 8, 0, 0, 0, 0, 8],
                [8, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 8, 0, 0, 0, 8, 0],
                [8, 8, 0, 0, 0, 0, 0]
            ], "output": [
                [0, 0, 0, 0, 0, 8, 8],
                [8, 8, 0, 0, 0, 1, 8],
                [8, 1, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 1, 1, 1],
                [1, 8, 0, 0, 1, 8, 1],
                [8, 8, 0, 0, 1, 1, 1]
            ]}
        ]
    }
    data_3 = {
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
                [8,0,0,0,8,0,0],
                [0,0,0,8,8,0,0],
                [0,0,0,0,0,0,0],
                [0,8,0,0,0,0,0],
                [8,8,0,0,0,0,0]
            ], "output": [
                [0,0,0,0,0,8,8],
                [8,8,0,0,0,1,8],
                [8,1,0,1,8,0,0],
                [0,0,0,8,8,0,0],
                [0,0,0,0,0,0,0],
                [1,8,0,0,0,0,0],
                [8,8,0,0,0,0,0]
            ]}
        ]
    }

    data_4 = {"train": [
        {"input": [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 2, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 4, 0, 1, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 3, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 3]
        ], "output": [
        [2, 2, 0, 0, 0, 0, 0, 0, 0, 0],
        [2, 2, 0, 0, 0, 0, 0, 0, 0, 0],
        [4, 4, 1, 1, 0, 0, 0, 0, 0, 0],
        [4, 4, 1, 1, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 3, 3, 0, 0, 0, 0],
        [0, 0, 0, 0, 3, 3, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 4, 4, 0, 0],
        [0, 0, 0, 0, 0, 0, 4, 4, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 3, 3],
        [0, 0, 0, 0, 0, 0, 0, 0, 3, 3]
        ]}, {"input": [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 1, 0, 3, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 4, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 8],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 2, 0, 2]
        ], "output": [
        [1, 1, 3, 3, 0, 0, 0, 0, 0, 0],
        [1, 1, 3, 3, 0, 0, 0, 0, 0, 0],
        [0, 0, 4, 4, 0, 0, 0, 0, 0, 0],
        [0, 0, 4, 4, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 8, 8],
        [0, 0, 0, 0, 0, 0, 0, 0, 8, 8],
        [0, 0, 0, 0, 0, 0, 2, 2, 2, 2],
        [0, 0, 0, 0, 0, 0, 2, 2, 2, 2]
        ]}, {"input": [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 3, 0, 2, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 1, 0, 1, 0, 0, 0, 0, 0, 4]
        ], "output": [
        [3, 3, 2, 2, 0, 0, 0, 0, 0, 0],
        [3, 3, 2, 2, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 0, 0, 0, 0, 4, 4],
        [1, 1, 1, 1, 0, 0, 0, 0, 4, 4]
        ]
        }], "test": [
        {"input": [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 6, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 3, 0, 0, 0, 4, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 2, 0, 0, 0, 0, 0, 0, 0, 0]
        ], "output": [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 6, 6, 0, 0, 0, 0, 0, 0],
        [0, 0, 6, 6, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
        [0, 0, 3, 3, 0, 0, 4, 4, 0, 0],
        [0, 0, 3, 3, 0, 0, 4, 4, 0, 0],
        [2, 2, 0, 0, 0, 0, 0, 0, 0, 0],
        [2, 2, 0, 0, 0, 0, 0, 0, 0, 0]
        ]}
        ]}

    data_5 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 2, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 3, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 3, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 2, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 2, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 2, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 3, 2, 2, 3, 0, 3, 2, 3, 0], [2, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 3, 2, 3, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 0], [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 3, 3], [0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 2, 3, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 3, 3], [0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0], [2, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 2, 0, 0, 0, 0], [0, 0, 2, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0, 2, 2, 0, 0, 0, 2, 0, 2, 0, 0], [0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 0, 2, 0, 2], [0, 0, 0, 0, 0, 0, 0, 3, 2, 2, 3, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 2, 0, 0, 0], [0, 3, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 3, 2, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3], [0, 3, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0, 0, 3, 2, 3], [0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 3, 2, 3], [2, 0, 0, 0, 0, 0, 0, 2, 3, 3, 3, 0, 0, 3, 3, 3], [0, 0, 0, 0, 0, 0, 0, 0, 3, 2, 3, 2, 0, 0, 0, 0], [0, 0, 2, 0, 2, 3, 3, 3, 3, 2, 3, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 3, 2, 2, 3, 3, 3, 2, 0, 2, 0, 0], [0, 0, 0, 2, 0, 3, 3, 3, 3, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0]]}]}

    data_6 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 1, 1]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1, 1, 1, 1], [0, 0, 0, 1, 1, 1, 1, 1, 1], [0, 0, 0, 1, 1, 1, 1, 1, 1]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 1, 1], [1, 1, 1, 0, 0, 0, 1, 1, 1], [1, 1, 1, 0, 0, 0, 1, 1, 1], [1, 1, 1, 0, 0, 0, 1, 1, 1], [1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0, 0]]}]}

    data_7 = {"train": [{"input": [[2, 0, 0, 0, 0], [0, 0, 0, 2, 0], [0, 0, 0, 0, 0], [0, 6, 0, 0, 0], [0, 0, 0, 0, 0]], "output": [[2, 1, 1, 1, 1], [1, 1, 1, 2, 1], [0, 0, 1, 1, 1], [0, 6, 0, 0, 0], [0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 3, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 8, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 1, 2], [0, 0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 3, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 8, 0], [0, 1, 1, 1, 0, 0, 0, 0], [0, 1, 2, 1, 0, 0, 0, 0], [0, 1, 1, 1, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0], [0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], "output": [[1, 1, 1, 0, 0], [1, 2, 1, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 7, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 7, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 5]], "output": [[0, 1, 1, 1, 0, 0, 0, 0, 7, 0], [0, 1, 2, 1, 0, 0, 0, 0, 0, 0], [0, 1, 1, 1, 0, 0, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0, 1, 2, 1, 0], [0, 0, 0, 0, 0, 0, 1, 1, 1, 0], [0, 7, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 1, 2, 1, 0, 0, 0], [0, 0, 0, 0, 1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 5]]}]}

    data_8 = {"train": [{"input": [[0, 0, 0], [0, 0, 0], [0, 0, 0]], "output": [[8, 8, 8], [8, 0, 8], [8, 8, 8]]}, {"input": [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], "output": [[8, 8, 8], [8, 0, 8], [8, 0, 8], [8, 8, 8]]}, {"input": [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], "output": [[8, 8, 8, 8], [8, 0, 0, 8], [8, 0, 0, 8], [8, 0, 0, 8], [8, 8, 8, 8]]}, {"input": [[0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]], "output": [[8, 8, 8, 8, 8, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 8, 8, 8, 8, 8]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]], "output": [[8, 8, 8, 8, 8, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 0, 0, 0, 0, 8], [8, 8, 8, 8, 8, 8]]}]}

    data_9 = {"train": [{"input": [[0, 2, 2], [0, 2, 2], [2, 0, 0]], "output": [[0, 2, 2], [0, 2, 2], [1, 0, 0]]}, {"input": [[2, 2, 2, 0], [0, 2, 0, 0], [0, 0, 0, 2], [0, 2, 0, 0]], "output": [[2, 2, 2, 0], [0, 2, 0, 0], [0, 0, 0, 1], [0, 1, 0, 0]]}, {"input": [[2, 2, 0, 0], [0, 2, 0, 0], [2, 2, 0, 2], [0, 0, 0, 0], [0, 2, 2, 2]], "output": [[2, 2, 0, 0], [0, 2, 0, 0], [2, 2, 0, 1], [0, 0, 0, 0], [0, 2, 2, 2]]}, {"input": [[2, 2, 0], [2, 0, 2], [0, 2, 0]], "output": [[2, 2, 0], [2, 0, 1], [0, 1, 0]]}], "test": [{"input": [[2, 2, 0, 2], [0, 2, 0, 0], [0, 0, 2, 0], [2, 0, 0, 0], [0, 0, 2, 2]], "output": [[2, 2, 0, 1], [0, 2, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 2, 2]]}]}

    data_10 = {"train": [{"input": [[1, 0, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 1, 0, 1, 0], [0, 0, 0, 0, 0]], "output": [[1, 2, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 1, 2, 1, 0], [0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 1, 0, 1, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 2, 1, 2, 1, 2, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 2, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 2, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 2, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 1, 0], [0, 1, 0, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 1, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 1, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 2, 1, 0], [0, 1, 2, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 2, 1, 2, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 2, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 2, 1, 0, 0, 0, 0, 0, 0]]}], "test": [{"input": [[0, 1, 0, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 0, 1, 0, 1, 0, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 1, 2, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 2, 1, 2, 1, 2, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 2, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1, 2, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 2, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]}]}

    data_11 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 4, 0, 4, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 4, 0, 4, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 7, 0, 0], [0, 0, 0, 0, 0, 7, 1, 7, 0], [0, 0, 0, 0, 0, 0, 7, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 8, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 2, 0, 0], [0, 0, 1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 8, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 4, 0, 4, 0], [0, 0, 7, 0, 0, 0, 2, 0, 0], [0, 7, 1, 7, 0, 4, 0, 4, 0], [0, 0, 7, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 7, 0, 0], [4, 0, 4, 0, 0, 7, 1, 7, 0], [0, 2, 0, 0, 0, 0, 7, 0, 0], [4, 0, 4, 0, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 6, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 4, 0, 4, 0, 0, 0, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 4, 0, 4, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 6, 0, 0], [0, 0, 0, 7, 0, 0, 0, 0, 0], [0, 0, 7, 1, 7, 0, 0, 0, 0], [0, 0, 0, 7, 0, 0, 0, 0, 0]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 0], [0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 8, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 6, 0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 7, 0, 0], [0, 4, 0, 4, 0, 7, 1, 7, 0], [0, 0, 2, 0, 0, 0, 7, 0, 0], [0, 4, 0, 4, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 8, 0, 0, 0], [0, 0, 0, 0, 0, 0, 4, 0, 4], [0, 6, 0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 4, 0, 4]]}]}

    data_12 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 5, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 5, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 1, 5, 0, 0, 0, 0], [0, 0, 1, 0, 1, 0, 0, 0, 0], [0, 0, 5, 1, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 5, 1, 5, 0], [0, 0, 0, 0, 0, 1, 0, 1, 0], [0, 5, 1, 5, 0, 5, 1, 5, 0], [0, 1, 0, 1, 0, 0, 0, 0, 0], [0, 5, 1, 5, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 5, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 5, 1, 5, 0, 0, 5, 1, 5], [0, 1, 0, 1, 0, 0, 1, 0, 1], [0, 5, 1, 5, 0, 0, 5, 1, 5], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 1, 5, 0, 0, 0, 0, 0], [0, 1, 0, 1, 0, 0, 0, 0, 0], [0, 5, 1, 5, 0, 5, 1, 5, 0], [0, 0, 0, 0, 0, 1, 0, 1, 0], [0, 0, 0, 0, 0, 5, 1, 5, 0]]}], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 5, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[5, 1, 5, 0, 0, 0, 0, 0, 0], [1, 0, 1, 0, 0, 0, 0, 0, 0], [5, 1, 5, 5, 1, 5, 0, 0, 0], [0, 0, 0, 1, 0, 1, 0, 0, 0], [0, 0, 0, 5, 1, 5, 5, 1, 5], [0, 0, 0, 0, 0, 0, 1, 0, 1], [0, 5, 1, 5, 0, 0, 5, 1, 5], [0, 1, 0, 1, 0, 0, 0, 0, 0], [0, 5, 1, 5, 0, 0, 0, 0, 0]]}]}

    data_13 = {"train": [{"input": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 5, 5, 5, 5], [0, 0, 0, 0, 0, 0, 5, 5, 5, 5], [0, 0, 0, 0, 0, 0, 5, 5, 5, 5], [0, 0, 0, 0, 0, 0, 5, 5, 5, 5], [0, 0, 0, 0, 0, 0, 5, 5, 5, 5]], "output": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 4, 4, 1, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 1, 4, 4, 1, 0, 1, 4, 4, 1], [0, 0, 0, 0, 0, 0, 4, 2, 2, 4], [0, 0, 0, 0, 0, 0, 4, 2, 2, 4], [0, 0, 0, 0, 0, 0, 4, 2, 2, 4], [0, 0, 0, 0, 0, 0, 1, 4, 4, 1]]}, {"input": [[5, 5, 5, 5, 5, 5, 0, 0, 0, 0], [5, 5, 5, 5, 5, 5, 0, 0, 0, 0], [5, 5, 5, 5, 5, 5, 0, 0, 0, 0], [5, 5, 5, 5, 5, 5, 0, 0, 0, 0], [5, 5, 5, 5, 5, 5, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5]], "output": [[1, 4, 4, 4, 4, 1, 0, 0, 0, 0], [4, 2, 2, 2, 2, 4, 0, 0, 0, 0], [4, 2, 2, 2, 2, 4, 0, 0, 0, 0], [4, 2, 2, 2, 2, 4, 0, 0, 0, 0], [1, 4, 4, 4, 4, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 4, 4, 4, 4, 1], [0, 0, 0, 0, 4, 2, 2, 2, 2, 4], [0, 0, 0, 0, 4, 2, 2, 2, 2, 4], [0, 0, 0, 0, 1, 4, 4, 4, 4, 1]]}], "test": [{"input": [[0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 5, 5, 5, 5, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5], [0, 0, 0, 0, 5, 5, 5, 5, 5, 5]], "output": [[0, 1, 4, 4, 1, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 4, 2, 2, 4, 0, 0, 0, 0, 0], [0, 1, 4, 4, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 4, 4, 4, 4, 1], [0, 0, 0, 0, 4, 2, 2, 2, 2, 4], [0, 0, 0, 0, 1, 4, 4, 4, 4, 1]]}]}

    data_14 = {"train": [{"input": [[0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [3, 3, 3, 8, 8, 3, 3, 3, 3, 3, 3, 3, 3], [3, 3, 3, 8, 8, 3, 3, 3, 3, 3, 3, 3, 3], [3, 3, 3, 8, 8, 3, 3, 3, 3, 3, 3, 3, 3], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0]], "output": [[0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3], [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3], [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0]], "output": [[0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [1, 1, 6, 6, 1, 1, 1, 1, 1], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0], [0, 0, 6, 6, 0, 0, 0, 0, 0]]}, {"input": [[0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [7, 7, 7, 7, 7, 7, 7], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0]], "output": [[0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [7, 7, 1, 7, 7, 7, 7], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0]]}, {"input": [[0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [2, 3, 2, 2, 2, 2], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0]], "output": [[0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [2, 2, 2, 2, 2, 2], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0]]}], "test": [{"input": [[0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [5, 5, 4, 4, 5, 5], [5, 5, 4, 4, 5, 5], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0]], "output": [[0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [5, 5, 5, 5, 5, 5], [5, 5, 5, 5, 5, 5], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0], [0, 0, 4, 4, 0, 0]]}]}

    #data = data_0 # 17.2% : without outside
    #data = data_1 # 16.0% : without orphan
    #data = data_2 # 28.2% : without outside
    #data = data_3 # 18.8% : without outside
    #data = data_4 # 35.0% : without outside # with border
    #data = data_5 # 37.9% : without outside
    #data = data_6 # 17.6% : without outside
    #data = data_7 # 33.8% : without orphan
    #data = data_8 # 100.0% : without orphan
    #data = data_9 # aedd82e4 # orthogonal only ?
    data = data_10 # a699fb00 # no rotation
    #data = data_11
    #data = data_12

    #data = data_13 # 5 nbr + tick
    #data = data_14 ?
    #data = data_15 # DEFAULT_TASK_ID = "10fcaaa3" # 1) composition 2) cellular automation
    #data = data_16



    train_pairs = [(item["input"], item["output"]) for item in data["train"]]
    test_pairs  = [(item["input"], item["output"]) for item in data["test"]]
    test_pairs_inputs  = [(item["input"]) for item in data["test"]]
    db_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "db", "database.db"))
    conn = sqlite3.connect(db_path)

    # Clear existing CA rules before inserting new ones
    conn.execute("DELETE FROM cellular_automaton;")
    conn.execute("DELETE FROM cellular_automaton_cells;")
    conn.commit()

    success = detect_and_insert_ca_pipeline(conn, train_pairs, test_pairs_inputs, bg=0)
    print("Pipeline success?", success)

    # --- New: Load rules from DB and apply to test inputs ---
    print(" Applying detected rules to test inputs: ")
    # Fetch all CA rules and their neighbor cells
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, input_color, output_color FROM cellular_automaton"
    )
    ca_rules = []
    for rule_id, in_col, out_col in cursor.fetchall():
        cursor.execute(
            "SELECT posRelX, posRelY, color, output FROM cellular_automaton_cells WHERE rule_id = ?",
            (rule_id,)
        )
        neighbors = cursor.fetchall()
        # Build rule dict
        ca_rules.append({
            "input_color": in_col,
            "output_color": out_col,
            "neighbors": [(dx, dy, col, out) for dx, dy, col, out in neighbors],
            "centric": True
        })

    # Apply CA to each test input
    for idx, (inp, exp) in enumerate(test_pairs):
        print(f"--- Test  # {idx} ---")
    print("Input:")
    for row in inp:
        print(row)
    pred = apply_ca(inp, ca_rules, bg=0)

    print("Expected Output:")
    for row in exp:
        print(row)
    print("Match? ", pred == exp)

    conn.close()

