# scripts/verify_task.py
import argparse
import copy
import json
import os
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from typing import Set, Tuple, List, Iterable, Mapping

from joblib._multiprocessing_helpers import mp

import constelize.tools.globals as GLOBAL
import constelize.library.attribute_access as _aa_mod
import constelize.tools.binding_train_map as btm
from constelize.core.binding import BindingStatus, ArgumentBinding
from constelize.core.procedure import Procedure, ActionInstance
from constelize.core.rule import Rule
from constelize.core.scenario import Scenario
from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json, load_json_inputs_from_json
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    evaluate_generic_procedures,
    load_arc_json, generate_submission_file, compare_submission_to_arc_outputs, print_test_results,
    generate_action_instances_from_db, evaluate_generic_procedures_on_scenarios, print_test_results_by_scenario,
    generate_submission_file_from_scenarios, preprocess_arc_with_action, compute_get_start_input,
    compute_buffer_and_repaint,
)
from constelize.tools.sqlite_loader import build_values_by_input, \
    build_attributes_by_input_and_values, build_colors_by_input, build_attributes_by_input_and_colors, \
    load_all_tables_from_sqlite
from constelize.tools.squeeze import normalize_procedures_with_levels, squeeze_with_unresolved
from scripts.verify_utils import filter_successful_procedures, SCRIPT_DIR, filter_successful_scenarios

class TimeoutException(Exception):
    """Raised when an operation exceeds its time limit."""
    pass

# ← module‐level, picklable target
def _timeout_target(queue, fn, args, kwargs):
    try:
        result = fn(*args, **kwargs)
        queue.put((True, result))
    except Exception as e:
        queue.put((False, e))

def run_with_timeout(fn, *args, timeout=30, **kwargs):
    """
    Runs fn(*args, **kwargs) in a child process, killing it
    if it runs longer than `timeout` seconds.
    """
    q = mp.Queue()
    # note: _timeout_target is at module top‐level now
    p = mp.Process(target=_timeout_target, args=(q, fn, args, kwargs))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join()
        raise TimeoutException(f"operation exceeded {timeout} seconds")
    success, result = q.get()
    if success:
        return result
    else:
        # re-raise whatever exception happened inside the child
        raise result

# --------------------------------------------------
# Wrapper to load globals and call generation logic
# --------------------------------------------------
def _setup_and_generate(current_scenario, current_rule, data, db_path, json_path, raw_json, results_path):
    # Load inputs/outputs into globals within child
    load_end_outputs_from_json(json_path)
    load_json_inputs_from_json(json_path)
    # Ensure data is current
    data = load_arc_json(json_path)

    btm.TOTAL_TRAINS = len(data.get("train", []))
    btm.ALL_TRAIN_IDS = set(range(btm.TOTAL_TRAINS))

    return generate_scenarios_and_rules(
        current_scenario,
        current_rule,
        data,
        db_path,
        json_path,
        raw_json,
        results_path,
    )

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
        "first_sight"        : os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py"),
        "object"             : os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py"),
        "sprite"             : os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py"),
        "light_cycle"        : os.path.join(PROJECT_ROOT, "pattern-finder", "light_cycle_analysis.py"),
        "cellular_automaton" : os.path.join(PROJECT_ROOT, "pattern-finder", "cellular_automaton_analysis.py"),
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

