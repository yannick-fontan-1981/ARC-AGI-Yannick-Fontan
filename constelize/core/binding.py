from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional, List, Union

class CandidateStatus(Enum):
    PENDING = auto()
    SUCCEEDED = auto()
    FAILED = auto()

@dataclass
class LinkCandidate:
    producer_id: str        # Procedure or Rule that can produce the value
    var_name: str           # The output var name in that producer
    status: CandidateStatus = CandidateStatus.PENDING

class BindingStatus(Enum):
    CONSTANT = auto()       # Fixed across all training examples
    VARIABLE = auto()       # Needs to be computed by another procedure
    UNRESOLVED = auto()     # Currently unknown; needs to be resolved
    MULTIPLE = auto()

@dataclass
class ArgumentBinding:
    name: str
    type: str
    binding: BindingStatus = BindingStatus.UNRESOLVED
    value: Optional[Union[str, Any]] = None  # constant or linked var
    source_procedure_id: Optional[str] = None  # current linked source (if any)
    candidates: Optional[List[LinkCandidate]] = None  # other options if binding == MULTIPLE