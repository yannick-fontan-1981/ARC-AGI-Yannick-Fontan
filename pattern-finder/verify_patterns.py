import json
import os
from solver.dsl import *
from solver.yannick_dsl import preprocess_grid_or_object

DATA_DIR = "data"
TRAINING_DIR = os.path.join(DATA_DIR, "training-1")
TESTS_DIR = os.path.join(DATA_DIR, "tests")
RESULT_FILE = os.path.join(TESTS_DIR, "test-1.json")
PATTERNS_MAP_FILE = os.path.join(DATA_DIR, "patterns-map.json")

os.makedirs(TESTS_DIR, exist_ok=True)

def parse_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def apply_operations(grid, operations):
    """
    Apply a series of operations to a grid.

    Args:
        grid: The input grid.
        operations: A list of operation names to apply.

    Returns:
        The transformed grid after applying the operations.
    """
    for operation in operations:
        if operation == "vmirror":
            grid = vmirror(grid)
        elif operation == "hmirror":
            grid = hmirror(grid)
        elif operation == "rot90":
            grid = rot90(grid)
        elif operation == "rot180":
            grid = rot180(grid)
        elif operation == "rot270":
            grid = rot270(grid)
        elif operation == "dmirror":
            grid = dmirror(grid)
        elif operation == "upscale":
            grid = vmirror(grid)
        elif operation == "replace":
            grid = vmirror(grid)
        elif operation == "hconcat":
            grid = vmirror(grid)
        elif operation == "crop":
            grid = vmirror(grid)
        elif operation == "switch":
            grid = vmirror(grid)
        else:
            raise ValueError(f"Unsupported operation: {operation}")
    return grid

def verify_patterns():
    """
    Verify patterns from patterns-map.json on training-1 data and test their consistency.
    """
    if not os.path.exists(PATTERNS_MAP_FILE):
        raise FileNotFoundError(f"Patterns map file not found: {PATTERNS_MAP_FILE}")

    patterns_map = parse_json(PATTERNS_MAP_FILE)
    results = {}

    for file_name in os.listdir(TRAINING_DIR):
        file_path = os.path.join(TRAINING_DIR, file_name)
        data = parse_json(file_path)

        file_results = []

        # Test consistency on train data
        for pattern in patterns_map:
            detected_patterns = pattern.get("detected_patterns", [])
            matched_operations = pattern.get("matched_operations", [])

            consistent = True
            for train_case in data.get("train", []):
                input_grid = preprocess_grid_or_object(train_case["input"])
                expected_output = preprocess_grid_or_object(train_case["output"])

                transformed_output = apply_operations(input_grid, matched_operations)
                if transformed_output != expected_output:
                    consistent = False
                    break

            if consistent:
                # Apply the operations to the test data
                for test_case in data.get("test", []):
                    input_grid = preprocess_grid_or_object(test_case["input"])
                    expected_output = preprocess_grid_or_object(test_case["output"])

                    transformed_output = apply_operations(input_grid, matched_operations)

                    file_results.append({
                        "input": test_case["input"],
                        "expected_output": test_case["output"],
                        "transformed_output": transformed_output,
                        "detected_patterns": detected_patterns,
                        "matched_operations": matched_operations,
                        "match": transformed_output == expected_output
                    })

        results[file_name] = file_results

    # Save the test results
    with open(RESULT_FILE, "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    verify_patterns()
