# FactoryTwin architecture (software-only)

## Prototype (implemented)

`ProductionLine.step()` is a discrete observation tick. By default a workpiece passes through feeder, conveyor, processing and packing stations with one productive tick per stage. FT-007 also permits a validated linear station graph with configurable cycle ticks. A single latched station fault blocks movement throughout this simple line. A local HTTP API exposes snapshots and demo controls.

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

1. Exactly one pipeline slot exists per configured station (four in the default demo); the station graph is a validated single route.
2. The enabled flag is Boolean and the latched fault references a known station.
3. Tick/counters are non-negative integers, and the next generated ID is positive.
4. Active workpieces have distinct, generated `WP-` IDs; generated IDs are not reused.
5. Workpiece conservation holds: `next_id - 1 == completed + scrapped + in_process`.
6. A paused or faulted line does not move/create/complete workpieces or change production counters. A simulated fault blocks the **whole line**, not only its named station.
7. Invalid commands or a second conflicting fault do not mutate state. Fault recovery requires `clear_fault`; resuming alone cannot bypass the fault.

The **observation tick still advances** when paused or faulted, preserving the existing `step()`/`GET /api/snapshot` behavior. It is not a measure of productive runtime. `scrapped` currently remains zero because scrap decisions have not been modeled. UI events retain only the last 40 entries; snapshots return the most recent 12. Snapshot event dictionaries are copies, so clients cannot accidentally mutate internal event history.

### API compatibility

`GET /api/snapshot`, `GET /api/health`, and `POST /api/control` remain unchanged. Snapshot fields and existing station status strings are preserved. Invalid controls still produce HTTP 400 with an error message; repeated valid actions produce HTTP 200 and remain idempotent. `recorded_at_utc` reflects wall-clock capture time, and is intentionally **not** part of deterministic simulation/replay.

## FT-006: timestamped events and deterministic replay (implemented)

All timing information is **simulated**; no physical equipment, external clock synchronization, or real-time control is involved.

### Event and clock model

- `step()` increments an **observation tick** even while paused or faulted. Every tick represents `TICK_DURATION_MS = 1000` *logical milliseconds*. This is a declared synthetic clock, **not** measured processing time or real seconds.
- Each domain event has its original `event`, `tick` and payload (`station` / `workpiece_id`), plus `seq` (an increasing event sequence) and `sim_time_ms` (tick × 1,000). Multiple events during one tick receive distinct sequence numbers but the same simulated time.
- The existing `events` buffer still retains at most 40 domain events. `/api/snapshot` returns its most recent 12. These are for the UI, **not** replay. `recorded_at_utc` on a snapshot remains a real UTC request/capture timestamp, and is explicitly excluded from replay comparisons.
- `operations` is a separate, chronological, in-memory replay journal of all accepted `control` and `step` operations, including accepted no-ops and paused/faulted ticks. It records `seq`, `kind`, `tick`, `sim_time_ms` and, for controls, `action` plus a station only when the action is `fault`. Invalid controls are not recorded.
- `reset` clears production state, buffered events, event/operation sequences, and earlier replay history, then records a deterministic `simulation_reset` event and a single `reset` control operation. Save/export the current trace **before** resetting if the previous session is needed.

### Trace export and verification

`ProductionLine.export_trace()` returns a detached, JSON-compatible envelope:

```json
{
  "schema": "factorytwin.trace.v1",
  "tick_duration_ms": 1000,
  "operations": [
    {"seq": 1, "kind": "step", "tick": 1, "sim_time_ms": 1000},
    {"seq": 2, "kind": "control", "tick": 1, "sim_time_ms": 1000, "action": "pause"}
  ],
  "final_state": {"...": "deterministic state projection"}
}
```

The `final_state` object contains current workpieces, counters, control latches, event sequence and bounded domain-event history, but omits non-deterministic `recorded_at_utc`. `ProductionLine.replay(trace)` validates the version, field names, sequential operation numbers and virtual timestamps; executes operations in order on a fresh isolated `ProductionLine`; and **rejects** malformed commands, unexpected transitions, out-of-order records and a mismatched final state. A replay produces no network traffic and does not call HTTP controls. Exact JSON number-vs-boolean types in final state are checked. Traces are not signed or trusted for authentication; they are reproducibility artifacts.

Example usage:

```python
import json
from factorytwin.sim import ProductionLine

live = ProductionLine()
live.step()
live.control("pause")
trace = json.loads(json.dumps(live.export_trace()))
replayed = ProductionLine.replay(trace)
assert replayed.state_data() == live.state_data()
```

