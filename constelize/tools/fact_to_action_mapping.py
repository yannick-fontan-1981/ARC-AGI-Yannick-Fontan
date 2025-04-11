import json
import sqlite3
from typing import Callable, List
from constelize.core.procedure import ActionInstance
from constelize.dsl.dsl import safe_to_grid
from constelize.dsl.grid_dsl import to_concrete_grid, rot180, hmirror, vmirror, grid_to_pretty_string, grids_equal
from constelize.core.binding import ArgumentBinding, BindingStatus

from constelize.core.registry import ActionRegistry

registry = ActionRegistry()
registry.register_all_actions()

_unique_id = 0;

def getUniqueId():
    global _unique_id
    _unique_id += 1
    return str(_unique_id)

END_OUTPUTS_BY_TRAINID = {}

def load_end_outputs_from_json(json_path: str):
    global END_OUTPUTS_BY_TRAINID
    with open(json_path, "r") as f:
        data = json.load(f)
    END_OUTPUTS_BY_TRAINID = {
        trainId: train["output"]
        for trainId, train in enumerate(data["train"])
    }

class FactToActionMapping:
    def __init__(self, fact_name: str, test_function: Callable[[sqlite3.Connection], List[dict]], build_function: Callable[[dict], ActionInstance]):
        self.fact_name = fact_name
        self.test_function = test_function  # SQL-based, returns a resultSet (list of dicts)
        self.build_function = build_function  # takes a result row and returns an ActionInstance

def build_start_input(id: int, grid, isTrain: bool, output_var: str = "input_grid") -> ActionInstance:
    return ActionInstance(
        id=f"start_input_{'train' if isTrain else 'test'}_{id}#{getUniqueId()}",
        action=registry.get_by_id("get_start_input"),
        bindings={},
        output_var=output_var,
        output_value=grid,
        trainId=(id if isTrain else -1),
        testId=(id if isTrain == False else -1),
        isTrain=isTrain,
        isFromInput=True,
        isToOutput=False
    )

def test_rotated_180(conn: sqlite3.Connection) -> List[dict]:
    query = """
    SELECT sprite_transformation.sprite_unique_id, 
           sprite_occurrence.isInsideInput, 
           sprite_occurrence.isInsideOutput, 
           sprite_occurrence.trainId,
           sprite_occurrence.testId, 
           sprite_unique.data 
    FROM sprite_transformation
    INNER JOIN sprite_unique ON sprite_unique.id = sprite_transformation.sprite_unique_id
    INNER JOIN sprite_occurrence ON sprite_transformation.id = sprite_occurrence.sprite_transformation_id
    WHERE rotated_180 = 1
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def build_rotated_180(row: dict) -> ActionInstance:
    action = registry.get_by_id("rotate_180")
    raw_data = json.loads(row["data"])
    input_grid = to_concrete_grid(raw_data)
    output_grid = rot180(input_grid)
    trainId = row["trainId"]

    return ActionInstance(
        id="rot180_instance_" + str(row["sprite_unique_id"]) + "#" + getUniqueId(),
        action=action,
        bindings={
            "grid": ArgumentBinding(
                name="grid",
                type="Grid",
                binding=BindingStatus.UNRESOLVED,
                value=input_grid
            )
        },
        output_var="rotated_grid",
        output_value=output_grid,
        output_type=action.output_type,
        trainId=trainId,
        testId=row["testId"],
        isTrain=trainId > -1,
        isToOutput=row["isInsideOutput"],
        END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
    )

def test_flipped_horizontal(conn: sqlite3.Connection) -> List[dict]:
    query = """
    SELECT sprite_transformation.sprite_unique_id,
           sprite_occurrence.isInsideInput,
           sprite_occurrence.isInsideOutput,
           sprite_occurrence.trainId,
           sprite_occurrence.testId, 
           sprite_unique.data
    FROM sprite_transformation
    INNER JOIN sprite_unique ON sprite_unique.id = sprite_transformation.sprite_unique_id
    INNER JOIN sprite_occurrence ON sprite_transformation.id = sprite_occurrence.sprite_transformation_id
    WHERE flipped_horiz = 1
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def build_flipped_horizontal(row: dict) -> ActionInstance:
    action = registry.get_by_id("hmirror")
    raw_data = json.loads(row["data"])
    input_grid = to_concrete_grid(raw_data)
    output_grid = hmirror(input_grid)
    trainId = row["trainId"]

    return ActionInstance(
        id="hmirror_instance_" + str(row["sprite_unique_id"]) + "#" + getUniqueId(),
        action=action,
        bindings={
            "grid": ArgumentBinding(
                name="grid",
                type="Grid",
                binding=BindingStatus.UNRESOLVED,
                value=input_grid
            )
        },
        output_var="mirrored_grid",
        output_value=output_grid,
        output_type=action.output_type,
        trainId=row["trainId"],
        testId=row["testId"],
        isTrain=trainId > -1,
        isToOutput=row["isInsideOutput"],
        END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
    )


def test_flipped_vertical(conn: sqlite3.Connection) -> List[dict]:
    query = """
    SELECT sprite_transformation.sprite_unique_id,
           sprite_occurrence.isInsideInput,
           sprite_occurrence.isInsideOutput,
           sprite_occurrence.trainId,
           sprite_occurrence.testId, 
           sprite_unique.data
    FROM sprite_transformation
    INNER JOIN sprite_unique ON sprite_unique.id = sprite_transformation.sprite_unique_id
    INNER JOIN sprite_occurrence ON sprite_transformation.id = sprite_occurrence.sprite_transformation_id
    WHERE flipped_vert = 1
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def build_flipped_vertical(row: dict) -> ActionInstance:
    action = registry.get_by_id("vmirror")
    raw_data = json.loads(row["data"])
    input_grid = to_concrete_grid(raw_data)
    output_grid = vmirror(input_grid)
    trainId = row["trainId"]

    return ActionInstance(
        id="vmirror_instance_" + str(row["sprite_unique_id"]) + "#" + getUniqueId(),
        action=action,
        bindings={
            "grid": ArgumentBinding(
                name="grid",
                type="Grid",
                binding=BindingStatus.UNRESOLVED,
                value=input_grid
            )
        },
        output_var="mirrored_grid",
        output_value=output_grid,
        output_type=action.output_type,
        trainId=row["trainId"],
        testId=row["testId"],
        isTrain=trainId > -1,
        isToOutput=row["isInsideOutput"],
        END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
    )


FACT_TO_ACTION_MAPPING = [
    FactToActionMapping("rotated_180", test_rotated_180, build_rotated_180),
    FactToActionMapping("flipped_horizontal", test_flipped_horizontal, build_flipped_horizontal),
    FactToActionMapping("flipped_vertical", test_flipped_vertical, build_flipped_vertical),
]
