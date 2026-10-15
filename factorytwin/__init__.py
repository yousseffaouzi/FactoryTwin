"""FactoryTwin software-only production-line simulation."""

# FT-008 keeps the historical sim.py API while layering genealogy/quality in a
# subclass. Rebinding the module symbol means existing imports continue to use
# `factorytwin.sim.ProductionLine` without rewriting legacy trace fixtures.
from . import sim as _sim
from .genealogy import GenealogyProductionLine, QUALITY_TRACE_SCHEMA

_sim.ProductionLine = GenealogyProductionLine
_sim.QUALITY_TRACE_SCHEMA = QUALITY_TRACE_SCHEMA
