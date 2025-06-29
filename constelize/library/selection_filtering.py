from constelize.core.action import Action
from constelize.core.categories import ActionCategory
from constelize.core.binding import ArgumentBinding, BindingStatus, Producer, ProduceValue, ProduceDict, ProduceList
from typing import Callable, FrozenSet, Any, Dict, List, Optional


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
    at the root, and handling nested ProduceList with attribute for recolor_maps.
    """
    table_key = "sprite_analysis"
    print(f"\n=== produce_dict START for trainId={trainId}, testId={testId} ===")
    # Root SelectSpriteRowsFunction
    def select_sprite_rows(trainId: int, testId: int, criteria: List[tuple], tbl: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        print(f"🔎 SelectSpriteRowsFunction → trainId={trainId}, testId={testId}, criteria={criteria}")
        out=[]
        for rid,row in tbl.items():
            if row.get('trainId')!=trainId or row.get('testId')!=testId: continue
            if all(row.get(col)==val for col,val,_ in criteria): out.append(row)
        print(f"🔍 Selected rows: {out}")
        return out

    # Concrete recolor selection function
    def select_recolor(
            trainId: int,
            spriteId: int,
            criteria: List[tuple],
            tbl: Dict[int, Dict[str, Any]],
            raw_arr: List[int],
            cumulValueMap: Dict[int, List[int]] = None) -> List[Any]:
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

    def eval_producer(prod: Producer, row_context: Optional[Dict[str,Any]]=None, depth: int=0) -> Any:
        indent = '  '*depth
        print(f"{indent}-- eval_producer: {type(prod).__name__} --")

                # Nested ProduceList with attribute (e.g. recolor_maps)
        if isinstance(prod, ProduceList) and row_context is not None and prod.attribute:
            # get the raw list of 'From' values
            raw_arr = prod.adapter(row_context.get(prod.attribute)) if prod.adapter else row_context.get(prod.attribute)
            print(f"{indent}  [LIST] attribute '{prod.attribute}' → {raw_arr}")
            # compute all 'To' values via select_recolor once
            sprite_id = row_context.get('id') or row_context.get('origin_sprite_id') or row_context.get('sprite_id')
            to_list = select_recolor(
                trainId,
                sprite_id,
                prod.maps['To'].criteria,
                tables[table_key],
                raw_arr=raw_arr,
                cumulValueMap=prod.maps['To'].cumulValueMap
            )
            print(f"{indent}  [LIST] raw Arr → {raw_arr}, To List → {to_list}")

            # 3) if fallback happened, align raw_arr to only those keys that exist in cumulValueMap
            if len(to_list) != len(raw_arr):
                valid_keys = set(prod.maps['To'].cumulValueMap.keys())
                raw_arr = [v for v in raw_arr if v in valid_keys]
                print(f"{indent}  [LIST] fallback trim raw_arr → {raw_arr}")

            print(f"{indent}  [LIST] zipped From/To pairs → {list(zip(raw_arr, to_list))}")

            # 4) build the output, skipping identity or missing
            out = []
            for v, to_val in zip(raw_arr, to_list):
                if v is None or to_val is None or v == to_val:
                    print(f"{indent}    skip pair {{'From':{v}, 'To':{to_val}}}")
                    continue
                elem = {'From': v, 'To': to_val}
                print(f"{indent}    pair {{'From':{v}, 'To':{to_val}}}")
                out.append(elem)
            return out

        # Leaf ProduceDict from row_context (repaint_coords)
        if isinstance(prod, ProduceDict) and row_context is not None:
            print(f"{indent}  [DICT] building dict from row_context keys {list(prod.maps.keys())}")
            return {k: eval_producer(child,row_context,depth+1) for k,child in prod.maps.items()}

        # Leaf ProduceValue from row_context
        if isinstance(prod, ProduceValue) and row_context is not None and prod.attribute:
            raw=row_context.get(prod.attribute)
            out=prod.adapter(raw) if prod.adapter else raw
            print(f"{indent}  [LEAF] attr '{prod.attribute}': {raw!r} → {out!r}")
            return out

        # Fallback: no match
        print(f"{indent}  [FALLBACK] None")
        return None

    # Root handling: produceObj should be ProduceList
    if isinstance(produceObj, ProduceList) and produceObj.criteria and getattr(produceObj,'suggested_by_train_function',None)=='SelectSpriteRowsFunction':
        tbl=tables.get(table_key,{})
        rows=select_sprite_rows(trainId,testId,produceObj.criteria,tbl)
        output={key:[] for key in produceObj.maps.keys()}
        for i,r in enumerate(rows):
            print(f"[ROOT] element #{i}, row {r}")
            for key,child in produceObj.maps.items():
                val=eval_producer(child,r,1)
                output[key].append(val)
        print(f"\n=== produce_dict END → {output!r} ===\n")
        return output

    # Otherwise generic
    result = eval_producer(produceObj,None,0)
    print(f"\n=== produce_dict END → {result!r} ===\n")
    return result





ACTIONS = [
    Action(
        id="sfilter",
        name="Simple Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=sfilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="Container",
        description="Filter elements in container based on condition."
    ),
    Action(
        id="mfilter",
        name="Merge Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=mfilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="FrozenSet",
        description="Filter elements and return merged set."
    ),
    Action(
        id="extract_first_match",
        name="Extract First Match",
        category=ActionCategory.SELECTION_FILTERING,
        function=extract,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="condition", type="Callable")
        ],
        output_type="Any",
        description="Extract first element that satisfies condition."
    ),
    Action(
        id="size_filter",
        name="Size Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=sizefilter,
        input_arguments=[
            ArgumentBinding(name="container", type="Container"),
            ArgumentBinding(name="n", type="Integer")
        ],
        output_type="FrozenSet",
        description="Filter container items by size."
    ),
    Action(
        id="color_filter",
        name="Color Filter",
        category=ActionCategory.SELECTION_FILTERING,
        function=colorfilter,
        input_arguments=[
            ArgumentBinding(name="objs", type="Objects"),
            ArgumentBinding(name="value", type="Integer")
        ],
        output_type="FrozenSet",
        description="Filter objects by color value."
    ),
    Action(
        id="producer_action",
        name="producer_action",
        description="based on a produce object, produce values to be bind by others",
        category=ActionCategory.SELECTION_FILTERING,
        input_arguments=[
            ArgumentBinding(name="trainId",    type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="testId",     type="Integer", binding=BindingStatus.CONTEXT),
            ArgumentBinding(name="produceObj", type="Integer", binding=BindingStatus.CONSTANT),
            ArgumentBinding(name="tables",     type="Tables",  binding=BindingStatus.CONSTANT)
        ],
        output_type="Dict",
        function=produce_dict,
        deterministic=True,
        pure=True,
        reversible=False
    )
]
