# FactoryTwin architecture (software-only)

## Prototype (implemented)

`ProductionLine.step()` is a discrete time tick. A workpiece passes through feeder, conveyor, processing and packing stations with a fixed duration per stage. The simulated fault flag pauses processing, and an explicit `clear_fault` control resumes the line. A local HTTP API exposes snapshots and demo controls.

## Planned core

- Separate simulation clock from wall time for fast-forward and deterministic replay.
- Explicit state-transition model for `IDLE`, `RUNNING`, `PAUSED`, `FAULT`, `RECOVERING`.
- Station blueprints: type, cycle time, queue capacity, failure profile, downstream routes.
- Event-sourced state + replay, workpiece IDs, audits.
- Defined production KPIs: good/scrap units, throughput, availability/performance/quality from known schedule.
- UI plant map and transport/state animation.

## Integration boundaries

This local app exposes simple JSON APIs only. OPC UA is an **optional future integration adapter** because it is a widely adopted industrial interoperability standard. Nothing here claims OPC UA conformance. Eclipse Ditto is a useful reference for separating device/twin representations; not integrated today.

## Security

The current HTTP POST controls are not authenticated, so server must remain bound to `127.0.0.1`. No actual actuator commands may originate from this demo. For a public service, add authn/authz, CSRF/CORS threat review, audit logging and isolated simulation instances.

## Terminology

This is an illustrative *digital twin software prototype*, not a validated physical twin of a specific real machine or assembly line. All equipment data and production counts are synthetic.
