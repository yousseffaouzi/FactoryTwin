# FT-010 — Synthetic production metrics and OEE

FactoryTwin reports metrics for a **software simulation**, not a measured physical production system. OEE is deliberately undefined unless the user explicitly declares a local reporting plan.

## Default behavior

Snapshots always expose terminal good/scrap counts, in-process count, observation ticks, production-enabled ticks and quality when its denominator exists. With no `--metrics-plan`, `planned_ticks`, availability, performance and OEE are `null`. This prevents the dashboard from treating HTTP polling time as a production schedule.

## Explicit OEE plan

A version-1 local JSON metrics plan can declare that every observed simulation tick in the current session is planned production time and provide an ideal output cycle baseline:

```json
{
  "version": 1,
  "planned_observation_ticks": true,
  "ideal_cycle_ticks": 2
}
```

Run with:

```bash
python -m factorytwin --metrics-plan config/oee_plan.json
```

The plan is reporting metadata only. It does not change routing, cycle times, quality, trace schemas, replay, persistence or control interlocks. If SQLite is enabled, the same or another reporting plan may be applied after restart because metrics are reconstructed from the deterministic operation journal.

## Definitions

For an enabled plan:

- **planned ticks** = all observation `step` ticks in the current simulation session, because the plan explicitly declares them planned;
- **production-enabled ticks** = planned ticks where the line was neither paused nor faulted at the step boundary. Backpressure does not turn a production-enabled tick into downtime;
- **availability** = `production_enabled_ticks / planned_ticks`;
- **performance** = `ideal_cycle_ticks * terminal_units / production_enabled_ticks`, where terminal units are good plus scrap workpieces and rework attempts do not create additional units;
- **quality** = `good_units / terminal_units`;
- **OEE** = availability × performance × quality.

A zero denominator produces JSON `null` rather than a fabricated zero percentage. Performance is not silently capped at 100%; a value above 1.0 produces a warning that the declared ideal-cycle baseline should be checked.

These formulas operate on synthetic logical ticks, not wall-clock seconds. `recorded_at_utc` remains capture metadata and is never used as a deterministic OEE denominator.

## Scope limitations

The current plan has no shift calendar, planned breaks, changeover classification, product-mix ideal rates, labor schedule or physical machine telemetry. Therefore this OEE is useful for controlled simulation scenarios only. It is not an industrial performance certificate and should not be compared directly with plant OEE unless the scheduling and ideal-rate assumptions are separately modeled and validated.
