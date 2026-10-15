"""Stable public simulator facade.

The deterministic base engine lives in :mod:`factorytwin.engine`.  This module
keeps the historical ``factorytwin.sim`` import surface while composing the
current runtime implementation without mutating module attributes from package
``__init__``.
"""
from __future__ import annotations

from .engine import (
    CUSTOM_TRACE_SCHEMA,
    MAX_REPLAY_OPERATIONS,
    STATIONS,
    TICK_DURATION_MS,
    TRACE_SCHEMA,
    LineState,
    ProductionLine as EngineProductionLine,
)

# During layered module initialization, genealogy/fault modules historically
# import ``ProductionLine`` from ``factorytwin.sim`` as their base class. Keep
# that name bound to the engine base until those layers are loaded, then expose
# the concrete public runtime below. No package-level mutation is required.
ProductionLine = EngineProductionLine

from .genealogy import QUALITY_TRACE_SCHEMA
from .faults import MULTI_FAULT_TRACE_SCHEMA
from .runtime import RuntimeProductionLine

ProductionLine = RuntimeProductionLine

__all__ = [
    "CUSTOM_TRACE_SCHEMA",
    "EngineProductionLine",
    "LineState",
    "MAX_REPLAY_OPERATIONS",
    "MULTI_FAULT_TRACE_SCHEMA",
    "ProductionLine",
    "QUALITY_TRACE_SCHEMA",
    "STATIONS",
    "TICK_DURATION_MS",
    "TRACE_SCHEMA",
]
