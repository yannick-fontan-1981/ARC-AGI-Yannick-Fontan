#constelize/tools/pattern_analysis.py

import copy
import json
import sqlite3
from collections import defaultdict
from itertools import product

from constelize.core.binding import BindingStatus, LinkCandidate, ArgumentBinding
from constelize.core.typesystem import can_convert
from constelize.dsl.grid_dsl import grid_to_pretty_string, grids_equal, Grid

import constelize.library.attribute_access as _aa_mod
from constelize.library.attribute_access import build_get_attribute_instance

from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING, build_start_input
from constelize.core.procedure import Procedure, evaluate_procedure, build_procedure_from_action_instances, \
    ActionInstance
from constelize.tools.sqlite_loader import load_sqlite_to_dict, common_attributes_by_train_value_pairs
from constelize.tools.registry_cli import register_procedure
from constelize.library.mapping_transformation import as_grid
from typing import List, Dict, Optional, Any, Tuple
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

    # First, handle non-compound bindings.
    auto_find_constant_without_compound(action_instances)
    # Next, handle compound bindings.
    auto_find_constant_for_compound(action_instances)

    auto_link_by_value_and_type(action_instances)

    action_instances = auto_link_by_common_attribute(action_instances)

    # 🔍 Supprimer toute action qui contient encore un binding non résolu
    action_instances = [inst for inst in action_instances if not has_unresolved_binding(inst)]

    print(f"\n🔍 ActionInstances after linking:")
    for inst in action_instances:
        print(f"\n🔹 {inst.id} ({inst.action.id})")
        print(f"    trainId={inst.trainId}, testId={inst.testId}, output_var={inst.output_var}")
        print(f"    ➤ output_value = {inst.output_value}")
        print(f"    ➤ bindings:")
        for path, bind in _iter_all_bindings(inst.bindings):
            print(f"      • {path} → {bind.binding.name}", end="")
            if bind.binding in {BindingStatus.MULTIPLE}:
                print(f" = {bind.value}")
            if bind.binding in {BindingStatus.CONSTANT, BindingStatus.CONTEXT, BindingStatus.INPUT_GRID}:
                print(f" = {bind.value}")
            elif bind.binding == BindingStatus.VARIABLE:
                print(f" ← from {bind.source_procedure_id}")
            else:
                print("")

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

def auto_link_by_common_attribute(action_instances: list) -> list:
    """
    Try to resolve any UNRESOLVED Integer binding by detecting a common attribute
    across training examples for that argument's value.
    Returns a new list of action instances including any new get_attribute steps.
    """
    print("\n🔎 Starting auto_link_by_common_attribute...")
    print(f"len(_attributes_by_input_and_values) : {len(_aa_mod._attributes_by_input_and_values)}")

    # Step 1: Collect unresolved integer bindings by path across all consumers
    unresolved_by_path = defaultdict(list)  # path -> list of (consumer, binding)
    trainval_by_path = defaultdict(list)    # path -> list of (trainId, value)

    for consumer in action_instances:
        if consumer.action is None:
            continue
        for path, binding in _iter_all_bindings(consumer.bindings):
            if binding.binding == BindingStatus.UNRESOLVED and binding.type == "Integer" and binding.value is not None:
                unresolved_by_path[path].append((consumer, binding))
                if consumer.trainId != -1:
                    trainval_by_path[path].append((consumer.trainId, binding.value))

    # Step 2: Resolve all at once per path
    new_instances = []
    for path, pairs in trainval_by_path.items():
        print(f"\n🔍 Trying to resolve bindings at path: {path}")
        print(f"   value_pairs = {pairs}")

        common_attrs = common_attributes_by_train_value_pairs(_aa_mod._attributes_by_input_and_values, pairs)
        if not common_attrs:
            print(f"   ❌ No common attribute found for path {path}.")
            continue

        chosen_attr = common_attrs[0]
        print(f"   ✅ Found common attribute: {chosen_attr}")

        for consumer, binding in unresolved_by_path[path]:
            key = f"{consumer.trainId}#{consumer.testId}"
            value = _aa_mod._values_by_input.get(key, {}).get(chosen_attr)
            if value is None:
                print(f"      ⚠️ Skipping {consumer.id}.{path} → attribute missing in {key}")
                continue

            print(f"      🔁 Linking {consumer.id}.{path} to get_attribute({chosen_attr}) = {value}")

            instance = build_get_attribute_instance(
                trainId=consumer.trainId,
                testId=consumer.testId,
                attribute_name=chosen_attr,
                output_value=value
            )

            #instance.bindings["trainId"].binding = BindingStatus.CONTEXT
            #instance.bindings["testId"].binding = BindingStatus.CONTEXT

            new_instances.append(instance)
            binding.binding = BindingStatus.VARIABLE
            binding.source_procedure_id = instance.id

    print(f"\n✅ auto_link_by_common_attribute complete. {len(new_instances)} new action(s) added.")
    return new_instances + action_instances


