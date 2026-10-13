"""Strict JSON blueprints for deterministic, single-route virtual factory lines."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")
MAX_STATIONS = 32
MAX_CYCLE_TICKS = 10_000


@dataclass(frozen=True)
class StationSpec:
    id: str
    cycle_ticks: int


@dataclass(frozen=True)
class FactoryBlueprint:
    """Canonical path through a directed single-route graph.

    Branching, merging, loops and parallel work are intentionally not supported
    until queue/routing semantics have been defined and tested.
    """

    stations: tuple[StationSpec, ...]

    @property
    def station_ids(self) -> tuple[str, ...]:
        return tuple(station.id for station in self.stations)

    def to_dict(self) -> dict:
        names = self.station_ids
        return {
            "version": 1,
            "stations": [{"id": station.id, "cycle_ticks": station.cycle_ticks}
                         for station in self.stations],
            "connections": [{"from": src, "to": dst}
                            for src, dst in zip(names, names[1:])],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FactoryBlueprint:
        if (not isinstance(data, dict) or set(data) !=
                {"version", "stations", "connections"} or
                type(data["version"]) is not int or data["version"] != 1):
            raise ValueError("invalid blueprint version or fields")
        raw_stations = data["stations"]
        raw_links = data["connections"]
        if (not isinstance(raw_stations, list) or
                not 1 <= len(raw_stations) <= MAX_STATIONS or
                not isinstance(raw_links, list) or
                len(raw_links) != len(raw_stations) - 1):
            raise ValueError("invalid station/connection count")

        lookup: dict[str, StationSpec] = {}
        for item in raw_stations:
            if not isinstance(item, dict) or set(item) != {"id", "cycle_ticks"}:
                raise ValueError("invalid station definition")
            name, cycle = item["id"], item["cycle_ticks"]
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("invalid station id")
            if type(cycle) is not int or not 1 <= cycle <= MAX_CYCLE_TICKS:
                raise ValueError("invalid cycle_ticks")
            if name in lookup:
                raise ValueError("duplicate station id")
            lookup[name] = StationSpec(name, cycle)

        successors: dict[str, str] = {}
        predecessors: dict[str, str] = {}
        for link in raw_links:
            if not isinstance(link, dict) or set(link) != {"from", "to"}:
                raise ValueError("invalid connection definition")
            src, dst = link["from"], link["to"]
            if (not isinstance(src, str) or not isinstance(dst, str) or
                    src not in lookup or dst not in lookup or src == dst):
                raise ValueError("invalid connection endpoint")
            if src in successors or dst in predecessors:
                raise ValueError("branching, merging or duplicate connection unsupported")
            successors[src] = dst
            predecessors[dst] = src

        starts = [name for name in lookup if name not in predecessors]
        ends = [name for name in lookup if name not in successors]
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError("blueprint must have exactly one entry and exit")
        ordered: list[StationSpec] = []
        seen: set[str] = set()
        current: str | None = starts[0]
        while current is not None:
            if current in seen:
                raise ValueError("cyclic blueprint")
            seen.add(current)
            ordered.append(lookup[current])
            current = successors.get(current)
        if len(seen) != len(lookup):
            raise ValueError("disconnected or cyclic blueprint")
        return cls(tuple(ordered))

    @classmethod
    def load(cls, path: str | Path) -> FactoryBlueprint:
        """Load a local JSON file; no network, remote URL, or hardware access."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"unable to load blueprint: {exc}") from exc
        return cls.from_dict(data)


DEFAULT_BLUEPRINT = FactoryBlueprint.from_dict({
    "version": 1,
    "stations": [{"id": name, "cycle_ticks": 1}
                 for name in ("Feeder", "Conveyor", "Processing", "Packing")],
    "connections": [{"from": a, "to": b} for a, b in
                    zip(("Feeder", "Conveyor", "Processing"),
                        ("Conveyor", "Processing", "Packing"))],
})
