"""Deterministic discrete-tick factory simulator (no physical equipment)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re

STATIONS = ("Feeder", "Conveyor", "Processing", "Packing")
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

    @property
    def state(self) -> LineState:
        """PAUSED takes precedence over FAULT; an active fault is still latched."""
        if not self.running:
            return LineState.PAUSED
        return LineState.FAULT if self.fault_station is not None else LineState.RUNNING

    def validate(self) -> None:
        """Reject malformed state and workpiece accounting before processing.

        A created workpiece is either in the pipeline, completed, or scrapped.
        Faults halt the entire line; workpiece movement is all-or-nothing.
        """
        if not isinstance(self.running, bool):
            raise ValueError("running must be a boolean")
        if self.fault_station is not None and self.fault_station not in STATIONS:
            raise ValueError("invalid fault station")
        for name, minimum in (("tick", 0), ("completed", 0), ("scrapped", 0), ("next_id", 1)):
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
        self.events.append({"tick": self.tick, "event": event, **data})
        self.events = self.events[-40:]

    def control(self, action: str, station: str | None = None) -> None:
        """Apply a validated, idempotent command without implicit fault recovery.

        Only reset erases the currently latched pause and station fault.
        Clearing a fault while paused does not resume production.
        """
        if action == "reset":
            self.__dict__.update(ProductionLine().__dict__)
            self.log("simulation_reset")
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
        self.validate()

    def step(self) -> dict:
        """Advance one observation tick; process only when the line is enabled and healthy."""
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
        self.validate()
        return self.snapshot()

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
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "state": self.state.value, "completed": self.completed, "scrapped": self.scrapped,
            "in_process": sum(x is not None for x in self.conveyor),
            "stations": stations, "events": [dict(event) for event in self.events[-12:]],
        }
