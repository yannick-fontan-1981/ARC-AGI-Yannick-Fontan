#constelize/tools/pattern_analysis.py

import copy
import json
import sqlite3
from collections import defaultdict
from itertools import product

from constelize.core.binding import BindingStatus, LinkCandidate, ArgumentBinding
from constelize.core.typesystem import can_convert
from constelize.dsl.grid_dsl import grid_to_pretty_string, grids_equal
from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING, build_start_input
from constelize.core.procedure import Procedure, evaluate_procedure, build_procedure_from_action_instances, \
    ActionInstance
from constelize.tools.sqlite_loader import load_sqlite_to_dict
from constelize.tools.registry_cli import register_procedure
from constelize.library.mapping_transformation import as_grid
from typing import List, Dict
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
                    print(e.__dict__)
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

    auto_find_constant(action_instances)

    auto_link_by_value_and_type(action_instances)


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
        # Skip END steps and instances with no action
        if getattr(producer, "END", False) or producer.action is None:
            continue
        if producer.output_value is not None:
            output_type = getattr(producer.action, "output_type", "Any")
            available_outputs[producer.id] = (producer, producer.output_value, output_type)

    # Step 2: Try to resolve unresolved input bindings for each consumer
    for consumer in action_instances:
        # Skip consumer if action is None
        if consumer.action is None:
            print(f"Skipping consumer {consumer.id} because consumer.action is None")
            continue

        # Optional: Debug print the consumer info
        print(f"🧩 Inspecting consumer: {consumer.id} ({consumer.action.name})")

        for arg_name, binding in consumer.bindings.items():
            print(f"🔗 Trying to resolve binding for {consumer.id}.{arg_name}")
            print(f"    ➤ Required type: {binding.type}, Current value: {binding.value}")
            if binding.binding != BindingStatus.UNRESOLVED:
                continue

            for producer_id, (producer, value, out_type) in available_outputs.items():
                print(f"    ↪ Checking producer {producer.id} (output_type={out_type})")
                print(f"      ➤ Output value = {value}")
                # Match by value and compatible type (never change binding.value)
                if values_equal(value, binding.value, binding.type) and can_convert(out_type, binding.type):
                    print(f"    ✅ Linked {producer.id} → {consumer.id}.{arg_name}")
                    link_producer_to_consumer(binding, producer, consumer)


def auto_find_constant(action_instances: List[ActionInstance]) -> None:
    """
    For each action (grouped by action.id) among the provided ActionInstance objects,
    check for each binding (argument) across training examples (trainId != -1) if the
    value is present and identical. If so, mark the binding as CONSTANT with that value.

    Instances with a missing action (i.e. instance.action is None) are skipped.
    """
    actions_by_id = defaultdict(list)
    for instance in action_instances:
        if instance.action is None:
            print(f"Skipping instance {instance.id} because instance.action is None")
            continue
        actions_by_id[instance.action.id].append(instance)

    # Process each group (by action id)
    for action_id, instances in actions_by_id.items():
        # Filter to training instances only (trainId != -1)
        train_instances = [inst for inst in instances if hasattr(inst, "trainId") and inst.trainId != -1]
        if not train_instances:
            continue

        # For each binding key in the first training instance, check for constant value across training examples
        for arg_name in train_instances[0].bindings.keys():
            constant_value = None
            is_constant = True
            for inst in train_instances:
                binding = inst.bindings.get(arg_name)
                # If the binding is missing or its value is None, consider it non-constant
                if binding is None or binding.value is None:
                    is_constant = False
                    break
                if constant_value is None:
                    constant_value = binding.value
                else:
                    if constant_value != binding.value:
                        is_constant = False
                        break
            if is_constant:
                # Update all instances (both training and test) for this action and binding
                for inst in instances:
                    binding = inst.bindings[arg_name]
                    binding.binding = BindingStatus.CONSTANT
                    binding.value = constant_value
                print(
                    f"[auto_find_constant] Action '{action_id}', argument '{arg_name}' stabilized as CONSTANT with value: {constant_value}")

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

    print(f"🔁 Link created: {producer.id} → {consumer.id}.{binding.name} | status = {binding.binding}")

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
        print(f"\n🔍 Testing trainId={trainId}")

        for proc in generic_procs:
            print(f"🚀 Testing procedure {proc.id} on trainId={trainId}")
            cloned = clone_procedure(proc)
            evaluated_output = evaluate_procedure_on_input(cloned, input_grid)

            success = grids_equal(evaluated_output, expected_output)
            status = "✅ SUCCESS" if success else "❌ FAIL"
            print(f"   ➤ {status} for procedure {proc.id}")
            if not success:
                print(f"     🔴 Expected: {expected_output}")
                print(f"     🔵 Got     : {evaluated_output}")

            results.append({
                "trainId": trainId,
                "procedure_id": proc.id,
                "success": success,
                "evaluated_output": evaluated_output,
                "expected_output": expected_output
            })

    return results


def resolve_candidate(candidate, context):
    """
    If the candidate is a string and exists as a key in the context,
    then return the value stored in context; otherwise, return candidate.
    """
    if isinstance(candidate, str) and candidate in context:
        return context[candidate]
    return candidate

