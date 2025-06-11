# constelize/tools/binding_train_map.py
import hashlib
import json
import pickle
from collections import defaultdict
from typing import Any

from constelize.core.binding import ArgumentBinding, BindingStatus

# binding_hash -> set of trainIds
bindingTrainMap: dict[str, set[int]] = defaultdict(set)

# Nombre total de trains ; on l'initialisera au lancement du pipeline
TOTAL_TRAINS: int = 0

ALL_TRAIN_IDS = set()

def _normalize_for_json(obj: Any) -> Any:
    """
    Recursively convert obj into something JSON-serializable:
      - dict → dict with sorted keys
      - list/tuple → list
      - set/frozenset → sorted list
      - primitives (str, int, float, bool, None) → unchanged
      - other → repr(obj)
    """
    if isinstance(obj, dict):
        # sort keys for deterministic ordering
        return {k: _normalize_for_json(obj[k]) for k in sorted(obj)}
    elif isinstance(obj, (list, tuple)):
        return [_normalize_for_json(el) for el in obj]
    elif isinstance(obj, (set, frozenset)):
        # sort the normalized elements so signature is stable
        normalized = [_normalize_for_json(el) for el in obj]
        try:
            return sorted(normalized)
        except TypeError:
            # if elements not directly comparable, sort by repr
            return sorted(normalized, key=repr)
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    else:
        # fallback: turn anything else into its repr string
        return repr(obj)

def serialize_binding(b: ArgumentBinding) -> dict[str, Any]:
    # same as before, but we let _normalize handle non-primitives downstream
    type_val   = b.type.name    if hasattr(b.type, "name")    else b.type
    status_val = b.binding.name if hasattr(b.binding, "name") else b.binding

    data: dict[str, Any] = {
        "type":   type_val,
        "status": status_val,
    }
    if b.binding == BindingStatus.CONSTANT:
        data["value"] = b.value
    if b.suggested_action is not None:
        data["suggested_action"] = b.suggested_action
    if b.suggested_transform is not None:
        data["suggested_transform"] = b.suggested_transform

    subs = b.sub_bindings
    if subs:
        if isinstance(subs, dict):
            data["sub_bindings"] = {
                key: serialize_binding(child)
                for key, child in sorted(subs.items())
            }
        elif isinstance(subs, (list, tuple)):
            data["sub_bindings"] = [serialize_binding(child) for child in subs]
        else:
            data["sub_bindings"] = repr(subs)
    return data

def make_binding_hash(binding: ArgumentBinding,
                      producer_action_id: str,
                      consumer_action_id: str,
                      path: str) -> str:
    # 1) Build the raw envelope
    envelope = {
        "producer": producer_action_id,
        "consumer": consumer_action_id,
        "path":     path,
        "binding":  serialize_binding(binding),
    }
    # 2) Normalize it into only JSON-friendly types
    normalized = _normalize_for_json(envelope)
    # 3) Dump with sorted keys → bytes → MD5
    raw = json.dumps(normalized, sort_keys=True).encode("utf-8")
    h   = hashlib.md5(raw).hexdigest()

    binding.binding_hash = h
    return h