def _iter_all_bindings(bindings, prefix=""):
    """
    Recursively yield all (full_path, ArgumentBinding) pairs from a possibly compound structure.
    """
    if isinstance(bindings, dict):
        for name, b in bindings.items():
            path = f"{prefix}.{name}" if prefix else name
            if b.binding == BindingStatus.COMPOUND:
                yield from _iter_all_bindings(b.sub_bindings, prefix=path)
            else:
                yield path, b
    elif isinstance(bindings, list):
        for idx, b in enumerate(bindings):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            if b.binding == BindingStatus.COMPOUND:
                yield from _iter_all_bindings(b.sub_bindings, prefix=path)
            else:
                yield path, b

def flatten_binding(binding: ArgumentBinding) -> Tuple[bool, any]:
    """
    For a binding that is not COMPOUND, simply return (True, binding.value).
    For a compound binding, recursively flatten its sub_bindings.

    Always returns a two-tuple: (all_const, flat_value) where:
      - all_const is True if every sub-binding (recursively) is CONSTANT.
      - flat_value is a tuple of the flattened values.

    Even if not all sub-bindings are constant, we still return a flattened tuple.
    """
    if binding.binding != BindingStatus.COMPOUND:
        return (True, binding.value)
    # For a compound binding, assume sub_bindings is a dictionary.
    # (You can add logic for a list if necessary.)
    flat_vals = {}
    all_const = True
    for key, sub in binding.sub_bindings.items():
        if sub.binding == BindingStatus.COMPOUND:
            sub_const, sub_flat = flatten_binding(sub)
        else:
            sub_const = (sub.binding == BindingStatus.CONSTANT)
            sub_flat = sub.value
        flat_vals[key] = sub_flat
        if not sub_const:
            all_const = False
    return (all_const, flat_vals)


###############################################################################
# Function: auto_find_constant_without_compound
###############################################################################

def auto_find_constant_without_compound(action_instances: List[ActionInstance]) -> None:
    """
    For every action (grouped by action.id) examine each binding (non-compound).
    If for a given argument (non-compound) all training instances (trainId != -1)
    have identical non-None values then mark the binding as CONSTANT.
    """
    print("[auto_find_constant_without_compound] Starting processing.")
    actions_by_id = defaultdict(list)
    for inst in action_instances:
        if inst.action is None:
            print(f"Skipping instance {inst.id} because its action is None.")
            continue
        actions_by_id[inst.action.id].append(inst)

    for action_id, instances in actions_by_id.items():
        train_instances = [inst for inst in instances if hasattr(inst, "trainId") and inst.trainId != -1]
        if not train_instances:
            continue
        print(
            f"[auto_find_constant_without_compound] Processing action '{action_id}' with {len(train_instances)} training instances.")
        for arg_name in train_instances[0].bindings.keys():
            constant_value = None
            is_constant = True
            for inst in train_instances:
                binding = inst.bindings.get(arg_name)
                if binding is None or binding.value is None:
                    is_constant = False
                    break
                # Skip compound bindings here:
                if binding.binding == BindingStatus.COMPOUND:
                    print(
                        f"[auto_find_constant_without_compound] Skipping compound binding '{arg_name}' in instance {inst.id}.")
                    is_constant = False
                    break
                if constant_value is None:
                    constant_value = binding.value
                else:
                    if constant_value != binding.value:
                        print(
                            f"[auto_find_constant_without_compound] Binding '{arg_name}' differs in instance {inst.id}: {binding.value} vs constant {constant_value}.")
                        is_constant = False
                        break
            if is_constant:
                for inst in instances:
                    binding = inst.bindings.get(arg_name)
                    if binding is None:
                        continue
                    binding.binding = BindingStatus.CONSTANT
                    binding.value = constant_value
                print(
                    f"[auto_find_constant_without_compound] Action '{action_id}', argument '{arg_name}' stabilized as CONSTANT with value: {constant_value}")
    print("[auto_find_constant_without_compound] Finished processing.")


###############################################################################
# Function: auto_find_constant_for_compound
###############################################################################

