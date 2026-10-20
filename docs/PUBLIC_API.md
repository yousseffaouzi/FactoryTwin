# Public Python API contract

FactoryTwin is pre-alpha software, but its intentional Python import surfaces are explicit and regression-tested. This document defines the imports that downstream examples and tests may rely on during the current development phase. It is a compatibility contract for this repository, not a semantic-versioning or production-support guarantee.

## Preferred package-root imports

Use the package root for ordinary simulator code:

```python
from factorytwin import (
    MULTI_FAULT_TRACE_SCHEMA,
    ProductionLine,
    QUALITY_TRACE_SCHEMA,
)
```

The package-root public surface is exactly:

- `ProductionLine` — the composed software-only simulator runtime exposed by `factorytwin.sim.ProductionLine`.
- `QUALITY_TRACE_SCHEMA` — the quality/genealogy trace schema identifier.
- `MULTI_FAULT_TRACE_SCHEMA` — the multi-fault trace schema identifier.

`ProductionLine` currently resolves to `RuntimeProductionLine`. The implementation class name is not itself part of the package-root contract; callers should prefer `factorytwin.ProductionLine` or `factorytwin.sim.ProductionLine`.

## Historical `factorytwin.sim` compatibility facade

The historical simulator module remains a supported compatibility facade. Its explicit public surface is:

- `CUSTOM_TRACE_SCHEMA`
- `EngineProductionLine`
- `LineState`
- `MAX_REPLAY_OPERATIONS`
- `MULTI_FAULT_TRACE_SCHEMA`
- `ProductionLine`
- `QUALITY_TRACE_SCHEMA`
- `STATIONS`
- `TICK_DURATION_MS`
- `TRACE_SCHEMA`

`factorytwin.sim.ProductionLine` is the current composed runtime. `factorytwin.sim.EngineProductionLine` is the deterministic base engine retained for compatibility and lower-level testing; it is not the package-root simulator class.

## What is not covered by this contract

Implementation modules such as `factorytwin.engine`, `factorytwin.genealogy`, `factorytwin.faults`, and `factorytwin.runtime` are internal layering details unless a symbol is also exported through one of the supported surfaces above. Their internal class names, inheritance structure, and helper functions may change as the architecture evolves.

The HTTP API, SSE transport, SQLite schema/recovery rules, trace payload formats, and browser UI have their own behavior tests and documentation; this document only defines Python import compatibility.

This contract does not expand FactoryTwin beyond software simulation. It does not imply PLC, SCADA, robotics, fieldbus, wire-compatible OPC UA, hardware control, safety-system use, or validation against a physical plant.

## Regression policy

`tests/test_module_boundary.py` verifies the exact `__all__` declarations, star-import results, runtime/base-engine identities, and the acyclic internal import boundary. Intentional public-surface changes should therefore update this document and the regression tests together.
