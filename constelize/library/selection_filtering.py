from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding, BindingStatus, Producer, ProduceValue, ProduceDict, ProduceList
from typing import Callable, FrozenSet, Any, Dict, List, Optional, Tuple


def sfilter(container: Any, condition: Callable) -> Any:
    return type(container)(e for e in container if condition(e))

def mfilter(container: Any, condition: Callable) -> FrozenSet:
    return frozenset(e for e in container if condition(e))

def extract(container: Any, condition: Callable) -> Any:
    return next((e for e in container if condition(e)), None)

def sizefilter(container: Any, n: int) -> FrozenSet:
    return frozenset(item for item in container if len(item) == n)

def colorfilter(objs: FrozenSet, value: int) -> FrozenSet:
    return frozenset(obj for obj in objs if next(iter(obj))[0] == value)

def produce_dict(
    trainId: int,
    testId: int,
    produceObj: Producer,
    tables: Dict[str, Dict[int, Dict[str, Any]]],
) -> Any:
    """
    Recursively walk the Producer tree, applying only SelectSpriteRowsFunction
    at the root, handling nested ProduceList with recolor logic, ProduceDict
    for repaint_coords, and ProduceValue for both simple attributes and
    coordinate lookup via select_coord().
    """
    table_key = "sprite_analysis"
    print(f"\n=== produce_dict START for trainId={trainId}, testId={testId} ===")

    if trainId == -1:
        print("for test (trainId == -1)")

    # ─── Helpers ─────────────────────────────────────────────────────────
    def select_sprite_rows(
            trainId: int,
            testId: int,
            criteria: List[Tuple[str, Any, int]],  # (column, expected_value, strict_weight)
            tbl: Dict[int, Dict[str, Any]],
            top_k: int | None = None,  # if set, returns up to top_k rows
            require_inside_input: bool = True  # if True, only rows with isInsideOutput==True
    ) -> List[Dict[str, Any]]:
        def weight(attr: str) -> int:
            # tweak these as you like
            if attr in ("isFromSplit", "isFromGlued", "isGrid", "hasBorder"):
                return 20
            if attr in ("nbColors", "colorUniqueOrder"):
                return 10
            if attr in ("sizeOrder", "isColorUnique"):
                return 5
            if attr.startswith("isTouching"):
                return 2
            return 1

        scored: List[Tuple[int, Dict[str, Any]]] = []
        total_possible = sum(weight(col) * w for col, _, w in criteria)

        for rid, row in tbl.items():
            # mandatory filtering by train/test
            if row.get("trainId") != trainId or row.get("testId") != testId:
                continue
            if require_inside_input and not row.get("isInsideInput", False):
                continue

            # compute this row’s score
            score = 0
            for col, expected, strict_w in criteria:
                if row.get(col) == expected:
                    score += weight(col) * strict_w

            if score > 0:
                scored.append((score, row))

        if not scored:
            print("🔍 No rows matched any criterion.")
            return []

        # sort by descending score
        scored.sort(key=lambda x: x[0], reverse=True)
        max_score = scored[0][0]

        # pick either top_k or all at max_score
        if top_k is not None:
            selected = scored[:top_k]
        else:
            selected = [(s, r) for s, r in scored if s == max_score]

        # debug output
        print(f"🔎 select_sprite_rows → trainId={trainId}, testId={testId}")
        print(f"    criteria={criteria}")
        print(f"    total_possible={total_possible}")
        for s, r in selected:
            print(f"    [score={s}] row id={r.get('id', '?')} → {r}")

        return [r for s, r in selected]

    def select_recolor(
        trainId: int,
        spriteId: int,
        criteria: List[tuple],
        tbl: Dict[int, Dict[str, Any]],
        raw_arr: List[int],
        cumulValueMap: Dict[int, List[int]] = None
    ) -> List[Any]:
        print(f"🔎 SelectRecolorFunction → trainId={trainId}, spriteId={spriteId}, criteria={criteria}")
        if cumulValueMap is not None:
            print(f"    cumulValueMap for this producer → {cumulValueMap!r}")
        result: List[Any] = []
        row = tbl.get(spriteId)
        if row is None or row.get('trainId') != trainId:
            print(f"🔍 No row for spriteId={spriteId} or trainId mismatch")
            return result
        for col, val, _ in criteria:
            v = row.get(col)
            print(f"    {col} → {v!r}")
            result.append(v)
        if not result and cumulValueMap:
            fallback: List[Any] = []
            for fr in raw_arr:
                if fr in cumulValueMap:
                    vals = cumulValueMap[fr]
                    print(f"⚠️ fallback add cumulValueMap[{fr}] → {vals}")
                    fallback.extend(vals)
            if fallback:
                return fallback
        print(f"🔍 Recolor values: {result}")
        return result

    def select_coord(
            trainId: int,
            spriteId: int,
            produceMap: Dict[tuple[int, int], List[int]],
            originMap: Dict[tuple[int, int], List[int]],
            criteriaColumn: str,
            row: Dict[str, Any],
    ) -> int | None:

        # ─── Special case: test example ───────────────────────────────
        if trainId == -1:
            base = row.get(criteriaColumn)
            print(f"🔎 select_coord (test) → origin from row[{criteriaColumn}] = {base!r}")

            # collect all train‐side coords for this sprite
            train_keys = [k for k in produceMap.keys()]
            p_lists = [produceMap[k] for k in train_keys]
            o_lists = [originMap.get(k, []) for k in train_keys]

            #print("train_keys")
            #print(train_keys)
            #print("o_lists")
            #print(o_lists)
            #print("p_lists")
            #print(p_lists)

            # 1) exact match across *all* trains?
            if p_lists and o_lists and all(p == o for p, o in zip(p_lists, o_lists)):
                print("    → all trains produce==origin → returning base origin")
                return base

            # 2) constant delta across *all* trains?
            #    (we only look at the first coord of each list here)
            deltas = []
            for p, o in zip(p_lists, o_lists):
                if p and o:
                    deltas.append(p[0] - o[0])
            if deltas and len(set(deltas)) == 1:
                delta = deltas[0]
                new_val = base + delta if base is not None else None
                print(f"    → constant train‐delta {delta}, base={base!r} → {new_val!r}")
                return new_val

            # 3) fallback to raw origin
            print("    → no uniform train pattern → returning base origin")
            return base

        # ─── Otherwise: the original train‐side logic ────────────────
        key = (trainId, spriteId)
        p_coords = produceMap.get(key, [])
        o_coords = originMap.get(key, [])

        print(f"🔎 select_coord → trainId={trainId}, spriteId={spriteId}")
        print(f"    produceMap[{key}] = {p_coords!r}")
        print(f"    originMap[{key}]  = {o_coords!r}")

        # 1) exact match → raw column value
        if p_coords and o_coords and p_coords == o_coords:
            base = row.get(criteriaColumn)
            print(f"    → produce==origin → using row[{criteriaColumn}] = {base!r}")
            return base

        # 2) constant delta → base + Δ
        if p_coords and o_coords:
            deltas = [p - o for p, o in zip(p_coords, o_coords)]
            if len(set(deltas)) == 1:
                delta = deltas[0]
                base = row.get(criteriaColumn)
                new_val = base + delta if base is not None else None
                print(f"    → constant delta {delta}, {criteriaColumn}={base!r} → {new_val!r}")
                return new_val

        # 3) fallback to produce coords
        if p_coords:
            val = p_coords[0]
            print(f"    → fallback produce coords[0] = {val!r}")
            return val

        # 4) fallback to origin coords
        if o_coords:
            val = o_coords[0]
            print(f"    → fallback origin coords[0] = {val!r}")
            return val

        # 5) nothing found
        print(f"    → no coords found → None")
        return None

    # ─── Core evaluator ─────────────────────────────────────────────────

    def eval_producer(prod: Producer, row_context: Optional[Dict[str, Any]] = None, depth: int = 0) -> Any:
        indent = '  ' * depth
        print(f"{indent}-- eval_producer: {type(prod).__name__} --")

        # 1) nested ProduceList (e.g. recolor_maps)
        if isinstance(prod, ProduceList) and row_context is not None and prod.attribute:
            raw_arr = prod.adapter(row_context.get(prod.attribute)) if prod.adapter else row_context.get(prod.attribute)
            print(f"{indent}  [LIST] attribute '{prod.attribute}' → {raw_arr}")
            sprite_id = (
                row_context.get('id')
                or row_context.get('origin_sprite_id')
                or row_context.get('sprite_id')
            )
            to_list = select_recolor(
                trainId,
                sprite_id,
                prod.maps['To'].criteria,
                tables[table_key],
                raw_arr=raw_arr,
                cumulValueMap=prod.maps['To'].cumulValueMap
            )
            print(f"{indent}  [LIST] raw Arr → {raw_arr}, To List → {to_list}")

            if len(to_list) != len(raw_arr):
                valid_keys = set(prod.maps['To'].cumulValueMap.keys())
                raw_arr = [v for v in raw_arr if v in valid_keys]
                print(f"{indent}  [LIST] fallback trim raw_arr → {raw_arr}")

            print(f"{indent}  [LIST] zipped From/To pairs → {list(zip(raw_arr, to_list))}")
            out: List[Dict[str, int]] = []
            for v, to_val in zip(raw_arr, to_list):
                if v is None or to_val is None or v == to_val:
                    print(f"{indent}    skip pair {{'From': {v}, 'To': {to_val}}}")
                    continue
                elem = {'From': v, 'To': to_val}
                print(f"{indent}    pair {elem}")
                out.append(elem)
            return out

        # 2) nested ProduceDict (e.g. repaint_coords)
        if isinstance(prod, ProduceDict) and row_context is not None:
            print(f"{indent}  [DICT] building dict from row_context keys {list(prod.maps.keys())}")
            return {
                k: eval_producer(child, row_context, depth + 1)
                for k, child in prod.maps.items()
            }

        # 3) coordinate lookup (only when tagged SelectCoordAction)
        if isinstance(prod, ProduceValue) and getattr(prod, 'suggested_by_train_function', None) == 'SelectCoordAction':
            sprite_id = (
                    row_context.get('id')
                    or row_context.get('origin_sprite_id')
                    or row_context.get('sprite_id')
            )
            return select_coord(
                trainId,
                sprite_id,
                prod.produceByTrainAndSpriteId,
                prod.originByTrainAndSpriteId,
                prod.attribute,  # e.g. "minX" or "minY"
                row_context
            )

        # 4) simple ProduceValue leaf
        if isinstance(prod, ProduceValue) and row_context is not None and prod.attribute:
            raw = row_context.get(prod.attribute)
            out = prod.adapter(raw) if prod.adapter else raw
            print(f"{indent}  [LEAF] attr '{prod.attribute}': {raw!r} → {out!r}")
            return out

        # 5) fallback
        print(f"{indent}  [FALLBACK] None")
        return None

    # ─── Root‐level: only for ProduceList suggested by SelectSpriteRowsFunction ──
    if (
        isinstance(produceObj, ProduceList)
        and produceObj.criteria
        and getattr(produceObj, 'suggested_by_train_function', None) == 'SelectSpriteRowsFunction'
    ):
        tbl = tables.get(table_key, {})
        rows = select_sprite_rows(trainId, testId, produceObj.criteria, tbl)
        output: Dict[str, List[Any]] = {key: [] for key in produceObj.maps.keys()}
        for i, r in enumerate(rows):
            print(f"[ROOT] element #{i}, row {r}")
            for key, child in produceObj.maps.items():
                val = eval_producer(child, r, depth=1)
                output[key].append(val)
        print(f"\n=== produce_dict END → {output!r} ===\n")
        return output

    # ─── Generic single‐producer path ────────────────────────────────────
    result = eval_producer(produceObj, None, depth=0)
    print(f"\n=== produce_dict END → {result!r} ===\n")
    return result

ACTIONS = [
    Action(
        id="producer_action",
        name="producer action",
        description=(
            "Produce"
        ),
        category=ActionCategory.SELECTION_FILTERING,
        input_arguments=[
            ArgumentBinding(name="trainId", type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="testId", type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="produceObj",   type="Producer",    binding=BindingStatus.CONSTANT),
            ArgumentBinding(name="tables",  type="Tables",    binding=BindingStatus.CONSTANT),
        ],
        output_type="Grid",
        function=produce_dict
    ),
]
