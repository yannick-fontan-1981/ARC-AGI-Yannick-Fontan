#constelize/tools/pattern_analysis.py

import copy
import json
import sqlite3
from collections import defaultdict
from itertools import product

import constelize.tools.globals as GLOBAL
from constelize.core.binding import BindingStatus, LinkCandidate, ArgumentBinding
from constelize.core.rule import Rule
from constelize.core.scenario import Scenario
from constelize.core.typesystem import can_convert
from constelize.dsl.grid_dsl import grid_to_pretty_string, grids_equal, Grid, concrete_grids_equal

import constelize.library.attribute_access as _aa_mod

from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING, build_start_input, \
    build_get_attribute_instance, build_select_sprite_and_attribute_instance
from constelize.core.procedure import Procedure, evaluate_procedure, ActionInstance
from constelize.tools.sqlite_loader import load_sqlite_to_dict, common_attributes_by_train_value_pairs, \
    extract_common_attribute_action
from constelize.tools.registry_cli import register_procedure
from constelize.library.mapping_transformation import as_grid
from typing import List, Dict, Optional, Any, Tuple
import traceback
import constelize.tools.binding_train_map as btm

from constelize.tools.squeeze import normalize_procedures_with_levels


def table_for_fact(fact_name: str) -> str:
    return {
        "rotated_180": "symmetry",
        "flipped_horizontal": "symmetry",
        "flipped_vertical": "symmetry",
    }.get(fact_name, fact_name)

def generate_action_instances_from_db(db_path: str, scenarioId: str, current_rule: Rule) -> List:
    ruleId = current_rule.id
    conn = sqlite3.connect(db_path)

    action_instances = []

    for mapping in FACT_TO_ACTION_MAPPING:
        try:
            if(mapping.fact_name=="denoise"):
                print("FACT_TO_ACTION_MAPPING denoise")
            rows = mapping.test_function(conn)
            for row in rows:
                try:
                    row["scenarioId"] = scenarioId
                    row["ruleId"] = ruleId
                    instance = mapping.build_function(row)
                    action_instances.append(instance)
                except Exception as e:
                    # ——— EXTRA DEBUG LOGGING ———————————————————————————————————————————————
                    print(f"[DEBUG gen_instances] mapping.fact_name = {mapping.fact_name}")
                    print(f"[DEBUG gen_instances] full row           = {row!r}")
                    print(f"[DEBUG gen_instances] raw inputs         = {{}}", row.get('data'))
                    print(f"[DEBUG gen_instances] exception type     = {type(e).__name__}")
                    import traceback;
                    traceback.print_exc()
                    # ——— ORIGINAL WARNING ——————————————————————————————————————————————
                    print(
                        f"⚠️ Failed to build ActionInstance for {mapping.fact_name} "
                        f"row {row.get('sprite_unique_id')}: {e}"
                    )
        except Exception as e:
            print(f"❌ SQL test_function failed for {mapping.fact_name}: {e}")

    conn.close()
    return action_instances