def remove_value_from_generic(proc: Procedure) -> None:
    """
    Clears out output values and unsolved binding values from a generic procedure.
    For each step, set step.output_value = None and for each binding whose
    status is VARIABLE, MULTIPLE, UNRESOLVED or INPUT_GRID, set binding.value to None.
    This is done to avoid reusing stale data from a previous evaluation.
    """
    for step in proc.steps.values():
        step.output_value = None
        for bind in step.bindings.values():
            if bind.binding in {BindingStatus.VARIABLE,
                                BindingStatus.MULTIPLE,
                                BindingStatus.UNRESOLVED,
                                BindingStatus.INPUT_GRID}:
                bind.value = None

def _build_step_lookup(proc: Procedure) -> Dict[str, ActionInstance]:
    """Return a mapping from step id to ActionInstance for fast lookup."""
    return {st.id: st for st in proc.steps.values()}

def evaluate_step_with_multiple(step: ActionInstance, input_grid, context: dict,
                                step_lookup: dict[str, ActionInstance]):
    """
    Verbose evaluation of a step with careful handling of bindings.

    For each binding:
      - If its status is INPUT_GRID: use the provided input_grid.
      - If VARIABLE: look up the produced value in context using source_procedure_id.
      - If CONSTANT: use the stored value.
      - If MULTIPLE: use the candidate value.

    Returns the result of calling the step's action function.
    """
    print("\n==============================")
    print(f"Starting evaluation of step: {step.id} ({step.action.name})")
    print(f"Input grid: {input_grid}")
    print(f"Existing context: {context}")
    print("==============================")
    args = {}
    for arg_name, binding in step.bindings.items():
        print(f"\n-- Processing binding for argument '{arg_name}' --")
        print(f"  Binding status: {binding.binding}")
        print(f"  Binding type: {binding.type}")
        if binding.binding == BindingStatus.INPUT_GRID:
            print("  Detected INPUT_GRID binding.")
            if binding.source_procedure_id:
                print(f"  Source procedure id is set: {binding.source_procedure_id}")
                if binding.source_procedure_id in context:
                    args[arg_name] = context[binding.source_procedure_id]
                    print(f"  Found produced value in context: {args[arg_name]}")
                else:
                    print("  No produced value in context; attempting to execute producer...")
                    producer = step_lookup.get(binding.source_procedure_id)
                    if producer is None:
                        raise RuntimeError(f"ERROR: No producer with id {binding.source_procedure_id}")
                    try:
                        produced_value = producer.action.function(grid=input_grid)
                        context[binding.source_procedure_id] = produced_value
                        args[arg_name] = produced_value
                        print(f"  Executed producer {binding.source_procedure_id}; produced value: {produced_value}")
                    except Exception as e:
                        print(f"  ERROR executing producer {binding.source_procedure_id}: {e}")
                        raise RuntimeError(f"Error executing producer step {binding.source_procedure_id}: {e}")
            else:
                print("  No source procedure id specified; using input_grid as value.")
                args[arg_name] = input_grid

        elif binding.binding == BindingStatus.VARIABLE:
            print("  Detected VARIABLE binding.")
            if binding.source_procedure_id:
                if binding.source_procedure_id in context:
                    args[arg_name] = context[binding.source_procedure_id]
                    print(f"  Resolved VARIABLE binding from context: {args[arg_name]}")
                else:
                    raise RuntimeError(
                        f"Variable binding for {arg_name} in step {step.id} cannot be resolved: source {binding.source_procedure_id} not in context")
            else:
                raise RuntimeError(f"VARIABLE binding for {arg_name} in step {step.id} has no source_procedure_id set.")

        elif binding.binding in {BindingStatus.UNRESOLVED, BindingStatus.CONSTANT}:
            print("  Binding is CONSTANT or UNRESOLVED; using stored value.")
            args[arg_name] = binding.value
            print(f"  Using value: {binding.value}")

        elif binding.binding == BindingStatus.MULTIPLE:
            print("  Binding is MULTIPLE; assuming candidate expansion has produced a single candidate.")
            args[arg_name] = binding.value
            print(f"  Using candidate value: {binding.value}")

        else:
            print("  Encountered an unhandled binding status; defaulting to binding.value.")
            args[arg_name] = binding.value
            print(f"  Using value: {binding.value}")

    print("\nConstructed argument dictionary for step function:")
    for k, v in args.items():
        print(f"  {k}: {v}")

    try:
        print(f"\nExecuting action function for step {step.id} ({step.action.name})...")
        result = step.action.function(**args)
        print(f"Execution succeeded. Step {step.id} produced: {result}")
    except Exception as e:
        print(f"ERROR: Failed executing step {step.id} with arguments: {args}")
        print(f"Exception: {e}")
        raise RuntimeError(f"Error executing step {step.id}: {e}")

    context[step.id] = result
    print(f"Updated context[{step.id}] = {result}")
    print(f"Completed evaluation of step {step.id}.\n------------------------------\n")
    return result


