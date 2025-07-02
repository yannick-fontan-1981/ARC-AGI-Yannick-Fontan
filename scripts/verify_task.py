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
from typing import Set, Tuple, List, Iterable, Mapping, Dict

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
    generate_action_instances_from_db, evaluate_generic_scenarios_on_tests, print_test_results_by_scenario,
    generate_submission_file_from_scenarios, preprocess_arc_with_action, compute_get_start_input,
    compute_buffer_and_repaint,
)
from constelize.tools.sqlite_loader import build_values_by_input, \
    build_attributes_by_input_and_values, build_colors_by_input, build_attributes_by_input_and_colors, \
    load_all_tables_from_sqlite
from constelize.tools.squeeze import normalize_procedures_with_levels, squeeze_with_unresolved, generate_producers
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

_unique_scenario_ids: Dict[str, int] = {}

def getUniqueScenarioId(action_id: str) -> str:
    """
    Return a unique incremental ID (as string) for the given action_id.
    Each action_id has its own counter starting from 1.
    """
    count = _unique_scenario_ids.get(action_id, 0) + 1
    _unique_scenario_ids[action_id] = count
    return str(count)

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
        "sprite"             : os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py"),
        "object"             : os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py"),
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


def split_action_instances_in_scenarios(data: dict, action_instances: List, current_scenario) -> List:
    """
    For each action.id flagged IN_SEPARATE_RULE across all trains:
      1) Draft procedures with constant bindings resolved
      2) Normalize drafts topologically to respect binding order
      3) Squeeze into a single generic procedure
      4) Assign each raw instance its scenarioId and pre-ruleId
      5) Attach the generic proc under the pre-rule and link to the main rule
      6) Build and attach a post-procedure invoking any revert_action
    Return the remainder.
    """
    # 1) gather all trainIds
    train_ids = {inst.trainId for inst in action_instances if inst.isTrain}

    # 2) group by action.id
    groups = defaultdict(list)
    for inst in action_instances:
        if getattr(inst, 'IN_SEPARATE_RULE', False):
            groups[inst.action.id].append(inst)

    # 3) keep only full groups
    valid_groups = {aid: insts for aid, insts in groups.items() if {i.trainId for i in insts} == train_ids}

    # 4) instances not in valid_groups remain
    rest = [inst for inst in action_instances if inst.action.id not in valid_groups]

    # 5) process each valid group
    for action_id, insts in valid_groups.items():
        # a) create pre, main, and post rules
        rule_pre_id  = f"rule_pre_{action_id}_{getUniqueScenarioId(action_id)}"
        rule_main_id = f"rule_main_{getUniqueScenarioId(action_id)}"
        rule_post_id = f"rule_post_{action_id}_{getUniqueScenarioId(action_id)}"

        rule_pre  = Rule(id=rule_pre_id)
        rule_main = Rule(id=rule_main_id)
        rule_post = Rule(id=rule_post_id)

        # b) new scenario with all rules
        scen_id = f"scenario_{action_id}_{getUniqueScenarioId(action_id)}"
        scenario = Scenario(
            id=scen_id,
            rules={rule_pre_id: rule_pre, rule_main_id: rule_main, rule_post_id: rule_post}
        )
        if scen_id.endswith("_3"):
            print(f"scenario aborted: {scen_id}")
            continue

        # c) assign raw instances to pre-rule
        for inst in insts:
            inst.scenarioId = scen_id
            inst.ruleId     = rule_pre_id

        # d) generate drafts
        draft = generate_draft_procedure(insts, data, scen_id, rule_pre)
        if isinstance(draft, Procedure):
            draft_list = [draft]
        elif isinstance(draft, dict):
            draft_list = [p for p in draft.values() if isinstance(p, Procedure)]
        else:
            print(f"⚠️ split: unexpected draft type for '{action_id}'")
            continue

        if not draft_list:
            print(f"⚠️ split: no draft procedures for '{action_id}'")
            continue

        # e) normalize and squeeze
        normalized_procs = normalize_procedures_with_levels(draft_list, scen_id, rule_pre_id)
        generic_procs    = squeeze_with_unresolved(normalized_procs, scen_id, rule_pre_id)
        if not generic_procs:
            print(f"⚠️ split: squeeze yielded none for '{action_id}'")
            continue

        # f) attach generic proc under pre-rule
        generic_proc = generic_procs[0]
        if not generic_proc.steps:
            print(f"⚠️ split: generic_proc has no steps for '{action_id}'")
            continue
        rule_pre.procedures             = generic_procs
        rule_pre.proc_producing_output = generic_proc
        generic_proc.action_producing_output = next(iter(generic_proc.steps.values()))

        # g) build post-procedure invoking revert_action
        post_steps: Dict[str, ActionInstance] = {}
        revert_action: ActionInstance = None
        for step in generic_proc.steps.values():
            if hasattr(step, 'revert_action') and step.revert_action:
                revert_action = ActionInstance(
                    id=f"{step.id}_revert",
                    action=step.revert_action,
                    bindings=step.revert_bindings,
                    output_var=step.output_var,
                    output_type=step.output_type,
                    trainId=step.trainId,
                    testId=step.testId,
                    isTrain=step.isTrain,
                    isToOutput=False
                )
                post_steps[revert_action.id] = revert_action
        if post_steps and revert_action:
            post_proc = Procedure(
                id=f"proc_post_{action_id}",
                steps=post_steps,
                scenarioId=scen_id,
                ruleId=rule_post_id,
                action_producing_output=revert_action
            )

            rule_post.procedures = [post_proc]
            rule_post.proc_producing_output = post_proc

        # h) link scenario execution order
        scenario.rule_to_launch_before = rule_pre
        scenario.rule_to_analyse       = rule_main
        scenario.rule_to_launch_after  = rule_post

        # i) enqueue scenario
        current_scenario.to_launch_next.append(scenario)
        GLOBAL.all_scenarios.append(scenario)

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
        id=f"scenario_{getUniqueScenarioId('first')}",
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

    # At least one generic proc passed training; if there's a test set, compare now
    if valid_scenario:
        print("🎯 Running successful procedure(s) on test set...")
        results_by_scenario = evaluate_generic_scenarios_on_tests(data, valid_scenario)
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
        print("🔴ℹ️🔴 No test outputs available; generating dummy submission from train outputs...")
        dummy_results = {sc.id: [] for sc in valid_scenario}
        generate_submission_file_from_scenarios(task_id, valid_scenario, data, submission_path, db_path, dummy_results)
        # compare against ARC (will use default behavior on submission)
        compare_result = compare_submission_to_arc_outputs(task_id, data, submission_path, comparison_path)
        print_total_time(results_path)
        return compare_result


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

    print("raw_with_sprites")
    print(raw_with_sprites)

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
    action_instances = generate_action_instances_from_db(data, db_path, scenarioId, current_rule)

    #print("exit(0)")
    #exit(0)

    compute_get_start_input(action_instances, data, ruleId, scenarioId)


    compute_buffer_and_repaint(action_instances, ruleId, scenarioId)
    rest_action_instances = split_action_instances_in_scenarios(data, action_instances, current_scenario)
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
    generic_with_producers = generate_producers(generic_with_unresolved, current_scenario, current_rule)
    generic_procs = split_contender_procs(generic_with_producers)

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

    #if current_scenario.id == "scenario_unzoom_1":
    #    print("exit")
    #    exit(0)

    if not successful:
        print("❌ No successful procedures found.")

        #print(f"current_scenario.to_launch_next: {current_scenario.to_launch_next}")
        for scenario in current_scenario.to_launch_next:
            print(f"scenario to launch next: {scenario.id}")
            if scenario.id == "scenario_denoise_3":
                print(f"scenario aborted: {scenario.id}")
                continue
            if scenario.id == "scenario_unzoom_3":
                print(f"scenario aborted: {scenario.id}")
                continue
            pre_rule = scenario.rule_to_launch_before
            generic_proc = pre_rule.proc_producing_output

            print( "1 !!! generic_proc.action_producing_output" )

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
    #DEFAULT_TASK_ID = "c8f0f002" # recolor
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
    #DEFAULT_TASK_ID = "3aa6fb7a" # cellular automation !
    #DEFAULT_TASK_ID = "7b7f7511" # crop if V or H ? Un-Repeat sprite ?
    #DEFAULT_TASK_ID = "4258a5f9" # cellular automation !

    # Training 4
    #DEFAULT_TASK_ID = "2dc579da" # sprite with nb hole 1 ?
    #DEFAULT_TASK_ID = "28bf18c6" # repeated object x2 horizontal
    #DEFAULT_TASK_ID = "3af2c5a8_simple" # repeated object x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "3af2c5a8" # repeated object x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "44f52bb0" # pixel blue if symmetry else pixel orange !
    #DEFAULT_TASK_ID = "62c24649" # repeated sprite x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "67e8384a" # repeated sprite x4 with flip horizontal + vertical
    #DEFAULT_TASK_ID = "7468f01a" # move sprite + flip horizontal
    #DEFAULT_TASK_ID = "662c240a" # select sprite not having diagonal symetry
    #DEFAULT_TASK_ID = "42a50994" # cellular automation, delete pixel surround by black
    #DEFAULT_TASK_ID = "56ff96f3" # Producer ! recolor, from minXY pixel to maxXY pixel !
    #DEFAULT_TASK_ID = "50cb2852" # for each rect draw rect: posX+1, posY+1, width-2, height-2 !
    #DEFAULT_TASK_ID = "4347f46a" # for each rect draw rect: posX+1, posY+1, width-2, height-2
    #DEFAULT_TASK_ID = "46f33fce_simple" # cellular automation with no orientation_invariant
    DEFAULT_TASK_ID = "46f33fce" # unzoom train output + cellular automation ?
     #DEFAULT_TASK_ID = "a740d043" # fill blue with black + shrink-canvas !
     #DEFAULT_TASK_ID = "a79310a0" # move + recolor
     #DEFAULT_TASK_ID = "aabf363d" # recolor with pixel alone + remove pixel alone, legend ?!
     #DEFAULT_TASK_ID = "ae4f1146" # select sprite with most blue ! Color#Order: 1#1 ? Or 9 cols: BlueOrder...
    #DEFAULT_TASK_ID = "b27ca6d3" # cellular automation
    #DEFAULT_TASK_ID = "ce22a75a" # cellular automation
    #DEFAULT_TASK_ID = "dc1df850" # cellular automation
    #DEFAULT_TASK_ID = "f25fbde4" # crop + zoom OR zoom + shrink-canvas
     #DEFAULT_TASK_ID = "44d8ac46" # fill with red only if square !
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
    #DEFAULT_TASK_ID = "bb43febb" # cellular automation, fill with red gray block but keep gray border
     #DEFAULT_TASK_ID = "e98196ab" # gray split line + Superposition with black bg
     #DEFAULT_TASK_ID = "f76d97a5" # recolor gray in black + invert color
     #DEFAULT_TASK_ID = "ce9e57f2" # lightCycle step by step with red first
     #DEFAULT_TASK_ID = "22eb0ac0" # INFINITE LOOP ! lightCycle between same color
     #DEFAULT_TASK_ID = "9f236235" # unzoom without split grid + flip horizontal
    #DEFAULT_TASK_ID = "a699fb00" # cellular automation

    trainings_number = 4
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


    # Training 6
    #DEFAULT_TASK_ID = "46442a0e" # sprite composition
    #DEFAULT_TASK_ID = "7fe24cdd" # sprite composition
    #DEFAULT_TASK_ID = "0ca9ddb6" # cellular automation
    #DEFAULT_TASK_ID = "543a7ed5" # fill hole with yellow and draw a border
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
    #DEFAULT_TASK_ID = "007bbfb7" # zoom + replace colored pixel by input
    #DEFAULT_TASK_ID = "496994bd" # top sprite flip vertical + repaint at bottom on input
    #DEFAULT_TASK_ID = "1f876c06" # lightCycle : trace diagonal line between same color pixel
    #DEFAULT_TASK_ID = "05f2a901" # gravity on red block toward teal block
    #DEFAULT_TASK_ID = "39a8645d" # un-repeat most present zone
    #DEFAULT_TASK_ID = "1b2d62fb" # brown superposition + recolored teal + inverted
    #DEFAULT_TASK_ID = "90c28cc7" # for block read, draw pixel same color
    #DEFAULT_TASK_ID = "b6afb2da" # cellular automation
    #DEFAULT_TASK_ID = "b9b7f026" # draw 1 pixel same color as block with 1 hole
    #DEFAULT_TASK_ID = "ba97ae07" # cellular automation ? lightCycle ? create object ?
    #DEFAULT_TASK_ID = "c9f8e694" # lightCycle : from left to right with same color + jump black
    #DEFAULT_TASK_ID = "d23f8c26" # redraw only center column
    #DEFAULT_TASK_ID = "d5d6de2d" # recolor + repaint
    #DEFAULT_TASK_ID = "dbc1a6ce" # lightCycle : draw line between aligned pixels
    #DEFAULT_TASK_ID = "ded97339" # lightCycle : draw line between aligned pixels
    #DEFAULT_TASK_ID = "ea786f4a" # lightCycle : draw black diagonal from corners
    #DEFAULT_TASK_ID = "08ed6ac7" # recolor based on size order
    #DEFAULT_TASK_ID = "40853293" # lightCycle : draw line between aligned pixels but vertical last
    #DEFAULT_TASK_ID = "5521c0d9" # shift upper, nb pixels = height
    #DEFAULT_TASK_ID = "f8ff0b80" # draw 3 pixels vertically with color based on size order
    #DEFAULT_TASK_ID = "85c4e7cd" # revert fill color based on size order
    #DEFAULT_TASK_ID = "d2abd087" # recolor red if 6 pixels else blue
    #DEFAULT_TASK_ID = "017c7c7b" # resize canvas + fill blue in red + repeat pixel + bigger black object
    #DEFAULT_TASK_ID = "363442ee" # repeat sprite on every blue pixel, anchor center
    #DEFAULT_TASK_ID = "5168d44c" # move red object 2 pixel right or down, green pixel anchor center
    #DEFAULT_TASK_ID = "e9614598" # draw green cross between 2 blue pixel
    #DEFAULT_TASK_ID = "d9fac9be" # draw pixel inside sprite hole (not bg holes)

    # Training 8
    #DEFAULT_TASK_ID = "e50d258f" # sprite with more red pixels
    #DEFAULT_TASK_ID = "810b9b61" # recolored green for has-border
    #DEFAULT_TASK_ID = "54d82841" # Gun ?
    #DEFAULT_TASK_ID = "60b61512" # Cellular automation || sprite recolor
    #DEFAULT_TASK_ID = "25d8a9c8" # Redraw 3 pixel horizontal line in gray on bg black
    #DEFAULT_TASK_ID = "239be575" # Same Teal object touching 2 red square = teal pixel, else black pixel
    #DEFAULT_TASK_ID = "67a423a3" # Yellow 3x3 border at intersection of 2 lines
    #DEFAULT_TASK_ID = "5c0a986e" # diagonal LightCycle
    #DEFAULT_TASK_ID = "6430c8c4" # superposition with split line + invert color
    #DEFAULT_TASK_ID = "94f9d214" # superposition without split line + invert color
    #DEFAULT_TASK_ID = "a1570a43" # move red sprite to maxX/maxY of top-left green pixel
    #DEFAULT_TASK_ID = "ce4f8723" # superposition with split line
    #DEFAULT_TASK_ID = "d13f3404" # resize + diagonal LightCycle
    #DEFAULT_TASK_ID = "dc433765" # move 1 pixel green pixel toward yellow pixel
    #DEFAULT_TASK_ID = "f2829549" # superposition with split line + invert color
    #DEFAULT_TASK_ID = "fafffa47" # superposition with split line + invert color
    #DEFAULT_TASK_ID = "fcb5c309" # select sprite with more colored holes and recolor border
    #DEFAULT_TASK_ID = "ff805c23" # select new sprite of symetry reparation
    #DEFAULT_TASK_ID = "e76a88a6" # repeat 2 colored sprite on gray block
    #DEFAULT_TASK_ID = "7c008303" # recolor 4 zones based on 4 legend !
    #DEFAULT_TASK_ID = "7f4411dc" # denoise
    #DEFAULT_TASK_ID = "b230c067" # size-order/isUnique recolor, small/unique = red, big/repeated = blue
    #DEFAULT_TASK_ID = "e8593010" # size-order block recolor, 1=green, 2=red, 3=blue
    #DEFAULT_TASK_ID = "6d75e8bb" # sprite recolor bg->red
    #DEFAULT_TASK_ID = "3f7978a0" # gray sprite zone with minY-1 / maxY+1
    #DEFAULT_TASK_ID = "1190e5a7" # create bg object with width / height = nb bg object hor / ver
    #DEFAULT_TASK_ID = "6e02f1e3" # output chosen by input nb colors, map {nbColor,outputGrid}
    #DEFAULT_TASK_ID = "a61f2674" # size order : small=red, middle=bg, greater=blue, greater ?!

    # Training 9

