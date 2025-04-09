from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.procedure import Procedure

@dataclass
class Rule:
    id: str
    input_vars: Dict[str, ArgumentBinding] = field(default_factory=dict)
    output_vars: List[str] = field(default_factory=list)
    procedures: Dict[str, Procedure] = field(default_factory=dict)
    active: bool = True
    comment: Optional[str] = None

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        local_scope = dict(inputs)
        for proc in self.procedures.values():
            if proc.active:
                local_scope.update(proc.run(local_scope))
        return {k: local_scope[k] for k in self.output_vars if k in local_scope}

    def get_unresolved_inputs(self) -> set[str]:
        """
        Returns the names of rule input variables that are still unresolved.
        """
        return {
            name
            for name, binding in self.input_vars.items()
            if binding.binding == BindingStatus.UNRESOLVED
        }