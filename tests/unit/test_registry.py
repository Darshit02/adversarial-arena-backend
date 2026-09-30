"""Unit tests for probe and validator registries and decorator discovery."""

import pytest

from app.probes.registry import get_probe_class, list_registered_probes
from app.validators.registry import get_validator_class, list_registered_validators


def test_probe_registry_lookup():
    """Verify get_probe_class retrieves registered classes and raises KeyError on unknown."""
    pair_cls = get_probe_class("pair")
    assert pair_cls.name == "pair"

    with pytest.raises(KeyError) as exc_info:
        get_probe_class("nonexistent_probe_name")

    assert "not found" in str(exc_info.value)


def test_validator_registry_lookup():
    """Verify get_validator_class retrieves registered classes and raises KeyError on unknown."""
    kw_cls = get_validator_class("keyword_filter")
    assert kw_cls.name == "keyword_filter"

    with pytest.raises(KeyError) as exc_info:
        get_validator_class("nonexistent_validator_name")

    assert "is not registered" in str(exc_info.value)


def test_schemas_present_in_catalogs():
    """Verify that catalog metadata contains parameter schemas."""
    probes = list_registered_probes()
    for p in probes:
        assert "name" in p
        assert "description" in p
        assert "param_schema" in p
        assert isinstance(p["param_schema"], dict)

    validators = list_registered_validators()
    for v in validators:
        assert "name" in v
        assert "param_schema" in v
        assert isinstance(v["param_schema"], dict)
