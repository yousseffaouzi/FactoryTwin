"""Explicit public runtime composition for FactoryTwin.

This module keeps compatibility behavior in the concrete public simulator class
instead of mutating parent classes at package-import time.
"""
from __future__ import annotations

from .faults import MultiFaultProductionLine
from .metrics import DEFAULT_METRICS_PLAN, production_metrics


class RuntimeProductionLine(MultiFaultProductionLine):
    """Concrete public simulator with reporting and compatibility behavior."""

    @classmethod
    def replay(cls, trace: dict):
        """Replay supported traces while preserving the legacy error contract."""
        try:
            return super().replay(trace)
        except IndexError as exc:
            raise ValueError("trace divergence after reset") from exc

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["metrics"] = production_metrics(self)
        return data

    def control(self, action: str, station: str | None = None) -> None:
        # Reset rebuilds type(self), so explicitly retain the reporting-only plan.
        plan = getattr(self, "metrics_plan", DEFAULT_METRICS_PLAN)
        super().control(action, station)
        self.metrics_plan = plan
