"""Registry and auto-discovery decorator for probe types."""

from collections.abc import Callable
from typing import Any
from app.probes.base import BaseProbe
from app.schemas.attack import RegisteredAttackInfo

_PROBE_REGISTRY: dict[str, type[BaseProbe]] = {}


def register_probe(name: str) -> Callable[[type[BaseProbe]], type[BaseProbe]]:
    """Decorator to register a probe implementation."""

    def decorator(cls: type[BaseProbe]) -> type[BaseProbe]:
        cls.name = name
        _PROBE_REGISTRY[name] = cls
        return cls

    return decorator


def get_probe_class(name: str) -> type[BaseProbe]:
    """Retrieve registered probe class by name."""
    if name not in _PROBE_REGISTRY:
        raise KeyError(f"Probe '{name}' not found. Available probes: {list(_PROBE_REGISTRY.keys())}")
    return _PROBE_REGISTRY[name]


def list_registered_probes() -> list[dict[str, Any]]:
    """Return catalog of available probe algorithms with parameter schemas."""
    catalog = []
    for name, cls in _PROBE_REGISTRY.items():
        schema = cls.param_schema.model_json_schema() if hasattr(cls, "param_schema") else {}
        catalog.append(
            {
                "name": name,
                "description": getattr(cls, "description", ""),
                "requires_whitebox": getattr(cls, "requires_whitebox", False),
                "param_schema": schema,
            }
        )
    return catalog