The committed fixture `tests/fixtures/replay_scenario_v1.json` covers production, pause, fault injection, recovery, and continued production. No new HTTP route is exposed for trace importing or replay; the existing localhost-only API remains intact.

**Limitations:** The full operation journal grows in memory until a reset; no durability, compression or automatic retention is provided yet (FT-009). Replay currently caps an input at 1,000,000 operations to limit resource consumption; very long uninterrupted sessions may exceed that cap and require future trace segmentation. The clock is fixed at one logical second per tick; station cycle lengths are now configurable in FT-007, but there is still no independent simulated event scheduler. Reproducibility is restricted to this trace version and implementation; schema evolution/migrations are future work.

## FT-007: configurable station graph and cycle ticks (implemented)

FactoryTwin accepts **local JSON blueprints** with three required keys: `version` (integer 1), `stations` (objects with unique `id` and positive integer `cycle_ticks`), and `connections` (directed `from`/`to` edges). The parser rejects unknown fields, unknown nodes, duplicate IDs or edges, cycles, disconnected segments, multiple inputs/outputs, branching and merging. It accepts 1–32 stations with cycle lengths from 1–10,000 productive ticks. Station IDs use letters, digits, underscore and hyphen, beginning with a letter, up to 32 characters.

The current scope intentionally supports **one non-branching chain**, with exactly one entry station and one exit. Source file ordering does not determine the route: graph validation orders stations from entry to exit. `factorytwin/blueprint.py` exposes `FactoryBlueprint.from_dict()`, `FactoryBlueprint.load()`, and `to_dict()`; `ProductionLine.from_blueprint(data)` creates an isolated run.

Example: [`config/assembly_line.json`](../config/assembly_line.json) specifies the linear chain `Feed (1 tick) → Inspect (2 ticks) → Pack (1 tick)`. Start the local dashboard with:

```bash
python -m factorytwin --blueprint config/assembly_line.json
```

Each station has one workpiece slot. An item arriving at a station requires exactly `cycle_ticks` **productive observation ticks** before transfer or completion. A station whose work is complete may be blocked if the next slot is occupied; its `remaining_ticks` stays zero until it can transfer. Updates use downstream-first processing: a workpiece moves at most one station per tick, and a downstream completion can free its slot for an upstream transfer in that same tick. An empty entry station injects one new synthetic workpiece on a productive tick. Pausing or a latched fault freezes processing, transfers and injection while observation ticks still advance. `reset` clears the session, but **preserves the validated blueprint**.

The existing `GET /api/snapshot` and `POST /api/control` endpoints work unchanged. `stations[]` now additionally exposes `cycle_ticks` and `remaining_ticks`; the dashboard dynamically populates the fault-station selector using the configured station names. The default 4-station, 1-tick line preserves its existing counters, event ordering, snapshots' original fields, and unmodified `factorytwin.trace.v1` replay fixture.

Custom non-default blueprints export `factorytwin.trace.v2` with their canonical blueprint and remaining processing ticks included in `final_state`. Replay validates the blueprint, reconstructs processing progress, and rejects state divergence. Existing `trace.v1` files still replay with the default four-station line. No new network endpoints for trace import/export or for editing blueprints are provided. Changes require restarting the local simulator with another blueprint.

**Not yet supported:** queues larger than one, branching/merging, parallel machines, rework, recipes, changeover times, random faults, yield modeling, physically calibrated performance, or operating equipment. These require explicit routing and timing semantics before implementation.

## Planned core

- Model productive machine time separately from observation ticks and support fast-forward.
- Enrich station blueprints with equipment types, queue capacities, failure profiles and multi-route graphs.
- Durable event persistence, full event-sourced state transitions, workpiece genealogy and audits.
- Defined production KPIs: good/scrap units, throughput, availability/performance/quality from known schedule.
- UI plant map and transport/state animation.

## Integration boundaries

This local app exposes simple JSON APIs only. OPC UA is an **optional future integration adapter** because it is a widely adopted industrial interoperability standard. Nothing here claims OPC UA conformance. Eclipse Ditto is a useful reference for separating device/twin representations; not integrated today.

## Security

The current HTTP POST controls are not authenticated, so the server must remain bound to `127.0.0.1`. No actual actuator commands may originate from this demo. For a public service, add authn/authz, CSRF/CORS threat review, audit logging and isolated simulation instances.

## Terminology

This is an illustrative *digital twin software prototype*, not a validated physical twin of a specific real machine or assembly line. All equipment data and production counts are synthetic.
