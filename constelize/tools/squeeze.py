# constelize/tools/squeeze.py

from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple, Union

from constelize.core.binding import ArgumentBinding, BindingStatus, LinkCandidate
from constelize.core.procedure import ActionInstance, Procedure
from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING


###############################################################################
# Utilities
###############################################################################

def _make_hashable(val):
    """Recursively turn *val* into a hashable representation."""
    if isinstance(val, list):
        return tuple(_make_hashable(x) for x in val)
    if isinstance(val, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in val.items()))
    if isinstance(val, set):
        return tuple(sorted(_make_hashable(x) for x in val))
    return val


def _constant_signature(step: ActionInstance) -> Tuple:
    """Return a tuple that uniquely identifies the constant bindings of *step*."""
    sig = []
    for name in sorted(step.bindings.keys()):
        b = step.bindings[name]
        if b.binding == BindingStatus.CONSTANT:
            sig.append((name, _make_hashable(b.value)))
    return tuple(sig)


def _find_equivalent(step: ActionInstance, candidates: List[ActionInstance]) -> ActionInstance | None:
    """
    Return the first candidate that has the same action.id and constant signature as *step*.
    """
    sig = _constant_signature(step)
    for cand in candidates:
        if cand.action.id == step.action.id and _constant_signature(cand) == sig:
            return cand
    return None


###############################################################################
# Topological helpers (kept as is)
###############################################################################

def _is_input_grid_only(inst: ActionInstance) -> bool:
    """True if every binding is either INPUT_GRID or CONSTANT."""
    for b in inst.bindings.values():
        if b.binding not in {BindingStatus.INPUT_GRID, BindingStatus.CONSTANT}:
            return False
    return True


def topological_levels(instances: Dict[str, ActionInstance]) -> List[List[str]]:
    """Return lists of step‑ids grouped by parallelisable level."""
    # 1. Build dependency graph.
    graph = defaultdict(set)
    in_deg = defaultdict(int, {sid: 0 for sid in instances})
    for inst in instances.values():
        for bind in inst.bindings.values():
            if bind.binding == BindingStatus.VARIABLE and bind.source_procedure_id:
                graph[bind.source_procedure_id].add(inst.id)
                in_deg[inst.id] += 1

    # 2. Perform Kahn’s algorithm.
    levels, cur = [], [n for n, d in in_deg.items() if d == 0]
    seen = set()
    while cur:
        levels.append(cur)
        nxt = []
        for n in cur:
            seen.add(n)
            for m in graph[n]:
                in_deg[m] -= 1
                if in_deg[m] == 0:
                    nxt.append(m)
        cur = nxt
    if len(seen) != len(instances):
        levels = [[sid] for sid in instances]

    # 3. Special re‑arrangement: collect INPUT_GRID‑only steps and END steps.
    input_grid_steps, end_steps = [], []
    for lvl in levels:
        for sid in list(lvl):  # iterate over a copy
            inst = instances[sid]
            if inst.END:
                end_steps.append(sid)
                lvl.remove(sid)
            elif _is_input_grid_only(inst):
                input_grid_steps.append(sid)
                lvl.remove(sid)
    levels = [lvl for lvl in levels if lvl]
    if input_grid_steps:
        levels.insert(0, sorted(input_grid_steps))
    if end_steps:
        levels.append(sorted(end_steps))
    return levels


def _order_steps(step_dict: Dict[str, ActionInstance]) -> Dict[str, ActionInstance]:
    """Return step_dict sorted in topological order (levels then id)."""
    lvls = topological_levels(step_dict)
    ordered_ids = [sid for lvl in lvls for sid in sorted(lvl)]
    return {f"step_{i + 1}": step_dict[sid] for i, sid in enumerate(ordered_ids)}


###############################################################################
# Sanitisation helper
###############################################################################
def _sanitise_branch(step_dict: Dict[str, ActionInstance]) -> None:
    """
    In place:
      • Set step.output_value = None.
      • For each binding, only reset binding.value if its binding status is UNRESOLVED.
      (If the binding is VARIABLE, MULTIPLE, CONSTANT, or INPUT_GRID, we consider it solved.)
    """
    for step in step_dict.values():
        step.output_value = None
        for bind in step.bindings.values():
            if bind.binding == BindingStatus.UNRESOLVED:
                bind.value = None

def update_source_procedure_recursive(binding, id_remap):
    if binding.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE) and binding.source_procedure_id:
        if binding.source_procedure_id in id_remap:
            old_id = binding.source_procedure_id
            binding.source_procedure_id = id_remap[old_id]
            print(f"         ↻ Deep remap: {old_id} → {binding.source_procedure_id}")

    if binding.binding == BindingStatus.COMPOUND:
        if isinstance(binding.sub_bindings, dict):
            for sub in binding.sub_bindings.values():
                update_source_procedure_recursive(sub, id_remap)
        elif isinstance(binding.sub_bindings, list):
            for sub in binding.sub_bindings:
                update_source_procedure_recursive(sub, id_remap)

