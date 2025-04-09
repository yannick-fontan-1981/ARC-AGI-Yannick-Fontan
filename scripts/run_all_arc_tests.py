import os
import glob
from constelize.tools.pattern_analysis import (
    generate_draft_procedure,
    extract_rules_from_procedure,
    evaluate_rule_on_arc,
)

# 📁 Chemins d’accès
db_path = "../db/database.db"
arc_folder = "../pattern-finder/data/training-1"
json_files = glob.glob(os.path.join(arc_folder, "*.json"))

# ⚙️ Génère la procédure une seule fois
procedure = generate_draft_procedure(db_path, name="shared_procedure")
rules = extract_rules_from_procedure(procedure)

# 🔁 Applique chaque Rule à chaque fichier JSON
for arc_file in json_files:
    print(f"\n📂 Testing file: {os.path.basename(arc_file)}")
    for rule in rules:
        print(f"  ▶️ Rule: {rule.id}")
        results = evaluate_rule_on_arc(rule, arc_file)
        print(f"     ✅ {results['passes']} / {results['total']} passed")
        if results["passes"] > 0:
            print("     ✔️ Match found!")
            break  # On s'arrête si une règle passe pour ce test
