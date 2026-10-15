# FactoryTwin reproducible demo

This walkthrough demonstrates **synthetic software behavior only**. It does not connect to a PLC, robot, SCADA system, production network, or physical machine.

## 1. Run the tests

From the repository root:

```bash
python -m unittest discover -s tests -v
```

Do not treat a previous CI run as evidence for a modified commit. Re-run the suite after changes.

## 2. Start the default local demo

```bash
python -m factorytwin
```

Open:

```text
http://127.0.0.1:8766/
```

The server is intentionally loopback-only.

## 3. Observe the snapshot contract

```bash
curl http://127.0.0.1:8766/api/snapshot
```

Each call advances one **observation tick**. While paused or faulted, observation time continues to advance, but productive station processing, transfers, creation and terminal production outcomes remain interlocked.

## 4. Exercise pause and fault behavior

Pause:

```bash
curl -X POST http://127.0.0.1:8766/api/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"pause"}'
```

Inject a station fault using a station name present in the active blueprint, then resume. A latched fault still blocks productive work; `resume` does not clear it. Clearing the fault does not implicitly undo a user pause.

Multi-station fault scenarios use the explicit additive/removal controls documented in `docs/FT-013_MULTI_STATION_FAULTS.md`; legacy one-fault commands remain compatible.

## 5. Run a configurable line

```bash
python -m factorytwin --blueprint config/assembly_line.json
```

The supplied example remains a strict linear route. Branching, merging and cyclic route graphs are rejected.

## 6. Demonstrate deterministic quality and genealogy

Use the local quality scenario example:

```text
config/quality_scenario.json
```

Quality decisions are predefined synthetic inputs. `GOOD` allows normal progression, `SCRAP` terminates the workpiece, and `REWORK` repeats the current station cycle. Rework does **not** send the item backward through the graph.

Read a generated workpiece record without advancing simulation time:

```bash
curl http://127.0.0.1:8766/api/workpieces/WP-0001
```

## 7. Persistence, metrics and streaming

Optional SQLite mode, production metrics/OEE inputs, and the SSE endpoint are documented in:

- `docs/FT-009_SQLITE_PERSISTENCE.md`
- `docs/FT-010_PRODUCTION_METRICS.md`
- `docs/FT-011_SSE_STREAMING.md`

The SSE stream is read-only transport. Snapshot polling remains a compatibility fallback and remains the observation-tick driver.

## 8. 2D dashboard

The browser renders the current station chain as an accessible 2D floor. It uses labels and text states in addition to visual styling, supports reduced-motion preferences, and requires no frontend build system or third-party CDN.

## 9. OPC-UA-style simulator boundary

`factorytwin/opcua_sim.py` provides an in-process, typed namespace/method mock for simulated integration tests. It deliberately opens no OPC UA network listener and does not connect to field equipment.

## Demo GIF

`docs/assets/factorytwin-demo.gif` is an **illustrative synthetic animation** of the project concepts: station flow, quality/rework, scrap, fault blocking and recovery. It is not a browser capture and not footage of a real factory. The actual executable demo is the localhost application described above.

## Reproduction record

For a release/demo checkpoint, record:

1. Git commit SHA and branch.
2. Python version.
3. Exact `unittest` result.
4. Blueprint/quality/OEE configuration used.
5. Whether SQLite mode was enabled and the database path.
6. Browser viewport if screenshots are captured.
7. A statement that all displayed plant data is synthetic.

This keeps screenshots, GIFs and blog material tied to a reproducible software state rather than implying physical validation.
