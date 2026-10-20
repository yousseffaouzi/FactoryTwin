"""FT-008 genealogy and deterministic synthetic quality routing."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint
from .engine import (
    CUSTOM_TRACE_SCHEMA,
    MAX_REPLAY_OPERATIONS,
    TICK_DURATION_MS,
    TRACE_SCHEMA,
    LineState,
    ProductionLine as LegacyProductionLine,
)
from .quality import DEFAULT_QUALITY_SCENARIO, QUALITY_OUTCOMES, QualityScenario

QUALITY_TRACE_SCHEMA = "factorytwin.trace.v3"


@dataclass
class StationVisit:
    station: str
    attempt: int
    entered_tick: int
    entered_sim_time_ms: int
    processing_completed_tick: int | None = None
    processing_completed_sim_time_ms: int | None = None
    outcome: str | None = None
    outcome_source: str | None = None
    exited_tick: int | None = None
    exited_sim_time_ms: int | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class WorkpieceRecord:
    id: str
    created_tick: int
    created_sim_time_ms: int
    status: str = "IN_PROCESS"
    visits: list[StationVisit] = field(default_factory=list)
    rework_count: int = 0
    terminal_tick: int | None = None
    terminal_sim_time_ms: int | None = None

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["visits"] = [visit.to_dict() for visit in self.visits]
        return data


@dataclass
class GenealogyProductionLine(LegacyProductionLine):
    """Production line with immutable workpiece IDs and station-attempt history."""

    quality_scenario: QualityScenario = field(default_factory=lambda: DEFAULT_QUALITY_SCENARIO)
    genealogy: dict[str, WorkpieceRecord] = field(default_factory=dict)
    rework_cycles: int = 0
    _quality_lookup: dict[tuple[str, str, int], str] = field(default_factory=dict, init=False,
                                                                      repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.quality_scenario, QualityScenario):
            raise ValueError("quality_scenario must be a validated QualityScenario")
        if QualityScenario.from_dict(self.quality_scenario.to_dict()) != self.quality_scenario:
            raise ValueError("invalid quality scenario")
        self.quality_scenario.validate_for_blueprint(self.blueprint)
        self._quality_lookup = self.quality_scenario.lookup()
        super().__post_init__()

    @classmethod
    def from_blueprint(cls, data: dict, quality_scenario: dict | None = None):
        quality = (DEFAULT_QUALITY_SCENARIO if quality_scenario is None
                   else QualityScenario.from_dict(quality_scenario))
        return cls(blueprint=FactoryBlueprint.from_dict(data), quality_scenario=quality)

    def validate(self) -> None:
        super().validate()
        if type(self.rework_cycles) is not int or self.rework_cycles < 0:
            raise ValueError("invalid rework_cycles")
        if not isinstance(self.genealogy, dict) or len(self.genealogy) != self.next_id - 1:
            raise ValueError("invalid genealogy accounting")
        for index, piece in enumerate(self.conveyor):
            if piece is None:
                continue
            record = self.genealogy.get(piece["id"])
            if (not isinstance(record, WorkpieceRecord) or record.status != "IN_PROCESS" or
                    not record.visits or
                    record.visits[-1].station != self.blueprint.stations[index].id or
                    record.visits[-1].exited_tick is not None):
                raise ValueError("active workpiece genealogy mismatch")

    def audit_genealogy(self) -> None:
        """Deep historical audit used by v3 export/replay and tests."""
        self.validate()
        station_index = {name: i for i, name in enumerate(self.blueprint.station_ids)}
        active = {piece["id"] for piece in self.conveyor if piece is not None}
        completed = scrapped = reworks = 0
        for number in range(1, self.next_id):
            identifier = f"WP-{number:04d}"
            record = self.genealogy.get(identifier)
            if (not isinstance(record, WorkpieceRecord) or record.id != identifier or
                    type(record.created_tick) is not int or record.created_tick < 0 or
                    record.created_sim_time_ms != record.created_tick * TICK_DURATION_MS or
                    type(record.rework_count) is not int or record.rework_count < 0 or
                    not record.visits):
                raise ValueError("invalid genealogy record")
            previous = None
            piece_reworks = 0
            for visit in record.visits:
                if (not isinstance(visit, StationVisit) or visit.station not in station_index or
                        type(visit.attempt) is not int or visit.attempt < 1 or
                        type(visit.entered_tick) is not int or visit.entered_tick < 0 or
                        visit.entered_sim_time_ms != visit.entered_tick * TICK_DURATION_MS):
                    raise ValueError("invalid station visit")
                if previous is None:
                    if station_index[visit.station] != 0 or visit.attempt != 1:
                        raise ValueError("invalid first genealogy visit")
                elif visit.station == previous.station:
                    if previous.outcome != "REWORK" or visit.attempt != previous.attempt + 1:
                        raise ValueError("invalid same-station rework history")
                elif (previous.outcome != "GOOD" or visit.attempt != 1 or
                      station_index[visit.station] != station_index[previous.station] + 1):
                    raise ValueError("invalid genealogy route order")
                if visit.processing_completed_tick is None:
                    if any(value is not None for value in
                           (visit.processing_completed_sim_time_ms, visit.outcome,
                            visit.outcome_source, visit.exited_tick, visit.exited_sim_time_ms)):
                        raise ValueError("partial processing history")
                else:
                    if (type(visit.processing_completed_tick) is not int or
                            visit.processing_completed_tick < visit.entered_tick or
                            visit.processing_completed_sim_time_ms !=
                            visit.processing_completed_tick * TICK_DURATION_MS or
                            visit.outcome not in QUALITY_OUTCOMES or
                            visit.outcome_source not in ("default", "scenario")):
                        raise ValueError("invalid processing outcome history")
                    if visit.outcome == "REWORK":
                        piece_reworks += 1
                    if visit.exited_tick is not None and (
                            type(visit.exited_tick) is not int or
                            visit.exited_tick < visit.processing_completed_tick or
                            visit.exited_sim_time_ms != visit.exited_tick * TICK_DURATION_MS):
                        raise ValueError("invalid station exit history")
                if previous is not None and previous.exited_tick is None:
                    raise ValueError("non-final genealogy visit has no exit")
                previous = visit
            if record.rework_count != piece_reworks:
                raise ValueError("workpiece rework count mismatch")
            reworks += piece_reworks
            last = record.visits[-1]
            if record.status == "IN_PROCESS":
                if (identifier not in active or last.exited_tick is not None or
                        record.terminal_tick is not None or record.terminal_sim_time_ms is not None):
                    raise ValueError("invalid active genealogy state")
            elif record.status == "COMPLETED":
                completed += 1
                if (identifier in active or last.outcome != "GOOD" or
                        station_index[last.station] != len(station_index) - 1 or
                        last.exited_tick is None or record.terminal_tick != last.exited_tick or
                        record.terminal_sim_time_ms != last.exited_sim_time_ms):
                    raise ValueError("invalid completed genealogy state")
            elif record.status == "SCRAPPED":
                scrapped += 1
                if (identifier in active or last.outcome != "SCRAP" or last.exited_tick is None or
                        record.terminal_tick != last.exited_tick or
                        record.terminal_sim_time_ms != last.exited_sim_time_ms):
                    raise ValueError("invalid scrapped genealogy state")
            else:
                raise ValueError("invalid genealogy status")
        if completed != self.completed or scrapped != self.scrapped or reworks != self.rework_cycles:
            raise ValueError("genealogy aggregate mismatch")

    def control(self, action: str, station: str | None = None) -> None:
        if action != "reset":
            return super().control(action, station)
        self.__dict__.update(type(self)(blueprint=self.blueprint,
                                       quality_scenario=self.quality_scenario).__dict__)
        self.log("simulation_reset")
        self._record("control", action="reset")
        self.validate()

    def _start_visit(self, record: WorkpieceRecord, station_index: int, attempt: int = 1) -> None:
        record.visits.append(StationVisit(self.blueprint.stations[station_index].id, attempt,
                                          self.tick, self.sim_time_ms))

    def _finish_processing(self, index: int, record: WorkpieceRecord) -> str:
        visit = record.visits[-1]
        key = (record.id, visit.station, visit.attempt)
        outcome = self._quality_lookup.get(key, "GOOD")
        visit.processing_completed_tick = self.tick
        visit.processing_completed_sim_time_ms = self.sim_time_ms
        visit.outcome = outcome
        visit.outcome_source = "scenario" if key in self._quality_lookup else "default"
        if key in self._quality_lookup:
            self.log("quality_outcome", workpiece_id=record.id, station=visit.station,
                     attempt=visit.attempt, outcome=outcome, source="synthetic_scenario")
        if outcome == "SCRAP":
            visit.exited_tick = record.terminal_tick = self.tick
            visit.exited_sim_time_ms = record.terminal_sim_time_ms = self.sim_time_ms
            record.status = "SCRAPPED"
            self.scrapped += 1
            self.conveyor[index] = None
            self.remaining_ticks[index] = 0
        elif outcome == "REWORK":
            visit.exited_tick = self.tick
            visit.exited_sim_time_ms = self.sim_time_ms
            record.rework_count += 1
            self.rework_cycles += 1
            self._start_visit(record, index, visit.attempt + 1)
            self.remaining_ticks[index] = self.blueprint.stations[index].cycle_ticks
        return outcome

    def step(self) -> dict:
        """Advance a tick; REWORK repeats only the current station, never a graph loop."""
        self.validate()
        self.tick += 1
        if self.state == LineState.RUNNING:
            for index in range(len(self.conveyor) - 1, -1, -1):
                piece = self.conveyor[index]
                if piece is None:
                    continue
                record = self.genealogy[piece["id"]]
                visit = record.visits[-1]
                if visit.processing_completed_tick is None:
                    if self.remaining_ticks[index]:
                        self.remaining_ticks[index] -= 1
                    if self.remaining_ticks[index]:
                        continue
                    if self._finish_processing(index, record) in ("SCRAP", "REWORK"):
                        continue
                if index == len(self.conveyor) - 1:
                    visit.exited_tick = record.terminal_tick = self.tick
                    visit.exited_sim_time_ms = record.terminal_sim_time_ms = self.sim_time_ms
                    record.status = "COMPLETED"
                    self.completed += 1
                    self.log("workpiece_completed", workpiece_id=record.id)
                elif self.conveyor[index + 1] is None:
                    visit.exited_tick = self.tick
                    visit.exited_sim_time_ms = self.sim_time_ms
                    self.conveyor[index + 1] = piece
                    self.remaining_ticks[index + 1] = self.blueprint.stations[index + 1].cycle_ticks
                    self._start_visit(record, index + 1)
                else:
                    continue
                self.conveyor[index] = None
                self.remaining_ticks[index] = 0
            if self.conveyor[0] is None:
                identifier = f"WP-{self.next_id:04d}"
                self.conveyor[0] = {"id": identifier}
                self.remaining_ticks[0] = self.blueprint.stations[0].cycle_ticks
                record = WorkpieceRecord(identifier, self.tick, self.sim_time_ms)
                self.genealogy[identifier] = record
                self._start_visit(record, 0)
                self.next_id += 1
                self.log("workpiece_created", workpiece_id=identifier)
        self._record("step")
        self.validate()
        return self.snapshot()

    def quality_state_data(self) -> dict:
        self.audit_genealogy()
        data = self.state_data()
        data["remaining_ticks"] = list(self.remaining_ticks)
        data["rework_cycles"] = self.rework_cycles
        data["genealogy"] = [self.genealogy[f"WP-{number:04d}"].to_dict()
                             for number in range(1, self.next_id)]
        return data

    def export_trace(self) -> dict:
        if not self.quality_scenario.enabled:
            return super().export_trace()
        return {
            "schema": QUALITY_TRACE_SCHEMA,
            "tick_duration_ms": TICK_DURATION_MS,
            "blueprint": self.blueprint.to_dict(),
            "quality_scenario": self.quality_scenario.to_dict(),
            "operations": deepcopy(self.operations),
            "final_state": self.quality_state_data(),
        }

    @classmethod
    def replay(cls, trace: dict):
        if not isinstance(trace, dict):
            raise ValueError("invalid trace header")
        schema = trace.get("schema")
        expected = {"schema", "tick_duration_ms", "operations", "final_state"}
        if schema == CUSTOM_TRACE_SCHEMA:
            expected.add("blueprint")
        elif schema == QUALITY_TRACE_SCHEMA:
            expected.update({"blueprint", "quality_scenario"})
        if (schema not in (TRACE_SCHEMA, CUSTOM_TRACE_SCHEMA, QUALITY_TRACE_SCHEMA) or
                set(trace) != expected or type(trace["tick_duration_ms"]) is not int or
                trace["tick_duration_ms"] != TICK_DURATION_MS):
            raise ValueError("invalid trace header")
        blueprint = (FactoryBlueprint.from_dict(trace["blueprint"])
                     if schema in (CUSTOM_TRACE_SCHEMA, QUALITY_TRACE_SCHEMA) else DEFAULT_BLUEPRINT)
        quality = (QualityScenario.from_dict(trace["quality_scenario"])
                   if schema == QUALITY_TRACE_SCHEMA else DEFAULT_QUALITY_SCENARIO)
        if schema == QUALITY_TRACE_SCHEMA and not quality.enabled:
            raise ValueError("quality trace requires at least one quality decision")
        quality.validate_for_blueprint(blueprint)
        operations = trace["operations"]
        if not isinstance(operations, list) or len(operations) > MAX_REPLAY_OPERATIONS:
            raise ValueError("invalid trace operation count")
        line = cls(blueprint=blueprint, quality_scenario=quality)
        for index, operation in enumerate(operations, 1):
            if not isinstance(operation, dict):
                raise ValueError(f"invalid trace record {index}")
            kind = operation.get("kind")
            keys = ({"seq", "kind", "tick", "sim_time_ms"} if kind == "step" else
                    {"seq", "kind", "tick", "sim_time_ms", "action"})
            if kind == "control" and operation.get("action") == "fault":
                keys.add("station")
            if kind not in ("step", "control") or set(operation) != keys:
                raise ValueError(f"invalid trace record {index}")
            if type(operation["seq"]) is not int or operation["seq"] != index:
                raise ValueError(f"invalid trace sequence {index}")
            try:
                line.step() if kind == "step" else line.control(operation["action"],
                                                                 operation.get("station"))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid trace transition {index}: {exc}") from exc
            if (type(operation["tick"]) is not int or type(operation["sim_time_ms"]) is not int or
                    line.operations[index - 1] != operation):
                raise ValueError(f"trace divergence at record {index}")
        final_state = line.quality_state_data() if schema == QUALITY_TRACE_SCHEMA else line.state_data()
        if (not isinstance(trace["final_state"], dict) or final_state != trace["final_state"] or
                json.dumps(final_state, sort_keys=True) != json.dumps(trace["final_state"], sort_keys=True)):
            raise ValueError("trace final state mismatch")
        return line

    def workpiece_genealogy(self, workpiece_id: str) -> dict:
        self.validate()
        record = self.genealogy.get(workpiece_id) if isinstance(workpiece_id, str) else None
        if record is None:
            raise ValueError("unknown workpiece")
        return deepcopy(record.to_dict())

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["rework_cycles"] = self.rework_cycles
        data["quality"] = {
            "mode": "deterministic_scenario" if self.quality_scenario.enabled else "default_good",
            "good_units": self.completed,
            "scrapped_units": self.scrapped,
            "rework_cycles": self.rework_cycles,
        }
        start = max(1, self.next_id - 8)
        data["recent_workpieces"] = []
        for number in range(start, self.next_id):
            record = self.genealogy[f"WP-{number:04d}"]
            visit = record.visits[-1]
            data["recent_workpieces"].append({
                "id": record.id, "status": record.status, "station": visit.station,
                "attempt": visit.attempt, "outcome": visit.outcome,
                "rework_count": record.rework_count,
            })
        return data
