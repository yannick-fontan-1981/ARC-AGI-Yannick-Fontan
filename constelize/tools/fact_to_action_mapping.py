# constelize/tools/fact_to_action_mapping.py

import json
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
from collections import defaultdict
from itertools import product

from constelize.core.procedure import ActionInstance, Procedure
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.registry import ActionRegistry
from constelize.dsl.grid_dsl import to_concrete_grid, grids_equal, unzoom, recolor_sprite, grid_to_pretty_string, crop, \
    Grid, fill_grid
from constelize.library.pattern_detection import detect_noise, denoise_grid
from constelize.library.spatial_transformation import zoom as zoom_function, canvas_by_ratio_fn, repaint
from constelize.tools.registry_singleton import registry

# Global unique ID counter for ActionInstances.
_unique_id = 0
def getUniqueId() -> str:
    global _unique_id
    _unique_id += 1
    return str(_unique_id)

# Global dictionary for expected outputs (populated from JSON).
END_OUTPUTS_BY_TRAINID: Dict[int, any] = {}
def load_end_outputs_from_json(json_path: str):
    global END_OUTPUTS_BY_TRAINID
    with open(json_path, "r") as f:
        data = json.load(f)
    END_OUTPUTS_BY_TRAINID = {
        trainId: train["output"]
        for trainId, train in enumerate(data.get("train", []))
    }

# Global dictionaries for input grids.
TRAIN_INPUT_GRIDS: Dict[int, any] = {}
TRAIN_OUTPUT_GRIDS: Dict[int, any] = {}
TEST_INPUT_GRIDS: Dict[int, any] = {}
def load_json_inputs_from_json(json_path: str):
    global TRAIN_INPUT_GRIDS, TRAIN_OUTPUT_GRIDS, TEST_INPUT_GRIDS
    with open(json_path, "r") as f:
        data = json.load(f)
    for trainId, item in enumerate(data.get("train", [])):
        TRAIN_INPUT_GRIDS[trainId] = item["input"]
        TRAIN_OUTPUT_GRIDS[trainId] = item["output"]
    for testId, item in enumerate(data.get("test", [])):
        TEST_INPUT_GRIDS[testId] = item["input"]

