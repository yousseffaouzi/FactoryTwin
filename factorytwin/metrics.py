"""Honest synthetic production metrics and opt-in OEE assumptions."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class MetricsPlan:
    """Declares whether observation ticks are planned production time.

    OEE is intentionally undefined unless `planned_observation_ticks` is true
    and an explicit ideal cycle baseline is supplied.
    """

    planned_observation_ticks: bool = False
    ideal_cycle_ticks: int | None = None

    @property
    def enabled(self) -> bool:
        return self.planned_observation_ticks

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "planned_observation_ticks": self.planned_observation_ticks,
            "ideal_cycle_ticks": self.ideal_cycle_ticks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetricsPlan":
        if (not isinstance(data, dict) or
                set(data) != {"version", "planned_observation_ticks", "ideal_cycle_ticks"} or
                type(data["version"]) is not int or data["version"] != 1 or
                type(data["planned_observation_ticks"]) is not bool):
            raise ValueError("invalid metrics plan")
        planned = data["planned_observation_ticks"]
        ideal = data["ideal_cycle_ticks"]
        if planned:
            if type(ideal) is not int or not 1 <= ideal <= 10_000:
                raise ValueError("enabled metrics plan requires ideal_cycle_ticks 1..10000")
        elif ideal is not None:
            raise ValueError("disabled metrics plan must use null ideal_cycle_ticks")
        return cls(planned, ideal)

    @classmethod
    def load(cls, path: str | Path) -> "MetricsPlan":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"unable to load metrics plan: {exc}") from exc
        return cls.from_dict(data)


DEFAULT_METRICS_PLAN = MetricsPlan()


def _productive_observation_ticks(operations: list[dict]) -> tuple[int, int]:
    """Return (observation ticks, ticks where production was enabled).

    This derives only from the deterministic operation journal. A RUNNING step
    counts as production-enabled even when normal backpressure means no unit
    completes on that exact tick.
    """
    running = True
    fault_station: str | None = None
    observations = productive = 0
    for operation in operations:
        if operation.get("kind") == "control":
            action = operation.get("action")
            if action == "reset":
                running = True
                fault_station = None
            elif action == "pause":
                running = False
            elif action == "resume":
                running = True
            elif action == "fault":
                fault_station = operation.get("station")
            elif action == "clear_fault":
                fault_station = None
        elif operation.get("kind") == "step":
            observations += 1
            if running and fault_station is None:
                productive += 1
    return observations, productive


def production_metrics(line, plan: MetricsPlan | None = None) -> dict:
    """Compute deterministic session metrics without changing simulation state."""
    selected = plan if plan is not None else getattr(line, "metrics_plan", DEFAULT_METRICS_PLAN)
    if not isinstance(selected, MetricsPlan):
        raise ValueError("metrics_plan must be a validated MetricsPlan")
    observations, productive = _productive_observation_ticks(line.operations)
    terminal = line.completed + line.scrapped
    quality = (line.completed / terminal) if terminal else None

    planned_ticks = observations if selected.enabled else None
    availability = None
    performance = None
    oee = None
    warnings: list[str] = []
    if selected.enabled:
        if planned_ticks:
            availability = productive / planned_ticks
        if productive:
            performance = selected.ideal_cycle_ticks * terminal / productive
            if performance > 1.0:
                warnings.append(
                    "performance exceeds 1.0; verify the declared ideal cycle baseline")
        if availability is not None and performance is not None and quality is not None:
            oee = availability * performance * quality
    return {
        "scope": "synthetic_session",
        "observation_ticks": observations,
        "planned_ticks": planned_ticks,
        "production_enabled_ticks": productive,
        "good_units": line.completed,
        "scrapped_units": line.scrapped,
        "terminal_units": terminal,
        "in_process": sum(piece is not None for piece in line.conveyor),
        "quality": quality,
        "availability": availability,
        "performance": performance,
        "oee": oee,
        "ideal_cycle_ticks": selected.ideal_cycle_ticks,
        "plan": selected.to_dict(),
        "warnings": warnings,
        "definitions": {
            "availability": "production_enabled_ticks / planned_ticks",
            "performance": "ideal_cycle_ticks * terminal_units / production_enabled_ticks",
            "quality": "good_units / terminal_units",
            "oee": "availability * performance * quality",
        },
    }
