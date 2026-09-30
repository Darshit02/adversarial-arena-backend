"""Pluggable probe algorithms module and registry discovery."""

from app.probes.base import (
    BaseProbe,
    ProbeAttempt,
    ProbeResult,
)
from app.probes.registry import (
    get_probe_class,
    list_registered_probes,
    register_probe,
)
from app.probes.pair import PAIRProbe
from app.probes.multiround import MultiRoundProbe, MultiRoundParams
from app.probes.autodan import AutoDANProbe, AutoDANParams
from app.probes.gcg import GCGProbe, GCGParams
from app.probes.knowledge_decomp import KnowledgeDecompProbe, KnowledgeDecompParams

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
