import copy
import json
import sqlite3
from collections import defaultdict

from constelize.core.binding import BindingStatus, LinkCandidate, ArgumentBinding
from constelize.core.typesystem import can_convert
from constelize.dsl.grid_dsl import grid_to_pretty_string, grids_equal
from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING, build_start_input
from constelize.core.procedure import Procedure, evaluate_procedure, build_procedure_from_action_instances
from constelize.tools.sqlite_loader import load_sqlite_to_dict
from constelize.tools.registry_cli import register_procedure
from constelize.library.mapping_transformation import as_grid
from typing import List
import traceback


def table_for_fact(fact_name: str) -> str:
    return {
        "rotated_180": "symmetry",
        "flipped_horizontal": "symmetry",
        "flipped_vertical": "symmetry",
    }.get(fact_name, fact_name)


def generate_action_instances_from_db(db_path: str) -> List:
    conn = sqlite3.connect(db_path)

    action_instances = []

    for mapping in FACT_TO_ACTION_MAPPING:
        try:
            rows = mapping.test_function(conn)
            for row in rows:
                try:
                    instance = mapping.build_function(row)
                    action_instances.append(instance)
                except Exception as e:
                    print(
                        f"⚠️ Failed to build ActionInstance for {mapping.fact_name} row {row.get('sprite_unique_id')}: {e}")
        except Exception as e:
            print(f"❌ SQL test_function failed for {mapping.fact_name}: {e}")

    conn.close()
    return action_instances


def generate_draft_procedure(db_path: str, json_path: str, name: str = "generated_procedure") -> List[Procedure]:
    action_instances = generate_action_instances_from_db(db_path)

    with open(json_path, "r") as f:
        json_data = json.load(f)

    # TRAIN
    for trainId, item in enumerate(json_data.get("train", [])):
        input_grid = item["input"]
        action_instances.append(build_start_input(trainId, input_grid, isTrain=True))

    # TEST
    for testId, item in enumerate(json_data.get("test", [])):
        input_grid = item["input"]
        action_instances.append(build_start_input(testId, input_grid, isTrain=False))


    #print(f"🧱 action_instances: {action_instances}")

    auto_link_by_value_and_type(action_instances)

    #TODO : auto_find_constant

    procedures = generate_procedures_by_train(action_instances)

    for train_id, proc in procedures.items():
        print(f"🔧 Procedure for train {train_id} has {len(proc.steps)} steps.")



    #print(generic_procs)

    #for instance in action_instances:
    #    print(f"🧱 Action: {instance.action.id}")
    #    print(f"   ↳ id            : {instance.id}")
    #    print(f"   ↳ trainId       : {instance.trainId}")
    #    print(f"   ↳ isFromInput   : {instance.isFromInput}")
    #    print(f"   ↳ isToOutput    : {instance.isToOutput}")
    #    print(f"   ↳ output_var    : {instance.output_var}")
    #    print(f"   ↳ used_by       : {instance.used_by}")
    #    print(f"   ↳ output_value  : {grid_to_pretty_string(instance.output_value)}")
    #    print(f"   ↳ bindings:")
    #    for name, binding in instance.bindings.items():
    #        print(f"            binding: {binding.binding}")
    #        print(f"source_procedure_id: {binding.source_procedure_id}")
    #        print(f"           - {name}: {grid_to_pretty_string(binding.value)}")
    #    print(f"   ↳ END           : {instance.END}")
    #    print()


    #print(f"   ↳ json_data  : {json_data}")
    #print(f"   ↳ json_data.get('train', [])  : {json_data.get("train", [])}")
    #print(f"   ↳ json_data.get('test', [])  : {json_data.get("test", [])}")


    #procedure = build_procedure_from_action_instances(action_instances, name=name)
    #register_procedure(procedure)
    return procedures



def extract_rules_from_procedure(procedure: Procedure) -> str:
    rule_descriptions = []
    for step in procedure.steps:
        action_id = step
        rule_descriptions.append(f"{action_id}")
    return "\n".join(rule_descriptions)


def evaluate_draft_procedure(procedure: Procedure, input_grid, expected_output_grid) -> bool:
    try:
        result = evaluate_procedure(procedure, input_grid)
        return result == expected_output_grid
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        return False

def auto_link_by_value_and_type(action_instances: list):
    """
    Try to auto-link unresolved input bindings in action_instances
    using available producers with matching value and compatible type.
    """
    # Step 1: Pre-fill available outputs from all action instances
    available_outputs = {}  # producer.id -> (producer_instance, value, type)
    for producer in action_instances:
        if getattr(producer, "END", False):
            continue  # Skip END steps
        if producer.output_value is not None:
            output_type = getattr(producer.action, "output_type", "Any")
            available_outputs[producer.id] = (producer, producer.output_value, output_type)


    #print(f"available_outputs")
    #print(available_outputs)

    # Step 2: Try to resolve unresolved input bindings
    for consumer in action_instances:
        for arg_name, binding in consumer.bindings.items():
            if binding.binding != BindingStatus.UNRESOLVED:
                continue

            for producer_id, (producer, value, out_type) in available_outputs.items():
                # Match by value and compatible type (never touch binding.value)
                if values_equal(value, binding.value, binding.type) and can_convert(out_type, binding.type):
                    link_producer_to_consumer(binding, producer, consumer)

