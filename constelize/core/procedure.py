import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from constelize.core.action import Action
from constelize.core.binding import BindingStatus, ArgumentBinding, Producer
from constelize.dsl.grid_dsl import Grid


@dataclass
class ActionInstance:
    id: str
    action: Action
    scenarioId: Optional[str] = None
    ruleId: Optional[str] = None
    trainId: Optional[int] = None
    testId: Optional[int] = None
    isTrain: Optional[bool] = None
    bindings: Dict[str, Any] = field(default_factory=dict)
    producers: Dict[str, Producer] = field(default_factory=dict)
    isFromInput: Optional[bool] = None
    isToOutput: Optional[bool] = None
    output_var: Optional[str] = None
    output_value: Optional[Any] = None
    output_type: Optional[str] = None
    used_by: Optional[List[str]] = field(default_factory=list)
    comment: Optional[str] = None
    active: bool = True
    toRepaint: bool = False
    repaintMinX: int = 0
    repaintMinY: int = 0
    repaintSuggestedSpriteId: Optional[int] = None
    bufferInstance: "ActionInstance" = None
    END: bool = False
    IN_SEPARATE_RULE: bool = False

    def get_unresolved_bindings(self) -> set[str]:
        return {
            name
            for name, binding in self.bindings.items()
            if binding.binding == BindingStatus.UNRESOLVED
        }

@dataclass
class Procedure:
    id: str
    scenarioId: Optional[str] = None
    ruleId: Optional[str] = None
    steps: Dict[str, ActionInstance] = field(default_factory=dict)
    active: bool = True
    comment: Optional[str] = None
    action_producing_output: ActionInstance = None

    def run(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        local_scope = {k: scope[k] for k in self.input_vars if k in scope}
        for step in self.steps.values():
            if not step.active:
                continue
            inputs = {
                k: (local_scope[v] if isinstance(v, str) and v in local_scope else v)
                for k, v in step.bindings.items()
            }
            result = step.action.function(**inputs)
            if step.output_var:
                local_scope[step.output_var] = result

        return {k: local_scope[k] for k in self.output_vars if k in local_scope}

    def get_unresolved_inputs(self) -> set[str]:
        """
        Returns the names of input variables that are still unresolved.
        """
        return {
            name
            for name, binding in self.input_vars.items()
            if binding.binding == BindingStatus.UNRESOLVED
        }

def evaluate_procedure(procedure: Procedure, expected_output=None) -> bool:
    for step in procedure.steps.values():
        if getattr(step, "END", False) and step.output_value == expected_output:
            return True
    return False
