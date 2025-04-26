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

# def solve_4c4377d9(I):
#     x1 = hmirror(I)
#     O = vconcat(x1, I)
# def solve_6d0aefbc(I):
#     x1 = vmirror(I)
#     O = hconcat(I, x1)
# def solve_6fa7a44f(I):
#     x1 = hmirror(I)
#     O = vconcat(I, x1)
# def solve_5614dbcf(I):
#     x1 = replace(I, FIVE, ZERO)
#     O = downscale(x1, THREE)
# def solve_5bd6f4ac(I):
#     x1 = tojvec(SIX)
#     O = crop(I, x1, THREE_BY_THREE)
# def solve_5582e5ca(I):
#     x1 = mostcolor(I)
#     O = canvas(x1, THREE_BY_THREE)
# def solve_8be77c9e(I):
#     x1 = hmirror(I)
#     O = vconcat(I, x1)
# def solve_c9e6f938(I):
#     x1 = vmirror(I)
#     O = hconcat(I, x1)
# def solve_2dee498d(I):
#     x1 = hsplit(I, THREE)
#     O = first(x1)

# Training 2
DEFAULT_TASK_ID = "4c4377d9"
#DEFAULT_TASK_ID = "6d0aefbc"
#DEFAULT_TASK_ID = "6fa7a44f"
#DEFAULT_TASK_ID = "5614dbcf"
#DEFAULT_TASK_ID = "5bd6f4ac"
#DEFAULT_TASK_ID = "5582e5ca"
#DEFAULT_TASK_ID = "8be77c9e"
#DEFAULT_TASK_ID = "c9e6f938"
#DEFAULT_TASK_ID = "2dee498d"

trainings_number = 2

parser = argparse.ArgumentParser()
parser.add_argument("--task_id", help="ARC task ID, e.g., 3c9b0459")
args = parser.parse_args()
TASK_ID = args.task_id if args.task_id else DEFAULT_TASK_ID

PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

json_path = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "training-" + str(trainings_number), f"{TASK_ID}.json")
db_path = os.path.join(PROJECT_ROOT, "db", "database.db")
results_path = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_results.txt")
submission_path = os.path.join(PROJECT_ROOT, "results", "submission.json")
comparison_path = os.path.join(PROJECT_ROOT, "results", f"test_{TASK_ID}_comparison.txt")

