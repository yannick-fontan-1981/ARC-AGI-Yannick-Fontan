#constelize/core/rule.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from constelize.core.binding import ArgumentBinding, BindingStatus
from constelize.core.procedure import Procedure

@dataclass
class Rule:
    id: str
    comment: Optional[str] = None
    tables: Dict[str, Dict[int, Dict[str, Any]]] = field(default_factory=dict)
    values_by_input: Dict[str, Dict[str, int]] = field(default_factory=dict)
    attributes_by_input_and_values: Dict[str, Dict[int, List[str]]] = field(default_factory=dict)
    colors_by_input: Dict[str, Dict[str, int]] = field(default_factory=dict)
    attributes_by_input_and_colors: Dict[str, Dict[int, List[str]]] = field(default_factory=dict)
    procedures: List[Procedure] = field(default_factory=list)
    generic_procs: List[Procedure] = field(default_factory=list)
    train_results: List[Dict[str, str]] = field(default_factory=list)
    active: bool = True
    rule_producing_input: "Rule" = None
    proc_producing_output: Procedure = None

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