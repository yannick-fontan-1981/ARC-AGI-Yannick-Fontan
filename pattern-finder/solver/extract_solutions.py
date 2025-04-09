import sqlite3
import os
import re

def create_solutions_table(conn):
    """
    Creates the 'solutions' table in the database if it does not exist.
    """
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solutions (
            filename TEXT NOT NULL,
            solution INTEGER NOT NULL,
            line INTEGER NOT NULL,
            function TEXT NOT NULL,
            param_1 TEXT,
            param_2 TEXT,
            param_3 TEXT,
            param_4 TEXT,
            param_5 TEXT,
            return_value TEXT,
            line_text TEXT NOT NULL,
            PRIMARY KEY (filename, solution, line)
        );
    """)
    conn.commit()

def extract_functions_from_solver(solver_path):
    """
    Extracts all function calls inside 'solve_*' functions in solver.py.
    Returns a list of tuples with function details.
    """
    with open(solver_path, "r") as f:
        lines = f.readlines()

    solutions = []  # Stores extracted solutions
    filename = None
    solution_counter = {}  # Dictionary to track solution numbers for each file
    inside_function = False  # Track whether we are inside a function
    function_line_number = 0  # Line number inside the function

    for i, line in enumerate(lines):
        line = line.strip()

        # Match function definitions: def solve_67a3c6ac(I):
        match = re.match(r"def solve_([a-f0-9]+)\(I\):", line)
        if match:
            filename = match.group(1)  # Extract the problem filename
            solution_counter[filename] = solution_counter.get(filename, -1) + 1  # Increment for new solutions
            inside_function = True  # We are now inside a function
            function_line_number = 1  # Reset function line counter
            continue

        if inside_function:
            if not line or line.startswith("return"):  # Stop processing after return statement
                inside_function = False
                continue

            # Extract function call components
            match_func = re.match(r"(\w+)\s*=\s*([\w\.]+)\((.*?)\)", line)
            if match_func:
                return_value = match_func.group(1)  # e.g., "O"
                function = match_func.group(2)  # e.g., "replace"
                params = match_func.group(3).split(",")  # e.g., ["I", "SIX", "TWO"]

                # Clean params (strip spaces and handle empty cases)
                params = [p.strip() for p in params if p.strip()] + [None] * (5 - len(params))

                solutions.append((
                    filename,
                    solution_counter[filename],  # solution number
                    function_line_number,  # Line inside the function (starting at 1)
                    function,
                    params[0], params[1], params[2], params[3], params[4],
                    return_value,
                    line  # Store full line for reference
                ))

            function_line_number += 1  # Increment function line count

    return solutions

def insert_solutions_into_db(conn, solutions):
    """
    Inserts extracted solutions into the 'solutions' table, avoiding duplicates.
    Converts all values to valid SQLite types (strings or NULL).
    """
    cur = conn.cursor()

    for solution in solutions:
        filename, solution_number, line, function, param_1, param_2, param_3, param_4, param_5, return_value, line_text = solution

        # Convert all non-None parameters to strings
        param_1 = str(param_1) if param_1 is not None else None
        param_2 = str(param_2) if param_2 is not None else None
        param_3 = str(param_3) if param_3 is not None else None
        param_4 = str(param_4) if param_4 is not None else None
        param_5 = str(param_5) if param_5 is not None else None
        return_value = str(return_value) if return_value is not None else None
        function = str(function)
        line_text = str(line_text)

        # Check if this solution already exists
        cur.execute("""
            SELECT COUNT(*) FROM solutions
            WHERE filename = ? AND solution = ? AND line = ?
        """, (filename, solution_number, line))

        if cur.fetchone()[0] > 0:
            print(f"Skipping {filename} - solution {solution_number}, line {line} (already exists).")
            continue  # Skip duplicates

        # Insert new solution
        cur.execute("""
            INSERT INTO solutions (filename, solution, line, function, 
                                  param_1, param_2, param_3, param_4, param_5, return_value, line_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (filename, solution_number, line, function, param_1, param_2, param_3, param_4, param_5, return_value, line_text))

    conn.commit()

def main_fill_solutions(solver_path, db_path="../../db/database.db"):
    """
    Extracts solutions from solver.py and stores them in the database.
    """
    conn = sqlite3.connect(db_path)
    create_solutions_table(conn)

    solutions = extract_functions_from_solver(solver_path)
    insert_solutions_into_db(conn, solutions)

    conn.close()
    print(f"✅ Successfully inserted {len(solutions)} solutions into 'solutions' table.")

if __name__ == "__main__":
    main_fill_solutions("./solvers.py")