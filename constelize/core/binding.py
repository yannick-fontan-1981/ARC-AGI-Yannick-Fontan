from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum, auto

class BindingStatus(Enum):
    CONSTANT = auto()       # Fixed across all training examples.
    VARIABLE = auto()       # Computed from another step.
    UNRESOLVED = auto()     # Not yet bound.
    MULTIPLE = auto()       # Requires candidate expansion.
    INPUT_GRID = auto()     # To be injected from JSON input.
    COMPOUND = auto()       # Structured binding for composite types.

@dataclass
class LinkCandidate:
    producer_id: str        # ID of the step or rule that can supply the value.
    var_name: str           # The output variable name in that producer.
    status: Optional[str] = None  # Optionally track candidate status.

@dataclass
class ArgumentBinding:
    name: str
    type: str  # For example: "Integer", "Grid", "Coord", "Array<Coord>", etc.
    binding: BindingStatus = BindingStatus.UNRESOLVED
    value: Optional[Union[str, Any]] = None  # For scalar values.
    source_procedure_id: Optional[str] = None  # Linked producer identifier.
    candidates: Optional[List[LinkCandidate]] = None  # For multiple candidate producers.
    # For compound types, store a nested structure.
    # Use a dict for composite types (e.g. Coord) or a list for arrays.
    sub_bindings: Optional[Union[Dict[str, ArgumentBinding], List[ArgumentBinding]]] = field(default_factory=dict)
    # New fields for sub-bindings length:
    # 1. sub_bindings_length_status indicates if the length is resolved and whether it is constant or variable.
    sub_bindings_length_status: BindingStatus = BindingStatus.UNRESOLVED
    # 2. sub_bindings_length_value holds the concrete integer value once resolved.
    sub_bindings_length_value: Optional[int] = None