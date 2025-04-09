from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple, Union, Dict

from constelize.core.binding import ArgumentBinding
from constelize.core.categories import ActionCategory


@dataclass
class Action:
    id: str                         # Unique ID like "translate#001" or "rotate_90#core"
    name: str                       # Display name like "translate" or "rotate"
    description: str
    category: ActionCategory
    input_arguments: List[ArgumentBinding]
    output_type: str
    function: Callable[..., Any]
    deterministic: bool = True
    pure: bool = True
    reversible: bool = False
    inverse_id: Optional[str] = None
    parameters: Optional[List[str]] = field(default_factory=list)
    examples: Optional[List[Tuple[Any, Any]]] = field(default_factory=list)