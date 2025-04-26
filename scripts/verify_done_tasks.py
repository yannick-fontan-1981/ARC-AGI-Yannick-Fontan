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
import time
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

# **NEW**: import the shared test_file from verify_task
from scripts.verify_task import test_file as vt_test_file

total_start_time = time.time()

# Paths configuration
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DONE_DIR = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "done-1")
DB_PATH = os.path.join(PROJECT_ROOT, "db", "database.db")
ORIG_DB = DB_PATH + ".orig"

FIRST_SIGHT_SCRIPT = os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py")
OBJECT_SCRIPT     = os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py")
SPRITE_SCRIPT     = os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py")

if not os.path.exists(ORIG_DB):
    shutil.copy(DB_PATH, ORIG_DB)

def reset_database():
    shutil.copy(ORIG_DB, DB_PATH)

def run_analysis_scripts(json_path: str):
    for script in (FIRST_SIGHT_SCRIPT, OBJECT_SCRIPT, SPRITE_SCRIPT):
        subprocess.run([sys.executable, script, json_path], check=True)

def test_file(json_path: str,
              results_path: str,
              submission_path: str,
              comparison_path: str,
              task_id: str) -> bool:
    # keep the local DB reset
    reset_database()
    # Delegate all the heavy lifting to verify_task.py's test_file
    # pass trainings_number=2 (unused inside vt_test_file)
    return vt_test_file(
        json_path=json_path,
        db_path=DB_PATH,
        results_path=results_path,
        submission_path=submission_path,
        comparison_path=comparison_path,
        task_id=task_id,
        trainings_number=1
    )

def main():
    results = {}
    for fname in sorted(os.listdir(DONE_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(DONE_DIR, fname)
        task_id = fname.replace(".json", "")
        print(f"{fname}: ", end="")

        results_path    = os.path.join(PROJECT_ROOT, "results", f"test_{task_id}_results.txt")
        submission_path = os.path.join(PROJECT_ROOT, "results", "submission.json")
        comparison_path = os.path.join(PROJECT_ROOT, "results", f"test_{task_id}_simple_comparison.txt")

        start_time = time.time()
        try:
            ok = test_file(path, results_path, submission_path, comparison_path, task_id)
        except Exception as e:
            print(f"❌ Exception occurred during {fname}: {e}")
            import traceback
            traceback.print_exc()
            ok = False
        duration = time.time() - start_time
        print(f"{'SUCCESS' if ok else 'FAIL'} ({duration:.2f}s)")
        results[fname] = (ok, duration)

    out_path = os.path.join(PROJECT_ROOT, "results", "done_tasks_results.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        for fname, (ok, duration) in results.items():
            status = "SUCCESS" if ok else "FAIL"
            f.write(f"{fname}: {status} in {duration:.2f} seconds\n")

    total_time = time.time() - total_start_time
    print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")

if __name__ == "__main__":
    main()
