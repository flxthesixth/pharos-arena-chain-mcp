"""Compatibility entrypoint; implementation lives under tasks/event-log-monitor/source."""
from importlib import import_module
import sys

implementation = import_module("tasks.event-log-monitor.source.arena_event_monitor")
if __name__ == "__main__":
    implementation.main()
sys.modules[__name__] = implementation