# --------------------------------------------------
# Main test_file logic without internal timeout
# --------------------------------------------------
def test_file(
    json_path,
    db_path,
    results_path,
    submission_path,
    comparison_path,
    task_id,
    trainings_number
):
    first_rule = Rule(id=f"rule_{getUniqueRuleId()}")
    first_scenario = Scenario(
        id=f"scenario_{getUniqueScenarioId()}",
        rules={first_rule.id: first_rule},
    )
    GLOBAL.all_scenarios.append(first_scenario)

    raw_json = open(json_path).read()
    load_end_outputs_from_json(json_path)
    load_json_inputs_from_json(json_path)
    data = load_arc_json(json_path)

    btm.TOTAL_TRAINS = len(data.get("train", []))
    btm.ALL_TRAIN_IDS = set(range(btm.TOTAL_TRAINS))

    # Call generation directly
    try:
        _setup_and_generate(
            first_scenario,
            first_rule,
            data,
            db_path,
            json_path,
            raw_json,
            results_path,
        )
    except Exception as e:
        print("❌ Exception during scenario/rule generation:")
        print(f"   • Exception type: {type(e).__name__}")
        print(f"   • Message       : {e}")
        # optional: show full stack trace
        traceback.print_exc()
        return False

    valid_scenario = filter_successful_scenarios()

    if not valid_scenario:
        print("⚠️ No fully successful generic procedure found. Skipping test execution.")
        print_total_time(results_path)
        return False

    # At least one generic proc passed training; if there's a test set, compare now
    if valid_scenario:
        print("🎯 Running successful procedure(s) on test set...")
        results_by_scenario = evaluate_generic_procedures_on_scenarios("test", data, valid_scenario)
        print_test_results_by_scenario(results_by_scenario, results_path, data)
        generate_submission_file_from_scenarios(task_id, valid_scenario, data, submission_path, db_path, results_by_scenario)
        # our updated compare now returns True if any attempt succeeded
        compare_result =  compare_submission_to_arc_outputs(task_id, data, submission_path, comparison_path)
        # if any test entry has an "output", return the compare_result,
        # otherwise fall back to valid_scenario
        test_entries = data.get("test", [])
        if isinstance(test_entries, dict):
            has_output = any(e.get("output") is not None for e in test_entries.values())
        else:
            has_output = any(e.get("output") is not None for e in test_entries)
        print_total_time(results_path)
        return compare_result if has_output else valid_scenario
    else:
        # no test outputs available → treat training success as overall success
        print_total_time(results_path)
        return True


def print_total_time(results_path):
    total_time = time.time() - start_time
    print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")
    print("✅ Evaluation completed. Results saved to", results_path)

