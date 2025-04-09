from constelize.core.procedure import Procedure, ArgumentBinding, BindingStatus
from copy import deepcopy
from typing import List
import itertools


def generate_procedure_variants(base: Procedure) -> List[Procedure]:
    variants = []

    # Collect candidate combinations for MULTIPLE bindings
    multi_bindings = []

    for step in base.steps.values():
        for name, binding in step.bindings.items():
            if binding.binding == BindingStatus.MULTIPLE:
                step_id = step.id
                candidates = binding.candidates  # each candidate is (value, status, source_procedure_id)
                multi_bindings.append((step_id, name, candidates))

    if not multi_bindings:
        return [base]

    # Group by step and argument name
    grouped = {}
    for step_id, arg_name, candidates in multi_bindings:
        grouped.setdefault((step_id, arg_name), []).extend(candidates)

    # Build cartesian product of candidate combinations
    keys = list(grouped.keys())
    all_combinations = itertools.product(*grouped.values())

    for combination in all_combinations:
        variant = deepcopy(base)

        for (step_id, arg_name), candidate in zip(keys, combination):
            value, status, source_id = candidate
            binding = ArgumentBinding(
                name=arg_name,
                value=value,
                binding=status,
                source_procedure_id=source_id
            )
            variant.steps[step_id].bindings[arg_name] = binding

        variants.append(variant)

    return variants
