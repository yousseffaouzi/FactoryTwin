# FactoryTwin — master task tracker

**Scope:** simulator + digital-twin software only. No physical PLC, robot, or industrial equipment integration.

Legend: `DONE`, `IN PROGRESS`, `TODO`, `ON HOLD`.

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| FT-001 | DONE | P0 | Document architecture and simulation scope | `README.md`, `docs/ARCHITECTURE.md` |
| FT-002 | DONE | P0 | Create deterministic production-line simulator | `factorytwin/sim.py` |
| FT-003 | DONE | P0 | Implement local API and interactive browser demo | `python -m factorytwin` |
| FT-004 | DONE | P0 | Add unit tests and GitHub Actions CI | Automated tests |
| FT-005 | TODO | P0 | Formalize state transitions, interlocks and invariants | Property/unit tests covering fault edge cases |
| FT-006 | TODO | P0 | Add timestamped event stream and deterministic replay | Replay fixture reproduces final state |
| FT-007 | TODO | P1 | Build configurable station graph + cycle-time model | JSON blueprint validation |
| FT-008 | TODO | P1 | Implement workpiece genealogy and quality routes | Tests for scrap/rework tracking |
| FT-009 | TODO | P1 | Persist events and snapshots in SQLite | Migration and recovery tests |
| FT-010 | TODO | P1 | Add production KPIs / OEE with honest definitions | Documented formulas and tests |
| FT-011 | TODO | P1 | Add WebSockets or SSE streaming | Reconnect/resync tests |
| FT-012 | TODO | P2 | Visual 2D factory floor and optional 3D layer | Accessible layout and screenshot review |
| FT-013 | TODO | P2 | Model fault injection for multiple stations | Fault matrix + deterministic test suite |
| FT-014 | TODO | P2 | Optional OPC UA *simulator* adapter | Local mock OPC UA integration tests |
| FT-015 | TODO | P2 | Publish GIF demo and architecture blog | Docs include reproduction steps |
| FT-016 | ON HOLD | P3 | PLC, SCADA, robotics, industrial plant interfaces | Separate future phase after safety review |

Tracker does not indicate a production-ready industrial digital twin.