def values_equal(v1, v2, type_name):
    if type_name == "Grid":
        return grids_equal(v1, v2)
    elif type_name == "FrozenSet":
        return frozenset(v1) == frozenset(v2)
    else:
        return v1 == v2

def link_producer_to_consumer(binding, producer, consumer):
    # Register consumer as dependent of this producer
    producer.used_by.append(consumer.id)

    # Add a candidate reference to the producer (using its ID)
    candidate = LinkCandidate(producer_id=producer.id, var_name=producer.id)

    if binding.candidates is None:
        binding.candidates = []
    binding.candidates.append(candidate)

    if len(producer.used_by) > 1:
        binding.binding = BindingStatus.MULTIPLE
        # Do NOT change binding.value
    else:
        binding.binding = BindingStatus.VARIABLE
        # Do NOT change binding.value
        binding.source_procedure_id = producer.id

def generate_procedures_by_train(action_instances: list) -> dict:
    """
    Crée une procédure par trainId pour les actions issues des données d'entraînement uniquement.
    """
    grouped = defaultdict(list)

    for instance in action_instances:
        if instance.isTrain and instance.trainId is not None:
            grouped[instance.trainId].append(instance)

    procedures_by_train = {}
    for train_id, instances in grouped.items():
        steps = {f"step_{i+1}": inst for i, inst in enumerate(instances)}
        proc = Procedure(id=f"proc_train_{train_id}", steps=steps)
        procedures_by_train[train_id] = proc

    return procedures_by_train

def test_generic_procs_on_trains(generic_procs, arc_json_data) -> List[dict]:
    """
    Teste chaque procédure générique sur tous les exemples d'entraînement d’un fichier ARC.
    Retourne une liste de résultats avec réussite ou échec.
    """
    results = []
    train_data = arc_json_data["train"]

    for trainId, train in enumerate(train_data):
        input_grid = train["input"]
        expected_output = train["output"]

        for proc in generic_procs:
            cloned = clone_procedure(proc)
            evaluated_output = evaluate_procedure_on_input(cloned, input_grid)

            success = grids_equal(evaluated_output, expected_output)
            results.append({
                "trainId": trainId,
                "procedure_id": proc.id,
                "success": success,
                "evaluated_output": evaluated_output,
                "expected_output": expected_output
            })

    return results

def evaluate_procedure_on_input(procedure, input_grid) -> any:
    context = {}

    print(f"\n🚀 Starting evaluation of procedure: {procedure.id}")
    for step_index, step in enumerate(procedure.steps.values(), 1):
        print(f"\n🔹 Step {step_index}: {step.id} ({step.action.name})")
        args = {}

        for arg_name, binding in step.bindings.items():
            print(f"   🔎 Binding {arg_name}: binding={binding.binding}, source_procedure_id={binding.source_procedure_id}")
            print(f"   └─ Binding '{arg_name}': {binding.binding.name}")
            if binding.binding == BindingStatus.CONSTANT:
                args[arg_name] = binding.value
                print(f"     ✅ Using constant value: {binding.value}")
            elif binding.binding == BindingStatus.VARIABLE and binding.source_procedure_id:
                val = context.get(binding.source_procedure_id)
                print(f"     🔁 Looking up value from '{binding.source_procedure_id}': {val}")
                if val is None:
                    raise ValueError(
                        f"❌ Missing value from step {binding.source_procedure_id} for {step.id}.{arg_name}")
                args[arg_name] = val
            elif step.action.name == "Get Input Grid":
                args[arg_name] = input_grid
                print(f"     📥 Injecting input grid directly for {arg_name}")

        print(f"   📦 Final args for step: {args}")

        try:
            if step.action.name == "Get Input Grid":
                result = input_grid
                print(f"   🟢 Result (input passthrough): {result}")
            else:
                result = step.action.function(**args)
                print(f"   ✅ Result: {result}")
        except Exception as e:
            print(f"   ❌ Exception occurred during execution of {step.id}")
            raise RuntimeError(f"💥 Error in step {step.id} ({step.action.name}): {e}")

        context[step.id] = result

        if step.END:
            print(f"\n🏁 END reached at step {step.id}. Returning result.")
            return result

    last_action = list(procedure.steps.values())[-1]
    print(f"\n⚠️ No END step defined. Returning result of last step: {last_action.id}")
    return context[last_action.id]