# =============================================================================
# Base FactToActionMapping class.
# =============================================================================
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
        similar_actions = {
            "rotate_90", "rotate_180", "rotate_270",
            "mirror_vertical", "mirror_horizontal",
            "flipped_horiz_90", "flipped_vert_90"
        }
        self.avoid_similar_as_source = (
            list(similar_actions) if action_id in similar_actions else []
        )

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = f"""
        SELECT DISTINCT
            st.sprite_unique_id,
            st.sprite_produce_id,
            so.isInsideInput,
            so.isInsideOutput,
            so.trainId,
            so.testId,
            source.data AS source_data,
            produced.data AS produced_data,
            po.minX,
            po.minY
        FROM sprite_transformation AS st
        INNER JOIN sprite_occurrence AS so ON st.id = so.sprite_transformation_id
        INNER JOIN sprite_occurrence AS po ON po.id = st.sprite_produce_id
        INNER JOIN sprite_unique AS produced ON produced.id = st.sprite_produce_id
        INNER JOIN sprite_unique AS source ON source.id = st.sprite_unique_id
        WHERE st.{self.column_name} = 1
        AND COALESCE(st.zoom_x, 1) = 1
        AND COALESCE(st.zoom_y, 1) = 1
        AND (st.recolored IS NULL OR st.recolored = '[]')
        AND so.sprite_id IS NOT NULL
        AND st.sprite_unique_id != st.sprite_produce_id
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]

        #if self.column_name == "rotated_180":
        #    print("[ test rotated_180 ]")
        #    print([dict(zip(columns, row)) for row in cursor.fetchall()])

        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        source_raw_data = json.loads(row["source_data"])
        input_grid = to_concrete_grid(source_raw_data)

        produced_raw_data = json.loads(row["produced_data"])
        output_grid = to_concrete_grid(produced_raw_data)

        if self.column_name == "rotated_180":
           print("[ rotated_180 ]")
           print("input_grid")
           print(grid_to_pretty_string(input_grid))
           print("output_grid")
           print(grid_to_pretty_string(output_grid))

        trainId = row["trainId"]
        return ActionInstance(
            id=f"{self.action_id}_instance_{row['sprite_unique_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.VARIABLE,
                    value=input_grid
                )
            },
            output_var=f"{self.action_id}_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=row["testId"],
            isTrain=trainId != -1,
            isToOutput=row["isInsideOutput"],
            toRepaint=True,
            repaintMinX=row["minX"],
            repaintMinY=row["minY"],
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

# =============================================================================
# ZoomFactToAction: mapping for zoom.
# =============================================================================
class ZoomFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("zoom", "zoom")

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT st.sprite_unique_id,
               st.sprite_produce_id,
               so.trainId,
               so.testId,
               so.isInsideOutput,
               su.data,
               st.zoom_x,
               st.zoom_y, so.minX, so.minY
        FROM sprite_transformation st
        JOIN sprite_occurrence so ON  so.sprite_transformation_id = st.id
        JOIN sprite_unique su ON su.id = st.sprite_produce_id
        WHERE (zoom_x > 1 OR zoom_y > 1)
        AND COALESCE(st.rotated_90, 0) = 0
        AND COALESCE(st.rotated_180, 0) = 0
        AND COALESCE(st.rotated_270, 0) = 0
        AND COALESCE(st.flipped_vert, 0) = 0
        AND COALESCE(st.flipped_horiz, 0) = 0
        AND COALESCE(st.flipped_vert_90, 0) = 0
        AND COALESCE(st.flipped_horiz_90, 0) = 0
        AND (st.recolored IS NULL OR st.recolored = '[]')
        AND so.sprite_id IS NOT NULL
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        seen = set()
        unique_rows = []
        for r in rows:
            key = (r["trainId"], r["zoom_x"], r["zoom_y"])  # anything that defines the zoom
            if key not in seen:
                seen.add(key)
                unique_rows.append(r)
        return unique_rows

    def _build_function(self, row: dict) -> ActionInstance:
        output_grid = to_concrete_grid(json.loads(row["data"]))
        zoom_x = int(row["zoom_x"])
        zoom_y = int(row["zoom_y"])
        input_grid = unzoom(output_grid, zoom_x, zoom_y)
        trainId = row["trainId"]

        print("ZoomFactToAction _build_function ")
        print("grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))")
        print(grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId)))
        print("output_grid")
        print(output_grid)
        print("END_OUTPUTS_BY_TRAINID.get(trainId))")
        print(END_OUTPUTS_BY_TRAINID.get(trainId))

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
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=zoom_x
                ),
                "zoom_y": ArgumentBinding(
                    name="zoom_y",
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=zoom_y
                )
            },
            output_var="zoomed_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=row["testId"],
            isTrain=trainId != -1,
            isToOutput=row["isInsideOutput"],
            toRepaint=True,
            repaintMinX=row["minX"],
            repaintMinY=row["minY"],
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

# =============================================================================
# RepeatedSpriteFactToAction: mapping for repeated sprite.
# =============================================================================
class RepeatedSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("repeated_sprite", "repeated_sprite")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> list[dict]:
        query = """
        SELECT
            so.sprite_unique_id,
            so.sprite_transformation_id,
            so.trainId,
            so.testId,
            source.data AS data,
            po.minX,
            po.minY,
            -- build the inputCoords exactly as before
            COALESCE(
              '[' || GROUP_CONCAT(
                CASE WHEN so.isInsideInput  = 1
                     THEN '['||so.minX||','||so.minY||']'
                END, ','
              ) || ']',
              '[]'
            ) AS inputCoords,
            -- build the outputCoords exactly as before
            COALESCE(
              '[' || GROUP_CONCAT(
                CASE WHEN so.isInsideOutput = 1
                     THEN '['||so.minX||','||so.minY||']'
                END, ','
              ) || ']',
              '[]'
            ) AS outputCoords
        FROM sprite_occurrence AS so
        JOIN sprite_transformation AS st
          ON st.id = so.sprite_transformation_id
        JOIN sprite_unique AS source
          ON source.id = st.sprite_unique_id        
        INNER JOIN sprite_occurrence AS po ON po.id = st.sprite_produce_id
        WHERE so.sprite_id IS NOT NULL
        GROUP BY
            so.sprite_unique_id,
            so.sprite_transformation_id,
            so.trainId,
            so.testId,
            source.data
        HAVING
            -- count *distinct* output coords, not raw rows
            COUNT(
              DISTINCT CASE WHEN so.isInsideOutput = 1
                            THEN so.minX || ',' || so.minY
                       END
            ) > 1
        ORDER BY
            so.sprite_unique_id,
            so.trainId,
            so.testId;
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        from constelize.dsl.grid_dsl import to_concrete_grid, paint

        # Convert stored sprite JSON to a grid.
        sprite_grid = to_concrete_grid(json.loads(row["data"]))
        # Decode fact coordinates for both input and output positions.
        input_coords = json.loads(row["inputCoords"])
        output_coords = json.loads(row["outputCoords"])
        # Sort the coordinate lists by row, then column.
        input_coords.sort(key=lambda coord: (coord[1], coord[0]))
        output_coords.sort(key=lambda coord: (coord[1], coord[0]))
        action = self.action
        trainId = row["trainId"]
        testId = row["testId"]

        # Retrieve the output grid from stored facts.
        output_grid_raw = END_OUTPUTS_BY_TRAINID.get(trainId)
        if output_grid_raw is None:
            raise ValueError(f"Missing output grid for trainId={trainId}")
        # Create an anonymized canvas (a blank grid) based on the output grid dimensions.
        anonymized_canvas = tuple(tuple(-8 for _ in row) for row in output_grid_raw)

        # Paint the sprite at all provided output coordinates.
        painted_canvas = anonymized_canvas
        for (x, y) in output_coords:
            painted_canvas = paint(painted_canvas, sprite_grid, (y, x))

        # --- Build compound binding for output_positions ---
        output_positions_binding = ArgumentBinding(
            name="output_positions",
            type="Array<Coord>",
            binding=BindingStatus.COMPOUND,
            sub_bindings=[],  # We will fill this list below.
            sub_bindings_length_status=BindingStatus.UNRESOLVED,
            sub_bindings_length_value=len(output_coords)
            #TODO value=output_coords ?
        )
        for idx, coord in enumerate(output_coords):
            x_val = int(coord[0])
            y_val = int(coord[1])
            sub_binding = ArgumentBinding(
                name=f"coord_{idx}",
                type="Coord",
                binding=BindingStatus.COMPOUND,
                sub_bindings={
                    "x": ArgumentBinding(name="x", type="Integer", binding=BindingStatus.UNRESOLVED, value=x_val),
                    "y": ArgumentBinding(name="y", type="Integer", binding=BindingStatus.UNRESOLVED, value=y_val)
                },
                # The coordinate itself is always composed of two parts.
                sub_bindings_length_status=BindingStatus.CONSTANT,
                sub_bindings_length_value=2
            )
            output_positions_binding.sub_bindings.append(sub_binding)

        # --- Build compound binding for input_positions with the same logic ---
        input_positions_binding = ArgumentBinding(
            name="input_positions",
            type="Array<Coord>",
            binding=BindingStatus.COMPOUND,
            sub_bindings=[],  # To be populated below.
            sub_bindings_length_status=BindingStatus.UNRESOLVED,
            sub_bindings_length_value=len(input_coords)
            # TODO value=output_coords ?
        )
        for idx, coord in enumerate(input_coords):
            x_val = int(coord[0])
            y_val = int(coord[1])
            sub_binding = ArgumentBinding(
                name=f"coord_{idx}",
                type="Coord",
                binding=BindingStatus.COMPOUND,
                sub_bindings={
                    "x": ArgumentBinding(name="x", type="Integer", binding=BindingStatus.UNRESOLVED, value=x_val),
                    "y": ArgumentBinding(name="y", type="Integer", binding=BindingStatus.UNRESOLVED, value=y_val)
                },
                sub_bindings_length_status=BindingStatus.CONSTANT,
                sub_bindings_length_value=2
            )
            input_positions_binding.sub_bindings.append(sub_binding)

        # --- Build and return the ActionInstance ---
        return ActionInstance(
            id=f"repeated_sprite_{row['sprite_unique_id']}#{getUniqueId()}",
            action=action,
            bindings={
                "output_canvas": ArgumentBinding(
                    name="output_canvas",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=anonymized_canvas
                ),
                "sprite": ArgumentBinding(
                    name="sprite",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=sprite_grid
                ),
                # Use the newly constructed compound bindings for input and output positions.
                "input_positions": input_positions_binding,
                "output_positions": output_positions_binding
            },
            output_var="repeated_grid",
            output_value=painted_canvas,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=testId,
            isTrain=(trainId != -1),
            isToOutput=True,
            toRepaint=True,
            repaintMinX=row["minX"],
            repaintMinY=row["minY"],
            END=False
        )

