import sqlite3
from collections import defaultdict
from typing import Dict, Any

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
                values_by_input[key_id][f"first_sight_analysis.{col}"] = row_data[col]

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
                values_by_input[key_id][f"{table_name}#{row_id}.{col}"] = val
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
                    values_by_input[key_id][key] = val

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

def common_attributes_by_train_value_pairs(
    attributes_by_input_and_values: dict[str, dict[int, list[str]]],
    pairs: list[tuple[int, int]]
) -> list[str]:
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

# Example usage:
if __name__ == "__main__":
    db_path = "../../db/database.db"
    values_by_input = build_values_by_input(db_path)
    attributes_by_input_and_values = build_attributes_by_input_and_values(values_by_input)

    # Visualisation rapide
    #for key, val_map in attributes_by_input_and_values.items():
    #    print(f"\n📦 For {key}:")
    #    for val, attrs in val_map.items():
    #        print(f"  🔢 {val}: {attrs}")

    # Test: attributs communs avec des valeurs différentes par train
    print("\n🔍 Testing common_attributes_by_train_value_pairs...")
    test_pairs = [(0, 3), (1, 3), (2, 4)]  # à adapter selon ton jeu de données
    common_attrs = common_attributes_by_train_value_pairs(attributes_by_input_and_values, test_pairs)

    print(f"\n✅ Common attributes for: {test_pairs}")
    for attr in common_attrs:
        print(f"   • {attr}")
