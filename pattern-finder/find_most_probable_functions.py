import sqlite3
import numpy as np


def load_first_sight_average_function(db_path="../db/database.db"):
    """
    Loads the training data from first_sight_average_function.
    Assumes that the first column is "function" (TEXT) and the remaining columns are numeric.
    Returns:
      - A dictionary mapping each function name (string) to its feature vector (numpy array).
      - A list of feature names (in the order they appear in the table, excluding "function").
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM first_sight_average_function")
    rows = cur.fetchall()
    col_names = [desc[0] for desc in cur.description]
    conn.close()

    # Assume first column is "function" and the rest are numeric features.
    # **Force the function names to be strings.**
    feature_names = col_names[1:]
    functions = {}
    for row in rows:
        func = str(row[0])  # <-- Force to string!
        # Convert remaining columns to a numpy array (float)
        features = np.array(row[1:], dtype=float)
        functions[func] = features
    return functions, feature_names


def load_first_sight_analysis_for_task(filename, db_path="../db/database.db"):
    """
    Loads the first_sight_analysis data for a given task (identified by filename)
    from the database. If multiple rows exist for that file (i.e. multiple train examples),
    it averages the numeric columns.

    Returns:
      - A numpy vector of the averaged features.
      - A list of feature names (columns, excluding "filename" and "trainId").
    If no data is found for the given filename, returns (None, None).
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM first_sight_analysis WHERE filename = ?", (filename,))
    rows = cur.fetchall()
    if not rows:
        conn.close()
        return None, None

    col_names = [desc[0] for desc in cur.description]
    # Define numeric columns as those except "filename" and "trainId"
    numeric_cols = [col for col in col_names if col not in {"filename", "trainId"}]
    indices = [col_names.index(col) for col in numeric_cols]

    # For each numeric column, compute the average (replace None with 0)
    averaged_data = {}
    for i, col in zip(indices, numeric_cols):
        values = [row[i] if row[i] is not None else 0 for row in rows]
        averaged_data[col] = sum(values) / len(values)

    conn.close()
    # Build feature vector (ordered by numeric_cols)
    feature_vector = np.array([averaged_data[col] for col in numeric_cols], dtype=float)
    return feature_vector, numeric_cols


def find_most_probable_functions(filename, db_path="../db/database.db", top_n=10):
    """
    For a given task identified by 'filename', this function:
      1. Loads the task's feature vector from first_sight_analysis (averaging if needed).
      2. Loads the training (average) features from first_sight_average_function.
      3. Computes the Euclidean distance between the task vector and each training function vector.
      4. Returns and prints the top_n functions (neighbors) ranked by similarity (lowest distance).
    """
    # Load the task's feature vector.
    task_vector, task_feature_names = load_first_sight_analysis_for_task(filename, db_path=db_path)
    if task_vector is None:
        print(f"No first_sight_analysis data found for {filename}.")
        return []

    # Load training data (function average features)
    function_dict, avg_feature_names = load_first_sight_average_function(db_path=db_path)

    # Check if the feature orders match.
    if task_feature_names != avg_feature_names:
        print("Warning: Feature names from first_sight_analysis and first_sight_average_function do not match!")
        print("Task features:", task_feature_names)
        print("Average features:", avg_feature_names)
        # In a robust solution, you would reorder task_vector accordingly.

    # Compute Euclidean distances.
    results = []
    for func, avg_vector in function_dict.items():
        if avg_vector.shape[0] != task_vector.shape[0]:
            continue  # Skip if dimensions do not match.
        distance = np.linalg.norm(task_vector - avg_vector)
        results.append((func, distance))

    # Sort results by distance (ascending)
    results.sort(key=lambda x: x[1])

    # Print the top_n neighbors.
    print("🔎 Top nearest functions for", filename)
    for i, (func, dist) in enumerate(results[:top_n], start=1):
        print(f"{i}. Function: {func}, Distance: {dist:.4f}")

    return results[:top_n]


def evaluate_all_tasks(db_path="../db/database.db", top_n=10):
    """
    For each filename in first_sight_analysis, runs find_most_probable_functions and compares
    the predicted (top nearest) function names with the ground truth in the solutions table.
    Logs the number of matches for each task and returns the total number of tasks with 0 matches.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Get all distinct filenames from first_sight_analysis.
    cur.execute("SELECT DISTINCT filename FROM first_sight_analysis")
    filenames = [row[0] for row in cur.fetchall()]

    zero_matches = 0
    total_tasks = len(filenames)

    print("=== Evaluation of Predicted Functions ===")
    for fname in filenames:
        # Load the task's feature vector
        task_vector, feature_names = load_first_sight_analysis_for_task(fname, db_path=db_path)
        if task_vector is None:
            print(f"Task {fname}: no analysis data found.")
            continue

        # Build a dictionary for the task features for consistency (order as in feature_names)
        task_features = {col: float(val) for col, val in zip(feature_names, task_vector)}

        # Get the top predicted functions.
        predictions = find_most_probable_functions(fname, db_path=db_path, top_n=top_n)
        predicted_functions = [pred[0] for pred in predictions]

        # Get actual functions from the solutions table for this task.
        cur.execute("SELECT DISTINCT function FROM solutions WHERE filename = ?", (fname,))
        actual_funcs = [row[0] for row in cur.fetchall()]

        # Count matches (if any predicted function appears in actual functions)
        matches = [f for f in predicted_functions if f in actual_funcs]
        num_matches = len(matches)

        print(f"\nTask {fname}:")
        print(f"  Predicted: {predicted_functions}")
        print(f"  Actual (from solutions): {actual_funcs}")
        print(f"  Number of matches: {num_matches}")

        if num_matches == 0:
            zero_matches += 1

    conn.close()
    print("\n=== Evaluation Complete ===")
    print(f"Total tasks evaluated: {total_tasks}")
    print(f"Number of tasks with 0 matches: {zero_matches}")
    return zero_matches


def main():
    # For example, evaluate all tasks and log the number of tasks with 0 matches.
    zero_matches = evaluate_all_tasks(db_path="../db/database.db", top_n=10)
    print(f"\nNumber of tasks with 0 matches: {zero_matches}")


if __name__ == "__main__":
    main()