def load_arc_json(json_path: str) -> dict:
    """
    Charge un fichier ARC .json et retourne le dictionnaire correspondant.
    """
    with open(json_path, "r") as f:
        return json.load(f)

def clone_procedure(proc: Procedure) -> Procedure:
    """
    Fait une copie indépendante et propre d'une procédure pour exécution isolée.
    """
    return copy.deepcopy(proc)

def run_generic_procs_on_tests(generic_procs, arc_json_data) -> list:
    """
    Évalue chaque procédure générique sur tous les exemples de test d’un fichier ARC.
    Retourne une liste de résultats avec réussite ou échec.
    """
    from constelize.tools.pattern_analysis import evaluate_procedure_on_input
    from constelize.dsl.grid_dsl import grids_equal
    import copy

    results = []
    test_data = arc_json_data["test"]

    for testId, test in enumerate(test_data):
        input_grid = test["input"]
        expected_output = test["output"]

        for proc in generic_procs:
            cloned = copy.deepcopy(proc)
            evaluated_output = evaluate_procedure_on_input(cloned, input_grid)
            success = grids_equal(evaluated_output, expected_output)

            results.append({
                "testId": testId,
                "procedure_id": proc.id,
                "success": success,
                "evaluated_output": evaluated_output,
                "expected_output": expected_output
            })

    return results


def generate_submission_file(task_id: str, generic_procs: List[Procedure], arc_data: dict, output_path: str) -> None:
    """
    Génère un fichier submission.json conforme au format ARC officiel
    en utilisant les prédictions issues des procédures symboliques génériques.
    """
    submission = {task_id: []}
    test_data = arc_data["test"]

    for test_entry in test_data:
        input_grid = test_entry["input"]
        expected_output = test_entry["output"]

        best_output = None
        for proc in generic_procs:
            cloned = copy.deepcopy(proc)
            try:
                predicted = evaluate_procedure_on_input(cloned, input_grid)
                if grids_equal(predicted, expected_output):
                    best_output = predicted
                    break  # dès qu'une prédiction est parfaite, on la garde
                elif best_output is None:
                    best_output = predicted
            except Exception as e:
                print(f"⚠️ Error evaluating procedure {proc.id} on test input: {e}")

        if best_output is None:
            best_output = [[0 for _ in row] for row in expected_output]  # fallback : grille vide

        submission[task_id].append({
            "attempt_1": best_output,
            "attempt_2": best_output
        })

    with open(output_path, "w") as f:
        json.dump(submission, f)

    print(f"📤 Submission file written to {output_path}")


def compare_submission_to_arc_outputs(task_id: str, arc_data: dict, submission_path: str, output_path: str) -> None:
    """
    Compare les prédictions du fichier submission.json avec les outputs présents dans le fichier ARC (si disponibles).
    Écrit un fichier de rapport avec True/False + score en cas d'échec (pixels correspondants / total).
    """
    import json

    def pixel_match_score(pred, expected) -> float:
        if len(pred) != len(expected) or len(pred[0]) != len(expected[0]):
            return 0.0  # dimensions mismatch = 0%
        total = sum(len(row) for row in expected)
        correct = sum(
            1 for i in range(len(pred))
            for j in range(len(pred[0]))
            if pred[i][j] == expected[i][j]
        )
        return correct / total if total > 0 else 0.0

    with open(submission_path, "r") as f:
        submission = json.load(f)

    results = []
    test_data = arc_data.get("test", [])
    task_preds = submission.get(task_id, [])

    for i, test in enumerate(test_data):
        expected = test.get("output")
        if expected is None:
            results.append({
                "testId": i,
                "success": None,
                "reason": "No ground truth output in ARC file"
            })
            continue

        pred_entry = task_preds[i] if i < len(task_preds) else {}
        attempt_1 = pred_entry.get("attempt_1")
        attempt_2 = pred_entry.get("attempt_2")

        match1 = attempt_1 == expected
        match2 = attempt_2 == expected

        if match1 or match2:
            results.append({
                "testId": i,
                "success": True,
                "score": 1.0
            })
        else:
            best_score = max(pixel_match_score(attempt_1, expected), pixel_match_score(attempt_2, expected))
            results.append({
                "testId": i,
                "success": False,
                "score": best_score,
                "percentage": f"{round(best_score * 100, 2)}%"
            })

    with open(output_path, "w") as f:
        for r in results:
            if r["success"] is True:
                f.write(f"✅ testId={r['testId']}: success\n")
            elif r["success"] is False:
                f.write(f"❌ testId={r['testId']}: failed, score={r['score']} ({r['percentage']})\n")
            else:
                f.write(f"⚠️ testId={r['testId']}: {r['reason']}\n")

    print(f"📊 Comparison report written to {output_path}")
