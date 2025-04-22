from typing import List

from constelize.core.binding import BindingStatus
from constelize.core.procedure import Procedure

def get_dependency_chain(proc: Procedure, final_step_id: str) -> set[str]:
    chain = set()
    stack = [final_step_id]
    while stack:
        sid = stack.pop()
        if sid in chain: continue
        chain.add(sid)
        step = proc.steps[sid]
        for b in step.bindings.values():
            src = getattr(b, "source_procedure_id", None)
            if b.binding == BindingStatus.VARIABLE and src:
                stack.append(src)
    return chain

def prune_procedure(proc: Procedure, executed_steps: List[str]) -> bool:
    if not executed_steps:
        return False

    final = executed_steps[-1]
    needed = get_dependency_chain(proc, final)

    # Identify active-but-unneeded steps
    to_remove = [sid for sid, step in proc.steps.items()
                 if step.active and sid not in needed]

    if not to_remove:
        return False

    for sid in to_remove:
        del proc.steps[sid]

    return True

def iterative_prune(generic_procs: list[Procedure], data: dict) -> list[Procedure]:
    from constelize.tools.pattern_analysis import evaluate_generic_procedures

    while True:
        results = evaluate_generic_procedures(
            "train",
            generic_procs,
            data,
            return_execution_trace=True
        )

        pruned = False
        for r in results:
            proc_id = r.get("procedure_id", "?")
            if not r.get("success"):
                print(f"⚠️ Skipping procedure {proc_id} due to failure.")
                continue
            if "executed_steps" not in r:
                print(f"⚠️ Missing 'executed_steps' for {proc_id}. Skipping.")
                continue
            if r.get("success") and "executed_steps" in r:
                proc = next((p for p in generic_procs if p.id == r["procedure_id"]), None)
                if proc:
                    print(f"🔧 Pruning procedure {proc.id} based on steps: {r['executed_steps']}")
                    if prune_procedure(proc, r["executed_steps"]):
                        pruned = True
                else:
                    print(f"⚠️ Procedure with id={r['procedure_id']} not found in current list.")

        if not pruned:
            break

    return generic_procs