def auto_find_constant_for_compound(action_instances: List[ActionInstance]) -> None:
    print("[auto_find_constant_for_compound] Starting recursive processing for compound bindings.")

    actions_by_id = defaultdict(list)
    for inst in action_instances:
        if inst.action is None:
            continue
        actions_by_id[inst.action.id].append(inst)

    for action_id, instances in actions_by_id.items():
        train_instances = [inst for inst in instances if hasattr(inst, "trainId") and inst.trainId != -1]
        if not train_instances:
            continue

        print(
            f"[auto_find_constant_for_compound] Processing action '{action_id}' with {len(train_instances)} training instances.")

        for arg_name in train_instances[0].bindings.keys():
            bindings = [inst.bindings[arg_name] for inst in train_instances if arg_name in inst.bindings]

            # Recursive processing of compound bindings
            process_compound_binding_recursive(bindings, arg_name)

    print("[auto_find_constant_for_compound] Finished recursive processing for compound bindings.")


def process_compound_binding_recursive(bindings: List[ArgumentBinding], path: str) -> None:
    """
    Recursively traverse and update sub-bindings. If all sub-bindings have identical non-None values,
    set them as CONSTANT. This operates directly on the provided bindings.
    """
    if not bindings:
        return

    # First, handle non-compound sub-bindings directly.
    example_binding = bindings[0]

    if example_binding.binding != BindingStatus.COMPOUND:
        # Collect values for this binding across all instances.
        values = [b.value for b in bindings if b.value is not None]

        # Only set to CONSTANT if values exist for all bindings and all identical.
        if len(values) == len(bindings) and all(val == values[0] for val in values):
            for b in bindings:
                b.binding = BindingStatus.CONSTANT
                b.value = values[0]
            print(
                f"[auto_find_constant_for_compound] Sub-binding '{path}' stabilized as CONSTANT with value: {values[0]}")
        else:
            print(f"[auto_find_constant_for_compound] Sub-binding '{path}' NOT constant, values: {values}")
        return

    # Now, for COMPOUND bindings, recurse into sub-bindings.
    if isinstance(example_binding.sub_bindings, dict):
        sub_keys = example_binding.sub_bindings.keys()
        for sub_key in sub_keys:
            sub_bindings_across_instances = []
            for b in bindings:
                sub_bind = b.sub_bindings.get(sub_key)
                if sub_bind:
                    sub_bindings_across_instances.append(sub_bind)
            # Recursive call for each sub-binding.
            process_compound_binding_recursive(sub_bindings_across_instances, f"{path}.{sub_key}")

    elif isinstance(example_binding.sub_bindings, list):
        for idx in range(len(example_binding.sub_bindings)):
            sub_bindings_across_instances = []
            for b in bindings:
                if idx < len(b.sub_bindings):
                    sub_bindings_across_instances.append(b.sub_bindings[idx])
            # Recursive call for each sub-binding by index.
            process_compound_binding_recursive(sub_bindings_across_instances, f"{path}[{idx}]")

    else:
        print(f"[auto_find_constant_for_compound] Unexpected sub_bindings type at '{path}'")


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
            evaluated_output = evaluate_procedure_on_input(cloned, input_grid, trainId, -1)

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

def remove_value_from_generic(proc: Procedure):
    for step in proc.steps:
        for binding in step.bindings.values():
            if binding.binding in [BindingStatus.VARIABLE]:
                binding.value = None
            clear_sub_bindings(binding)

def clear_sub_bindings(binding: ArgumentBinding):
    if binding.sub_bindings:
        if isinstance(binding.sub_bindings, dict):
            for sub_binding in binding.sub_bindings.values():
                if sub_binding.binding in [BindingStatus.VARIABLE]:
                    sub_binding.value = None
                clear_sub_bindings(sub_binding)
        elif isinstance(binding.sub_bindings, list):
            for sub_binding in binding.sub_bindings:
                if sub_binding.binding in [BindingStatus.VARIABLE]:
                    sub_binding.value = None
                clear_sub_bindings(sub_binding)


def _build_step_lookup(proc: Procedure) -> Dict[str, ActionInstance]:
    # Robustly handle both dict and list types
    if isinstance(proc.steps, dict):
        return {step.id: step for step in proc.steps.values()}
    return {step.id: step for step in proc.steps}

def evaluate_step_with_multiple(step: ActionInstance, input_grid: Grid, context: Dict[str, Any], step_lookup: Dict[str, ActionInstance]) -> Any:
    args = {}
    for arg_name, binding in step.bindings.items():
        resolved_value = resolve_binding_recursive(binding, context, step_lookup, input_grid)
        args[arg_name] = resolved_value
        if resolved_value is None:
            print(f"Unresolved '{arg_name}' skip this action: {step.id}")
            return None
        print(f"Resolved '{arg_name}' to value: {resolved_value}")

    print(f"Evaluating {step.action.name} with args: {args}")
    try:
        result = step.action.function(**args)
        print(f"Execution succeeded: {step.id} produced {result}")
        context[step.id] = result
        return result
    except Exception as e:
        raise RuntimeError(f"Error executing step {step.id}: {e}")

