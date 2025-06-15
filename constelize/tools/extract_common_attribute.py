import json
from collections import defaultdict
from itertools import combinations, product
from typing import Dict, Any, List, Tuple, Optional, Set

def extract_common_object_grid_action(
    pairs: List[Tuple[int, int]],
    path: str,
    tables: Dict[str, Dict[int, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """
    Identify discriminative object_analysis attributes for a set
    of objects across training instances, and emit a selectObjectGridAction spec.

    Steps:
      1) Deduplicate target object_analysis IDs from the (trainId, oid) pairs.
      2) Load each corresponding row from tables["object_analysis"].
      3) Build the list of candidate columns (exclude metadata & raw data).
      4) Find columns whose values are identical across all target rows.
      5) From those, keep only columns that match exactly the target set (no extras).
      6) Package and return the action spec with those criteria.
    """
    print("🔵 Starting verbose extract_common_object_grid_action")
    print(f"  • Binding path: {path!r}")
    print(f"  • Incoming (trainId, object_analysis_id) pairs: {pairs!r}")

    # 1) Deduplicate and collect target IDs
    target_ids: List[int] = []
    for train_id, oid in pairs:
        if oid not in target_ids:
            target_ids.append(oid)
    print(f"  • Deduplicated object_analysis IDs: {target_ids!r}")
    if not target_ids:
        print("❌ No object IDs found → aborting.")
        return None

    # 2) Retrieve rows for those IDs
    obj_tbl = tables.get("object_analysis", {})
    print(f"  • Loaded object_analysis table with {len(obj_tbl)} rows")
    target_rows: List[Dict[str, Any]] = []
    for oid in target_ids:
        row = obj_tbl.get(oid)
        if row is None:
            print(f"❌ Missing row for object_analysis.id={oid} → aborting.")
            return None
        print(f"    – Row for ID={oid}: {row}")
        target_rows.append(row)
    print(f"  • Retrieved {len(target_rows)} target rows")

    # 3) Identify candidate columns to test
    exclude = {"id", "trainId", "testId", "data"}
    all_columns = list(target_rows[0].keys())
    candidate_cols = [col for col in all_columns if col not in exclude]
    print(f"  • Candidate columns (excluding {exclude}): {candidate_cols!r}")

    # 4) Find columns with identical values across all targets
    common: List[Tuple[str, Any]] = []
    for col in candidate_cols:
        first_val = target_rows[0].get(col)
        if all(row.get(col) == first_val for row in target_rows[1:]):
            common.append((col, first_val))
    print(f"  • Common attributes across targets: {common!r}")
    if not common:
        print("❌ No attributes common to all targets → aborting.")
        return None

    # 5) Filter for discriminative criteria among input objects only
    discriminative: List[Tuple[str, Any, int]] = []
    target_set = set(target_ids)
    for col, val in common:
        matching_ids = {
            oid for oid, row in obj_tbl.items()
            if row.get("isInsideInput") == 1
               and row.get("testId") == -1
               and row.get(col) == val
        }
        #print(f"    – Testing ({col!r} == {val!r}) on input objects: matches IDs {sorted(matching_ids)!r}")
        if matching_ids == target_set:
            discriminative.append((col, val, 1))
            #print(f"      ✓ {col!r} is discriminative among inputs")
        #else:
            #print(f"      ✗ {col!r} not discriminative (matches {sorted(matching_ids)!r}, target {sorted(target_set)!r})")
    #print(f"  • Final discriminative criteria: {discriminative!r}")
    if not discriminative:
        print("❌ No discriminative criteria remain → aborting.")
        return None

    # 6) Build and return the action spec
    spec = {
        "type":     "selectObjectGridAction",
        "criteria": discriminative,
        "path":     path
    }
    print(f"✅ Emitting action spec: {spec!r}")
    print("🔵 Completed extract_common_object_grid_action")
    return spec

def extract_common_sprite_grid_action(
    pairs: List[Tuple[int, int]],
    path: str,
    tables: Dict[str, Dict[int, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """
    (Verbose) Identify discriminative sprite_analysis attributes for a set
    of sprites across training instances, and emit a selectSpriteGridAction spec.

    Steps:
      1) Deduplicate target sprite_analysis IDs from the (trainId, sid) pairs.
      2) Load each corresponding row from tables["sprite_analysis"].
      3) Build the list of candidate columns (exclude metadata & raw data).
      4) Find columns whose values are identical across all target rows.
      5) From those, keep only columns that match exactly the target set (no extras).
      6) Package and return the action spec with those criteria.
    """

    print("🔵 Starting verbose extract_common_sprite_grid_action")
    print(f"  • Binding path: {path!r}")
    print(f"  • Incoming (trainId, sprite_analysis_id) pairs: {pairs!r}")

    # 1) Deduplicate and collect target IDs
    target_ids: List[int] = []
    for train_id, sid in pairs:
        if sid not in target_ids:
            target_ids.append(sid)
    print(f"  • Deduplicated sprite_analysis IDs: {target_ids!r}")
    if not target_ids:
        print("❌ No sprite IDs found → aborting.")
        return None

    # 2) Retrieve rows for those IDs
    sprite_tbl = tables.get("sprite_analysis", {})
    print(f"  • Loaded sprite_analysis table with {len(sprite_tbl)} rows")
    target_rows: List[Dict[str, Any]] = []
    for sid in target_ids:
        row = sprite_tbl.get(sid)
        if row is None:
            print(f"❌ Missing row for sprite_analysis.id={sid} → aborting.")
            return None
        print(f"    – Row for ID={sid}: {row}")
        target_rows.append(row)
    print(f"  • Retrieved {len(target_rows)} target rows")

    # 3) Identify candidate columns to test
    exclude = {"id", "trainId", "testId", "data"}
    all_columns = list(target_rows[0].keys())
    candidate_cols = [col for col in all_columns if col not in exclude]
    print(f"  • Candidate columns (excluding {exclude}): {candidate_cols!r}")

    # 4) Find columns with identical values across all targets
    common: List[Tuple[str, Any]] = []
    for col in candidate_cols:
        first_val = target_rows[0].get(col)
        if all(row.get(col) == first_val for row in target_rows[1:]):
            common.append((col, first_val))
    print(f"  • Common attributes across targets: {common!r}")
    if not common:
        print("❌ No attributes common to all targets → aborting.")
        return None

    # 5) Filter for discriminative criteria among input sprites only
    discriminative: List[Tuple[str, Any, int]] = []
    target_set = set(target_ids)
    for col, val in common:
        # only consider sprites where isInsideInput == 1  AND  testId == -1
        matching_ids = {
            sid
            for sid, row in sprite_tbl.items()
            if row.get("isInsideInput") == 1
               and row.get("testId") == -1
               and row.get(col) == val
        }
        print(f"    – Testing ({col!r} == {val!r}) on input sprites: matches IDs {sorted(matching_ids)!r}")
        if matching_ids == target_set:
            discriminative.append((col, val ,1))
            print(f"      ✓ {col!r} is discriminative among inputs")
        else:
            print(
                f"      ✗ {col!r} not discriminative (matches {sorted(matching_ids)!r}, target {sorted(target_set)!r})")
    print(f"  • Final discriminative criteria: {discriminative!r}")
    if not discriminative:
        print("❌ No discriminative criteria remain → aborting.")
        return None

    # 6) Build and return the action spec
    spec = {
        "type":     "selectSpriteGridAction",
        "criteria": discriminative,
        "path":     path
    }
    print(f"✅ Emitting action spec: {spec!r}")
    print("🔵 Completed extract_common_sprite_grid_action")
    return spec



def extract_common_attribute_action(
    attributes_by_input_and_values: Dict[str, Dict[int, List[str]]],
    pairs: List[Tuple[int, int]],
    path: str,
    tables: Dict[str, Dict[int, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """
    Verbose tracing of:
      1) per-train and cross-train common column discovery
      2) row collection
      3) sprite ID resolution
      4) deduplication by data
      5) grouping by similarity
      6) criteria search
      7) early getAttributeAction return if applicable
    """

    #print("=== extract_common_attribute_action START ===")
    #print(f"Path: {path!r}")
    #print(f"Input pairs (trainId,testId): {pairs}")
    #print(f"Loaded tables: {list(tables.keys())}")
    #print(f"Attributes buckets: {list(attributes_by_input_and_values.keys())}")

    # 0) Group criteria values by train
    values_by_train = group_values_by_train(pairs)
    #print("1) group_values_by_train →")
    #for tid, vals in values_by_train.items():
    #    print(f"   Train {tid}: {vals}")

    # ∎ very first: look for a common FIRST_SIGHT_ANALYSIS attribute
    #print("2) Computing per-train common columns for 'first_sight_analysis'")
    per_train_fsa = compute_common_columns(
        attributes_by_input_and_values,
        values_by_train,
        "first_sight_analysis",
    )
    #print(f"   per_train_fsa: {per_train_fsa}")

    #print("3) Intersect and prioritize across trains")
    fsa_common = intersect_and_prioritize(path, per_train_fsa)
    #print(f"   fsa_common: {fsa_common}")

    if fsa_common:
        #print(f"4) Found common first_sight_analysis.{fsa_common[0]}, returning GET_ATTRIBUTE")
        return {
            "type": "getAttributeAction",
            "attribute": f"first_sight_analysis.{fsa_common[0]}"
        }

    per_train_common = compute_common_columns(attributes_by_input_and_values, values_by_train, "sprite_analysis")

    # if not common_for_train:
    #    print("    → No overlap within this train → returning None")
    #    return None

    common_columns = intersect_common_columns(path, per_train_common)

    #if not cols:
    #    print("    → No common columns across trains → returning None")
    #    return None

    # 4) Build per-train list of table#rowId for those columns
    per_train_rows = compute_per_train_rows(attributes_by_input_and_values, common_columns, values_by_train)

    # 5) Resolve sprite_occurrence → sprite_analysis IDs
    occ2sprite = compute_occ2sprite(tables)

    sprite_ids_by_train = compute_sprite_ids_by_train(occ2sprite, per_train_rows)

    deduped = dedupe_sprite_by_train(sprite_ids_by_train, tables)

    #print("\n==> 8) Find most‐alike sprite pairs")
    groups = group_similar_sprites_by_attributes(common_columns, deduped, tables)
    #print("    Most-alike pairs:", groups)

    all_sprites = compute_all_input_only_sprites(deduped, tables)

    action = compute_select_sprite_and_attribute_action(all_sprites, common_columns, groups, pairs, path, tables,
                                                        values_by_train)
    if action:
        #print("\n==> Returning select action:", action)
        return action

    # --- FALLBACK: object‐level grouping using the same 5–10 pipeline ---
    print("==> No sprite‐level action found, falling back to object‐level grouping")

    per_train_common_obj = compute_common_columns(attributes_by_input_and_values, values_by_train, "object_analysis")

    # if not common_for_train:
    #    print("    → No overlap within this train → returning None")
    #    return None

    common_columns_obj = intersect_common_columns(path, per_train_common_obj)

    # 5) Build per‐train list of object_analysis / object_occurrence row IDs,
    #    in the exact order of common_columns_obj
    per_train_rows_obj = {tid: [] for tid in values_by_train}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key, {})

        # for each column in priority order…
        for col in common_columns_obj:
            # check each unresolved value
            for v in dict.fromkeys(vals):
                for full in attr_map.get(v, []):
                    if "." not in full:
                        continue
                    table_row, full_col = full.split(".", 1)
                    if full_col != col:
                        continue
                    table_name = table_row.split("#", 1)[0]
                    if table_name in ("object_analysis", "shape_occurrence"):
                        per_train_rows_obj[train_id].append(table_row)

    #print("    per_train_rows_obj (prioritized):", per_train_rows_obj)

    # 6) Resolve object_occurrence → object_analysis IDs
    obj_occ = tables.get("object_occurrence", {})
    occ2obj = { rid: row["object_id"] for rid, row in obj_occ.items() }

    # 7) Collapse to object IDs per train
    object_ids_by_train: Dict[str, List[int]] = {}
    for train_id, rows in per_train_rows_obj.items():
        seen, ordered = set(), []
        for full in rows:
            if "#" not in full:
                continue
            table, id_str = full.split("#", 1)
            rid = int(id_str)
            # map occurrence → real object_id
            oid = rid if table == "object_analysis" else occ2obj.get(rid)
            if oid is None or oid in seen:
                continue
            seen.add(oid)
            ordered.append(oid)
        key = f"{train_id}#-1"
        object_ids_by_train[key] = ordered
        #print(f"  {key} → raw object IDs (ordered):", ordered)

    # 8) Deduplicate by object 'data' payload
    deduped_obj: Dict[str, List[int]] = {}
    for key, oids in object_ids_by_train.items():
        seen, uniq = set(), []
        for oid in oids:
            data = tables["object_analysis"][oid].get("data")
            if data not in seen:
                seen.add(data)
                uniq.append(oid)
        deduped_obj[key] = uniq
        #print(f"  {key} → deduped object IDs:", uniq)

    # 9) Build all candidate object‐groups via Cartesian product
    from itertools import product
    train_keys   = sorted(deduped_obj.keys())                # e.g. ["0#-1","1#-1","2#-1"]
    per_id_lists = [deduped_obj[k] for k in train_keys]      # e.g. [[2], [4], [5,6]]
    groups_obj   = list(product(*per_id_lists))
    #print("    Candidate object groups:", groups_obj)

    # 10) Build negatives = all input‐only objects
    train_ids = [int(k.split("#",1)[0]) for k in deduped_obj]
    all_objects = [
        oid for oid,row in tables["object_analysis"].items()
        if row.get("trainId") in train_ids and row.get("isInsideInput") == 1
    ]
    #print("    all_objects (negatives):", all_objects)

    # 11) Find minimal distinguishing criteria per object‐group
    for group in groups_obj:
        if any(sid is None for sid in group):
            continue
        print("1) find_minimal_selection_criteria_for_table")
        crit = find_minimal_selection_criteria_for_table(
            group, all_objects, tables, table_key="object_analysis"
        )
        #print(f"    Object group {group} → criteria: {crit}")
        output_attr = next(iter(common_columns_obj), None)
        #print(f"    output attribute: {output_attr}")
        if crit and output_attr:
            action = {
                "type":             "selectObjectAndAttributeAction",
                "criteria":         crit,
                "output_attribute": output_attr,
                "for_objects":      list(group)
            }
            #print("==> Returning selectObjectAndAttributeAction:", action)
            return action

    #print("==> No object‐level group matched either → returning None")
    return None

def intersect_and_prioritize(
    path: str,
    per_train_common: Dict[int, Set[str]]
) -> List[str]:
    """
    Intersect all the per-train column sets, then sort them so that `path`
    (if present) comes first, the rest in alphabetical order.
    Returns the final prioritized list of column names.
    """
    #print("\n==> Intersect across trains")
    if not per_train_common:
        return []

    # compute the intersection
    common_cols = set.intersection(*per_train_common.values())
    #print(f"    intersection: {common_cols}")

    if not common_cols:
        return []

    # prioritize `path` first if it’s in the intersection
    if path in common_cols:
        rest = sorted(common_cols - {path})
        result = [path] + rest
    else:
        result = sorted(common_cols)

    #print(f"    prioritized columns: {result}")
    return result

def compute_select_sprite_and_attribute_action(all_sprites, common_columns, groups, pairs, path, tables,
                                               values_by_train):
    action = None
    #print("\n==> 10) Search minimal distinguishing criteria for each group")
    for group in groups:
        if any(sid is None for sid in group):
            #print(f"    🔹 Skipping incomplete group {group}")
            continue
        print("2) find_minimal_selection_criteria_for_table")
        crit = find_minimal_selection_criteria_for_table(group, all_sprites, tables, table_key="sprite_analysis")
        #print(f"    Group {group} → criteria: {crit}")
        if crit:
            # 11) restrict to columns that actually exist on sprite_analysis
            sprite_tbl = tables["sprite_analysis"]
            # grab one row to see which columns are present
            sample = next(iter(sprite_tbl.values()), {})
            sprite_cols = [c for c in common_columns if c in sample]

            # map trainId → original unresolved value
            pairs_by_train = {t: v for t, v in pairs}
            train_ids_sorted = sorted(values_by_train.keys())

            output_attr = None
            for col in sprite_cols:
                # check that for each sprite in our chosen group, sprite_tbl[sid][col]
                # matches the original unresolved binding value for its train
                ok = True
                for sid, train_id in zip(group, train_ids_sorted):
                    if sprite_tbl[sid][col] != pairs_by_train[train_id]:
                        ok = False
                        break
                if ok:
                    output_attr = col
                    break

            # if none matched exactly, fall back safely
            if output_attr is None:
                output_attr = path if path in sprite_cols else (sprite_cols[0] if sprite_cols else path)

            action = {
                "type": "selectSpriteAndAttributeAction",
                "criteria": crit,
                "output_attribute": output_attr,
                "for_sprites": list(group)
            }
            break
    return action


def compute_all_input_only_sprites(deduped, tables):
    #print("\n==> 9) input-only sprites in these trains")
    train_ids = [int(k.split("#", 1)[0]) for k in deduped]
    all_sprites = [
        sid for sid, row in tables["sprite_analysis"].items()
        if row["trainId"] in train_ids and row.get("isInsideInput") == 1
    ]
    #print("    all_sprites:", all_sprites)
    return all_sprites


def dedupe_sprite_by_train(sprite_ids_by_train, tables):
    #print("\n==> 7) Deduplicate by sprite data per train")
    deduped: Dict[str, List[int]] = {}
    for key, sids in sprite_ids_by_train.items():
        seen, uniq = set(), []
        for sid in sids:
            data = tables["sprite_analysis"][sid]["data"]
            if data not in seen:
                seen.add(data)
                uniq.append(sid)
        deduped[key] = uniq
        #print(f"  {key} → deduped sprite IDs:", uniq)
    return deduped


def compute_sprite_ids_by_train(occ2sprite, per_train_rows):
    #print("\n==> 6) Collapse to sprite IDs per train")
    sprite_ids_by_train: Dict[str, List[int]] = {}
    for train_id, rows in per_train_rows.items():
        sids = set()
        for tr in rows:
            if "#" not in tr:
                continue
            table, id_str = tr.split("#", 1)
            rid = int(id_str)
            if table == "sprite_analysis":
                sids.add(rid)
            elif table == "sprite_occurrence":
                target = occ2sprite.get(rid)
                if target is not None:
                    sids.add(target)
        key = f"{train_id}#-1"
        sprite_ids_by_train[key] = sorted(sids)
        #print(f"  {key} → raw sprite IDs:", sprite_ids_by_train[key])
    return sprite_ids_by_train


def compute_occ2sprite(tables):
    #print("\n==> 5) Resolve sprite_occurrence → sprite_analysis IDs")
    sprite_occ = tables.get("sprite_occurrence", {})
    occ2sprite = {rid: row["sprite_id"] for rid, row in sprite_occ.items()}
    #print("    occ2sprite map size:", len(occ2sprite))
    return occ2sprite


def compute_per_train_rows(attributes_by_input_and_values, common_columns, values_by_train):
    #print("\n==> 4) Build per-train list of table#rowId for those columns")
    per_train_rows: Dict[int, List[str]] = {tid: [] for tid in values_by_train}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values[key]
        for v in dict.fromkeys(vals):
            for full in attr_map.get(v, []):
                if "." not in full:
                    continue
                table_row, col = full.split(".", 1)
                table_name = table_row.split("#", 1)[0]
                # <<< only keep sprite tables here
                if table_name not in ("sprite_analysis", "sprite_occurrence"):
                    continue
                if col in common_columns:
                    per_train_rows[train_id].append(table_row)
        #print(f"  Train {train_id} rows:", per_train_rows[train_id])
    return per_train_rows


def group_values_by_train(pairs):
    #print("==> 1) Group & dedupe values by train")
    values_by_train: Dict[int, List[int]] = {}
    for train_id, value in pairs:
        values_by_train.setdefault(train_id, []).append(value)
    #print("    values_by_train:", values_by_train)
    return values_by_train


def intersect_common_columns(path: str, per_train_common: Dict[int, Set[str]]) -> List[str]:
    #print("==> 3) Intersect across trains (with verbose tracking)")
    common_columns = None

    for tid, cols in per_train_common.items():
        #print(f"  Train {tid} has common columns: {sorted(cols)}")
        if common_columns is None:
            common_columns = set(cols)
        else:
            #print(f"    ∩ with previous: {sorted(common_columns)}")
            common_columns &= cols
            #print(f"    → intersection now: {sorted(common_columns)}")

    #if not common_columns:
    #    print("⚠️ Intersection is empty — no column common to all trains.")
    #else:
    #    print(f"✅ Final common columns: {sorted(common_columns)}")
    return common_columns

def compute_common_columns(
    attributes_by_input_and_values: Dict[str, Dict[int, List[str]]],
    values_by_train: Dict[int, List[int]],
    table_name: str
) -> Dict[int, Set[str]]:
    """
    For each trainId in values_by_train, look up the list of numeric values for that
    train, then for each value collect the set of columns (after the dot) coming from
    TABLE_NAME (e.g. "sprite_analysis" or "first_sight_analysis"), and intersect them.
    Returns a map trainId → set of common column names.
    """
    #print(f"\n==> Compute per-train common columns for `{table_name}`")
    per_train_common: Dict[int, Set[str]] = {}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key, {})
        #print(f"  Train {train_id}, values={vals}, attr_map keys={list(attr_map.keys())}")

        common_for_train: Optional[Set[str]] = None
        for v in dict.fromkeys(vals):
            raw_attrs = attr_map.get(v, [])
            cols = set()
            for full in raw_attrs:
                if "." not in full:
                    continue
                table_row, col = full.split(".", 1)
                tname = table_row.split("#", 1)[0]
                if tname == table_name:
                    cols.add(col)
            #print(f"    Value {v} → filtered columns: {cols}")

            if common_for_train is None:
                common_for_train = cols
            else:
                common_for_train &= cols

        # if nothing matched at all, produce an empty set
        per_train_common[train_id] = common_for_train or set()
        #print(f"    → common_for_train[{train_id}] = {per_train_common[train_id]}")
    return per_train_common

def group_similar_sprites_by_attributes(
    common_columns: List[str],
    sprite_ids_by_train: Dict[str, List[int]],
    tables: Dict[str, Dict[int, Dict[str, Any]]],
    tie_threshold: float = 0.1
) -> List[Tuple[int, ...]]:
    """
    Pour N trains, renvoie des tuples (sid_ref, sid_train1, ..., sid_trainN)
    appariés d'abord par index dans le train de référence, puis, pour les
    restants, par plus petite distance L1, avec repli sur l'index si distance
    trop proche (tie_threshold relatif).
    """
    # 1) repérer le train de référence (le plus long)
    train_keys = sorted(sprite_ids_by_train.keys())
    if not train_keys:
        return []
    # référence = clé dont la liste est la plus longue
    ref_key = max(train_keys, key=lambda k: len(sprite_ids_by_train[k]))
    other_keys = [k for k in train_keys if k != ref_key]

    lists = {k: sprite_ids_by_train[k] for k in train_keys}

    # 2) colonnes communes valides
    sprite_tbl = tables.get("sprite_analysis", {})
    if not sprite_tbl:
        #print("⚠️ sprite_analysis vide")
        return []
    sample = next(iter(sprite_tbl.values()))
    valid_cols = [c for c in common_columns if c in sample]
    if not valid_cols:
        #print("⚠️ Pas de colonne commune:", common_columns)
        return []

    # 3) vecteurs de features pour chaque train
    feats = {}
    for k, lst in lists.items():
        feats[k] = {sid: [sprite_tbl[sid][col] for col in valid_cols] for sid in lst}

    used = {k: set() for k in train_keys}
    groups: List[Tuple[int, ...]] = []

    # 4) appariement direct par index
    ref_list = lists[ref_key]
    min_len = min(len(lists[k]) for k in train_keys)
    for i in range(min_len):
        tup = tuple(lists[k][i] for k in train_keys)
        groups.append(tup)
        for k, sid in zip(train_keys, tup):
            used[k].add(sid)

    # 5) pour chaque sid_ref restant, chercher son meilleur match dans chaque autre train
    for sid_ref in ref_list:
        if sid_ref in used[ref_key]:
            continue
        used[ref_key].add(sid_ref)
        vec_ref = feats[ref_key][sid_ref]
        grp = [sid_ref]

        for k in other_keys:
            # candidats non encore utilisés
            cands = [sid for sid in lists[k] if sid not in used[k]]
            if not cands:
                grp.append(None)
                continue

            # calcul des distances
            dists = [(sid, sum(abs(a-b) for a,b in zip(vec_ref, feats[k][sid])))
                     for sid in cands]
            dists.sort(key=lambda x: x[1])
            best_sid, best_d = dists[0]
            # si tie proche, retomber sur appariement par index
            if len(dists) > 1:
                second_d = dists[1][1]
                # check relatif
                if second_d - best_d <= tie_threshold * max(best_d, 1):
                    # on choisit le candidat à même index que sid_ref
                    idx = ref_list.index(sid_ref)
                    if idx < len(cands):
                        best_sid = cands[idx]
            grp.append(best_sid)
            used[k].add(best_sid)

        # reconstitue tuple dans l'ordre train_keys
        # grp = [sid_ref] + [match pour chaque other_keys]
        full_tup = []
        for k in train_keys:
            if k == ref_key:
                full_tup.append(sid_ref)
            else:
                # les valeurs dans grp sont dans l'ordre other_keys
                full_tup.append(grp[1 + other_keys.index(k)])
        groups.append(tuple(full_tup))

    return groups

def find_minimal_selection_criteria_for_table(
    group: Tuple[int, ...],
    all_ids: List[int],
    tables: Dict[str, Dict[int, Dict[str, Any]]],
    table_key: str
) -> List[Tuple[str, Any, int]]:
    """
    Retourne une liste de (colonne, valeur, poids), en commençant par
    les critères stricts (poids=3), puis les lâches (poids=1).
    - strict : inclut tous les positifs et exclut *tous* les négatifs
    - lâche  : inclut tous les positifs et exclut *au moins* un négatif
    """
    # 1) filtrage des lignes d'entraînement (isInsideInput ou testId==-1)
    raw = tables.get(table_key, {})
    if table_key == "first_sight_analysis":
        tbl = {sid: row for sid, row in raw.items() if row.get("testId") == -1}
    else:
        tbl = {sid: row for sid, row in raw.items() if row.get("isInsideInput")}
    if not tbl:
        return []

    positives = set(group) & set(tbl.keys())
    negatives = set(all_ids) - positives
    # s'il n'y a pas de positifs ou pas de négatifs, on ne peut rien distinguer
    if not positives or not negatives:
        return []

    sample = next(iter(tbl.values()))
    cols = list(sample.keys())

    strict = []
    loose  = []

    # 2) parcourir toutes les colonnes
    for col in cols:
        # 2a) est-elle constante sur tous les positifs ?
        pos_vals = {tbl[sid][col] for sid in positives}
        if len(pos_vals) != 1:
            continue
        val = pos_vals.pop()

        # 2b) stricte : *tous* les négatifs doivent être ≠
        if all(tbl[n][col] != val for n in negatives):
            strict.append((col, val, 10))
        # 2c) lâche : au moins un négatif est ≠
        elif any(tbl[n][col] != val for n in negatives):
            loose.append((col, val, 1))

    # 3) concatène strict + (loose sans doublons de colonne)
    strict_cols = {col for col, _, _ in strict}
    merged = strict + [(c, v, w) for (c, v, w) in loose if c not in strict_cols]
    return merged

def find_minimal_selection_criteria_for_table_old(
    group: Tuple[int, ...],
    all_ids: List[int],
    tables: Dict[str, Dict[int, Dict[str, Any]]],
    table_key: str
) -> List[Tuple[str, Any, int]]:
    """
    Find a minimal set of (column,value) tests that include all group IDs (positives)
    and exclude all other IDs (negatives), but only over rows where isInsideInput==True.
    If all positives have isFromSplit==1, ensure ('isFromSplit', 1) is always returned.
    """
    strict = find_minimal_selection_criteria_for_table_strict(
        group,
        all_ids,
        tables,
        table_key
    )
    if strict:
        return strict

    # 1) pull the raw table and filter to input‐side rows only
    raw = tables.get(table_key, {})
    tbl = {sid: row for sid, row in raw.items() if row.get("isInsideInput")}
    if not tbl:
        return []

    ids = set(tbl.keys())

    # 2) split into positives/negatives within input‐side
    positives = {sid for sid in group if sid in ids}
    negatives = ids - positives
    if not positives or not negatives:
        return []

    # 3) find columns constant across the positives
    sample = next(iter(tbl.values()))
    all_cols = list(sample.keys())
    constant_cols = [
        col for col in all_cols
        if len({tbl[sid][col] for sid in positives}) == 1
    ]

    # 4) keep only those that discriminate (at least one negative differs)
    discriminating = []
    for col in constant_cols:
        val = tbl[next(iter(positives))][col]
        if any(tbl[n][col] != val for n in negatives):
            discriminating.append((col, val, 1))

    return discriminating

def find_minimal_selection_criteria_for_table_strict(
    group: Tuple[int, ...],
    all_ids: List[int],
    tables: Dict[str, Dict[int, Dict[str, Any]]],
    table_key: str
) -> List[Tuple[str, Any, int]]:
    """
    Verbose version of minimal selection criteria finder.
    Finds a minimal set of (column, value) pairs that include all group IDs and exclude negatives.
    Always prints internal state at each step.
    """
    print("\n=== find_minimal_selection_criteria_for_table_verbose ===")
    print(f"Table key: {table_key}")
    print(f"Group IDs: {group}")
    print(f"All IDs: {all_ids}")

    # 1) pull the raw table and filter to input‑side rows only
    raw = tables.get(table_key, {})
    print(f"Loaded raw rows count: {len(raw)}")
    if table_key == "first_sight_analysis":
        tbl = {sid: row for sid, row in raw.items() if row.get("testId") == -1}
    else:
        tbl = {sid: row for sid, row in raw.items() if row.get("isInsideInput") }
    print(f"Filtered to isInsideInput rows: {len(tbl)} rows")
    if not tbl:
        print("No input‑side rows found; returning []")
        return []

    ids = set(all_ids) #set(tbl.keys())
    print(f"Candidate row IDs after filtering: {ids}")
    filtered_ids = set(tbl.keys())
    print(f"Rows present in tbl: {filtered_ids}")

    # 2) split into positives and negatives within input‑side
    positives = {sid for sid in group if sid in ids}
    negatives = ids - positives
    print(f"Positives: {positives}")
    print(f"Negatives: {negatives}")

    if not positives:
        print("No positives; returning []")
        return []
    if not negatives:
        print("No negatives; returning []")
        return []

    # 3) find columns constant across the positives
    sample = next(iter(tbl.values()))
    all_cols = list(sample.keys())
    print(f"All columns: {all_cols}")
    constant_cols = []
    for col in all_cols:
        values = {tbl[s][col] for s in positives}
        if len(values) == 1:
            constant_cols.append(col)
        print(f"Column '{col}' values in positives: {values}")
    print(f"Constant columns across positives: {constant_cols}")

    # 4) keep only those that discriminate (all negatives differ)
    discriminating: List[Tuple[str, Any, int]] = []
    for col in constant_cols:
        # get the single positive value
        val = tbl[next(iter(positives))][col]
        # collect every negative’s value for this column
        neg_vals = [tbl[n][col] for n in negatives]
        # check that none of the negatives match the positive
        all_differ = all(v != val for v in neg_vals)
        print(f"Checking column '{col}': positive value = {val}, negative values = {neg_vals}")
        if all_differ:
            discriminating.append((col, val, 10))
            print(f"  → Column '{col}' discriminates all negatives; keeping ({col}, {val})")
        else:
            print(f"  → Column '{col}' does not discriminate all negatives; skipping")

    print(f"Discriminating criteria: {discriminating}")
    print("=== end ===\n")
    return discriminating



def common_attributes_by_train_value_pairs(
    attributes_by_input_and_values: dict[str, dict[int, list[str]]],
    pairs: list[tuple[int, int]],
    path: str,
    tables: dict[str, dict[int, dict[str, Any]]]
) -> list[str]:
    # 1) group and dedupe values by train
    values_by_train: dict[int, list[int]] = {}
    for train_id, value in pairs:
        values_by_train.setdefault(train_id, []).append(value)

    # 2) per-train intersection
    per_train_common: dict[int, set[str]] = {}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key)
        if not attr_map:
            return []

        common_for_train: set[str] | None = None
        for v in dict.fromkeys(vals):
            raw_attrs = attr_map.get(v, [])
            # ← extract just the part after the dot:
            cols_for_value = {
                full.split(".", 1)[1]
                for full in raw_attrs
                if "." in full
            }
            if common_for_train is None:
                common_for_train = cols_for_value
            else:
                common_for_train &= cols_for_value

            # if no common column **names** in this train, bail out
            if not common_for_train:
                #print(f"no common column **names** in this train, bail out")
                return []

        per_train_common[train_id] = common_for_train  # type: ignore

    # 3) cross-train intersection
    common_attrs = set.intersection(*per_train_common.values()) if per_train_common else set()
    if not common_attrs:
        #print(f"not common_attrs")
        return []

    # 4) split out table#row → column, but only for columns we kept
    col_to_rows: dict[str, list[str]] = {}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values[key]
        for v in dict.fromkeys(vals):
            for full in attr_map.get(v, []):
                if "." not in full:
                    continue
                table_row, col = full.split(".", 1)
                if col in common_attrs:
                    col_to_rows.setdefault(col, []).append(table_row)

    # 5) display and return
    #for col in sorted(common_attrs):
    #    rows = sorted(set(col_to_rows.get(col, [])))
    #    print(f"{col} → {rows}")
    #    #print(f"{col}")

    # Step 5) split into sprite vs object
    sprite_rows_by_table = defaultdict(set)
    object_rows_by_table = defaultdict(set)

    for col in common_attrs:
        for table_row in col_to_rows.get(col, []):
            table, rid_str = table_row.split("#", 1)
            rid = int(rid_str)

            if table.startswith("sprite_"):
                # anything coming from sprite_analysis, sprite_occurrence,
                # sprite_unique, sprite_transformation
                sprite_rows_by_table[table].add(rid)
            elif table.startswith("object_") or table.startswith("shape_"):
                # object_analysis, shape_occurrence, shape, shape_transformation
                object_rows_by_table[table].add(rid)

    # for display
    for table, ids in sprite_rows_by_table.items():
        print(f"[SPRITE] {table}: {sorted(ids)}")
    for table, ids in object_rows_by_table.items():
        print(f"[OBJECT] {table}: {sorted(ids)}")

    return (
        sorted(common_attrs),
        {t: set(ids) for t, ids in sprite_rows_by_table.items()},
        {t: set(ids) for t, ids in object_rows_by_table.items()}
    )

def common_attributes_by_train_value_pairs_old(
    attributes_by_input_and_values: dict[str, dict[int, list[str]]],
    pairs: list[tuple[int, int]],
    path: str
) -> list[str]:
    #if( path == "minX"):
    #    print("common_attributes_by_train_value_pairs")
    common_attrs = None

    for train_id, value in pairs:
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key)
        if not attr_map:
            return []
        attrs_for_value = set(attr_map.get(value, []))
        if common_attrs is None:
            common_attrs = attrs_for_value
        else:
            common_attrs &= attrs_for_value

        if not common_attrs:
            return []

    return sorted(common_attrs) if common_attrs else []
