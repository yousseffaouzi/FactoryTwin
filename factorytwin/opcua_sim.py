"""In-process OPC UA-style namespace simulation for FactoryTwin.

This module intentionally does NOT implement the OPC UA wire protocol. It is a
local mock adapter for exercising namespace/node/method mappings against the
software simulator before any real protocol library or network endpoint exists.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any

NAMESPACE_INDEX = 2
ROOT = "FactoryTwin"
MAX_BROWSE_NODES = 512


@dataclass(frozen=True)
class SimulatedOpcUaNode:
    node_id: str
    browse_name: str
    data_type: str
    node_class: str = "Variable"
    writable: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "browse_name": self.browse_name,
            "data_type": self.data_type,
            "node_class": self.node_class,
            "writable": self.writable,
        }


def node_id(path: str) -> str:
    return f"ns={NAMESPACE_INDEX};s={ROOT}.{path}"


class SimulatedOpcUaAdapter:
    """Typed, read-only namespace façade plus explicit simulator methods.

    `read()` and `browse()` are observation-only and never call `step()`.
    `call_method()` delegates only to FactoryTwin's existing validated controls.
    """

    METHOD_ACTIONS = {
        node_id("Methods.Pause"): ("pause", False),
        node_id("Methods.Resume"): ("resume", False),
        node_id("Methods.Fault"): ("fault", True),
        node_id("Methods.AddFault"): ("fault_add", True),
        node_id("Methods.ClearFault"): ("clear_fault", False),
        node_id("Methods.ClearFaultStation"): ("clear_fault_station", True),
        node_id("Methods.Reset"): ("reset", False),
    }

    def __init__(self, line, lock: Lock | None = None):
        self.line = line
        self.lock = lock or Lock()
        self._nodes = self._build_nodes()

    def _build_nodes(self) -> dict[str, SimulatedOpcUaNode]:
        nodes = {
            node_id("Line.State"): SimulatedOpcUaNode(node_id("Line.State"), "State", "String"),
            node_id("Line.Tick"): SimulatedOpcUaNode(node_id("Line.Tick"), "Tick", "UInt64"),
            node_id("Line.SimTimeMs"): SimulatedOpcUaNode(node_id("Line.SimTimeMs"), "SimTimeMs", "UInt64"),
            node_id("Production.Completed"): SimulatedOpcUaNode(node_id("Production.Completed"), "Completed", "UInt64"),
            node_id("Production.Scrapped"): SimulatedOpcUaNode(node_id("Production.Scrapped"), "Scrapped", "UInt64"),
            node_id("Production.ReworkCycles"): SimulatedOpcUaNode(node_id("Production.ReworkCycles"), "ReworkCycles", "UInt64"),
            node_id("Production.InProcess"): SimulatedOpcUaNode(node_id("Production.InProcess"), "InProcess", "UInt32"),
            node_id("Faults.ActiveStations"): SimulatedOpcUaNode(node_id("Faults.ActiveStations"), "ActiveStations", "String[]"),
        }
        for station in self.line.blueprint.stations:
            prefix = f"Stations.{station.id}"
            for suffix, dtype in (
                ("Status", "String"), ("Workpiece", "String"),
                ("CycleTicks", "UInt32"), ("RemainingTicks", "UInt32"),
                ("Faulted", "Boolean"),
            ):
                identifier = node_id(f"{prefix}.{suffix}")
                nodes[identifier] = SimulatedOpcUaNode(identifier, suffix, dtype)
        for identifier in self.METHOD_ACTIONS:
            browse = identifier.rsplit(".", 1)[-1]
            nodes[identifier] = SimulatedOpcUaNode(
                identifier, browse, "Method", node_class="Method", writable=False)
        if len(nodes) > MAX_BROWSE_NODES:
            raise ValueError("simulated OPC UA namespace exceeds node limit")
        return nodes

    def browse(self) -> list[dict]:
        """Return the deterministic node inventory without touching simulation time."""
        return [self._nodes[key].to_dict() for key in sorted(self._nodes)]

    def _snapshot(self) -> dict:
        return self.line.snapshot()

    def read(self, identifier: str) -> Any:
        if not isinstance(identifier, str) or identifier not in self._nodes:
            raise ValueError("unknown simulated OPC UA node")
        if self._nodes[identifier].node_class != "Variable":
            raise ValueError("node is not readable as a variable")
        with self.lock:
            snapshot = self._snapshot()
        fixed = {
            node_id("Line.State"): snapshot["state"],
            node_id("Line.Tick"): snapshot["tick"],
            node_id("Line.SimTimeMs"): snapshot["sim_time_ms"],
            node_id("Production.Completed"): snapshot["completed"],
            node_id("Production.Scrapped"): snapshot["scrapped"],
            node_id("Production.ReworkCycles"): snapshot["rework_cycles"],
            node_id("Production.InProcess"): snapshot["in_process"],
            node_id("Faults.ActiveStations"): list(snapshot.get("fault_stations", [])),
        }
        if identifier in fixed:
            return deepcopy(fixed[identifier])
        parts = identifier.split(";s=", 1)[1].split(".")
        if len(parts) != 4 or parts[0] != ROOT or parts[1] != "Stations":
            raise ValueError("unsupported simulated OPC UA node")
        station_name, attribute = parts[2], parts[3]
        station = next((item for item in snapshot["stations"] if item["name"] == station_name), None)
        if station is None:
            raise ValueError("station no longer exists")
        mapping = {
            "Status": station["status"],
            "Workpiece": station["workpiece"] or "",
            "CycleTicks": station["cycle_ticks"],
            "RemainingTicks": station["remaining_ticks"],
            "Faulted": station["name"] in snapshot.get("fault_stations", []),
        }
        if attribute not in mapping:
            raise ValueError("unsupported simulated OPC UA node")
        return deepcopy(mapping[attribute])

    def write(self, identifier: str, value: Any) -> None:
        """Variables are deliberately read-only; control is explicit via methods."""
        if not isinstance(identifier, str) or identifier not in self._nodes:
            raise ValueError("unknown simulated OPC UA node")
        raise ValueError("simulated OPC UA variables are read-only")

    def call_method(self, identifier: str, *, station: str | None = None) -> dict:
        if not isinstance(identifier, str) or identifier not in self.METHOD_ACTIONS:
            raise ValueError("unknown simulated OPC UA method")
        action, station_required = self.METHOD_ACTIONS[identifier]
        if station_required:
            if not isinstance(station, str) or not station:
                raise ValueError("station argument required")
        elif station is not None:
            raise ValueError("method does not accept a station argument")
        with self.lock:
            self.line.control(action, station)
            result = self.line.snapshot()
        return deepcopy(result)