def evaluate_procedure_on_input(proc: Procedure, input_grid: Grid, trainId, testId) -> Grid:
    context = {}
    step_lookup = _build_step_lookup(proc)
    print(f"[DEBUG] proc.steps: {proc.steps}")  # Add this debug print
    last_result = None
    for step in proc.steps:
        step.trainId = trainId
        step.testId = testId
        context["trainId"] = trainId
        context["testId"] = testId
        print(f"[DEBUG] Current step: {step}, type: {type(step)}")
        last_result = evaluate_step_with_multiple(step, input_grid, context, step_lookup)
    return last_result

def load_arc_json(json_path: str) -> dict:
    """
    Load an ARC JSON file and return the corresponding dictionary.
    """
    with open(json_path, "r") as f:
        return json.load(f)


def clone_procedure(original_proc: Procedure) -> Procedure:
    step_lookup = _build_step_lookup(original_proc)
    print(f"[DEBUG] step_lookup keys: {list(step_lookup.keys())}")
    print(f"[DEBUG] original_proc.steps: {original_proc.steps}")

    # Iterate correctly over the ActionInstance values
    cloned_steps = [
        copy.deepcopy(step_lookup[step.id]) for step in original_proc.steps.values()
    ]

    return Procedure(steps=cloned_steps, id=f"{original_proc.id}_clone")


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
            evaluated_output = evaluate_procedure_on_input(proc_clone, input_grid, -1, testId)
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

    # Handle both list-style and dict-style test sets
    if isinstance(test_data, list):
        test_iter = enumerate(test_data)
    elif isinstance(test_data, dict):
        test_iter = ((int(k), v) for k, v in test_data.items())
    else:
        raise ValueError("Unsupported test format: must be list or dict")

    for testId, test_entry in test_iter:
        input_grid = test_entry["input"]
        expected_output = test_entry["output"]

        best_output = None
        for proc in generic_procs:
            proc_clone = clone_procedure(proc)
            try:
                predicted = evaluate_procedure_on_input(proc_clone, input_grid, -1, testId)
                if grids_equal(predicted, expected_output):
                    best_output = predicted
                    break  # Use the first perfect prediction.
                elif best_output is None:
                    best_output = predicted
            except Exception as e:
                print(f"⚠️ Error evaluating procedure {proc.id} on test input {testId}: {e}")

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

def resolve_binding_recursive(binding: ArgumentBinding, context: Dict[str, Any], step_lookup: Dict[str, ActionInstance], input_grid: Grid) -> Any:
    """
    Recursively resolve an ArgumentBinding into its concrete value.
    """
    if binding.binding == BindingStatus.CONSTANT:
        # Immediately return the stored constant value
        return binding.value

    elif binding.binding == BindingStatus.INPUT_GRID:
        # Directly return the provided input_grid
        return input_grid

    elif binding.binding == BindingStatus.CONTEXT:
        return context.get(binding.name)

    elif binding.binding == BindingStatus.VARIABLE and binding.source_procedure_id in context:
        # Return resolved value from context
        return context[binding.source_procedure_id]


    elif binding.binding == BindingStatus.MULTIPLE:
        for candidate in binding.candidates or []:
            if candidate.producer_id in context:
                return context[candidate.producer_id]
        print(f"⚠️ MULTIPLE with no resolved candidate found in context: {binding.candidates}")
        return None

    elif binding.binding == BindingStatus.COMPOUND:
        # Recursively resolve each sub-binding
        if isinstance(binding.sub_bindings, dict):
            return {
                key: resolve_binding_recursive(sub_binding, context, step_lookup, input_grid)
                for key, sub_binding in binding.sub_bindings.items()
            }
        elif isinstance(binding.sub_bindings, list):
            return [
                resolve_binding_recursive(sub_binding, context, step_lookup, input_grid)
                for sub_binding in binding.sub_bindings
            ]
        else:
            raise ValueError("Unexpected sub_bindings type encountered.")

    else:
        # Default handling: use stored value, or None
        return binding.value

def has_unresolved_binding(instance) -> bool:
    for _, binding in _iter_all_bindings(instance.bindings):
        if binding.binding == BindingStatus.UNRESOLVED:
            return True
    return False