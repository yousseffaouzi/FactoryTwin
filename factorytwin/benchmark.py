"""Synthetic software benchmark reporting for FactoryTwin.

This module measures software execution and storage characteristics only. It is
not a real-time, industrial-control, hardware, or plant-performance benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import tempfile
import time

from .fault_persistence import FaultPersistentProductionLine
from .sim import ProductionLine

BENCHMARK_SCHEMA = "factorytwin.benchmark.v1"
BENCHMARK_NOTE = (
    "Synthetic software benchmark only; no real-time, hardware, plant, or "
    "industrial-performance claim."
)


def _json_bytes(value) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _rate(units: int, elapsed_ns: int) -> float:
    return round(units * 1_000_000_000 / max(elapsed_ns, 1), 2)


def _seconds(elapsed_ns: int) -> float:
    return round(elapsed_ns / 1_000_000_000, 6)


def _sqlite_storage_bytes(path: Path) -> int:
    candidates = (path, Path(f"{path}-wal"))
    return sum(candidate.stat().st_size for candidate in candidates if candidate.exists())


def run_benchmark(*, ticks: int = 2_000, sqlite_ticks: int = 100) -> dict:
    """Run a bounded synthetic benchmark and return a JSON-compatible report."""
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1:
        raise ValueError("ticks must be a positive integer")
    if isinstance(sqlite_ticks, bool) or not isinstance(sqlite_ticks, int) or sqlite_ticks < 1:
        raise ValueError("sqlite_ticks must be a positive integer")

    line = ProductionLine()
    started = time.perf_counter_ns()
    for _ in range(ticks):
        line.step()
    simulation_ns = time.perf_counter_ns() - started
    line.validate()
    line.audit_genealogy()
    trace = line.export_trace()
    snapshot = line.snapshot()

    started = time.perf_counter_ns()
    replayed = ProductionLine.replay(trace)
    replay_ns = time.perf_counter_ns() - started
    if replayed.export_trace() != trace:
        raise RuntimeError("benchmark replay diverged")

    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "benchmark.sqlite3"
        persistent = FaultPersistentProductionLine.open(database)
        started = time.perf_counter_ns()
        for _ in range(sqlite_ticks):
            persistent.step()
        sqlite_ns = time.perf_counter_ns() - started
        persistent.validate()
        sqlite_bytes = _sqlite_storage_bytes(database)
        sqlite_operations = len(persistent.operations)

    return {
        "schema": BENCHMARK_SCHEMA,
        "note": BENCHMARK_NOTE,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "in_memory": {
            "ticks": ticks,
            "elapsed_seconds": _seconds(simulation_ns),
            "ticks_per_second": _rate(ticks, simulation_ns),
            "completed": line.completed,
            "snapshot_bytes": _json_bytes(snapshot),
            "trace_bytes": _json_bytes(trace),
        },
        "replay": {
            "operations": len(trace["operations"]),
            "elapsed_seconds": _seconds(replay_ns),
            "operations_per_second": _rate(len(trace["operations"]), replay_ns),
        },
        "sqlite": {
            "ticks": sqlite_ticks,
            "operations": sqlite_operations,
            "elapsed_seconds": _seconds(sqlite_ns),
            "ticks_per_second": _rate(sqlite_ticks, sqlite_ns),
            "storage_bytes": sqlite_bytes,
            "bytes_per_operation": round(sqlite_bytes / max(sqlite_operations, 1), 2),
        },
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Report bounded synthetic FactoryTwin software benchmark metrics"
    )
    parser.add_argument("--ticks", type=_positive_int, default=2_000)
    parser.add_argument("--sqlite-ticks", type=_positive_int, default=100)
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)
    report = run_benchmark(ticks=args.ticks, sqlite_ticks=args.sqlite_ticks)
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