# Relaunch analyses
subprocess.run(["python", os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py"), json_path])
subprocess.run(["python", os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py"), json_path])
subprocess.run(["python", os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py"), json_path])

_values = build_values_by_input(db_path)
_attrs  = build_attributes_by_input_and_values(_values)
_aa_mod._values_by_input = _values
_aa_mod._attributes_by_input_and_values = _attrs
print(f"[verify_task] Injected attributes: {len(_attrs)} entries")

# Load data
load_end_outputs_from_json(json_path)
load_json_inputs_from_json(json_path)
data = load_arc_json(json_path)
procedures = generate_draft_procedure(db_path, json_path, name=f"{TASK_ID}_procedure")

# the number of trains :
btm.TOTAL_TRAINS = len(procedures)
btm.ALL_TRAIN_IDS = set(range(btm.TOTAL_TRAINS))

print("\n📦 [Post generate_draft_procedure] Listing initial steps:")
for proc_id, proc in procedures.items():
    print(f"  🔸 {proc_id} has {len(proc.steps)} steps")
    for step in proc.steps.values():
        print(f"    • {step.id} ({step.action.id})")
        if "repeated_sprite" in step.id or step.action.id == "repeated_sprite":
            print(f"    🧩 FOUND repeated_sprite in {step.id}")

normalized_procs = normalize_procedures_with_levels(list(procedures.values()))

print("\n🧪 [Pre-Squeeze] Inspecting normalized procedures...")
for i, proc in enumerate(normalized_procs):
    print(f"  📦 Proc {i+1}: {proc.id} with {len(proc.steps)} steps")
    for step in proc.steps.values():
        print(f"    🔹 {step.id} ({step.action.name})")
        if "repeated_sprite" in step.id or step.action.id == "repeated_sprite":
            print(f"    🧩 Found repeated_sprite step in {proc.id} → {step.id}")

generic_proc_with_unresolved = squeeze_with_unresolved(normalized_procs)

print("\n🧪 [Post-Squeeze] Inspecting unresolved generic procedures...")
for i, proc in enumerate(generic_proc_with_unresolved):
    print(f"  🧪 Generic Proc {i+1}: {proc.id} with {len(proc.steps)} steps")
    for step in proc.steps.values():
        print(f"    🔸 {step.id} ({step.action.name})")
        if "repeated_sprite" in step.id or step.action.id == "repeated_sprite":
            print(f"    🔍 STILL has repeated_sprite → {step.id}")

generic_procs = copy.deepcopy(generic_proc_with_unresolved)


# === EVALUATION & PRUNING ===
results = evaluate_generic_procedures("train", generic_procs, data)

if all(r["success"] for r in results):
    print("🎯 All trains passed, skipping second evaluation.")
    with open(results_path, "w") as f:
        f.write("✅ TRAINING RESULTS:\n")
        for r in results:
            status = "✅" if r["success"] else "❌"
            f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")
    valid_proc_ids = [proc.id for proc in generic_procs]
    valid_procs = [proc for proc in generic_procs if proc.id in valid_proc_ids]
    print("🎯 At least one generic procedure passed all training examples. Running on test set...")
    test_results = evaluate_generic_procedures("test", valid_procs, data)
    print_test_results(test_results, results_path)
    generate_submission_file(TASK_ID, valid_procs, data, submission_path, test_results)
    compare_submission_to_arc_outputs(TASK_ID, data, submission_path, comparison_path)

    total_time = time.time() - start_time
    print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")
    print("✅ Evaluation completed. Results saved to", results_path)
    exit(0)

print(f"\n🔗 [Link Summary Before Removal] for procedure: {proc.id}")
for step in proc.steps.values():
    print(f"  🔹 Step {step.id} ({step.action.id})")
    for name, bind in step.bindings.items():
        desc = f"    • {name}: {bind.binding.name}"
        if bind.binding == BindingStatus.CONSTANT:
            desc += f" = {bind.value}"
        elif bind.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE):
            if bind.source_procedure_id:
                desc += f" → from {bind.source_procedure_id}"
            if bind.candidates:
                cand_ids = ', '.join(c.producer_id for c in bind.candidates)
                desc += f" | candidates: {cand_ids}"
        elif bind.binding == BindingStatus.INPUT_GRID:
            desc += " (from INPUT_GRID)"
        print(desc)

# Else: prune unresolved actions
for proc in generic_procs:
    proc.steps = remove_unresolved_actions_from_generic(proc.steps)

validate_get_start_input_usage(generic_procs)

print("🔧 Pruning generic procedures until stable…")
generic_procs = iterative_prune(generic_procs, data)

print("=== GENERIC PROCEDURES ===")
for i, proc in enumerate(generic_procs):
    print(f"[{i}] Procedure id={proc.id}, steps={list(proc.steps.keys())}")
    for sid, step in proc.steps.items():
        binds = []
        for name, bind in step.bindings.items():
            st = bind.binding.name
            if bind.binding.name == "CONSTANT":
                binds.append(f"{name}=CONST({bind.value})")
            elif bind.binding.name in ("VARIABLE", "MULTIPLE"):
                src = bind.source_procedure_id or ", ".join(c.producer_id for c in (bind.candidates or []))
                binds.append(f"{name}={st}→{src}")
            else:
                val = f"={bind.value}" if bind.value is not None else ""
                binds.append(f"{name}={st}{val}")
        print(f"     - {sid}: action={step.action.id}, " + "; ".join(binds))
print("===========================")

# Second evaluation
results = evaluate_generic_procedures("train", generic_procs, data)
with open(results_path, "w") as f:
    f.write("✅ TRAINING RESULTS:\n")
    for r in results:
        status = "✅" if r["success"] else "❌"
        f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")

valid_proc_ids = filter_successful_procedures(results)
valid_procs = [proc for proc in generic_procs if proc.id in valid_proc_ids]

if valid_procs:
    print("🎯 At least one generic procedure passed all training examples. Running on test set...")
    test_results = evaluate_generic_procedures("test", valid_procs, data)
    print_test_results(test_results, results_path)
    generate_submission_file(TASK_ID, valid_procs, data, submission_path, test_results)
    compare_submission_to_arc_outputs(TASK_ID, data, submission_path, comparison_path)
else:
    print("⚠️ No fully successful generic procedure found. Skipping test execution.")

total_time = time.time() - start_time
print(f"\n⏱️ Total verification time: {total_time:.2f} seconds")
print("✅ Evaluation completed! Results saved to", results_path)
