# constelize/tools/squeeze.py

from __future__ import annotations

import copy
import uuid
from collections import defaultdict, OrderedDict
from typing import Dict, List, Tuple, Union, Set, Any

from constelize.core.binding import ArgumentBinding, BindingStatus, LinkCandidate, Producer
from constelize.core.procedure import ActionInstance, Procedure
from constelize.tools.extract_common_attribute import extract_common_sprite_rows_criteria, \
    extract_common_sprite_values_criteria
from constelize.tools.fact_to_action_mapping import FACT_TO_ACTION_MAPPING, build_producer_action
import constelize.tools.binding_train_map as btm
from constelize.tools.registry_singleton import registry


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
    """Return lists of step-ids grouped by parallelisable level."""
    # 1. Build dependency graph, in-degree counts, and a seen_sources map to avoid duplicate edges.
    graph: Dict[str, Set[str]] = defaultdict(set)
    in_deg: Dict[str, int] = {sid: 0 for sid in instances}
    seen_sources: Dict[str, Set[str]] = defaultdict(set)

    for inst in instances.values():
        tgt = inst.id
        for bind in inst.bindings.values():
            src = bind.source_procedure_id
            if bind.binding in (BindingStatus.VARIABLE, BindingStatus.BUFFER) and src:
                # only add one edge per (src→tgt) pair
                if src not in seen_sources[tgt]:
                    graph[src].add(tgt)
                    in_deg[tgt] += 1
                    seen_sources[tgt].add(src)

    # 2. Perform Kahn’s algorithm.
    levels: List[List[str]] = []
    cur: List[str] = [n for n, d in in_deg.items() if d == 0]
    seen: Set[str] = set()
    while cur:
        levels.append(cur)
        nxt: List[str] = []
        for n in cur:
            seen.add(n)
            for m in graph[n]:
                in_deg[m] -= 1
                if in_deg[m] == 0:
                    nxt.append(m)
        cur = nxt

    # if there's a cycle (not all nodes seen), fall back to singleton levels
    if len(seen) != len(instances):
        levels = [[sid] for sid in instances]

    # 3. Special re-arrangement: collect INPUT_GRID-only steps and END steps.
    input_grid_steps: List[str] = []
    end_steps: List[str] = []
    for lvl in levels:
        for sid in list(lvl):
            inst = instances[sid]
            if inst.END:
                end_steps.append(sid)
                lvl.remove(sid)
            elif _is_input_grid_only(inst):
                input_grid_steps.append(sid)
                lvl.remove(sid)

    # remove any now-empty levels
    levels = [lvl for lvl in levels if lvl]

    # prepend INPUT_GRID-only and append END steps
    if input_grid_steps:
        levels.insert(0, sorted(input_grid_steps))
    if end_steps:
        levels.append(sorted(end_steps))

    return levels

def _order_steps(step_dict: Dict[str, ActionInstance]) -> Dict[str, ActionInstance]:
    """
    Return step_dict sorted in topological order (levels then id),
    with verbose debug output.
    """
    #print("\n=== _order_steps START ===")
    #print(f"Input step_dict keys: {list(step_dict.keys())}\n")

    # 1) Compute topological levels
    #print("1) Computing topological levels...")
    lvls = topological_levels(step_dict)
    #print(f"   → Levels returned: {lvls}\n")

    # 2) Flatten levels into a single ordered list
    #print("2) Flattening levels into ordered list of IDs...")
    ordered_ids = []
    for lvl_idx, lvl in enumerate(lvls, start=1):
        sorted_lvl = sorted(lvl)
        #print(f"   Level {lvl_idx}: {sorted_lvl}")
        ordered_ids.extend(sorted_lvl)
    #print(f"   → Flattened order: {ordered_ids}\n")

    # 3) Re-key the dictionary as step_1, step_2, …
    #print("3) Rebuilding dict with new keys...")
    ordered_dict: Dict[str, ActionInstance] = {}
    for i, sid in enumerate(ordered_ids):
        new_key = f"step_{i+1}"
        ordered_dict[new_key] = step_dict[sid]
        #print(f"   Mapping original '{sid}' → new key '{new_key}'")
    #print()

    #print("Final ordered_dict keys:", list(ordered_dict.keys()))
    #print("=== _order_steps END ===\n")
    return ordered_dict


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


