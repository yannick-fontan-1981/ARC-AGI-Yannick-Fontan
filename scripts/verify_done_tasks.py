#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
import time

from scripts.verify_utils import filter_successful_procedures, SCRIPT_DIR
# Import the shared test_file and timeout machinery from verify_task
from scripts.verify_task import test_file as vt_test_file, run_with_timeout, TimeoutException

# Paths configuration
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DONE_DIR = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "done")
DB_PATH = os.path.join(PROJECT_ROOT, "db", "database.db")
ORIG_DB = DB_PATH + ".orig"

FIRST_SIGHT_SCRIPT = os.path.join(PROJECT_ROOT, "pattern-finder", "first_sight_analysis.py")
OBJECT_SCRIPT     = os.path.join(PROJECT_ROOT, "pattern-finder", "object_analysis.py")
SPRITE_SCRIPT     = os.path.join(PROJECT_ROOT, "pattern-finder", "sprite_analysis.py")

total_start_time = time.time()

if not os.path.exists(ORIG_DB):
    shutil.copy(DB_PATH, ORIG_DB)

def reset_database():
    shutil.copy(ORIG_DB, DB_PATH)

def run_analysis_scripts(json_path: str):
    for script in (FIRST_SIGHT_SCRIPT, OBJECT_SCRIPT, SPRITE_SCRIPT):
        subprocess.run([sys.executable, script, json_path], check=True)

# Local wrapper that applies a timeout to vt_test_file
def test_file(json_path: str,
              results_path: str,
              submission_path: str,
              comparison_path: str,
              task_id: str,
              timeout: int = 30) -> bool:
    # keep the local DB reset
    reset_database()
    # Delegate heavy lifting under a timeout
    try:
        return run_with_timeout(
            vt_test_file,
            json_path,
            DB_PATH,
            results_path,
            submission_path,
            comparison_path,
            task_id,
            1,            # trainings_number (unused in vt_test_file)
            timeout=timeout
        )
    except TimeoutException as te:
        print(f"⚠️ Timeout during verify_task for {task_id}: {te}")
        return False
    except Exception as e:
        print(f"❌ Exception during verify_task for {task_id}: {e}")
        return False


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
        ok = test_file(path, results_path, submission_path, comparison_path, task_id)
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