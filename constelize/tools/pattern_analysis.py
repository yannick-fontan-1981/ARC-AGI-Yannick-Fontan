import json
import sqlite3

from constelize.dsl.grid_dsl import grid_to_pretty_string
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


def generate_draft_procedure(db_path: str, json_path: str, name: str = "generated_procedure") -> Procedure:
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

    for instance in action_instances:
        print(f"🧱 Action: {instance.action.id}")
        print(f"   ↳ id            : {instance.id}")
        print(f"   ↳ trainId       : {instance.trainId}")
        print(f"   ↳ isFromInput   : {instance.isFromInput}")
        print(f"   ↳ isToOutput    : {instance.isToOutput}")
        print(f"   ↳ output_var    : {instance.output_var}")
        print(f"   ↳ output_value  : {grid_to_pretty_string(instance.output_value)}")
        print(f"   ↳ bindings:")
        for name, binding in instance.bindings.items():
            print(f"       - {name}: {grid_to_pretty_string(binding.value)}")
        print(f"   ↳ END           : {instance.END}")
        print()


    #print(f"   ↳ json_data  : {json_data}")
    #print(f"   ↳ json_data.get('train', [])  : {json_data.get("train", [])}")
    #print(f"   ↳ json_data.get('test', [])  : {json_data.get("test", [])}")

    procedure = build_procedure_from_action_instances(action_instances, name=name)
    register_procedure(procedure)
    return procedure


def extract_rules_from_procedure(procedure: Procedure) -> str:
    rule_descriptions = []
    for step in procedure.steps:
        action_id = step.action_id
        args = {arg.name: arg.value for arg in step.input_bindings}
        rule_descriptions.append(f"{action_id}({args})")
    return "\n".join(rule_descriptions)


def evaluate_draft_procedure(procedure: Procedure, input_grid, expected_output_grid) -> bool:
    try:
        result = evaluate_procedure(procedure, input_grid)
        return result == expected_output_grid
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        return False