def squeeze_with_unresolved(train_procs: List[Procedure], scenarioId: str, ruleId: str) -> List[Procedure]:
    from copy import deepcopy
    from collections import defaultdict

    print("\n🎨 squeeze_with_unresolved – starting")

    if not train_procs:
        return []

    branches: List[Dict[str, ActionInstance]] = [{}]
    action_counters: Dict[str, int] = defaultdict(int)
    end_by_generic: Dict[str, Set[int]] = defaultdict(set)
    train_to_generic_id: Dict[str, str] = {}
    all_train_ids: Set[int] = set(
        step.trainId
        for proc in train_procs
        for step in proc.steps.values()
        if step.trainId is not None
    )

    def _const_signature(step):
        return tuple(
            (k, repr(b.value))
            for k, b in sorted(step.bindings.items())
            if b.binding == BindingStatus.CONSTANT
        )

    def _binding_signature(step: ActionInstance, step_lookup: dict[str, ActionInstance]) -> tuple:
        """
        Build a signature for an ActionInstance based on all its bindings' hashes,
        using make_binding_hash when needed.
        """
        signature = []
        for name, binding in sorted(step.bindings.items()):
            if binding.binding_hash is None:
                producer_id = binding.source_procedure_id
                producer_action_id = (
                    step_lookup[producer_id].action.id
                    if producer_id in step_lookup else "?"
                )
                consumer_action_id = step.action.id
                path = name
                btm.make_binding_hash(binding, producer_action_id, consumer_action_id, path)
            signature.append((name, binding.binding_hash))
        return tuple(signature)

    def replace_nested_source_ids(
            binding: Union[ArgumentBinding, dict, list],
            mapping: dict,
            current_consumer_id: str,
            branch: dict
    ):
        print("replace_nested_source_ids")
        if current_consumer_id== "select_object_grid#1":
            print("current_consumer_id " + current_consumer_id)
        # Si c'est un ArgumentBinding
        if isinstance(binding, ArgumentBinding):

            # 1) On gère d'abord le statut MULTIPLE
            if binding.binding == BindingStatus.MULTIPLE and binding.candidates:
                print("🛠️ [ replace_nested_source_ids MULTIPLE ]")
                # On ne conserve que les candidats présents dans tous les trains
                print("binding.candidates")
                print(binding.candidates)
                print("btm.bindingTrainMap")
                print(btm.bindingTrainMap)
                print("btm.ALL_TRAIN_IDS")
                print(btm.ALL_TRAIN_IDS)
                valid_cands = [
                    cand for cand in binding.candidates
                    if btm.bindingTrainMap.get(cand.binding_hash, set()) == btm.ALL_TRAIN_IDS
                ]
                print("valid_cands")
                print(valid_cands)

                if len(valid_cands) == 0:
                    # aucun candidat valable → on repasse en UNRESOLVED
                    print("⚠️ MULTIPLE→UNRESOLVED: aucun candidat présent dans tous les trains")
                    binding.binding = BindingStatus.UNRESOLVED
                    binding.source_procedure_id = None
                    binding.candidates = None

                elif len(valid_cands) == 1:
                    # unique candidat → on bascule en VARIABLE
                    cand = valid_cands[0]
                    new_id = mapping.get(cand.producer_id, cand.producer_id)
                    print(f"🛠️ MULTIPLE→VARIABLE: choix unique {cand.producer_id} → {new_id}")
                    binding.binding = BindingStatus.VARIABLE
                    binding.source_procedure_id = new_id
                    binding.candidates = None
                    if new_id in branch and current_consumer_id not in branch[new_id].used_by:
                        branch[new_id].used_by.append(current_consumer_id)

                else:
                    # plusieurs candidats → on cherche d'abord un get_start_input
                    print(f"🛡️ MULTIPLE reste MULTIPLE ({len(valid_cands)} candidats)")
                    # recherche d'un candidat 'get_start_input'
                    gi = [c for c in valid_cands if c.producer_id.startswith("start_input")]
                    print(f"gi: {gi}")
                    if gi:
                        cand = gi[0]
                        new_id = mapping.get(cand.producer_id, cand.producer_id)
                        print(f"🌟 Priorité get_start_input → bascule en INPUT_GRID sur {cand.producer_id} → {new_id}")
                        binding.binding = BindingStatus.INPUT_GRID
                        binding.source_procedure_id = new_id
                        binding.candidates = None
                        if new_id in branch and current_consumer_id not in branch[new_id].used_by:
                            branch[new_id].used_by.append(current_consumer_id)
                    else:
                        # on ne garde que les candidats valides
                        binding.candidates = valid_cands
                        print(f"🛡️ Conserve candidats valides: {[c.producer_id for c in valid_cands]}")

            # 2) Ensuite, si on est en VARIABLE, on remplace l’ID via mapping
            if binding.binding in (BindingStatus.VARIABLE, BindingStatus.BUFFER) and binding.source_procedure_id in mapping:
                old_id = binding.source_procedure_id
                new_id = mapping[old_id]
                print(f"🔁 Replacing source_procedure_id {old_id} → {new_id} for consumer {current_consumer_id}")
                binding.source_procedure_id = new_id
                if new_id in branch and current_consumer_id not in branch[new_id].used_by:
                    branch[new_id].used_by.append(current_consumer_id)

            # 3) Descente récursive dans les sub_bindings
            replace_nested_source_ids(binding.sub_bindings, mapping, current_consumer_id, branch)

        # Si c'est un dict de sub-bindings
        elif isinstance(binding, dict):
            for sub in binding.values():
                replace_nested_source_ids(sub, mapping, current_consumer_id, branch)

        # Si c'est une liste de sub-bindings
        elif isinstance(binding, list):
            for item in binding:
                replace_nested_source_ids(item, mapping, current_consumer_id, branch)

    for proc in train_procs:
        print(f"\n🚂 Processing train procedure {proc.id} with {len(proc.steps)} steps")
        for step in proc.steps.values():
            print(f"\n🔧 Analyzing step {step.id} ({step.action.id})")

            new_branches = []
            for branch in branches:
                for bind in step.bindings.values():
                    if bind.binding in (BindingStatus.VARIABLE, BindingStatus.MULTIPLE, BindingStatus.BUFFER):
                        old_id = bind.source_procedure_id
                        if old_id and old_id in train_to_generic_id:
                            print(f"🔗 Updating binding source_procedure_id {old_id} → {train_to_generic_id[old_id]}")
                            bind.source_procedure_id = train_to_generic_id[old_id]
                        if bind.candidates:
                            for cand in bind.candidates:
                                if cand.producer_id in train_to_generic_id:
                                    print(f"↻ Updating candidate: {cand.producer_id} → {train_to_generic_id[cand.producer_id]}")
                                    cand.producer_id = train_to_generic_id[cand.producer_id]

                found = None
                for b in branch.values():
                    if b.action.id == step.action.id:
                        b_sig = _binding_signature(b, proc.steps)
                        s_sig = _binding_signature(step, proc.steps)
                        print(f"🧪 Comparing with existing {b.id} ({b.action.id})")
                        print(f"    sig_existing: {b_sig}")
                        print(f"    sig_current : {s_sig}")
                        if b_sig == s_sig:
                            print(f"✅ Found matching action by signature: {b.id}")
                            found = b
                            break

                if found:
                    # record the mapping from this train-step to the generic
                    train_to_generic_id[step.id] = found.id
                    print(f"✅ Mapped {step.id} to existing generic {found.id}")

                    # if this is a repaint, re-wire its bufferInstance onto the generic
                    if step.action.id == "repaint" and step.bufferInstance:
                        old_buf_id = step.bufferInstance.id
                        if old_buf_id in train_to_generic_id:
                            generic_buf_id = train_to_generic_id[old_buf_id]

                            # 1) found is the generic repaint; branch holds your generic init
                            found.bufferInstance = branch[generic_buf_id]
                            print(f"🔧 Rewired repaint# → bufferInstance {generic_buf_id}")

                    new_branches.append(branch)

                    if step.END:
                        #print("end_by_generic[found.id].add(step.trainId)")
                        #print(f"end_by_generic[{found.id}].add({step.trainId}) for step.id: {step.id}")
                        end_by_generic[found.id].add(step.trainId)

                    continue

                # No match → create a new instance
                copied = deepcopy(step)
                action_counters[copied.action.id] += 1
                copied.id = f"{copied.action.id}#{action_counters[copied.action.id]}"
                print(f"🆕 Creating new generic step {copied.id} from {step.id}")
                train_to_generic_id[step.id] = copied.id
                #print(f" copied.bindings.values ")
                #print(copied.bindings.values())


                for b in copied.bindings.values():
                    replace_nested_source_ids(b, train_to_generic_id, copied.id, branch)
                    # Restore constants if missing
                    if b.binding == BindingStatus.CONSTANT and b.value is None:
                        original_bind = step.bindings.get(b.name)
                        if original_bind and original_bind.binding == BindingStatus.CONSTANT:
                            b.value = original_bind.value
                            print(f"💾 Restored constant value {b.name} = {b.value}")
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
                            print(f"📥 Injected input grid for {copied.id}")

                branch2 = branch.copy()
                branch2[copied.id] = copied
                new_branches.append(branch2)

                if step.END:
                    #print("end_by_generic[copied.id].add(step.trainId)")
                    #print(f"end_by_generic[{copied.id}].add({step.trainId}) for step.id: {step.id}")
                    end_by_generic[copied.id].add(step.trainId)

            branches = new_branches

    # Final pass
    generic_procs = []
    for idx, branch in enumerate(branches):
        for s in branch.values():
            s.output_value = None
            for b in s.bindings.values():
                if b.binding == BindingStatus.UNRESOLVED:
                    b.value = None

        step_ids = set(branch.keys())
        for s in branch.values():
            if s.used_by:
                s.used_by = [uid for uid in s.used_by if uid in step_ids]
        for gen_step in branch.values():
            if not gen_step.END:
                if gen_step.IN_SEPARATE_RULE:
                    gen_step.END = True
                else:
                    ended_ids = end_by_generic.get(gen_step.id, set())
                    gen_step.END = all_train_ids <= ended_ids
                #print(f"gen_step.id: {gen_step.id} ")
                #print(f"ended_ids: {ended_ids}, all_train_ids: {all_train_ids} gen_step.END: {gen_step.END}, ")
                #print(end_by_generic)

        # On recompute la liste des IDs à conserver impérativement
        final_output_ids = {s.id for s in branch.values() if s.END}

        # On identifie les étapes inutilisées
        to_remove = [
            sid for sid in branch
            if not is_step_still_used(sid, branch) and sid not in final_output_ids
        ]
        for sid in to_remove:
            action_id = branch[sid].action.id
            if action_id in ("get_start_input", "initialize_buffer", "repaint"):
                print(f"[DEBUG] On conserve {sid} (action {action_id} protégée)")
                continue
            print(f"🧹 Removing unused step: {sid} (action {action_id})")
            branch.pop(sid)

        proc = Procedure(id=f"generic_proc_{idx+1}", steps=branch, scenarioId=scenarioId, ruleId=ruleId)
        print(f"\n🧬 Final generic_proc_{idx+1}")
        for sid, step in proc.steps.items():
            print(f"   {sid} ({step.action.id})")
        generic_procs.append(proc)

    return generic_procs

