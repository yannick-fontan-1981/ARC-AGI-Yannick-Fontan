from typing import List, Dict
from collections import defaultdict, deque
from itertools import product
from constelize.core.procedure import Procedure, ActionInstance
from constelize.core.binding import ArgumentBinding, BindingStatus


def topological_levels(instances: Dict[str, ActionInstance]) -> List[List[str]]:
    """
    Retourne les étapes regroupées par niveaux topologiques (actions parallélisables).
    Chaque niveau contient les étapes pouvant être exécutées en parallèle.
    """
    graph = defaultdict(set)
    in_degree = defaultdict(int)

    for instance_id in instances:
        in_degree[instance_id] = 0

    for instance in instances.values():
        for binding in instance.bindings.values():
            if binding.binding == BindingStatus.VARIABLE and binding.source_procedure_id:
                source = binding.source_procedure_id
                target = instance.id
                graph[source].add(target)
                in_degree[target] += 1

    levels: List[List[str]] = []
    current_level = [node for node, deg in in_degree.items() if deg == 0]
    visited = set()

    while current_level:
        levels.append(current_level)
        next_level = []

        for node in current_level:
            visited.add(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_level.append(neighbor)

        current_level = next_level

    if len(visited) != len(instances):
        print("⚠️ Cycle detected or incomplete sort. Falling back to flat topological order.")
        return [[node] for node in visited]

    return levels


def normalize_procedures_with_levels(procedures: List[Procedure]) -> List[Procedure]:
    normalized = []
    for proc in procedures:
        id_based_steps = {step.id: step for step in proc.steps.values()}
        levels = topological_levels(id_based_steps)
        flat_ordered_ids = [step_id for group in levels for step_id in group]
        sorted_steps = {step_id: id_based_steps[step_id] for step_id in flat_ordered_ids}
        normalized_proc = Procedure(id=proc.id, steps=sorted_steps)
        normalized.append(normalized_proc)

        print(f"🧭 {proc.id} topological levels:")
        for i, group in enumerate(levels):
            print(f"  Niveau {i}: {group}")

    return normalized

def squeeze_with_remapped_sources(procedures: List[Procedure]) -> List[Procedure]:
    if not procedures:
        return []

    aligned_steps = defaultdict(list)
    for proc in procedures:
        for i, step in enumerate(proc.steps.values()):
            aligned_steps[i].append(step)

    generic_procedures = [{}]
    action_counters = defaultdict(int)
    global_id_remap: Dict[str, str] = {}

    print("🔄 Starting squeeze_with_remapped_sources...")

    for i in sorted(aligned_steps.keys()):
        step_group = aligned_steps[i]
        action_names = {step.action.name for step in step_group}
        print(f"\n🧱 Step group {i + 1}: {action_names}")

        has_get_input = "Get Input Grid" in action_names
        if len(action_names) != 1:
            if has_get_input:
                print("ℹ️  Including 'Get Input Grid' despite divergence.")
                step_group = [s for s in step_group if s.action.name == "Get Input Grid"]
            else:
                print("⚠️  Diverging actions in step group — skipping")
                continue

        action_ref = step_group[0].action
        bindings_by_arg = defaultdict(set)
        types_by_arg = {}
        original_source_ids_by_arg = {}
        original_binding_map = {}

        for step in step_group:
            for arg_name, binding in step.bindings.items():
                types_by_arg[arg_name] = binding.type
                original_binding_map[arg_name] = binding
                if binding.binding == BindingStatus.CONSTANT:
                    bindings_by_arg[arg_name].add(binding.value)
                elif binding.binding == BindingStatus.VARIABLE and binding.source_procedure_id:
                    bindings_by_arg[arg_name].add(None)
                    original_source_ids_by_arg[arg_name] = binding.source_procedure_id
                else:
                    bindings_by_arg[arg_name].add(None)

        binding_names = list(bindings_by_arg.keys())
        value_combinations = product(*[sorted(vals, key=lambda v: str(v)) for vals in bindings_by_arg.values()])

        new_generics = []
        for combo in value_combinations:
            bindings = {}
            action_counters[action_ref.name] += 1
            new_id = f"{action_ref.id}#{action_counters[action_ref.name]}"

            print(f"\n🔧 Generating new instance {new_id} for action: {action_ref.name}")
            print(f"   ➤ Binding combo: {dict(zip(binding_names, combo))}")

            for gproc in generic_procedures:
                for arg_name, val in zip(binding_names, combo):
                    b_type = types_by_arg[arg_name]
                    original_binding = original_binding_map[arg_name]

                    if val is not None:
                        binding = ArgumentBinding(
                            name=arg_name,
                            type=b_type,
                            binding=BindingStatus.CONSTANT,
                            value=val
                        )
                    elif arg_name in original_source_ids_by_arg:
                        original_source_id = original_source_ids_by_arg[arg_name]
                        resolved_id = global_id_remap.get(original_source_id)

                        if resolved_id is None:
                            print(f"⚠️ Cannot remap original ID '{original_source_id}' → source_procedure_id is None")
                            binding_status = BindingStatus.UNRESOLVED
                        else:
                            print(f"🔁 Remapped {original_source_id} → {resolved_id}")
                            binding_status = BindingStatus.VARIABLE

                        binding = ArgumentBinding(
                            name=arg_name,
                            type=b_type,
                            binding=binding_status,
                            value=None,
                            source_procedure_id=resolved_id,
                            candidates=original_binding.candidates
                        )
                    else:
                        binding = ArgumentBinding(
                            name=arg_name,
                            type=b_type,
                            binding=BindingStatus.UNRESOLVED,
                            value=None
                        )

                    bindings[arg_name] = binding

                action_instance = ActionInstance(
                    id=new_id,
                    action=action_ref,
                    bindings=bindings,
                    output_var=new_id,
                    output_type=action_ref.output_type,
                    used_by=[],
                )

                for step in step_group:
                    print(f"🔄 Remapping {step.id} → {new_id}")
                    global_id_remap[step.id] = new_id

                for b in bindings.values():
                    if b.binding == BindingStatus.VARIABLE and b.source_procedure_id:
                        if b.source_procedure_id in gproc:
                            print(f"📎 {b.source_procedure_id} → used_by → {new_id}")
                            gproc[b.source_procedure_id].used_by.append(new_id)

                new_proc = gproc.copy()
                new_proc[new_id] = action_instance
                new_generics.append(new_proc)

        generic_procedures = new_generics

    result = []
    for i, step_dict in enumerate(generic_procedures):
        proc_id = f"squeezed_proc_{i+1}"
        steps = list(step_dict.values())
        if steps:
            steps[-1].END = True  # ✅ Mark the final step with END=True
        proc = Procedure(
            id=proc_id,
            steps={f"step_{j+1}": step for j, step in enumerate(steps)}
        )
        result.append(proc)
        print(f"\n✅ {proc_id} generated with {len(proc.steps)} step(s): {[s.action.name for s in proc.steps.values()]}")
        if steps and steps[-1].END:
            print(f"  ➤ Marked {steps[-1].id} as END ✅")

    return result

