# scripts/verify_task.py
import argparse
import copy
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

import constelize.tools.globals as GLOBAL
import constelize.library.attribute_access as _aa_mod
import constelize.tools.binding_train_map as btm
from constelize.core.binding import BindingStatus, ArgumentBinding
from constelize.core.procedure import Procedure
from constelize.core.rule import Rule
from constelize.core.scenario import Scenario
from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json, load_json_inputs_from_json
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    evaluate_generic_procedures,
    load_arc_json, generate_submission_file, compare_submission_to_arc_outputs, print_test_results,
    generate_action_instances_from_db, evaluate_generic_procedures_on_scenarios, print_test_results_by_scenario,
    generate_submission_file_from_scenarios, preprocess_arc_with_action,
)
from constelize.tools.sqlite_loader import build_values_by_input, \
    build_attributes_by_input_and_values
from constelize.tools.squeeze import normalize_procedures_with_levels, squeeze_with_unresolved
from scripts.verify_utils import filter_successful_procedures, SCRIPT_DIR, filter_successful_scenarios

PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

start_time = time.time()

_unique_scenario_id = 0
def getUniqueScenarioId() -> str:
    global _unique_scenario_id
    _unique_scenario_id += 1
    return str(_unique_scenario_id)

_unique_rule_id = 0
def getUniqueRuleId() -> str:
    global _unique_rule_id
    _unique_rule_id += 1
    return str(_unique_rule_id)

def validate_get_start_input_usage(procedures):
    for proc in procedures:
        for step in proc.steps.values():
            if step.action and step.action.id == "get_start_input":
                if not step.used_by:
                    print(f"⚠️ Warning: 'get_start_input' step {step.id} is not used by any other action in {proc.id}!")


def run_analysis_scripts(
    json_source: str,
    *,
    inline: bool = False,
    name: str | None = None
):
    """
    Invoke the three analysis scripts on either:
      - a file path (inline=False), or
      - a raw JSON string  (inline=True).
    Optionally override the “filename” each one sees via --name.
    """
    scripts = {
        "first_sight": os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py"),
        "object"     : os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py"),
        "sprite"     : os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py"),
    }

    for which, script_path in scripts.items():
        cmd = [sys.executable, script_path, json_source]
        if inline:
            cmd.append("--inline")
        if name:
            cmd.extend(["--name", name])

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            print(f"⚠️ Analysis script not found: {script_path}; skipping.")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Analysis script {which} exited with code {e.returncode}; continuing.")

def split_action_instances_in_scenarios(action_instances, current_scenario):
    # 1) Collect all trainIds
    train_ids = {inst.trainId for inst in action_instances if inst.isTrain}

    # 2) Bucket the flagged instances by action.id
    by_in_separate_rule_action = defaultdict(list)
    for inst in action_instances:
        if inst.IN_SEPARATE_RULE:
            by_in_separate_rule_action[inst.action.id].append(inst)

    # 3) Only keep those whose bucket covers *every* train
    pre_groups = {
        aid: insts
        for aid, insts in by_in_separate_rule_action.items()
        if {i.trainId for i in insts} == train_ids
    }

    # 4) Everything else stays in the “rest”
    rest = [inst for inst in action_instances
            if inst.action.id not in pre_groups]

    for action_id, instances in pre_groups.items():
        rule_by_separate_action = Rule(id=f"rule_pre_{action_id}_{getUniqueRuleId()}")
        rulePreId = rule_by_separate_action.id
        scenario_by_separate_action = Scenario(
            id=f"scenario_{action_id}_{getUniqueScenarioId()}",
            rules={rule_by_separate_action.id: rule_by_separate_action}
        )
        scenarioId = scenario_by_separate_action.id
        all_proc_train = []
        for inst in instances:
            steps = {inst.id: inst}
            proc_train = Procedure(id=f"proc_pre_{action_id}_train_{inst.trainId}", steps=steps, scenarioId=scenarioId, ruleId=rulePreId)
            all_proc_train.append(proc_train)
        generic_procs = squeeze_with_unresolved(all_proc_train, scenarioId, rulePreId)
        generic_proc = generic_procs[0]
        generic_action = next(iter(generic_proc.steps.values()))
        generic_proc.action_producing_output = generic_action
        rule_by_separate_action.procedures = generic_procs
        rule_by_separate_action.generic_procs = generic_procs
        rule_by_separate_action.proc_producing_output = generic_proc
        rule_main = Rule(id=f"rule_main_{getUniqueRuleId()}")
        ruleMainId = rule_main.id
        rule_main.rule_producing_input = rule_by_separate_action
        scenario_by_separate_action.rules = {
            rulePreId: rule_by_separate_action,
            ruleMainId: rule_main
        }
        scenario_by_separate_action.rule_to_launch_before = rule_by_separate_action
        scenario_by_separate_action.rule_to_analyse = rule_main
        current_scenario.to_launch_next.append(scenario_by_separate_action)
        GLOBAL.all_scenarios.append(scenario_by_separate_action)
    return rest

