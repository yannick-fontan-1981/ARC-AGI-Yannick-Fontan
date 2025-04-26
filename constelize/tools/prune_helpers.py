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
    """
    Répète l’évaluation des procédures génériques sur les données d’entraînement.
    À chaque itération :
      - Si une procédure réussit, on réduit (prune) ses étapes aux seules réellement exécutées.
      - Si une procédure échoue ou n’est pas complète, elle est ignorée.
    On boucle jusqu’à ce qu’aucune procédure ne soit modifiée.
    """
    from constelize.tools.pattern_analysis import evaluate_generic_procedures

    round_num = 1

    while True:
        print(f"\n🔁 [iterative_prune] Round {round_num} — evaluating {len(generic_procs)} procedure(s)...")

        results = evaluate_generic_procedures(
            mode="train",                       # Évalue uniquement sur les exemples d'entraînement
            procedures=generic_procs,           # Liste des procédures génériques à tester
            data=data,                          # Contenu du fichier ARC (JSON)
            return_execution_trace=True         # Demande le détail des étapes exécutées
        )

        pruned = False

        for r in results:
            proc_id = r.get("procedure_id", "?")
            trainId = r.get("trainId", -1)
            success = r.get("success", False)
            executed_steps = r.get("executed_steps")

            if not success:
                print(f"⚠️ Procedure {proc_id} FAILED on trainId={trainId}. It will not be pruned from this example.")
                continue

            if executed_steps is None:
                print(f"⚠️ Procedure {proc_id} on trainId={trainId} succeeded but missing 'executed_steps'.")
                continue

            print(f"✅ Procedure {proc_id} succeeded on trainId={trainId}.")
            print(f"   📦 Executed steps: {executed_steps}")

            # On récupère la procédure correspondante
            proc = next((p for p in generic_procs if p.id == proc_id), None)
            if proc is None:
                print(f"⚠️ Could not find Procedure object with id={proc_id}. Skipping.")
                continue

            # On tente de la réduire à ses étapes utiles
            did_prune = prune_procedure(proc, executed_steps)
            if did_prune:
                print(f"🪓 Pruned procedure {proc.id} → kept only {len(executed_steps)} step(s).")
                pruned = True
            else:
                print(f"🧊 Procedure {proc.id} unchanged after pruning.")

        if not pruned:
            print(f"\n🛑 No further pruning possible. Terminating.")
            break

        round_num += 1

    return generic_procs