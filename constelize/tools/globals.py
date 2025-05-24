# constelize/tools/globals.py
import json
from typing import List, Dict, Any, Tuple

from constelize.core.scenario import Scenario
from constelize.dsl.grid_dsl import to_concrete_grid

all_scenarios: List[Scenario] = []


def load_sprite_analysis_table(
    scenarioId: str,
    ruleId: str
) -> Dict[int, Dict[str, Any]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    'sprite_analysis' table (indexed by id). If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                # rule.tables was populated by load_all_tables_from_sqlite
                return rule.tables.get("sprite_analysis", {})
    return {}

def load_object_analysis_table(
    scenarioId: str,
    ruleId: str
) -> Dict[int, Dict[str, Any]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    'object_analysis' table (indexed by id). If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                # rule.tables was populated by load_all_tables_from_sqlite
                return rule.tables.get("object_analysis", {})
    return {}

def get_values_by_scenario_rule(scenarioId: str, ruleId: str) -> Dict[str, Dict[str, int]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    `values_by_input` map.  If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                return rule.values_by_input
    return {}

def get_attributes_by_scenario_rule(scenarioId: str, ruleId: str) -> Dict[str, Dict[int, List[str]]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    `attributes_by_input_and_values` map.  If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                return rule.attributes_by_input_and_values
    return {}

def get_colors_by_scenario_rule(scenarioId: str, ruleId: str) -> Dict[str, Dict[str, Any]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    `colors_by_input` map. If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                return rule.colors_by_input
    return {}


def get_attributes_colors_by_scenario_rule(scenarioId: str, ruleId: str) -> Dict[str, Dict[int, List[str]]]:
    """
    Look up the Scenario with the given ID, then return that Rule’s
    `attributes_by_input_and_colors` map.  If not found, return an empty dict.
    """
    for scen in all_scenarios:
        if scen.id == scenarioId:
            rule = scen.rules.get(ruleId)
            if rule is not None:
                return rule.attributes_by_input_and_colors
    return {}

def build_object_data_id_map(
    scenarioId: str,
    ruleId:     str
) -> Dict[int, Dict[Tuple[Tuple[int, ...], ...], int]]:
    """
    Return a map from each trainId to its objects’ shape patterns → object_analysis.id.
    Each shape pattern is the minimal bounding patch with non-object cells as -1.

    Steps:
     1. Fetch object_analysis table: id → { "trainId", "data", "color" }.
     2. Parse `data` JSON into list of absolute coordinates.
     3. For each object, compute its bounding box from coords.
     4. Build a patch grid of size (height×width), fill -1, then set object pixels.
     5. Convert to tuple-of-tuples as dict key, grouped by trainId.
    """
    obj_tbl = load_object_analysis_table(scenarioId, ruleId)
    object_data_id_map: Dict[int, Dict[Tuple[Tuple[int, ...], ...], int]] = {}

    for oid, row in obj_tbl.items():
        if int(row.get("isInsideInput", 0)) != 1:
            continue
        train_id = int(row.get("trainId", -1))
        if train_id == -1:
            continue
        data_json = row.get("data")
        if not data_json:
            continue

        # parse JSON into Python list of [r, c]
        coords_abs: List[Tuple[int,int]] = json.loads(data_json)
        if not coords_abs:
            continue

        # compute bounding box from coords
        rows_coord = [r for r, _ in coords_abs]
        cols_coord = [c for _, c in coords_abs]
        min_r, max_r = min(rows_coord), max(rows_coord)
        min_c, max_c = min(cols_coord), max(cols_coord)
        height = max_r - min_r + 1
        width  = max_c - min_c + 1
        color = int(row.get("color", 0))

        # build minimal patch grid with -1 padding
        patch = [[-1 for _ in range(width)] for _ in range(height)]
        for r, c in coords_abs:
            local_r = r - min_r
            local_c = c - min_c
            patch[local_r][local_c] = color

        # freeze to tuple-of-tuples for hashing
        grid_key = tuple(tuple(row_vals) for row_vals in patch)
        object_data_id_map.setdefault(train_id, {})[grid_key] = oid

    return object_data_id_map

def build_sprite_data_id_map(
    scenarioId: str,
    ruleId:     str
) -> Dict[Tuple[Tuple[int, ...], ...], int]:
    """
    Return a map from each sprite’s **concrete grid** (as a tuple-of-tuples)
    to its sprite_analysis.id, so you can go from your (trainId, rawGrid)
    pairs directly to (trainId, sprite_analysis_id).

    Steps:
     1. Fetch sprite_analysis table: id → { ..., "data": JSON(grid) }.
     2. Parse the JSON into a Python structure.
     3. Convert to the concrete Grid (list-of-lists) via to_concrete_grid.
     4. Reify as a tuple-of-tuples for use as a dict key.
    """
    sprite_tbl = load_sprite_analysis_table(scenarioId, ruleId)
    sprite_data_id_map: Dict[Tuple[Tuple[int, ...], ...], int] = {}

    for sa_id, row in sprite_tbl.items():
        if not row.get("isInsideInput", False):
            continue

        data_json = row.get("data")
        if data_json is None:
            continue

        # 2) Parse JSON into Python (likely list-of-lists of ints)
        raw_payload = json.loads(data_json)

        # 3) Convert into your concrete Grid representation
        concrete = to_concrete_grid(raw_payload)

        # 4) Turn the 2D list into a hashable tuple-of-tuples
        grid_key = tuple(tuple(r) for r in concrete)

        sprite_data_id_map[grid_key] = sa_id

    return sprite_data_id_map