###############################################################################
# New squeeze implementation – NO INDEX ALIGNMENT; renamed to squeeze_with_unresolved
###############################################################################

def get_all_nested_source_ids(binding: Union[ArgumentBinding, dict, list]) -> set[str]:
    ids = set()
    if isinstance(binding, ArgumentBinding):
        if binding.source_procedure_id:
            ids.add(binding.source_procedure_id)
        ids.update(get_all_nested_source_ids(binding.sub_bindings))
    elif isinstance(binding, dict):
        for sub in binding.values():
            ids.update(get_all_nested_source_ids(sub))
    elif isinstance(binding, list):
        for item in binding:
            ids.update(get_all_nested_source_ids(item))
    return ids

def is_step_still_used(step_id: str, branch: dict) -> bool:
    for s in branch.values():
        for b in s.bindings.values():
            if step_id in get_all_nested_source_ids(b):
                return True
    return False

def squeeze_with_unresolved(train_procs: List[Procedure]) -> List[Procedure]:
    from copy import deepcopy
    from collections import defaultdict

    print("\n🎨 squeeze_with_unresolved – updating producer/candidate ids")

    if not train_procs:
        return []

    branches: List[Dict[str, ActionInstance]] = [{}]
    action_counters: Dict[str, int] = defaultdict(int)
    train_to_generic_id: Dict[str, str] = {}

    def replace_nested_source_ids(binding: Union[ArgumentBinding, dict, list], mapping: dict, current_consumer_id: str, branch: dict):
        if isinstance(binding, ArgumentBinding):
            if binding.source_procedure_id in mapping:
                old_id = binding.source_procedure_id
                new_id = mapping[old_id]
                print(f"🔁 Replacing source_procedure_id {old_id} → {new_id}")
                binding.source_procedure_id = new_id
                if new_id in branch:
                    if current_consumer_id not in branch[new_id].used_by:
                        branch[new_id].used_by.append(current_consumer_id)
            replace_nested_source_ids(binding.sub_bindings, mapping, current_consumer_id, branch)
        elif isinstance(binding, dict):
            for sub in binding.values():
                replace_nested_source_ids(sub, mapping, current_consumer_id, branch)
        elif isinstance(binding, list):
            for item in binding:
                replace_nested_source_ids(item, mapping, current_consumer_id, branch)

    for proc in train_procs:
        for step in proc.steps.values():
            new_branches = []
            for branch in branches:
                for bind in step.bindings.values():
                    if bind.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE):
                        old_id = bind.source_procedure_id
                        if old_id and old_id in train_to_generic_id:
                            bind.source_procedure_id = train_to_generic_id[old_id]
                        if bind.candidates:
                            for cand in bind.candidates:
                                if cand.producer_id in train_to_generic_id:
                                    print(f"↻ Updating candidate: {cand.producer_id} → {train_to_generic_id[cand.producer_id]}")
                                    cand.producer_id = train_to_generic_id[cand.producer_id]

                found = None
                for b in branch.values():
                    if b.action.id == step.action.id:
                        const_match = all(
                            b.bindings[k].value == step.bindings[k].value
                            for k in b.bindings
                            if b.bindings[k].binding == BindingStatus.CONSTANT
                        )
                        if const_match:
                            found = b
                            break

                if found:
                    train_to_generic_id[step.id] = found.id
                    new_branches.append(branch)
                    continue

                copied = deepcopy(step)
                action_counters[copied.action.id] += 1
                copied.id = f"{copied.action.id}#{action_counters[copied.action.id]}"
                train_to_generic_id[step.id] = copied.id

                # 🔁 Met à jour les source ids + restaure manuellement les constantes si absentes
                for b in copied.bindings.values():
                    replace_nested_source_ids(b, train_to_generic_id, copied.id, branch)
                    if b.binding == BindingStatus.CONSTANT and b.value is None:
                        original_bind = step.bindings.get(b.name)
                        if original_bind and original_bind.binding == BindingStatus.CONSTANT:
                            b.value = original_bind.value
                            print(f"💾 Restored constant value for {b.name} = {b.value}")

                for b in copied.bindings.values():
                    replace_nested_source_ids(b, train_to_generic_id, copied.id, branch)
                    if b.candidates:
                        for cand in b.candidates:
                            if cand.producer_id in train_to_generic_id:
                                print(f"↻ Updating candidate: {cand.producer_id} → {train_to_generic_id[cand.producer_id]}")
                                cand.producer_id = train_to_generic_id[cand.producer_id]

                if copied.output_type is None:
                    copied.output_type = copied.action.output_type

                if copied.action.id == "get_start_input":
                    for b in copied.bindings.values():
                        if b.binding == BindingStatus.INPUT_GRID and b.value is None and copied.output_value:
                            b.value = copied.output_value

                branch2 = branch.copy()
                branch2[copied.id] = copied
                new_branches.append(branch2)
            branches = new_branches

    generic_procs = []
    for idx, branch in enumerate(branches):
        for s in branch.values():
            s.output_value = None
            for b in s.bindings.values():
                if b.binding == BindingStatus.UNRESOLVED:
                    b.value = None

        # 🧹 Clean up unused 'used_by' references pointing to removed steps
        step_ids = set(branch.keys())
        for s in branch.values():
            if s.used_by:
                s.used_by = [uid for uid in s.used_by if uid in step_ids]

        # 🧹 Remove truly unused steps unless they produce final output
        final_output_ids = {s.id for s in branch.values() if s.END or s.isToOutput}
        to_remove = [
            sid for sid in branch
            if not is_step_still_used(sid, branch) and sid not in final_output_ids
        ]
        for sid in to_remove:
            if branch[sid].action.id == "get_start_input":
                continue  # 🔒 Never remove get_start_input
            print(f"🧹 Removing truly unused producer: {sid} from generic_proc_{idx + 1}")
            branch.pop(sid)

        proc = Procedure(id=f"generic_proc_{idx+1}", steps=branch)

        print_bindings_recursive(proc)

        generic_procs.append(proc)

    return generic_procs


