import os
from collections import defaultdict

from constelize.core.scenario import Scenario
from constelize.tools import globals as GLOBAL

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def filter_successful_procedures(train_results: list[dict]) -> list[str]:
    """
    Returns the list of procedure_ids that passed on all train results.
    Adds logging for each procedure's status.
    """
    success_map = defaultdict(list)
    for r in train_results:
        pid = r["procedure_id"]
        success = r["success"]
        success_map[pid].append(success)

    successful_pids = []
    for pid, results in success_map.items():
        if all(results):
            print(f"✅ Procedure '{pid}' succeeded on all {len(results)} train examples.")
            successful_pids.append(pid)
        else:
            print(f"❌ Procedure '{pid}' failed on some train examples: {results}")
    return successful_pids

def filter_successful_rules(scenario) -> list[str]:
    """
    Returns the list of rule_ids in the scenario that have at least one procedure
    that succeeded on all examples.
    Logs which rules pass or fail.
    """
    successful = []
    print(f"\n🔍 Evaluating scenario '{scenario.id}' with {len(scenario.rules)} rules.")
    for rule_id, rule in scenario.rules.items():
        passed = filter_successful_procedures(rule.train_results)
        if passed:
            print(f"✅ Rule '{rule_id}' has at least one successful procedure: {passed}")
            successful.append(rule_id)
        else:
            print(f"❌ Rule '{rule_id}' has no successful procedures.")
    return successful

def filter_successful_scenarios() -> list[Scenario]:
    """
    Returns the list of scenario_ids where at least one rule has a successful procedure.
    Logs scenario-level success/failure.
    """
    successful_scenarios = []
    print("\n📋 Starting evaluation of all scenarios...")
    for scenario in GLOBAL.all_scenarios:
        ok_rules = filter_successful_rules(scenario)
        if ok_rules:  # ✅ changed from full match to at least one
            print(f"🎯 Scenario '{scenario.id}' is SUCCESSFUL — passed rules: {ok_rules}")
            successful_scenarios.append(scenario)
        else:
            print(f"🛑 Scenario '{scenario.id}' is INCOMPLETE — no rules passed.")
    return successful_scenarios