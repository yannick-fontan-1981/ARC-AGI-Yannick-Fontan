#constelize/core/scenario.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from constelize.core.rule import Rule  # You'll need to create rule.py

@dataclass
class Scenario:
    id: str
    rules: Dict[str, Rule] = field(default_factory=dict)
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_targets: Dict[str, Any] = field(default_factory=dict)
    comment: Optional[str] = None
    rule_to_launch_before: Rule = None
    rule_to_analyse: Rule = None
    to_launch_next: List["Scenario"] = field(default_factory=list)

    def run(self) -> Dict[str, Any]:
        scope: Dict[str, Any] = dict(self.input_data)
        rule_results: Dict[str, Dict[str, Any]] = {}

        for rule_id, rule in self.rules.items():
            # Filter scope to only what the rule declares it needs
            rule_inputs = {var: scope[var] for var in rule.input_vars if var in scope}
            rule_output = rule.run(rule_inputs)
            rule_results[rule_id] = rule_output
            scope.update(rule_output)  # Push outputs into global scope for other rules

        return {k: scope[k] for k in self.output_targets if k in scope}

    def get_unresolved_inputs(self) -> Dict[str, set[str]]:
        scope = set(self.input_data.keys())
        unresolved_by_rule = {}

        for rule_id, rule in self.rules.items():
            if not rule.active:
                continue

            missing = rule.get_unresolved_inputs()
            unresolved_by_rule[rule_id] = missing

            scope.update(rule.output_vars)  # advance the scope for next rule

        return unresolved_by_rule
