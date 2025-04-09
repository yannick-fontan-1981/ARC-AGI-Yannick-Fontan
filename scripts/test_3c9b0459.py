import os

from constelize.tools.fact_to_action_mapping import load_end_outputs_from_json
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    extract_rules_from_procedure,
)
from constelize.core.procedure import evaluate_procedure
from constelize.tools.sqlite_loader import load_all_tables_from_sqlite

# 📁 Fichiers d'entrée
json_path = "pattern-finder/data/training-1/3c9b0459.json"
db_path = "db/database.db"
results_path = "results/test_3c9b0459_results.txt"

# 🧠 Étape 1 : Générer une procédure symbolique
load_end_outputs_from_json(json_path)
procedure = generate_draft_procedure(db_path, json_path, name="3c9b0459_procedure")

# 📜 Étape 2 : Extraire les règles symboliques
rules = extract_rules_from_procedure(procedure)

# 🧪 Étape 3 : Évaluer la procédure sur les données d’entrée
tables = load_all_tables_from_sqlite(db_path)
evaluation_result = evaluate_procedure(procedure, tables)

# 💾 Étape 4 : Sauvegarde du résultat
with open(results_path, "w") as f:
    f.write("✅ RULES:\n")
    for rule in rules:
        f.write(f"- {rule}\n")

    f.write("\n✅ EVALUATION:\n")
    f.write(str(evaluation_result))

print("✅ Evaluation completed. Results saved to", results_path)
