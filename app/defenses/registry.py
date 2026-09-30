"""Registry and discovery decorator for pluggable defenses."""

from collections.abc import Callable
from typing import Any

from app.defenses.base import BaseDefense

_DEFENSE_REGISTRY: dict[str, type[BaseDefense]] = {}


def register_defense(name: str) -> Callable[[type[BaseDefense]], type[BaseDefense]]:
    """Decorator to register a defense class in the global discovery registry."""

    def decorator(cls: type[BaseDefense]) -> type[BaseDefense]:
        cls.name = name
        _DEFENSE_REGISTRY[name] = cls
        return cls

    return decorator


def get_defense_class(name: str) -> type[BaseDefense]:
    """Retrieve registered defense class by name."""
    if name not in _DEFENSE_REGISTRY:
        raise KeyError(
            f"Defense '{name}' is not registered. Available: {list(_DEFENSE_REGISTRY.keys())}"
        )
    return _DEFENSE_REGISTRY[name]


def list_registered_defenses() -> list[dict[str, Any]]:
    """List all registered defense implementations and schemas."""
    result = []
    for name, cls in _DEFENSE_REGISTRY.items():
        schema = cls.param_schema.model_json_schema() if cls.param_schema else {}
        result.append(
            {
                "name": name,
                "description": getattr(cls, "description", ""),
                "param_schema": schema,
            }
        )
    return result