def fill_producer_criteria(
    producer: Producer,
    tables: Dict[str, Dict[int, Dict[str, Any]]],
    table_key: str = "sprite_analysis"
) -> None:
    """
    Recursively walk this producer and any nested producers,
    calling extract_common_sprite_rows_criteria on each one
    that has a resultByTrainId + suggested_action.
    """
    # 1) If this node wants criteria, compute & attach them
    if producer.suggested_by_train_function and producer.resultByTrainId:
        producer.criteria = extract_common_sprite_rows_criteria(
            producer.resultByTrainId,
            tables,
            table_key=table_key
        )
        print("  suggested_by_train_function:", producer.suggested_by_train_function)
        print("  criteria:", producer.criteria)
    if producer.suggested_by_sprite_function and producer.produceByTrainAndSpriteId:
        producer.criteria = extract_common_sprite_values_criteria(
            producer.produceByTrainAndSpriteId,
            tables,
            table_key=table_key
        )
        print("  suggested_by_sprite_function:", producer.suggested_by_sprite_function)
        print("  criteria:", producer.criteria)


    # 2) Recurse into any nested maps
    for child in producer.maps.values():
        fill_producer_criteria(child, tables, table_key)



def collect_produced_names(producer: Producer) -> Set[str]:
    """
    Recursively collect all keys in producer.maps as the names of
    elements this producer action will emit.
    """
    names: Set[str] = set(producer.maps.keys())
    for child in producer.maps.values():
        names |= collect_produced_names(child)
    return names


