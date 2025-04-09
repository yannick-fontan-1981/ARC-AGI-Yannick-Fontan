import inspect

def preprocess_grid_or_object(data):
    """
    Preprocess the input data to ensure compatibility with solvers.

    Args:
        data: A grid (list of lists or tuple of tuples) or an object (frozenset).

    Returns:
        A preprocessed grid (tuple of tuples) or object (frozenset).
    """
    if isinstance(data, list):  # Convert grid list to tuple of tuples
        return tuple(tuple(row) for row in data)
    elif isinstance(data, tuple):  # Already in correct format
        return data
    elif isinstance(data, frozenset):  # Assume it's an object and return as-is
        return data
    else:
        raise ValueError(f"Unsupported data format: {type(data)}")


def extract_called_operations(solver_function):
    """
    Extract the operations called inside a solver function by analyzing its code.

    Args:
        solver_function: The solver function to analyze.

    Returns:
        A list of strings representing the operations called within the solver.
    """
    code_lines = inspect.getsource(solver_function).splitlines()

    operations = []
    for line in code_lines:
        line = line.strip()
        if "(" in line and ")" in line and not line.startswith("def") and not line.startswith("return"):
            operation = line.split("(")[0].strip()
            operations.append(operation)

    # Remove any assignment prefixes like "O = " or "x1 = "
    operations = [op.split("=")[-1].strip() if "=" in op else op for op in operations]
    return operations


def find_transformations_with_solver(solver_function, input_grid, output_grid):
    """
    Use a solver function to extract transformations applied to an input grid.

    Args:
        solver_function: The solver function to test.
        input_grid: The input grid.
        output_grid: The expected output grid.

    Returns:
        A dictionary containing detected patterns and matched operations.
    """
    # Extract operations dynamically from the solver
    operations_called = extract_called_operations(solver_function)

    # Preprocess the grids to ensure compatibility
    preprocessed_input = preprocess_grid_or_object(input_grid)
    preprocessed_output = preprocess_grid_or_object(output_grid)

    # Verify if the solver produces the expected result
    solver_result = solver_function(preprocessed_input)
    if solver_result == preprocessed_output:
        return {
            "detected_patterns": operations_called,
            "matched_operations": operations_called
        }

    return {
        "detected_patterns": [],
        "matched_operations": []
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


def integrate_extract_operations(file_name, solver_function):
    """
    Integrate the extraction of operations for a specific solver.

    Args:
        file_name: The name of the file being processed.
        solver_function: The solver function for the file.

    Returns:
        A dictionary with the extracted operations.
    """
    operations = extract_called_operations(solver_function)
    return {
        "file": file_name,
        "extracted_operations": list(set(operations))
    }