def test_file(json_path, db_path, results_path, submission_path, comparison_path, task_id, trainings_number):
    first_rule = Rule( id=f"rule_{getUniqueRuleId()}")
    first_scenario = Scenario(
        id=f"scenario_{getUniqueScenarioId()}",
        rules={first_rule.id: first_rule},  # map rule ID → Rule instance
    )
    GLOBAL.all_scenarios.append(first_scenario)

    raw_json = open(json_path).read()
    load_end_outputs_from_json(json_path)
    load_json_inputs_from_json(json_path)
    data = load_arc_json(json_path)

    btm.TOTAL_TRAINS = len(data.get("train", []))
    btm.ALL_TRAIN_IDS = set(range(btm.TOTAL_TRAINS))

    generate_scenarios_and_rules(first_scenario, first_rule, data, db_path, json_path, raw_json, results_path)

    # pick the scenarios that fully succeeded
    valid_scenario = filter_successful_scenarios()

    if valid_scenario:
        print("🎯 At least one scenario with generic procedure passed all training examples. Running on test set...")
        results_by_scenario = evaluate_generic_procedures_on_scenarios("test", data, valid_scenario)
        print_test_results_by_scenario(results_by_scenario, results_path, data)
        generate_submission_file_from_scenarios(task_id, valid_scenario, data, submission_path, results_by_scenario)
        compare_submission_to_arc_outputs(task_id, data, submission_path, comparison_path)
    else:
        print("⚠️ No fully successful generic procedure found. Skipping test execution.")

    total_time = time.time() - start_time
    print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")
    print("✅ Evaluation completed. Results saved to", results_path)

    # return True if tests ran (even partially), False only if no valid train‐proc
    return bool(valid_scenario)


