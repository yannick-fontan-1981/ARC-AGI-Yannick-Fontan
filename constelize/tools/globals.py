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