def print_bindings_recursive(proc):
    print("\n🧪 Post-Squeeze bindings inspection:")

    def print_binding(path, binding, level=1):
        indent = "    " * level
        src = f", source → {binding.source_procedure_id}" if binding.source_procedure_id else ""
        print(f"{indent}🔸 {path} → {binding.binding}, value={binding.value}{src}")

        if binding.binding == BindingStatus.COMPOUND:
            if isinstance(binding.sub_bindings, list):
                for i, sub in enumerate(binding.sub_bindings):
                    print_binding(f"{path}[{i}]", sub, level + 1)
            elif isinstance(binding.sub_bindings, dict):
                for k, sub in binding.sub_bindings.items():
                    print_binding(f"{path}.{k}", sub, level + 1)

    for sid, step in proc.steps.items():
        for arg, b in step.bindings.items():
            print_binding(f"{sid}.{arg}", b)


def normalize_procedures_with_levels(procs: List[Procedure]) -> List[Procedure]:
    """Return copies of *procs* whose steps are sorted topologically."""
    norm = []
    for p in procs:
        ordered = _order_steps({s.id: s for s in p.steps.values()})
        norm.append(Procedure(id=p.id, steps=ordered))
    return norm

def remove_unresolved_actions_from_generic(branch: Dict[str, ActionInstance]) -> Dict[str, ActionInstance]:
    """
    Return a new branch dictionary that excludes any ActionInstance with unresolved bindings.
    Steps marked as END=True are protected from removal.
    Also preserves steps that are used indirectly by protected actions (transitive closure).
    """
    print("\n🔍 [remove_unresolved_actions_from_generic] Scanning branch for unsolved actions...")

    def has_unresolved_binding(binding) -> bool:
        if binding.binding == BindingStatus.UNRESOLVED:
            return True
        if binding.binding == BindingStatus.COMPOUND:
            if isinstance(binding.sub_bindings, list):
                return any(has_unresolved_binding(sub) for sub in binding.sub_bindings)
            elif isinstance(binding.sub_bindings, dict):
                return any(has_unresolved_binding(sub) for sub in binding.sub_bindings.values())
        return False

    protected = set()
    unresolved = set()

    # Étape 1 — Marquer les END=True
    for sid, step in branch.items():
        if getattr(step, "END", False):
            print(f"    ✅ Step {sid} is protected (END=True)")
            protected.add(sid)

    # Étape 2 — Marquer ceux qui n'ont PAS de bindings non résolus
    for sid, step in branch.items():
        print(f"  🔎 Inspecting step: {step.id} ({step.action.name})")
        for bname, bind in step.bindings.items():
            print(f"    • Binding '{bname}' → status: {bind.binding.name}, value: {bind.value}")
            if has_unresolved_binding(bind):
                print(f"    ❌ Step {step.id} has unresolved binding: '{bname}'")
                unresolved.add(sid)
                break
        else:
            if sid not in protected:
                print(f"    ✅ Step {step.id} is tentatively kept.")
                protected.add(sid)

    # Étape 3 — Propagation : protéger tous les producteurs liés aux protégés
    def mark_dependencies(sid: str):
        if sid in protected:
            return
        if sid not in branch:
            print(f"⚠️ Skipping unknown source step: {sid}")
            return
        step = branch[sid]
        for b in step.bindings.values():
            if b.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE):
                src_id = b.source_procedure_id
                if src_id and src_id not in protected:
                    print(f"    🔄 Propagating protection to {src_id} (used by {sid})")
                    protected.add(src_id)
                    mark_dependencies(src_id)

    for sid in list(protected):
        mark_dependencies(sid)

    # Étape 4 — Construction de la nouvelle branche
    new_branch = {}
    for sid in protected:
        if sid not in unresolved and sid in branch:
            new_branch[sid] = branch[sid]
        elif sid in unresolved:
            print(f"    ⚠️ Step {sid} was protected but contains unresolved bindings — skipped.")

    print(f"  ✅ Final branch size after protection + unresolved filter: {len(new_branch)} (from {len(branch)})")
    return new_branch