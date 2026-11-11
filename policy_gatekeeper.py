"""Compatibility entrypoint; implementation lives under tasks/policy-gatekeeper/source."""
from importlib import import_module
import sys

implementation = import_module("tasks.policy-gatekeeper.source.policy_gatekeeper")
if __name__ == "__main__":
    raise SystemExit(implementation.main())
sys.modules[__name__] = implementation
