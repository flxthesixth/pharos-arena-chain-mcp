"""Compatibility entrypoint; implementation lives under tasks/read-contract-state/source."""
from importlib import import_module
import sys

implementation = import_module("tasks.read-contract-state.source.arena_contract_state")
if __name__ == "__main__":
    if "--self-test" in sys.argv:
        implementation.self_test()
        print("self-test passed")
    else:
        print(implementation.json.dumps(implementation.snapshot(), indent=2))
sys.modules[__name__] = implementation
