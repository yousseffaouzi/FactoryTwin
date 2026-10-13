# FactoryTwin

**A software-only industrial production-line digital twin prototype.**

> **Status:** pre-alpha demo. All factory equipment, signals, workpieces and faults are simulated. **Not a PLC, SCADA, hardware controller, OPC UA server, or production-ready digital twin.**

## What you can run today
- Deterministic four-station demo and configurable linear virtual production lines (1–32 stations).
- Workpiece flow, production count, scrap count, equipment states and alarm log.
- Explicit `RUNNING` / `PAUSED` / `FAULT` state model with tested fault interlocks and workpiece accounting invariants.
- Timestamped synthetic events (simulation-relative milliseconds) and JSON-exportable deterministic replay traces, including custom blueprints.
- Validated JSON station connections, configurable productive cycle ticks, and single-slot backpressure.
- Browser dashboard and local JSON API.
- Pause, resume, inject/clear station fault and reset operations (localhost only).
- Automated unit and loopback API tests; no dependencies, Docker or hardware required.

## Quick start
Requires Python 3.11+.

```bash
python -m factorytwin
# or: python -m factorytwin --blueprint config/assembly_line.json
# open http://127.0.0.1:8766
```

Tests:

```bash
python -m unittest discover -s tests -v
```

API examples:

```bash
curl http://127.0.0.1:8766/api/snapshot
curl -X POST http://127.0.0.1:8766/api/control -H 'Content-Type: application/json' -d '{"action":"pause"}'
```

## Architecture

```text
Discrete tick simulator -> Equipment/workpiece state -> JSON snapshot + event log
                                                      |
                                           Local REST HTTP API
                                                      |
                                            Browser dashboard
```

- `factorytwin/sim.py` — station state, workpiece movement, cycle timing, counters, and fault logic.
- `factorytwin/blueprint.py` — strict JSON graph validation and canonical station order.
- `config/assembly_line.json` — example virtual factory blueprint.
- `factorytwin/__main__.py` — local demo API and static serving.
- `web/index.html` — zero-build production line UI.
- `TODO.md` — progress tracker with statuses.
- `docs/ARCHITECTURE.md` — implemented state transitions, replay format, invariants and roadmap.

The current fault model supports **one latched station fault** and blocks the whole pipeline. `resume` does not clear faults; `clear_fault` does not override `pause`. Calling `GET /api/snapshot` advances an observation tick even when production is paused or faulted, but workpieces do not move. See [state transitions and invariants](docs/ARCHITECTURE.md#ft-005-line-states-and-interlocks-implemented).

## Configurable station graph (FT-007)

A local JSON blueprint defines the stations, directed connections, and each station's `cycle_ticks` (productive simulation ticks). Start the **software-only** dashboard with:

```bash
python -m factorytwin --blueprint config/assembly_line.json
```

The example runs `Feed (1) → Inspect (2) → Pack (1)`; the browser automatically displays the configured machines and lets you inject faults into the selected station. Blueprints are strictly checked before starting the localhost server. This version supports **one linear route with one workpiece per station**, deterministic backpressure and cycle durations; loops, branching, merging, multi-machine queues and physical devices are outside its scope.

For scripting, use `ProductionLine.from_blueprint(data)` or `ProductionLine(blueprint=FactoryBlueprint.load(path))`. Custom simulations export replay traces under `factorytwin.trace.v2` (including the canonical blueprint and remaining cycle ticks), while the original default-line `trace.v1` fixtures remain compatible. See [FT-007 design](docs/ARCHITECTURE.md#ft-007-configurable-station-graph-and-cycle-ticks-implemented).

## Deterministic replay (FT-006)

Replay is available through the **Python engine**, not through the unauthenticated HTTP API:

```python
import json
from factorytwin.sim import ProductionLine

line = ProductionLine()
for _ in range(6):
    line.step()
line.control("pause")
trace = line.export_trace()  # JSON-serializable; independent of wall time
restored = ProductionLine.replay(json.loads(json.dumps(trace)))
assert restored.state_data() == line.state_data()
```

Every event includes `seq`, `tick`, and `sim_time_ms`; every tick is a fixed logical 1,000 ms. These are **synthetic** simulation timestamps, not wall-clock timestamps or measured machine durations. `recorded_at_utc` remains the time the snapshot was requested. The dashboard shows the most recent events, while replay uses a separate operation journal in memory. `reset` starts a new replay session; save a trace *before* resetting if you want to retain it. Trace persistence, automatic rotation, and streaming are not yet implemented. See [FT-006 replay design](docs/ARCHITECTURE.md#ft-006-timestamped-events-and-deterministic-replay-implemented).

## Future (not yet implemented)
Event persistence in SQLite, scenario designer, additional equipment types and queue/routing models, extended equipment states and recovery timing, WebSockets, optional OPC UA adapter, OEE with clearly-defined denominator and planned time, 2D/3D animated plant map, and broader integration tests.

## Safety
This project must **never** be used as an industrial control system. The demo `/api/control` has no authentication because it binds to loopback only; it must not be exposed to untrusted networks.

## References
- OPC Foundation / OPC UA: https://opcfoundation.org/about/opc-technologies/opc-ua/
- Eclipse Ditto digital twins: https://eclipse.dev/ditto/intro-overview.html

MIT-licensed software. See `LICENSE` and `CONTRIBUTING.md`.