def generate_producers(
    squeezed_procs: List[Procedure],
    current_scenario,
    current_rule
) -> List[Procedure]:
    """
    For each Procedure, inject a single reusable producer-action blueprint
    for every declared Producer. Update downstream bindings whose name is in
    the set of produced element names (collected from producer_obj.maps).
    """
    print("\n🎨 generate_producers – starting")
    new_procs: List[Procedure] = []

    for proc in squeezed_procs:
        new_steps: "OrderedDict[str, ActionInstance]" = OrderedDict()

        for step in proc.steps.values():
            # 1) For each declared producer in this step
            for producer_key, producer_obj in step.producers.items():
                print(f"proc.id={proc.id} step.id={step.id} producer_key={producer_key}")
                # a) compute criteria
                fill_producer_criteria(producer_obj, current_rule.tables)

                # b) build the single blueprint action instance
                producer_instance = build_producer_action(
                    producer_key,
                    producer_obj,
                    current_rule.tables,
                    scenarioId=step.scenarioId,
                    ruleId=step.ruleId
                )

                # c) register this instance before the original step
                new_steps[producer_instance.id] = producer_instance

                # d) update original step bindings whose name is one of the produced elements
                produced_names = collect_produced_names(producer_obj)
                for bind_name, bind in step.bindings.items():
                    if bind.binding == BindingStatus.PRODUCE and bind_name in produced_names:
                        bind.source_procedure_id = producer_instance.id

            # 2) now add the original step
            new_steps[step.id] = step

        # replace steps and collect
        proc.steps = new_steps
        new_procs.append(proc)

    return new_procs


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

