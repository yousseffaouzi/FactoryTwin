"""FT-007: topology validation, backpressure, cycles, replay and local API."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from factorytwin.blueprint import FactoryBlueprint, DEFAULT_BLUEPRINT, MAX_STATIONS
from factorytwin.sim import ProductionLine, STATIONS, CUSTOM_TRACE_SCHEMA, TRACE_SCHEMA
import factorytwin.__main__ as api


ROOT = Path(__file__).resolve().parents[1]


def plan(names=("Start", "Slow", "Exit"), cycles=(1, 2, 1)):
    return {"version": 1, "stations": [
        {"id": name, "cycle_ticks": cycle} for name, cycle in zip(names, cycles)],
        "connections": [{"from": a, "to": b} for a, b in zip(names, names[1:])]}


class BlueprintValidationTest(unittest.TestCase):
    def test_default_matches_legacy(self):
        self.assertEqual(DEFAULT_BLUEPRINT.station_ids, STATIONS)
        self.assertEqual(tuple(x.cycle_ticks for x in DEFAULT_BLUEPRINT.stations), (1, 1, 1, 1))
        self.assertEqual(ProductionLine().export_trace()["schema"], TRACE_SCHEMA)
        line = ProductionLine()
        for _ in range(7):
            line.step()
        self.assertEqual(line.completed, 3)
        self.assertEqual(line.state_data().keys(),
                         {"tick", "sim_time_ms", "state", "running", "fault_station",
                          "completed", "scrapped", "next_id", "conveyor",
                          "event_sequence", "events"})

    def test_example_json_load_and_canonical_order(self):
        bp = FactoryBlueprint.load(ROOT / "config" / "assembly_line.json")
        self.assertEqual(bp.station_ids, ("Feed", "Inspect", "Pack"))
        self.assertEqual([s.cycle_ticks for s in bp.stations], [1, 2, 1])
        self.assertEqual(FactoryBlueprint.from_dict(bp.to_dict()), bp)
        self.assertEqual([x["name"] for x in ProductionLine(blueprint=bp).snapshot()["stations"]],
                         list(bp.station_ids))

    def test_connection_input_order_does_not_affect_canonicalization(self):
        a = plan()
        b = deepcopy(a)
        b["stations"].reverse()
        b["connections"].reverse()
        self.assertEqual(FactoryBlueprint.from_dict(a), FactoryBlueprint.from_dict(b))

    def test_single_station_supported(self):
        bp = FactoryBlueprint.from_dict(plan(("Only",), (3,)))
        line = ProductionLine(blueprint=bp)
        for _ in range(4):
            line.step()
        self.assertEqual(line.completed, 1)
        self.assertEqual(line.next_id, 3)

    def test_invalid_blueprints_rejected(self):
        base = plan()
        cases = [None, [], {}, {**base, "version": True}, {**base, "version": 2},
                 {**base, "stations": []}, {**base, "connections": []},
                 {**base, "extra": "bad"},
                 {**base, "stations": [base["stations"][0]] * 3},
                 {**base, "stations": [*base["stations"], {"id": "Start", "cycle_ticks": 1}]},
                 {**base, "connections": [{"from": "Start", "to": "Unknown"}, base["connections"][1]]},
                 {**base, "connections": [{"from": "Start", "to": "Start"}, base["connections"][1]]},
                 {**base, "connections": [{"from": "Start", "to": "Slow"}] * 2},
                 {**base, "connections": [{"from": "Start", "to": "Slow"}, {"from": "Start", "to": "Exit"}]},
                 {**base, "connections": [{"from": "Start", "to": "Exit"}, {"from": "Slow", "to": "Exit"}]},
                 {**base, "connections": [{"from": "Start", "to": "Slow"}, {"from": "Slow", "to": "Start"}]},
                 {**base, "connections": [{"from": "Start", "to": "Slow"}, {"from": "Slow", "to": "Exit"}, {"from": "Exit", "to": "Start"}]},
                 {**base, "stations": [{"id": "Start", "cycle_ticks": 0}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": "Start", "cycle_ticks": -1}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": "Start", "cycle_ticks": True}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": "Start", "cycle_ticks": 10_001}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": "../X", "cycle_ticks": 1}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": "X"}, *base["stations"][1:]]},
                 {**base, "stations": [{"id": 123, "cycle_ticks": 1}, *base["stations"][1:]]},
                 {**base, "connections": [{"from": "Start", "to": "Slow", "type": "http"}, base["connections"][1]]}]
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    FactoryBlueprint.from_dict(case)

    def test_too_many_stations_rejected(self):
        many = tuple(f"S{i}" for i in range(MAX_STATIONS + 1))
        with self.assertRaises(ValueError):
            FactoryBlueprint.from_dict(plan(many, (1,) * len(many)))

    def test_file_validation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text('{"stations":[}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unable to load blueprint"):
                FactoryBlueprint.load(p)
            with self.assertRaises(ValueError):
                FactoryBlueprint.load(Path(tmp) / "absent.json")


class ConfiguredEngineTest(unittest.TestCase):
    def setUp(self):
        self.line = ProductionLine.from_blueprint(plan())

    def test_cycle_times_and_blocked_transfer(self):
        line = self.line
        for _ in range(5):
            line.step()
        self.assertEqual(line.completed, 1)
        self.assertEqual([x["id"] if x else None for x in line.conveyor],
                         ["WP-0003", "WP-0002", None])
        self.assertEqual(line.remaining_ticks, [0, 1, 0])
        self.assertEqual(line.next_id - 1,
                         line.completed + line.scrapped + line.snapshot()["in_process"])

    def test_single_slot_backpressure_preserves_workpieces(self):
        line = ProductionLine.from_blueprint(plan(("A", "B", "C"), (1, 1, 4)))
        for _ in range(25):
            line.step()
            line.validate()
            self.assertEqual(line.next_id - 1,
                             line.completed + line.scrapped + line.snapshot()["in_process"])
        self.assertGreater(line.completed, 1)
        self.assertEqual(line.scrapped, 0)
        self.assertLessEqual(line.snapshot()["in_process"], 3)

    def test_fault_pause_and_reset_keep_blueprint(self):
        line = self.line
        for _ in range(4):
            line.step()
        line.control("fault", "Slow")
        frozen = (deepcopy(line.conveyor), list(line.remaining_ticks), line.next_id)
        line.step()
        self.assertEqual((line.conveyor, line.remaining_ticks, line.next_id), frozen)
        line.control("pause")
        line.control("clear_fault")
        line.step()
        self.assertEqual((line.conveyor, line.remaining_ticks, line.next_id), frozen)
        line.control("resume")
        line.step()
        line.control("reset")
        self.assertEqual(line.blueprint.station_ids, ("Start", "Slow", "Exit"))
        self.assertEqual(line.remaining_ticks, [0, 0, 0])
        self.assertEqual(line.conveyor, [None, None, None])
        self.assertEqual(line.tick, 0)
        self.assertEqual(ProductionLine.replay(line.export_trace()).export_trace(), line.export_trace())
        with self.assertRaisesRegex(ValueError, "unknown station"):
            line.control("fault", "Processing")

    def test_custom_trace_replay_roundtrip_and_continuation(self):
        line = self.line
        for _ in range(11):
            line.step()
        line.control("pause")
        line.step()
        line.control("fault", "Exit")
        line.control("resume")
        line.step()
        line.control("clear_fault")
        for _ in range(4):
            line.step()
        trace = json.loads(json.dumps(line.export_trace()))
        self.assertEqual(trace["schema"], CUSTOM_TRACE_SCHEMA)
        self.assertEqual(trace["blueprint"], line.blueprint.to_dict())
        copy = ProductionLine.replay(trace)
        self.assertEqual(copy.export_trace(), trace)
        for obj in (line, copy):
            for _ in range(6):
                obj.step()
        self.assertEqual(copy.export_trace(), line.export_trace())

    def test_tampering_blueprint_or_remaining_rejected(self):
        for _ in range(5):
            self.line.step()
        original = self.line.export_trace()
        modified = deepcopy(original)
        modified["blueprint"]["stations"][1]["cycle_ticks"] += 1
        with self.assertRaises(ValueError):
            ProductionLine.replay(modified)
        modified = deepcopy(original)
        modified["final_state"]["remaining_ticks"][1] = 400
        with self.assertRaisesRegex(ValueError, "final state mismatch"):
            ProductionLine.replay(modified)
        modified = deepcopy(original)
        del modified["blueprint"]
        with self.assertRaisesRegex(ValueError, "invalid trace header"):
            ProductionLine.replay(modified)

    def test_zero_remaining_blocked_workpiece_is_valid(self):
        line = ProductionLine.from_blueprint(plan(("A", "B"), (1, 5)))
        for _ in range(4):
            line.step()
        self.assertEqual(line.remaining_ticks[0], 0)
        self.assertIsNotNone(line.conveyor[0])
        line.validate()

    def test_long_run_roundtrip(self):
        for _ in range(200):
            self.line.step()
        self.assertGreater(self.line.completed, 30)
        self.assertEqual(self.line.state_data(),
                         ProductionLine.replay(self.line.export_trace()).state_data())

    def test_unavailable_cycle_time_never_advances_during_pause(self):
        line = self.line
        line.step()
        before = list(line.remaining_ticks)
        line.control("pause")
        for _ in range(5):
            line.step()
        self.assertEqual(line.remaining_ticks, before)
        self.assertEqual(line.sim_time_ms, 6000)
        line.control("resume")
        line.step()
        self.assertEqual(line.snapshot()["stations"][1]["remaining_ticks"], 2)


class CustomApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_custom_snapshot_and_fault_api(self):
        with api.LOCK:
            previous = api.SIM
            api.SIM = ProductionLine.from_blueprint(plan())
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            try:
                conn.request("GET", "/api/snapshot")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read())
                self.assertEqual([s["name"] for s in payload["stations"]],
                                 ["Start", "Slow", "Exit"])
                self.assertEqual([s["cycle_ticks"] for s in payload["stations"]], [1, 2, 1])
                conn.request("POST", "/api/control", json.dumps({"action": "fault", "station": "Slow"}),
                             {"Content-Type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read())
                self.assertEqual(payload["state"], "FAULT")
                self.assertEqual(payload["stations"][1]["status"], "FAULT")
            finally:
                conn.close()
        finally:
            with api.LOCK:
                api.SIM = previous


if __name__ == "__main__":
    unittest.main()
