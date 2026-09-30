"""Registry and discovery decorator for pluggable validators."""

from collections.abc import Callable
from typing import Any
from app.validators.base import BaseValidator

_VALIDATOR_REGISTRY: dict[str, type[BaseValidator]] = {}


def register_validator(name: str) -> Callable[[type[BaseValidator]], type[BaseValidator]]:
    """Decorator to register a validator class in the discovery registry."""

    def decorator(cls: type[BaseValidator]) -> type[BaseValidator]:
        cls.name = name
        _VALIDATOR_REGISTRY[name] = cls
        return cls

    return decorator


def get_validator_class(name: str) -> type[BaseValidator]:
    """Retrieve registered validator class by identifier."""
    if name not in _VALIDATOR_REGISTRY:
        raise KeyError(f"Validator '{name}' is not registered. Available: {list(_VALIDATOR_REGISTRY.keys())}")
    return _VALIDATOR_REGISTRY[name]


def list_registered_validators() -> list[dict[str, Any]]:
    """List all registered validator implementations and schemas."""
    result = []
    for name, cls in _VALIDATOR_REGISTRY.items():
        schema = cls.param_schema.model_json_schema() if cls.param_schema else {}
        result.append(
            {
                "name": name,
                "description": getattr(cls, "description", ""),
                "param_schema": schema,
            }
        )
    return result
