import sqlite3
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
        #"first_sight_analysis",
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