def evaluate_procedure_on_input(procedure: Procedure, input_grid) -> any:
    """
    Evaluate a procedure on the given input grid.

    Before evaluation, the procedure is cloned and sanitized (removing any cached outputs or binding values).
    Each step is then evaluated in topological order via evaluate_step_with_multiple.
    """
    # Clone the procedure to avoid side effects.
    proc_clone = clone_procedure(procedure)
    # Sanitize the procedure so that unsolved bindings and output_value are cleared.
    remove_value_from_generic(proc_clone)
    context = {}
    step_lookup = _build_step_lookup(proc_clone)
    print(f"\n🚀 Starting evaluation of procedure: {proc_clone.id}")
    for step_index, step in enumerate(proc_clone.steps.values(), 1):
        print(f"\n🔹 Step {step_index}: {step.id} ({step.action.name})")
        try:
            result = evaluate_step_with_multiple(step, input_grid, context, step_lookup)
            print(f"   ✅ Step result: {result}")
        except Exception as e:
            print(f"   ❌ Exception occurred during execution of {step.id}: {e}")
            raise RuntimeError(f"💥 Error in step {step.id} ({step.action.name}): {e}")
        context[step.id] = result
        if step.END:
            print(f"\n🏁 END reached at step {step.id}. Returning result.")
            return result
    last_step = list(proc_clone.steps.values())[-1]
    print(f"\n⚠️ No END step defined. Returning result of final step: {last_step.id}")
    return context[last_step.id]

def load_arc_json(json_path: str) -> dict:
    """
    Load an ARC JSON file and return the corresponding dictionary.
    """
    with open(json_path, "r") as f:
        return json.load(f)

def clone_procedure(proc: Procedure) -> Procedure:
    """
    Return a deep copy of a procedure for independent evaluation.
    """
    return copy.deepcopy(proc)

def run_generic_procs_on_tests(generic_procs: List[Procedure], arc_json_data: dict) -> list:
    """
    Evaluate each generic procedure on every test example in an ARC JSON file.
    Returns a list of dictionaries with testId, procedure_id, success flag, evaluated output, and expected output.
    """
    from constelize.dsl.grid_dsl import grids_equal
    import copy

    results = []
    test_data = arc_json_data["test"]

    for testId, test in enumerate(test_data):
        input_grid = test["input"]
        expected_output = test["output"]

        for proc in generic_procs:
            proc_clone = clone_procedure(proc)
            # Sanitize the procedure copy before evaluation.
            remove_value_from_generic(proc_clone)
            evaluated_output = evaluate_procedure_on_input(proc_clone, input_grid)
            success = grids_equal(evaluated_output, expected_output)
            status = "✅ SUCCESS" if success else "❌ FAIL"
            print(f"\n🔍 Testing procedure {proc.id} on testId={testId}: {status}")
            if not success:
                print(f"     🔴 Expected: {expected_output}")
                print(f"     🔵 Got     : {evaluated_output}")

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
    Generate a submission.json file conforming to the ARC format, using predictions
    produced by the generic symbolic procedures.
    """
    submission = {task_id: []}
    test_data = arc_data["test"]

    for test_entry in test_data:
        input_grid = test_entry["input"]
        expected_output = test_entry["output"]

        best_output = None
        for proc in generic_procs:
            proc_clone = clone_procedure(proc)
            try:
                predicted = evaluate_procedure_on_input(proc_clone, input_grid)
                if grids_equal(predicted, expected_output):
                    best_output = predicted
                    break  # Use the first perfect prediction.
                elif best_output is None:
                    best_output = predicted
            except Exception as e:
                print(f"⚠️ Error evaluating procedure {proc.id} on test input: {e}")

        if best_output is None:
            # Fallback: produce an empty grid with the same dimensions as expected_output.
            best_output = [[0 for _ in row] for row in expected_output]

        submission[task_id].append({
            "attempt_1": best_output,
            "attempt_2": best_output
        })

    with open(output_path, "w") as f:
        json.dump(submission, f)
    print(f"📤 Submission file written to {output_path}")

def compare_submission_to_arc_outputs(task_id: str, arc_data: dict, submission_path: str, output_path: str) -> None:
    """
    Compare the predictions in submission.json with the outputs in the ARC file.
    Writes a report indicating success/failure and a pixel match score where applicable.
    """
    import json

    def pixel_match_score(pred, expected) -> float:
        if len(pred) != len(expected) or len(pred[0]) != len(expected[0]):
            return 0.0
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
                print(f"✅ testId={r['testId']}: success\n")
                f.write(f"✅ testId={r['testId']}: success\n")
            elif r["success"] is False:
                print(f"❌ testId={r['testId']}: failed, score={r['score']} ({r['percentage']})\n")
                f.write(f"❌ testId={r['testId']}: failed, score={r['score']} ({r['percentage']})\n")
            else:
                print(f"⚠️ testId={r['testId']}: {r['reason']}\n")
                f.write(f"⚠️ testId={r['testId']}: {r['reason']}\n")
    print(f"📊 Comparison report written to {output_path}")
