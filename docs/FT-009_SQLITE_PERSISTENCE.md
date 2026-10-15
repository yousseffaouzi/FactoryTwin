# FT-009 — Optional local SQLite persistence

FactoryTwin remains a local, software-only simulator. SQLite persistence is **opt-in** and writes only to a user-selected local file; the default `python -m factorytwin` path remains in-memory and dependency-free beyond Python's standard library.

## Transaction boundary

Every accepted `step()` or control operation is treated as one persistence unit. The simulator first applies the deterministic operation while the API lock excludes other callers, then SQLite commits the operation journal row, deterministic state snapshot, and any newly emitted domain events in one transaction. If that database transaction fails, FactoryTwin restores the complete pre-operation in-memory runtime before returning a `PersistenceError`. The HTTP server maps persistence failures to `503` and does not expose the uncommitted state.

This is application-level rollback around a single-process simulator; it is not a distributed transaction and does not claim industrial controller durability.

## Sessions and reset

Persistence uses a UUID session identity that is database metadata only and never participates in deterministic simulated time or replay. `started_at_utc` is wall-clock metadata; operation/event ordering continues to use deterministic `seq`, `tick`, and `sim_time_ms`.

A normal operation appends to the current session. `reset` atomically marks the previous session closed, creates a new session with the same validated blueprint and quality scenario, and writes the reset operation as the new session's first record. Historical sessions are retained rather than truncated.

## Stored records

Schema version 2 stores:

- `sessions`: session identity, wall-clock creation metadata, trace schema, canonical blueprint/quality configuration and closed/open state;
- `operations`: the complete replay operation journal, keyed by `(session_id, seq)`;
- `snapshots`: one deterministic final-state projection per accepted operation;
- `events`: the complete event journal, independent of the simulator's 40-event UI retention window.

Tick and sequence indexes support bounded local reads. `SQLiteStore.list_snapshots()` rejects limits outside `1..1000`.

## Recovery and integrity

Opening an existing database recovers the newest open session. FactoryTwin verifies contiguous operation sequence numbers, a matching latest snapshot, complete event sequence accounting, supported trace schema, stored configuration, and then reconstructs state through the existing deterministic replay validator. A supplied blueprint or quality scenario must match the open session or startup fails closed.

SQLite schema versioning uses `PRAGMA user_version`. Version 2 is current. A defined version-1 layout migrates transactionally to version 2 by adding the session `closed` state and indexes. Unknown future versions, unversioned non-empty databases, incomplete schemas, corrupted snapshots and replay divergence are rejected instead of silently repaired.

SQLite runs in WAL mode with foreign keys, a busy timeout, and full synchronous commits. Reads use independent connections so local readers can inspect bounded snapshots while the simulator writes.

## Usage

In-memory behavior is unchanged:

```bash
python -m factorytwin
```

Opt in to local persistence:

```bash
python -m factorytwin --database ./factorytwin.sqlite3
```

Persistence can be combined with the existing local blueprint and deterministic quality scenario options. Restarting with the same database restores the latest open session; explicit configuration supplied on restart must match the persisted session.

## Non-goals

FT-009 does not add a cloud database, multi-writer tenancy, remote database access, authentication, replication, backup policy, time-series analytics, OEE, or physical equipment connectivity. It does not change `GET /api/snapshot`: that request still advances one observation tick, and with persistence enabled that tick is committed before the response is exposed.
