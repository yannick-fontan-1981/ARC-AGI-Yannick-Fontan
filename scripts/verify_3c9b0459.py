import json
from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    extract_rules_from_procedure,
    test_generic_procs_on_trains,
    run_generic_procs_on_tests,
    load_arc_json, generate_submission_file, compare_submission_to_arc_outputs,
)
from constelize.tools.sqlite_loader import load_all_tables_from_sqlite
from constelize.tools.squeeze import squeeze_with_remapped_sources, \
    normalize_procedures_with_levels

import sys
import os
from collections import defaultdict

# Add the root directory to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

# 📁 Fichiers d'entrée
json_path = os.path.join(PROJECT_ROOT, "pattern-finder", "data", "training-1", "3c9b0459.json")
db_path = os.path.join(PROJECT_ROOT, "db", "database.db")
results_path = os.path.join(PROJECT_ROOT, "results", "test_3c9b0459_results.txt")
submission_path = os.path.join(PROJECT_ROOT, "results", "submission.json")

def filter_successful_procedures(results):
    success_map = defaultdict(list)
    for r in results:
        success_map[r["procedure_id"]].append(r["success"])
    return [pid for pid, success_list in success_map.items() if all(success_list)]

# 🧠 Étape 1 : Générer une procédure symbolique
load_end_outputs_from_json(json_path)
data = load_arc_json(json_path)
procedures = generate_draft_procedure(db_path, json_path, name="3c9b0459_procedure")
normalized_procs = normalize_procedures_with_levels(list(procedures.values()))
generic_procs = squeeze_with_remapped_sources(normalized_procs)

# 🧪 Étape 2 : Test sur les entrées d'entraînement
results = test_generic_procs_on_trains(generic_procs, data)

# 💾 Étape 3 : Sauvegarde des résultats d'entraînement
with open(results_path, "w") as f:
    f.write("✅ TRAINING RESULTS:\n")
    for r in results:
        status = "✅" if r["success"] else "❌"
        f.write(f"{status} trainId={r['trainId']}, proc={r['procedure_id']}\n")

# 🔎 Filtrer uniquement les procédures génériques 100% valides
valid_proc_ids = filter_successful_procedures(results)
valid_procs = [proc for proc in generic_procs if proc.id in valid_proc_ids]

# 🚀 Étape 4 : Si au moins une procédure passe tous les training, on teste les exemples de test
if valid_procs:
    print("🎯 At least one generic procedure passed all training examples. Running on test set...")
    test_results = run_generic_procs_on_tests(valid_procs, data)

    with open(results_path, "a") as f:
        f.write("\n✅ TEST RESULTS:\n")
        for r in test_results:
            status = "✅" if r["success"] else "❌"
            f.write(f"{status} testId={r['testId']}, proc={r['procedure_id']}\n")

    # 📤 Génération du fichier de soumission
    generate_submission_file("3c9b0459", valid_procs, data, submission_path)
else:
    print("⚠️ No fully successful generic procedure found. Skipping test execution.")

comparison_path = os.path.join(PROJECT_ROOT, "results", "test_3c9b0459_comparison.txt")
compare_submission_to_arc_outputs("3c9b0459", data, submission_path, comparison_path)

print("✅ Evaluation completed. Results saved to", results_path)