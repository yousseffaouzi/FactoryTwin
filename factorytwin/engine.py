"""Deterministic discrete-tick factory simulator (no physical equipment)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import re

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint

STATIONS = DEFAULT_BLUEPRINT.station_ids  # Backwards-compatible demo station names.
TICK_DURATION_MS = 1000  # Simulation-relative time; not elapsed wall-clock time.
TRACE_SCHEMA = "factorytwin.trace.v1"  # Unchanged for existing four-station traces.
CUSTOM_TRACE_SCHEMA = "factorytwin.trace.v2"
MAX_REPLAY_OPERATIONS = 1_000_000
_WORKPIECE_ID = re.compile(r"WP-(\d{4,})\Z")


class LineState(str, Enum):
    """Observable line states; pauses and station faults remain separate latches."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAULT = "FAULT"


@dataclass
class ProductionLine:
    tick: int = 0
    running: bool = True
    fault_station: str | None = None
    completed: int = 0
    scrapped: int = 0
    next_id: int = 1
    conveyor: list[dict | None] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    event_sequence: int = 0
    operations: list[dict] = field(default_factory=list)
    blueprint: FactoryBlueprint = field(default_factory=lambda: DEFAULT_BLUEPRINT)
    remaining_ticks: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.blueprint, FactoryBlueprint):
            raise ValueError("blueprint must be a validated FactoryBlueprint")
        # Reject a manually constructed blueprint with invalid graph semantics.
        if FactoryBlueprint.from_dict(self.blueprint.to_dict()) != self.blueprint:
            raise ValueError("invalid blueprint station order")
        if not self.conveyor:
            self.conveyor = [None] * len(self.blueprint.stations)
        if not self.remaining_ticks:
            self.remaining_ticks = [0] * len(self.blueprint.stations)
        self.validate()

    @classmethod
    def from_blueprint(cls, data: dict) -> ProductionLine:
        """Build a virtual line from a strictly validated JSON-compatible blueprint."""
        return cls(blueprint=FactoryBlueprint.from_dict(data))

    @property
    def state(self) -> LineState:
        """PAUSED takes precedence over FAULT; an active fault is still latched."""
        if not self.running:
            return LineState.PAUSED
        return LineState.FAULT if self.fault_station is not None else LineState.RUNNING

    @property
    def sim_time_ms(self) -> int:
        """Deterministic virtual elapsed time, not a UTC capture timestamp."""
        return self.tick * TICK_DURATION_MS

    def validate(self) -> None:
        """Reject malformed state and workpiece accounting before processing."""
        if not isinstance(self.running, bool):
            raise ValueError("running must be a boolean")
        if self.fault_station is not None and self.fault_station not in self.blueprint.station_ids:
            raise ValueError("invalid fault station")
        for name, minimum in (("tick", 0), ("completed", 0), ("scrapped", 0),
                              ("next_id", 1), ("event_sequence", 0)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"invalid {name}")
        if not isinstance(self.conveyor, list) or len(self.conveyor) != len(self.blueprint.stations):
            raise ValueError("invalid conveyor slots")
        if (not isinstance(self.remaining_ticks, list) or
                len(self.remaining_ticks) != len(self.blueprint.stations)):
            raise ValueError("invalid remaining_ticks")
        ids = []
        for i, piece in enumerate(self.conveyor):
            remaining = self.remaining_ticks[i]
            if type(remaining) is not int or not 0 <= remaining <= self.blueprint.stations[i].cycle_ticks:
                raise ValueError("invalid remaining_ticks")
            if piece is None:
                if remaining:
                    raise ValueError("empty station cannot be processing")
                continue
            if not isinstance(piece, dict) or not isinstance(piece.get("id"), str):
                raise ValueError("invalid workpiece")
            identifier = piece["id"]
            match = _WORKPIECE_ID.fullmatch(identifier)
            if match is None or not 1 <= int(match.group(1)) < self.next_id:
                raise ValueError("invalid workpiece ID")
            ids.append(identifier)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate workpiece ID")
        if self.next_id - 1 != self.completed + self.scrapped + len(ids):
            raise ValueError("workpiece accounting invariant violated")

    def log(self, event: str, **data) -> None:
        self.event_sequence += 1
        self.events.append({"tick": self.tick, "event": event, "seq": self.event_sequence,
                            "sim_time_ms": self.sim_time_ms, **data})
        self.events = self.events[-40:]

    def _record(self, kind: str, action: str | None = None, station: str | None = None) -> None:
        operation = {"seq": len(self.operations) + 1, "kind": kind,
                     "tick": self.tick, "sim_time_ms": self.sim_time_ms}
        if kind == "control":
            operation["action"] = action
            if action == "fault":
                operation["station"] = station
        self.operations.append(operation)

    def control(self, action: str, station: str | None = None) -> None:
        """Apply a validated, idempotent command without implicit fault recovery."""
        if action == "reset":
            # Reset all runtime state, but keep the active station configuration.
            self.__dict__.update(ProductionLine(blueprint=self.blueprint).__dict__)
            self.log("simulation_reset")
            self._record("control", action="reset")
            self.validate()
            return

        self.validate()
        if action == "pause":
            if self.running:
                self.running = False
                self.log("line_paused")
        elif action == "resume":
            if not self.running:
                self.running = True
                self.log("line_resumed")
        elif action == "fault":
            if station not in self.blueprint.station_ids:
                raise ValueError("unknown station")
            if self.fault_station is not None and self.fault_station != station:
                raise ValueError("fault already active; clear it before selecting another station")
            if self.fault_station is None:
                self.fault_station = station
                self.log("fault_injected", station=station)
        elif action == "clear_fault":
            if self.fault_station is not None:
                self.fault_station = None
                self.log("fault_cleared")
        else:
            raise ValueError("unknown control action")
        self._record("control", action=action, station=station)
        self.validate()

    def step(self) -> dict:
        """Advance one observation tick with single-slot, downstream-first transfers.

        Processing requires cycle_ticks *productive* ticks. A completed piece
        remains at its station if the next station is occupied. Each piece can
        move at most once per step; downstream moves can free space upstream.
        Pauses and faults stop work, transfers and injection, not clock ticks.
        """
        self.validate()
        self.tick += 1
        if self.state == LineState.RUNNING:
            for i in range(len(self.conveyor) - 1, -1, -1):
                piece = self.conveyor[i]
                if piece is None:
                    continue
                if self.remaining_ticks[i]:
                    self.remaining_ticks[i] -= 1
                if self.remaining_ticks[i]:
                    continue
                if i == len(self.conveyor) - 1:
                    self.completed += 1
                    self.log("workpiece_completed", workpiece_id=piece["id"])
                elif self.conveyor[i + 1] is None:
                    self.conveyor[i + 1] = piece
                    self.remaining_ticks[i + 1] = self.blueprint.stations[i + 1].cycle_ticks
                else:
                    continue  # Completed but blocked; no duplicate processing.
                self.conveyor[i] = None
                self.remaining_ticks[i] = 0
            if self.conveyor[0] is None:
                self.conveyor[0] = {"id": f"WP-{self.next_id:04d}"}
                self.remaining_ticks[0] = self.blueprint.stations[0].cycle_ticks
                self.next_id += 1
                self.log("workpiece_created", workpiece_id=self.conveyor[0]["id"])
        self._record("step")
        self.validate()
        return self.snapshot()

    def state_data(self) -> dict:
        """Deterministic state projection, excluding wall-clock capture time."""
        self.validate()
        data = {
            "tick": self.tick, "sim_time_ms": self.sim_time_ms, "state": self.state.value,
            "running": self.running, "fault_station": self.fault_station,
            "completed": self.completed, "scrapped": self.scrapped, "next_id": self.next_id,
            "conveyor": deepcopy(self.conveyor), "event_sequence": self.event_sequence,
            "events": deepcopy(self.events),
        }
        if self.blueprint != DEFAULT_BLUEPRINT:
            data["blueprint"] = self.blueprint.to_dict()
            data["remaining_ticks"] = list(self.remaining_ticks)
        return data

    def export_trace(self) -> dict:
        """Export replayable operations; UI event truncation does not affect replay."""
        trace = {"schema": TRACE_SCHEMA, "tick_duration_ms": TICK_DURATION_MS,
                 "operations": deepcopy(self.operations), "final_state": self.state_data()}
        if self.blueprint != DEFAULT_BLUEPRINT:
            trace["schema"] = CUSTOM_TRACE_SCHEMA
            trace["blueprint"] = self.blueprint.to_dict()
        return trace

    @classmethod
    def replay(cls, trace: dict) -> ProductionLine:
        """Reconstruct a trace in memory; reject invalid records or divergence."""
        if not isinstance(trace, dict):
            raise ValueError("invalid trace header")
        schema = trace.get("schema")
        expected = {"schema", "tick_duration_ms", "operations", "final_state"}
        if schema == CUSTOM_TRACE_SCHEMA:
            expected.add("blueprint")
        if (schema not in (TRACE_SCHEMA, CUSTOM_TRACE_SCHEMA) or set(trace) != expected or
                type(trace["tick_duration_ms"]) is not int or
                trace["tick_duration_ms"] != TICK_DURATION_MS):
            raise ValueError("invalid trace header")
        blueprint = (FactoryBlueprint.from_dict(trace["blueprint"])
                     if schema == CUSTOM_TRACE_SCHEMA else DEFAULT_BLUEPRINT)
        operations = trace["operations"]
        if not isinstance(operations, list) or len(operations) > MAX_REPLAY_OPERATIONS:
            raise ValueError("invalid trace operation count")
        line = cls(blueprint=blueprint)
        for index, operation in enumerate(operations, 1):
            if not isinstance(operation, dict):
                raise ValueError(f"invalid trace record {index}")
            kind = operation.get("kind")
            expected_keys = ({"seq", "kind", "tick", "sim_time_ms"} if kind == "step" else
                             {"seq", "kind", "tick", "sim_time_ms", "action"})
            if kind == "control" and operation.get("action") == "fault":
                expected_keys.add("station")
            if kind not in ("step", "control") or set(operation) != expected_keys:
                raise ValueError(f"invalid trace record {index}")
            if type(operation["seq"]) is not int or operation["seq"] != index:
                raise ValueError(f"invalid trace sequence {index}")
            try:
                if kind == "step":
                    line.step()
                else:
                    line.control(operation["action"], operation.get("station"))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid trace transition {index}: {exc}") from exc
            if (type(operation["tick"]) is not int or
                    type(operation["sim_time_ms"]) is not int or
                    index > len(line.operations) or line.operations[index - 1] != operation):
                raise ValueError(f"trace divergence at record {index}")
        if (not isinstance(trace["final_state"], dict) or
                line.state_data() != trace["final_state"] or
                json.dumps(line.state_data(), sort_keys=True) !=
                json.dumps(trace["final_state"], sort_keys=True)):
            raise ValueError("trace final state mismatch")
        return line

    def snapshot(self) -> dict:
        self.validate()
        stations = [{
            "name": station.id,
            "status": "FAULT" if self.fault_station == station.id else
                      "PAUSED" if not self.running else
                      "BLOCKED" if self.fault_station else "RUNNING",
            "workpiece": self.conveyor[i]["id"] if self.conveyor[i] else None,
            "cycle_ticks": station.cycle_ticks,
            "remaining_ticks": self.remaining_ticks[i],
        } for i, station in enumerate(self.blueprint.stations)]
        return {
            "source": "synthetic", "tick": self.tick,
            "sim_time_ms": self.sim_time_ms,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "state": self.state.value, "completed": self.completed, "scrapped": self.scrapped,
            "in_process": sum(x is not None for x in self.conveyor),
            "stations": stations, "events": [dict(event) for event in self.events[-12:]],
        }