def generate_scenarios_and_rules(current_scenario, current_rule, data, db_path, json_path, raw_json, results_path):
    scenarioId = current_scenario.id
    ruleId = current_rule.id

    # 1) deserialize the incoming ARC JSON
    payload = json.loads(raw_json)

    # 2) convert your new_sprites (tuple‐of‐tuples) into lists so they're JSON‐serializable
    serial_sprites = {}
    for key, grids in current_scenario.new_sprites.items():
        serial_sprites[key] = []
        for grid in grids:
            # grid is Tuple[Tuple[int,...],...]
            serial_sprites[key].append([list(row) for row in grid])

    # 3) embed under a top‐level field
    payload["new_sprites"] = serial_sprites

    # 4) re‐dump to a single JSON string
    raw_with_sprites = json.dumps(payload)

    run_analysis_scripts(raw_with_sprites, inline=True, name=json_path)

    # 2) inject the sqlite‐derived attributes
    _tables = load_all_tables_from_sqlite(db_path)
    _values = build_values_by_input(db_path)
    _attrs = build_attributes_by_input_and_values(_values)
    _aa_mod._values_by_input = _values
    _aa_mod._attributes_by_input_and_values = _attrs
    _colors = build_colors_by_input(db_path)
    _attrs_color = build_attributes_by_input_and_colors(_colors)
    _aa_mod._colors_by_input = _colors
    _aa_mod._attributes_by_input_and_colors = _attrs_color
    print(f"[verify_task] Injected attributes: {len(_attrs)} entries")
    current_rule.tables = _tables
    current_rule.values_by_input = _values
    current_rule.attributes_by_input_and_values = _attrs
    current_rule.colors_by_input = _colors
    current_rule.attributes_by_input_and_colors = _attrs_color
    #print("_colors")
    #print(_colors)
    #print("_attrs_color")
    #print(_attrs_color)
    print(f"\n📥 [generate_draft_procedure] Loading from DB: {db_path} and JSON: {json_path}")
    action_instances = generate_action_instances_from_db(db_path, scenarioId, current_rule)
    compute_get_start_input(action_instances, data, ruleId, scenarioId)
    compute_buffer_and_repaint(action_instances, ruleId, scenarioId)
    rest_action_instances = split_action_instances_in_scenarios(action_instances, current_scenario)
    procedures = generate_draft_procedure(rest_action_instances, data, scenarioId, current_rule)
    # debug: list initial steps

    # normalize + squeeze + deep copy
    normalized_procs = normalize_procedures_with_levels(list(procedures.values()), scenarioId, ruleId)

    print("\n📦 [Post generate_draft_procedure] Listing initial steps:")
    for proc in normalized_procs:
        print(f"  🔸 {proc.id} has {len(proc.steps)} steps")
        for step in proc.steps.values():
            print(f"    • {step.id} ({step.action.id})")

    generic_with_unresolved = squeeze_with_unresolved(normalized_procs, scenarioId, ruleId)



    generic_procs = split_contender_procs(generic_with_unresolved)

    # If exactly one END‐marked instance exists among all candidate procs,
    # drop every other proc so only that lineage remains.
    end_pairs = [
        (p, inst)
        for p in generic_procs
        for inst in p.steps.values()
        if getattr(inst, "END", False)
    ]
    if len(end_pairs) == 1:
        proc_to_keep, _ = end_pairs[0]
        generic_procs = [p for p in generic_procs if p.id == proc_to_keep.id]
        print(f"ℹ️  Pruned to single‐END lineage: keeping proc {proc_to_keep.id}")

    normalized_splits = []
    for idx, proc in enumerate(generic_procs, start=1):
        # 1) normalize this single proc
        norm_proc = normalize_procedures_with_levels(
            [proc],
            proc.scenarioId,
            proc.ruleId
        )[0]  # normalize_procedures_with_levels returns a list :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}
        normalized_splits.append(norm_proc)
        # 2) print exactly like squeeze_with_unresolved does:
        print(
            f"\n🧬 Final normalized_split_{idx}")  # similar to “Final generic_proc_X” :contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}
        for sid, step in norm_proc.steps.items():
            print(f"   {sid} ({step.action.id})")

    generic_procs_copy = copy.deepcopy(normalized_splits)
    # === EVALUATION & PRUNING on TRAIN ===
    train_results = evaluate_generic_procedures("train", generic_procs_copy, data, scenarioId, ruleId)
    # write training results
    with open(results_path, "w") as f:
        f.write("✅ TRAINING RESULTS:\n")
        for r in train_results:
            status = "✅" if r["success"] else "❌"
            f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")
    current_rule.procedures = normalized_procs
    # record train_results & pick only those procs that were 100% successful
    current_rule.train_results = train_results
    successful = filter_successful_procedures(train_results)
    if not successful:
        print("❌ No successful procedures found.")

    # prune out any procedures that did *not* pass on every training example
    pruned = [p for p in generic_procs_copy if p.id in successful]
    if len(pruned) < len(generic_procs_copy):
        print(f"ℹ️  Pruned {len(generic_procs_copy) - len(pruned)} procedures; {len(pruned)} remain for testing")

    current_rule.generic_procs = pruned

    if not successful:
        print("❌ No successful procedures found.")

        #print(f"current_scenario.to_launch_next: {current_scenario.to_launch_next}")
        for scenario in current_scenario.to_launch_next:
            print(f"scenario to launch next: {scenario.id}")
            pre_rule = scenario.rule_to_launch_before
            generic_proc = pre_rule.proc_producing_output
            action_inst = generic_proc.action_producing_output
            new_arc_data = preprocess_arc_with_action(data, action_inst)
            new_raw_json = json.dumps(new_arc_data)
            mem_path = scenario.id
            print(f"new_raw_json: {new_raw_json}")
            print("current_scenario.new_sprites")
            print(current_scenario.new_sprites)
            scenario.new_sprites = current_scenario.new_sprites
            generate_scenarios_and_rules(
                scenario,
                scenario.rule_to_analyse,
                new_arc_data,  # ← the in-memory ARC dict
                db_path,
                mem_path,
                new_raw_json,  # ← the JSON‐string version
                results_path
            )

