"""FT-013 simultaneous station fault latches with legacy control compatibility."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json

from .blueprint import FactoryBlueprint
from .engine import MAX_REPLAY_OPERATIONS, LineState, TICK_DURATION_MS
from .genealogy import GenealogyProductionLine
from .quality import QualityScenario

MULTI_FAULT_TRACE_SCHEMA = "factorytwin.trace.v4"


@dataclass
class MultiFaultProductionLine(GenealogyProductionLine):
    """Adds explicit multi-fault controls without changing legacy `fault` semantics."""

    fault_stations: list[str] = field(default_factory=list)
    _multi_fault_used: bool = False

    def __post_init__(self) -> None:
        if self.fault_station is not None and not self.fault_stations:
            self.fault_stations = [self.fault_station]
        self._sync_fault_alias()
        super().__post_init__()

    def _sync_fault_alias(self) -> None:
        active = set(self.fault_stations)
        self.fault_stations = [name for name in self.blueprint.station_ids if name in active]
        self.fault_station = self.fault_stations[0] if self.fault_stations else None

    @property
    def state(self) -> LineState:
        if not self.running:
            return LineState.PAUSED
        return LineState.FAULT if self.fault_stations else LineState.RUNNING

    def validate(self) -> None:
        if not isinstance(self.fault_stations, list):
            raise ValueError("fault_stations must be a list")
        if len(self.fault_stations) != len(set(self.fault_stations)):
            raise ValueError("duplicate fault station")
        if any(name not in self.blueprint.station_ids for name in self.fault_stations):
            raise ValueError("invalid fault station")
        expected = [name for name in self.blueprint.station_ids if name in self.fault_stations]
        if self.fault_stations != expected:
            raise ValueError("fault_stations must use blueprint order")
        alias = self.fault_stations[0] if self.fault_stations else None
        if self.fault_station != alias:
            raise ValueError("legacy fault_station alias mismatch")
        super().validate()

    def _record_extended_control(self, action: str, station: str | None = None) -> None:
        operation = {"seq": len(self.operations) + 1, "kind": "control",
                     "tick": self.tick, "sim_time_ms": self.sim_time_ms, "action": action}
        if station is not None:
            operation["station"] = station
        self.operations.append(operation)

    def control(self, action: str, station: str | None = None) -> None:
        # Keep the old one-fault command behavior exactly. A second distinct
        # legacy `fault` is still rejected; simultaneous latches require fault_add.
        if action == "fault":
            self.validate()
            if station not in self.blueprint.station_ids:
                raise ValueError("unknown station")
            if self.fault_stations and station not in self.fault_stations:
                raise ValueError("fault already active; clear it before selecting another station")
            if not self.fault_stations:
                self.fault_stations = [station]
                self._sync_fault_alias()
                self.log("fault_injected", station=station)
            self._record("control", action="fault", station=station)
            self.validate()
            return
        if action == "clear_fault":
            self.validate()
            if self.fault_stations:
                self.fault_stations = []
                self._sync_fault_alias()
                self.log("fault_cleared")
            self._record("control", action="clear_fault")
            self.validate()
            return
        if action in ("fault_add", "clear_fault_station"):
            self.validate()
            if station not in self.blueprint.station_ids:
                raise ValueError("unknown station")
            self._multi_fault_used = True
            if action == "fault_add":
                if station not in self.fault_stations:
                    self.fault_stations.append(station)
                    self._sync_fault_alias()
                    self.log("fault_injected", station=station)
            elif station in self.fault_stations:
                self.fault_stations.remove(station)
                self._sync_fault_alias()
                self.log("fault_cleared", station=station)
            self._record_extended_control(action, station)
            self.validate()
            return

        # pause/resume/reset and invalid controls retain parent behavior. Reset
        # rebuilds type(self), therefore clears all fault latches and v4 usage.
        super().control(action, station)
        if action == "reset":
            self._sync_fault_alias()
        self.validate()

    def snapshot(self) -> dict:
        data = super().snapshot()
        active = set(self.fault_stations)
        for station in data["stations"]:
            if station["name"] in active:
                station["status"] = "FAULT"
            elif not self.running:
                station["status"] = "PAUSED"
            elif active:
                station["status"] = "BLOCKED"
            else:
                station["status"] = "RUNNING"
        data["fault_stations"] = list(self.fault_stations)
        return data

    def multi_fault_state_data(self) -> dict:
        data = self.quality_state_data()
        data["fault_stations"] = list(self.fault_stations)
        return data

    def export_trace(self) -> dict:
        if not self._multi_fault_used:
            return super().export_trace()
        return {"schema": MULTI_FAULT_TRACE_SCHEMA, "tick_duration_ms": TICK_DURATION_MS,
                "blueprint": self.blueprint.to_dict(),
                "quality_scenario": self.quality_scenario.to_dict(),
                "operations": deepcopy(self.operations),
                "final_state": self.multi_fault_state_data()}

    @classmethod
    def replay(cls, trace: dict):
        if not isinstance(trace, dict) or trace.get("schema") != MULTI_FAULT_TRACE_SCHEMA:
            return super().replay(trace)
        expected = {"schema", "tick_duration_ms", "blueprint", "quality_scenario",
                    "operations", "final_state"}
        if (set(trace) != expected or type(trace["tick_duration_ms"]) is not int or
                trace["tick_duration_ms"] != TICK_DURATION_MS):
            raise ValueError("invalid trace header")
        blueprint = FactoryBlueprint.from_dict(trace["blueprint"])
        quality = QualityScenario.from_dict(trace["quality_scenario"])
        quality.validate_for_blueprint(blueprint)
        operations = trace["operations"]
        if not isinstance(operations, list) or len(operations) > MAX_REPLAY_OPERATIONS:
            raise ValueError("invalid trace operation count")
        line = cls(blueprint=blueprint, quality_scenario=quality)
        for index, operation in enumerate(operations, 1):
            if not isinstance(operation, dict):
                raise ValueError(f"invalid trace record {index}")
            kind = operation.get("kind")
            if kind == "step":
                keys = {"seq", "kind", "tick", "sim_time_ms"}
            elif kind == "control":
                action = operation.get("action")
                keys = {"seq", "kind", "tick", "sim_time_ms", "action"}
                if action in ("fault", "fault_add", "clear_fault_station"):
                    keys.add("station")
            else:
                raise ValueError(f"invalid trace record {index}")
            if (set(operation) != keys or type(operation.get("seq")) is not int or
                    operation["seq"] != index):
                raise ValueError(f"invalid trace record {index}")
            try:
                line.step() if kind == "step" else line.control(operation["action"], operation.get("station"))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid trace transition {index}: {exc}") from exc
            if (type(operation["tick"]) is not int or type(operation["sim_time_ms"]) is not int or
                    line.operations[index - 1] != operation):
                raise ValueError(f"trace divergence at record {index}")
        if not line._multi_fault_used:
            raise ValueError("multi-fault trace contains no extended fault operation")
        final_state = line.multi_fault_state_data()
        if (not isinstance(trace["final_state"], dict) or final_state != trace["final_state"] or
                json.dumps(final_state, sort_keys=True) != json.dumps(trace["final_state"], sort_keys=True)):
            raise ValueError("trace final state mismatch")
        return line
