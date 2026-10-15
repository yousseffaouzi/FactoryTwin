"""FactoryTwin software-only production-line simulation."""

# The public simulator is composed inside factorytwin.sim. Importing the package
# no longer mutates another module's ProductionLine or trace-schema attributes.
from .sim import MULTI_FAULT_TRACE_SCHEMA, QUALITY_TRACE_SCHEMA, ProductionLine

__all__ = ["MULTI_FAULT_TRACE_SCHEMA", "ProductionLine", "QUALITY_TRACE_SCHEMA"]
