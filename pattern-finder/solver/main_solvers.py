import os
import json
import inspect
import tqdm

import arc_types
import constants
import dsl
import tests
import solvers

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "solver")))


def get_data(train=True):
    path = f'../data/{"training" if train else "evaluation"}'
    data = {}
    for fn in os.listdir(path):
        with open(f'{path}/{fn}') as f:
            data[fn.rstrip('.json')] = json.load(f)
    ast = lambda g: tuple(tuple(r) for r in g)
    return {
        'train': {k: [{
            'input': ast(e['input']),
            'output': ast(e['output']),
        } for e in v['train']] for k, v in data.items()},
        'test': {k: [{
            'input': ast(e['input']),
            'output': ast(e['output']),
        } for e in v['test']] for k, v in data.items()}
    }


def get_functions(path):
    """ returns a list of available functions """
    with open(path, 'r') as f:
        code = f.read()
    functions = []
    for row in code.split('\n'):
        if row.startswith('def '):
            function = row.split('def ')[1].split('(')[0]
            functions.append(function)
    return functions


def run_dsl_tests(dsl_module, test_module):
    """ Test DSL primitives, but ignore missing tests """
    dsl_functions = get_functions(dsl_module.__file__)
    test_functions = get_functions(test_module.__file__)

    expected = set([f'test_{f}' for f in dsl_functions])
    actual = set(test_functions)

    missing_tests = expected - actual
    extra_tests = actual - expected

    if missing_tests:
        print(f"⚠️ Ignoring missing tests: {missing_tests}")
    if extra_tests:
        print(f"⚠️ Extra tests found but not required: {extra_tests}")

    available_tests = expected.intersection(actual)  # Only keep existing tests
    for fun in available_tests:
        getattr(test_module, fun)()  # Run only available tests


def verify_solvers_formatting(solvers_module, dsl_module):
    """ tests the implementd solvers for formatting """
    with open('constants.py', 'r') as f:
        constants = [c.split(' = ')[0] for c in f.readlines() if ' = ' in c]
    definitions = {
        function: inspect.getsource(getattr(solvers_module, function)) \
            for function in get_functions(solvers_module.__file__)
    }
    dsl_interface = get_functions(dsl_module.__file__)
    n_correct = 0
    n = len(definitions)
    for key, definition in definitions.items():
        try:
            lines = definition.split('\n')
            assert lines[0] == f'def {key}(I):'
            assert lines[-1] == ''
            variables = set()
            calls = set()
            for line in lines[1:-2]:
                variable, call = line.lstrip().split(' = ')
                function, args = call.split('(')
                assert variable not in dsl_interface
                assert variable not in variables
                assert call not in calls
                variables.add(variable)
                calls.add(call)
                assert function in dsl_interface or function in variables
                assert args[-1] == ')'
                args = [args[:-1]] if ',' not in args else args[:-1].split(', ')
                for arg in args:
                    assert any([
                        arg in variables, arg in dsl_interface,
                        arg in constants, arg == 'I'
                    ])
            for v in variables:
                assert sum([
                    definition.count(vs) for vs in [
                        f'({v})', f'({v}, ', f', {v})',
                        f', {v}, ', f' {v} = ', f' {v}('
                    ]
                ]) > 1 or v == 'O'
            n_correct += 1
        except:
            pass
    print(f'{n_correct} out of {n} solvers formatted correctly.')


def verify_solvers_correctness(data, solvers_module):
    """
    Tests the implemented solvers for correctness and prints details on failures.
    """
    n_correct = 0
    n_total = len(data["train"])
    incorrect_solvers = []  # Store incorrect solvers for reporting

    for key in tqdm.tqdm(data['train'].keys(), total=n_total):
        task = data['train'][key] + data['test'][key]

        try:
            solver = getattr(solvers_module, f'solve_{key}')
            all_passed = True  # Track if all cases pass for this solver

            for i, ex in enumerate(task):
                try:
                    output = solver(ex['input'])  # Run the solver
                    if output != ex['output']:  # Check if the result is incorrect
                        all_passed = False
                        incorrect_solvers.append({
                            "solver": f"solve_{key}",
                            "test_case": i + 1,
                            "input": ex['input'],
                            "expected_output": ex['output'],
                            "actual_output": output
                        })
                except Exception as e:
                    all_passed = False
                    incorrect_solvers.append({
                        "solver": f"solve_{key}",
                        "test_case": i + 1,
                        "input": ex['input'],
                        "error": str(e)
                    })

            if all_passed:
                n_correct += 1

        except AttributeError:
            print(f"⚠️ No solver found for task: {key}")

    print(f'\n✅ {n_correct} out of {n_total} tasks solved correctly.')

    # Print details about incorrect solvers
    if incorrect_solvers:
        print("\n❌ Incorrect Solvers:")
        for err in incorrect_solvers:
            print(f"\n🔴 Solver: {err['solver']} | Test Case: {err['test_case']}")
            print(f"   📥 Input: {err['input']}")
            if "error" in err:
                print(f"   ⚠️ Error: {err['error']}")
            else:
                print(f"   ✅ Expected Output: {err['expected_output']}")
                print(f"   ❌ Actual Output: {err['actual_output']}")

def main():
    data = get_data(train=True)
    #run_dsl_tests(dsl, tests)
    verify_solvers_formatting(solvers, dsl)
    verify_solvers_correctness(data, solvers)


if __name__ == '__main__':
    main()
