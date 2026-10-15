"""FactoryTwin software-only production-line simulation."""

# FT-008 keeps the historical sim.py API while layering genealogy/quality in a
# subclass. Rebinding the module symbol means existing imports continue to use
# `factorytwin.sim.ProductionLine` without rewriting legacy trace fixtures.
from . import sim as _sim
from .genealogy import GenealogyProductionLine, QUALITY_TRACE_SCHEMA

_original_replay = GenealogyProductionLine.replay.__func__


def _replay_with_legacy_divergence_guard(cls, trace):
    """Normalize malformed reset traces to the legacy ValueError contract."""
    try:
        return _original_replay(cls, trace)
    except IndexError as exc:
        raise ValueError("trace divergence after reset") from exc


GenealogyProductionLine.replay = classmethod(_replay_with_legacy_divergence_guard)
_sim.ProductionLine = GenealogyProductionLine
_sim.QUALITY_TRACE_SCHEMA = QUALITY_TRACE_SCHEMA
