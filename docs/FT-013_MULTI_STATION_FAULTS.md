# FT-013 — Multiple station fault scenarios

FactoryTwin now supports multiple simultaneous **synthetic** station fault latches while preserving the legacy one-fault API contract.

## Compatibility model

The original `fault` control is unchanged: it injects one station fault and rejects a second distinct station until `clear_fault` is called. Existing traces, API clients and regression tests therefore keep their historical behavior.

FT-013 adds two explicit controls:

- `fault_add` with `station`: add that station to the active fault set; repeated adds are idempotent.
- `clear_fault_station` with `station`: clear only that station's latch; clearing an inactive valid station is idempotent.

The existing `clear_fault` remains a compatibility command and clears **all** active latches.

## Interlock semantics

Faults remain a whole-line production interlock. Any active station fault prevents processing, quality evaluation, transfers, completion and workpiece creation while observation ticks continue to advance. This deliberately preserves the FT-005 safety model rather than inventing local bypass routing.

Independent recovery refers to the latches: clearing one station does not clear another. If any latch remains, reported state stays `FAULT`. User pause still has display precedence; `resume` never clears fault latches.

Snapshots add `fault_stations` in validated blueprint order. The legacy `fault_station` engine field remains an alias of the first active station so old logic has a deterministic representative value. Each active station renders `FAULT`; non-faulted stations render `BLOCKED` while another latch is active.

## Replay

Sessions that never use the new controls continue exporting trace.v1/v2/v3 exactly as before. Once `fault_add` or `clear_fault_station` is used, export switches to `factorytwin.trace.v4`. V4 embeds the canonical blueprint and quality scenario plus `fault_stations` in the deterministic final state. V4 replay validates operation keys, station controls and final state before accepting the trace.

Reset clears all fault latches and starts a fresh session; subsequent export can return to the appropriate legacy trace schema because prior-session history is not retained across reset.

## Persistence and metrics

The server's persistent runtime promotes an open SQLite session to trace.v4 atomically with the first extended fault operation. V4 restart recovery uses the same deterministic replay validator. The underlying FT-009 database schema remains version 2 because the existing session `trace_schema` column already supports versioned trace envelopes.

OEE availability reconstruction tracks the full fault-latch set. A planned tick is production-enabled only when the line is running and **no** fault latch is active.

## Non-goals

This remains synthetic fault injection. FT-013 does not diagnose equipment, emulate electrical safety circuits, implement per-station bypass production, actuate machines, or validate physical recovery procedures. The loopback-only boundary is unchanged.
