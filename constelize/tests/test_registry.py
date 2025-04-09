from constelize.core.registry import ActionRegistry

def test_registry_loads_without_error():
    registry = ActionRegistry()
    registry.register_all_actions()
    assert len(registry.all()) > 0
    assert any(action.name == "add" for action in registry.all())  # Example check