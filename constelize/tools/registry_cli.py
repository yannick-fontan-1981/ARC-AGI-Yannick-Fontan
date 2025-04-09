# constelize/tools/registry_cli.py

import sys
from constelize.core.registry import ActionRegistry

def list_actions():
    registry = ActionRegistry()
    registry.register_all_actions()

    print("📚 List of Registered Actions:\n")
    for action in registry.all():
        input_names = ", ".join(arg.name for arg in action.input_arguments)
        print(f"🧱 {action.id} :: {action.name}")
        print(f"   ↳ Category: {action.category.value}")
        print(f"   ↳ Inputs: ({input_names}) → {action.output_type}\n")

    print("📚 Total :")
    print(len(registry.all()))

def main():
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h"}:
        print("Usage:")
        print("  constelize list-actions     List all registered elementary actions")
        return

    if args[0] == "list-actions":
        list_actions()
    else:
        print(f"Unknown command: {args[0]}")
        print("Try: constelize --help")

def register_procedure(procedure):
    print(f"📦 Procedure '{procedure.id}' registered with {len(procedure.steps)} steps.")

if __name__ == "__main__":
    main()
