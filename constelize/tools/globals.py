# constelize/tools/globals.py

from typing import List, Dict, Any

from constelize.core.scenario import Scenario

all_scenarios: List[Scenario] = []

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
