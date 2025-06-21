# constelize/tools/fact_to_action_mapping.py
import itertools
import json
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
from collections import Counter
from collections import defaultdict
from itertools import product

from constelize.core.procedure import ActionInstance, Procedure
from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.registry import ActionRegistry
from constelize.dsl.grid_dsl import to_concrete_grid, grids_equal, unzoom, recolor_sprite, grid_to_pretty_string, crop, \
    Grid, fill_grid, shift, shift_with_background, shift_sprite_with_background, paint, makeShrinkableCanvas, \
    shrinkCanvas, zoom, apply_all_cycles, concrete_grids_equal, apply_ca, select_conditional_object, \
    apply_cellular_automaton
from constelize.library.pattern_detection import detect_noise, denoise_grid, apply_symmetry_fill, \
    extract_connected_components
from constelize.library.spatial_transformation import zoom as zoom_function, canvas_by_ratio_fn, repaint, \
    canvas_by_object_size_fn
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

def checkAnyInputEqualOrSmallerThanOutput() -> bool:
    """
    Return True if any training‐example’s input grid is equal‐or‐smaller
    (in width or height) than its corresponding output grid.
    """
    for trainId, inp in TRAIN_INPUT_GRIDS.items():
        out = TRAIN_OUTPUT_GRIDS.get(trainId)
        if out is None:
            continue

        h_in = len(inp)
        w_in = len(inp[0]) if h_in else 0
        h_out = len(out)
        w_out = len(out[0]) if h_out else 0

        # if input is equal‐or‐smaller in either dimension, bail out
        if w_in < w_out or h_in < h_out or (w_in == w_out and h_in == h_out):
            return True

    return False

def checkInputSmaller() -> bool:
    """
    Return True as soon as any training‐example’s input grid is strictly smaller
    (in width or height) than its corresponding output grid.
    Otherwise return False.
    """
    for trainId, inp in TRAIN_INPUT_GRIDS.items():
        out = TRAIN_OUTPUT_GRIDS.get(trainId)
        if out is None:
            # no output to compare, skip
            continue

        # assume both inp and out are List[List[…]]
        h_in = len(inp)
        w_in = len(inp[0]) if h_in else 0
        h_out = len(out)
        w_out = len(out[0]) if h_out else 0

        # if output is bigger in either dimension, we have an “input smaller” case
        if w_in < w_out or h_in < h_out:
            return True

    return False

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
        self.current_rule = None
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
            sa.id AS sprite_analysis_id,
            sa.isGrid,
            st.sprite_unique_id,
            sa.trainId,
            sa.testId,
            source.data AS source_data,
			sa_po.minX,
			sa_po.minY
        FROM sprite_transformation AS st
        INNER JOIN sprite_unique AS produced ON produced.id = st.sprite_produce_id
        INNER JOIN sprite_unique AS source ON source.id = st.sprite_unique_id
        INNER JOIN sprite_analysis AS sa ON sa.id = source.sprite_id
        LEFT JOIN sprite_analysis AS sa_po ON sa_po.id = produced.sprite_id
        WHERE st.{self.column_name} = 1
          AND COALESCE(st.zoom_x, 1) = 1
          AND COALESCE(st.zoom_y, 1) = 1
          AND (st.recolored IS NULL OR st.recolored = '[]')
          AND sa.isInsideInput = 1
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # 2) Pour chaque (trainId, testId), ne garder que la ligne dont
        #    'source_data' est la plus volumineuse (le plus grand nombre d'éléments JSON).
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in rows:
            key = (r['trainId'], r['testId'])
            grouped[key].append(r)

        filtered = []
        for key, candidates in grouped.items():
            # trouver la longueur JSON la plus grande
            best = max(
                candidates,
                key=lambda r: len(json.loads(r['source_data']))
            )
            filtered.append(best)

        return filtered

    def _build_function(self, row: dict) -> ActionInstance:
        source_raw_data = json.loads(row["source_data"])
        input_grid = to_concrete_grid(source_raw_data)

        #if self.column_name == "rotated_180":
           #print("[ rotated_180 ]")
           #print("input_grid")
           #print(grid_to_pretty_string(input_grid))
           #print("output_grid")
           #print(grid_to_pretty_string(output_grid))

        grid_binding = ArgumentBinding(
            name="grid",
            type="Grid",
            binding=BindingStatus.UNRESOLVED,
            value=input_grid
        )
        isGrid = row["isGrid"]
        if isGrid:
            grid_binding.binding = BindingStatus.INPUT_GRID
        else:
            sprite_analysis_id = row.get("sprite_analysis_id")
            if sprite_analysis_id is not None:
                grid_binding.suggested_action = "selectSpriteGridAction"
                grid_binding.suggested_sprite_id =  sprite_analysis_id

        trainId = row["trainId"]

        output_grid = self.action.function(input_grid)

        #isEnd = grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        #print(f"trainId: {trainId}, Rot/Flip END:")
        #print(isEnd)
        #print(grid_to_pretty_string(output_grid))
        #print(grid_to_pretty_string(END_OUTPUTS_BY_TRAINID.get(trainId)))


        return ActionInstance(
            id=f"{self.action_id}_instance_{row['sprite_unique_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "grid": grid_binding
            },
            output_var=f"{self.action_id}_grid",
            output_value=output_grid,
            output_type=self.action.output_type,
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=row["testId"],
            isTrain=trainId != -1,
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
        WITH filtered AS (
          SELECT
            st.sprite_unique_id,
            st.sprite_produce_id,
            so.trainId,
            so.testId,
            so.isInsideOutput,
            su.data,
            st.zoom_x,
            st.zoom_y,
            so.minX,
            so.minY,
            -- compute a per-row zoom_factor without any window/aggregate
            CASE 
              WHEN st.zoom_x > st.zoom_y THEN st.zoom_x 
              ELSE st.zoom_y 
            END AS zoom_factor
          FROM sprite_transformation st
          JOIN sprite_occurrence  so ON so.sprite_transformation_id = st.id
          JOIN sprite_unique      su ON su.id = st.sprite_produce_id
          WHERE (st.zoom_x > 1 OR st.zoom_y > 1)
            AND COALESCE(st.rotated_90 , 0) = 0
            AND COALESCE(st.rotated_180, 0) = 0
            AND COALESCE(st.rotated_270, 0) = 0
            AND COALESCE(st.flipped_vert , 0) = 0
            AND COALESCE(st.flipped_horiz, 0) = 0
            AND COALESCE(st.flipped_vert_90 , 0) = 0
            AND COALESCE(st.flipped_horiz_90, 0) = 0
            AND (st.recolored IS NULL OR st.recolored = '[]')
            AND so.sprite_id IS NOT NULL
        ),
        ranked AS (
          SELECT
            *,
            ROW_NUMBER() 
              OVER (
                PARTITION BY trainId 
                ORDER   BY zoom_factor DESC
              ) AS rn
          FROM filtered
        )
        SELECT
          sprite_unique_id,
          sprite_produce_id,
          trainId,
          testId,
          isInsideOutput,
          data,
          zoom_x,
          zoom_y,
          minX,
          minY
        FROM ranked
        WHERE rn = 1;
        """
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Collect which trainIds have zoom
        train_ids_with_zoom = {r["trainId"] for r in rows if r["trainId"] != -1}
        all_train_ids = set(TRAIN_INPUT_GRIDS.keys())

        if not all_train_ids.issubset(train_ids_with_zoom):
            #print(f"❌ Zoom not detected in all training examples. Found: {train_ids_with_zoom}, Expected: {all_train_ids}")
            return []

        seen = set()
        unique_rows = []
        for r in rows:
            key = (r["trainId"], r["zoom_x"], r["zoom_y"])
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

        #print("ZoomFactToAction _build_function ")
        #print("grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))")
        #print(grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId)))
        #print("output_grid")
        #print(output_grid)
        #print("END_OUTPUTS_BY_TRAINID.get(trainId))")
        #print(END_OUTPUTS_BY_TRAINID.get(trainId))

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
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # require at least one recolor hit in every train
        train_ids_with_recolor = {r["trainId"] for r in rows if r["trainId"] != -1}
        all_train_ids = set(TRAIN_INPUT_GRIDS.keys())
        if not all_train_ids.issubset(train_ids_with_recolor):
            return []

        return rows

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

class UnRepeatSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("unrepeated_sprite", "unrepeated_sprite")

    def _test_function(self, conn):
        query = """
        WITH sprite_output_counts AS (
            SELECT
                st.sprite_produce_id AS sprite_unique_id,
                so.trainId,
                COUNT(DISTINCT so.minX || ',' || so.minY) AS count_occurrences,
                MAX(LENGTH(su.data)) AS data_len
            FROM sprite_occurrence so
            JOIN sprite_transformation st ON so.sprite_transformation_id = st.id
            JOIN sprite_unique su ON su.id = st.sprite_produce_id
            WHERE so.isInsideOutput = 1
            GROUP BY st.sprite_produce_id, so.trainId
        )
        SELECT
            so.sprite_transformation_id,
            st.sprite_produce_id AS sprite_unique_id,
            so.trainId,
            so.testId,
            su.data,
            so.minX,
            so.minY,
            COUNT(DISTINCT so.minX || ',' || so.minY) AS occurrence_count
        FROM sprite_occurrence so
        JOIN sprite_transformation st ON so.sprite_transformation_id = st.id
        JOIN sprite_unique su ON su.id = st.sprite_produce_id
        JOIN sprite_output_counts soc ON soc.sprite_unique_id = st.sprite_produce_id AND soc.trainId = so.trainId
        WHERE so.isInsideOutput = 1
        GROUP BY st.sprite_produce_id, so.trainId, so.testId
        HAVING occurrence_count = 1
        ORDER BY soc.data_len DESC
        LIMIT 1
        """
        cursor = conn.execute(query)
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        train_ids_found = {r["trainId"] for r in rows if r["trainId"] != -1}
        if not set(TRAIN_OUTPUT_GRIDS.keys()).issubset(train_ids_found):
            return []

        return rows

    def _build_function(self, row: dict) -> ActionInstance:
        sprite_grid = to_concrete_grid(json.loads(row["data"]))
        output_coords = [(row["minX"], row["minY"])]
        trainId = row["trainId"]
        testId = row["testId"]

        output_grid_raw = TRAIN_OUTPUT_GRIDS.get(trainId)
        if output_grid_raw is None:
            raise ValueError(f"Missing output grid for trainId={trainId}")

        anonymized_canvas = tuple(tuple(-8 for _ in r) for r in output_grid_raw)
        painted_canvas = paint(anonymized_canvas, sprite_grid, (row["minY"], row["minX"]))

        output_positions_binding = ArgumentBinding(
            name="output_positions",
            type="Array<Coord>",
            binding=BindingStatus.COMPOUND,
            sub_bindings=[],
            sub_bindings_length_status=BindingStatus.UNRESOLVED,
            sub_bindings_length_value=1
        )
        x_val = int(row["minX"])
        y_val = int(row["minY"])
        output_positions_binding.sub_bindings.append(
            ArgumentBinding(
                name="coord_0",
                type="Coord",
                binding=BindingStatus.COMPOUND,
                sub_bindings={
                    "x": ArgumentBinding(name="x", type="Integer", binding=BindingStatus.UNRESOLVED, value=x_val),
                    "y": ArgumentBinding(name="y", type="Integer", binding=BindingStatus.UNRESOLVED, value=y_val),
                },
                sub_bindings_length_status=BindingStatus.CONSTANT,
                sub_bindings_length_value=2
            )
        )

        return ActionInstance(
            id=f"unrepeated_sprite_{row['sprite_unique_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "output_canvas": ArgumentBinding(
                    name="output_canvas", type="Grid", binding=BindingStatus.UNRESOLVED, value=anonymized_canvas),
                "sprite": ArgumentBinding(
                    name="sprite", type="Grid", binding=BindingStatus.UNRESOLVED, value=sprite_grid),
                "output_positions": output_positions_binding,
            },
            output_var="unrepeated_grid",
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
            #print("TRAIN_INPUT_GRIDS")
            #print(TRAIN_INPUT_GRIDS)
            if trainId in TRAIN_INPUT_GRIDS:
                input_grid = TRAIN_INPUT_GRIDS[trainId]
                #print(f"[CanvasByRatio] Using TRAIN_INPUT_GRIDS for trainId {trainId}: {input_grid}")
            else:
                raise ValueError(f"No input grid found in TRAIN_INPUT_GRIDS for trainId {trainId}")
        else:
            #print("TEST_INPUT_GRIDS")
            #print(TEST_INPUT_GRIDS)
            testId = row.get("testId", -1)
            if testId in TEST_INPUT_GRIDS:
                input_grid = TEST_INPUT_GRIDS[testId]
                #print(f"[CanvasByRatio] Using TEST_INPUT_GRIDS for testId {testId}: {input_grid}")
            else:
                raise ValueError(f"No input grid found in TEST_INPUT_GRIDS for testId {testId}")
        output_grid = canvas_by_ratio_fn(input_grid, ratio_w, ratio_h)
        #print(f"[CanvasByRatio] For id {trainId if trainId != -1 else row.get('testId', -1)}, using ratio=({ratio_w}, {ratio_h}), computed canvas: {output_grid}")
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

class CanvasByObjectSizeFactToAction(FactToActionMapping):
    def __init__(self):
        # fact_name is just a label; action_id must match the registered action
        super().__init__("canvas_by_object_size", "canvas_by_object_size")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        if checkInputSmaller():
            return []
        query = """
        SELECT DISTINCT
            inp.trainId,
            inp.testId,			
            obj.id AS object_id,
            inp.width  AS input_width,
            inp.height AS input_height,
            outp.width AS output_width,
            outp.height AS output_height,
            obj.width AS object_width,
            obj.height AS object_height
        FROM sprite_analysis AS inp
        JOIN sprite_analysis AS outp
          ON inp.trainId = outp.trainId
         AND inp.testId  = outp.testId
        JOIN object_analysis AS obj
          ON obj.trainId = inp.trainId
         AND obj.testId  = inp.testId
         AND obj.isInsideInput = 1
        WHERE
          inp.isInsideInput   = 1
          AND inp.isGrid       = 1
          AND outp.isInsideOutput = 1
          AND outp.isGrid      = 1
          -- grid sizes must differ
          AND (outp.width != inp.width OR outp.height != inp.height)
          -- exclude cases where output is ≥ input in both dimensions
          AND NOT (outp.width >= inp.width AND outp.height >= inp.height)
          -- and there must be an object whose size exactly equals the output
          AND obj.width  = outp.width
          AND obj.height = outp.height
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # 2) Bail out if no candidate at all
        if not rows:
            return []

        # 3) Which trains actually matched?
        found_tids = {r["trainId"] for r in rows if r["trainId"] != -1}

        # 4) Expected trains from TRAIN_INPUT_GRIDS
        expected_tids = set(TRAIN_INPUT_GRIDS.keys())

        # 5) Only proceed if every train has at least one row
        if found_tids != expected_tids:
            return []

        return rows

    def _build_function(self, row: dict) -> ActionInstance:
        obj_w = int(row["object_width"])
        obj_h = int(row["object_height"])
        trainId, testId = row["trainId"], row["testId"]
        output_grid = canvas_by_object_size_fn(obj_w, obj_h)

        return ActionInstance(
            id=f"canvas_by_object_size#{getUniqueId()}",
            action=self.action,
            bindings={
                "object_width": ArgumentBinding(
                    "object_width", "Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=obj_w,
                    suggested_action="selectObjectAndAttributeAction",
                    suggested_object_id=row["object_id"],
                    suggested_attribute="width"
                ),
                "object_height": ArgumentBinding(
                    "object_height", "Integer",
                    binding=BindingStatus.UNRESOLVED,
                    value=obj_h,
                    suggested_action="selectObjectAndAttributeAction",
                    suggested_object_id=row["object_id"],
                    suggested_attribute="height"
                ),
            },
            output_var="canvas_grid",
            output_value=output_grid,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=trainId,
            testId=testId,
            isTrain=(trainId != -1),
            isToOutput=True,
            END=False
        )

