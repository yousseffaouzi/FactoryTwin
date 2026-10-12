"""Deterministic discrete-tick factory simulator (no physical equipment)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import re

STATIONS = ("Feeder", "Conveyor", "Processing", "Packing")
TICK_DURATION_MS = 1000  # Simulation-relative time; not elapsed wall-clock time.
TRACE_SCHEMA = "factorytwin.trace.v1"
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
    conveyor: list[dict | None] = field(default_factory=lambda: [None] * len(STATIONS))
    events: list[dict] = field(default_factory=list)
    event_sequence: int = 0
    operations: list[dict] = field(default_factory=list)

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
        if self.fault_station is not None and self.fault_station not in STATIONS:
            raise ValueError("invalid fault station")
        for name, minimum in (("tick", 0), ("completed", 0), ("scrapped", 0),
                              ("next_id", 1), ("event_sequence", 0)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"invalid {name}")
        if not isinstance(self.conveyor, list) or len(self.conveyor) != len(STATIONS):
            raise ValueError("invalid conveyor slots")
        ids = []
        for piece in self.conveyor:
            if piece is None:
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
            self.__dict__.update(ProductionLine().__dict__)
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
            if station not in STATIONS:
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
        """Advance one observation tick; process only when enabled and healthy."""
        self.validate()
        self.tick += 1
        if self.state == LineState.RUNNING:
            exiting = self.conveyor[-1]
            if exiting is not None:
                self.completed += 1
                self.log("workpiece_completed", workpiece_id=exiting["id"])
            self.conveyor = [None, *self.conveyor[:-1]]
            self.conveyor[0] = {"id": f"WP-{self.next_id:04d}"}
            self.next_id += 1
            self.log("workpiece_created", workpiece_id=self.conveyor[0]["id"])
        self._record("step")
        self.validate()
        return self.snapshot()

    def state_data(self) -> dict:
        """Deterministic state projection, excluding wall-clock capture time."""
        self.validate()
        return {
            "tick": self.tick, "sim_time_ms": self.sim_time_ms, "state": self.state.value,
            "running": self.running, "fault_station": self.fault_station,
            "completed": self.completed, "scrapped": self.scrapped, "next_id": self.next_id,
            "conveyor": deepcopy(self.conveyor), "event_sequence": self.event_sequence,
            "events": deepcopy(self.events),
        }

    def export_trace(self) -> dict:
        """Export a JSON-compatible, detached trace since the most recent reset.

        The entire accepted command/tick history is kept in memory until reset;
        the 40-item UI event buffer is *not* the replay source.
        """
        return {"schema": TRACE_SCHEMA, "tick_duration_ms": TICK_DURATION_MS,
                "operations": deepcopy(self.operations), "final_state": self.state_data()}

    @classmethod
    def replay(cls, trace: dict) -> ProductionLine:
        """Rebuild and verify state from an exported deterministic operation trace.

        Reject malformed, reordered, or inconsistent records; never replay external
        traces via a running HTTP server or real industrial equipment.
        """
        if (not isinstance(trace, dict) or set(trace) !=
                {"schema", "tick_duration_ms", "operations", "final_state"} or
                trace["schema"] != TRACE_SCHEMA or
                type(trace["tick_duration_ms"]) is not int or
                trace["tick_duration_ms"] != TICK_DURATION_MS):
            raise ValueError("invalid trace header")
        operations = trace["operations"]
        if not isinstance(operations, list) or len(operations) > MAX_REPLAY_OPERATIONS:
            raise ValueError("invalid trace operation count")
        line = cls()
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
                # JSON representation retains number-vs-boolean distinction.
                json.dumps(line.state_data(), sort_keys=True) !=
                json.dumps(trace["final_state"], sort_keys=True)):
            raise ValueError("trace final state mismatch")
        return line

    def snapshot(self) -> dict:
        self.validate()
        stations = [{
            "name": name,
            "status": "FAULT" if self.fault_station == name else
                      "PAUSED" if not self.running else
                      "BLOCKED" if self.fault_station else "RUNNING",
            "workpiece": self.conveyor[i]["id"] if self.conveyor[i] else None,
        } for i, name in enumerate(STATIONS)]
        return {
            "source": "synthetic", "tick": self.tick,
            "sim_time_ms": self.sim_time_ms,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "state": self.state.value, "completed": self.completed, "scrapped": self.scrapped,
            "in_process": sum(x is not None for x in self.conveyor),
            "stations": stations, "events": [dict(event) for event in self.events[-12:]],
        }
