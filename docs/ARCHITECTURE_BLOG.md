# Building FactoryTwin: a local-first industrial simulation prototype

FactoryTwin started as a deliberately small four-station production-line demo. The goal was not to imitate a complete plant on day one. The goal was to establish the behaviors that become difficult to repair later: deterministic state transitions, workpiece conservation, explicit interlocks, replayability, strict configuration validation, and an honest boundary between simulated software and physical industrial systems.

The result is still a prototype, but it now has a coherent software architecture that can support deeper industrial-engineering experiments without pretending to be a deployed control system.

## Start with invariants, not graphics

The earliest line model had four synthetic stations and a browser page. The important step was formalizing what a simulator is allowed to do.

FactoryTwin separates a user pause latch from station-fault latches. A paused line reports `PAUSED` even when a fault remains latched. `resume` does not clear faults, and clearing a fault does not silently resume a paused line. Observation time continues while productive activity is interlocked.

Workpiece accounting is equally explicit:

```text
generated workpieces = completed + scrapped + active workpieces
```

That invariant is checked continuously. A simulator that loses or duplicates parts under backpressure is not a useful basis for genealogy, persistence, or OEE.

## Deterministic time and replay

FactoryTwin uses synthetic logical ticks rather than wall-clock timing. That makes a run reproducible and testable. Events carry monotonically ordered sequence numbers, ticks and simulated milliseconds, while the UTC timestamp in an HTTP snapshot is only a capture time.

Replay traces evolved without discarding old fixtures. The original default line keeps `trace.v1`; custom blueprints use `trace.v2`; quality/genealogy introduced `trace.v3`; multi-fault behavior added `trace.v4`. Backward compatibility is treated as a regression contract rather than an incidental implementation detail.

## Configuration without pretending the graph is general

The blueprint file looks graph-like, but the current routing model intentionally validates exactly one connected acyclic linear chain. It rejects branches, merges, cycles and disconnected stations.

That limitation matters for quality rework. FactoryTwin does not silently create a backward routing loop. A synthetic `REWORK` outcome repeats processing at the **same station** under the same workpiece identity. This provides meaningful reprocessing semantics while preserving the validated linear-route model. A true routing loop would require a separate queue/routing design.

## Genealogy and synthetic quality

Each workpiece can now carry a station-attempt history. Synthetic quality scenarios provide deterministic `GOOD`, `SCRAP` and `REWORK` decisions. Unspecified attempts default to good behavior, which keeps the ordinary demo deterministic and avoids hidden randomness.

Scrap is terminal and participates in conservation. Rework increments a rework-cycle count but does not create a new workpiece. Genealogy is exposed through a read-only API so an observation does not advance the simulation tick.

These are simulated quality semantics. They are not measurements from a real inspection system.

## Local persistence with recovery semantics

SQLite was added as an optional local durability layer rather than a mandatory service. The default demo can still run with no database. Persistence uses versioned schema/migration behavior, transactional journals and replay-based recovery checks.

The design keeps synthetic simulation time separate from wall-clock storage metadata and avoids turning persistence failure into a partially advanced in-memory simulation.

## Metrics only when denominators are defined

OEE is easy to display and easy to misrepresent. FactoryTwin therefore requires explicit planned-observation and ideal-cycle assumptions before producing an OEE value. Zero-denominator cases remain undefined rather than being coerced into plausible-looking percentages.

Availability, performance and quality values are synthetic session metrics. They are useful for controlled simulation experiments, not certification of physical equipment.

## Streaming without changing simulation semantics

The local SSE endpoint is transport, not a second simulation clock. It provides bounded replay, `Last-Event-ID` handling, resynchronization and slow-client isolation. Snapshot polling remains supported, and the existing snapshot endpoint retains its documented observation-tick behavior.

Keeping transport separate from simulation semantics prevents a browser reconnection policy from accidentally changing plant behavior.

## A 2D floor before a 3D showcase

The current visualization focuses on a responsive accessible 2D station floor. Text labels, semantic landmarks, progress information and reduced-motion behavior are more important at this stage than adding a 3D engine.

A 3D layer remains optional because visual complexity should not outrun the simulation model.

## Multiple faults, explicit recovery

The fault model expanded from one latched station to independent station fault latches while preserving the legacy controls. The whole production line remains interlocked when any modeled station fault is active, and the pause-precedence rule is unchanged.

Fault state is included in replay, persistence recovery and availability accounting so the feature is not only cosmetic.

## An OPC-UA-style mock, not an OPC UA server

FactoryTwin includes an optional in-process adapter that exposes typed synthetic nodes and validated control-style methods. This is useful for testing software boundaries and namespace ideas.

It intentionally does **not** open a wire-compatible OPC UA endpoint, discover field devices, or control physical equipment. Calling it a production OPC UA server would be inaccurate.

## Why the project remains local-first

The current server binds to `127.0.0.1` and its controls are unauthenticated. That is acceptable for a local development demo and unacceptable for an internet-facing industrial service.

The project therefore keeps the following boundaries explicit:

- no physical PLC/SCADA/robot control;
- no production-network deployment;
- no cloud service required;
- no claim that synthetic cycle times are calibrated machine measurements;
- no claim that threshold or scenario logic is validated predictive maintenance;
- no claim that software tests validate a physical digital twin.

## What the architecture enables next

The current foundation can support richer queue/routing models, generalized rework paths, scenario tooling, more equipment abstractions, historical analysis and optional 3D visualization. Those should be introduced only when their semantics can be stated and tested.

FactoryTwin's value comes from being explicit about what is modeled. A credible simulation platform is not the one with the most industrial vocabulary; it is the one whose state, timing, routing, quality, persistence and metrics mean exactly what the code and tests say they mean.
