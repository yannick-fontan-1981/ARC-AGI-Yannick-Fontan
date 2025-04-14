# scripts/verify_task.py

import json
import argparse
import os
import sys
from collections import defaultdict
import sqlite3
import subprocess

from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json, load_json_inputs_from_json, \
    TRAIN_INPUT_GRIDS, TEST_INPUT_GRIDS
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    extract_rules_from_procedure,
    test_generic_procs_on_trains,
    run_generic_procs_on_tests,
    load_arc_json, generate_submission_file, compare_submission_to_arc_outputs,
)
from constelize.tools.sqlite_loader import load_all_tables_from_sqlite
from constelize.tools.squeeze import squeeze_with_remapped_sources, normalize_procedures_with_levels

# Default task ID
#DEFAULT_TASK_ID = "3c9b0459"
#DEFAULT_TASK_ID = "9dfd6313"
#DEFAULT_TASK_ID = "67a3c6ac"
#DEFAULT_TASK_ID = "68b16354"
#DEFAULT_TASK_ID = "74dd1130"
#DEFAULT_TASK_ID = "6150a2bd"
DEFAULT_TASK_ID = "9172f3a0"
 #DEFAULT_TASK_ID = "a416b8f3_simple"
#DEFAULT_TASK_ID = "b1948b0a"
#DEFAULT_TASK_ID = "c8f0f002"
#DEFAULT_TASK_ID = "c59eb873"
#DEFAULT_TASK_ID = "d10ecb37"
#DEFAULT_TASK_ID = "d511f180"
#DEFAULT_TASK_ID = "ed36ccf7"

# Parse CLI arguments
parser = argparse.ArgumentParser()
parser.add_argument("--task_id", help="ARC task ID, e.g., 3c9b0459")
args = parser.parse_args()
TASK_ID = args.task_id if args.task_id else DEFAULT_TASK_ID

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

json_path = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "training-1", f"{TASK_ID}.json")
db_path = os.path.join(PROJECT_ROOT, "db", "database.db")
results_path = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_results.txt")
submission_path = os.path.join(PROJECT_ROOT, "results", "submission.json")
comparison_path = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_comparison.txt")

# Relaunch object_analysis and sprite_analysis scripts
object_script = os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py")
sprite_script = os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py")
subprocess.run(["python", object_script, json_path])
subprocess.run(["python", sprite_script, json_path])

def filter_successful_procedures(results):
    success_map = defaultdict(list)
    for r in results:
        success_map[r["procedure_id"]].append(r["success"])
    return [pid for pid, success_list in success_map.items() if all(success_list)]

# Load and process ARC task
load_end_outputs_from_json(json_path)
load_json_inputs_from_json(json_path)

data = load_arc_json(json_path)
procedures = generate_draft_procedure(db_path, json_path, name=f"{TASK_ID}_procedure")
normalized_procs = normalize_procedures_with_levels(list(procedures.values()))
generic_procs = squeeze_with_remapped_sources(normalized_procs)

# Test on training examples
results = test_generic_procs_on_trains(generic_procs, data)
with open(results_path, "w") as f:
    f.write("✅ TRAINING RESULTS:\\n")
    for r in results:
        status = "✅" if r["success"] else "❌"
        f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\\n")

# Keep only fully successful procedures
valid_proc_ids = filter_successful_procedures(results)
valid_procs = [proc for proc in generic_procs if proc.id in valid_proc_ids]

if valid_procs:
    print("🎯 At least one generic procedure passed all training examples. Running on test set...")
    test_results = run_generic_procs_on_tests(valid_procs, data)
    with open(results_path, "a") as f:
        print("\\n✅ TEST RESULTS:\\n")
        f.write("\\n✅ TEST RESULTS:\\n")
        for r in test_results:
            status = "✅" if r["success"] else "❌"
            print(f"{status} testId={r['testId']}, proc={r['procedure_id']}\\n")
            f.write(f"{status} testId={r['testId']}, proc={r['procedure_id']}\\n")

    generate_submission_file(TASK_ID, valid_procs, data, submission_path)
    compare_submission_to_arc_outputs(TASK_ID, data, submission_path, comparison_path)
else:
    print("⚠️ No fully successful generic procedure found. Skipping test execution.")

print("✅ Evaluation completed. Results saved to", results_path)
