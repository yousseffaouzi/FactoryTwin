"""FactoryTwin software-only production-line simulation."""

# Preserve the historical `factorytwin.sim.ProductionLine` import while keeping
# runtime behavior in an explicit concrete class rather than mutating parent
# classes during package import.
from . import sim as _sim
from .genealogy import QUALITY_TRACE_SCHEMA
from .faults import MULTI_FAULT_TRACE_SCHEMA
from .runtime import RuntimeProductionLine

_sim.ProductionLine = RuntimeProductionLine
_sim.QUALITY_TRACE_SCHEMA = QUALITY_TRACE_SCHEMA
_sim.MULTI_FAULT_TRACE_SCHEMA = MULTI_FAULT_TRACE_SCHEMA