def split_contender_procs(generic_procs: list[Procedure]) -> list[Procedure]:

    def collect_lineage(proc: Procedure, start_id: str) -> set[str]:
        lineage = set()

        def walk_bindings(bind):
            """Yield bind and recurse into any nested sub_bindings."""
            yield bind
            sub = getattr(bind, "sub_bindings", None)
            if sub:
                children = sub.values() if isinstance(sub, Mapping) else (
                    sub if isinstance(sub, Iterable) else []
                )
                for child in children:
                    # only recurse into things that look like a Binding
                    if hasattr(child, "source_procedure_id"):
                        yield from walk_bindings(child)

        def dfs(step_id: str):
            # **GUARD**: skip any source id we no longer have
            if step_id not in proc.steps:
                print(f"   ⚠️  step {step_id!r} not in proc.steps, skipping")
                return
            if step_id in lineage:
                return
            lineage.add(step_id)
            inst = proc.steps[step_id]

            for bind_name, bind in inst.bindings.items():
                for b in walk_bindings(bind):
                    src = getattr(b, "source_procedure_id", None)
                    if src:
                        path = getattr(b, "path", "")
                        print(f"   • via {bind_name}{'.'+path if path else ''} ← {src}")
                        dfs(src)

        print(f"↪ collect_lineage for proc={proc.id}, starting at END step={start_id}")
        dfs(start_id)
        print(f"→ lineage collected: {sorted(lineage)}\n")
        return lineage

    # 1) find every (proc, inst) where inst.END == True
    end_pairs = [
        (proc, inst)
        for proc in generic_procs
        for inst in proc.steps.values()
        if getattr(inst, "END", False)
    ]
    # 2) if there's exactly one END, prune *that* proc to its lineage —
    #    this will drop any stray steps (like a second move_object).
    if len(end_pairs) == 1:
        proc, end_inst = end_pairs[0]
        lineage_ids = collect_lineage(proc, end_inst.id)
        # always keep these two entry‐points
        for sid, step in proc.steps.items():
            if step.action.id in ("get_start_input", "get_attribute"):
                lineage_ids.add(sid)

        sub_steps = {
            sid: copy.deepcopy(proc.steps[sid])
            for sid in proc.steps
            if sid in lineage_ids
        }
        return [
            Procedure(
                id=proc.id,
                scenarioId=proc.scenarioId,
                ruleId=proc.ruleId,
                steps=sub_steps
            )
        ]
    # 3) if there are no ENDs, bail out as before
    if len(end_pairs) == 0:
        return generic_procs

    contender_procs = []
    for proc, end_inst in end_pairs:
        print(f"   • Splitting proc={proc.id} at END step={end_inst.id}")
        lineage_ids = collect_lineage(proc, end_inst.id)

        # always keep get_start_input & get_attribute
        for sid, step in proc.steps.items():
            if step.action.id in ("get_start_input", "get_attribute"):
                lineage_ids.add(sid)

        sub_steps = {
            sid: copy.deepcopy(proc.steps[sid])
            for sid in proc.steps
            if sid in lineage_ids
        }
        contender_procs.append(
            Procedure(
                id=f"{proc.id}_contender_{end_inst.id}",
                scenarioId=proc.scenarioId,
                ruleId=proc.ruleId,
                steps=sub_steps
            )
        )

    return contender_procs

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
    #DEFAULT_TASK_ID = "d10ecb37_crop"
    #DEFAULT_TASK_ID = "d511f180"
    #DEFAULT_TASK_ID = "ed36ccf7"

    # Training 2
    #DEFAULT_TASK_ID = "4c4377d9" # sprite computation with flip_vert + identity
    #DEFAULT_TASK_ID = "6d0aefbc"
    #DEFAULT_TASK_ID = "6fa7a44f"
    #DEFAULT_TASK_ID = "5614dbcf_zoom_out"
    #DEFAULT_TASK_ID = "5614dbcf"
    #DEFAULT_TASK_ID = "5bd6f4ac"
    #DEFAULT_TASK_ID = "5582e5ca"
    #DEFAULT_TASK_ID = "8be77c9e"
    #DEFAULT_TASK_ID = "c9e6f938"
    #DEFAULT_TASK_ID = "2dee498d" # crop
    #DEFAULT_TASK_ID = "2dee498d_mini" # crop

    # Training 3
    #DEFAULT_TASK_ID = "1cf80156"
    #DEFAULT_TASK_ID = "32597951" # colorZone sprite + recolor + repaint
    #DEFAULT_TASK_ID = "25ff71a9" # move object 1 pixel lower
    #DEFAULT_TASK_ID = "0b148d64"
    #DEFAULT_TASK_ID = "1f85a75f" # crop
    #DEFAULT_TASK_ID = "23b5c85d"
    #DEFAULT_TASK_ID = "9ecd008a" # find missing sprite in symmetry
    #DEFAULT_TASK_ID = "ac0a08a4" # zoom based on nb_pixel alone
    #DEFAULT_TASK_ID = "be94b721" # select greater object (sizeOrder 2 ?)
    #DEFAULT_TASK_ID = "c909285e" # get sprite with alone color
    #DEFAULT_TASK_ID = "f25ffba3" # composition with vertical symmetry
    #DEFAULT_TASK_ID = "c1d99e64" # red lightCycle on black line touching both border
    #DEFAULT_TASK_ID = "b91ae062" # zoom based on nb_colors-1
    DEFAULT_TASK_ID = "3aa6fb7a" # cellular automation !
    #DEFAULT_TASK_ID = "7b7f7511" # crop if V or H ? Repeated sprite ?
    #DEFAULT_TASK_ID = "4258a5f9" # cellular automation !

    trainings_number = 3
    TASK_ID = args.task_id if args.task_id else DEFAULT_TASK_ID

    PROJECT_ROOT     = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    db_path          = os.path.join(PROJECT_ROOT, "db", "database.db")
    json_path        = os.path.join(PROJECT_ROOT, "pattern-finder", "data", f"training-{trainings_number}", f"{TASK_ID}.json")
    results_path     = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_results.txt")
    submission_path  = os.path.join(PROJECT_ROOT, "results", "submission.json")
    comparison_path  = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_comparison.txt")

    #success = test_file(json_path, db_path, results_path, submission_path, comparison_path, TASK_ID, trainings_number)
    try:
        success = run_with_timeout(
            test_file,
            json_path,
            db_path,
            results_path,
            submission_path,
            comparison_path,
            TASK_ID,
            trainings_number,
            timeout=30000000000000,
        )
    except TimeoutException as te:
        print(f"⚠️ Overall test_file timed out: {te}")
        success = False


    # Training 4
    #DEFAULT_TASK_ID = "2dc579da" # sprite with nb hole 1 ?
    #DEFAULT_TASK_ID = "28bf18c6" # repeated object x2 horizontal
    #DEFAULT_TASK_ID = "3af2c5a8" # repeated object x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "44f52bb0" # pixel blue if symmetry else pixel orange !
    #DEFAULT_TASK_ID = "62c24649" # repeated sprite x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "67e8384a" # repeated sprite x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "7468f01a" # move sprite + flip horizontal
    #DEFAULT_TASK_ID = "662c240a" # select sprite not in cumulated disqualified sprite's shapes !!!
    #DEFAULT_TASK_ID = "42a50994" # cellular automation, delete pixel surround by black
    #DEFAULT_TASK_ID = "56ff96f3" # draw rect from minXY pixel to maxXY pixel !
    #DEFAULT_TASK_ID = "50cb2852" # for each rect draw rect: posX+1, posY+1, width-2, height-2 !
    #DEFAULT_TASK_ID = "4347f46a" # for each rect draw rect: posX+1, posY+1, width-2, height-2
    #DEFAULT_TASK_ID = "46f33fce" # cellular automation + zoom ?
    #DEFAULT_TASK_ID = "a740d043" # fill blue with black + shrink-canvas !
    #DEFAULT_TASK_ID = "a79310a0" # move + recolor
    #DEFAULT_TASK_ID = "aabf363d" # recolor with pixel alone + remove pixel alone, legend ?!
    #DEFAULT_TASK_ID = "ae4f1146" # select sprite with most blue ! Color#Order: 1#1 ? Or 9 cols: BlueOrder...
    #DEFAULT_TASK_ID = "b27ca6d3" # cellular automation
    #DEFAULT_TASK_ID = "ce22a75a" # cellular automation
    #DEFAULT_TASK_ID = "dc1df850" # cellular automation
    #DEFAULT_TASK_ID = "f25fbde4" # crop + zoom OR zoom + shrink-canvas
    #DEFAULT_TASK_ID = "44d8ac46" # fill square with red !
    #DEFAULT_TASK_ID = "1e0a9b12" # gravity down !
    #DEFAULT_TASK_ID = "0d3d703e" # apply cumulated recolor !
    #DEFAULT_TASK_ID = "3618c87e" # gravity down for blue only !
    #DEFAULT_TASK_ID = "1c786137" # sprite in hole of object (sizeOrder or color alone)

    # Training 5
    #DEFAULT_TASK_ID = "8efcae92" # get sprite with redOrder 1
    #DEFAULT_TASK_ID = "445eab21" # create 2x2 object with same color as greater rect
    #DEFAULT_TASK_ID = "6f8cd79b" # color border, cellular automation or lightCycle ?
    #DEFAULT_TASK_ID = "2013d3e2" # crop 3x3 with right-bottom at center of sprite
    #DEFAULT_TASK_ID = "41e4d17e" # pink lightCycle, ground teal, cloud blue
    #DEFAULT_TASK_ID = "9565186b" # repaint greater object with gray background
    #DEFAULT_TASK_ID = "aedd82e4" # cellular automation
    #DEFAULT_TASK_ID = "bb43febb" # fill with red gray block but keep gray border
    #DEFAULT_TASK_ID = "e98196ab" # gray split line + Superposition with black bg
    #DEFAULT_TASK_ID = "f76d97a5" # recolor gray in black + invert color
    #DEFAULT_TASK_ID = "ce9e57f2" # lightCycle step by step with red first
    #DEFAULT_TASK_ID = "22eb0ac0" # lightCycle between same color
    #DEFAULT_TASK_ID = "9f236235" # unzoom without split grid + flip horizontal
    #DEFAULT_TASK_ID = "a699fb00" # cellular automation

    # Training 6
    #DEFAULT_TASK_ID = "46442a0e" # sprite composition
    #DEFAULT_TASK_ID = "7fe24cdd" # sprite composition
    #DEFAULT_TASK_ID = "0ca9ddb6" # cellular automation
    #DEFAULT_TASK_ID = "543a7ed5" # fill hole with yellow and draw a border, cellular automation ?
    #DEFAULT_TASK_ID = "0520fde7" # gray splitter line + superposition: 2 blue = red
    #DEFAULT_TASK_ID = "dae9d2b5" # superposition: 2 black = black else pink
    #DEFAULT_TASK_ID = "8d5021e8" # sprite composition
    #DEFAULT_TASK_ID = "928ad970" # lightCycle ? colorZone ? draw rect inside 4 gray points
    #DEFAULT_TASK_ID = "b60334d2" # cellular automation
    #DEFAULT_TASK_ID = "b94a9452" # invert color and shrink
    #DEFAULT_TASK_ID = "d037b0a7" # lightCycle ? Fluid ? repeat pixel to the bottom
    #DEFAULT_TASK_ID = "d0f5fe59" # count object = canvas size + diagonal lightCycle
    #DEFAULT_TASK_ID = "e3497940" # gray splitter + superposition right & left flipped horizontally
    #DEFAULT_TASK_ID = "e9afcf9a" # lightCycle with jump ?
    #DEFAULT_TASK_ID = "48d8fb45" # select object under gray pixel
    #DEFAULT_TASK_ID = "d406998b" # columns recoloring 1/2 starting from right
    #DEFAULT_TASK_ID = "5117e062" # select sprite with teal + recolor with sprite first color
    #DEFAULT_TASK_ID = "3906de3d" # gravity up !
    #DEFAULT_TASK_ID = "00d62c1b" # fill holes with yellow
    #DEFAULT_TASK_ID = "7b6016b9" # change black to green + fill holes with red
    #DEFAULT_TASK_ID = "67385a82" # fill block with size > 1 with teal
    #DEFAULT_TASK_ID = "a5313dff" # fill holes not touching border with blue
    #DEFAULT_TASK_ID = "ea32f347" # sizeOrder : 1 blue, 2 yellow, 3 red
    #DEFAULT_TASK_ID = "d631b094" # create object with height 1 and width nb colored pixels
    #DEFAULT_TASK_ID = "10fcaaa3" # 1) composition 2) cellular automation

    # Training 7
    #DEFAULT_TASK_ID = "007bbfb7" #
    #DEFAULT_TASK_ID = "496994bd" #
    #DEFAULT_TASK_ID = "1f876c06" #
    #DEFAULT_TASK_ID = "05f2a901" #
    #DEFAULT_TASK_ID = "39a8645d" #
    #DEFAULT_TASK_ID = "1b2d62fb" #
    #DEFAULT_TASK_ID = "90c28cc7" #
    #DEFAULT_TASK_ID = "b6afb2da" #
    #DEFAULT_TASK_ID = "b9b7f026" #
    #DEFAULT_TASK_ID = "ba97ae07" #
    #DEFAULT_TASK_ID = "c9f8e694" #
    #DEFAULT_TASK_ID = "d23f8c26" #
    #DEFAULT_TASK_ID = "d5d6de2d" #
    #DEFAULT_TASK_ID = "dbc1a6ce" #
    #DEFAULT_TASK_ID = "ded97339" #
    #DEFAULT_TASK_ID = "ea786f4a" #
    #DEFAULT_TASK_ID = "08ed6ac7" #
    #DEFAULT_TASK_ID = "40853293" #
    #DEFAULT_TASK_ID = "5521c0d9" #
    #DEFAULT_TASK_ID = "f8ff0b80" #
    #DEFAULT_TASK_ID = "85c4e7cd" #
    #DEFAULT_TASK_ID = "d2abd087" #
    #DEFAULT_TASK_ID = "017c7c7b" #
    #DEFAULT_TASK_ID = "363442ee" #
    #DEFAULT_TASK_ID = "5168d44c" #
    #DEFAULT_TASK_ID = "e9614598" #
    #DEFAULT_TASK_ID = "d9fac9be" #

    # Training 8
    #DEFAULT_TASK_ID = "e50d258f" #
    #DEFAULT_TASK_ID = "810b9b61" #
    #DEFAULT_TASK_ID = "54d82841" #
    #DEFAULT_TASK_ID = "60b61512" #
    #DEFAULT_TASK_ID = "25d8a9c8" #
    #DEFAULT_TASK_ID = "239be575" #
    #DEFAULT_TASK_ID = "67a423a3" #
    #DEFAULT_TASK_ID = "5c0a986e" #
    #DEFAULT_TASK_ID = "6430c8c4" #
    #DEFAULT_TASK_ID = "94f9d214" #
    #DEFAULT_TASK_ID = "a1570a43" #
    #DEFAULT_TASK_ID = "ce4f8723" #
    #DEFAULT_TASK_ID = "d13f3404" #
    #DEFAULT_TASK_ID = "dc433765" #
    #DEFAULT_TASK_ID = "f2829549" #
    #DEFAULT_TASK_ID = "fafffa47" #
    #DEFAULT_TASK_ID = "fcb5c309" #
    #DEFAULT_TASK_ID = "ff805c23" #
    #DEFAULT_TASK_ID = "e76a88a6" #
    #DEFAULT_TASK_ID = "7c008303" #
    #DEFAULT_TASK_ID = "7f4411dc" #
    #DEFAULT_TASK_ID = "b230c067" #
    #DEFAULT_TASK_ID = "e8593010" #
    #DEFAULT_TASK_ID = "6d75e8bb" #
    #DEFAULT_TASK_ID = "3f7978a0" #
    #DEFAULT_TASK_ID = "1190e5a7" #
    #DEFAULT_TASK_ID = "6e02f1e3" #
    #DEFAULT_TASK_ID = "a61f2674" #

    # Training 9
