"""FT-014: local in-process OPC UA-style namespace adapter tests."""
from copy import deepcopy
import socket
import unittest
from unittest.mock import patch

from factorytwin.blueprint import FactoryBlueprint
from factorytwin.opcua_sim import NAMESPACE_INDEX, SimulatedOpcUaAdapter, node_id
from factorytwin.sim import ProductionLine


def plan():
    return FactoryBlueprint.from_dict({
        "version": 1,
        "stations": [{"id": "Feed", "cycle_ticks": 1},
                     {"id": "Inspect", "cycle_ticks": 2}],
        "connections": [{"from": "Feed", "to": "Inspect"}],
    })


class SimulatedOpcUaAdapterTest(unittest.TestCase):
    def setUp(self):
        self.line = ProductionLine(blueprint=plan())
        self.adapter = SimulatedOpcUaAdapter(self.line)

    def test_namespace_uses_stable_opcua_style_nodeids(self):
        nodes = self.adapter.browse()
        self.assertTrue(nodes)
        self.assertTrue(all(node["node_id"].startswith(f"ns={NAMESPACE_INDEX};s=FactoryTwin.")
                            for node in nodes))
        self.assertEqual(nodes, sorted(nodes, key=lambda n: n["node_id"]))
        self.assertTrue(all(node["writable"] is False for node in nodes))

    def test_read_is_observation_only_and_does_not_advance_tick(self):
        self.line.step()
        tick = self.line.tick
        self.assertEqual(self.adapter.read(node_id("Line.Tick")), tick)
        self.assertEqual(self.adapter.read(node_id("Line.State")), "RUNNING")
        self.assertEqual(self.line.tick, tick)

    def test_station_nodes_reflect_real_simulator_snapshot(self):
        self.line.step()
        self.assertEqual(self.adapter.read(node_id("Stations.Feed.Workpiece")), "WP-0001")
        self.assertEqual(self.adapter.read(node_id("Stations.Feed.CycleTicks")), 1)
        self.assertEqual(self.adapter.read(node_id("Stations.Inspect.CycleTicks")), 2)
        self.assertEqual(self.adapter.read(node_id("Stations.Feed.Status")), "RUNNING")

    def test_method_controls_delegate_to_validated_engine(self):
        state = self.adapter.call_method(node_id("Methods.Pause"))
        self.assertEqual(state["state"], "PAUSED")
        self.assertFalse(self.line.running)
        state = self.adapter.call_method(node_id("Methods.Resume"))
        self.assertEqual(state["state"], "RUNNING")
        state = self.adapter.call_method(node_id("Methods.Fault"), station="Inspect")
        self.assertEqual(state["fault_stations"], ["Inspect"])
        self.assertEqual(self.adapter.read(node_id("Stations.Inspect.Faulted")), True)

    def test_extended_multi_fault_methods_work_without_bypass(self):
        self.adapter.call_method(node_id("Methods.AddFault"), station="Feed")
        self.adapter.call_method(node_id("Methods.AddFault"), station="Inspect")
        before = deepcopy(self.line.conveyor)
        self.line.step()
        self.assertEqual(self.line.conveyor, before)
        self.assertEqual(self.adapter.read(node_id("Faults.ActiveStations")), ["Feed", "Inspect"])
        state = self.adapter.call_method(node_id("Methods.ClearFaultStation"), station="Feed")
        self.assertEqual(state["state"], "FAULT")
        self.assertEqual(state["fault_stations"], ["Inspect"])

    def test_variables_are_read_only(self):
        before = deepcopy(self.line.export_trace())
        with self.assertRaisesRegex(ValueError, "read-only"):
            self.adapter.write(node_id("Production.Completed"), 999)
        self.assertEqual(self.line.export_trace(), before)

    def test_invalid_nodes_methods_and_arguments_are_atomic(self):
        before = deepcopy(self.line.export_trace())
        with self.assertRaises(ValueError):
            self.adapter.read("ns=2;s=FactoryTwin.Unknown")
        with self.assertRaises(ValueError):
            self.adapter.call_method(node_id("Methods.Fault"))
        with self.assertRaises(ValueError):
            self.adapter.call_method(node_id("Methods.Pause"), station="Feed")
        with self.assertRaises(ValueError):
            self.adapter.call_method("ns=2;s=FactoryTwin.Methods.NotReal")
        self.assertEqual(self.line.export_trace(), before)

    def test_reset_method_preserves_blueprint_and_resets_session(self):
        self.line.step(); self.line.step()
        state = self.adapter.call_method(node_id("Methods.Reset"))
        self.assertEqual(state["tick"], 0)
        self.assertEqual([s["name"] for s in state["stations"]], ["Feed", "Inspect"])
        self.assertEqual(self.adapter.read(node_id("Production.Completed")), 0)

    def test_adapter_never_opens_a_socket(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            adapter = SimulatedOpcUaAdapter(self.line)
            adapter.browse()
            adapter.read(node_id("Line.Tick"))
            adapter.call_method(node_id("Methods.Pause"))

    def test_browse_inventory_contains_variables_and_methods(self):
        inventory = {node["node_id"]: node for node in self.adapter.browse()}
        self.assertEqual(inventory[node_id("Line.State")]["node_class"], "Variable")
        self.assertEqual(inventory[node_id("Methods.Reset")]["node_class"], "Method")
        self.assertEqual(inventory[node_id("Stations.Inspect.RemainingTicks")]["data_type"], "UInt32")


if __name__ == "__main__":
    unittest.main()
