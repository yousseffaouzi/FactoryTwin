"""FT-013: simultaneous station fault latches, replay and persistence."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from factorytwin.blueprint import FactoryBlueprint
from factorytwin.fault_persistence import FaultPersistentProductionLine
from factorytwin.metrics import MetricsPlan, production_metrics
from factorytwin.sim import MULTI_FAULT_TRACE_SCHEMA, ProductionLine, TRACE_SCHEMA
import factorytwin.__main__ as api


def plan():
    return FactoryBlueprint.from_dict({
        "version": 1,
        "stations": [{"id": name, "cycle_ticks": 1} for name in ("Feed", "Inspect", "Pack")],
        "connections": [{"from": "Feed", "to": "Inspect"}, {"from": "Inspect", "to": "Pack"}],
    })


class MultiFaultEngineTest(unittest.TestCase):
    def test_legacy_fault_still_rejects_second_distinct_station(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault", "Feed")
        before = deepcopy(line.export_trace())
        with self.assertRaisesRegex(ValueError, "fault already active"):
            line.control("fault", "Inspect")
        self.assertEqual(line.export_trace(), before)
        self.assertEqual(line.fault_stations, ["Feed"])
        self.assertNotEqual(line.export_trace()["schema"], MULTI_FAULT_TRACE_SCHEMA)

    def test_explicit_fault_add_supports_multiple_latches(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault_add", "Pack")
        line.control("fault_add", "Feed")
        self.assertEqual(line.fault_stations, ["Feed", "Pack"])
        self.assertEqual(line.fault_station, "Feed")
        self.assertEqual(line.state.value, "FAULT")
        statuses = {s["name"]: s["status"] for s in line.snapshot()["stations"]}
        self.assertEqual(statuses, {"Feed": "FAULT", "Inspect": "BLOCKED", "Pack": "FAULT"})
        self.assertEqual(line.export_trace()["schema"], MULTI_FAULT_TRACE_SCHEMA)

    def test_independent_clear_leaves_other_fault_latched(self):
        line = ProductionLine(blueprint=plan())
        line.step()
        before_slots = deepcopy(line.conveyor)
        line.control("fault_add", "Feed")
        line.control("fault_add", "Inspect")
        line.step()
        self.assertEqual(line.conveyor, before_slots)
        tick = line.tick
        line.control("clear_fault_station", "Feed")
        self.assertEqual(line.fault_stations, ["Inspect"])
        self.assertEqual(line.state.value, "FAULT")
        line.step()
        self.assertEqual(line.tick, tick + 1)
        self.assertEqual(line.conveyor, before_slots)
        line.control("clear_fault_station", "Inspect")
        self.assertEqual(line.state.value, "RUNNING")
        line.step()
        self.assertNotEqual(line.conveyor, before_slots)

    def test_pause_precedence_and_resume_does_not_clear_multiple_faults(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault_add", "Feed")
        line.control("fault_add", "Pack")
        line.control("pause")
        self.assertEqual(line.state.value, "PAUSED")
        line.control("resume")
        self.assertEqual(line.state.value, "FAULT")
        self.assertEqual(line.fault_stations, ["Feed", "Pack"])

    def test_legacy_clear_fault_clears_all_extended_latches(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault_add", "Feed")
        line.control("fault_add", "Pack")
        line.control("clear_fault")
        self.assertEqual(line.fault_stations, [])
        self.assertIsNone(line.fault_station)
        self.assertEqual(line.state.value, "RUNNING")
        self.assertEqual(line.operations[-1]["action"], "clear_fault")

    def test_extended_controls_are_idempotent_and_invalid_station_is_atomic(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault_add", "Inspect")
        event_count = line.event_sequence
        line.control("fault_add", "Inspect")
        self.assertEqual(line.event_sequence, event_count)
        line.control("clear_fault_station", "Feed")
        self.assertEqual(line.fault_stations, ["Inspect"])
        before = deepcopy(line.export_trace())
        with self.assertRaisesRegex(ValueError, "unknown station"):
            line.control("fault_add", "Missing")
        self.assertEqual(line.export_trace(), before)

    def test_trace_v4_roundtrip_and_continuation(self):
        line = ProductionLine(blueprint=plan())
        for _ in range(4): line.step()
        line.control("fault_add", "Feed")
        line.control("fault_add", "Pack")
        line.step()
        line.control("clear_fault_station", "Feed")
        line.step()
        trace = json.loads(json.dumps(line.export_trace()))
        self.assertEqual(trace["schema"], MULTI_FAULT_TRACE_SCHEMA)
        restored = ProductionLine.replay(trace)
        self.assertEqual(restored.export_trace(), trace)
        line.control("clear_fault_station", "Pack")
        restored.control("clear_fault_station", "Pack")
        line.step(); restored.step()
        self.assertEqual(restored.export_trace(), line.export_trace())

    def test_tampered_v4_fault_state_is_rejected(self):
        line = ProductionLine(blueprint=plan())
        line.control("fault_add", "Feed")
        trace = line.export_trace()
        changed = deepcopy(trace)
        changed["final_state"]["fault_stations"] = ["Pack"]
        with self.assertRaisesRegex(ValueError, "final state mismatch"):
            ProductionLine.replay(changed)

    def test_reset_clears_fault_session_and_returns_to_legacy_schema(self):
        line = ProductionLine()
        line.control("fault_add", "Feeder")
        self.assertEqual(line.export_trace()["schema"], MULTI_FAULT_TRACE_SCHEMA)
        line.control("reset")
        self.assertEqual(line.fault_stations, [])
        self.assertEqual(line.export_trace()["schema"], TRACE_SCHEMA)

    def test_oee_availability_tracks_all_fault_latches(self):
        line = ProductionLine(blueprint=plan())
        line.metrics_plan = MetricsPlan(True, 1)
        line.step()
        line.control("fault_add", "Feed")
        line.step()
        line.control("fault_add", "Pack")
        line.step()
        line.control("clear_fault_station", "Feed")
        line.step()
        line.control("clear_fault_station", "Pack")
        line.step()
        metrics = production_metrics(line)
        self.assertEqual(metrics["observation_ticks"], 5)
        self.assertEqual(metrics["production_enabled_ticks"], 2)
        self.assertEqual(metrics["availability"], 0.4)

    def test_trace_v4_persists_and_recovers_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "faults.sqlite3"
            line = FaultPersistentProductionLine.open(path, blueprint=plan())
            for _ in range(3): line.step()
            line.control("fault_add", "Feed")
            line.control("fault_add", "Pack")
            line.step()
            line.control("clear_fault_station", "Feed")
            expected = json.loads(json.dumps(line.export_trace()))
            restored = FaultPersistentProductionLine.open(path)
            self.assertEqual(restored.export_trace(), expected)
            self.assertEqual(restored.fault_stations, ["Pack"])


class MultiFaultApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=5)

    def setUp(self):
        with api.LOCK:
            api.SIM = ProductionLine(blueprint=plan())
            from factorytwin.streaming import SnapshotStreamHub
            api.STREAM = SnapshotStreamHub()

    def post(self, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            payload = json.dumps(body)
            conn.request("POST", "/api/control", payload, {"Content-Type":"application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_api_can_add_and_clear_selected_fault_latches(self):
        status, state = self.post({"action":"fault_add", "station":"Feed"})
        self.assertEqual(status, 200)
        self.assertEqual(state["fault_stations"], ["Feed"])
        status, state = self.post({"action":"fault_add", "station":"Pack"})
        self.assertEqual(status, 200)
        self.assertEqual(state["fault_stations"], ["Feed", "Pack"])
        status, state = self.post({"action":"clear_fault_station", "station":"Feed"})
        self.assertEqual(status, 200)
        self.assertEqual(state["fault_stations"], ["Pack"])
        self.assertEqual(state["state"], "FAULT")


if __name__ == "__main__":
    unittest.main()
