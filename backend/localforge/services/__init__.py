"""Service package public boundary.

This package intentionally avoids eager service imports. Several services depend
on storage and transaction modules, so importing them here creates clean
interpreter cycles for independent modules such as compliance evidence.
"""

from typing import Any

__all__ = [
    "ProjectService",
    "TaskService",
    "ExecutionService",
    "AuditService",
    "SafetyService",
    "APISimulationService",
]

_SERVICE_IMPORTS = {
    "ProjectService": ("localforge.services.project", "ProjectService"),
    "TaskService": ("localforge.services.task", "TaskService"),
    "ExecutionService": ("localforge.services.execution", "ExecutionService"),
    "AuditService": ("localforge.services.audit", "AuditService"),
    "SafetyService": ("localforge.services.safety", "SafetyService"),
    "APISimulationService": ("localforge.services.simulation", "APISimulationService"),
}


def __getattr__(name: str) -> Any:
    if name not in _SERVICE_IMPORTS:
        raise AttributeError(name)
    module_name, object_name = _SERVICE_IMPORTS[name]
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, object_name)
    globals()[name] = value
    return value
