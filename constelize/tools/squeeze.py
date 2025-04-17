from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple

from constelize.core.binding import ArgumentBinding, BindingStatus, LinkCandidate
from constelize.core.procedure import ActionInstance, Procedure


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
def squeeze_with_unresolved(train_procs: List[Procedure]) -> List[Procedure]:
    """
    Build generic procedures (one per branch) from a list of per‑train procedures
    without relying on positional indices. Steps are merged (forked) based on action
    identity and constant‑binding signature. All id translations occur on the fly.

    This verbose version logs every decision.
    """
    print("\n═══════════════════════════════════════════════════════════════")
    print("🎬 squeeze_with_unresolved – starting")
    print(f"• Received {len(train_procs)} train procedure(s)")
    if not train_procs:
        print("  → Nothing to do. Returning []")
        return []

    # Data structures:
    branches: List[Dict[str, ActionInstance]] = [{}]  # start with one empty branch
    action_counters: Dict[str, int] = defaultdict(int)  # for unique id generation per action
    train_to_generic_id: Dict[str, str] = {}  # maps train step id -> generic step id

    # First pass: iterate over train procedures and build/fork branches
    for proc_idx, proc in enumerate(train_procs):
        print(f"\n────────────────────────────────────────────")
        print(f"📑 Processing train procedure #{proc_idx} (id={proc.id})")
        for step_idx, step in enumerate(proc.steps.values()):
            print(f"\n  🔹 Train step #{step_idx} (id={step.id}, action={step.action.name})")
            new_branches: List[Dict[str, ActionInstance]] = []
            for branch_idx, branch in enumerate(branches):
                print(f"    • Considering branch #{branch_idx} (contains {len(branch)} step(s))")
                # For each binding in this train step, update its source_procedure_id according to
                # the mapping from previously processed steps.
                for b_name, bind in step.bindings.items():
                    if bind.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE):
                        old_src = bind.source_procedure_id
                        if old_src:
                            new_src = train_to_generic_id.get(old_src, old_src)
                            if new_src != old_src:
                                print(f"      ↻ Remapping binding '{b_name}': {old_src} → {new_src}")
                                bind.source_procedure_id = new_src
                                if bind.candidates is not None:
                                    for cand in bind.candidates:
                                        if cand.producer_id == old_src:
                                            print(f"         ↻ Also remapping candidate from {old_src} → {new_src}")
                                            cand.producer_id = new_src

                # Try to reuse an equivalent generic step in this branch.
                equiv = _find_equivalent(step, list(branch.values()))
                if equiv:
                    print(f"      ✅ Found equivalent generic step {equiv.id}; reusing it.")
                    train_to_generic_id[step.id] = equiv.id
                    new_branches.append(branch)
                    continue

                # Otherwise, fork the branch with a deep copy of the step.
                copied = copy.deepcopy(step)
                action_counters[copied.action.id] += 1
                copied.id = f"{copied.action.id}#{action_counters[copied.action.id]}"
                train_to_generic_id[step.id] = copied.id
                print(f"      ➕ No equivalent – creating new generic step {copied.id}")
                # Update producers in the new branch:
                for bind in copied.bindings.values():
                    if bind.binding == BindingStatus.VARIABLE and bind.source_procedure_id:
                        prod = branch.get(bind.source_procedure_id)
                        if prod and copied.id not in prod.used_by:
                            prod.used_by.append(copied.id)
                            print(f"         • Updated producer {prod.id}.used_by ← {copied.id}")
                branch2 = branch.copy()
                branch2[copied.id] = copied
                new_branches.append(branch2)
                print(f"      ↳ Forked branch now has {len(branch2)} step(s)")
            branches = new_branches
            print(f"    → After processing step, total branches: {len(branches)}")

    # Second pass: ensure that all VARIABLE/MULTIPLE bindings’ source_procedure_ids (and their candidate lists)
    # are properly remapped using the global train_to_generic_id map.
    print("\n────────────────────────────────────────────")
    print("🛠 Second pass: re-updating VARIABLE/MULTIPLE bindings")
    for branch in branches:
        for step in branch.values():
            for bind in step.bindings.values():
                if bind.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE) and bind.source_procedure_id:
                    old_source = bind.source_procedure_id
                    new_source = train_to_generic_id.get(old_source, old_source)
                    if new_source != old_source:
                        print(f"      ↻ Updating binding in step {step.id}: {old_source} → {new_source}")
                        bind.source_procedure_id = new_source
                    if bind.candidates is not None:
                        for cand in bind.candidates:
                            if cand.producer_id in train_to_generic_id:
                                old_cand = cand.producer_id
                                cand.producer_id = train_to_generic_id[old_cand]
                                print(
                                    f"         ↻ Updating candidate in step {step.id}: {old_cand} → {cand.producer_id}")
                update_source_procedure_recursive(bind, train_to_generic_id)

    # Final assembly: build Procedure objects, order steps, and mark the last step with END=True.
    print("\n────────────────────────────────────────────")
    print("📦 Building final generic Procedure objects")
    generic_procs: List[Procedure] = []
    for idx, step_dict in enumerate(branches, 1):
        _sanitise_branch(step_dict)  # Only wipe bindings with UNRESOLVED status
        print(f"\n  🛠 Branch #{idx}: contains {len(step_dict)} step(s)")
        ordered_steps = _order_steps(step_dict)
        if ordered_steps:
            last_key = list(ordered_steps.keys())[-1]
            ordered_steps[last_key].END = True
            print(f"     • Marked step {ordered_steps[last_key].id} as END")
        proc_id = f"generic_proc_{idx}"
        generic_procs.append(Procedure(id=proc_id, steps=ordered_steps))
        print(f"     → Created Procedure '{proc_id}'")

    print("\n🎉 squeeze_with_unresolved – done. Generated "
          f"{len(generic_procs)} generic procedure(s)")
    print("═══════════════════════════════════════════════════════════════\n")
    return generic_procs


def normalize_procedures_with_levels(procs: List[Procedure]) -> List[Procedure]:
    """Return copies of *procs* whose steps are sorted topologically."""
    norm = []
    for p in procs:
        ordered = _order_steps({s.id: s for s in p.steps.values()})
        norm.append(Procedure(id=p.id, steps=ordered))
    return norm

def remove_unresolved_actions_from_generic(branch: Dict[str, ActionInstance]) -> Dict[str, ActionInstance]:
    """
    Return a new branch dictionary that excludes any ActionInstance that has at least one binding
    with status UNRESOLVED. (These actions are considered unsolved.)
    """
    print("  [remove_unresolved_actions_from_generic] Scanning branch for unsolved actions:")
    new_branch = {}
    for sid, step in branch.items():
        unresolved = False
        for bname, bind in step.bindings.items():
            if bind.binding == BindingStatus.UNRESOLVED:
                print(f"    → Removing step {step.id} due to unresolved binding '{bname}'.")
                unresolved = True
                break
        if not unresolved:
            new_branch[sid] = step
    return new_branch