# =============================================================================
# build_start_input: Now modified to use BindingStatus.INPUT_GRID
# =============================================================================
def build_start_input(id: int, grid, isTrain: bool, scenarioId: str = "scenario_1", ruleId: str = "rule_1") -> ActionInstance:
    #print("[ build_start_input ] registry.get_by_id(get_start_input)")
    action = registry.get_by_id("get_start_input")
    #print(action)
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

    #print(f"build_get_attribute_instance binding_type: {binding_type}")

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
    criteria: List[Tuple[str, Any, int]],
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
    criteria: List[Tuple[str, Any, int]],
    attribute_name: str,
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
    trainId: int,
    testId: int,
    output_grid: Grid,
    criteria: List[Tuple[str, Any, int]],
    scenarioId: str,
    ruleId: str,
    transform: Optional[Dict[str,Any]] = None
) -> ActionInstance:
    action = registry.get_by_id("select_sprite_grid")

    # ── 1) core bindings ─────────────────────────────────────────────────────────
    bindings = {
        "scenarioId": ArgumentBinding(
            name="scenarioId",
            type="String",
            binding=BindingStatus.INSTANCE,
            value=scenarioId
        ),
        "ruleId": ArgumentBinding(
            name="ruleId",
            type="String",
            binding=BindingStatus.INSTANCE,
            value=ruleId
        ),
        "trainId": ArgumentBinding(
            name="trainId",
            type="Integer",
            binding=BindingStatus.CONTEXT,
            value=trainId
        ),
        "testId": ArgumentBinding(
            name="testId",
            type="Integer",
            binding=BindingStatus.CONTEXT,
            value=testId
        ),
        "criteria": ArgumentBinding(
            name="criteria",
            type="List[Tuple[String,Any]]",
            binding=BindingStatus.CONSTANT,
            value=criteria
        ),
    }

    # ── 2) optional transform binding ────────────────────────────────────────────
    if transform is not None:
        bindings["transform"] = ArgumentBinding(
            name="transform",
            type="TransformSpec",
            binding=BindingStatus.CONSTANT,
            value=transform
        )

    # ── 3) build and return the ActionInstance ─────────────────────────────────
    return ActionInstance(
        id=f"select_sprite_grid_{trainId}_{getUniqueId()}",
        action=action,
        bindings=bindings,
        # carry the actual selected grid as the action’s output
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

def build_select_object_grid_instance(
    trainId:    int,
    testId:     int,
    criteria:   List[Tuple[str, Any, int]],
    output_grid: Grid,
    scenarioId: str,
    ruleId:     str
) -> ActionInstance:
    from constelize.core.binding import BindingStatus
    action = registry.get_by_id("select_object_grid")
    inst_id = f"select_object_grid_{scenarioId}_{ruleId}_train{trainId}_test{testId}"
    return ActionInstance(
        id=inst_id,
        action=action,
        bindings={
            "scenarioId": ArgumentBinding(
                name="scenarioId", type="String",
                binding=BindingStatus.INSTANCE, value=scenarioId
            ),
            "ruleId": ArgumentBinding(
                name="ruleId", type="String",
                binding=BindingStatus.INSTANCE, value=ruleId
            ),
            "trainId": ArgumentBinding(
                name="trainId", type="Integer",
                binding=BindingStatus.CONTEXT, value=trainId
            ),
            "testId": ArgumentBinding(
                name="testId", type="Integer",
                binding=BindingStatus.CONTEXT, value=testId
            ),
            "criteria": ArgumentBinding(
                name="criteria", type="List[Tuple[String,int]]",
                binding=BindingStatus.CONSTANT, value=criteria
            ),
        },
        output_var="selected_object_grid",
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

    #print(f"build_repaint_instance repaintMinX {instance.repaintMinX} repaintMinY {instance.repaintMinY}")
    #print(f"buffer_inst.output_value {buffer_inst.output_value}")
    #print(f"instance.output_value {instance.output_value}")

    output_value = repaint(
        buffer_inst.output_value,
        instance.output_value,
        instance.repaintMinX,
        instance.repaintMinY
    )

    suggested_id = getattr(instance, "repaintSuggestedSpriteId", None)

    # Conditional binding fields for minX/minY
    minX_binding_kwargs = {
        "name": "minX",
        "type": "Integer",
        "binding": BindingStatus.UNRESOLVED,
        "value": instance.repaintMinX
    }
    minY_binding_kwargs = {
        "name": "minY",
        "type": "Integer",
        "binding": BindingStatus.UNRESOLVED,
        "value": instance.repaintMinY
    }

    if suggested_id:
        minX_binding_kwargs.update({
            "suggested_action": "selectSpriteAndAttributeAction",
            "suggested_sprite_id": suggested_id,
            "suggested_attribute": "minX"
        })
        minY_binding_kwargs.update({
            "suggested_action": "selectSpriteAndAttributeAction",
            "suggested_sprite_id": suggested_id,
            "suggested_attribute": "minY"
        })

    return ActionInstance(
        id=instance_id,
        action=action,
        bindings={
            "base": ArgumentBinding(
                name="base",
                type="Grid",
                binding=BindingStatus.BUFFER,
                value=buffer_inst.output_value,
                source_procedure_id=buffer_inst.id
            ),
            "patch": ArgumentBinding(
                name="patch",
                type="Grid",
                binding=BindingStatus.VARIABLE,
                value=instance.output_value,
                source_procedure_id=instance.id
            ),
            "minX": ArgumentBinding(**minX_binding_kwargs),
            "minY": ArgumentBinding(**minY_binding_kwargs),
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

def build_set_output_bg_color_fact_to_action(
    trainId:             int,
    testId:              int,
    bg_color:            int,
    input_value:         Grid,
    output_value:        Grid,
    source_producer_id:  str,
    scenarioId:          str,
    ruleId:              str
) -> ActionInstance:
    """
    Build an ActionInstance for the `set_output_bg_color_fact_to_action`
    which fills all `-1` pixels in `input_value` with `bg_color`, producing
    `output_value`.
    """
    # 1) Look up the action in the registry
    action = registry.get_by_id("set_output_bg_color")  # adapt this ID to your registration

    # 2) Construct a unique instance ID
    inst_id = (
        f"set_output_bg_color_{scenarioId}_{ruleId}_"
        f"{source_producer_id}_train{trainId}_test{testId}"
    )

    # 3) Build and return the ActionInstance
    return ActionInstance(
        id=inst_id,
        action=action,
        bindings={
            "bg_color":      ArgumentBinding("bg_color",      "Color", binding=BindingStatus.UNRESOLVED, value=bg_color),
            "grid":          ArgumentBinding(
                                name="grid",
                                type="Grid",
                                binding=BindingStatus.VARIABLE,
                                value=input_value,
                                source_procedure_id=source_producer_id,
                                use_anonymized=False
                              ),
        },
        output_var="filled_grid",
        output_type="Grid",
        output_value=output_value,
        trainId=trainId,
        testId=testId,
        isTrain=(testId == -1),
        isToOutput=True,
        scenarioId=scenarioId,
        ruleId=ruleId
    )

class RecolorSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("recolor_sprite", "recolor_sprite")

    def _test_function(self, conn) -> list[dict]:
        query = """
        SELECT DISTINCT
            su.sprite_id as origin_sprite_id,
            sp.sprite_id as produce_sprite_id,
            st.sprite_unique_id,
            so.trainId,
            so.testId,
            so.isInsideOutput,
            su.data,
            st.recolored,
            so.minX as produce_minX,
            so.minY as produce_minY,
            sa.minX as origin_minX,
            sa.minY as origin_minY
        FROM sprite_transformation AS st
        JOIN sprite_occurrence AS so
          ON so.sprite_transformation_id = st.id
        JOIN sprite_unique AS su
          ON su.id = st.sprite_unique_id	
        JOIN sprite_unique AS sp
          ON sp.id = st.sprite_produce_id	
        JOIN sprite_analysis AS sa
          ON sa.id = su.sprite_id		  	  
        WHERE
          st.recolored        IS NOT NULL
          AND st.recolored   != '[]'
          AND COALESCE(st.zoom_x,         1) = 1
          AND COALESCE(st.zoom_y,         1) = 1
          AND COALESCE(st.rotated_90,     0) = 0
          AND COALESCE(st.rotated_180,    0) = 0
          AND COALESCE(st.rotated_270,    0) = 0
          AND COALESCE(st.flipped_vert,   0) = 0
          AND COALESCE(st.flipped_horiz,  0) = 0
          AND COALESCE(st.flipped_vert_90,0) = 0
          AND COALESCE(st.flipped_horiz_90,0) = 0
          AND so.sprite_id IS NOT NULL
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # make sure every trainId in our training set has at least one recolor hit
        train_ids_with_recolor = {r["trainId"] for r in rows if r["trainId"] != -1}
        all_train_ids        = set(TRAIN_INPUT_GRIDS.keys())
        if all_train_ids - train_ids_with_recolor:
            # some train example never saw a recolor → abort
            return []

        return rows

    def _build_function(self, row):
        base_data = json.loads(row["data"])
        input_grid = to_concrete_grid(base_data)
        recolor_pairs = json.loads(row["recolored"])
        output_grid = recolor_sprite(input_grid, recolor_pairs)
        trainId = row["trainId"]


        use_origin = (
                row.get("produce_minX") == row.get("origin_minX") and
                row.get("produce_minY") == row.get("origin_minY")
        )
        suggested_id = int(row["origin_sprite_id"]) if use_origin else None
        repaint_minX = int(row["origin_minX"]) if use_origin else None
        repaint_minY = int(row["origin_minY"]) if use_origin else None

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
            repaintMinX=repaint_minX,
            repaintMinY=repaint_minY,
            repaintSuggestedSpriteId=suggested_id,
            END=grids_equal(output_grid, END_OUTPUTS_BY_TRAINID.get(trainId))
        )

class CropSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("crop_sprite", "crop_sprite")

    def _test_function(self, conn):
        if checkAnyInputEqualOrSmallerThanOutput():
            #print("CropSpriteFactToAction: checkAnyInputEqualOrSmallerThanOutput")
            return []
        query = """
        SELECT DISTINCT
            su.sprite_id                   AS sprite_id,
            so.trainId                     AS trainId,
            so.testId                      AS testId,
            so.minX                        AS minX,
            so.minY                        AS minY,
            su.width                       AS width,
            su.height                      AS height,
            su.data                        AS data,
            st.recolored                   AS recolor
        FROM sprite_occurrence so
          -- only keep occurrences coming from an output‐side sprite
          JOIN sprite_analysis sa
            ON so.sprite_id = sa.id
           AND sa.isInsideOutput = 1
           AND sa.pixelCount > 3
          JOIN sprite_transformation st
            ON so.sprite_transformation_id = st.id
          JOIN sprite_unique su
            ON so.sprite_unique_id = su.id
        WHERE
            -- no geometric transforms
            st.rotated_90   = 0
          AND st.rotated_180  = 0
          AND st.rotated_270  = 0
          AND st.flipped_vert = 0
          AND st.flipped_horiz= 0
          AND st.flipped_vert_90  = 0
          AND st.flipped_horiz_90 = 0
          -- only pure crops (no recolor)
          AND st.recolored  = '[]'
          AND st.zoom_x = 1
          AND st.zoom_y = 1
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _build_function(self, row):
        #print(f"[DEBUG crop_sprite] Received row: {row}")
        if row is None:
            #print("[DEBUG crop_sprite] Row is None, skipping build")
            return None
        if row is None:
            return None
        input_grid = TRAIN_INPUT_GRIDS[row["trainId"]] if row["trainId"] != -1 else TEST_INPUT_GRIDS[row["testId"]]
        grid = to_concrete_grid(input_grid)
        #cropped = crop(
        #    grid,
        #    int(row["minX"]),
        #    int(row["minY"]),
        #    int(row["width"]),
        #    int(row["height"])
        #)

        #print("grid_to_pretty_string(cropped)")
        #print(grid_to_pretty_string(cropped))

        raw_data = to_concrete_grid(json.loads(row["data"]))
        #print("grid_to_pretty_string(raw_data)")
        #print(grid_to_pretty_string(raw_data))

        return ActionInstance(
            id=f"crop_sprite_{row['trainId']}_{row['minX']}_{row['minY']}#{getUniqueId()}",
            action=registry.get_by_id("crop_sprite"),
            bindings={
                "grid": ArgumentBinding("grid", "Grid",        binding=BindingStatus.INPUT_GRID),
                "minX": ArgumentBinding("minX", "Integer",     binding=BindingStatus.UNRESOLVED, value=row["minX"],   suggested_action="selectSpriteAndAttributeAction", suggested_sprite_id=row["sprite_id"], suggested_attribute="minX"),
                "minY": ArgumentBinding("minY", "Integer",     binding=BindingStatus.UNRESOLVED, value=row["minY"],   suggested_action="selectSpriteAndAttributeAction", suggested_sprite_id=row["sprite_id"], suggested_attribute="minY"),
                "width": ArgumentBinding("width", "Integer",   binding=BindingStatus.UNRESOLVED, value=row["width"],  suggested_action="selectSpriteAndAttributeAction", suggested_sprite_id=row["sprite_id"], suggested_attribute="width"),
                "height": ArgumentBinding("height", "Integer", binding=BindingStatus.UNRESOLVED, value=row["height"], suggested_action="selectSpriteAndAttributeAction", suggested_sprite_id=row["sprite_id"], suggested_attribute="height"),
            },
            output_var="cropped_sprite",
            output_value=raw_data,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True
        )

# todo : improve object_analysis and this select
class CropObjectFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("crop_object", "crop_object")

    def _test_function(self, conn: sqlite3.Connection) -> list[dict]:
        # find every object that ends up in the output (but wasn’t in the input)
        query = """
        SELECT
            oa.id        AS object_id,
            oa.trainId   AS trainId,
            oa.testId    AS testId,
            oa.minX      AS minX,
            oa.minY      AS minY,
            (oa.maxX - oa.minX) AS width,
            (oa.maxY - oa.minY) AS height,
            oa.data      AS data
        FROM object_analysis oa
        WHERE oa.isInsideInput  = 0
          AND oa.isInsideOutput = 1
        """
        cursor = conn.execute(query)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _build_function(self, row: dict) -> ActionInstance:
        #print(f"[DEBUG crop_object] row → {row}")
        # pick the right grid
        raw = TRAIN_INPUT_GRIDS if row["trainId"] != -1 else TEST_INPUT_GRIDS
        grid = to_concrete_grid(raw[row["trainId"] if row["trainId"] != -1 else row["testId"]])

        ## perform the actual crop
        #cropped = crop(
        #    grid,
        #    int(row["minX"]),
        #    int(row["minY"]),
        #    int(row["width"]),
        #    int(row["height"])
        #)
        #print("[DEBUG crop_object] cropped →")
        #print(grid_to_pretty_string(cropped))

        raw_data = to_concrete_grid(json.loads(row["data"]))
        #print("grid_to_pretty_string(raw_data)")
        #print(grid_to_pretty_string(raw_data))

        # build the instance, but leave every dimension UNRESOLVED
        # and tag them so we can suggest a selectObjectAndAttributeAction later
        return ActionInstance(
            id=f"crop_object_{row['trainId']}_{row['minX']}_{row['minY']}#{getUniqueId()}",
            action=registry.get_by_id("crop_object"),
            bindings={
                "grid":   ArgumentBinding("grid",   "Grid",    binding=BindingStatus.INPUT_GRID),
                "minX":   ArgumentBinding("minX",   "Integer", binding=BindingStatus.UNRESOLVED, value=row["minX"],
                                          suggested_action="selectObjectAndAttributeAction",
                                          suggested_object_id=row["object_id"],
                                          suggested_attribute="minX"),
                "minY":   ArgumentBinding("minY",   "Integer", binding=BindingStatus.UNRESOLVED, value=row["minY"],
                                          suggested_action="selectObjectAndAttributeAction",
                                          suggested_object_id=row["object_id"],
                                          suggested_attribute="minY"),
                "width":  ArgumentBinding("width",  "Integer", binding=BindingStatus.UNRESOLVED, value=row["width"],
                                          suggested_action="selectObjectAndAttributeAction",
                                          suggested_object_id=row["object_id"],
                                          suggested_attribute="width"),
                "height": ArgumentBinding("height", "Integer", binding=BindingStatus.UNRESOLVED, value=row["height"],
                                          suggested_action="selectObjectAndAttributeAction",
                                          suggested_object_id=row["object_id"],
                                          suggested_attribute="height"),
            },
            output_var="cropped_object",
            output_value=raw_data,
            output_type="Grid",
            scenarioId=row.get("scenarioId"),
            ruleId=row.get("ruleId"),
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
          sc.sprite_id,                    -- make sure we select this!
          sc.computation_id,

          -- main (canvas) info
          main.width   AS width,
          main.height  AS height,
          main.data    AS canvas_data,

          -- sub‐sprite info
          sub.data     AS sprite_data,

          -- placement offsets
          sc.sub_rel_min_x AS x,
          sc.sub_rel_min_y AS y,

          -- linkage back to unique & original
          su.id            AS sprite_unique_id,
          sc.sprite_origin_id     AS sprite_origin_id,
          sa_orig.bgColor  AS sprite_origin_bg,

          -- transformation details
          st.id            AS sprite_transformation_id,
          st.zoom_x,
          st.zoom_y,
          st.recolored,
          st.rotated_90,
          st.rotated_180,
          st.rotated_270,
          st.flipped_vert,
          st.flipped_horiz,
          st.flipped_vert_90,
          st.flipped_horiz_90

        FROM sprite_computation AS sc

        JOIN sprite_analysis AS main 
          ON main.id            = sc.sprite_id
        JOIN sprite_analysis AS sub  
          ON sub.id             = sc.sub_sprite_id

        JOIN sprite_unique     AS su  
          ON su.id              = st.sprite_unique_id

         -- the unique‐sprite table
        JOIN sprite_unique AS su_st  
          ON su_st.id = st.sprite_unique_id
        
        -- ensure that the unique’s original sprite was inside the input
        LEFT JOIN sprite_analysis AS sa_orig
          ON sa_orig.id = su_st.sprite_id
         AND sa_orig.isInsideInput = 1
 
        LEFT JOIN sprite_transformation AS st 
          ON st.id              = sc.sprite_transformation_id
		

        ORDER BY
          sc.trainId,
          sc.sprite_id,
          sc.computation_id,
          sc.sub_rel_min_x,
          sc.sub_rel_min_y
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
                "y": row["y"],
                "sprite_origin_id": row["sprite_origin_id"],
                "sprite_origin_bg": row["sprite_origin_bg"],
                "sprite_transformation_id": row["sprite_transformation_id"],
                "zoom_x":                   row["zoom_x"],
                "zoom_y":                   row["zoom_y"],
                "recolored":                json.loads(row["recolored"]),    # if stored as JSON string
                "rotated_90":               bool(row["rotated_90"]),
                "rotated_180":              bool(row["rotated_180"]),
                "rotated_270":              bool(row["rotated_270"]),
                "flipped_vert":             bool(row["flipped_vert"]),
                "flipped_horiz":            bool(row["flipped_horiz"]),
                "flipped_vert_90":          bool(row["flipped_vert_90"]),
                "flipped_horiz_90":         bool(row["flipped_horiz_90"])
            })

        return list(grouped.values())

    def _build_function(self, row):
        trainId = row["trainId"]
        sub_sprites_info = row["sub_sprites"]

        # 1) Start with a large shrinkable canvas (30×30 of -1)
        mask_sprite = makeShrinkableCanvas()

        # 2) Paint each sub‐sprite onto the mask
        painted = mask_sprite
        sprite_grids = []
        for sub in sub_sprites_info:
            grid = to_concrete_grid(json.loads(sub["sprite_data"]))
            grid = tuple(tuple(cell for cell in row) for row in grid)
            x, y = sub["x"], sub["y"]
            painted = paint(painted, grid, (y, x))
            sprite_grids.append(grid)

        painted = shrinkCanvas(painted)
        #print(f"[ painted: {painted} ]")

        # 3) Build ArgumentBindings for sub_sprites, including suggested_transform
        sub_bindings = []
        for idx, sub in enumerate(sub_sprites_info):
            # pack the transform spec
            transform_spec = {
                "zoom_x":          sub.get("zoom_x", sub.get("zoomX", 1)),
                "zoom_y":          sub.get("zoom_y", sub.get("zoomY", 1)),
                "recolored":       sub.get("recolored", []),
                "rotated_90":      bool(sub.get("rotated_90", 0)),
                "rotated_180":     bool(sub.get("rotated_180", 0)),
                "rotated_270":     bool(sub.get("rotated_270", 0)),
                "flipped_vert":    bool(sub.get("flipped_vert", 0)),
                "flipped_horiz":   bool(sub.get("flipped_horiz", 0)),
                "flipped_vert_90": bool(sub.get("flipped_vert_90", 0)),
                "flipped_horiz_90":bool(sub.get("flipped_horiz_90", 0)),
            }

            origin_id = sub.get("sprite_origin_id")
            binding_kwargs = {
                "name":               f"sprite_{idx}",
                "type":               "Grid",
                "binding":            BindingStatus.UNRESOLVED,
                "value":              sprite_grids[idx],
                "suggested_action":   "selectSpriteGridAction" if origin_id is not None else None,
                "suggested_sprite_id": origin_id,
                "suggested_transform": transform_spec
            }
            sub_bindings.append(ArgumentBinding(**binding_kwargs))

        # 4) Build position bindings as before
        position_bindings = []
        for idx, sub in enumerate(sub_sprites_info):
            x, y = sub["x"], sub["y"]
            coord_binding = ArgumentBinding(
                name=f"coord_{idx}",
                type="Coord",
                binding=BindingStatus.COMPOUND,
                sub_bindings={
                    "x": ArgumentBinding(name="x", type="Integer",
                                         binding=BindingStatus.UNRESOLVED, value=x),
                    "y": ArgumentBinding(name="y", type="Integer",
                                         binding=BindingStatus.UNRESOLVED, value=y),
                },
                sub_bindings_length_status=BindingStatus.CONSTANT,
                sub_bindings_length_value=2
            )
            position_bindings.append(coord_binding)

        bg_color_bindings = []
        for idx, sub in enumerate(sub_sprites_info):
            color = sub.get("sprite_origin_bg", -1)
            origin_id = sub.get("sprite_origin_id")

            bg_color_bindings.append(ArgumentBinding(
                name=f"bg_color_{idx}",
                type="Integer",
                binding=BindingStatus.UNRESOLVED,
                value=color,
                suggested_action="selectSpriteAndAttributeAction" if origin_id is not None else None,
                suggested_sprite_id=origin_id,
                suggested_attribute="bgColor",
                suggested_default=0
            ))

        # 5) Return the composition ActionInstance
        return ActionInstance(
            id=f"sprite_composition_{trainId}_{row['sprite_id']}#{getUniqueId()}",
            action=self.action,
            bindings={
                "sub_sprites": ArgumentBinding(
                    name="sub_sprites",
                    type="Array<Grid>",
                    binding=BindingStatus.COMPOUND,
                    sub_bindings=sub_bindings,
                    sub_bindings_length_status=BindingStatus.CONSTANT,
                    sub_bindings_length_value=len(sub_bindings)
                ),
                "positions": ArgumentBinding(
                    name="positions",
                    type="Array<Coord>",
                    binding=BindingStatus.COMPOUND,
                    sub_bindings=position_bindings,
                    sub_bindings_length_status=BindingStatus.CONSTANT,
                    sub_bindings_length_value=len(position_bindings)
                ),
                "bg_colors": ArgumentBinding(
                    name="bg_colors",
                    type="Array<Integer>",
                    binding=BindingStatus.COMPOUND,
                    sub_bindings=bg_color_bindings,
                    sub_bindings_length_status=BindingStatus.CONSTANT,
                    sub_bindings_length_value=len(bg_color_bindings)
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
        #print("[ DenoiseFactToAction ] _build_function")
        input_grid = json.loads(row["input_grid"])
        noise_list = json.loads(row["noise_map"])  # [[i,j,color], ...]
        noise_map = {(i, j): color for i, j, color in noise_list}
        output_grid = json.loads(row["output_grid"])

        #print(f"[ DenoiseFactToAction ] input_grid : {grid_to_pretty_string(input_grid)}")
        #print(f"[ DenoiseFactToAction ] output_grid : {grid_to_pretty_string(output_grid)}")

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

class FixSymmetryFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("fix_symmetry", "fix_symmetry")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn):
        #print("\n🔍 Running FixSymmetryFactToAction._test_function")
        results = []
        skipped = []
        for trainId, grid in TRAIN_INPUT_GRIDS.items():
            #print(f"  ▶️ Checking trainId={trainId}")
            h = len(grid)
            w = len(grid[0]) if h else 0
            #print(f"    Grid size: {h}x{w}")
            if h < 10 or w < 10:
                #print("    ⚠️ Grid too small (<10x10), skipping")
                skipped.append(trainId)
                continue
            sym_rows = sum(all(row[j] == row[w-1-j] for j in range(w)) for row in grid)
            sym_cols = sum(all(grid[i][j] == grid[h-1-i][j] for i in range(h)) for j in range(w))
            pct_rows, pct_cols = sym_rows / h, sym_cols / w
            #print(f"    Symmetric rows: {sym_rows}/{h} ({pct_rows:.2%}), cols: {sym_cols}/{w} ({pct_cols:.2%})")
            isH, isV = pct_rows >= 0.75, pct_cols >= 0.75
            #print(f"    Detected isH={isH}, isV={isV}")
            if not (isH or isV):
                #print("    ❌ Neither symmetry meets threshold, skipping")
                skipped.append(trainId)
                continue

            holes_H = []
            holes_V = []
            if isH:
                holes_H = [(i, j) for i in range(h) for j in range(w) if grid[i][j] != grid[i][w-1-j]]
            if isV:
                holes_V = [(i, j) for i in range(h) for j in range(w) if grid[i][j] != grid[h-1-i][j]]
            merged_holes = holes_H + holes_V
            # 2. Gather the pixel values at those coordinates
            colors = [grid[i][j] for (i, j) in merged_holes]
            # 3. Count frequencies and pick the most common
            color_counts = Counter(colors)
            mode_color, mode_count = color_counts.most_common(1)[0]
            #print(f"Most frequent hole‐color is {mode_color} (appears {mode_count} times)")
            filtered_holes = [
                (i, j)
                for (i, j) in merged_holes
                if grid[i][j] == mode_color
            ]

            #print(f"Filtered holes (only color={mode_color}): {filtered_holes}")

            if not filtered_holes:
                #print("    ⚠️ No holes to fix after filtering, skipping")
                skipped.append(trainId)
                continue
            axeX, axeY = (w-1)/2, (h-1)/2
            results.append({
                "sprite_unique_id": None,
                "trainId": trainId,
                "testId": -1,
                "isHorizontal": int(isH),
                "isVertical":   int(isV),
                "axeX": axeX,
                "axeY": axeY,
                "Holes": filtered_holes
            })
            #print(f"    ✅ Appended symmetry fix task for trainId={trainId}")
        if skipped:
            return []
        return results

    def _build_function(self, row):
        trainId = row["trainId"]
        testId = row["testId"]
        scenarioId = row["scenarioId"]
        #print(f"\n🔧 Running FixSymmetryFactToAction._build_function for trainId={trainId}")
        grid = TRAIN_INPUT_GRIDS[trainId]
        holes = row["Holes"]
        #print("    Original grid:")
        #print(grid_to_pretty_string(grid))
        fixed = apply_symmetry_fill(grid, row['isHorizontal'], row['isVertical'], holes)
        #print("   🔄 Resulting filled grid:")
        #print(grid_to_pretty_string(fixed))
        sprites = extract_connected_components(fixed, holes)
        #print(f"    🆕 NEW_SPRITES count={len(sprites)}")
        #for idx, sp in enumerate(sprites):
        #    print(f"      🖼️ Sprite[{idx}]:")
        #    print(grid_to_pretty_string(sp))
        inst = ActionInstance(
            id=f"fix_symmetry_{trainId}#{getUniqueId()}",
            action=registry.get_by_id("fix_symmetry"),
            bindings={
                "grid":       ArgumentBinding(name="grid",       type="Grid", binding=BindingStatus.INPUT_GRID, value=grid),
                "scenarioId": ArgumentBinding(name="scenarioId", type="String", binding=BindingStatus.INSTANCE, value=scenarioId),
                "trainId":    ArgumentBinding(name="trainId",    type="Integer", binding=BindingStatus.CONTEXT, value=trainId),
                "testId":     ArgumentBinding(name="testId",     type="Integer", binding=BindingStatus.CONTEXT, value=testId),
            },
            output_var="fixed_grid",
            output_type="Grid",
            output_value=fixed,
            scenarioId=row.get("scenarioId"),
            ruleId=row.get("ruleId"),
            trainId=trainId,
            testId=-1,
            isTrain=True,
            isToOutput=True
        )
        inst.IN_SEPARATE_RULE = True
        inst.NEW_SPRITES = sprites
        #print(f"    📦 Generated ActionInstance with NEW_SPRITES={sprites}")
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
          AND outp.pixelCount > 3
          AND zoom_x < 6
          AND zoom_y < 6
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
            if zoom(out_grid, zx, zy) == inp_grid:
                valid.append(r)

        return valid

    def _build_function(self, row: dict) -> ActionInstance:

        # Parse grids and factors
        input_grid = to_concrete_grid(json.loads(row["input_data"]))
        output_grid = to_concrete_grid(json.loads(row["output_data"]))
        zx = int(row["zoom_x"])
        zy = int(row["zoom_y"])

        #print("[ Zoom Out build ]")
        #print("input_grid")
        #print(grid_to_pretty_string(input_grid))
        #print("output_grid")
        #print(grid_to_pretty_string(output_grid))

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
            [-5 if (min_r + y, min_c + x) in coords_set else -1
             for x in range(width)]
            for y in range(height)
        ]
        mask_grid: Grid = tuple(tuple(row) for row in mask_grid_list)

        # Build output grid: replace -8 with color, keep -1 as background
        color = row["color"]
        output_grid: Grid = fill_grid(mask_grid,color)

        #print(f" [ CreateObjectFactToAction ] color: {color}")
        #print(f"mask_grid")
        #print(grid_to_pretty_string(mask_grid))
        #print(f"output_grid")
        #print(grid_to_pretty_string(output_grid))

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

class MoveObjectFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("move_object", "move_object", "isMoved")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT
          oa.id AS object_id,
          oa.trainId,
          oa.testId,
          oa.color AS color,
          oa.minX AS patch_min_x,
          oa.minY AS patch_min_y,
          oa.moveRelX AS move_rel_x,
          oa.moveRelY AS move_rel_y,          
          oa.newPosX AS new_pos_x,
          oa.newPosY AS new_pos_y,
          oa.moveBehindColor AS background_color,
          oa.width,
          oa.height,
          oa.data
        FROM object_analysis AS oa
        WHERE oa.isMoved = 1
          AND oa.isInsideInput = 1
          AND oa.isRotatedOrFlipped = 0
          AND oa.isRecolored = 0
          AND oa.isZoomed = 0
        """
        cursor = conn.execute(query)
        cols = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def _build_function(self, row: dict) -> ActionInstance:
        # Offsets and colors
        object_color = int(row["color"])
        bg_color = int(row.get("background_color", 0))
        move_rel_x = int(row["move_rel_x"])
        move_rel_y = int(row["move_rel_y"])

        # Patch bounding box
        patch_min_x = int(row["patch_min_x"])
        patch_min_y = int(row["patch_min_y"])
        new_pos_x = int(row["new_pos_x"])
        new_pos_y = int(row["new_pos_y"])
        patch_w = int(row["width"])
        patch_h = int(row["height"])

        if bg_color == -1:
            move_rel_x = 0
            move_rel_y = 0
            patch_min_x = 0
            patch_min_y = 0

        # now extract the patch, anonymizing everything that isn't the object:
        coords: list[list[int]] = json.loads(row["data"])
        patch_grid = [[-1 for _ in range(patch_w)] for __ in range(patch_h)]
        for i_off, j_off in coords:
            # guard in case data contains out-of-bounds:
            if 0 <= i_off < patch_h and 0 <= j_off < patch_w:
                patch_grid[i_off][j_off] = object_color
        patch = tuple(tuple(r) for r in patch_grid)

        # Create anonymized output grid
        base_output = TRAIN_OUTPUT_GRIDS[row["trainId"]]
        rows_out = len(base_output)
        cols_out = len(base_output[0]) if rows_out else 0
        anon_grid = tuple(tuple(-8 for _ in range(cols_out)) for _ in range(rows_out))

        # Perform shift, producing updated_grid
        updated_grid = shift_with_background(
            anon_grid,
            patch,
            patch_min_x,
            patch_min_y,
            move_rel_x,
            move_rel_y,
            new_pos_x,
            new_pos_y,
            object_color,
            bg_color
        )

        #print("MoveObjectFactToAction")
        #print(grid_to_pretty_string(updated_grid))

        action = registry.get_by_id(self.action_id)
        # Bind all 8 parameters as UNRESOLVED
        bindings = {
            "grid": ArgumentBinding(
                name="grid", type="Grid",
                binding=BindingStatus.UNRESOLVED, value=anon_grid
            ),
            "patch": ArgumentBinding(
                name="patch", type="Grid",
                binding=BindingStatus.UNRESOLVED, value=patch, use_anonymized=False,
                suggested_action="selectObjectGridAction", suggested_object_id=row["object_id"]
            ),
            "new_pos_x": ArgumentBinding(
                name="new_pos_x", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=new_pos_x
            ),
            "new_pos_y": ArgumentBinding(
                name="new_pos_y", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=new_pos_y
            ),
            "object_color": ArgumentBinding(
                name="object_color", type="Color",
                binding=BindingStatus.UNRESOLVED, value=object_color
            ),
            "background_color": ArgumentBinding(
                name="background_color", type="Color",
                binding=BindingStatus.UNRESOLVED, value=bg_color
            ),
        }

        if bg_color == -1:
            # constant bindings for patch coordinates
            bindings["patch_min_x"] = ArgumentBinding(
                name="patch_min_x", type="Integer",
                binding=BindingStatus.CONSTANT, value=patch_min_x
            )
            bindings["patch_min_y"] = ArgumentBinding(
                name="patch_min_y", type="Integer",
                binding=BindingStatus.CONSTANT, value=patch_min_y
            )
            bindings["move_rel_x"] = ArgumentBinding(
                name="move_rel_x", type="Integer",
                binding=BindingStatus.CONSTANT, value=move_rel_x
            )
            bindings["move_rel_y"] = ArgumentBinding(
                name="move_rel_y", type="Integer",
                binding=BindingStatus.CONSTANT, value=move_rel_y
            )
        else:
            # unresolved with suggestions
            bindings["patch_min_x"] = ArgumentBinding(
                name="patch_min_x", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=patch_min_x,
                suggested_action="selectObjectAndAttributeAction",
                suggested_object_id=row["object_id"], suggested_attribute="minX"
            )
            bindings["patch_min_y"] = ArgumentBinding(
                name="patch_min_y", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=patch_min_y,
                suggested_action="selectObjectAndAttributeAction",
                suggested_object_id=row["object_id"], suggested_attribute="minY"
            )
            bindings["move_rel_x"] = ArgumentBinding(
                name="move_rel_x", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=move_rel_x
            )
            bindings["move_rel_y"] = ArgumentBinding(
                name="move_rel_y", type="Integer",
                binding=BindingStatus.UNRESOLVED, value=move_rel_y
            )

        return ActionInstance(
            id=f"move_object_{row['object_id']}#{getUniqueId()}",
            action=action,
            bindings=bindings,
            output_var="updated_grid",
            output_value=updated_grid,
            output_type=action.output_type,
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True,
            END=False
        )

class MoveSpriteFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("move_sprite", "move_sprite", "isMoved")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        query = """
        SELECT
          sa.id               AS sprite_id,
          sa.trainId,
          sa.testId,
          sa.bgColor          AS color,
          sa.minX             AS patch_min_x,
          sa.minY             AS patch_min_y,
          sa.moveRelX         AS move_rel_x,
          sa.moveRelY         AS move_rel_y,
          sa.newPosX          AS new_pos_x,
          sa.newPosY          AS new_pos_y,
          sa.moveBehindColor  AS background_color,
          sa.width,
          sa.height,
          sa.data
        FROM sprite_analysis AS sa
        WHERE sa.isMoved = 1
          AND sa.isInsideInput = 1
          AND sa.isRotatedOrFlipped = 0
          AND sa.isRecolored = 0
          AND sa.isZoomed = 0
        """
        cursor = conn.execute(query)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # 1) If no moved sprites at all, bail out immediately
        if not rows:
            return []

        # 2) FILTER OUT any box that is strictly contained by a larger one
        def box_contains(outer, inner):
            # treat coordinates as half-open: [minX, minX+width)
            ox1, oy1 = outer["patch_min_x"], outer["patch_min_y"]
            ow, oh = outer["width"], outer["height"]
            ix1, iy1 = inner["patch_min_x"], inner["patch_min_y"]
            iw, ih = inner["width"], inner["height"]

            return (
                    ix1 >= ox1 and
                    iy1 >= oy1 and
                    ix1 + iw <= ox1 + ow and
                    iy1 + ih <= oy1 + oh and
                    # strictly smaller in area so identical boxes aren’t dropped
                    (iw * ih) < (ow * oh)
            )

        filtered = []
        # group by trainId and testId so we only compare boxes within same scenario
        keyfunc = lambda r: (r["trainId"], r["testId"])
        for _, group in itertools.groupby(sorted(rows, key=keyfunc), key=keyfunc):
            group = list(group)
            for r in group:
                # keep r only if no other box contains it
                if not any(box_contains(other, r) for other in group if other is not r):
                    filtered.append(r)
        rows = filtered

        # 3) Which trainIds still saw a move?
        train_rows = [r for r in rows if r["testId"] == -1]
        found_tids = {r["trainId"] for r in train_rows}

        # 4) All expected trainIds from TRAIN_INPUT_GRIDS
        expected_tids = set(TRAIN_INPUT_GRIDS.keys())

        # 5) Only proceed if every trainId is covered
        if found_tids != expected_tids:
            return []

        return rows

    def _build_function(self, row: dict) -> ActionInstance:
        # Core parameters
        bg_color     = int(row.get("background_color", 0))
        move_rel_x   = int(row["move_rel_x"])
        move_rel_y   = int(row["move_rel_y"])

        patch_min_x  = int(row["patch_min_x"])
        patch_min_y  = int(row["patch_min_y"])
        new_pos_x    = int(row["new_pos_x"])
        new_pos_y    = int(row["new_pos_y"])
        patch_w      = int(row["width"])
        patch_h      = int(row["height"])

        # if bg is missing, reset shift to zero (no valid backing)
        if bg_color == -1:
            move_rel_x = move_rel_y = 0
            patch_min_x = patch_min_y = 0

        coords = json.loads(row["data"])  # e.g. [[4,[3,1]], [0,[4,4]], …]
        patch_w = int(row["width"])
        patch_h = int(row["height"])

        # initialize an empty patch
        patch_grid = [[-1 for _ in range(patch_w)] for __ in range(patch_h)]
        for color, (dy, dx) in coords:
            # only fill valid coords
            if 0 <= dy < patch_h and 0 <= dx < patch_w:
                patch_grid[dy][dx] = int(color)

        # freeze into tuples
        patch = tuple(tuple(r) for r in patch_grid)

        #print("MoveSpriteFactToAction")
        #print("patch")
        #print(grid_to_pretty_string(patch))

        # prepare anonymized output canvas
        base_output = TRAIN_OUTPUT_GRIDS[row["trainId"]]
        rows_out = len(base_output)
        cols_out = len(base_output[0]) if rows_out else 0
        anon_grid = tuple(tuple(-8 for _ in range(cols_out)) for _ in range(rows_out))

        #print("anon_grid")
        #print(grid_to_pretty_string(anon_grid))

        # shift with background color
        updated_grid = shift_sprite_with_background(
            patch,
            patch_min_x,
            patch_min_y,
            move_rel_x,
            move_rel_y,
            new_pos_x,
            new_pos_y,
            background_color=bg_color,
            grid=anon_grid
        )

        #print("updated_grid")
        #print(grid_to_pretty_string(updated_grid))

        # Create bindings
        bindings = {}

        # Only add `grid` binding if grid size != patch size
        if (rows_out, cols_out) != (patch_h, patch_w):
            bindings["grid"] = ArgumentBinding("grid", "Grid", binding=BindingStatus.UNRESOLVED, value=anon_grid)

        bindings["patch"] = ArgumentBinding(
            "patch", "Grid", binding=BindingStatus.UNRESOLVED,
            value=patch, use_anonymized=False,
            suggested_action="selectSpriteGridAction",
            suggested_sprite_id=row["sprite_id"]
        )
        bindings["new_pos_x"] = ArgumentBinding("new_pos_x", "Integer", binding=BindingStatus.UNRESOLVED, value=new_pos_x)
        bindings["new_pos_y"] = ArgumentBinding("new_pos_y", "Integer", binding=BindingStatus.UNRESOLVED, value=new_pos_y)
        bindings["background_color"] = ArgumentBinding("background_color", "Color", binding=BindingStatus.UNRESOLVED, value=bg_color)

        if bg_color == -1:
            # for missing bg, make shift constants
            bindings["patch_min_x"] = ArgumentBinding("patch_min_x", "Integer", binding=BindingStatus.CONSTANT, value=patch_min_x)
            bindings["patch_min_y"] = ArgumentBinding("patch_min_y", "Integer", binding=BindingStatus.CONSTANT, value=patch_min_y)
            bindings["move_rel_x"]  = ArgumentBinding("move_rel_x",  "Integer", binding=BindingStatus.CONSTANT, value=move_rel_x)
            bindings["move_rel_y"]  = ArgumentBinding("move_rel_y",  "Integer", binding=BindingStatus.CONSTANT, value=move_rel_y)
        else:
            bindings["patch_min_x"] = ArgumentBinding(
                "patch_min_x", "Integer", binding=BindingStatus.UNRESOLVED, value=patch_min_x,
                suggested_action="selectSpriteAndAttributeAction",
                suggested_sprite_id=row["sprite_id"], suggested_attribute="minX"
            )
            bindings["patch_min_y"] = ArgumentBinding(
                "patch_min_y", "Integer", binding=BindingStatus.UNRESOLVED, value=patch_min_y,
                suggested_action="selectSpriteAndAttributeAction",
                suggested_sprite_id=row["sprite_id"], suggested_attribute="minY"
            )
            bindings["move_rel_x"]  = ArgumentBinding("move_rel_x", "Integer", binding=BindingStatus.UNRESOLVED, value=move_rel_x)
            bindings["move_rel_y"]  = ArgumentBinding("move_rel_y", "Integer", binding=BindingStatus.UNRESOLVED, value=move_rel_y)

        action = registry.get_by_id(self.action_id)
        return ActionInstance(
            id=f"move_sprite_{row['sprite_id']}#{getUniqueId()}",
            action=action,
            bindings=bindings,
            output_var="updated_grid",
            output_value=updated_grid,
            output_type=action.output_type,
            trainId=row["trainId"],
            testId=row["testId"],
            isTrain=(row["trainId"] != -1),
            isToOutput=True,
            END=False
        )

class LightCycleFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("apply_light_cycles", "apply_light_cycles")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        """
        Return one fact row per trainId (from TRAIN_INPUT_GRIDS), each containing:
          - trainId
          - testId = -1
          - lightCycles: a Python list of dicts, where
              * pixel_rel is a Python list of [color, [dx,dy]]
              * common_neighbors and common_rowcol values are frozensets of ints
        """
        cursor = conn.execute("SELECT * FROM light_cycle")
        cols = [d[0] for d in cursor.description]
        raw_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # We now post‐process each raw row so that:
        #  - row["pixel_rel"]    (a JSON string) → a Python list
        #  - each "colors_at_*"  (a JSON string) → frozenset(ints)
        #  - each "colors_in_*"  (a JSON string) → frozenset(ints)
        #  - We only keep the keys you actually need (id, light_cycle_id, action, etc.)
        #
        # In your example, the fields we want to convert are:
        #     pixel_rel,
        #     colors_at_north, colors_at_north_east, …, colors_at_north_west,
        #     colors_in_next_row, colors_in_previous_row, colors_in_next_col, colors_in_previous_col,
        #     color, direction_x, direction_y, order_idx, action
        #
        # Everything else can be dropped (or left as default), but we’ll reconstruct exactly the dict shape you showed.

        def parse_one(row: dict) -> dict:
            out = {}
            # copy over simple scalar fields
            out["id"] = row["id"]
            out["light_cycle_id"] = row["light_cycle_id"]
            out["action"] = row["action"]
            out["direction_x"] = row["direction_x"]
            out["direction_y"] = row["direction_y"]
            out["color"] = row["color"]
            out["order_idx"] = row["order_idx"]

            # 1) pixel_rel: originally stored as a JSON‐string in the SQL table
            #    Example: "[[-2, [-1, -1]], [-2, [0, -1]], …]"
            #    We want out["pixel_rel"] to be a Python list, e.g.
            #       [[-2, [-1,-1]], [-2, [0,-1]], …]
            try:
                out["pixel_rel"] = json.loads(row["pixel_rel"])
            except (TypeError, json.JSONDecodeError):
                # If pixel_rel was NULL or not a valid JSON string, fallback to empty list
                out["pixel_rel"] = []

            # 2) common_neighbors: each direction was stored under its own column as a JSON‐string.
            #    We want a nested dict of frozensets:
            #       "common_neighbors": {
            #           "north":       frozenset([...]),
            #           "north_east":  frozenset([...]),
            #            …,
            #           "north_west":  frozenset([...])
            #       }
            cn = {}
            for key in [
                "colors_at_north",
                "colors_at_north_east",
                "colors_at_east",
                "colors_at_south_east",
                "colors_at_south",
                "colors_at_south_west",
                "colors_at_west",
                "colors_at_north_west"
            ]:
                raw = row.get(key, "[]")
                try:
                    lst = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    lst = []
                # store under the shorter direction name, e.g. "north"
                dir_name = key.replace("colors_at_", "")
                cn[dir_name] = frozenset(lst)
            out["common_neighbors"] = cn

            # 3) common_rowcol: same idea, four columns of JSON‐strings
            crc = {}
            for key in [
                "colors_in_next_row",
                "colors_in_previous_row",
                "colors_in_next_col",
                "colors_in_previous_col"
            ]:
                raw = row.get(key, "[]")
                try:
                    lst = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    lst = []
                # shorten the key, e.g. "next_row"
                short = key.replace("colors_in_", "")
                crc[short] = frozenset(lst)
            out["common_rowcol"] = crc

            return out

        all_light_cycles: List[dict] = [parse_one(r) for r in raw_rows]

        # Finally, build one result‐dict per trainId
        results: List[dict] = []
        for train_id in TRAIN_INPUT_GRIDS.keys():
            results.append({
                "trainId": train_id,
                "testId": -1,
                # We want `lightCycles` to be a Python list, not a JSON‐string.
                # So we pass the list of dicts directly (the framework will serialize if needed).
                "lightCycles": all_light_cycles
            })

        return results

    def _build_function(self, row: dict) -> ActionInstance:
        """
        Given a fact row with keys 'trainId', 'testId', and 'lightCycles' (JSON string),
        bind:
          - input_grid: from TRAIN_INPUT_GRIDS[trainId]
          - light_cycles: the parsed list of all cycle rows
        Compute output_value by applying those cycles to input_grid.
        """
        train_id = row["trainId"]
        test_id = row["testId"]
        light_cycles = row["lightCycles"]  # list of dicts

        # 1) Retrieve the input grid directly from the global dictionary
        input_grid = TRAIN_INPUT_GRIDS[train_id]

        # 2) Apply all light cycles to produce the final grid
        output_grid = apply_all_cycles(input_grid, light_cycles)

        #if train_id == 0 :
        #    print(f"light cycles: ")
        #    print(light_cycles)

        #print(f"light cycle output_grid for train_id: {train_id}")
        #print(grid_to_pretty_string(output_grid))

        # 3) Build argument bindings
        action_template = registry.get_by_id(self.action_id)
        bindings = {
            "input_grid": ArgumentBinding(
                name="input_grid",
                type="Grid",
                binding=BindingStatus.INPUT_GRID,
                value=input_grid
            ),
            "light_cycles": ArgumentBinding(
                name="light_cycles",
                type="List",
                binding=BindingStatus.CONSTANT,
                value=light_cycles
            )
        }

        # 4) Construct and return the ActionInstance
        return ActionInstance(
            id=f"{self.action_id}_{train_id}#{getUniqueId()}",
            action=action_template,
            bindings=bindings,
            output_var="result_grid",
            output_value=output_grid,
            output_type="Grid",
            scenarioId=row["scenarioId"],
            ruleId=row["ruleId"],
            trainId=train_id,
            testId=test_id,
            isTrain=True,
            isToOutput=True,
            END=False
        )

class CellularAutomatonFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("apply_cellular_automaton", "apply_cellular_automaton")
        self.test_function = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> List[dict]:
        cur = conn.execute("SELECT id, input_color, output_color, wildcard_colors, tick FROM cellular_automaton")
        rules_raw = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        ca_rules: List[Dict] = []
        for rw in rules_raw:
            rid = rw['id']
            cur = conn.execute("SELECT posRelX, posRelY, color, output FROM cellular_automaton_cells WHERE rule_id=?",(rid,))
            neighbors = [(dx, dy, color, output) for dx, dy, color, output in cur.fetchall()]
            ca_rules.append({
                'input_color': rw['input_color'],
                'output_color': rw['output_color'],
                'wildcard_colors': rw['wildcard_colors'],
                'tick': rw['tick'],
                'neighbors': neighbors
            })
        results: List[dict] = []
        for train_id in TRAIN_INPUT_GRIDS.keys():
            results.append({'trainId': train_id, 'testId': -1, 'ca_rules': ca_rules})
        return results

    def _build_function(self, row: dict) -> ActionInstance:
        train_id = row['trainId']
        test_id = row.get('testId', -1)
        ca_rules = row.get('ca_rules', [])
        input_grid = TRAIN_INPUT_GRIDS[train_id]
        output_grid = apply_cellular_automaton(input_grid, ca_rules)

        print("fact apply_ca")
        print(grid_to_pretty_string(output_grid))

        action = registry.get_by_id(self.action_id)
        bindings = {
            'input_grid': ArgumentBinding('input_grid','Grid',BindingStatus.INPUT_GRID,input_grid),
            'ca_rules': ArgumentBinding('ca_rules','List',BindingStatus.CONSTANT,ca_rules)
        }
        return ActionInstance(
            id=f"{self.action_id}_{train_id}#{getUniqueId()}",
            action=action,
            bindings=bindings,
            output_var='result_grid',
            output_value=output_grid,
            output_type='Grid',
            scenarioId=row.get('scenarioId'),
            ruleId=row.get('ruleId'),
            trainId=train_id,
            testId=test_id,
            isTrain=True,
            isToOutput=True,
            END=False
        )

class ConditionalObjectFactToAction(FactToActionMapping):
    def __init__(self):
        super().__init__("conditional_objects", "conditional_objects")
        self.test_function  = self._test_function
        self.build_function = self._build_function

    def _test_function(self, conn: sqlite3.Connection) -> list[dict]:
        """
        Use the in-memory tables (current_rule.tables) rather than SQL.
        Returns one fact‐row per trainId with key 'conditionalObjects' = list of dicts.
        """
        # grab all four tables
        tables = self.current_rule.tables
        sc_tbl = tables["shape_conditional"]        # {id: { ... }}
        so_tbl = tables["shape_occurrence"]
        sh_tbl = tables["shape"]
        st_tbl = tables["shape_transformation"]

        # collect one conditional‐object row per (sc, occurrence)
        all_conds = []
        for sc_id, sc in sc_tbl.items():
            # parse criteria JSON once
            sc_color = sc.get("color")
            crit_fsa = json.loads(sc["criteria_first_sight"] or "[]")
            crit_ssg = json.loads(sc["criteria_sprite_grid"] or "[]")
            else_tid = sc.get("else_transformation_id")

            # find all matching occurrences
            for so in so_tbl.values():
                if (so["shape_transformation_id"] != sc["shape_transformation_id"]
                    or so["isInsideOutput"] != 1
                    or so["isInsideTrain"]  != 1
                    or so["testId"]         != -1):
                    continue

                trainId = so["trainId"]
                testId  = so["testId"]

                # find the corresponding shape row
                sh = next(
                    row for row in sh_tbl.values()
                    if (row["id"]==sc["shape_id"])
                )
                obj_data = json.loads(sh["data"])

                # transformation flags
                st = st_tbl[sc["shape_transformation_id"]]

                fact = {
                    "id":                        sc_id,
                    "color":                     sc_color,
                    "criteria_first_sight":      crit_fsa,
                    "criteria_sprite_grid":      crit_ssg,
                    "else_transformation_id":    else_tid,
                    "trainId":                   trainId,
                    "testId":                    testId,
                    "object_data":               obj_data,
                    "rotated_90":                bool(st["rotated_90"]),
                    "rotated_180":               bool(st["rotated_180"]),
                    "rotated_270":               bool(st["rotated_270"]),
                    "flipped_vert":              bool(st["flipped_vert"]),
                    "flipped_horiz":             bool(st["flipped_horiz"]),
                    "flipped_vert_90":           bool(st["flipped_vert_90"]),
                    "flipped_horiz_90":          bool(st["flipped_horiz_90"]),
                    "zoom_x":                    st["zoom_x"],
                    "zoom_y":                    st["zoom_y"]
                }
                all_conds.append(fact)

        # assemble one result per train
        results = []
        for trainId in TRAIN_INPUT_GRIDS:
            results.append({
                "trainId":            trainId,
                "testId":             -1,
                "conditionalObjects": all_conds
            })
        #print("ConditionalObjectFactToAction Test results:")
        #print(results)
        return results

    def _build_function(self, row: dict) -> ActionInstance:
        """
        Binds:
          - input_grid
          - conditionalObjects
        Calls select_conditional_object(trainId,testId,candidates) to compute output_value.
        """
        trainId    = row["trainId"]
        testId     = row["testId"]
        conditionalObjects = row["conditionalObjects"]

        # bind the actual input grid
        input_grid = TRAIN_INPUT_GRIDS[trainId]

        # select best object by criteria
        output_grid = select_conditional_object(trainId, testId, conditionalObjects, self.current_rule.tables)
        #print("select_conditional_object")
        #print(grid_to_pretty_string(output_grid))

        bindings = {
            "trainId": ArgumentBinding(name="trainId", type="Integer", binding=BindingStatus.CONTEXT, value=trainId),
            "testId": ArgumentBinding(name="testId", type="Integer", binding=BindingStatus.CONTEXT, value=testId),
            "tables": ArgumentBinding(
                name="tables",
                type="Table",
                binding=BindingStatus.CONSTANT,
                value=self.current_rule.tables
            ),
            "conditionalObjects": ArgumentBinding(
                name="conditionalObjects",
                type="Table",
                binding=BindingStatus.CONSTANT,
                value=conditionalObjects
            )
        }

        return ActionInstance(
            id=f"conditional_objects_{trainId}#{getUniqueId()}",
            action=registry.get_by_id(self.action_id),
            bindings=bindings,
            output_var="result_object",
            output_value=output_grid,
            output_type="Grid",
            scenarioId=row.get("scenarioId"),
            ruleId=row.get("ruleId"),
            trainId=trainId,
            testId=testId,
            isTrain=True,
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
    CanvasByObjectSizeFactToAction(),
    RecolorSpriteFactToAction(),
    SpriteComputationFactToAction(),
    DenoiseFactToAction(),
    ZoomOutFactToAction(),
    CreateObjectFactToAction(),
    MoveObjectFactToAction(),
    MoveSpriteFactToAction(),
    CropSpriteFactToAction(),
    FixSymmetryFactToAction(),
    LightCycleFactToAction(),
    CellularAutomatonFactToAction(),
    ConditionalObjectFactToAction(),
]