def generate_scenarios_and_rules(current_scenario, current_rule, data, db_path, json_path, raw_json, results_path):
    scenarioId = current_scenario.id
    ruleId = current_rule.id
    run_analysis_scripts(raw_json, inline=True, name=json_path)
    # 2) inject the sqlite‐derived attributes
    _values = build_values_by_input(db_path)
    _attrs = build_attributes_by_input_and_values(_values)
    _aa_mod._values_by_input = _values
    _aa_mod._attributes_by_input_and_values = _attrs
    print(f"[verify_task] Injected attributes: {len(_attrs)} entries")
    current_rule.values_by_input = _values
    current_rule.attributes_by_input_and_values = _attrs
    print(f"\n📥 [generate_draft_procedure] Loading from DB: {db_path} and JSON: {json_path}")
    action_instances = generate_action_instances_from_db(db_path, scenarioId, ruleId)
    rest_action_instances = split_action_instances_in_scenarios(action_instances, current_scenario)
    procedures = generate_draft_procedure(rest_action_instances, data, scenarioId, ruleId)
    # debug: list initial steps
    print("\n📦 [Post generate_draft_procedure] Listing initial steps:")
    for proc_id, proc in procedures.items():
        print(f"  🔸 {proc_id} has {len(proc.steps)} steps")
        for step in proc.steps.values():
            print(f"    • {step.id} ({step.action.id})")
    # normalize + squeeze + deep copy
    normalized_procs = normalize_procedures_with_levels(list(procedures.values()), scenarioId, ruleId)
    generic_with_unresolved = squeeze_with_unresolved(normalized_procs, scenarioId, ruleId)
    generic_procs = copy.deepcopy(generic_with_unresolved)
    # === EVALUATION & PRUNING on TRAIN ===
    train_results = evaluate_generic_procedures("train", generic_procs, data, scenarioId, ruleId)
    # write training results
    with open(results_path, "w") as f:
        f.write("✅ TRAINING RESULTS:\n")
        for r in train_results:
            status = "✅" if r["success"] else "❌"
            f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")
    current_rule.procedures = normalized_procs
    current_rule.generic_procs = generic_procs
    current_rule.train_results = train_results
    successful = filter_successful_procedures(train_results)
    if not successful:
        print("❌ No successful procedures found.")
        for scenario in current_scenario.to_launch_next:
            print(f"scenario to launch next: {scenario.id}")
            pre_rule = scenario.rule_to_launch_before
            generic_proc = pre_rule.proc_producing_output
            action_inst = generic_proc.action_producing_output
            new_arc_data = preprocess_arc_with_action(data, action_inst)
            new_raw_json = json.dumps(new_arc_data)
            mem_path = scenario.id
            print(f"new_raw_json: {new_raw_json}")
            generate_scenarios_and_rules(
                scenario,
                scenario.rule_to_analyse,
                new_arc_data,  # ← the in-memory ARC dict
                db_path,
                mem_path,
                new_raw_json,  # ← the JSON‐string version
                results_path
            )


if __name__ == "__main__":
    # ---- ARG PARSING & PATH SETUP ----
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_id", help="ARC task ID, e.g., 3c9b0459")
    args = parser.parse_args()

    # Training 1
    #DEFAULT_TASK_ID = "3c9b0459"
    #DEFAULT_TASK_ID = "9dfd6313"
    #DEFAULT_TASK_ID = "67a3c6ac"
    #DEFAULT_TASK_ID = "68b16354"
    #DEFAULT_TASK_ID = "74dd1130"
    #DEFAULT_TASK_ID = "6150a2bd"
    #DEFAULT_TASK_ID = "9172f3a0"
    #DEFAULT_TASK_ID = "a416b8f3"
    #DEFAULT_TASK_ID = "b1948b0a"
    #DEFAULT_TASK_ID = "c8f0f002"
    #DEFAULT_TASK_ID = "c59eb873"
    #DEFAULT_TASK_ID = "d10ecb37"
    #DEFAULT_TASK_ID = "d511f180"
    #DEFAULT_TASK_ID = "ed36ccf7"

    # Training 2
    #DEFAULT_TASK_ID = "4c4377d9"
    #DEFAULT_TASK_ID = "6d0aefbc"
    #DEFAULT_TASK_ID = "6fa7a44f"
    #DEFAULT_TASK_ID = "5614dbcf_zoom_out"
    DEFAULT_TASK_ID = "5614dbcf"
    #DEFAULT_TASK_ID = "5bd6f4ac"
    #DEFAULT_TASK_ID = "5582e5ca"
    #DEFAULT_TASK_ID = "8be77c9e"
    #DEFAULT_TASK_ID = "c9e6f938"
    #DEFAULT_TASK_ID = "2dee498d"

    TASK_ID = args.task_id if args.task_id else DEFAULT_TASK_ID
    trainings_number = 2

    PROJECT_ROOT     = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    db_path          = os.path.join(PROJECT_ROOT, "db", "database.db")
    json_path        = os.path.join(PROJECT_ROOT, "pattern-finder", "data", f"training-{trainings_number}", f"{TASK_ID}.json")
    results_path     = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_results.txt")
    submission_path  = os.path.join(PROJECT_ROOT, "results", "submission.json")
    comparison_path  = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_comparison.txt")

    success = test_file(json_path, db_path, results_path, submission_path, comparison_path, TASK_ID, trainings_number)
