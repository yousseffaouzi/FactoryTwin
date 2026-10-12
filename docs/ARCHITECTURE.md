# FactoryTwin architecture (software-only)

## Prototype (implemented)

`ProductionLine.step()` is a discrete observation tick. A workpiece passes through feeder, conveyor, processing and packing stations with one processing step per stage. A single latched station fault blocks movement throughout this simple line. A local HTTP API exposes snapshots and demo controls.

## FT-005: line states and interlocks (implemented)

The **observable** line state is computed from two independent pieces of state:

- `running` — whether the operator has enabled production (`True` initially).
- `fault_station` — the sole latched fault (`None` initially, otherwise one of the four station names).

| Running enabled | Fault latched | Reported `state` | Processing permitted |
|---|---|---|---|
| Yes | No | `RUNNING` | Yes |
| Yes | Yes | `FAULT` | No |
| No | No | `PAUSED` | No |
| No | Yes | `PAUSED` | No |

`PAUSED` takes precedence in the line-level status to maintain the existing JSON API. A fault remains latched while paused and is visible on the corresponding station's `status=FAULT`; other stations report `PAUSED`. When enabled with a fault, the faulted station reports `FAULT` and all others report `BLOCKED`.

### Control transitions

| Command | Effect | Repeated/invalid behavior |
|---|---|---|
| `pause` | Sets `running=False`; does not clear a fault | Already paused: no-op, no duplicate event |
| `resume` | Sets `running=True`; **does not clear a fault** | Already enabled: no-op; fault continues to block movement |
| `fault` with valid station | Latches one fault, stopping the entire pipeline | Same station: no-op; different station: `ValueError` until fault cleared; unknown station: `ValueError` |
| `clear_fault` | Clears a latched fault; **does not resume** a paused line | No fault: no-op |
| `reset` | Restores the original empty, enabled line; tick/counters/IDs reset | Clears event history and records one `simulation_reset`; repeated reset produces the same state |
| Unknown command | Never applied | `ValueError`, no state/event mutation |

Only `RUNNING`, `PAUSED` and `FAULT` are presently supported. `IDLE`, `RECOVERING` and `STOPPED` are deliberately **not** added because the current four-stage prototype has no startup, recovery timing, or shutdown semantics. Those can be introduced once there are precise requirements and tests. The simulator is not a safety interlock for real machines.

### Invariants

`ProductionLine.validate()` checks before/after processing and before accepting ordinary controls:

1. Exactly four pipeline slots exist, one per known station.
2. The enabled flag is Boolean and the latched fault references a known station.
3. Tick/counters are non-negative integers, and the next generated ID is positive.
4. Active workpieces have distinct, generated `WP-` IDs; generated IDs are not reused.
5. Workpiece conservation holds: `next_id - 1 == completed + scrapped + in_process`.
6. A paused or faulted line does not move/create/complete workpieces or change production counters. A simulated fault blocks the **whole line**, not only its named station.
7. Invalid commands or a second conflicting fault do not mutate state. Fault recovery requires `clear_fault`; resuming alone cannot bypass the fault.

The **observation tick still advances** when paused or faulted, preserving the existing `step()`/`GET /api/snapshot` behavior. It is not a measure of productive runtime. `scrapped` currently remains zero because scrap decisions have not been modeled. Events retain only the last 40 entries; snapshots return the most recent 12. Snapshot event dictionaries are copies, so clients cannot accidentally mutate internal event history.

### API compatibility

`GET /api/snapshot`, `GET /api/health`, and `POST /api/control` remain unchanged. Snapshot fields and existing station status strings are preserved. Invalid controls still produce HTTP 400 with an error message; repeated valid actions produce HTTP 200 and remain idempotent. `recorded_at_utc` reflects wall-clock capture time, and is intentionally **not** part of deterministic simulation/replay.

## Planned core

- Separate productive simulation time from observation ticks and wall time for fast-forward and deterministic replay.
- Configurable station blueprints: type, cycle time, queue capacity, failure profile, downstream routes.
- Event-sourced state + replay, workpiece IDs, audits and clear recovery semantics.
- Defined production KPIs: good/scrap units, throughput, availability/performance/quality from known schedule.
- UI plant map and transport/state animation.

## Integration boundaries

This local app exposes simple JSON APIs only. OPC UA is an **optional future integration adapter** because it is a widely adopted industrial interoperability standard. Nothing here claims OPC UA conformance. Eclipse Ditto is a useful reference for separating device/twin representations; not integrated today.

## Security

The current HTTP POST controls are not authenticated, so the server must remain bound to `127.0.0.1`. No actual actuator commands may originate from this demo. For a public service, add authn/authz, CSRF/CORS threat review, audit logging and isolated simulation instances.

## Terminology

This is an illustrative *digital twin software prototype*, not a validated physical twin of a specific real machine or assembly line. All equipment data and production counts are synthetic.
