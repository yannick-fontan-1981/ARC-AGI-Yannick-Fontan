import json
import os
import importlib
from solver.dsl import vmirror, hmirror, rot90, rot180
from solver.yannick_dsl import preprocess_grid_or_object, extract_called_operations, find_transformations_with_solver

# Dynamic solver import and mapping
DATA_DIR = "data"
TRAINING_DIR = os.path.join(DATA_DIR, "training-1")
RESULT_DIR = os.path.join(DATA_DIR, "results-1")
RESULT_FILE = os.path.join(RESULT_DIR, "patterns_results.json")
PATTERNS_MAP_FILE = os.path.join(DATA_DIR, "patterns-map.json")

os.makedirs(RESULT_DIR, exist_ok=True)

def load_solvers():
    """
    Dynamically load solver functions based on files in the training directory.

    Returns:
        dict: A mapping of file names to solver functions.
    """
    solvers = {}
    for file_name in os.listdir(TRAINING_DIR):
        if file_name.endswith(".json"):
            solver_name = f"solve_{os.path.splitext(file_name)[0]}"
            try:
                solver_module = importlib.import_module("solver.solvers")
                solver_function = getattr(solver_module, solver_name, None)
                if solver_function:
                    solvers[file_name] = solver_function
            except (ImportError, AttributeError):
                print(f"Solver function {solver_name} for {file_name} not found.")
    return solvers

SOLVER_OPERATIONS = load_solvers()

def parse_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)


def get_shape(grid):
    """Get the shape of a single grid (height and width)."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    return height, width


def analyze_canvas(data):
    """Perform detailed canvas analysis."""
    input_shapes = [get_shape(item["input"]) for item in data.get("train", [])]
    output_shapes = [get_shape(item["output"]) for item in data.get("train", [])]

    all_inputs_same_size = all(s == input_shapes[0] for s in input_shapes)
    all_outputs_same_size = all(s == output_shapes[0] for s in output_shapes)
    inputs_outputs_equal = all(inp == out for inp, out in zip(input_shapes, output_shapes))

    proportions = [
        (out[0] / inp[0], out[1] / inp[1])
        for inp, out in zip(input_shapes, output_shapes)
        if inp[0] > 0 and inp[1] > 0
    ]
    consistent_proportion = all(p == proportions[0] for p in proportions) if proportions else False

    return {
        "all_inputs_same_size": all_inputs_same_size,
        "all_outputs_same_size": all_outputs_same_size,
        "inputs_outputs_equal": inputs_outputs_equal,
        "consistent_proportion": consistent_proportion
    }


def process_files(files):
    """
    Process a list of files to extract patterns and operations.

    Args:
        files: List of file names to process.

    Returns:
        A dictionary of results for each file.
    """
    results = {}
    for file_name in files:
        file_path = os.path.join(TRAINING_DIR, file_name)
        data = parse_json(file_path)

        canvas_analysis = analyze_canvas(data)
        trainings = []

        # Get the associated solver function
        solver_function = SOLVER_OPERATIONS.get(file_name)
        if not solver_function:
            continue

        for idx, train_data in enumerate(data.get("train", [])):
            input_grid = train_data["input"]
            output_grid = train_data["output"]

            # Extract transformations using the solver
            transformations = find_transformations_with_solver(solver_function, input_grid, output_grid)

            trainings.append({
                "id": idx,
                "patterns": [transformations]
            })

        results[file_name] = {
            "canvas_analysis": canvas_analysis,
            "trainings": trainings
        }

    return results


def save_results(results):
    with open(RESULT_FILE, "w") as f:
        json.dump(results, f, indent=4)


def update_patterns_map(results):
    """
    Consolidate all detected patterns and matched operations into patterns-map.json.

    Args:
        results: The results dictionary from process_files.
    """
    patterns_map = []

    # Load existing patterns-map if it exists
    if os.path.exists(PATTERNS_MAP_FILE):
        with open(PATTERNS_MAP_FILE, "r") as f:
            patterns_map = json.load(f)

    # Extract unique patterns from results
    for file_result in results.values():
        for training in file_result.get("trainings", []):
            for pattern in training.get("patterns", []):
                if pattern not in patterns_map:
                    patterns_map.append(pattern)

    # Save updated patterns-map
    with open(PATTERNS_MAP_FILE, "w") as f:
        json.dump(patterns_map, f, indent=4)


def main():
    files = [file_name for file_name in os.listdir(TRAINING_DIR) if file_name.endswith(".json")]

    results = process_files(files)
    save_results(results)
    update_patterns_map(results)


if __name__ == "__main__":
    main()
