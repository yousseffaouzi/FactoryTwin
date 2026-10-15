"""FactoryTwin software-only production-line simulation."""

# FT-008 keeps the historical sim.py API while layering genealogy/quality in a
# subclass. Rebinding the module symbol means existing imports continue to use
# `factorytwin.sim.ProductionLine` without rewriting legacy trace fixtures.
from . import sim as _sim
from .genealogy import GenealogyProductionLine, QUALITY_TRACE_SCHEMA
from .metrics import DEFAULT_METRICS_PLAN, production_metrics

_original_replay = GenealogyProductionLine.replay.__func__
_original_snapshot = GenealogyProductionLine.snapshot
_original_control = GenealogyProductionLine.control


def _replay_with_legacy_divergence_guard(cls, trace):
    """Normalize malformed reset traces to the legacy ValueError contract."""
    try:
        return _original_replay(cls, trace)
    except IndexError as exc:
        raise ValueError("trace divergence after reset") from exc


def _snapshot_with_metrics(self):
    data = _original_snapshot(self)
    data["metrics"] = production_metrics(self)
    return data


def _control_preserving_metrics_plan(self, action, station=None):
    # Metrics assumptions do not affect deterministic simulation/replay, but a
    # reset must not silently discard a locally selected reporting plan.
    plan = getattr(self, "metrics_plan", DEFAULT_METRICS_PLAN)
    result = _original_control(self, action, station)
    self.metrics_plan = plan
    return result


GenealogyProductionLine.replay = classmethod(_replay_with_legacy_divergence_guard)
GenealogyProductionLine.snapshot = _snapshot_with_metrics
GenealogyProductionLine.control = _control_preserving_metrics_plan
_sim.ProductionLine = GenealogyProductionLine
_sim.QUALITY_TRACE_SCHEMA = QUALITY_TRACE_SCHEMA