def generate_draft_procedure(action_instances, json_data: dict, scenarioId: str, current_rule: Rule) -> List[Procedure]:
    ruleId = current_rule.id

    print(f"🔍 Loaded {len(action_instances)} action instances from DB.")

    #with open(json_path, "r") as f:
    #    json_data = json.load(f)

    # TRAIN
    for trainId, item in enumerate(json_data.get("train", [])):
        input_grid = item["input"]
        ai = build_start_input(trainId, input_grid, True, scenarioId, ruleId)
        print(f"📥 Added get_start_input for trainId={trainId}: {ai.id}")
        action_instances.append(ai)

    # TEST
    for testId, item in enumerate(json_data.get("test", [])):
        input_grid = item["input"]
        ai = build_start_input(testId, input_grid, False, scenarioId, ruleId)
        print(f"📥 Added get_start_input for testId={testId}: {ai.id}")
        action_instances.append(ai)

    print("\n🔧 Running constant detection...")
    auto_find_constant_for_signature(action_instances)
    auto_find_constant_without_compound(action_instances)
    auto_find_constant_for_compound(action_instances)

    print("\n🔗 Linking by value and type...")
    auto_link_by_value_and_type(action_instances)

    print("\n🔗 Linking by common attributes...")
    action_instances = auto_link_by_common_attribute(action_instances, scenarioId, current_rule)

    print("\n🧹 Filtering unresolved bindings...")
    before = len(action_instances)

    unresolved = [inst for inst in action_instances if has_unresolved_binding(inst)]
    if unresolved:
        print("\n🧹 Unresolved actions that will be removed:")
        for inst in unresolved:
            print(f"  ⛔ {inst.id} ({inst.action.name})")
            for path, bind in _iter_all_bindings(inst.bindings):
                if bind.binding == BindingStatus.UNRESOLVED:
                    print(f"    • Missing: {path} → UNRESOLVED")

    action_instances = [inst for inst in action_instances if not has_unresolved_binding(inst)]
    after = len(action_instances)
    print(f"✅ Filtered unresolved actions: {before - after} removed, {after} remaining.")

    print(f"\n🔍 [Post-Linking] Final ActionInstances:")
    for inst in action_instances:
        print(f"\n🔹 {inst.id} ({inst.action.name})")
        print(f"    trainId={inst.trainId}, testId={inst.testId}, output_var={inst.output_var}")
        print(f"    ➤ output_value = {inst.output_value}")
        print(f"    ➤ bindings:")
        for path, bind in _iter_all_bindings(inst.bindings):
            line = f"      • {path} → {bind.binding.name}"
            if bind.binding in {BindingStatus.MULTIPLE, BindingStatus.CONSTANT, BindingStatus.CONTEXT}:
                line += f" = {bind.value}"
            elif bind.binding == BindingStatus.VARIABLE:
                line += f" ← from {bind.source_procedure_id}"
            print(line)

    print("\n🧩 Generating procedures by trainId...")
    procedures = generate_procedures_by_train(action_instances, scenarioId, ruleId)
    for train_id, proc in procedures.items():
        print(f"  🔧 Procedure for trainId={train_id} has {len(proc.steps)} steps:")
        for step in proc.steps.values():
            print(f"    • {step.id} ({step.action.name})")

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

    Also re-inject values into action_instances for each trainId individually.
    Supports recursive descent into COMPOUND bindings.
    """

    avoid_map = {
        a.action.id: set(getattr(a, "avoid_similar_as_source", []))
        for a in FACT_TO_ACTION_MAPPING
        if getattr(a, "avoid_similar_as_source", None)
    }

    link_stats = {}
    grouped_by_train = defaultdict(list)
    for instance in action_instances:
        grouped_by_train[instance.trainId].append(instance)

    for trainId, instances in grouped_by_train.items():
        print(f"\n🚂 Processing trainId={trainId} with {len(instances)} action(s)")
        successful_links = 0
        skipped_links = 0
        failed_links = 0

        available_outputs = {}
        for producer in instances:
            if getattr(producer, "END", False) or producer.action is None:
                continue
            if producer.output_value is not None:
                output_type = getattr(producer.action, "output_type", "Any")
                available_outputs[producer.id] = (producer, producer.output_value, output_type)

        for consumer in instances:
            if consumer.action is None:
                print(f"⛔ Skipping consumer {consumer.id} because consumer.action is None")
                continue

            print(f"\n🧩 Inspecting consumer: {consumer.id} ({consumer.action.name})")

            def recursively_process_bindings(binding: ArgumentBinding, path: str):
                nonlocal successful_links, skipped_links, failed_links

                print(f"🔗 Attempting to resolve binding '{path}'")
                print(f"    ➤ Required type: {binding.type}, Current status: {binding.binding}, Current value: {binding.value}")

                if binding.binding == BindingStatus.COMPOUND:
                    if isinstance(binding.sub_bindings, list):
                        for i, sub in enumerate(binding.sub_bindings):
                            recursively_process_bindings(sub, f"{path}[{i}]")
                    elif isinstance(binding.sub_bindings, dict):
                        for k, sub in binding.sub_bindings.items():
                            recursively_process_bindings(sub, f"{path}.{k}")
                    skipped_links += 1
                    return

                if binding.binding not in (BindingStatus.UNRESOLVED, BindingStatus.INPUT_GRID, BindingStatus.VARIABLE):
                    print(f"    ⏭️ Already resolved as {binding.binding}, skipping.")
                    skipped_links += 1
                    return

                if hasattr(binding, "per_train_value") and trainId in binding.per_train_value:
                    binding.value = binding.per_train_value[trainId]
                    binding.binding = BindingStatus.CONSTANT
                    print(f"    💉 Injected per-train constant for trainId={trainId}: {binding.value}")
                    successful_links += 1
                    return

                #print( "available_outputs.items()" )
                #print( available_outputs.items() )
                found = False
                sorted_producers = sorted(
                    available_outputs.items(),
                    key=lambda item: 0 if consumer.bindings.get(path.split(".")[0], binding).type == "Grid" and item[1][0].action.id == "get_start_input" else 1
                )
                for producer_id, (producer, value, out_type) in sorted_producers:
                    if producer.id == consumer.id:
                        print(f"    ⚠️ Skipping self-link: {producer.id}")
                        continue

                    if consumer.action.id in avoid_map and producer.action.id in avoid_map[consumer.action.id]:
                        print(f"    ⛔ Avoiding link from {producer.action.id} to {consumer.action.id} due to avoid_map")
                        continue

                    if binding.value is not None and not values_equal(value, binding.value, binding.type):
                        #print(f"    ❌ Value mismatch with producer {producer.id}")
                        #print(f"       value {value}")
                        #print(f"       binding.value {binding.value}")
                        #print(f"       binding.type {binding.type}")

                        continue
                    else:
                        #print("-----------------------")
                        #print("value")
                        #print(value)
                        #print("binding.value")
                        #print(binding.value)
                        print(f"    ✅ Value matches (or not specified) with producer {producer.id}, binding.type {binding.type} ")

                    if not can_convert(out_type, binding.type):
                        print(f"    ❌ Type {out_type} not compatible with required {binding.type}")
                        continue
                    else:
                        print(f"    ✅ Type {out_type} is compatible with {binding.type}")

                    if binding.binding == BindingStatus.INPUT_GRID:
                        print(f"    🛡️ INPUT_GRID detected – skipping linking but marking as resolved")
                        found = True
                        skipped_links += 1
                        break

                    print(f"    🔗 Linking {producer.id} → {consumer.id}.{path}")
                    link_producer_to_consumer(binding, producer, consumer, path)
                    found = True
                    successful_links += 1
                    continue

                if not found:
                    print(f"    ❌ No matching producer found for binding '{path}' on {consumer.id}")
                    failed_links += 1

            for arg_name, binding in consumer.bindings.items():
                recursively_process_bindings(binding, arg_name)

        link_stats[trainId] = {
            "successful": successful_links,
            "skipped": skipped_links,
            "failed": failed_links,
        }

    print("\n📊 Link Summary:")
    for trainId, stats in link_stats.items():
        print(f"  ▶️ trainId={trainId}: ✅ {stats['successful']} linked, 🛑 {stats['skipped']} skipped, ❌ {stats['failed']} unresolved")

def auto_link_by_common_attribute(
    action_instances: List,
    scenarioId: str,
    current_rule: Rule
) -> List:
    """
    Try to resolve any UNRESOLVED Integer or Color binding by detecting
    a common attribute across training examples for that argument's value.
    Returns a new list of action instances including any new get/select steps.
    """
    ruleId = current_rule.id
    print("\n🔎 auto_link_by_common_attribute...")

    # 1) Collect unresolved bindings
    unresolved_by_path = defaultdict(list)    # path -> [(consumer, binding), ...]
    trainval_by_path   = defaultdict(list)    # path -> [(trainId, value), ...]
    for consumer in action_instances:
        for path, binding in _iter_all_bindings(consumer.bindings):
            if binding.binding == BindingStatus.UNRESOLVED \
            and binding.value is not None \
            and binding.type in ("Integer", "Color"):
                unresolved_by_path[path].append((consumer, binding))
                if consumer.trainId != -1:
                    trainval_by_path[path].append((consumer.trainId, binding.value))

    new_instances = []

    # 2) For each path, attempt to extract a common-attribute action
    for path, pairs in trainval_by_path.items():
        binding_type = unresolved_by_path[path][0][1].type
        pairs = list(dict.fromkeys(pairs))
        print(f"\n🔍 Resolving path={path} type={binding_type}, value_pairs={pairs}")

        # pick the right attribute map
        if binding_type == "Integer":
            attr_map = GLOBAL.get_attributes_by_scenario_rule(scenarioId, ruleId)
        elif binding_type == "Color":
            attr_map = GLOBAL.get_attributes_colors_by_scenario_rule(scenarioId, ruleId)
        else:
            continue

        # call your refactored function
        action_spec = extract_common_attribute_action(
            attr_map, pairs, path, current_rule.tables
        )
        if action_spec is None:
            print(f"   ❌ No common attribute action for path {path}")
            continue

        # 3a) getAttributeAction
        if action_spec["type"] == "getAttributeAction":
            full_attr = action_spec["attribute"]               # e.g. "sprite_analysis.minX"
            print(f"   ✅ getAttributeAction → {full_attr}")

            for consumer, binding in unresolved_by_path[path]:
                key = f"{consumer.trainId}#{consumer.testId}"
                if binding_type == "Integer":
                    value = GLOBAL.get_values_by_scenario_rule(scenarioId, ruleId) \
                                 .get(key, {}) \
                                 .get(full_attr)
                else:
                    value = GLOBAL.get_colors_by_scenario_rule(scenarioId, ruleId) \
                                 .get(key, {}) \
                                 .get(full_attr)
                if value is None:
                    print(f"      ⚠️ Missing value for {consumer.id}.{path} in {key}")
                    continue

                print(f"      🔁 Linking {consumer.id}.{path} to get_attribute({full_attr}) = {value}")
                inst = build_get_attribute_instance(
                    trainId       = consumer.trainId,
                    testId        = consumer.testId,
                    binding_type  = binding_type,
                    attribute_name= full_attr,
                    output_value  = value,
                    scenarioId    = consumer.scenarioId,
                    ruleId        = consumer.ruleId
                )
                new_instances.append(inst)
                binding.binding = BindingStatus.VARIABLE
                binding.source_procedure_id = inst.id

        # 3b) selectSpriteAndAttributeAction
        elif action_spec["type"] == "selectSpriteAndAttributeAction":
            criteria = action_spec["criteria"]
            output_attr = action_spec["output_attribute"]
            sprite_ids = action_spec["for_sprites"]

            print(
                f"   ✅ selectSpriteAndAttributeAction → criteria={criteria}, attribute={output_attr}, sprites={sprite_ids}")

            # Loop over all consumers that are waiting for this value
            for consumer_step, binding in unresolved_by_path[path]:
                # Infer trainId/testId from the consumer (they are typically set)
                train_id = consumer_step.trainId
                test_id = consumer_step.testId

                # Compute output value for this context (using trainId/testId if needed)
                value = _aa_mod.select_sprite_and_attribute_fn(
                    scenarioId=scenarioId,
                    ruleId=ruleId,
                    criteria=criteria,
                    attribute_name=output_attr,
                    sprite_ids=sprite_ids,
                    trainId=train_id,
                    testId=test_id
                )

                # Build an ActionInstance for this consumer
                instance = build_select_sprite_and_attribute_instance(
                    trainId=train_id,
                    testId=test_id,
                    binding_type=binding_type,
                    output_value=value,
                    criteria=criteria,
                    attribute_name=output_attr,
                    sprite_ids=sprite_ids,
                    scenarioId=scenarioId,
                    ruleId=ruleId
                )

                # Register and link it
                new_instances.append(instance)
                binding.binding = BindingStatus.VARIABLE
                binding.source_procedure_id = instance.id

        else:
            print(f"   ⚠️ Unknown action type {action_spec['type']} for path {path}")

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

def auto_find_constant_for_signature(action_instances: List[ActionInstance]) -> None:
    """
    Level 1 constant detection (per your spec):

    1. Group by action.id **and** by trainId.
    2. Skip any action.id that does not appear in *every* train.
    3. For each action.id present in all trains:
       - For each instance in train 0, build a “signature” of its UNRESOLVED Integer bindings:
           sig = [(arg_name, value), …]
       - Check that *every* other train has *some* instance with exactly that same sig.
       - If so, **promote** those bindings in *all* matching instances to CONSTANT.
    """
    # 1) collect all trainIds
    train_ids = sorted({inst.trainId for inst in action_instances if inst.trainId is not None and inst.trainId != -1})

    # 2) group instances by action.id and trainId
    by_action: Dict[str, Dict[int, List[ActionInstance]]] = defaultdict(lambda: defaultdict(list))

    #print(action_instances)

    for inst in action_instances:
        if inst.action is None:
            continue
        tid = inst.trainId
        if tid is None or tid == -1:
            continue
        by_action[inst.action.id][tid].append(inst)

    # 3) for each action.id present in all trains
    for action_id, trains_map in by_action.items():
        if set(trains_map.keys()) != set(train_ids):
            # skip if not in every train
            continue

        # 4) for each candidate “base” in train 0
        for base in trains_map[train_ids[0]]:
            # build signature of its UNRESOLVED integer args
            sig: List[Tuple[str,int]] = [
                (name, b.value)
                for name, b in base.bindings.items()
                if b.binding == BindingStatus.UNRESOLVED
                   and b.type == "Integer"
                   and b.value is not None
            ]
            if not sig:
                continue

            # 5) find matching instance in each other train
            matched = {train_ids[0]: base}
            ok = True
            for tid in train_ids[1:]:
                found = None
                for inst in trains_map[tid]:
                    if all(
                        (inst.bindings[n].binding == BindingStatus.UNRESOLVED and
                         inst.bindings[n].value == v)
                        for n, v in sig
                    ):
                        found = inst
                        break
                if found:
                    matched[tid] = found
                else:
                    ok = False
                    break

            if not ok:
                continue

            # 6) promote all those bindings to CONSTANT
            for inst in matched.values():
                for name, value in sig:
                    b = inst.bindings[name]
                    b.binding = BindingStatus.CONSTANT
                    b.value = value

            print(f"[auto_find_constant_for_signature] "
                  f"Action '{action_id}' sig={sig} → promoted to CONSTANT")


###############################################################################
# Function: auto_find_constant_without_compound
###############################################################################


def auto_find_constant_without_compound(action_instances: List[ActionInstance]) -> None:
    """
    For every action (grouped by action.id) examine each non‑compound Integer binding.
    If for a given argument all training instances (trainId != -1)
    have identical integer values, mark that argument CONSTANT across ALL instances.
    """
    # 1) Group all instances by action ID
    actions_by_id = defaultdict(list)
    for inst in action_instances:
        if inst.action is None:
            continue
        actions_by_id[inst.action.id].append(inst)

    # 2) For each action, look at its Integer arguments
    for action_id, instances in actions_by_id.items():
        # Collect only those with trainId != -1
        train_instances = [inst for inst in instances if getattr(inst, "trainId", -1) != -1]
        if not train_instances:
            continue

        # Iterate over each argument name
        for arg_name, binding_example in train_instances[0].bindings.items():
            # Only consider pure Integer arguments
            if binding_example.type != "Integer" and binding_example.type != "Color":
                continue

            # Gather all train‐instance values for this argument
            values = []
            for inst in train_instances:
                b = inst.bindings.get(arg_name)
                # skip if missing, compound, or no value
                if b is None or b.binding == BindingStatus.COMPOUND or b.value is None:
                    values = None
                    break
                # skip non‐int values
                if not isinstance(b.value, int):
                    values = None
                    break
                values.append(b.value)

            # If we aborted or found <1 value, skip
            if not values:
                continue

            # Check if all are identical
            first_val = values[0]
            if all(v == first_val for v in values):
                # Stabilize: mark CONSTANT on every instance (train or test)
                for inst in instances:
                    b = inst.bindings.get(arg_name)
                    if b:
                        b.binding = BindingStatus.CONSTANT
                        b.value   = first_val
                print(f"[auto_find_constant_without_compound] Action '{action_id}', "
                      f"argument '{arg_name}' → CONSTANT = {first_val}")

###############################################################################
# Function: auto_find_constant_for_compound
###############################################################################

def auto_find_constant_for_compound(action_instances: List[ActionInstance]) -> None:
    print("[auto_find_constant_for_compound] Starting recursive processing for compound bindings.")

    # Étape 1 : identifier tous les trainId utilisés
    global_train_ids = {inst.trainId for inst in action_instances if inst.trainId is not None and inst.trainId != -1}
    print(f"[auto_find_constant_for_compound] Global trainIds = {sorted(global_train_ids)}")

    # Étape 2 : regrouper les actions par ID
    actions_by_id = defaultdict(list)
    for inst in action_instances:
        if inst.action is not None:
            actions_by_id[inst.action.id].append(inst)

    for action_id, instances in actions_by_id.items():
        # Étape 3 : sélectionner uniquement les instances de train
        train_instances = [inst for inst in instances if inst.trainId in global_train_ids]

        # Vérifie si toutes les trainId sont couvertes
        instance_train_ids = {inst.trainId for inst in train_instances}
        if instance_train_ids != global_train_ids:
            print(f"⚠️ [SKIP] Action '{action_id}' is missing train instances. Expected {sorted(global_train_ids)}, found {sorted(instance_train_ids)}")
            continue

        print(f"[auto_find_constant_for_compound] Processing action '{action_id}' with {len(train_instances)} training instances.")
        print(f"✅ All expected trainIds present: {sorted(instance_train_ids)}")

        # Traitement des arguments
        for arg_name in train_instances[0].bindings.keys():
            bindings_by_train = {
                inst.trainId: inst.bindings[arg_name]
                for inst in train_instances
                if arg_name in inst.bindings
            }

            if action_id == "unzoom":
                print("🧪 [DEBUG] arg_name =", arg_name)
                print("🧪 [DEBUG] train_ids =", list(bindings_by_train.keys()))
                print("🧪 [DEBUG] bindings =", list(bindings_by_train.values()))

            if set(bindings_by_train.keys()) != global_train_ids:
                print(f"⚠️ [SKIP] arg '{arg_name}' missing train bindings — expected={global_train_ids}, got={bindings_by_train.keys()}")
                continue

            bindings = list(bindings_by_train.values())
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
        return concrete_grids_equal(v1, v2)
    elif type_name == "FrozenSet":
        return frozenset(v1) == frozenset(v2)
    elif type_name.startswith("Array<"):
        subtype = type_name[6:-1]  # extrait "Grid" de "Array<Grid>"
        if len(v1) != len(v2):
            return False
        return all(values_equal(a, b, subtype) for a, b in zip(v1, v2))
    elif type_name == "Coord":
        return v1.get("x") == v2.get("x") and v1.get("y") == v2.get("y")
    else:
        return v1 == v2

def link_producer_to_consumer(binding, producer, consumer, path):
    # Register consumer as dependent of this producer
    producer.used_by.append(consumer.id)

    # Calculez le hash en fournissant les deux action IDs
    bh = btm.make_binding_hash(binding,
                           producer.action.id,
                           consumer.action.id,
                           path)

    # Add a candidate reference to the producer (using its ID)
    candidate = LinkCandidate(producer_id=producer.id, var_name=producer.id, binding_hash=bh)

    if binding.candidates is None:
        binding.candidates = []
    binding.candidates.append(candidate)

    if binding.source_procedure_id is not None:
        if  binding.source_procedure_id != producer.id:
            print(f"⚠️ Conflict: binding already linked to {binding.source_procedure_id}, now trying {producer.id}")
        binding.binding = BindingStatus.MULTIPLE
        # Do NOT change binding.value
    else:
        binding.binding = BindingStatus.VARIABLE
        # Do NOT change binding.value
        binding.source_procedure_id = producer.id

    # Enregistrez le trainId
    if consumer.trainId is not None and consumer.trainId > -1:
        btm.bindingTrainMap[bh].add(consumer.trainId)

    print(f"📍 binding-hash={bh} pour producer={producer.action.id} → consumer={consumer.action.id}, train={consumer.trainId}")

    print(f"🔁 Link created: {producer.id} → {consumer.id}.{binding.name} | status = {binding.binding}")

def generate_procedures_by_train(action_instances: list, scenarioId: str, ruleId: str) -> dict:
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
        proc = Procedure(id=f"proc_train_{train_id}", steps=steps, scenarioId=scenarioId, ruleId=ruleId)
        procedures_by_train[train_id] = proc

    return procedures_by_train

def pixel_accuracy(grid1, grid2):
    """
    Return a dictionary with pixel-level accuracy comparison between two grids:
    - matching: number of matching pixels
    - total: total number of pixels compared
    - accuracy: float between 0.0 and 1.0
    """
    if not isinstance(grid1, (list, tuple)) or not isinstance(grid2, (list, tuple)):
        return {"matching": 0, "total": 0, "accuracy": 0.0}

    if len(grid1) != len(grid2) or any(len(r1) != len(r2) for r1, r2 in zip(grid1, grid2)):
        return {"matching": 0, "total": 0, "accuracy": 0.0}

    matching = 0
    total = 0
    for row1, row2 in zip(grid1, grid2):
        for a, b in zip(row1, row2):
            total += 1
            if a == b:
                matching += 1

    accuracy = matching / total if total > 0 else 0.0
    return {"matching": matching, "total": total, "accuracy": accuracy}


def preprocess_arc_with_action(arc_data: dict,
                               action_inst) -> dict:
    """
    Apply `generic_proc.action_producing_output.action.function`
    to every train‐ and test‐input in arc_data, returning a fresh
    in-memory ARC dict with those transformed inputs.
    """
    fn = action_inst.action.function                     # the raw Python function
    # figure out the function's single argument name (e.g. "grid")
    arg_name = next(iter(action_inst.bindings.keys()))

    # transform the train set
    new_train = []
    for ex in arc_data["train"]:
        inp = ex["input"]
        # call fn as either fn(inp) or fn(**{arg_name: inp})
        try:
            out = fn(inp)
        except TypeError:
            out = fn(**{arg_name: inp})
        new_train.append({
            "input": out,
            "output": ex["output"]
        })

    # transform the test set (if any)
    new_test = []
    for ex in arc_data.get("test", []):
        inp = ex["input"]
        try:
            out = fn(inp)
        except TypeError:
            out = fn(**{arg_name: inp})
        new_test.append({"input": out})

    return {"train": new_train, "test": new_test}

def evaluate_generic_procedures_on_scenarios(mode: str, data: dict, scenarios: list):
    """
    Évalue un lot de procédures génériques par scénario.

    Args:
        mode: "train" ou "test"
        data: données ARC (JSON)
        scenarios: liste d’objets Scenario

    Returns:
        Dict[scenario_id] → liste des résultats d’évaluation
    """
    results_by_scenario = {}

    for scenario in scenarios:
        print(f"\n🔍 Evaluating scenario '{scenario.id}' with {len(scenario.rules)} rules.")

        if hasattr(scenario, "rule_to_launch_before") and scenario.rule_to_launch_before:
            pre_rule = scenario.rule_to_launch_before
            generic_proc = pre_rule.proc_producing_output
            action_inst = generic_proc.action_producing_output

            print(f"⚙️ Preprocessing scenario with action from rule '{pre_rule.id}'...")
            new_arc_data = preprocess_arc_with_action(data, action_inst)

            main_rule = scenario.rule_to_analyse
            print(f"➡️  Evaluating main rule '{main_rule.id}' with {len(main_rule.generic_procs)} procs")

            results = evaluate_generic_procedures(
                mode=mode,
                procedures=main_rule.generic_procs,
                data=new_arc_data,
                scenarioId=scenario.id,
                ruleId="*",
            )
            results_by_scenario[scenario.id] = results

            # 🔁 Répartition dans le rule cible uniquement
            proc_result_map = defaultdict(list)
            for r in results:
                proc_result_map[r["procedure_id"]].append(r)
            main_rule.train_results = []
            for proc in main_rule.generic_procs:
                main_rule.train_results.extend(proc_result_map.get(proc.id, []))

        else:
            all_generic_procs = []
            for rule in scenario.rules.values():
                all_generic_procs.extend(rule.generic_procs)

            if not all_generic_procs:
                print(f"⚠️ No generic procedures in scenario '{scenario.id}'")
                continue

            print(f"➡️  Evaluating all rules with {len(all_generic_procs)} generic procedures...")
            results = evaluate_generic_procedures(
                mode=mode,
                procedures=all_generic_procs,
                data=data,
                scenarioId=scenario.id,
                ruleId="*",
            )
            results_by_scenario[scenario.id] = results

            # 🔁 Répartition dans chaque règle du scénario
            proc_result_map = defaultdict(list)
            for r in results:
                proc_result_map[r["procedure_id"]].append(r)

            for rule_id, rule in scenario.rules.items():
                rule.train_results = []
                for proc in rule.generic_procs:
                    rule.train_results.extend(proc_result_map.get(proc.id, []))
                print(f"📌 Rule '{rule_id}' received {len(rule.train_results)} result(s).")

    return results_by_scenario

def evaluate_generic_procedures(
    mode: str,
    procedures: List[Procedure],
    data,
    scenarioId: str,
    ruleId: str,
    allow_multiple_end=False,
    return_execution_trace=False
):
    def get_original_step(proc: Procedure, cloned_step_id: str) -> Optional[ActionInstance]:
        return proc.steps.get(cloned_step_id)

    def learn_from_success(proc: Procedure, selected_step: Optional[str]):
        if selected_step:
            original_step = get_original_step(proc, selected_step)
            if original_step:
                original_step.END = True
                print(f"💾 Learned END=True on step {selected_step} for procedure {proc.id}")

    def fallback_if_no_end(proc_clone: Procedure, candidate_outputs: List):
        if not candidate_outputs:
            for step in reversed(proc_clone.steps.values()):
                if step.output_type == "Grid" and step.output_value is not None:
                    candidate_outputs.append((step.id, step.output_value))
                    print(f"🧠 Fallback: using {step.id} as implicit END candidate")
                    break

    results = []
    dataset = data[mode]
    procedures = normalize_procedures_with_levels(procedures, scenarioId, ruleId)

    for proc in procedures:
        for idx, example in enumerate(dataset):
            input_grid = example.get("input")
            expected_output = example.get("output")  # can be missing

            trainId = idx if mode == "train" else -1
            testId = -1 if mode == "train" else idx

            # skip if missing output in training mode (must compare)
            if expected_output is None and mode == "train":
                print(f"⚠️ Skipping trainId={trainId}: no output available.")
                continue

            proc_clone = clone_procedure(proc)

            print(f"\n🔍 Testing {'trainId' if trainId != -1 else 'testId'}={trainId if trainId != -1 else testId}")
            context = {
                "input_grid": input_grid,
                "trainId": trainId,
                "testId": testId,
            }

            candidate_outputs = []
            trace = []
            executed_steps = []

            for step in proc_clone.steps.values():
                resolved_args = {}
                skip = False
                for arg_name, binding in step.bindings.items():
                    resolved = resolve_binding_recursive(binding, context, input_grid, step)
                    if resolved is None:
                        print(f"Unresolved '{arg_name}' → skipping {step.id}")
                        skip = True
                        break
                    resolved_args[arg_name] = resolved

                if skip:
                    continue

                print(f"⚙️  Evaluating {step.action.name} with args: {resolved_args}")
                output = step.action.function(**resolved_args)
                step.output_value = output
                context[step.id] = output
                executed_steps.append(step.id)

                if return_execution_trace:
                    trace.append({
                        "step_id": step.id,
                        "action": step.action.id,
                        "args": resolved_args,
                        "output": output,
                    })

                if step.END:
                    candidate_outputs.append((step.id, output))
                    if expected_output is not None and not concrete_grids_equal(output, expected_output):
                        print(f"🧑‍☠️ {step.id} marked inactive due to wrong output")
                        step.active = False

            selected_output = None
            selected_step = None

            if not candidate_outputs:
                for step in proc_clone.steps.values():
                    if step.output_type == "Grid" and step.output_value is not None:
                        if expected_output is not None and concrete_grids_equal(step.output_value, expected_output):
                            candidate_outputs.append((step.id, step.output_value))
                            print(f"🧠 Matching output in {step.id} even though END=False")

            if not candidate_outputs:
                fallback_if_no_end(proc_clone, candidate_outputs)

            if candidate_outputs:
                selected_step, selected_output = candidate_outputs[-1]

            if expected_output is None:
                print(f"📝 No expected output: storing raw result for testId={testId}")
                results.append({
                    "procedure_id": proc.id,
                    "trainId": trainId,
                    "testId": testId,
                    "evaluated_output": selected_output,
                    "success": None,
                    "reason": "No expected output",
                    "executed_steps": executed_steps if return_execution_trace else None,
                    "execution_trace": trace if return_execution_trace else None,
                })
                continue

            # Else: standard evaluation
            success = concrete_grids_equal(selected_output, expected_output)
            if success:
                print(f"✅ SUCCESS for procedure {proc.id} via step {selected_step}")
                learn_from_success(proc, selected_step)
            else:
                print(f"❌ FAIL for procedure {proc.id}")
                print(f"   🔴 Expected: {expected_output}")
                print(f"   🔸 Got     : {selected_output}")

            accuracy_info = pixel_accuracy(selected_output, expected_output)

            result = {
                "procedure_id": proc.id,
                "trainId": trainId,
                "testId": testId,
                "success": success,
                "evaluated_output": selected_output,
                "expected_output": expected_output,
                "matching_pixels": accuracy_info["matching"],
                "total_pixels": accuracy_info["total"],
                "pixel_accuracy": accuracy_info["accuracy"]
            }
            if return_execution_trace:
                result["execution_trace"] = trace
                result["executed_steps"] = executed_steps

            results.append(result)

    return results

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

            # 🔁 Inject train-specific values into get_start_input
            for step in cloned.steps.values():
                step.trainId = trainId
                if step.action and step.action.id == "get_start_input":
                    print(f"💉 Injecting input_grid into get_start_input for trainId={trainId}")
                    step.output_value = input_grid
                    if "grid" in step.bindings:
                        step.bindings["grid"].value = input_grid
                        step.bindings["grid"].binding = BindingStatus.INPUT_GRID

            evaluated_output = evaluate_procedure_on_input(cloned, input_grid, trainId, -1)

            success = concrete_grids_equal(evaluated_output, expected_output)
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

def remove_value_from_generic(proc):
    for step in proc.steps.values():
        print(f"🧹 Cleaning step: {step.id}")
        for arg_name, binding in step.bindings.items():
            print(f"  🔍 {arg_name}: binding={binding.binding}, value={binding.value}, source={binding.source_procedure_id}")
            if binding.binding in [BindingStatus.VARIABLE, BindingStatus.INPUT_GRID]:
                print(f"  ✨ Clearing value, source, and candidates")
                binding.value = None
            clear_sub_bindings(binding)
            print(f"  ✅ Cleaned: binding={binding.binding}, value={binding.value}, source={binding.source_procedure_id}")

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

def evaluate_step_with_multiple(step, input_grid, context):
    # auto-fill CONTEXT bindings before resolution
    for arg_name, binding in step.bindings.items():
        if binding.binding == BindingStatus.CONTEXT:
            if arg_name in context and binding.value is None:
                binding.value = context[arg_name]
                print(f"🧬 Injected CONTEXT binding: {arg_name} = {binding.value}")

    args = {}
    for arg_name, binding in step.bindings.items():
        resolved_value = resolve_binding_recursive(binding, context, input_grid, step)
        args[arg_name] = resolved_value
        if resolved_value is None:
            print(f"Unresolved '{arg_name}' skip this action: {step.id}")
            return None
        print(f"Resolved '{arg_name}' to value: {resolved_value}")

    print(f"Evaluating {step.action.name} with args: {args}")
    try:
        result = step.action.function(**args)
        step.output_value = result
        context[step.id] = result
        print(f"Execution succeeded and stored in context: {step.id} produced {result}")
        return result
    except Exception as e:
        print(f"[ERROR] Step {step.id} threw {type(e).__name__}: {e}")
        step.active = False
        return None

def evaluate_procedure_on_input(proc: Procedure, input_grid: Grid, trainId, testId) -> Grid:
    context = {}
    print(f"[DEBUG] proc.steps: {proc.steps}")  # Add this debug print
    last_result = None
    for step in proc.steps.values():
        step.trainId = trainId
        step.testId = testId
        context["trainId"] = trainId
        context["testId"] = testId
        print(f"[DEBUG] Current step: {step}, type: {type(step)}")
        last_result = evaluate_step_with_multiple(step, input_grid, context)
    return last_result

def load_arc_json(json_path: str) -> dict:
    """
    Load an ARC JSON file and return the corresponding dictionary.
    """
    with open(json_path, "r") as f:
        return json.load(f)


def clone_procedure(original_proc: Procedure) -> Procedure:
    #print(f"[DEBUG] original_proc.steps: {original_proc.steps}")

    cloned_steps = {}
    for step in original_proc.steps.values():
        cloned_step = copy.deepcopy(step)
        # Reset all train-dependent values
        cloned_step.trainId = None
        cloned_step.testId = None
        cloned_step.isTrain = False
        cloned_step.output_value = None
        for binding in cloned_step.bindings.values():
            if binding.binding in (BindingStatus.CONSTANT, BindingStatus.INPUT_GRID, BindingStatus.VARIABLE):
                continue  # keep constants and linked inputs
            binding.value = None
        cloned_steps[cloned_step.id] = cloned_step

    return Procedure(steps=cloned_steps, id=f"{original_proc.id}_clone", scenarioId=original_proc.scenarioId, ruleId=original_proc.ruleId)


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
            success = concrete_grids_equal(evaluated_output, expected_output)
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

def generate_submission_file_from_scenarios(
    task_id: str,
    valid_scenarios: List[Scenario],
    arc_data: dict,
    output_path: str,
    results_by_scenario: Optional[dict] = None
) -> None:
    """
    Generate a submission.json file using predictions from valid_scenarios.
    Picks best result (highest pixel accuracy) for each test input.
    """
    submission = {task_id: []}
    num_tests = len(arc_data.get("test", []))

    if results_by_scenario is not None:
        # Collect best predictions per testId
        best_outputs_by_testId = {}

        for scenario in valid_scenarios:
            scenario_id = scenario.id
            results = results_by_scenario.get(scenario_id, [])

            for r in results:
                tid = r.get("testId", -1)
                if tid < 0:
                    continue
                acc = r.get("pixel_accuracy", 0.0)
                current_best = best_outputs_by_testId.get(tid)

                if current_best is None or acc > current_best["pixel_accuracy"]:
                    best_outputs_by_testId[tid] = {
                        "evaluated_output": r.get("evaluated_output"),
                        "pixel_accuracy": acc,
                        "procedure_id": r.get("procedure_id"),
                    }

        for tid in range(num_tests):
            best = best_outputs_by_testId.get(tid)
            if best is None:
                print(f"⚠️ No result for testId={tid}, fallback to [[0],[0],[0]]")
                best_output = [[0], [0], [0]]
            else:
                best_output = best["evaluated_output"]
                print(f"✅ testId={tid} uses proc={best['procedure_id']} with accuracy={best['pixel_accuracy']:.2f}")

            # Convert tuple to list if needed
            if isinstance(best_output, tuple):
                best_output = [list(row) for row in best_output]
            elif not isinstance(best_output, list) or not all(isinstance(row, list) for row in best_output):
                print(f"⚠️ Invalid output format for testId={tid}, fallback to default.")
                best_output = [[0], [0], [0]]

            submission[task_id].append({
                "attempt_1": best_output,
                "attempt_2": best_output
            })
    else:
        test_data = arc_data.get("test", [])
        if isinstance(test_data, dict):
            test_data = list(test_data.values())

        for test_entry in test_data:
            expected_output = test_entry.get("output", [[0]])
            best_output = [[0] for _ in expected_output] if isinstance(expected_output, list) else [[0], [0], [0]]
            submission[task_id].append({
                "attempt_1": best_output,
                "attempt_2": best_output
            })

    with open(output_path, "w") as f:
        json.dump(submission, f)
    print(f"📤 Submission file written to {output_path}")


def generate_submission_file(task_id: str, generic_procs: List[Procedure], arc_data: dict, output_path: str, test_results: Optional[List[dict]] = None) -> None:
    """
    Generate a submission.json file conforming to the ARC format, using predictions
    produced by the generic symbolic procedures.
    If `test_results` is provided, reuse those predictions instead of re-evaluating.
    """
    submission = {task_id: []}

    if test_results is not None:
        # Use provided test results directly
        for result in test_results:
            best_output = result.get("evaluated_output")

            # Convert tuple to list if needed
            if isinstance(best_output, tuple):
                best_output = [list(row) for row in best_output]

            if not isinstance(best_output, list) or not all(isinstance(row, list) for row in best_output):
                print(f"⚠️ Invalid output format in test_results: {best_output}. Using fallback.")
                best_output = [[0], [0], [0]]

            submission[task_id].append({
                "attempt_1": best_output,
                "attempt_2": best_output
            })
    else:
        test_data = arc_data["test"]

        # Handle both list-style and dict-style test sets
        if isinstance(test_data, list):
            test_iter = enumerate(test_data)
        elif isinstance(test_data, dict):
            test_iter = ((int(k), v) for k, v in test_data.items())
        else:
            raise ValueError("Unsupported test format: must be list or dict")

        for testId, test_entry in test_iter:
            expected_output = test_entry["output"]

            # Fallback if no test_results and no evaluation is wanted
            best_output = [[0] for _ in expected_output] if isinstance(expected_output, list) else [[0], [0], [0]]

            submission[task_id].append({
                "attempt_1": best_output,
                "attempt_2": best_output
            })

    with open(output_path, "w") as f:
        json.dump(submission, f)
    print(f"📤 Submission file written to {output_path}")

def print_test_results_by_scenario(results_by_scenario: dict, output_path: str, arc_data: Optional[dict] = None) -> None:
    def compute_pixel_accuracy(pred, expected):
        if not pred or not expected or len(pred) != len(expected) or len(pred[0]) != len(expected[0]):
            return 0, 0, 0.0
        matching = sum(
            1 for i in range(len(pred))
            for j in range(len(pred[0]))
            if pred[i][j] == expected[i][j]
        )
        total = len(pred) * len(pred[0])
        return matching, total, matching / total if total > 0 else 0.0

    with open(output_path, "a") as f:
        print("\n✅ TEST RESULTS BY SCENARIO:\n")
        f.write("\n✅ TEST RESULTS BY SCENARIO:\n")

        for scenario_id, results in results_by_scenario.items():
            print(f"\n📦 Scenario: {scenario_id}")
            f.write(f"\n📦 Scenario: {scenario_id}\n")

            for r in results:
                if r.get("testId", -1) == -1:
                    continue  # skip non-test entries
                pred = r.get("evaluated_output")
                if pred is None:
                    print(f"⚠️ No evaluated_output for testId={r['testId']}, skipping.")
                    continue

                # Recompute accuracy if missing
                expected = None
                if arc_data is not None:
                    test_set = arc_data.get("test", [])
                    if isinstance(test_set, dict):
                        expected = test_set.get(str(r["testId"]), {}).get("output")
                    elif isinstance(test_set, list) and r["testId"] < len(test_set):
                        expected = test_set[r["testId"]].get("output")

                if expected is not None:
                    matching, total, acc = compute_pixel_accuracy(pred, expected)
                    status = "✅" if matching == total else "❌"
                    acc_str = f"{acc * 100:.2f}%"
                    line = f"{status} testId={r['testId']}, proc={r['procedure_id']}, accuracy={acc_str} ({matching}/{total})"
                else:
                    line = f"⚠️ testId={r['testId']}, proc={r['procedure_id']}, no expected output"

                print(line)
                f.write(line + "\n")

def print_test_results(test_results: List[dict], output_path: str) -> None:
    with open(output_path, "a") as f:
        print("\n✅ TEST RESULTS:\n")
        f.write("\n✅ TEST RESULTS:\n")
        for r in test_results:
            status = "✅" if r["success"] else "❌"
            acc = f"{r['pixel_accuracy'] * 100:.2f}%"
            line = f"{status} testId={r['testId']}, proc={r['procedure_id']}, accuracy={acc} ({r['matching_pixels']}/{r['total_pixels']})"
            print(line)
            f.write(line + "\n")

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


def resolve_binding_recursive(binding, context, input_grid, step):
    """
    Recursively resolve an ArgumentBinding into its concrete value.
    """
    #print(f"resolve_binding_recursive: binding={binding}")
    #print(f"resolve_binding_recursive: context={context}")
    #print(f"resolve_binding_recursive: input_grid={input_grid}")

    print(f"🧠 Resolving binding: name={binding.name}, status={binding.binding}, value={binding.value}, source={binding.source_procedure_id}")

    if binding.binding == BindingStatus.CONSTANT:
        print(f"  📌 Constant binding resolved to: {binding.value}")
        return binding.value

    elif binding.binding == BindingStatus.INSTANCE:
        if binding.name.startswith("binding_"):
            attr = binding.name.split("_", 1)[1]
            value = getattr(binding, attr, None)
            #print(step)
            print(f"  📌 special instance binding from binding.{attr} → {value}")
            return value
        else:
            value = getattr(step, binding.name, None)
            print(f"  📌 instance binding resolved to: {value}")
            return value

    elif binding.binding == BindingStatus.INPUT_GRID:
        if "input_grid" in context:
            print(f"  🌐 Input grid binding resolved from context['input_grid']")
            return context["input_grid"]
        else:
            print(f"  🌐 Input grid binding fallback to input_grid argument")
            return input_grid

    elif binding.binding == BindingStatus.CONTEXT:
        context_val = context.get(binding.name)
        print(f"  🗃️ Context binding resolved to: {context_val}")
        return context_val

    elif binding.binding == BindingStatus.VARIABLE:
        if binding.source_procedure_id in context:
            context_val = context[binding.source_procedure_id]
            print(f"  🔁 Variable binding resolved from context[{binding.source_procedure_id}]: {context_val}")
            return context_val
        print(f"  🚫 Variable binding unresolved: source_procedure_id {binding.source_procedure_id} not found in context")
        return None

    elif binding.binding == BindingStatus.MULTIPLE:
        for candidate in binding.candidates or []:
            resolved_id = candidate.producer_id
            if "get_start_input" in resolved_id:
                print(f"✩ {resolved_id} return the input grid !")
                return input_grid
            if resolved_id == binding.source_procedure_id:
                print(f"⛔ Skipping self-link for {resolved_id} on MULTIPLE")
                continue
            if resolved_id in context:
                print(f"✩ MULTIPLE binding: using candidate {resolved_id} for {binding.name}")
                return context[resolved_id]
        print(f"⚠️ MULTIPLE with no resolved candidate found in context: {binding.candidates}")
        print(f"   🔎 Available context keys: {list(context.keys())}")
        return None

    elif binding.binding == BindingStatus.COMPOUND:
        if isinstance(binding.sub_bindings, dict):
            print(f"  🔄 Resolving compound dict for {binding.name}")
            return {
                key: resolve_binding_recursive(sub_binding, context, input_grid, step)
                for key, sub_binding in binding.sub_bindings.items()
            }
        elif isinstance(binding.sub_bindings, list):
            print(f"  🔄 Resolving compound list for {binding.name} with {len(binding.sub_bindings)} elements")
            return [
                resolve_binding_recursive(sub_binding, context, input_grid, step)
                for sub_binding in binding.sub_bindings
            ]
        else:
            raise ValueError("Unexpected sub_bindings type encountered.")

    else:
        print(f"  🔚 Unhandled binding type {binding.binding} Returning value: {binding.value}")
        return binding.value



def has_unresolved_binding(instance) -> bool:
    for _, binding in _iter_all_bindings(instance.bindings):
        if binding.binding == BindingStatus.UNRESOLVED:
            return True
    return False