# scripts/verify_done_tasks.py

#!/usr/bin/env python3
import copy
import json
import os
import sqlite3
import subprocess
import sys
import shutil
import importlib
from collections import defaultdict

# Import necessary functions and modules
from constelize.tools.fact_to_action_mapping import (
    load_end_outputs_from_json,
    load_json_inputs_from_json
)
import constelize.tools.fact_to_action_mapping as ftam_mod
import constelize.library.attribute_access as aa_mod
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    evaluate_generic_procedures,
    load_arc_json,
    print_test_results,
    generate_submission_file,
    compare_submission_to_arc_outputs
)
from constelize.tools.squeeze import (
    normalize_procedures_with_levels,
    squeeze_with_unresolved,
    remove_unresolved_actions_from_generic
)
from constelize.tools.sqlite_loader import (
    build_values_by_input,
    build_attributes_by_input_and_values
)
from scripts.verify_utils import filter_successful_procedures, SCRIPT_DIR

# Paths configuration
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DONE_DIR = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "done")
DB_PATH = os.path.join(PROJECT_ROOT, "db", "database.db")
ORIG_DB = DB_PATH + ".orig"

FIRST_SIGHT_SCRIPT = os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py")
OBJECT_SCRIPT = os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py")
SPRITE_SCRIPT = os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py")

if not os.path.exists(ORIG_DB):
    shutil.copy(DB_PATH, ORIG_DB)

def reset_database():
    shutil.copy(ORIG_DB, DB_PATH)

def run_analysis_scripts(json_path: str):
    for script in (FIRST_SIGHT_SCRIPT, OBJECT_SCRIPT, SPRITE_SCRIPT):
        subprocess.run([sys.executable, script, json_path], check=True)

def test_file(json_path: str, results_path: str, submission_path: str, comparison_path: str, task_id: str) -> bool:
    reset_database()
    run_analysis_scripts(json_path)

    import constelize.tools.registry_singleton as rs_mod
    import constelize.core.registry as reg_mod
    importlib.reload(ftam_mod)
    importlib.reload(aa_mod)
    importlib.reload(rs_mod)

    ftam_mod._unique_id = 0
    ftam_mod.END_OUTPUTS_BY_TRAINID.clear()
    ftam_mod.TRAIN_INPUT_GRIDS.clear()
    ftam_mod.TEST_INPUT_GRIDS.clear()
    load_end_outputs_from_json(json_path)
    load_json_inputs_from_json(json_path)

    ActionRegistry = reg_mod.ActionRegistry
    rs_mod.registry = ActionRegistry()
    rs_mod.registry.register_all_actions()

    values = build_values_by_input(DB_PATH)
    attrs = build_attributes_by_input_and_values(values)
    aa_mod._values_by_input = values
    aa_mod._attributes_by_input_and_values = attrs

    data = load_arc_json(json_path)
    procedures = generate_draft_procedure(DB_PATH, json_path, name="procedure")
    normalized = normalize_procedures_with_levels(list(procedures.values()))
    squeezed = squeeze_with_unresolved(normalized)

    generic_procs = [copy.deepcopy(p) for p in squeezed]
    for proc in generic_procs:
        proc.steps = remove_unresolved_actions_from_generic(proc.steps)

    train_results = evaluate_generic_procedures("train", generic_procs, data)

    if all(r["success"] for r in train_results):
        print("🎯 All trains passed, skipping second evaluation.")
        valid_procs = generic_procs
    else:
        valid_ids = filter_successful_procedures(train_results)
        if not valid_ids:
            return False
        valid_procs = [p for p in generic_procs if p.id in valid_ids]

    print("🎯 At least one generic procedure passed all training examples. Running on test set...")
    test_results = evaluate_generic_procedures("test", valid_procs, data)
    print_test_results(test_results, results_path)
    generate_submission_file(task_id, valid_procs, data, submission_path, test_results)
    compare_submission_to_arc_outputs(task_id, data, submission_path, comparison_path)
    return all(r['success'] for r in test_results)

def main():
    results = {}
    for fname in sorted(os.listdir(DONE_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(DONE_DIR, fname)
        task_id = fname.replace(".json", "")
        print(f"{fname}: ", end="")

        results_path = os.path.join(PROJECT_ROOT, "results", f"test_{task_id}_results.txt")
        submission_path = os.path.join(PROJECT_ROOT, "results", "submission.json")
        comparison_path = os.path.join(PROJECT_ROOT, "results", f"test_{task_id}_simple_comparison.txt")

        try:
            ok = test_file(path, results_path, submission_path, comparison_path, task_id)
        except Exception:
            ok = False
        print("SUCCESS" if ok else "FAIL")
        results[fname] = ok

    out_path = os.path.join(PROJECT_ROOT, "results", "done_tasks_results.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        for fname, ok in results.items():
            f.write(f"{fname}: {'SUCCESS' if ok else 'FAIL'}\n")

if __name__ == "__main__":
    main()
