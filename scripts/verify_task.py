# scripts/verify_task.py

import copy
import json
import argparse
import os
import sys
from collections import defaultdict
import sqlite3
import subprocess
import time

from constelize.core.binding import BindingStatus
from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json, load_json_inputs_from_json, \
    TRAIN_INPUT_GRIDS, TEST_INPUT_GRIDS
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    extract_rules_from_procedure,
    evaluate_generic_procedures,
    run_generic_procs_on_tests,
    load_arc_json, generate_submission_file, compare_submission_to_arc_outputs, print_test_results,
)
from constelize.tools.prune_helpers import iterative_prune
from constelize.tools.sqlite_loader import load_all_tables_from_sqlite, build_values_by_input, \
    build_attributes_by_input_and_values
from constelize.tools.squeeze import normalize_procedures_with_levels, squeeze_with_unresolved, \
    remove_unresolved_actions_from_generic
import constelize.library.attribute_access as _aa_mod
from scripts.verify_utils import filter_successful_procedures, SCRIPT_DIR
import constelize.tools.binding_train_map as btm

start_time = time.time()

def validate_get_start_input_usage(procedures):
    for proc in procedures:
        for step in proc.steps.values():
            if step.action and step.action.id == "get_start_input":
                if not step.used_by:
                    print(f"⚠️ Warning: 'get_start_input' step {step.id} is not used by any other action in {proc.id}!")

def run_analysis_scripts(json_path):
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    # ensure our code is first on PYTHONPATH
    sys.path.insert(0, PROJECT_ROOT)

    # first_sight and object always must succeed
    subprocess.run(
        ["python", os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py"), json_path],
        check=True
    )
    subprocess.run(
        ["python", os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py"), json_path],
        check=True
    )

    # sprite_analysis can fail if a table is missing; warn & continue
    try:
        subprocess.run(
            ["python", os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py"), json_path],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Warning: sprite_analysis.py failed ({e}); continuing anyway")


def test_file(json_path, db_path, results_path, submission_path, comparison_path, task_id, trainings_number):
    # 1) run the three analysis scripts
    run_analysis_scripts(json_path)

    # 2) inject the sqlite‐derived attributes
    _values = build_values_by_input(db_path)
    _attrs  = build_attributes_by_input_and_values(_values)
    _aa_mod._values_by_input = _values
    _aa_mod._attributes_by_input_and_values = _attrs
    print(f"[verify_task] Injected attributes: {len(_attrs)} entries")

    # 3) load the ARC JSON and build procedures
    load_end_outputs_from_json(json_path)
    load_json_inputs_from_json(json_path)
    data = load_arc_json(json_path)
    procedures = generate_draft_procedure(db_path, json_path, name=f"{task_id}_procedure")

    # tell binding_train_map how many trains we have
    btm.TOTAL_TRAINS = len(procedures)
    btm.ALL_TRAIN_IDS = set(range(btm.TOTAL_TRAINS))

    # debug: list initial steps
    print("\n📦 [Post generate_draft_procedure] Listing initial steps:")
    for proc_id, proc in procedures.items():
        print(f"  🔸 {proc_id} has {len(proc.steps)} steps")
        for step in proc.steps.values():
            print(f"    • {step.id} ({step.action.id})")

    # normalize + squeeze + deep copy
    normalized_procs = normalize_procedures_with_levels(list(procedures.values()))
    generic_with_unresolved = squeeze_with_unresolved(normalized_procs)
    generic_procs = copy.deepcopy(generic_with_unresolved)

    # === EVALUATION & PRUNING on TRAIN ===
    train_results = evaluate_generic_procedures("train", generic_procs, data)
    # write training results
    with open(results_path, "w") as f:
        f.write("✅ TRAINING RESULTS:\n")
        for r in train_results:
            status = "✅" if r["success"] else "❌"
            f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")

    # pick the procedures that fully succeeded
    valid_ids = filter_successful_procedures(train_results)
    valid_procs = [p for p in generic_procs if p.id in valid_ids]

    if valid_procs:
        print("🎯 At least one generic procedure passed all training examples. Running on test set...")
        test_results = evaluate_generic_procedures("test", valid_procs, data)
        print_test_results(test_results, results_path)
        generate_submission_file(task_id, valid_procs, data, submission_path, test_results)
        compare_submission_to_arc_outputs(task_id, data, submission_path, comparison_path)
    else:
        print("⚠️ No fully successful generic procedure found. Skipping test execution.")

    total_time = time.time() - start_time
    print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")
    print("✅ Evaluation completed. Results saved to", results_path)

    # return True if tests ran (even partially), False only if no valid train‐proc
    return bool(valid_procs)


if __name__ == "__main__":
    # ---- ARG PARSING & PATH SETUP ----
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_id", help="ARC task ID, e.g., 3c9b0459")
    args = parser.parse_args()

    # Training 1
    # DEFAULT_TASK_ID = "3c9b0459"
    # DEFAULT_TASK_ID = "9dfd6313"
    # DEFAULT_TASK_ID = "67a3c6ac"
    # DEFAULT_TASK_ID = "68b16354"
    # DEFAULT_TASK_ID = "74dd1130"
    # DEFAULT_TASK_ID = "6150a2bd"
    # DEFAULT_TASK_ID = "9172f3a0"
    # DEFAULT_TASK_ID = "a416b8f3"
    # DEFAULT_TASK_ID = "b1948b0a"
    # DEFAULT_TASK_ID = "c8f0f002"
    # DEFAULT_TASK_ID = "c59eb873"
    # DEFAULT_TASK_ID = "d10ecb37"
    # DEFAULT_TASK_ID = "d511f180"
    # DEFAULT_TASK_ID = "ed36ccf7"

    # Training 2
    DEFAULT_TASK_ID = "4c4377d9"
    # DEFAULT_TASK_ID = "6d0aefbc"
    # DEFAULT_TASK_ID = "6fa7a44f"
    # DEFAULT_TASK_ID = "5614dbcf"
    # DEFAULT_TASK_ID = "5bd6f4ac"
    # DEFAULT_TASK_ID = "5582e5ca"
    # DEFAULT_TASK_ID = "8be77c9e"
    # DEFAULT_TASK_ID = "c9e6f938"
    # DEFAULT_TASK_ID = "2dee498d"

    TASK_ID = args.task_id if args.task_id else DEFAULT_TASK_ID
    trainings_number = 2

    PROJECT_ROOT     = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    db_path          = os.path.join(PROJECT_ROOT, "db", "database.db")
    json_path        = os.path.join(PROJECT_ROOT, "pattern-finder", "data", f"training-{trainings_number}", f"{TASK_ID}.json")
    results_path     = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_results.txt")
    submission_path  = os.path.join(PROJECT_ROOT, "results", "submission.json")
    comparison_path  = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_comparison.txt")

    success = test_file(json_path, db_path, results_path, submission_path, comparison_path, TASK_ID, trainings_number)
