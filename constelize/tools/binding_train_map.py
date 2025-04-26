# constelize/tools/binding_train_map.py
import hashlib
import pickle
from collections import defaultdict

from constelize.core.binding import ArgumentBinding

# binding_hash -> set of trainIds
bindingTrainMap: dict[str, set[int]] = defaultdict(set)

# Nombre total de trains ; on l'initialisera au lancement du pipeline
TOTAL_TRAINS: int = 0

ALL_TRAIN_IDS = set()

def make_binding_hash(binding: ArgumentBinding,
                      producer_action_id: str,
                      consumer_action_id: str,
                      path: str) -> str:
    #if binding.binding_hash:
    #    print(f"[make_binding_hash binding.binding_hash already present: {binding.binding_hash}]")
    #    return binding.binding_hash

    sig = (
        producer_action_id,
        consumer_action_id,
        path,
        binding.type,
        #binding.binding.name,
        #repr(binding.value)
    )
    raw = pickle.dumps(sig)
    h = hashlib.md5(raw).hexdigest()
    binding.binding_hash = h

    print(f"[make_binding_hash producer_action_id: {producer_action_id}]")
    print(f"[make_binding_hash consumer_action_id: {consumer_action_id}]")
    print(f"[make_binding_hash path: {path}]")
    print(f"[make_binding_hash binding.type: {binding.type}]")
    #print(f"[make_binding_hash binding.binding.name: {binding.binding.name}]")
    #print(f"[make_binding_hash repr(binding.value): {repr(binding.value)}]")
    print(f"[make_binding_hash hash: {h}]")

    return h