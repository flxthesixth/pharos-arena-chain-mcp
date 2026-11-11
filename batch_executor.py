"""Compatibility entrypoint; implementation lives under tasks/batch-executor/source."""
from importlib import import_module
import sys

implementation = import_module("tasks.batch-executor.source.batch_executor")
if __name__ == "__main__":
    raise SystemExit(implementation.main())
sys.modules[__name__] = implementation
