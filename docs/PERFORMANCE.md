# Synthetic performance and resource reporting

FactoryTwin includes a bounded benchmark reporter for software-development visibility. The numbers are environment-dependent and must not be interpreted as industrial throughput, real-time guarantees, equipment capacity, hardware qualification, or plant-performance evidence.

## Run it

```bash
python -m factorytwin.benchmark --ticks 2000 --sqlite-ticks 100 --json
```

The report records the Python/runtime environment and four software-oriented measurements:

- in-memory simulation ticks per second;
- deterministic trace replay operations per second;
- serialized snapshot and trace sizes;
- SQLite synthetic write rate and resulting database/WAL storage bytes.

GitHub Actions runs this reporter on the Python 3.12 matrix job so each validated commit has a reference result in its CI log. The workflow deliberately has **no throughput or latency threshold**: hosted-runner contention, filesystem behavior and Python patch versions can move these numbers without indicating a correctness regression.

Correctness and long-run recovery remain separate gates in the normal test suite. See `docs/VALIDATION.md` for the bounded soak scenarios.

## Interpretation boundary

Use these measurements to spot large software regressions or estimate local development costs. Do not convert simulation ticks per second into production units per hour, PLC scan guarantees, control-loop deadlines, network capacity, OEE, or equipment availability. Those claims require validated physical-system measurements and are outside the current software-only scope.