# =============================================================================
# CanvasByRatioFactToAction: mapping for canvas by ratio.
# =============================================================================
class CanvasByRatioFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("canvas_by_ratio", "canvas_by_ratio")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT
          input.trainId,
          input.width  AS input_width,
          input.height AS input_height,
          output.width AS output_width,
          output.height AS output_height,
          (output.width  * 1.0 / input.width ) AS ratio_width,
          (output.height * 1.0 / input.height) AS ratio_height
        FROM sprite_analysis AS input
        JOIN sprite_analysis AS output
          ON input.trainId = output.trainId
        WHERE
          input.isInsideInput  = 1
          AND input.isGrid      = 1
          AND output.isInsideOutput = 1
          AND output.isGrid     = 1
          -- exclude the trivial 1×1 case:
          AND NOT (output.width = input.width AND output.height = input.height)
        """
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        all_rows = [dict(zip(columns, row)) for row in rows]
        if not all_rows:
            return []
        first = all_rows[0]
        rw = first["ratio_width"]
        rh = first["ratio_height"]
        # Ensure all ratios are identical and integer-valued.
        for row in all_rows:
            if row["ratio_width"] != rw or row["ratio_height"] != rh:
                return []
            if not rw.is_integer() or not rh.is_integer():
                return []
        return all_rows

    def _build_function(self, row: dict) -> ActionInstance:
        from constelize.library.spatial_transformation import canvas_by_ratio_fn
        ratio_w = int(row["ratio_width"])
        ratio_h = int(row["ratio_height"])
        action = self.action
        # Retrieve the trainId; a valid training fact has trainId != -1.
        trainId = row.get("trainId", -1)
        if trainId != -1:
            print("TRAIN_INPUT_GRIDS")
            print(TRAIN_INPUT_GRIDS)
            if trainId in TRAIN_INPUT_GRIDS:
                input_grid = TRAIN_INPUT_GRIDS[trainId]
                print(f"[CanvasByRatio] Using TRAIN_INPUT_GRIDS for trainId {trainId}: {input_grid}")
            else:
                raise ValueError(f"No input grid found in TRAIN_INPUT_GRIDS for trainId {trainId}")
        else:
            print("TEST_INPUT_GRIDS")
            print(TEST_INPUT_GRIDS)
            testId = row.get("testId", -1)
            if testId in TEST_INPUT_GRIDS:
                input_grid = TEST_INPUT_GRIDS[testId]
                print(f"[CanvasByRatio] Using TEST_INPUT_GRIDS for testId {testId}: {input_grid}")
            else:
                raise ValueError(f"No input grid found in TEST_INPUT_GRIDS for testId {testId}")
        output_grid = canvas_by_ratio_fn(input_grid, ratio_w, ratio_h)
        print(f"[CanvasByRatio] For id {trainId if trainId != -1 else row.get('testId', -1)}, using ratio=({ratio_w}, {ratio_h}), computed canvas: {output_grid}")
        return ActionInstance(
            id=f"canvas_by_ratio#{getUniqueId()}",
            action=action,
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.INPUT_GRID,
                    value=None
                ),
                "ratio_width": ArgumentBinding(
                    name="ratio_width",
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=ratio_w
                ),
                "ratio_height": ArgumentBinding(
                    name="ratio_height",
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=ratio_h
                )
            },
            output_var="canvas_grid",
            output_value=output_grid,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=row.get("testId", -1),
            isTrain=(trainId != -1),
            isToOutput=True,
            END=False
        )

# =============================================================================
# build_start_input: Now modified to use BindingStatus.INPUT_GRID
# =============================================================================
def build_start_input(id: int, grid, isTrain: bool, scenarioId: str = "scenario_1", ruleId: str = "rule_1") -> ActionInstance:
    print("[ build_start_input ] registry.get_by_id(get_start_input)")
    action = registry.get_by_id("get_start_input")
    print(action)
    return ActionInstance(
        id=f"start_input_{'train' if isTrain else 'test'}_{id}#{getUniqueId()}",
        action=action,
        bindings={
            "grid": ArgumentBinding(
                name="grid",
                type="Grid",
                binding=BindingStatus.INPUT_GRID,
                value=None
            )
        },
        output_var="input_grid",
        output_value=grid,
        scenarioId=scenarioId,
        ruleId=ruleId,
        trainId=id if isTrain else -1,
        testId=-1 if isTrain else id,
        isTrain=isTrain,
        isFromInput=True,
        isToOutput=False
    )


def build_get_attribute_instance(
    scenarioId: str,
    ruleId: str,
    binding_type: str,
    trainId: int,
    testId:  int,
    attribute_name: str,
    output_value: int
) -> ActionInstance:
    """
    Build an ActionInstance for the `get_attribute` action,
    with all three bindings set as CONSTANT.
    """
    # Grab the action from the registry (we assume it’s already registered)
    action   = registry.get_by_id("get_attribute")

    print(f"build_get_attribute_instance binding_type: {binding_type}")

    return ActionInstance(
        id=f"get_attribute_{scenarioId}_{ruleId}_{trainId}_{testId}_{attribute_name}",
        action=action,
        bindings={
            "scenarioId":     ArgumentBinding("scenarioId",     "String",     binding=BindingStatus.INSTANCE, value=scenarioId),
            "ruleId":         ArgumentBinding("ruleId",         "String",     binding=BindingStatus.INSTANCE, value=ruleId),
            "binding_type":   ArgumentBinding("binding_type",   binding_type, binding=BindingStatus.INSTANCE, value=binding_type),
            "trainId":        ArgumentBinding("trainId",        "Integer",    binding=BindingStatus.CONTEXT,  value=trainId),
            "testId":         ArgumentBinding("testId",         "Integer",    binding=BindingStatus.CONTEXT,  value=testId),
            "attribute_name": ArgumentBinding("attribute_name", "String",     binding=BindingStatus.CONSTANT, value=attribute_name),
        },
        output_var=f"attr_{attribute_name}",
        output_value=output_value,
        scenarioId=scenarioId,
        ruleId=ruleId,
        trainId=trainId,
        testId=testId,
        isTrain=(trainId != -1),
        isToOutput=True
    )

def build_select_sprite_and_attribute_instance(
    trainId: int,
    testId: int,
    binding_type: str,
    output_value: Any,
    criteria: List[Tuple[str, Any]],
    attribute_name: str,
    scenarioId: str,
    ruleId: str
) -> ActionInstance:
    """
    Build an ActionInstance for the `select_sprite_and_attribute` action,
    customized per train/test example. Output value is provided.
    """
    action = registry.get_by_id("select_sprite_and_attribute")

    instance_id = (
        f"select_sprite_and_attribute_{scenarioId}_{ruleId}_{attribute_name}"
        f"_train{trainId}_test{testId}"
    )

    return ActionInstance(
        id=instance_id,
        action=action,
        bindings={
            "scenarioId":     ArgumentBinding("scenarioId",     "String",                      binding=BindingStatus.INSTANCE, value=scenarioId),
            "ruleId":         ArgumentBinding("ruleId",         "String",                      binding=BindingStatus.INSTANCE, value=ruleId),
            "trainId":        ArgumentBinding("trainId",        "Integer",                     binding=BindingStatus.CONTEXT,  value=trainId),
            "testId":         ArgumentBinding("testId",         "Integer",                     binding=BindingStatus.CONTEXT,  value=testId),
            "criteria":       ArgumentBinding("criteria",       "List[Tuple[String,Integer]]", binding=BindingStatus.CONSTANT, value=criteria),
            "attribute_name": ArgumentBinding("attribute_name", "String",                      binding=BindingStatus.CONSTANT, value=attribute_name)
        },
        output_var=f"select_{attribute_name}", # _train{trainId}_test{testId}
        output_type=binding_type,
        output_value=output_value,
        trainId=trainId,
        testId=testId,
        isTrain=(testId == -1),
        isToOutput=False,
        scenarioId=scenarioId,
        ruleId=ruleId
    )

def build_select_object_and_attribute_instance(
    trainId: int,
    testId: int,
    binding_type: str,
    output_value: Any,
    criteria: List[Tuple[str, Any]],
    attribute_name: str,
    object_ids: List[int],
    scenarioId: str,
    ruleId: str
) -> ActionInstance:
    """
    Build an ActionInstance for the `select_object_and_attribute` action,
    customized per train/test example. Output value is provided.
    """
    action = registry.get_by_id("select_object_and_attribute")

    instance_id = (
        f"select_object_and_attribute_{scenarioId}_{ruleId}_{attribute_name}"
        f"_train{trainId}_test{testId}"
    )

    return ActionInstance(
        id=instance_id,
        action=action,
        bindings={
            "scenarioId":     ArgumentBinding("scenarioId",     "String",                      binding=BindingStatus.INSTANCE, value=scenarioId),
            "ruleId":         ArgumentBinding("ruleId",         "String",                      binding=BindingStatus.INSTANCE, value=ruleId),
            "trainId":        ArgumentBinding("trainId",        "Integer",                     binding=BindingStatus.CONTEXT,  value=trainId),
            "testId":         ArgumentBinding("testId",         "Integer",                     binding=BindingStatus.CONTEXT,  value=testId),
            "criteria":       ArgumentBinding("criteria",       "List[Tuple[String,Integer]]", binding=BindingStatus.CONSTANT, value=criteria),
            "attribute_name": ArgumentBinding("attribute_name", "String",                      binding=BindingStatus.CONSTANT, value=attribute_name),
            "object_ids":     ArgumentBinding("object_ids",     "List[Integer]",               binding=BindingStatus.CONSTANT, value=object_ids),
        },
        output_var=f"select_{attribute_name}",
        output_type=binding_type,
        output_value=output_value,
        trainId=trainId,
        testId=testId,
        isTrain=(testId == -1),
        isToOutput=False,
        scenarioId=scenarioId,
        ruleId=ruleId
    )

def build_select_sprite_grid_instance(
    trainId:    int,
    testId:     int,
    criteria:   List[Tuple[str, Any]],
    output_grid: Any,
    scenarioId: str,
    ruleId:     str
) -> ActionInstance:
    action   = registry.get_by_id("select_sprite_grid")
    inst_id  = f"select_sprite_grid_{scenarioId}_{ruleId}_train{trainId}_test{testId}"
    return ActionInstance(
      id=inst_id,
      action=action,
      bindings={
        "scenarioId": ArgumentBinding("scenarioId", "String",                      binding=BindingStatus.INSTANCE,  value=scenarioId),
        "ruleId":     ArgumentBinding("ruleId",     "String",                      binding=BindingStatus.INSTANCE,  value=ruleId),
        "trainId":    ArgumentBinding("trainId",    "Integer",                     binding=BindingStatus.CONTEXT,   value=trainId),
        "testId":     ArgumentBinding("testId",     "Integer",                     binding=BindingStatus.CONTEXT,   value=testId),
        "criteria":   ArgumentBinding("criteria",   "List[Tuple[String,Integer]]",  binding=BindingStatus.CONSTANT,  value=criteria),
      },
      output_var="selected_sprite_grid",
      output_value=output_grid,
      output_type="Grid",
      scenarioId=scenarioId,
      ruleId=ruleId,
      trainId=trainId,
      testId=testId,
      isTrain=(testId == -1),
      isToOutput=False
    )

def build_repaint_instance(
    instance: ActionInstance,
    buffer_inst: ActionInstance
) -> ActionInstance:
    action = registry.get_by_id("repaint")

    instance_id = f"repaint_{instance.scenarioId}_{instance.ruleId}_{instance.id}_train{instance.trainId}_test{instance.testId}"

    print(f"build_repaint_instance repaintMinX {instance.repaintMinX} repaintMinY {instance.repaintMinY} ")
    #print(f"buffer_inst.output_value {grid_to_pretty_string(buffer_inst.output_value)} ")
    print(f"buffer_inst.output_value {buffer_inst.output_value} ")
    #print(f"instance.output_value {grid_to_pretty_string(instance.output_value)} ")
    print(f"instance.output_value {instance.output_value} ")
    output_value = repaint(buffer_inst.output_value, instance.output_value, instance.repaintMinX, instance.repaintMinY)

    return ActionInstance(
        id=instance_id,
        action=action,
        bindings={
            # "scenarioId":     ArgumentBinding("scenarioId",     "String",                      binding=BindingStatus.INSTANCE,   value=instance.scenarioId),
            # "ruleId":         ArgumentBinding("ruleId",         "String",                      binding=BindingStatus.INSTANCE,   value=instance.ruleId),
            # "trainId":        ArgumentBinding("trainId",        "Integer",                     binding=BindingStatus.CONTEXT,    value=instance.trainId),
            # "testId":         ArgumentBinding("testId",         "Integer",                     binding=BindingStatus.CONTEXT,    value=instance.testId),
            "base":           ArgumentBinding("base",           "Grid",                        binding=BindingStatus.BUFFER,     value=buffer_inst.output_value, source_procedure_id=buffer_inst.id),
            "patch":          ArgumentBinding("patch",         "Grid",                        binding=BindingStatus.VARIABLE,   value=instance.output_value, source_procedure_id=instance_id),
            "minX":           ArgumentBinding("minX",           "Integer",                     binding=BindingStatus.UNRESOLVED, value=instance.repaintMinX),
            "minY":           ArgumentBinding("minY",           "Integer",                     binding=BindingStatus.UNRESOLVED, value=instance.repaintMinY),
        },
        output_var=f"repaint_{instance.id}",
        output_type="Grid",
        output_value=output_value,
        trainId=instance.trainId,
        testId=instance.testId,
        isTrain=(instance.testId == -1),
        isToOutput=False,
        scenarioId=instance.scenarioId,
        ruleId=instance.ruleId,
        bufferInstance=buffer_inst
    )

class RecolorSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("recolor_sprite", "recolor_sprite")

    def _test_function(self, conn):
        query = """
        SELECT distinct st.sprite_unique_id, so.trainId, so.testId, so.isInsideOutput,
               su.data, st.recolored, so.minX, so.minY
        FROM sprite_transformation st
        JOIN sprite_occurrence so ON so.sprite_transformation_id = st.id
        JOIN sprite_unique su ON su.id = st.sprite_unique_id        
        WHERE st.recolored IS NOT NULL AND st.recolored != '[]'
        AND COALESCE(st.zoom_x, 1) = 1
        AND COALESCE(st.zoom_y, 1) = 1
        AND COALESCE(st.rotated_90, 0) = 0
        AND COALESCE(st.rotated_180, 0) = 0
        AND COALESCE(st.rotated_270, 0) = 0
        AND COALESCE(st.flipped_vert, 0) = 0
        AND COALESCE(st.flipped_horiz, 0) = 0
        AND COALESCE(st.flipped_vert_90, 0) = 0
        AND COALESCE(st.flipped_horiz_90, 0) = 0
        AND so.sprite_id IS NOT NULL
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _build_function(self, row):
        base_data = json.loads(row["data"])
        input_grid = to_concrete_grid(base_data)
        recolor_pairs = json.loads(row["recolored"])
        output_grid = recolor_sprite(input_grid, recolor_pairs)
        trainId = row["trainId"]
        return ActionInstance(
            id=f"recolor_{row['sprite_unique_id']}#{getUniqueId()}",
            action=registry.get_by_id(self.action_id),
            bindings={
                "grid": ArgumentBinding(name="grid", type="Grid", binding=BindingStatus.UNRESOLVED, value=input_grid),
                "recolor_map": ArgumentBinding(name="recolor_map", type="List<List<Integer>>", binding=BindingStatus.UNRESOLVED, value=recolor_pairs)
            },
            output_var="recolored_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=row["testId"],
            isTrain=(trainId != -1),
            isToOutput=row["isInsideOutput"],
            toRepaint=True,
            repaintMinX=row["minX"],
            repaintMinY=row["minY"],
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

class CropSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("crop_sprite", "crop_sprite")

    def _test_function(self, conn):
        query = """
        SELECT
          so.trainId   AS trainId,
          so.testId    AS testId,
          so.minX      AS minX,
          so.minY      AS minY,
          su.width     AS width,
          su.height    AS height,
          su.data      AS data
        FROM sprite_occurrence so
        JOIN sprite_transformation st ON so.sprite_transformation_id = st.id
        JOIN sprite_unique su ON so.sprite_unique_id = su.id
        WHERE so.sprite_id IS NULL
          AND st.rotated_90=0 AND st.rotated_180=0 AND st.rotated_270=0
          AND st.flipped_vert=0 AND st.flipped_horiz=0
          AND st.flipped_vert_90=0 AND st.flipped_horiz_90=0
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _build_function(self, row):
        print(f"[DEBUG crop_sprite] Received row: {row}")
        if row is None:
            print("[DEBUG crop_sprite] Row is None, skipping build")
            return None
        if row is None:
            return None
        input_grid = TRAIN_INPUT_GRIDS[row["trainId"]] if row["trainId"] != -1 else TEST_INPUT_GRIDS[row["testId"]]
        grid = to_concrete_grid(input_grid)
        cropped = crop(
            grid,
            int(row["minX"]),
            int(row["minY"]),
            int(row["width"]),
            int(row["height"])
        )

        print("grid_to_pretty_string(cropped)")
        print(grid_to_pretty_string(cropped))

        return ActionInstance(
            id=f"crop_sprite_{row['trainId']}_{row['minX']}_{row['minY']}#{getUniqueId()}",
            action=registry.get_by_id("crop_sprite"),
            bindings={
                "grid": ArgumentBinding("grid", "Grid", binding=BindingStatus.INPUT_GRID),
                "minX": ArgumentBinding("minX", "Integer", binding=BindingStatus.UNRESOLVED, value=row["minX"]),
                "minY": ArgumentBinding("minY", "Integer", binding=BindingStatus.UNRESOLVED, value=row["minY"]),
                "width": ArgumentBinding("width", "Integer", binding=BindingStatus.UNRESOLVED, value=row["width"]),
                "height": ArgumentBinding("height", "Integer", binding=BindingStatus.UNRESOLVED, value=row["height"]),
            },
            output_var="cropped_sprite",
            output_value=cropped,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True
        )

class SpriteComputationFactToAction:
    def __init__(self):
        self.fact_name = "sprite_computation"
        self.action_id = "sprite_computation_paint"
        self.action = registry.get_by_id(self.action_id)
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn):
        query = """
        SELECT
            sc.trainId,
            sc.sprite_id,
            sc.computation_id,
            main.width  AS width,
            main.height AS height,
            main.data   AS canvas_data,
            sub.data    AS sprite_data,
            sc.sub_rel_min_x AS x,
            sc.sub_rel_min_y AS y
        FROM sprite_computation sc
        JOIN sprite_analysis main ON main.id = sc.sprite_id
        JOIN sprite_analysis sub ON sub.id = sc.sub_sprite_id
        ORDER BY sc.trainId, sc.sprite_id, sc.computation_id
        """
        cursor = conn.execute(query)
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Group rows manually by (trainId, sprite_id, computation_id)
        from collections import defaultdict
        grouped = defaultdict(lambda: {
            "trainId": None, "sprite_id": None, "computation_id": None,
            "canvas_data": None, "width": None, "height": None,
            "sub_sprites": []
        })

        for row in rows:
            key = (row["trainId"], row["sprite_id"], row["computation_id"])
            group = grouped[key]
            group["trainId"] = row["trainId"]
            group["sprite_id"] = row["sprite_id"]
            group["computation_id"] = row["computation_id"]
            group["canvas_data"] = row["canvas_data"]
            group["width"] = row["width"]
            group["height"] = row["height"]
            group["sub_sprites"].append({
                "sprite_data": row["sprite_data"],
                "x": row["x"],
                "y": row["y"]
            })

        return list(grouped.values())

    def _build_function(self, row):
        from constelize.dsl.grid_dsl import to_concrete_grid, paint, grids_equal

        trainId = row["trainId"]
        sub_sprites_info = row["sub_sprites"]
        canvas_data = json.loads(row["canvas_data"])
        h, w = int(row["height"]), int(row["width"])

        # 🧱 Create anonymized mask: -8 for each pixel in the canvas
        coords = [coord for val, coord in canvas_data]
        mask = [[-1 for _ in range(w)] for _ in range(h)]
        for i, j in coords:
            if 0 <= i < h and 0 <= j < w:
                mask[i][j] = -8
        mask_sprite = tuple(tuple(row) for row in mask)

        sprite_grids = []
        painted = mask_sprite
        position_bindings = []

        for idx, sub in enumerate(sub_sprites_info):
            sprite = to_concrete_grid(json.loads(sub["sprite_data"]))
            sprite = tuple(tuple(cell for cell in row) for row in sprite)  # ensure copy
            x, y = sub["x"], sub["y"]
            painted = paint(painted, sprite, (y, x))
            sprite_grids.append(sprite)

            coord_binding = ArgumentBinding(
                name=f"coord_{idx}",
                type="Coord",
                binding=BindingStatus.COMPOUND,
                sub_bindings={
                    "x": ArgumentBinding(name="x", type="Integer", binding=BindingStatus.UNRESOLVED, value=x),
                    "y": ArgumentBinding(name="y", type="Integer", binding=BindingStatus.UNRESOLVED, value=y),
                },
                sub_bindings_length_status=BindingStatus.CONSTANT,
                sub_bindings_length_value=2
            )
            position_bindings.append(coord_binding)

        #sprite_computation_paint(mask_sprite, )
        print(f"[ painted: {painted} ]")

        return ActionInstance(
            id=f"sprite_composition_{trainId}_{row['sprite_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "canvas": ArgumentBinding(
                    name="canvas",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=mask_sprite
                ),
                "sub_sprites": ArgumentBinding(
                    name="sub_sprites",
                    type="Array<Grid>",
                    binding=BindingStatus.COMPOUND,
                    sub_bindings=[
                        ArgumentBinding(
                            name=f"sprite_{i}",
                            type="Grid",
                            binding=BindingStatus.UNRESOLVED,
                            value=tuple(tuple(cell for cell in row) for row in sprite_grids[i])  # deepcopy défensif ici
                        )
                        for i in range(len(sprite_grids))
                    ],
                    sub_bindings_length_status=BindingStatus.CONSTANT,
                    sub_bindings_length_value=len(sprite_grids)
                ),
                "positions": ArgumentBinding(
                    name="positions",
                    type="Array<Coord>",
                    binding=BindingStatus.COMPOUND,
                    sub_bindings=position_bindings,
                    sub_bindings_length_status=BindingStatus.CONSTANT,
                    sub_bindings_length_value=len(position_bindings)
                )
            },
            output_var="sprite_composed_grid",
            output_value=painted,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=-1,
            isTrain=True,
            isToOutput=True,
            END=grids_equal(painted, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

# =============================================================================
# DenoiseFactToAction: mapping to denoise a noised grid
# =============================================================================
class DenoiseFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("denoise", "denoise")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        rows: List[Dict[str, Any]] = []
        threshold_ratio = 0.07

        for trainId, grid in TRAIN_INPUT_GRIDS.items():
            # compute noise map
            noise_map = detect_noise(grid)
            total_pixels = len(grid) * len(grid[0])
            # require at least 7% noisy pixels
            if len(noise_map) < threshold_ratio * total_pixels:
                return []
            # compute the denoised output
            denoised = denoise_grid(grid, noise_map)
            rows.append({
                "trainId": trainId,
                "testId": -1,
                # pass the raw grid and maps as JSON strings
                "input_grid": json.dumps(grid),
                "output_grid": json.dumps(denoised),
                "noise_map": json.dumps([[i, j, c] for (i, j), c in noise_map.items()]),
            })

        return rows

    def _build_function(self, row: dict) -> ActionInstance:
        print("[ DenoiseFactToAction ] _build_function")
        input_grid = json.loads(row["input_grid"])
        noise_list = json.loads(row["noise_map"])  # [[i,j,color], ...]
        noise_map = {(i, j): color for i, j, color in noise_list}
        output_grid = json.loads(row["output_grid"])

        print(f"[ DenoiseFactToAction ] input_grid : {grid_to_pretty_string(input_grid)}")
        print(f"[ DenoiseFactToAction ] output_grid : {grid_to_pretty_string(output_grid)}")

        trainId = row["trainId"]
        testId = row["testId"]

        # 2. Look up the action
        action = registry.get_by_id(self.action_id)

        # 3. Build the ActionInstance
        inst = ActionInstance(
            id=f"{self.action_id}_{trainId}#{getUniqueId()}",
            action=action,
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.INPUT_GRID,
                    value=input_grid
                )
            },
            output_var="denoised_grid",
            output_value=output_grid,
            output_type=action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=testId,
            isTrain=(trainId != -1),
            isToOutput=True
        )

        # 4. Mark this instance as needing its own rule
        inst.IN_SEPARATE_RULE = True

        return inst

class ZoomOutFactToAction(FactToActionMapping):
    def __init__(self):
        # We assume you've registered an 'unzoom' action in your ActionRegistry
        super().__init__("zoom_out", "unzoom")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn) -> list[dict]:
        # Find all cases where input→output is a clean integer shrink
        query = """
        SELECT
          inp.trainId,
          inp.testId,
          inp.id   AS input_sprite_id,
          outp.id  AS output_sprite_id,
          inp.width  AS in_w,
          inp.height AS in_h,
          outp.width  AS out_w,
          outp.height AS out_h,
          (inp.width  / outp.width)  AS zoom_x,
          (inp.height / outp.height) AS zoom_y,
          inp.data   AS input_data,
          outp.data  AS output_data
        FROM sprite_analysis AS inp
        JOIN sprite_analysis AS outp
          ON inp.trainId = outp.trainId
         AND inp.testId  = outp.testId
        WHERE
          inp.isInsideInput  = 1
          AND outp.isInsideOutput = 1
          /* integer shrink factors */
          AND inp.width  % outp.width  = 0
          AND inp.height % outp.height = 0
          /* skip trivial 1×1 */
          AND (inp.width  != outp.width
            OR  inp.height != outp.height)
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        candidates = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # now filter by actual unzoom()
        valid = []
        for r in candidates:
            inp_grid = to_concrete_grid(json.loads(r["input_data"]))
            out_grid = to_concrete_grid(json.loads(r["output_data"]))
            zx = int(r["zoom_x"])
            zy = int(r["zoom_y"])
            # only keep if unzoom really matches
            if unzoom(inp_grid, zx, zy) == out_grid:
                valid.append(r)

        return valid

    def _build_function(self, row: dict) -> ActionInstance:

        # Parse grids and factors
        input_grid = to_concrete_grid(json.loads(row["input_data"]))
        output_grid = to_concrete_grid(json.loads(row["output_data"]))
        zx = int(row["zoom_x"])
        zy = int(row["zoom_y"])

        print("[ Zoom Out build ]")
        print("input_grid")
        print(grid_to_pretty_string(input_grid))
        print("output_grid")
        print(grid_to_pretty_string(output_grid))

        return ActionInstance(
            id=f"zoom_out_{row['input_sprite_id']}#{getUniqueId()}",
            action=self.action,  # the 'unzoom' action
            bindings={
                "grid": ArgumentBinding(
                    name="grid",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=input_grid
                ),
                "zoom_x": ArgumentBinding(
                    name="zoom_x",
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=zx
                ),
                "zoom_y": ArgumentBinding(
                    name="zoom_y",
                    type="Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=zy
                ),
            },
            output_var="unzoomed_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True,
            END=(unzoom(input_grid, zx, zy) == output_grid)
        )

# =============================================================================
# CreateObjectFactToAction: mapping for newly created output‐only objects
# =============================================================================
class CreateObjectFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("create_object", "create_object")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT DISTINCT
          so.object_id AS object_id,
          so.trainId   AS trainId,
          so.testId    AS testId,
          oa.data      AS data,
          oa.color     AS color
        FROM object_analysis AS oa
        JOIN shape_occurrence AS so 
          ON so.object_id = oa.id
        WHERE
          so.isInsideOutput = 1
          AND NOT EXISTS (
            SELECT 1
            FROM object_analysis AS ia
            JOIN shape_occurrence  AS ii
              ON ii.object_id = ia.id
            WHERE
              ii.isInsideInput = 1
              AND ii.trainId     = so.trainId
              AND ii.testId      = so.testId
              AND ia.data        = oa.data
              AND ia.color       = oa.color
          )
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        # Load list of pixel coords for this object
        coords: List[List[int]] = json.loads(row["data"])
        coords_set = {(r, c) for r, c in coords}

        # Compute bounding box
        rows = [r for r, _ in coords]
        cols = [c for _, c in coords]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)
        height = max_r - min_r + 1
        width = max_c - min_c + 1

        # Build mask grid as list of lists, then convert to tuple of tuples
        mask_grid_list = [
            [-8 if (min_r + y, min_c + x) in coords_set else -1
             for x in range(width)]
            for y in range(height)
        ]
        mask_grid: Grid = tuple(tuple(row) for row in mask_grid_list)

        # Build output grid: replace -8 with color, keep -1 as background
        color = row["color"]
        output_grid: Grid = fill_grid(mask_grid,color)

        print(f" [ CreateObjectFactToAction ] color: {color}")
        print(f"mask_grid")
        print(grid_to_pretty_string(mask_grid))
        print(f"output_grid")
        print(grid_to_pretty_string(output_grid))

        action = registry.get_by_id(self.action_id)
        return ActionInstance(
            id=f"{self.action_id}_{row['object_id']}#{getUniqueId()}",
            action=action,
            bindings={
                "mask": ArgumentBinding(
                    name="mask",
                    type="Grid",
                    binding=BindingStatus.UNRESOLVED,
                    value=mask_grid
                ),
                "color": ArgumentBinding(
                    name="color",
                    type="Color",
                    binding=BindingStatus.UNRESOLVED,
                    value=color
                )
            },
            output_var="new_object",
            output_value=output_grid,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True,
            END=False
        )

# =============================================================================
# FACT_TO_ACTION_MAPPING: list of all mappings.
# =============================================================================
FACT_TO_ACTION_MAPPING: List[FactToActionMapping] = [
    FactToActionMapping("rotated_90", "rotate_90"),
    FactToActionMapping("rotated_180", "rotate_180"),
    FactToActionMapping("rotated_270", "rotate_270"),
    FactToActionMapping("flipped_horizontal", "mirror_vertical", "flipped_horiz"),
    FactToActionMapping("flipped_vertical", "mirror_horizontal", "flipped_vert"),
    FactToActionMapping("flipped_horiz_90", "flipped_horiz_90"),
    FactToActionMapping("flipped_vert_90", "flipped_vert_90"),
    ZoomFactToAction(),
    RepeatedSpriteFactToAction(),
    CanvasByRatioFactToAction(),
    RecolorSpriteFactToAction(),
    CropSpriteFactToAction(),
    SpriteComputationFactToAction(),
    DenoiseFactToAction(),
    ZoomOutFactToAction(),
    CreateObjectFactToAction()
]

