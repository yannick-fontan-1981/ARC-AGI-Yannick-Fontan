import json
import sqlite3
from collections import defaultdict
from itertools import combinations
from typing import Dict, Any, List, Iterable, Tuple, Optional


# Ajout facultatif d’un alias plus explicite
def load_sqlite_to_dict(db_path: str):
    return load_all_tables_from_sqlite(db_path)

def load_table_from_sqlite(conn: sqlite3.Connection, table_name: str, key_field: str) -> Dict[str, Dict[str, Any]]:
    cursor = conn.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    col_names = [description[0] for description in cursor.description]

    return {
        str(row[col_names.index(key_field)]): dict(zip(col_names, row))
        for row in rows
    }

def load_all_tables_from_sqlite(db_path: str) -> Dict[str, Dict[int, Dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    tables = {}

    for table_name in [
        "first_sight_analysis",
        "object_analysis",
        "shape",
        "shape_transformation",
        "shape_occurrence",
        "sprite_analysis",
        "sprite_unique",
        "sprite_transformation",
        "sprite_occurrence"
    ]:
        cursor.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        indexed_rows = {}
        for row in rows:
            row_dict = dict(zip(columns, row))
            row_id = row_dict["id"]
            indexed_rows[row_id] = row_dict

        tables[table_name] = indexed_rows

    conn.close()
    return tables

def is_excluded_column(col_name):
    return col_name == "id" or col_name.endswith("_id")

def _sanitize_binding_value(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value

def build_values_by_input(db_path: str):
    tables = load_all_tables_from_sqlite(db_path)
    values_by_input = defaultdict(dict)

    # 🧩 1. Columns to keep from first_sight_analysis (only input-related)
    input_columns_first_sight_analysis = [
        "widthInput", "heightInput", "diffWidthHeightInput", "ratioWidthHeightInput",
        "areaInput", "countBlocksInput", "countZonesInput", "countColorsInput"
    ]
    first_sight = tables.get("first_sight_analysis", {})
    for row_id, row_data in first_sight.items():
        train_id, test_id = row_data.get("trainId", -1), row_data.get("testId", -1)
        if train_id == -1 and test_id == -1:
            continue
        key_id = f"{train_id}#{test_id}"
        for col in input_columns_first_sight_analysis:
            if col in row_data and row_data[col] is not None:
                values_by_input[key_id][f"first_sight_analysis.{col}"] = _sanitize_binding_value(row_data[col])

    # 🧩 2. Tables with isInsideInput flag
    relevant_shape_ids = set()
    relevant_shape_trans_ids = set()
    relevant_sprite_ids = set()
    relevant_sprite_trans_ids = set()

    def process_occurrence_table(table_name):
        rows = tables.get(table_name, {})
        for row_id, row_data in rows.items():
            if not row_data.get("isInsideInput"):
                continue
            train_id = row_data.get("trainId", -1)
            test_id = row_data.get("testId", -1)
            if train_id == -1 and test_id == -1:
                continue
            key_id = f"{train_id}#{test_id}"
            for col, val in row_data.items():
                if is_excluded_column(col) or col in {'id', 'trainId', 'testId', 'filename', 'isInsideInput', 'isInsideOutput', 'isInsideTrain', 'isInsideTest'}:
                    continue
                values_by_input[key_id][f"{table_name}#{row_id}.{col}"] = _sanitize_binding_value(val)
            # track ids for later joins
            if table_name == "shape_occurrence":
                shape_id = row_data.get("shape_id")
                shape_trans_id = row_data.get("shape_transformation_id")
                if shape_id is not None:
                    relevant_shape_ids.add(shape_id)
                if shape_trans_id is not None:
                    relevant_shape_trans_ids.add(shape_trans_id)
            if table_name == "sprite_occurrence":
                sprite_id = row_data.get("sprite_unique_id")
                sprite_trans_id = row_data.get("sprite_transformation_id")
                if sprite_id is not None:
                    relevant_sprite_ids.add(sprite_id)
                if sprite_trans_id is not None:
                    relevant_sprite_trans_ids.add(sprite_trans_id)

    for tbl in ["object_analysis", "shape_occurrence", "sprite_occurrence", "sprite_analysis"]:
        process_occurrence_table(tbl)

    # 🧩 3. Join tables WITHOUT isInsideInput but filtered by previous ids
    def process_joined_table(table_name, allowed_ids: set):
        rows = tables.get(table_name, {})
        for row_id, row_data in rows.items():
            if row_id not in allowed_ids:
                continue
            for col, val in row_data.items():
                if is_excluded_column(col):
                    continue
                key = f"{table_name}#{row_id}.{col}"
                for key_id in values_by_input:
                    values_by_input[key_id][key] = _sanitize_binding_value(val)

    process_joined_table("shape", relevant_shape_ids)
    process_joined_table("shape_transformation", relevant_shape_trans_ids)
    process_joined_table("sprite_unique", relevant_sprite_ids)
    process_joined_table("sprite_transformation", relevant_sprite_trans_ids)

    return values_by_input

def build_attributes_by_input_and_values(values_by_input: dict[str, dict[str, int]]) -> dict[str, dict[int, list[str]]]:
    attributes_by_input_and_values = {}

    for input_key, attr_map in values_by_input.items():
        value_to_attrs = defaultdict(list)
        for attr, val in attr_map.items():
            if isinstance(val, (int, float)):  # ignore non-numeric (just in case)
                value_to_attrs[val].append(attr)
        attributes_by_input_and_values[input_key] = dict(value_to_attrs)

    return attributes_by_input_and_values


def extract_common_attribute_action_old_to_remove(
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

    print("==> 1) Group & dedupe values by train")
    values_by_train: Dict[int, List[int]] = {}
    for train_id, value in pairs:
        values_by_train.setdefault(train_id, []).append(value)
    print("    values_by_train:", values_by_train)

    print("\n==> 2) Compute per-train common columnNames (after the dot)")
    per_train_common: Dict[int, set] = {}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key, {})
        print(f"  Train {train_id}, attr_map keys: {list(attr_map.keys())}")

        common_for_train: Optional[set] = None
        for v in dict.fromkeys(vals):
            raw = attr_map.get(v, [])
            cols = set()
            for full in raw:
                if "." not in full:
                    continue
                table_row, col = full.split(".", 1)
                table_name = table_row.split("#", 1)[0]
                if table_name == "sprite_analysis":
                    cols.add(col)
            print(f"    Value {v} → filtered columns: {cols}")

            if common_for_train is None:
                common_for_train = cols
            else:
                common_for_train &= cols

            if not common_for_train:
                print("    → No overlap within this train → returning None")
                return None

        per_train_common[train_id] = common_for_train  # type: ignore
    print("    per_train_common:", per_train_common)

    print("\n==> 3) Intersect across trains")
    cols = set.intersection(*per_train_common.values())
    if not cols:
        print("    → No common columns across trains → returning None")
        return None

    # prioritize `path` first
    if path in cols:
        rest = sorted(cols - {path})
        common_columns = [path] + rest
    else:
        common_columns = sorted(cols)

    print("    common_columns (prioritized):", common_columns)

    # Early getAttributeAction si l'attribut existe dans first_sight_analysis
    fsample = next(iter(tables.get("first_sight_analysis", {}).values()), {})
    for col in common_columns:
        if col in fsample:
            print(f"\n==> Early return: single first_sight_analysis column '{col}'")
            return {
                "type": "getAttributeAction",
                "attribute": f"first_sight_analysis.{col}"
            }

    # Early getAttributeAction if exactly one direct column
    #sprite_sample = next(iter(tables.get("sprite_analysis", {}).values()), {})
    #if len(common_columns) == 1 and common_columns[0] in sprite_sample:
    #    col = common_columns[0]
    #    print(f"\n==> Early return: single direct sprite_analysis column '{col}'")
    #    return {
    #        "type": "getAttributeAction",
    #        "attribute": f"sprite_analysis.{col}"
    #    }

    print("\n==> 4) Build per-train list of table#rowId for those columns")
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
        print(f"  Train {train_id} rows:", per_train_rows[train_id])

    print("\n==> 5) Resolve sprite_occurrence → sprite_analysis IDs")
    sprite_occ = tables.get("sprite_occurrence", {})
    occ2sprite = {rid: row["sprite_id"] for rid,row in sprite_occ.items()}
    print("    occ2sprite map size:", len(occ2sprite))

    print("\n==> 6) Collapse to sprite IDs per train")
    sprite_ids_by_train: Dict[str, List[int]] = {}
    for train_id, rows in per_train_rows.items():
        sids = set()
        for tr in rows:
            if "#" not in tr:
                continue
            table, id_str = tr.split("#",1)
            rid = int(id_str)
            if table == "sprite_analysis":
                sids.add(rid)
            elif table == "sprite_occurrence":
                target = occ2sprite.get(rid)
                if target is not None:
                    sids.add(target)
        key = f"{train_id}#-1"
        sprite_ids_by_train[key] = sorted(sids)
        print(f"  {key} → raw sprite IDs:", sprite_ids_by_train[key])

    print("\n==> 7) Deduplicate by sprite data per train")
    deduped: Dict[str, List[int]] = {}
    for key, sids in sprite_ids_by_train.items():
        seen, uniq = set(), []
        for sid in sids:
            data = tables["sprite_analysis"][sid]["data"]
            if data not in seen:
                seen.add(data)
                uniq.append(sid)
        deduped[key] = uniq
        print(f"  {key} → deduped sprite IDs:", uniq)

    print("\n==> 8) Find most‐alike sprite pairs")
    groups = group_similar_sprites_by_attributes(common_columns, deduped, tables)
    print("    Most-alike pairs:", groups)

    print("\n==> 9) Build negatives = input-only sprites in these trains")
    train_ids = [int(k.split("#",1)[0]) for k in deduped]
    all_sprites = [
        sid for sid,row in tables["sprite_analysis"].items()
        if row["trainId"] in train_ids and row.get("isInsideInput") == 1
    ]
    print("    all_sprites (negatives):", all_sprites)

    print("\n==> 10) Search minimal distinguishing criteria for each group")
    for group in groups:
        if any(sid is None for sid in group):
            print(f"    🔹 Skipping incomplete group {group}")
            continue
        crit = find_minimal_selection_criteria_for_table(group, all_sprites, tables, table_key="sprite_analysis")
        print(f"    Group {group} → criteria: {crit}")
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
            print("\n==> Returning select action:", action)
            return action

    # --- FALLBACK: object‐level grouping using the same 5–10 pipeline ---
    print("==> No sprite‐level action found, falling back to object‐level grouping")

    # 5) Build per‐train list of object_analysis / object_occurrence row IDs,
    #    in the exact order of common_columns
    per_train_rows_obj = {tid: [] for tid in values_by_train}
    for train_id, vals in values_by_train.items():
        key = f"{train_id}#-1"
        attr_map = attributes_by_input_and_values.get(key, {})

        # for each column in priority order…
        for col in common_columns:
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

    print("    per_train_rows_obj (prioritized):", per_train_rows_obj)

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
        print(f"  {key} → raw object IDs (ordered):", ordered)

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
        print(f"  {key} → deduped object IDs:", uniq)

    # 9) Build all candidate object‐groups via Cartesian product
    from itertools import product
    train_keys   = sorted(deduped_obj.keys())                # e.g. ["0#-1","1#-1","2#-1"]
    per_id_lists = [deduped_obj[k] for k in train_keys]      # e.g. [[2], [4], [5,6]]
    groups_obj   = list(product(*per_id_lists))
    print("    Candidate object groups:", groups_obj)

    # 10) Build negatives = all input‐only objects
    train_ids = [int(k.split("#",1)[0]) for k in deduped_obj]
    all_objects = [
        oid for oid,row in tables["object_analysis"].items()
        if row.get("trainId") in train_ids and row.get("isInsideInput") == 1
    ]
    print("    all_objects (negatives):", all_objects)

    # 11) Find minimal distinguishing criteria per object‐group
    for group in groups_obj:
        if any(sid is None for sid in group):
            continue
        crit = find_minimal_selection_criteria_for_table(
            group, all_objects, tables, table_key="object_analysis"
        )
        print(f"    Object group {group} → criteria: {crit}")
        if crit:
            # choose an output_attr (fall back to path if no exact match)
            obj_sample = next(iter(tables["object_analysis"].values()), {})
            output_attr = path if path in obj_sample else crit[0][0]
            action = {
                "type":             "selectObjectAndAttributeAction",
                "criteria":         crit,
                "output_attribute": output_attr,
                "for_objects":      list(group)
            }
            print("==> Returning selectObjectAndAttributeAction:", action)
            return action

    print("==> No object‐level group matched either → returning None")
    return None



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
        print("⚠️ sprite_analysis vide")
        return []
    sample = next(iter(sprite_tbl.values()))
    valid_cols = [c for c in common_columns if c in sample]
    if not valid_cols:
        print("⚠️ Pas de colonne commune:", common_columns)
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
) -> List[Tuple[str, Any]]:
    """
    Find a minimal set of (column,value) tests that include all group IDs (positives)
    and exclude all other IDs (negatives), but only searching over columns that
    are constant in the positives and actually discriminate them from negatives.
    """
    tbl = tables.get(table_key, {})
    if not tbl:
        return []

    # split positives/negatives
    positives = {sid for sid in group if sid is not None}
    negatives = set(all_ids) - positives
    if not positives or not negatives:
        return []

    # all columns in the table
    sample = next(iter(tbl.values()))
    all_cols = list(sample.keys())

    # 1) keep only columns constant in positives
    constant_cols = []
    for col in all_cols:
        vals = {tbl[sid][col] for sid in positives}
        if len(vals) == 1:
            constant_cols.append(col)

    # 2) from those, keep only columns that at least one negative fails
    discriminating_cols = []
    for col in constant_cols:
        val = tbl[next(iter(positives))][col]
        if any(tbl[n][col] != val for n in negatives):
            discriminating_cols.append((col, val))

    # if nothing discriminates at all, give up
    if not discriminating_cols:
        return []

    # 3) try single‐column criteria first
    return discriminating_cols
    #for col, val in discriminating_cols:
    #    return [(col, val)]

    # (Optional) 4) if you really need multi‐column criteria, try pairs
    #    but only on the small discriminating subset
    if len(discriminating_cols) > 1:
        cols_only = [col for col, _ in discriminating_cols]
        for a, b in combinations(cols_only, 2):
            # both must be constant in positives
            v1 = tbl[next(iter(positives))][a]
            v2 = tbl[next(iter(positives))][b]
            # check that no negative matches both
            if all(not (tbl[n][a] == v1 and tbl[n][b] == v2) for n in negatives):
                return [(a, v1), (b, v2)]

    # fallback: no minimal criteria found
    return []



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
                print(f"no common column **names** in this train, bail out")
                return []

        per_train_common[train_id] = common_for_train  # type: ignore

    # 3) cross-train intersection
    common_attrs = set.intersection(*per_train_common.values()) if per_train_common else set()
    if not common_attrs:
        print(f"not common_attrs")
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
    for col in sorted(common_attrs):
        rows = sorted(set(col_to_rows.get(col, [])))
        print(f"{col} → {rows}")
        #print(f"{col}")

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
    if( path == "minX"):
        print("common_attributes_by_train_value_pairs")
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

def build_colors_by_input(db_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Returns a dict:
      key = "trainId#testId"
      value = { attribute_name: attribute_value, ... }
    Aggregates from:
      - first_sight_analysis (the 4 most/least‐color columns)
      - object_analysis via shape_occurrence
      - sprite_analysis
      - sprite_transformation
      - sprite_unique via sprite_occurrence
    """
    tables = load_all_tables_from_sqlite(db_path)
    colors_by_input = defaultdict(dict)

    # 1) first_sight_analysis: grab the 8 color metrics
    fsa = tables.get("first_sight_analysis", {})
    color_cols = [
        "firstMostColorInput", "secondMostColorInput",
        "firstLeastColorInput","secondLeastColorInput"
    ]
    for row_id, row in fsa.items():
        train_id, test_id = row.get("trainId", -1), row.get("testId", -1)
        if train_id == -1 and test_id == -1:
            continue
        key = f"{train_id}#{test_id}"
        for col in color_cols:
            if col in row and row[col] is not None:
                colors_by_input[key][f"first_sight_analysis.{col}"] = row[col]

    # 2) object_analysis via shape_occurrence (to filter by isInsideInput & get train/test)
    object_rows = tables.get("object_analysis", {})
    for so_id, so in tables.get("shape_occurrence", {}).items():
        if not so.get("isInsideInput"):
            continue
        key = f"{so['trainId']}#{so['testId']}"
        obj_id = so["object_id"]                  # this is the object_analysis row id
        oa = object_rows.get(obj_id, {})
        for col in ("color","orthoNeighborColorList","diagNeighborColorList","neighborColorList"):
            if col in oa:
                colors_by_input[key][f"object_analysis#{obj_id}.{col}"] = oa[col]

    # 3) sprite_analysis
    for row_id, row in tables.get("sprite_analysis", {}).items():
        if not row.get("isInsideInput"):
            continue
        key = f"{row['trainId']}#{row['testId']}"
        if 'bgColor' in row:
            colors_by_input[key][f"sprite_analysis#{row_id}.bgColor"] = row['bgColor']

    # 4) sprite_transformation
    for row_id, row in tables.get("sprite_transformation", {}).items():
        if "recolored" not in row:
            continue
        t_train, t_test = row.get("trainId"), row.get("testId")
        if t_train is None or t_test is None:
            continue
        key = f"{t_train}#{t_test}"
        colors_by_input[key][f"sprite_transformation#{row_id}.recolored"] = row["recolored"]

    # 5) sprite_unique via sprite_occurrence
    sprite_unique_rows = tables.get("sprite_unique", {})
    for so_id, so in tables.get("sprite_occurrence", {}).items():
        if not so.get("isInsideInput"):
            continue
        key = f"{so['trainId']}#{so['testId']}"
        su = sprite_unique_rows.get(so["sprite_unique_id"], {})
        for col in ("colorPresent","colorAbsent","colorOrder","colorMost","colorLeast"):
            if col in su:
                colors_by_input[key][f"sprite_unique#{so_id}.{col}"] = su[col]

    #print("colors_by_input")
    #print(colors_by_input)

    return colors_by_input


def build_attributes_by_input_and_colors(
    colors_by_input: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[Any, List[str]]]:
    def _flatten(vals: Iterable) -> Iterable:
        for v in vals:
            if isinstance(v, (list, tuple)):
                yield from _flatten(v)
            else:
                yield v

    attributes_by_input_and_colors: Dict[str, Dict[Any, List[str]]] = {}

    for input_key, color_map in colors_by_input.items():
        value_to_attrs: Dict[Any, List[str]] = defaultdict(list)

        # same parsing / flattening you already have:
        for attr_name, color_val in color_map.items():
            if isinstance(color_val, str):
                try:
                    parsed = json.loads(color_val)
                except json.JSONDecodeError:
                    parsed = color_val
            else:
                parsed = color_val

            if isinstance(parsed, (list, tuple)):
                for cv in _flatten(parsed):
                    value_to_attrs[cv].append(attr_name)
            else:
                value_to_attrs[parsed].append(attr_name)

        # *** NEW: prioritize sprite_unique.colorMost ***
        PRIORITY = "sprite_unique.colorMost"
        for cv, attrs in value_to_attrs.items():
            if PRIORITY in attrs:
                idx = attrs.index(PRIORITY)
                # move it to front
                attrs.insert(0, attrs.pop(idx))

        attributes_by_input_and_colors[input_key] = dict(value_to_attrs)

    return attributes_by_input_and_colors