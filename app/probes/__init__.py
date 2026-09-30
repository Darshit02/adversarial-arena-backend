"""Pluggable probe algorithms module and registry discovery."""

from app.probes.autodan import AutoDANParams, AutoDANProbe
from app.probes.base import (
    BaseProbe,
    ProbeAttempt,
    ProbeResult,
)
from app.probes.gcg import GCGParams, GCGProbe
from app.probes.knowledge_decomp import KnowledgeDecompParams, KnowledgeDecompProbe
from app.probes.multiround import MultiRoundParams, MultiRoundProbe
from app.probes.pair import PAIRProbe
from app.probes.registry import (
    get_probe_class,
    list_registered_probes,
    register_probe,
)

__all__ = [
    "BaseProbe",
    "ProbeAttempt",
    "ProbeResult",
    "register_probe",
    "get_probe_class",
    "list_registered_probes",
    "PAIRProbe",
    "MultiRoundProbe",
    "MultiRoundParams",
    "AutoDANProbe",
    "AutoDANParams",
    "GCGProbe",
    "GCGParams",
    "KnowledgeDecompProbe",
    "KnowledgeDecompParams",
]
