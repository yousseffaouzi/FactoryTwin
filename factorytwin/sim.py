"""Discrete simulated factory floor; no real industrial equipment."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

STATIONS = ("Feeder", "Conveyor", "Processing", "Packing")


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

    def log(self, event: str, **data) -> None:
        self.events.append({"tick": self.tick, "event": event, **data})
        self.events = self.events[-40:]

    def control(self, action: str, station: str | None = None) -> None:
        if action == "pause":
            self.running = False
            self.log("line_paused")
        elif action == "resume":
            self.running = True
            self.log("line_resumed")
        elif action == "fault":
            if station not in STATIONS:
                raise ValueError("unknown station")
            self.fault_station = station
            self.log("fault_injected", station=station)
        elif action == "clear_fault":
            self.fault_station = None
            self.log("fault_cleared")
        elif action == "reset":
            self.__dict__.update(ProductionLine().__dict__)
            self.log("simulation_reset")
        else:
            raise ValueError("unknown control action")

    def step(self) -> dict:
        self.tick += 1
        if self.running and self.fault_station is None:
            exiting = self.conveyor[-1]
            if exiting is not None:
                self.completed += 1
                self.log("workpiece_completed", workpiece_id=exiting["id"])
            self.conveyor = [None, *self.conveyor[:-1]]
            self.conveyor[0] = {"id": f"WP-{self.next_id:04d}"}
            self.next_id += 1
            self.log("workpiece_created", workpiece_id=self.conveyor[0]["id"])
        return self.snapshot()

    def snapshot(self) -> dict:
        state = "PAUSED" if not self.running else ("FAULT" if self.fault_station else "RUNNING")
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
            "state": state, "completed": self.completed, "scrapped": self.scrapped,
            "in_process": sum(x is not None for x in self.conveyor),
            "stations": stations, "events": list(self.events[-12:]),
        }
