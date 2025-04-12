import json
import sqlite3
from typing import Callable, List, Optional
from constelize.core.procedure import ActionInstance
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.registry import ActionRegistry
from constelize.dsl.grid_dsl import to_concrete_grid, grids_equal, unzoom
from constelize.library.spatial_transformation import zoom as zoom_function

registry = ActionRegistry()
registry.register_all_actions()

END_OUTPUTS_BY_TRAINID = {}
_unique_id = 0

def getUniqueId():
    global _unique_id
    _unique_id += 1
    return str(_unique_id)

def load_end_outputs_from_json(json_path: str):
    global END_OUTPUTS_BY_TRAINID
    with open(json_path, "r") as f:
        data = json.load(f)
    END_OUTPUTS_BY_TRAINID = {
        trainId: train["output"]
        for trainId, train in enumerate(data["train"])
    }

class FactToActionMapping:
    def __init__(
        self,
        fact_name: str,
        action_id: str,
        column_name: Optional[str] = None
    ):
        self.fact_name = fact_name
        self.column_name = column_name or fact_name
        self.action_id = action_id
        self.action = registry.get_by_id(action_id)
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = f"""
        SELECT sprite_transformation.sprite_unique_id,
               sprite_occurrence.isInsideInput,
               sprite_occurrence.isInsideOutput,
               sprite_occurrence.trainId,
               sprite_occurrence.testId,
               sprite_unique.data
        FROM sprite_transformation
        INNER JOIN sprite_unique ON sprite_unique.id = sprite_transformation.sprite_unique_id
        INNER JOIN sprite_occurrence ON sprite_transformation.id = sprite_occurrence.sprite_transformation_id
        WHERE {self.column_name} = 1
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        raw_data = json.loads(row["data"])
        input_grid = to_concrete_grid(raw_data)
        output_grid = self.action.function(input_grid)

        trainId = row["trainId"]
        return ActionInstance(
            id=f"{self.action_id}_instance_{row['sprite_unique_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=input_grid
                )
            },
            output_var=f"{self.action_id}_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            trainId=trainId,
            testId=row["testId"],
            isTrain=trainId > -1,
            isToOutput=row["isInsideOutput"],
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

class ZoomFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("zoom", "zoom")

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT st.sprite_unique_id,
               so.trainId,
               so.testId,
               so.isInsideOutput,
               su.data,
               st.zoom_x,
               st.zoom_y
        FROM sprite_transformation st
        JOIN sprite_occurrence so ON so.sprite_unique_id = st.sprite_unique_id
        JOIN sprite_unique su ON su.id = st.sprite_unique_id
        WHERE (zoom_x > 1 OR zoom_y > 1)
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        output_grid = to_concrete_grid(json.loads(row["data"]))
        zoom_x = int(row["zoom_x"])
        zoom_y = int(row["zoom_y"])
        input_grid = unzoom(output_grid, zoom_x, zoom_y)

        trainId = row["trainId"]
        return ActionInstance(
            id=f"zoom_instance_{row['sprite_unique_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=input_grid
                ),
                "zoom_x": ArgumentBinding(
                    name="zoom_x",
                    type="int",
                    binding=BindingStatus.CONSTANT,
                    value=zoom_x
                ),
                "zoom_y": ArgumentBinding(
                    name="zoom_y",
                    type="int",
                    binding=BindingStatus.CONSTANT,
                    value=zoom_y
                )
            },
            output_var="zoomed_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            trainId=trainId,
            testId=row["testId"],
            isTrain=trainId > -1,
            isToOutput=row["isInsideOutput"],
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

def build_start_input(id: int, grid, isTrain: bool, output_var: str = "input_grid") -> ActionInstance:
    return ActionInstance(
        id=f"start_input_{'train' if isTrain else 'test'}_{id}#{getUniqueId()}",
        action=registry.get_by_id("get_start_input"),
        bindings={},
        output_var=output_var,
        output_value=grid,
        trainId=id if isTrain else -1,
        testId=-1 if isTrain else id,
        isTrain=isTrain,
        isFromInput=True,
        isToOutput=False
    )

FACT_TO_ACTION_MAPPING: List[FactToActionMapping] = [
    FactToActionMapping("rotated_90", "rotate_90"),
    FactToActionMapping("rotated_180", "rotate_180"),
    FactToActionMapping("rotated_270", "rotate_270"),
    FactToActionMapping("flipped_horizontal", "mirror_vertical", "flipped_horiz"),
    FactToActionMapping("flipped_vertical", "mirror_horizontal", "flipped_vert"),
    FactToActionMapping("flipped_horiz_90", "flipped_horiz_90"),
    FactToActionMapping("flipped_vert_90", "flipped_vert_90"),
    ZoomFactToAction(),
]