def normalize_procedures_with_levels(
    procs: List[Procedure],
    scenarioId: str,
    ruleId: str
) -> List[Procedure]:
    """
    Return copies of *procs* whose steps are sorted topologically,
    with detailed debug output.
    """
    #print("\n=== normalize_procedures_with_levels START ===")
    #print(f"Total procedures to normalize: {len(procs)}\n")

    normalized: List[Procedure] = []
    for proc_idx, p in enumerate(procs, start=1):
        #print(f"--- Processing Procedure {proc_idx}/{len(procs)}: id={p.id} ---")
        original_ids = [step.id for step in p.steps.values()]
        #print(f"Original step IDs (unsorted): {original_ids}")

        # Build a mapping id→ActionInstance and call our verbose _order_steps
        step_map = {s.id: s for s in p.steps.values()}
        #print("Calling _order_steps to sort topologically...")
        ordered_map = _order_steps(step_map)  # assumes verbose _order_steps

        new_ids = list(ordered_map.keys())
        #print(f"Ordered step keys: {new_ids}")
        #print(f"Corresponding original IDs in order: {[step_map_id for step_map_id in ordered_map.values()]}\n")

        # Re-wrap into a new Procedure
        new_proc = Procedure(
            id=p.id,
            steps=ordered_map,
            scenarioId=scenarioId,
            ruleId=ruleId
        )
        normalized.append(new_proc)
        #print(f"Procedure {p.id} normalized → contains {len(ordered_map)} steps.\n")

    #print("=== normalize_procedures_with_levels END ===\n")
    return normalized

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