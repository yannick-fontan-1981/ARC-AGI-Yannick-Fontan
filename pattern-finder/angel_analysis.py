# pattern-finder/angel_analysis.py
import argparse
import os
import sqlite3
import json
from collections import defaultdict
from constelize.tools.sqlite_loader import load_all_tables_from_sqlite
def detect_and_store_angels(db_path: str):
    import sqlite3, json
    from collections import defaultdict
    from constelize.tools.sqlite_loader import load_all_tables_from_sqlite

    conn = sqlite3.connect(db_path)
    tables = load_all_tables_from_sqlite(db_path)
    sprites = tables.get("sprite_analysis", {})
    objects = tables.get("object_analysis", {})

    sprites_by_train = defaultdict(list)
    in_objs_by_train = defaultdict(list)
    out_objs_by_train = defaultdict(list)

    for s in sprites.values():
        if s["trainId"] >= 0:
            sprites_by_train[s["trainId"]].append(s)

    for o in objects.values():
        if o["trainId"] < 0:
            continue
        if o["isInsideInput"]:
            in_objs_by_train[o["trainId"]].append(o)
        if o["isInsideOutput"]:
            out_objs_by_train[o["trainId"]].append(o)

    c = conn.cursor()
    c.execute("DELETE FROM angel_analysis;")

    for trainId, sprite_list in sprites_by_train.items():
        in_objs = in_objs_by_train.get(trainId, [])
        out_objs = out_objs_by_train.get(trainId, [])

        for s in sprite_list:
            inp = bool(s["isInsideInput"])
            out = bool(s["isInsideOutput"])
            disapear = inp and not out
            createSprite = out and not inp
            createObject = False

            if not (disapear or createSprite):
                continue

            h = s.get("height", 0)
            w = s.get("width", 0)
            one_pixel = (h == 1 and w == 1)
            colors = json.loads(s.get("colorPresent", "[]"))
            bicolor = (len(colors) == 2)
            angel_color = s.get("colorMost")

            rec = {
                "sprite_id": s["id"],
                "block_id": None,
                "shape_id": None,
                "one_pixel": one_pixel,
                "bicolor": bicolor,
                "color_used": False,
                "position_x_used": False,
                "position_y_used": False,
                "height_used": False,
                "width_used": False,
                "color_match": False,
                "position_x_match": False,
                "position_y_match": False,
                "height_match": False,
                "width_match": False,
                "multiple_selection": False,
                "disapear": disapear,
                "createObject": createObject,
                "createSprite": createSprite,
                "input_target": None,
                "output_target": None,
                "target_touching_top": None,
                "target_touching_right": None,
                "target_touching_bottom": None,
                "target_touching_left": None,
                "x_angel_origin": s.get("minX"),
                "x_angel_position": s.get("minX"),
                "x_target_origin": None,
                "x_target_position": None,
                "x_target_multiplier": None,
                "x_target_zone_width": None,
                "x_target_zone_height": None,
                "y_angel_position": s.get("minY"),
                "y_target_origin": None,
                "y_target_position": None,
                "y_target_multiplier": None,
                "y_target_zone_width": None,
                "y_target_zone_height": None,
                "angel_criteria": None,
                "angel_match_attribute": None,
                "angel_match_type": None,
                "angel_match_value": None,
                "angel_used_attribute": None,
                "angel_used_type": None,
                "angel_used_value": None,
                "target_criteria": None,
                "target_attribute": None,
                "target_type": None,
                "target_value": None,
            }

            matches = []
            for o_in in in_objs:
                for o_out in out_objs:
                    if o_in["trainId"] != trainId or o_out["trainId"] != trainId:
                        continue
                    if o_out["color"] != o_in["color"] and o_out["color"] == angel_color:
                        rec["color_match"] = True
                        matches.append(("color", o_in["id"], o_out["id"]))
                    if o_out["minX"] != o_in["minX"] and o_out["minX"] == rec["x_angel_origin"]:
                        rec["position_x_match"] = True
                        matches.append(("position_x", o_in["id"], o_out["id"]))
                    if o_out["minY"] != o_in["minY"] and o_out["minY"] == rec["y_angel_position"]:
                        rec["position_y_match"] = True
                        matches.append(("position_y", o_in["id"], o_out["id"]))
                    if o_out["width"] != o_in["width"] and o_out["width"] == w:
                        rec["width_match"] = True
                        matches.append(("width", o_in["id"], o_out["id"]))
                    if o_out["height"] != o_in["height"] and o_out["height"] == h:
                        rec["height_match"] = True
                        matches.append(("height", o_in["id"], o_out["id"]))
                    if "sizeOrder" in o_in and o_out.get("sizeOrder") != o_in.get("sizeOrder"):
                        if o_out.get("sizeOrder") == s.get("pixelCount"):
                            rec["angel_used_attribute"] = "sizeOrder"
                            rec["angel_used_value"] = o_out["sizeOrder"]
                            matches.append(("sizeOrder", o_in["id"], o_out["id"]))

            if not matches:
                continue

            rec["input_target"], rec["output_target"] = matches[0][1], matches[0][2]
            rec["multiple_selection"] = len({(i, o) for _, i, o in matches}) > 1

            rec["color_used"] = rec["color_match"]
            rec["position_x_used"] = rec["position_x_match"]
            rec["position_y_used"] = rec["position_y_match"]
            rec["width_used"] = rec["width_match"]
            rec["height_used"] = rec["height_match"]

            cols = ", ".join(rec.keys())
            phs = ", ".join("?" for _ in rec)
            c.execute(f"INSERT INTO angel_analysis ({cols}) VALUES ({phs})", tuple(rec.values()))

    conn.commit()
    conn.close()

def main(json_source, *, inline=False, name=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path    = os.path.abspath(os.path.join(script_dir, "..", "db", "database.db"))

    # open a connection so that any future calls could also use it
    conn = sqlite3.connect(db_path)

    # Determine the “filename” label for this run
    if name:
        filename = name
    elif inline:
        filename = "<in-memory-json>"
    else:
        filename = os.path.basename(json_source)

    # Load the JSON (we don’t actually use it here, but we keep the pattern)
    if inline:
        data = json.loads(json_source)
    else:
        with open(json_source, "r") as f:
            data = json.load(f)

    print(f"[angel_analysis] running for '{filename}' → db: {db_path}")
    # run the detection routine
    detect_and_store_angels(db_path)

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect and populate angel_analysis from the ARC DB."
    )
    parser.add_argument(
        "json_input",
        help="Path to an ARC JSON file, or (with --inline) a raw JSON string"
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Treat json_input as raw JSON text rather than a file path"
    )
    parser.add_argument(
        "--name", "-n",
        help="If provided, use this as the scenario name instead of the file basename"
    )
    args = parser.parse_args()
    main(args.json_input, inline=args.inline, name=args.name)