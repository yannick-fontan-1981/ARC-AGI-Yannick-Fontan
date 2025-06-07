import json

from constelize.core.registry import ActionRegistry
from constelize.dsl.grid_dsl import apply_all_cycles


def test_registry_loads_without_error():
    registry = ActionRegistry()
    registry.register_all_actions()
    assert len(registry.all()) > 0
    assert any(action.name == "add" for action in registry.all())  # Example check






def main():
    # Example input grid (train_id = 0) as given in your test:
    input_grid = [
        [  1,  0,  0,  0,  1,  1,  1,  1,  0,  1,  1,  0,  1,  0,  1,  0,  1,  1,  1 ],
        [  1,  0,  1,  0,  1,  1,  1,  1,  0,  0,  1,  1,  1,  1,  1,  1,  0,  1,  1 ],
        [  1,  1,  1,  1,  0,  0,  1,  1,  0,  1,  0,  0,  0,  1,  0,  1,  0,  1,  0 ],
        [  1,  0,  1,  1,  1,  1,  1,  1,  0,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1 ],
        [  1,  0,  1,  1,  0,  1,  1,  1,  0,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1 ],
        [  1,  1,  0,  1,  0,  1,  1,  0,  0,  0,  0,  1,  0,  1,  1,  0,  0,  0,  1 ],
        [  1,  0,  0,  1,  1,  0,  1,  0,  0,  1,  1,  1,  1,  1,  1,  1,  0,  1,  0 ],
        [  1,  1,  0,  0,  1,  1,  1,  1,  0,  1,  0,  1,  1,  1,  0,  1,  1,  1,  1 ],
        [  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0 ],  # row 8
        [  1,  1,  1,  0,  0,  1,  1,  1,  0,  1,  0,  0,  1,  1,  1,  1,  1,  1,  1 ],
        [  1,  1,  0,  0,  1,  1,  0,  0,  0,  1,  1,  0,  0,  0,  1,  0,  1,  0,  1 ],
        [  1,  0,  1,  0,  1,  0,  0,  1,  0,  1,  1,  1,  1,  0,  0,  1,  1,  1,  1 ]
    ]

    # These four “start” rows come from your light_cycle table for train 0:
    # We parse JSON‐style strings for pixel_rel, neighbor sets, and row/col sets.
    light_cycles = [
        {
            "id": 1,
            "light_cycle_id": 0,
            "action": "start",
            "direction_x": 0,
            "direction_y": 1,
            "pixel_rel": json.loads(
                "[[-2, [-1, -1]], [-2, [0, -1]], [-2, [1, -1]], [0, [0, 0]], [0, [0, 1]], [0, [0, 2]]]"
            ),
            "common_neighbors": {
                "north":        frozenset(json.loads("[-2]")),
                "north_east":   frozenset(json.loads("[-2]")),
                "east":         frozenset(json.loads("[-8]")),
                "south_east":   frozenset(json.loads("[-8]")),
                "south":        frozenset(json.loads("[0]")),
                "south_west":   frozenset(json.loads("[-8]")),
                "west":         frozenset(json.loads("[-8]")),
                "north_west":   frozenset(json.loads("[-2]"))
            },
            "common_rowcol": {
                "next_row":     frozenset(json.loads("[-8, 0]")),
                "prev_row":     frozenset(json.loads("[]")),
                "next_col":     frozenset(json.loads("[-8, 0]")),
                "prev_col":     frozenset(json.loads("[-8, 0]"))
            },
            "color": 2,
            "order_idx": 0
        },
        {
            "id": 2,
            "light_cycle_id": 0,
            "action": "start",
            "direction_x": 1,
            "direction_y": 0,
            "pixel_rel": json.loads(
                "[[0, [1, -2]], [-2, [-1, -1]], [-2, [-1, 0]], [0, [0, 0]], [0, [1, 0]], [0, [2, 0]], [-2, [-1, 1]]]"
            ),
            "common_neighbors": {
                "north":        frozenset(json.loads("[-8]")),
                "north_east":   frozenset(json.loads("[-8]")),
                "east":         frozenset(json.loads("[0]")),
                "south_east":   frozenset(json.loads("[-8]")),
                "south":        frozenset(json.loads("[-8]")),
                "south_west":   frozenset(json.loads("[-2]")),
                "west":         frozenset(json.loads("[-2]")),
                "north_west":   frozenset(json.loads("[-2]"))
            },
            "common_rowcol": {
                "next_row":     frozenset(json.loads("[-8, 0]")),
                "prev_row":     frozenset(json.loads("[-8, 0]")),
                "next_col":     frozenset(json.loads("[-8, 0]")),
                "prev_col":     frozenset(json.loads("[]"))
            },
            "color": 2,
            "order_idx": 0
        },
        {
            "id": 3,
            "light_cycle_id": 0,
            "action": "start",
            "direction_x": -1,
            "direction_y": 0,
            "pixel_rel": json.loads(
                "[[-2, [1, -1]], [0, [-2, 0]], [0, [-1, 0]], [0, [0, 0]], [-2, [1, 0]], [-2, [1, 1]]]"
            ),
            "common_neighbors": {
                "north":        frozenset(json.loads("[-8]")),
                "north_east":   frozenset(json.loads("[-2]")),
                "east":         frozenset(json.loads("[-2]")),
                "south_east":   frozenset(json.loads("[-2]")),
                "south":        frozenset(json.loads("[-8]")),
                "south_west":   frozenset(json.loads("[-8]")),
                "west":         frozenset(json.loads("[0]")),
                "north_west":   frozenset(json.loads("[-8]"))
            },
            "common_rowcol": {
                "next_row":     frozenset(json.loads("[-8, 0]")),
                "prev_row":     frozenset(json.loads("[-8, 0]")),
                "next_col":     frozenset(json.loads("[]")),
                "prev_col":     frozenset(json.loads("[-8, 0]"))
            },
            "color": 2,
            "order_idx": 0
        },
        {
            "id": 4,
            "light_cycle_id": 0,
            "action": "start",
            "direction_x": 0,
            "direction_y": -1,
            "pixel_rel": json.loads(
                "[[0, [0, -2]], [0, [0, -1]], [0, [0, 0]], [-2, [-1, 1]], [-2, [0, 1]], [-2, [1, 1]]]"
            ),
            "common_neighbors": {
                "north":        frozenset(json.loads("[0]")),
                "north_east":   frozenset(json.loads("[-8]")),
                "east":         frozenset(json.loads("[-8]")),
                "south_east":   frozenset(json.loads("[-2]")),
                "south":        frozenset(json.loads("[-2]")),
                "south_west":   frozenset(json.loads("[-2]")),
                "west":         frozenset(json.loads("[-8]")),
                "north_west":   frozenset(json.loads("[-8]"))
            },
            "common_rowcol": {
                "next_row":     frozenset(json.loads("[]")),
                "prev_row":     frozenset(json.loads("[-8, 0]")),
                "next_col":     frozenset(json.loads("[-8, 0]")),
                "prev_col":     frozenset(json.loads("[-8, 0]"))
            },
            "color": 2,
            "order_idx": 0
        }
    ]

    print("=== Running verbose _apply_all_cycles ===")
    output_grid = apply_all_cycles(input_grid, light_cycles)

    print("\n=== Output Grid ===")
    for row in output_grid:
        print(row)


if __name__ == "__main__":
    main()