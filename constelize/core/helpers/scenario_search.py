from typing import List, Tuple, Dict
from copy import deepcopy
from itertools import product
from constelize.core.scenario import Scenario
from constelize.core.binding import ArgumentBinding, BindingStatus, LinkCandidate, CandidateStatus


def collect_multi_bindings(scenario: Scenario) -> List[Tuple[str, str, str, str, ArgumentBinding]]:
    """
    Returns a list of all (rule_id, proc_id, step_id, arg_name, binding)
    where the binding has MULTIPLE candidates.
    """
    results = []
    for rule_id, rule in scenario.rules.items():
        for proc_id, proc in rule.procedures.items():
            for step_id, step in proc.steps.items():
                for arg_name, binding in step.bindings.items():
                    if binding.binding == BindingStatus.MULTIPLE and binding.candidates:
                        results.append((rule_id, proc_id, step_id, arg_name, binding))
    return results


def generate_all_scenario_variants(draft: Scenario, max_variants: int = 1000) -> List[Scenario]:
    """
    Generates all possible scenarios by resolving each MULTIPLE ArgumentBinding
    using the Cartesian product of all available candidates.
    """
    multi_bindings = collect_multi_bindings(draft)

    if not multi_bindings:
        return [deepcopy(draft)]

    # List of lists of candidates per binding
    candidate_lists = [binding.candidates for (_, _, _, _, binding) in multi_bindings]

    # Compute Cartesian product of all combinations
    all_combinations = list(product(*candidate_lists))
    all_combinations = all_combinations[:max_variants]  # Optional cap

    variants = []

    for idx, combo in enumerate(all_combinations):
        variant = deepcopy(draft)
        variant.id = f"{draft.id}_variant_{idx}"

        for i, (rule_id, proc_id, step_id, arg_name, binding) in enumerate(multi_bindings):
            selected_candidate = combo[i]
            var_binding = variant.rules[rule_id].procedures[proc_id].steps[step_id].bindings[arg_name]

            # Update binding to LINKED with selected candidate
            var_binding.binding = BindingStatus.LINKED
            var_binding.value = selected_candidate.var_name
            var_binding.source_procedure_id = selected_candidate.producer_id

            # Optionally mark candidate as being used
            selected_candidate.status = CandidateStatus.PENDING

        variants.append(variant)

    return variants