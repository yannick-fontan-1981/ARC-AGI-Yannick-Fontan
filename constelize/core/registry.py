# constelize/core/registry.py

import importlib
import pkgutil
from typing import List

from constelize.core.action import Action
from constelize.core.categories import ActionCategory

class ActionRegistry:
    def __init__(self):
        self.actions_by_id = {}
        self.actions_by_name = {}
        self.actions_by_category = {}

    def register(self, action: Action):
        if action.id in self.actions_by_id:
            raise ValueError(f"Duplicate action ID: {action.id}")
        self.actions_by_id[action.id] = action
        self.actions_by_name.setdefault(action.name, []).append(action)
        self.actions_by_category.setdefault(action.category, []).append(action)

    def get_by_id(self, id: str):
        return self.actions_by_id.get(id)

    def get_by_name(self, name: str):
        return self.actions_by_name.get(name, [])

    def get_by_category(self, category: str):
        return self.actions_by_category.get(category, [])

    def all(self) -> List[Action]:
        return list(self.actions_by_id.values())

    def summary(self):
        print("🧠 Registered Actions Summary:")
        for category, actions in self.actions_by_category.items():
            print(f"  - {category}: {len(actions)} actions")

    def register_all_actions(self):
        from constelize import library

        # Discover all modules in constelize.library
        for finder, module_name, is_pkg in pkgutil.iter_modules(library.__path__):
            full_module_name = f"constelize.library.{module_name}"
            try:
                mod = importlib.import_module(full_module_name)
                if hasattr(mod, "ACTIONS"):
                    for action in getattr(mod, "ACTIONS"):
                        self.register(action)
            except Exception as e:
                print(f"⚠️ Could not import {full_module_name}: {e}")
