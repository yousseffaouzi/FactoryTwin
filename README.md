# FactoryTwin

**A software-only industrial production-line digital twin prototype.**

> **Status:** pre-alpha demo. All factory equipment, signals, workpieces and faults are simulated. **Not a PLC, SCADA, hardware controller, OPC UA server, or production-ready digital twin.**

## What you can run today
- Deterministic small production-line simulator with four virtual stations.
- Workpiece flow, production count, scrap count, equipment states and alarm log.
- Explicit `RUNNING` / `PAUSED` / `FAULT` state model with tested fault interlocks and workpiece accounting invariants.
- Browser dashboard and local JSON API.
- Pause, resume, inject/clear station fault and reset operations (localhost only).
- Automated unit and loopback API tests; no dependencies, Docker or hardware required.

## Quick start
Requires Python 3.11+.

```bash
python -m factorytwin
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

- `factorytwin/sim.py` — station state, workpiece movement, counter and fault logic.
- `factorytwin/__main__.py` — local demo API and static serving.
- `web/index.html` — zero-build production line UI.
- `TODO.md` — progress tracker with statuses.
- `docs/ARCHITECTURE.md` — implemented state transitions, invariants and roadmap.

The current fault model supports **one latched station fault** and blocks the whole pipeline. `resume` does not clear faults; `clear_fault` does not override `pause`. Calling `GET /api/snapshot` advances an observation tick even when production is paused or faulted, but workpieces do not move. See [state transitions and invariants](docs/ARCHITECTURE.md#ft-005-line-states-and-interlocks-implemented).

## Future (not yet implemented)
Event persistence and deterministic replay, scenario designer, recipe / cycle time configuration, extended equipment states and recovery timing, WebSockets, optional OPC UA adapter, OEE with clearly-defined denominator and planned time, 2D/3D animated plant map, and broader integration tests.

## Safety
This project must **never** be used as an industrial control system. The demo `/api/control` has no authentication because it binds to loopback only; it must not be exposed to untrusted networks.

## References
- OPC Foundation / OPC UA: https://opcfoundation.org/about/opc-technologies/opc-ua/
- Eclipse Ditto digital twins: https://eclipse.dev/ditto/intro-overview.html

MIT-licensed software. See `LICENSE` and `CONTRIBUTING.md`.
