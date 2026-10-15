# FactoryTwin — master task tracker

**Scope:** simulator + digital-twin software only. No physical PLC, robot, or industrial equipment integration.

Legend: `DONE`, `IN PROGRESS`, `TODO`, `BLOCKED`, `ON HOLD`.

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| FT-001 | DONE | P0 | Document architecture and simulation scope | `README.md`, `docs/ARCHITECTURE.md` |
| FT-002 | DONE | P0 | Create deterministic production-line simulator | `factorytwin/sim.py` |
| FT-003 | DONE | P0 | Implement local API and interactive browser demo | `python -m factorytwin` |
| FT-004 | DONE | P0 | Add unit tests and GitHub Actions CI | Automated tests |
| FT-005 | DONE | P0 | Formalize state transitions, interlocks and invariants | `ProductionLine.state`, `validate()`, documented transition table, 24 simulator tests and 3 loopback API regression tests (`python -m unittest discover -s tests -v`) |
| FT-006 | DONE | P0 | Add timestamped event stream and deterministic replay | Event `seq` + `sim_time_ms`; JSON trace export/replay; `tests/fixtures/replay_scenario_v1.json`; 42 automated tests (including API regressions) |
| FT-007 | DONE | P1 | Build configurable station graph + cycle-time model | Strict `FactoryBlueprint` validation; 1–32 single-route stations; configurable productive `cycle_ticks`; `config/assembly_line.json`; trace.v2 replay; CLI + dashboard integration; 58/58 GitHub Actions tests |
| FT-008 | DONE | P1 | Implement workpiece genealogy and quality routes | Immutable workpiece genealogy; deterministic GOOD/SCRAP/same-station REWORK scenario semantics; conservation/interlock/backpressure + trace.v1/v2 compatibility and trace.v3 replay; read-only genealogy API; 72/72 GitHub Actions tests at `64a8667f33d63f95aedd4f9b12267c0c1162b630` ([run 38666833965](https://github.com/yousseffaouzi/FactoryTwin/actions/runs/38666833965)) |
| FT-009 | DONE | P1 | Persist events and snapshots in SQLite | Optional local SQLite schema v2; transactional operation/snapshot/event journals; reset preserves historical sessions; replay-validated restart recovery; v1→v2 migration; write-failure memory rollback; bounded concurrent reads; default no-database mode preserved; 86/86 GitHub Actions tests at `46ec6b3fd2eaee68e2ad08d9ed6377965d53b457` ([run 38667404492](https://github.com/yousseffaouzi/FactoryTwin/actions/runs/38667404492)) |
| FT-010 | TODO | P1 | Add production KPIs / OEE with honest definitions | Documented formulas and tests |
| FT-011 | TODO | P1 | Add WebSockets or SSE streaming | Reconnect/resync tests |
| FT-012 | TODO | P2 | Visual 2D factory floor and optional 3D layer | Accessible layout and screenshot review |
| FT-013 | TODO | P2 | Model fault injection for multiple stations | Fault matrix + deterministic test suite |
| FT-014 | TODO | P2 | Optional OPC UA *simulator* adapter | Local mock OPC UA integration tests |
| FT-015 | TODO | P2 | Publish GIF demo and architecture blog | Docs include reproduction steps |
| FT-016 | ON HOLD | P3 | PLC, SCADA, robotics, industrial plant interfaces | Separate future phase after safety review |

Tracker does not indicate a production-ready industrial digital twin.
