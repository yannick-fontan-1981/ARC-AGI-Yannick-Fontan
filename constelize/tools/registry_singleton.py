# constelize/tools/registry_singleton.py

from constelize.core.registry import ActionRegistry

registry = ActionRegistry()
registry.register_all_actions()