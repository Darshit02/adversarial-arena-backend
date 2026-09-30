"""Registry and auto-discovery decorator for attack algorithms."""

from collections.abc import Callable

from app.attacks.base import BaseAttack
from app.schemas.attack import RegisteredAttackInfo

_ATTACK_REGISTRY: dict[str, type[BaseAttack]] = {}


def register_attack(name: str) -> Callable[[type[BaseAttack]], type[BaseAttack]]:
    """Decorator to register an attack class in the engine discovery catalog."""

    def decorator(cls: type[BaseAttack]) -> type[BaseAttack]:
        cls.name = name
        _ATTACK_REGISTRY[name] = cls
        return cls

    return decorator


def get_attack_class(name: str) -> type[BaseAttack]:
    """Retrieve registered attack class by name."""
    if name not in _ATTACK_REGISTRY:
        raise KeyError(
            f"Attack '{name}' not found. Available attacks: {list(_ATTACK_REGISTRY.keys())}"
        )
    return _ATTACK_REGISTRY[name]


def list_registered_attacks() -> list[RegisteredAttackInfo]:
    """Return schema and metadata for all available attack algorithms."""
    catalog: list[RegisteredAttackInfo] = []
    for name, cls in _ATTACK_REGISTRY.items():
        schema = cls.param_schema.model_json_schema() if hasattr(cls, "param_schema") else {}
        catalog.append(
            RegisteredAttackInfo(
                name=name,
                description=getattr(cls, "description", ""),
                requires_whitebox=getattr(cls, "requires_whitebox", False),
                param_schema=schema,
            )
        )
    return catalog
